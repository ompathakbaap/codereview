"""
LangGraph-powered AI Code Review Agent

Supports two backends (selected via environment variables):
  - Groq  (default): set GROQ_API_KEY + GROQ_MODEL
  - Ollama (local):  set OLLAMA_BASE_URL (e.g. http://localhost:11434) + OLLAMA_MODEL

Graph flow:
  START -> analyze_structure -> [bug_check, security_check, style_check, perf_check] -> aggregate -> END
Each node runs in parallel; results are merged in aggregate.
"""
import json
import re
import asyncio
import httpx
from typing import TypedDict, Annotated, List
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.language_models.chat_models import BaseChatModel
from app.core.config import settings
import structlog

logger = structlog.get_logger()


# -- State --------------------------------------------------------------------

def merge_issues(a: list, b: list) -> list:
    return a + b


class ReviewState(TypedDict):
    code: str
    language: str
    review_id: str
    structure_summary: str
    issues: Annotated[List[dict], merge_issues]
    status: str
    error: str


# -- LLM factory --------------------------------------------------------------

def get_llm(streaming: bool = False, max_tokens: int | None = None) -> BaseChatModel:
    """
    Returns ChatOllama if OLLAMA_BASE_URL is configured, else ChatGroq.
    To use Ollama: set OLLAMA_BASE_URL=http://localhost:11434 and OLLAMA_MODEL=llama3.2
    """
    if getattr(settings, "OLLAMA_BASE_URL", None):
        from langchain_ollama import ChatOllama
        model = getattr(settings, "OLLAMA_MODEL", "llama3.2")
        logger.info("llm.backend", backend="ollama", model=model)
        return ChatOllama(
            base_url=settings.OLLAMA_BASE_URL,
            model=model,
            temperature=0.1,
        )
    else:
        from langchain_groq import ChatGroq
        logger.info("llm.backend", backend="groq", model=settings.GROQ_MODEL)
        groq_kwargs = {"max_tokens": max_tokens} if max_tokens is not None else {}
        return ChatGroq(
            api_key=settings.GROQ_API_KEY,
            model=settings.GROQ_MODEL,
            temperature=0.1,
            streaming=streaming,
            max_retries=0,
            request_timeout=45,
            **groq_kwargs,
        )


# -- Retry wrapper ------------------------------------------------------------

async def _invoke_with_retry(llm: BaseChatModel, messages: list, max_retries: int = 3):
    """Invoke LLM with exponential backoff on 429 rate limit errors."""
    for attempt in range(max_retries):
        try:
            return await llm.ainvoke(messages)
        except Exception as e:
            err = str(e)
            if "429" in err or "rate_limit" in err.lower():
                if attempt >= max_retries - 1:
                    break
                wait = 2 ** attempt * 5  # 5s, 10s, 20s
                logger.warning("llm.rate_limited", attempt=attempt + 1, wait_seconds=wait)
                await asyncio.sleep(wait)
            else:
                raise
    raise Exception("Service busy — rate limit exceeded after retries. Please try again in a few minutes.")


def _is_rate_limit_or_service_error(error: Exception) -> bool:
    err = str(error).lower()
    return any(token in err for token in ["429", "rate_limit", "rate limit", "503", "overloaded", "timeout", "malformed json"])


# -- Issue parser -------------------------------------------------------------

def _parse_issues(raw: str, category: str) -> list[dict]:
    """Safely parse JSON array of issues from LLM output."""
    try:
        clean = raw.strip()
        clean = re.sub(r"```json\s*|```\s*", "", clean).strip()
        data = json.loads(clean)
        issues = data if isinstance(data, list) else data.get("issues", [])
        for issue in issues:
            issue["category"] = category
        return issues
    except Exception as e:
        logger.warning("parse_issues_failed", category=category, error=str(e))
        return []


_MAX_REVIEW_CHARS = 10_000
_REVIEW_MAX_TOKENS = 6144
_REVIEW_MAX_ISSUES = 20


def _truncate_code_for_review(code: str) -> tuple[str, bool]:
    """Trim large submissions so the active LLM backend stays within token limits."""
    if len(code) <= _MAX_REVIEW_CHARS:
        return code, False
    return (
        code[:_MAX_REVIEW_CHARS]
        + f"\n\n... [code truncated at {_MAX_REVIEW_CHARS} characters for token budget] ...",
        True,
    )


