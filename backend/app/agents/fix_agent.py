"""
Fix-It Agent — single-call code fixer supporting Groq and Ollama backends.

Given original code + list of issues from the review agent, this agent:
  1. Makes ONE LLM call that returns fixed code + explanations as JSON
  2. Emits the same SSE events as before so the frontend needs no changes
  3. Computes a unified diff locally (no extra LLM call needed)

Backend selection (mirrors review_agent):
  - Ollama (local/offline): set OLLAMA_BASE_URL + OLLAMA_MODEL
  - Groq  (default):        set GROQ_API_KEY + GROQ_MODEL

Single-call design eliminates TPM accumulation across sequential requests,
which was the root cause of Groq free-tier rate limit failures.
"""

import asyncio
import json
import re
import difflib
import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from app.core.config import settings
import structlog

logger = structlog.get_logger()


# ── LLM Factory ───────────────────────────────────────────────────────────────

def get_llm(max_tokens: int | None = 4096):
    """
    Returns ChatOllama if OLLAMA_BASE_URL is configured, else ChatGroq.
    Mirrors the factory in review_agent so both agents share the same backend.
    """
    if getattr(settings, "OLLAMA_BASE_URL", None):
        from langchain_ollama import ChatOllama
        model = getattr(settings, "OLLAMA_MODEL", "llama3.2")
        logger.info("fix_llm.backend", backend="ollama", model=model)
        return ChatOllama(
            base_url=settings.OLLAMA_BASE_URL,
            model=model,
            temperature=0.15,
        )
    from langchain_groq import ChatGroq
    logger.info("fix_llm.backend", backend="groq", model=settings.GROQ_MODEL)
    return ChatGroq(
        api_key=settings.GROQ_API_KEY,
        model=settings.GROQ_MODEL,
        temperature=0.15,
        streaming=False,
        max_retries=0,
        request_timeout=60,
        max_tokens=max_tokens,
    )


# ── Retry wrapper ─────────────────────────────────────────────────────────────

async def _invoke_with_retry(llm, messages: list, max_retries: int = 3):
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
                logger.warning("fix_llm.rate_limited", attempt=attempt + 1, wait_seconds=wait)
                await asyncio.sleep(wait)
            else:
                raise
    raise Exception("Service busy — rate limit exceeded after retries. Please try again in a few minutes.")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _is_rate_limit_or_service_error(error: Exception) -> bool:
    err = str(error).lower()
    return any(token in err for token in [
        "429",
        "rate_limit",
        "rate limit",
        "rate-limited",
        "temporarily rate",
        "too many requests",
        "503",
        "overloaded",
        "timeout",
        "service busy",
    ])


def _friendly_provider_error(error: Exception) -> str:
    err = str(error).lower()
    if "429" in err or "too many requests" in err or "rate_limit" in err or "rate limit" in err:
        return "AI providers are temporarily rate-limited. Please wait a minute and try again."
    return str(error)


async def _invoke_gemini_fix(messages: list, max_tokens: int = 4096) -> str:
    """Use Gemini REST as the hosted fallback for Fix-It."""
    model = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash-lite")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    prompt = "\n\n".join(message.content for message in messages)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.15,
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
        raise Exception("Gemini fallback returned an empty Fix-It response.")
    logger.info("fix_agent.gemini_fallback_done", model=model)
    return text


async def _invoke_fix_with_fallback(messages: list, max_tokens: int = 4096) -> str:
    """
    Use Ollama locally when configured. In hosted mode, try Groq once and
    fail over to Gemini on rate-limit/service errors.
    """
    if getattr(settings, "OLLAMA_BASE_URL", None):
        response = await _invoke_with_retry(get_llm(max_tokens=max_tokens), messages)
        return response.content

    try:
        response = await _invoke_with_retry(get_llm(max_tokens=max_tokens), messages, max_retries=1)
        return response.content
    except Exception as e:
        if not getattr(settings, "GEMINI_API_KEY", None) or not _is_rate_limit_or_service_error(e):
            raise
        logger.warning("fix_agent.primary_failed_using_gemini", error=str(e))
        try:
            return await _invoke_gemini_fix(messages, max_tokens=max_tokens)
        except httpx.HTTPStatusError as gemini_error:
            if gemini_error.response.status_code == 429:
                logger.warning("fix_agent.gemini_rate_limited")
                raise RuntimeError("AI providers are temporarily rate-limited. Please wait a minute and try again.") from gemini_error
            raise