def _extract_json_object(raw: str) -> str:
    """Extract the first balanced JSON object, tolerating fences or extra text."""
    clean = raw.strip()
    clean = re.sub(r"^```(?:json)?\s*", "", clean)
    clean = re.sub(r"\s*```$", "", clean).strip()

    start = clean.find("{")
    if start == -1:
        raise json.JSONDecodeError("No JSON object found", clean, 0)

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(clean)):
        char = clean[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return clean[start:index + 1]

    raise json.JSONDecodeError("Unterminated JSON object", clean, start)


REVIEW_SYSTEM = """You are a senior software engineer performing a concise code review.

Review the code for bugs, security problems, style/maintainability issues, and performance issues in ONE pass.

Return ONLY a valid JSON object, no markdown:
{
  "summary": "1 sentence summary of what the code does",
  "issues": [
    {
      "category": "bug|security|style|performance",
      "severity": "critical|high|medium|low|info",
      "line_start": <line number as integer or null>,
      "line_end": <line number as integer or null>,
      "title": "short title",
      "description": "one concise sentence",
      "suggestion": "one concise sentence",
      "code_snippet": "short snippet, max 120 chars"
    }
  ]
}

Return at most 20 issues. Prioritize real bugs/security issues that would matter in a review demo. Keep all fields short. Do not invent issues. If no issues are found, return an empty issues array.
"""


def _parse_review_result(raw: str) -> tuple[str, list[dict]]:
    """Parse the single-call review JSON."""
    try:
        clean = _extract_json_object(raw)
        data = json.loads(clean)
        summary = data.get("summary", "")
        issues = data.get("issues", [])
        if not isinstance(issues, list):
            issues = []
        for issue in issues:
            issue["category"] = issue.get("category", "bug")
        return summary, issues
    except Exception as e:
        logger.warning("parse_review_result_failed", error=str(e))
        raise ValueError("Review model returned malformed JSON.") from e


def _line_number_for(code: str, needle: str) -> int | None:
    for index, line in enumerate(code.splitlines(), start=1):
        if needle in line:
            return index
    return None


def _static_issue(code: str, needle: str, category: str, severity: str, title: str, description: str, suggestion: str) -> dict:
    line = _line_number_for(code, needle)
    return {
        "category": category,
        "severity": severity,
        "line_start": line,
        "line_end": line,
        "title": title,
        "description": description,
        "suggestion": suggestion,
        "code_snippet": needle,
    }


def _deterministic_review(code: str, language: str) -> tuple[str, list[dict]]:
    """Language-aware fallback review for demo reliability when model JSON is malformed."""
    language_key = (language or "").lower()
    checks = [
        ("api_key", "security", "high", "Possible hardcoded API key", "A secret-like identifier appears in source.", "Move secrets to environment variables."),
        ("password", "security", "medium", "Password handling needs review", "Password-related code is present and may require secure hashing/storage.", "Use a proven password hashing library and avoid plaintext storage."),
        ("secret", "security", "high", "Possible hardcoded secret", "A secret-like value appears in source.", "Move secrets to environment variables or a secret manager."),
        ("token", "security", "medium", "Token handling needs review", "Token-related code is present and may be hardcoded or weakly validated.", "Use secure token generation and constant-time comparison where appropriate."),
        ("eval(", "security", "critical", "Dynamic code execution", "eval can execute attacker-controlled code.", "Avoid eval and use safe parsers/allowlists."),
        ("exec(", "security", "critical", "Dynamic code execution", "exec can execute attacker-controlled code.", "Avoid exec and use safe parsers/allowlists."),
        ("shell=True", "security", "critical", "Command injection risk", "Shell execution can run attacker-controlled commands.", "Use argument arrays and validate allowed commands."),
        ("innerHTML", "security", "high", "Potential XSS", "Writing to innerHTML can execute untrusted markup.", "Use textContent or sanitize trusted HTML."),
        ("dangerouslySetInnerHTML", "security", "high", "Potential XSS", "dangerouslySetInnerHTML can render untrusted HTML.", "Sanitize HTML or avoid raw HTML rendering."),
        ("SELECT *", "performance", "low", "Broad database selection", "Selecting all columns can waste bandwidth and expose data.", "Select only required columns."),
        (" OR \"", "bug", "medium", "Suspicious always-true OR condition", "A standalone string or expression in an OR condition can make it always true.", "Compare the variable on both sides or use membership checks."),
        (" OR '", "bug", "medium", "Suspicious always-true OR condition", "A standalone string or expression in an OR condition can make it always true.", "Compare the variable on both sides or use membership checks."),
        ("password = \"", "security", "high", "Hardcoded password", "A password-like value appears hardcoded.", "Move credentials to a secret manager or environment variable."),
        ("api_token = \"", "security", "high", "Hardcoded API token", "An API token appears hardcoded.", "Move API tokens to a secret manager or environment variable."),
    ]

    if "python" in language_key or language_key in {"py", ""}:
        checks.extend([
            ("hashlib.md5", "security", "high", "Insecure MD5 hashing", "MD5 is unsafe for passwords or auth tokens.", "Use bcrypt/argon2 for passwords and secrets/HMAC for tokens."),
            ("pickle.loads", "security", "critical", "Unsafe deserialization", "pickle.loads can execute code with untrusted data.", "Use JSON or another safe format."),
            ("random.randint(0, len(", "bug", "medium", "Off-by-one random index", "randint includes the upper bound.", "Use random.choice after checking the list is non-empty."),
            ("while True:", "bug", "medium", "Unbounded loop", "The loop has no visible stop condition.", "Add cancellation or a clear break condition."),
            ("return a / b", "bug", "medium", "Division by zero risk", "The divisor is not checked.", "Validate the divisor before dividing."),
            ("return total / len(scores)", "bug", "medium", "Average can divide by zero", "The average divides by the list length without confirming it is non-empty.", "Return a default or raise a controlled error for empty input."),
            ("return orders[0]", "bug", "medium", "Unsafe first item access", "Accessing index 0 can crash on empty lists.", "Check the list before indexing."),
            ("profile[\"contact\"][\"email\"]", "bug", "medium", "Unsafe nested dictionary access", "Missing nested keys can crash.", "Use safe access and validate required fields."),
            ("except:", "bug", "low", "Bare except hides errors", "A bare except can swallow important failures.", "Catch specific exception types."),
            ("open(path, \"w\")", "bug", "medium", "File handle may leak", "Opening files without a context manager can leak handles.", "Use with open(...) as f."),
            ("for i in range(0, len(names) + 1)", "bug", "medium", "Off-by-one loop", "The loop accesses one element beyond the list.", "Use range(len(names))."),
        ])
        if "conn = connect_db()" in code and "conn.close()" not in code and "with sqlite3.connect" not in code:
            checks.append(("conn = connect_db()", "bug", "medium", "Database connections are not closed", "Connections can leak resources.", "Use context managers or close connections in finally blocks."))
        if "\" + username + \"" in code or "\" + str(user_id)" in code or "\" + keyword + \"" in code:
            checks.append(("cursor.execute", "security", "critical", "SQL injection risk", "SQL queries appear to use string concatenation.", "Use parameterized queries."))

    if any(lang in language_key for lang in ["javascript", "typescript", "js", "ts", "tsx", "jsx"]):
        checks.extend([
            ("localStorage", "security", "medium", "Sensitive data in localStorage", "localStorage is accessible to injected scripts.", "Avoid storing secrets in localStorage."),
            ("Math.random", "security", "medium", "Weak randomness", "Math.random is not cryptographically secure.", "Use crypto.getRandomValues for security-sensitive randomness."),
            ("JSON.parse(", "bug", "low", "JSON parse can throw", "JSON.parse may crash without error handling.", "Wrap parsing in try/catch for untrusted input."),
            ("crypto.createHash(\"md5\")", "security", "high", "Insecure MD5 hashing", "MD5 is unsafe for passwords or auth tokens.", "Use bcrypt/argon2 for passwords."),
            ("child_process.exec", "security", "critical", "Command injection risk", "child_process.exec can execute attacker-controlled commands.", "Use execFile/spawn with validated arguments."),
            ("fs.writeFileSync(path", "security", "high", "Unsafe file write path", "User-controlled paths can cause path traversal.", "Normalize and validate paths inside the upload directory."),
            ("fs.unlinkSync(\"uploads/\" + filename)", "security", "high", "Unsafe file deletion path", "User-controlled filenames can delete unintended files.", "Normalize and validate paths inside the upload directory."),
            ("rows[0]", "bug", "medium", "Unchecked first row access", "Accessing rows[0] can crash when no rows are returned.", "Check rows.length before indexing."),
            ("scores.length", "bug", "medium", "Division by zero/empty average risk", "Average calculation does not handle empty arrays correctly.", "Return a default or error for empty arrays."),
            ("items[index].name", "bug", "medium", "Unsafe random item access", "The random index can point outside the array or items can be empty.", "Use bounds checks and Math.floor(Math.random() * items.length)."),
            ("payment.status === \"paid\" || \"completed\"", "bug", "medium", "Always-true condition", "The string literal makes the condition truthy for every payment.", "Use ['paid', 'completed'].includes(payment.status)."),
            ("return null;", "bug", "low", "Early return inside loop", "Returning null inside the loop can stop searching too early.", "Return null after the loop finishes."),
            ("i <= names.length", "bug", "medium", "Off-by-one loop", "The loop accesses one element past the array end.", "Use i < names.length."),
            ("return a / b", "bug", "medium", "Division by zero risk", "The divisor is not checked.", "Validate b before dividing."),
            ("orders[0].total", "bug", "medium", "Unsafe first order access", "Accessing the first order can crash when orders is empty.", "Check orders.length first."),
            ("headers[\"user-agent\"].split", "bug", "medium", "Unsafe header access", "Missing user-agent header can crash.", "Use a default string before splitting."),
            ("DB_PASSWORD = \"", "security", "high", "Hardcoded database password", "Database credentials are hardcoded.", "Load credentials from environment variables."),
            ("JWT_SECRET = \"", "security", "high", "Hardcoded JWT secret", "JWT signing secrets are hardcoded.", "Load JWT secrets from a secret manager."),
            ("API_TOKEN = \"", "security", "high", "Hardcoded API token", "API tokens are hardcoded.", "Load tokens from environment variables."),
            ("db.query(query", "security", "high", "SQL injection risk", "A query string is executed directly and may include user input.", "Use parameterized queries/placeholders."),
            ("fs.readFileSync(path", "security", "medium", "Unsafe file read path", "User-controlled file paths can read unintended files.", "Validate and constrain file paths."),
            ("requestCounts[ip] = requestCounts[ip] + 1", "bug", "medium", "NaN rate limit counter", "Incrementing undefined produces NaN.", "Initialize counters with a default value."),
            ("setTimeout(() =>", "bug", "medium", "Async state update race", "Delayed shared-state updates can race with other operations.", "Use atomic updates or locking/transactions."),
        ])

    if "java" in language_key:
        checks.extend([
            ("MessageDigest.getInstance(\"MD5\")", "security", "high", "Insecure MD5 hashing", "MD5 is unsafe for passwords or auth tokens.", "Use bcrypt/argon2/PBKDF2 with salt and work factor."),
            ("Runtime.getRuntime().exec", "security", "critical", "Command injection risk", "Executing commands from code can be unsafe.", "Validate commands and avoid shell execution."),
            ("Statement statement", "security", "high", "SQL injection risk", "Raw SQL statements can concatenate user input.", "Use PreparedStatement."),
            ("catch (Exception", "bug", "medium", "Overbroad exception handling", "Catching all exceptions can hide failures.", "Catch specific exception types."),
            ("System.out.println", "security", "low", "Potential sensitive logging", "Printing data directly can leak sensitive values.", "Use structured logging and avoid secrets."),
            ("new Random()", "security", "medium", "Weak randomness", "java.util.Random is not secure for sensitive use.", "Use SecureRandom for security-sensitive randomness."),
        ])

    issues = []
    lowered_code = code.lower()
    for needle, category, severity, title, description, suggestion in checks:
        if needle.lower() in lowered_code:
            issues.append(_static_issue(code, needle, category, severity, title, description, suggestion))

    summary = "Static fallback review found likely issues after AI review output could not be parsed."
    return summary, issues[:_REVIEW_MAX_ISSUES]


def _merge_static_findings(code: str, language: str, issues: list[dict], max_issues: int = _REVIEW_MAX_ISSUES) -> list[dict]:
    _, static_issues = _deterministic_review(code, language)
    merged = list(issues)
    seen = {
        (
            (issue.get("title") or "").lower(),
            str(issue.get("line_start") or ""),
            (issue.get("code_snippet") or "").lower(),
        )
        for issue in merged
    }
    for issue in static_issues:
        key = (
            (issue.get("title") or "").lower(),
            str(issue.get("line_start") or ""),
            (issue.get("code_snippet") or "").lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(issue)
        if len(merged) >= max_issues:
            break
    return merged


async def review_all_once(code: str, language: str) -> tuple[str, list[dict]]:
    code_for_llm, was_truncated = _truncate_code_for_review(code)
    if was_truncated:
        logger.warning(
            "review_agent.code_truncated",
            original_chars=len(code),
            sent_chars=len(code_for_llm),
        )

    messages = [
        SystemMessage(content=REVIEW_SYSTEM),
        HumanMessage(content=f"Language: {language}\n\n```\n{code_for_llm}\n```"),
    ]

    try:
        llm = get_llm(max_tokens=_REVIEW_MAX_TOKENS)
        groq_retries = 3 if getattr(settings, "OLLAMA_BASE_URL", None) else 1
        response = await _invoke_with_retry(llm, messages, max_retries=groq_retries)
        summary, issues = _parse_review_result(response.content)
        return summary, _merge_static_findings(code_for_llm, language, issues)
    except Exception as e:
        if getattr(settings, "OLLAMA_BASE_URL", None):
            raise
        if not getattr(settings, "GEMINI_API_KEY", None) or not _is_rate_limit_or_service_error(e):
            raise
        logger.warning("review_agent.primary_failed_using_gemini", error=str(e))
        try:
            raw = await _invoke_gemini_review(messages, max_tokens=_REVIEW_MAX_TOKENS)
        except httpx.HTTPStatusError as gemini_error:
            if gemini_error.response.status_code == 429:
                logger.warning("review_agent.gemini_rate_limited_using_static_fallback")
                return _deterministic_review(code_for_llm, language)
            raise
        try:
            summary, issues = _parse_review_result(raw)
            return summary, _merge_static_findings(code_for_llm, language, issues)
        except ValueError as parse_error:
            logger.warning("review_agent.gemini_parse_failed_retrying_compact", error=str(parse_error))
            compact_messages = [
                SystemMessage(content=REVIEW_SYSTEM + "\nUse extremely compact JSON. No field may exceed 80 characters."),
                HumanMessage(content=f"Language: {language}\n\n```\n{code_for_llm}\n```"),
            ]
            try:
                raw = await _invoke_gemini_review(compact_messages, max_tokens=2048)
            except httpx.HTTPStatusError as gemini_error:
                if gemini_error.response.status_code == 429:
                    logger.warning("review_agent.gemini_compact_rate_limited_using_static_fallback")
                    return _deterministic_review(code_for_llm, language)
                raise
            try:
                summary, issues = _parse_review_result(raw)
                return summary, _merge_static_findings(code_for_llm, language, issues)
            except ValueError as final_parse_error:
                logger.warning(
                    "review_agent.all_model_parses_failed_using_static_fallback",
                    error=str(final_parse_error),
                    language=language,
                )
                return _deterministic_review(code_for_llm, language)


async def _invoke_gemini_review(messages: list, max_tokens: int = 2048) -> str:
    """Use Gemini REST as a hosted fallback without adding another SDK."""
    model = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash-lite")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    prompt = "\n\n".join(message.content for message in messages)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
        },
    }
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": settings.GEMINI_API_KEY,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    parts = (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [])
    )
    text = "".join(part.get("text", "") for part in parts)
    if not text:
        raise Exception("Gemini fallback returned an empty response.")
    logger.info("review_agent.gemini_fallback_done", model=model)
    return text


# -- Node: Analyze Structure --------------------------------------------------

async def analyze_structure(state: ReviewState) -> dict:
    llm = get_llm()
    messages = [
        SystemMessage(content="You are a senior software engineer. Briefly summarize what this code does in 2-3 sentences. Be concise."),
        HumanMessage(content=f"Language: {state['language']}\n\n```\n{state['code']}\n```"),
    ]
    response = await _invoke_with_retry(llm, messages)
    return {"structure_summary": response.content, "status": "running"}


# -- Node: Bug Check ----------------------------------------------------------

BUG_SYSTEM = """You are an expert bug hunter. Your job is to find EVERY bug, crash, and logic error in the code — do not skip any.

Look specifically for ALL of the following:
- CRASH BUGS: division by zero, index out of bounds, calling methods on None/null, empty list/dict access
- LOGIC BUGS: return statement inside a loop (exits too early), wrong operator (= vs ==), off-by-one errors, incorrect conditionals
- EXCEPTION HANDLING: bare `except:` or `except Exception:` that swallows errors silently, missing try/except around risky operations, catching too broadly (e.g. catching KeyboardInterrupt)
- RESOURCE LEAKS: files opened but never closed (not using `with`), database connections never closed, sockets never closed
- NULL/NONE ERRORS: no existence check before dict key access with `[]`, no check before `.get()` chained calls
- UNREACHABLE CODE: code after a return/break/continue, conditions that can never be true
- TYPE ERRORS: adding incompatible types, passing wrong type to a function
- INFINITE LOOPS: while True with no guaranteed exit, missing break condition
- CONCURRENCY BUGS: shared mutable state, race conditions

Be thorough. If there are 10 bugs, report all 10. Do NOT merge multiple bugs into one. Do NOT skip a bug because it seems minor.

Respond ONLY with a valid JSON array (no markdown, no explanation). Each element:
{
  "severity": "critical|high|medium|low",
  "line_start": <line number as integer or null>,
  "line_end": <line number as integer or null>,
  "title": "short title",
  "description": "what the bug is and why it causes a problem",
  "suggestion": "exact fix with corrected code if possible",
  "code_snippet": "the exact buggy lines from the code"
}

If no bugs found, return [].
"""