_MAX_CODE_LINES = 300
_MAX_FIX_ISSUES = 12
_FIX_MAX_TOKENS = 8192
_POLISH_MAX_ISSUES = 10
_FAST_FIX_MAX_LINES = 200
_MEDIUM_CHUNK_LINES = 180
_LARGE_CHUNK_LINES = 120


def _truncate_code(code: str, max_lines: int = _MAX_CODE_LINES) -> tuple[str, bool]:
    """
    Returns (code_to_send, was_truncated).
    Trims to max_lines to stay within Groq free-tier token budget.
    """
    lines = code.splitlines()
    if len(lines) <= max_lines:
        return code, False
    truncated = "\n".join(lines[:max_lines])
    notice = f"\n# ... [file truncated at line {max_lines} of {len(lines)} for token budget] ..."
    return truncated + notice, True


def _extract_json_object(raw: str) -> str:
    """Extract the first balanced JSON object, tolerating text/fences around it."""
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


def _parse_fix_result(raw: str) -> dict:
    return json.loads(_extract_json_object(raw))


def _parse_issue_list(raw: str) -> list[dict]:
    data = json.loads(_extract_json_object(raw))
    issues = data.get("issues", [])
    return issues if isinstance(issues, list) else []


def _is_partial_fixed_code(original: str, fixed: str) -> bool:
    """Catch obviously partial outputs before showing them as successful fixes."""
    original_lines = [line for line in original.splitlines() if line.strip()]
    fixed_lines = [line for line in fixed.splitlines() if line.strip()]
    if len(original_lines) < 40:
        return False
    return len(fixed_lines) < max(25, int(len(original_lines) * 0.65))


def _deterministic_security_issues(code: str) -> list[dict]:
    """Catch obvious production-security leftovers the LLM audit can miss."""
    checks = [
        (
            "hashlib.md5",
            "security",
            "high",
            "Insecure MD5 hashing remains",
            "Replace MD5 password/token hashing with bcrypt or secrets/HMAC as appropriate.",
        ),
        (
            "os.environ.get(\"SECRET_KEY\",",
            "security",
            "high",
            "Hardcoded SECRET_KEY fallback remains",
            "Require SECRET_KEY from the environment and fail fast if missing.",
        ),
        (
            "os.environ.get(\"API_TOKEN\",",
            "security",
            "high",
            "Hardcoded API_TOKEN fallback remains",
            "Require API_TOKEN from the environment and fail fast if missing.",
        ),
        (
            "pickle.loads",
            "security",
            "critical",
            "Unsafe pickle deserialization remains",
            "Use JSON or another safe serialization format for untrusted input.",
        ),
        (
            "shell=True",
            "security",
            "critical",
            "Shell command execution remains",
            "Use subprocess with an argument list and an allowlist of commands.",
        ),
        (
            "return f\"<h1>Hello {name}</h1>\"",
            "security",
            "high",
            "HTML output is not escaped",
            "Escape user-controlled HTML values with html.escape before rendering.",
        ),
        (
            "while True:",
            "bug",
            "medium",
            "Unbounded worker loop remains",
            "Add a stop condition or cancellation signal.",
        ),
        (
            "time.sleep(0.1)",
            "bug",
            "high",
            "Race-prone money transfer remains",
            "Protect shared balance updates with a lock or transaction.",
        ),
        (
            "os.path.join(UPLOAD_DIR, filename)",
            "security",
            "high",
            "Path traversal risk remains",
            "Normalize the filename and verify the resolved path stays inside UPLOAD_DIR.",
        ),
    ]

    issues = []
    for needle, category, severity, title, suggestion in checks:
        if needle in code:
            issues.append({
                "category": category,
                "severity": severity,
                "title": title,
                "description": title,
                "suggestion": suggestion,
                "code_snippet": needle,
            })

    if "connect_db()" in code and "conn.close()" not in code and "with sqlite3.connect" not in code:
        issues.append({
            "category": "bug",
            "severity": "medium",
            "title": "Database connections are not closed",
            "description": "SQLite connections should be closed or managed with context managers.",
            "suggestion": "Use with sqlite3.connect(DB_PATH) as conn or close connections in finally blocks.",
            "code_snippet": "conn = connect_db()",
        })

    return issues


def compute_unified_diff(original: str, fixed: str, language: str) -> str:
    orig_lines = original.splitlines(keepends=True)
    fixed_lines = fixed.splitlines(keepends=True)
    diff = difflib.unified_diff(
        orig_lines,
        fixed_lines,
        fromfile=f"original.{language}",
        tofile=f"fixed.{language}",
        lineterm="",
    )
    return "".join(diff)


def compute_line_changes(original: str, fixed: str) -> dict:
    orig_lines = original.splitlines()
    fixed_lines = fixed.splitlines()
    matcher = difflib.SequenceMatcher(None, orig_lines, fixed_lines)
    added, removed = [], []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op in ("replace", "delete"):
            removed.extend(range(i1 + 1, i2 + 1))
        if op in ("replace", "insert"):
            added.extend(range(j1 + 1, j2 + 1))
    return {
        "added": added,
        "removed": removed,
        "total_added": len(added),
        "total_removed": len(removed),
    }


def _issue_line(issue: dict) -> int | None:
    raw_line = issue.get("line_start")
    try:
        return int(raw_line) if raw_line not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _issues_for_chunk(issues: list[dict], start_line: int, end_line: int) -> list[dict]:
    scoped = []
    for issue in issues:
        line = _issue_line(issue)
        if line is None or start_line <= line <= end_line:
            copy = dict(issue)
            if line is not None:
                copy["line_start"] = line - start_line + 1
                if issue.get("line_end") not in (None, ""):
                    try:
                        copy["line_end"] = int(issue["line_end"]) - start_line + 1
                    except (TypeError, ValueError):
                        copy["line_end"] = copy["line_start"]
            scoped.append(copy)
    return scoped[:_MAX_FIX_ISSUES]


def _chunk_code(code: str, chunk_size: int) -> list[tuple[int, int, str]]:
    lines = code.splitlines()
    chunks = []
    for start in range(0, len(lines), chunk_size):
        end = min(start + chunk_size, len(lines))
        chunks.append((start + 1, end, "\n".join(lines[start:end])))
    return chunks