async def bug_check(state: ReviewState) -> dict:
    llm = get_llm()
    messages = [
        SystemMessage(content=BUG_SYSTEM),
        HumanMessage(content=f"Language: {state['language']}\n\n```\n{state['code']}\n```"),
    ]
    response = await _invoke_with_retry(llm, messages)
    issues = _parse_issues(response.content, "bug")
    logger.info("bug_check.done", count=len(issues))
    return {"issues": issues}


# -- Node: Security Check -----------------------------------------------------

SECURITY_SYSTEM = """You are a security code auditor (OWASP expert). Check for: SQL injection, XSS, insecure deserialization, hardcoded secrets/credentials, insecure random, path traversal, SSRF, broken auth, unvalidated input, and other OWASP Top 10 issues.

Respond ONLY with a valid JSON array (no markdown, no explanation). Each element:
{
  "severity": "critical|high|medium|low",
  "line_start": "line number or null",
  "line_end": "line number or null",
  "title": "short title",
  "description": "security risk explanation",
  "suggestion": "how to remediate",
  "code_snippet": "relevant code snippet"
}

If no issues found, return [].
"""

async def security_check(state: ReviewState) -> dict:
    llm = get_llm()
    messages = [
        SystemMessage(content=SECURITY_SYSTEM),
        HumanMessage(content=f"Language: {state['language']}\n\n```\n{state['code']}\n```"),
    ]
    response = await _invoke_with_retry(llm, messages)
    issues = _parse_issues(response.content, "security")
    logger.info("security_check.done", count=len(issues))
    return {"issues": issues}