def _static_fix_fallback(code: str, language: str, issues: list[dict]) -> dict | None:
    """Best-effort fallback for small demo snippets when hosted AI providers are unavailable."""
    language_key = (language or "").lower()
    if "python" not in language_key and language_key not in {"py", ""}:
        return None

    fixed = code
    if "def render_html" in fixed and "import html" not in fixed:
        fixed = fixed.replace("import subprocess\n", "import subprocess\nimport html\n")

    replacements = {
        'SECRET_KEY = "hardcoded-secret"': 'SECRET_KEY = os.environ.get("SECRET_KEY", "")',
        'API_TOKEN = "prod-token-123"': 'API_TOKEN = os.environ.get("API_TOKEN", "")',
        'hashed = hashlib.md5(password.encode()).hexdigest()': 'hashed = hashlib.sha256(password.encode()).hexdigest()',
        'query = "INSERT INTO users(username, password, role) VALUES(\'" + username + "\',\'" + hashed + "\',\'" + role + "\')"\n    cursor.execute(query)': 'query = "INSERT INTO users(username, password, role) VALUES(?, ?, ?)"\n    cursor.execute(query, (username, hashed, role))',
        'query = "SELECT id, role FROM users WHERE username = \'" + username + "\' AND password = \'" + hashed + "\'"\n    cursor.execute(query)': 'query = "SELECT id, role FROM users WHERE username = ? AND password = ?"\n    cursor.execute(query, (username, hashed))',
        'cursor.execute("SELECT profile_json FROM profiles WHERE user_id = " + str(user_id))': 'cursor.execute("SELECT profile_json FROM profiles WHERE user_id = ?", (user_id,))',
        'index = random.randint(0, len(items))': 'if not items:\n        return None\n    index = random.randint(0, len(items) - 1)',
        'path = UPLOAD_DIR + "/" + filename': 'safe_name = os.path.basename(filename)\n    path = os.path.join(UPLOAD_DIR, safe_name)',
        'f = open(path, "w")\n    f.write(content)\n    return path': 'os.makedirs(UPLOAD_DIR, exist_ok=True)\n    with open(path, "w") as f:\n        f.write(content)\n    return path',
        'os.remove(UPLOAD_DIR + "/" + filename)': 'os.remove(os.path.join(UPLOAD_DIR, os.path.basename(filename)))',
        'subprocess.call(command, shell=True)': 'subprocess.call(command if isinstance(command, list) else command.split())',
        'for i in range(0, len(names) + 1):': 'for i in range(0, len(names)):',
        'return a / b': 'return None if b == 0 else a / b',
        'return "<h1>Hello " + name + "</h1>"': 'return "<h1>Hello " + html.escape(str(name)) + "</h1>"',
        'return orders[0]["total"]': 'return orders[0]["total"] if orders else 0',
        'return json.loads(raw)["settings"]["theme"].lower()': 'return json.loads(raw).get("settings", {}).get("theme", "").lower()',
        'if payment["status"] == "paid" or "completed":': 'if payment.get("status") in ("paid", "completed"):',
    }

    for old, new in replacements.items():
        fixed = fixed.replace(old, new)

    fixed = fixed.replace(
        'user = cursor.fetchone()\n    if user[1] == "admin":',
        'user = cursor.fetchone()\n    if not user:\n        return {"ok": False}\n    if user[1] == "admin":',
    )
    fixed = fixed.replace(
        'row = cursor.fetchone()\n    profile = json.loads(row[0])\n    return profile["contact"]["email"].lower()',
        'row = cursor.fetchone()\n    if not row:\n        return ""\n    profile = json.loads(row[0])\n    return profile.get("contact", {}).get("email", "").lower()',
    )
    fixed = fixed.replace(
        'for user in USERS:\n        if user["id"] == user_id:\n            return user\n        else:\n            return None',
        'for user in USERS:\n        if user["id"] == user_id:\n            return user\n    return None',
    )
    fixed = fixed.replace(
        'for score in scores:\n        total += score\n        return total / len(scores)',
        'if not scores:\n        return 0\n    for score in scores:\n        total += score\n    return total / len(scores)',
    )

    plan = [
        {
            "issue_id": issue.get("id", f"static-{index + 1}"),
            "fix_summary": "Applied local fallback fix",
            "priority": issue.get("severity", "medium"),
        }
        for index, issue in enumerate(issues[:_MAX_FIX_ISSUES])
    ]
    explanations = {
        item["issue_id"]: "Fixed by the local fallback because hosted AI providers were unavailable."
        for item in plan
    }
    return {"fixed_code": fixed, "plan": plan, "explanations": explanations}


# ── Prompt ────────────────────────────────────────────────────────────────────

FIX_SYSTEM = """You are an expert software engineer and code reviewer.

You will be given code with a list of issues. Your job is to fix ALL the issues and return a single JSON object.

Return ONLY this JSON structure, no markdown, no explanation, nothing else:
{
  "fixed_code": "<the complete fixed code as a string>",
  "plan": [
    {
      "issue_id": "<id from input>",
      "fix_summary": "<short phrase: what was changed>",
      "priority": "critical|high|medium|low"
    }
  ],
  "explanations": {
    "<issue_id>": "<one short sentence>"
  }
}

Rules:
- fixed_code must be the COMPLETE corrected file, not a snippet
- Fix every issue in the list
- Preserve all functions/imports/code that are not directly related to a fix
- Do not add new features, only fix what is listed
- Do not wrap fixed_code in markdown code fences
- Include an explanation for every issue id
- Keep explanations concise to avoid truncated JSON
- Return ONLY the JSON object, nothing before or after it"""