# -- Node: Style Check --------------------------------------------------------

STYLE_SYSTEM = """You are a code style and maintainability reviewer. Check for: naming conventions, function length, code duplication (DRY), missing documentation, overly complex logic, poor abstractions, and language-specific best practices.

Respond ONLY with a valid JSON array (no markdown, no explanation). Each element:
{
  "severity": "medium|low|info",
  "line_start": "line number or null",
  "line_end": "line number or null",
  "title": "short title",
  "description": "style issue explanation",
  "suggestion": "how to improve",
  "code_snippet": "relevant code snippet"
}

If no issues found, return [].
"""

async def style_check(state: ReviewState) -> dict:
    llm = get_llm()
    messages = [
        SystemMessage(content=STYLE_SYSTEM),
        HumanMessage(content=f"Language: {state['language']}\n\n```\n{state['code']}\n```"),
    ]
    response = await _invoke_with_retry(llm, messages)
    issues = _parse_issues(response.content, "style")
    logger.info("style_check.done", count=len(issues))
    return {"issues": issues}


# -- Node: Performance Check --------------------------------------------------

PERF_SYSTEM = """You are a performance optimization expert. Check for: N+1 queries, unnecessary loops, missing caching, inefficient data structures, blocking I/O in async code, memory leaks, and algorithmic complexity issues.

Respond ONLY with a valid JSON array (no markdown, no explanation). Each element:
{
  "severity": "high|medium|low",
  "line_start": "line number or null",
  "line_end": "line number or null",
  "title": "short title",
  "description": "performance issue explanation",
  "suggestion": "how to optimize",
  "code_snippet": "relevant code snippet"
}

If no issues found, return [].
"""

async def performance_check(state: ReviewState) -> dict:
    llm = get_llm()
    messages = [
        SystemMessage(content=PERF_SYSTEM),
        HumanMessage(content=f"Language: {state['language']}\n\n```\n{state['code']}\n```"),
    ]
    response = await _invoke_with_retry(llm, messages)
    issues = _parse_issues(response.content, "performance")
    logger.info("performance_check.done", count=len(issues))
    return {"issues": issues}


# -- Node: Aggregate ----------------------------------------------------------

async def aggregate(state: ReviewState) -> dict:
    return {"status": "complete"}


# -- Build Graph --------------------------------------------------------------

def build_review_graph() -> StateGraph:
    graph = StateGraph(ReviewState)

    graph.add_node("analyze_structure", analyze_structure)
    graph.add_node("bug_check", bug_check)
    graph.add_node("security_check", security_check)
    graph.add_node("performance_check", performance_check)
    graph.add_node("aggregate", aggregate)

    graph.set_entry_point("analyze_structure")

    graph.add_edge("analyze_structure", "bug_check")
    graph.add_edge("bug_check", "security_check")
    graph.add_edge("security_check", "performance_check")
    graph.add_edge("performance_check", "aggregate")

    graph.add_edge("aggregate", END)

    return graph.compile()