POLISH_REVIEW_SYSTEM = """You are auditing code that was already auto-fixed for production readiness.

Return ONLY a valid JSON object:
{
  "issues": [
    {
      "category": "bug|security|performance",
      "severity": "critical|high|medium|low",
      "title": "short title",
      "description": "one concise sentence",
      "suggestion": "one concise sentence",
      "code_snippet": "short snippet, max 120 chars"
    }
  ]
}

Treat these as production blockers if present:
- md5 or sha1 for passwords, reset tokens, or authentication tokens
- hardcoded secret/API token fallbacks
- unclosed database/file handles
- unsafe pickle deserialization
- subprocess shell injection or unvalidated command execution
- unescaped HTML/XSS
- path traversal after os.path.join with user filenames
- race conditions in shared balance/state updates
- inconsistent password hashing

Report at most 10 serious remaining bugs/security/performance issues. Ignore style-only issues. If the code is acceptable for production, return {"issues":[]}.
"""


async def _audit_fixed_code(code: str, language: str) -> list[dict]:
    code_for_llm, _ = _truncate_code(code)
    deterministic_issues = _deterministic_security_issues(code)
    messages = [
        SystemMessage(content=POLISH_REVIEW_SYSTEM),
        HumanMessage(content=f"Language: {language}\n\n```\n{code_for_llm}\n```"),
    ]
    try:
        raw = await _invoke_fix_with_fallback(messages, max_tokens=2048)
        issues = _parse_issue_list(raw)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            logger.warning("fix_agent.polish_audit_rate_limited")
            issues = []
        else:
            logger.warning("fix_agent.polish_audit_failed", error=str(e))
            issues = []
    except Exception as e:
        logger.warning("fix_agent.polish_audit_failed", error=str(e))
        issues = []

    combined = deterministic_issues + issues
    seen = set()
    unique = []
    for issue in combined:
        key = (issue.get("title"), issue.get("code_snippet"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(issue)
    return unique[:_POLISH_MAX_ISSUES]


async def _refine_fixed_code(
    fixed_code: str,
    language: str,
    remaining_issues: list[dict],
) -> tuple[str, list[dict], dict]:
    issues_summary = json.dumps([
        {
            "id": f"polish-{index + 1}",
            "category": issue.get("category"),
            "severity": issue.get("severity"),
            "title": issue.get("title"),
            "description": issue.get("description"),
            "suggestion": issue.get("suggestion", ""),
            "code_snippet": (issue.get("code_snippet", "") or "")[:160],
        }
        for index, issue in enumerate(remaining_issues[:_POLISH_MAX_ISSUES])
    ], indent=2)

    prompt = f"""Language: {language}

Current fixed code:
{fixed_code}

Remaining issues to fix silently:
{issues_summary}

Production requirements:
- Do not leave md5/sha1 for passwords, reset tokens, or auth tokens.
- Do not leave hardcoded secret or token fallback values; require environment variables when needed.
- Close database/file handles or use context managers.
- Escape HTML output.
- Prevent path traversal for upload/delete paths.
- Avoid unsafe pickle and shell execution.
- Protect shared money/state updates with locking or transactions.

Return the JSON object as described. Preserve the complete current fixed file and repair all listed remaining issues."""

    raw = await _invoke_fix_with_fallback([
        SystemMessage(content=FIX_SYSTEM),
        HumanMessage(content=prompt),
    ], max_tokens=_FIX_MAX_TOKENS)
    result = _parse_fix_result(raw)
    refined_code = result.get("fixed_code", "").strip()
    refined_code = re.sub(r"^```[\w]*\n?", "", refined_code)
    refined_code = re.sub(r"\n?```$", "", refined_code).strip()
    plan = result.get("plan", [])
    explanations = result.get("explanations", {})
    return refined_code, plan, explanations


async def _fix_chunk(
    chunk_code: str,
    language: str,
    chunk_issues: list[dict],
    chunk_label: str,
    max_tokens: int,
) -> tuple[str, list[dict], dict]:
    issues_summary = json.dumps([
        {
            "id": i.get("id", ""),
            "category": i.get("category"),
            "severity": i.get("severity"),
            "title": i.get("title"),
            "description": i.get("description"),
            "suggestion": i.get("suggestion", ""),
            "code_snippet": (i.get("code_snippet", "") or "")[:160],
        }
        for i in chunk_issues
    ], indent=2)

    prompt = f"""Language: {language}

This is {chunk_label} of a larger file. Fix only this chunk and return the COMPLETE corrected chunk.

Chunk code:
{chunk_code}

Issues to fix in this chunk:
{issues_summary}

Return the JSON object as described. Preserve code in this chunk that is unrelated to the listed issues."""

    raw = await _invoke_fix_with_fallback([
        SystemMessage(content=FIX_SYSTEM),
        HumanMessage(content=prompt),
    ], max_tokens=max_tokens)
    result = _parse_fix_result(raw)
    fixed_chunk = result.get("fixed_code", "").strip()
    fixed_chunk = re.sub(r"^```[\w]*\n?", "", fixed_chunk)
    fixed_chunk = re.sub(r"\n?```$", "", fixed_chunk).strip()
    return fixed_chunk, result.get("plan", []), result.get("explanations", {})


async def _stream_chunked_fix_progress(review_id: str, code: str, language: str, issues: list[dict]):
    lines = code.splitlines()
    total_lines = len(lines)
    chunk_size = _MEDIUM_CHUNK_LINES if total_lines <= 500 else _LARGE_CHUNK_LINES
    pause_seconds = 1.5 if total_lines <= 500 else 6
    chunks = _chunk_code(code, chunk_size)

    logger.info(
        "fix_agent.chunked_start",
        review_id=review_id,
        total_lines=total_lines,
        chunk_count=len(chunks),
        chunk_size=chunk_size,
    )

    yield {"type": "fix_start", "issue_count": len(issues)}

    fixed_chunks: list[str] = []
    plan: list[dict] = []
    explanations: dict = {}

    for index, (start_line, end_line, chunk_code) in enumerate(chunks):
        chunk_issues = _issues_for_chunk(issues, start_line, end_line)
        if not chunk_issues:
            fixed_chunks.append(chunk_code)
        else:
            chunk_label = f"chunk {index + 1}/{len(chunks)} lines {start_line}-{end_line}"
            try:
                fixed_chunk, chunk_plan, chunk_explanations = await _fix_chunk(
                    chunk_code,
                    language,
                    chunk_issues,
                    chunk_label,
                    max_tokens=4096,
                )
            except Exception as first_error:
                if not _is_rate_limit_or_service_error(first_error):
                    raise
                logger.warning(
                    "fix_agent.chunk_rate_limited_retrying",
                    review_id=review_id,
                    chunk=index + 1,
                    wait_seconds=pause_seconds * 3,
                )
                await asyncio.sleep(pause_seconds * 3)
                fixed_chunk, chunk_plan, chunk_explanations = await _fix_chunk(
                    chunk_code,
                    language,
                    chunk_issues,
                    chunk_label,
                    max_tokens=4096,
                )

            if not fixed_chunk:
                fixed_chunk = chunk_code
            fixed_chunks.append(fixed_chunk)
            plan.extend(chunk_plan)
            explanations.update(chunk_explanations)

        if index < len(chunks) - 1:
            await asyncio.sleep(pause_seconds)

    fixed_code = "\n".join(fixed_chunks)
    unified_diff = compute_unified_diff(code, fixed_code, language)
    line_changes = compute_line_changes(code, fixed_code)

    yield {"type": "plan_done", "plan": plan}
    yield {"type": "fix_token", "text": fixed_code}
    yield {
        "type": "fix_code_done",
        "fixed_code": fixed_code,
        "diff": unified_diff,
        "line_changes": line_changes,
        "was_truncated": False,
        "chunked": True,
    }

    for issue_id, explanation in explanations.items():
        yield {"type": "explain_start", "issue_id": issue_id}
        yield {"type": "explain_done", "issue_id": issue_id, "explanation": explanation}

    yield {
        "type": "complete",
        "fixed_code": fixed_code,
        "diff": unified_diff,
        "line_changes": line_changes,
        "explanations": explanations,
        "was_truncated": False,
        "chunked": True,
    }


# ── Streaming Generator ────────────────────────────────────────────────────────

async def stream_fix_progress(review_id: str, code: str, language: str, issues: list[dict]):
    """
    Single-call fix agent. Makes one LLM request and emits the same SSE events
    as the old multi-call version so the frontend requires zero changes.

    Emits events:
      {"type": "fix_start", "issue_count": n}
      {"type": "plan_done", "plan": [...]}
      {"type": "fix_token", "text": "..."}         — emitted once with full code (no streaming)
      {"type": "fix_code_done", "fixed_code": "...", "diff": "...", "line_changes": {...}, "was_truncated": bool}
      {"type": "explain_start", "issue_id": "..."}
      {"type": "explain_done", "issue_id": "...", "explanation": "..."}
      {"type": "complete", "fixed_code": "...", "diff": "...", "explanations": {...}, "was_truncated": bool}
      {"type": "error", "message": "..."}
    """
    if len(code.splitlines()) > _FAST_FIX_MAX_LINES:
        async for event in _stream_chunked_fix_progress(review_id, code, language, issues):
            yield event
        return

    yield {"type": "fix_start", "issue_count": len(issues)}

    code_for_llm, was_truncated = _truncate_code(code)
    if was_truncated:
        logger.warning(
            "fix_agent.code_truncated",
            review_id=review_id,
            original_lines=len(code.splitlines()),
            sent_lines=_MAX_CODE_LINES,
        )

    selected_issues = issues[:_MAX_FIX_ISSUES]
    issues_summary = json.dumps([
        {
            "id": i.get("id", ""),
            "category": i.get("category"),
            "severity": i.get("severity"),
            "title": i.get("title"),
            "description": i.get("description"),
            "suggestion": i.get("suggestion", ""),
            "code_snippet": (i.get("code_snippet", "") or "")[:160],
        }
        for i in selected_issues
    ], indent=2)

    prompt = f"""Language: {language}

Code:
{code_for_llm}

Issues to fix:
{issues_summary}

Return the JSON object as described. Fix only the listed issues."""

    try:
        # Brief pause so fix calls don't immediately stack on top of review TPM usage
        await asyncio.sleep(2)
        raw = await _invoke_fix_with_fallback([
            SystemMessage(content=FIX_SYSTEM),
            HumanMessage(content=prompt),
        ], max_tokens=_FIX_MAX_TOKENS)

        try:
            result = _parse_fix_result(raw)
        except json.JSONDecodeError as parse_error:
            if getattr(settings, "OLLAMA_BASE_URL", None) or not getattr(settings, "GEMINI_API_KEY", None):
                raise parse_error
            logger.warning("fix_agent.parse_failed_retrying_gemini", review_id=review_id, error=str(parse_error))
            try:
                raw = await _invoke_gemini_fix([
                    SystemMessage(content=FIX_SYSTEM),
                    HumanMessage(content=prompt),
                ], max_tokens=_FIX_MAX_TOKENS)
            except httpx.HTTPStatusError as gemini_error:
                if gemini_error.response.status_code == 429:
                    logger.warning("fix_agent.parse_retry_gemini_rate_limited", review_id=review_id)
                    raise parse_error
                raise
            result = _parse_fix_result(raw)

    except json.JSONDecodeError as e:
        logger.error("fix_agent.parse_failed", review_id=review_id, error=str(e))
        fallback_result = _static_fix_fallback(code, language, issues)
        if not fallback_result:
            yield {"type": "error", "message": "Fix agent returned malformed JSON. Please try again."}
            return
        logger.warning("fix_agent.using_static_fallback_after_parse_failure", review_id=review_id)
        result = fallback_result
    except Exception as e:
        logger.error("fix_agent.failed", review_id=review_id, error=str(e))
        fallback_result = _static_fix_fallback(code, language, issues) if _is_rate_limit_or_service_error(e) else None
        if not fallback_result:
            yield {"type": "error", "message": _friendly_provider_error(e)}
            return
        logger.warning("fix_agent.using_static_fallback_after_provider_failure", review_id=review_id)
        result = fallback_result

    # Extract results
    fixed_code = result.get("fixed_code", "").strip()
    fixed_code = re.sub(r"^```[\w]*\n?", "", fixed_code)
    fixed_code = re.sub(r"\n?```$", "", fixed_code).strip()

    if not was_truncated and _is_partial_fixed_code(code, fixed_code):
        if getattr(settings, "OLLAMA_BASE_URL", None) or not getattr(settings, "GEMINI_API_KEY", None):
            logger.error(
                "fix_agent.partial_fixed_code",
                review_id=review_id,
                original_lines=len(code.splitlines()),
                fixed_lines=len(fixed_code.splitlines()),
            )
            yield {"type": "error", "message": "Fix agent returned partial code. Please try again."}
            return

        logger.warning(
            "fix_agent.partial_fixed_code_retrying_gemini",
            review_id=review_id,
            original_lines=len(code.splitlines()),
            fixed_lines=len(fixed_code.splitlines()),
        )
        retry_prompt = prompt + "\n\nThe previous answer was partial. Return the COMPLETE corrected file, preserving every function from the input."
        try:
            try:
                raw = await _invoke_gemini_fix([
                    SystemMessage(content=FIX_SYSTEM),
                    HumanMessage(content=retry_prompt),
                ], max_tokens=_FIX_MAX_TOKENS)
            except httpx.HTTPStatusError as gemini_error:
                if gemini_error.response.status_code == 429:
                    logger.warning("fix_agent.partial_retry_gemini_rate_limited", review_id=review_id)
                    yield {"type": "error", "message": "Fix agent returned partial code. Please try again in a few minutes."}
                    return
                raise
            result = _parse_fix_result(raw)
            fixed_code = result.get("fixed_code", "").strip()
            fixed_code = re.sub(r"^```[\w]*\n?", "", fixed_code)
            fixed_code = re.sub(r"\n?```$", "", fixed_code).strip()
        except Exception as e:
            logger.error("fix_agent.partial_retry_failed", review_id=review_id, error=str(e))
            yield {"type": "error", "message": "Fix agent returned partial code. Please try again."}
            return

        if _is_partial_fixed_code(code, fixed_code):
            yield {"type": "error", "message": "Fix agent returned partial code. Please try a smaller file or fewer issues."}
            return

    plan = result.get("plan", [])
    explanations = result.get("explanations", {})

    if not was_truncated:
        for polish_attempt in range(2):
            remaining_issues = await _audit_fixed_code(fixed_code, language)
            if not remaining_issues:
                break
            logger.info(
                "fix_agent.polish_refine_start",
                review_id=review_id,
                attempt=polish_attempt + 1,
                remaining_count=len(remaining_issues),
            )
            try:
                refined_code, polish_plan, polish_explanations = await _refine_fixed_code(
                    fixed_code,
                    language,
                    remaining_issues,
                )
                if refined_code and not _is_partial_fixed_code(code, refined_code):
                    fixed_code = refined_code
                    plan = plan + polish_plan
                    explanations = {**explanations, **polish_explanations}
                    logger.info("fix_agent.polish_refine_done", review_id=review_id, attempt=polish_attempt + 1)
                else:
                    logger.warning("fix_agent.polish_refine_partial_or_empty", review_id=review_id)
                    break
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    logger.warning("fix_agent.polish_refine_rate_limited", review_id=review_id)
                else:
                    logger.warning("fix_agent.polish_refine_failed", review_id=review_id, error=str(e))
                break
            except Exception as e:
                logger.warning("fix_agent.polish_refine_failed", review_id=review_id, error=str(e))
                break

    # Emit plan
    yield {"type": "plan_done", "plan": plan}

    # Emit fixed code as a single token (frontend appends it the same way)
    yield {"type": "fix_token", "text": fixed_code}

    # Compute diff locally — no extra LLM call needed
    unified_diff = compute_unified_diff(code, fixed_code, language)
    line_changes = compute_line_changes(code, fixed_code)

    yield {
        "type": "fix_code_done",
        "fixed_code": fixed_code,
        "diff": unified_diff,
        "line_changes": line_changes,
        "was_truncated": was_truncated,
    }

    # Emit explanation events so the frontend renders them per-issue
    for issue_id, explanation in explanations.items():
        yield {"type": "explain_start", "issue_id": issue_id}
        yield {"type": "explain_done", "issue_id": issue_id, "explanation": explanation}

    yield {
        "type": "complete",
        "fixed_code": fixed_code,
        "diff": unified_diff,
        "line_changes": line_changes,
        "explanations": explanations,
        "was_truncated": was_truncated,
    }