# Singleton compiled graph
review_graph = build_review_graph()


async def run_review(review_id: str, code: str, language: str) -> ReviewState:
    """Run the review pipeline with one LLM call on the active backend."""
    summary, issues = await review_all_once(code, language)
    return {
        "code": code,
        "language": language,
        "review_id": review_id,
        "structure_summary": summary,
        "issues": issues,
        "status": "complete",
        "error": "",
    }


# -- SSE Streaming ------------------------------------------------------------

_NODE_LABELS = {
    "analyze_structure": "Analyzing structure",
    "bug_check": "Checking for bugs",
    "security_check": "Auditing security",
    "style_check": "Reviewing style",
    "performance_check": "Profiling performance",
    "aggregate": "Aggregating results",
}

_NODE_SYSTEMS = {
    "bug_check": BUG_SYSTEM,
    "security_check": SECURITY_SYSTEM,
    "style_check": STYLE_SYSTEM,
    "performance_check": PERF_SYSTEM,
}


async def _stream_node(node: str, code: str, language: str):
    """
    Stream tokens from a single review node.
    Falls back gracefully on rate limit errors.
    """
    llm = get_llm(streaming=True)
    system = _NODE_SYSTEMS.get(node, "")
    messages = [
        SystemMessage(content=system),
        HumanMessage(content=f"Language: {language}\n\n```\n{code}\n```"),
    ]

    label = _NODE_LABELS.get(node, node)
    yield {"type": "node_start", "node": node, "label": label}

    full_text = ""

    try:
        async for chunk in llm.astream(messages):
            token = chunk.content
            if token:
                full_text += token
                yield {"type": "token", "node": node, "text": token}
    except Exception as e:
        if "429" in str(e) or "rate_limit" in str(e).lower():
            # Retry without streaming on rate limit
            response = await _invoke_with_retry(get_llm(), messages)
            full_text = response.content
            yield {"type": "token", "node": node, "text": full_text}
        else:
            raise

    issues = _parse_issues(full_text, node.replace("_check", ""))
    yield {"type": "node_done", "node": node, "issue_count": len(issues), "issues": issues}


async def stream_review_progress(review_id: str, code: str, language: str):
    """
    Async generator for SSE endpoint.
    Emits the same node-shaped progress events while using one LLM request.
    """
    yield {"type": "node_start", "node": "analyze_structure", "label": _NODE_LABELS["analyze_structure"]}
    summary, all_issues = await review_all_once(code, language)
    yield {"type": "node_done", "node": "analyze_structure", "issue_count": 0, "summary": summary}

    node_categories = {
        "bug_check": "bug",
        "security_check": "security",
        "style_check": "style",
        "performance_check": "performance",
    }

    for node, category in node_categories.items():
        yield {"type": "node_start", "node": node, "label": _NODE_LABELS[node]}
        node_issues = [issue for issue in all_issues if issue.get("category") == category]
        yield {
            "type": "node_done",
            "node": node,
            "issue_count": len(node_issues),
            "issues": node_issues,
        }

    yield {"type": "complete", "issue_count": len(all_issues), "issues": all_issues}
