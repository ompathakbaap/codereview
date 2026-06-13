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
                wait = 2 ** attempt * 5  # 5s, 10s, 20s
                logger.warning("llm.rate_limited", attempt=attempt + 1, wait_seconds=wait)
                await asyncio.sleep(wait)
            else:
                raise
    raise Exception("Service busy — rate limit exceeded after retries. Please try again in a few minutes.")


def _is_rate_limit_or_service_error(error: Exception) -> bool:
    err = str(error).lower()
    return any(token in err for token in ["429", "rate_limit", "rate limit", "503", "overloaded", "timeout"])


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


def _truncate_code_for_review(code: str) -> tuple[str, bool]:
    """Trim large submissions so the active LLM backend stays within token limits."""
    if len(code) <= _MAX_REVIEW_CHARS:
        return code, False
    return (
        code[:_MAX_REVIEW_CHARS]
        + f"\n\n... [code truncated at {_MAX_REVIEW_CHARS} characters for token budget] ...",
        True,
    )


REVIEW_SYSTEM = """You are a senior software engineer performing a concise code review.

Review the code for bugs, security problems, style/maintainability issues, and performance issues in ONE pass.

Return ONLY a valid JSON object, no markdown:
{
  "summary": "2-3 sentence summary of what the code does",
  "issues": [
    {
      "category": "bug|security|style|performance",
      "severity": "critical|high|medium|low|info",
      "line_start": <line number as integer or null>,
      "line_end": <line number as integer or null>,
      "title": "short title",
      "description": "what is wrong and why it matters",
      "suggestion": "specific remediation",
      "code_snippet": "the exact relevant code"
    }
  ]
}

Prioritize real issues that would matter in a review demo. Do not invent issues. If no issues are found, return an empty issues array.
"""


def _parse_review_result(raw: str) -> tuple[str, list[dict]]:
    """Parse the single-call review JSON."""
    try:
        clean = raw.strip()
        clean = re.sub(r"^```(?:json)?\s*", "", clean)
        clean = re.sub(r"\s*```$", "", clean).strip()
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
        return "", []


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
        llm = get_llm(max_tokens=2048)
        response = await _invoke_with_retry(llm, messages)
        return _parse_review_result(response.content)
    except Exception as e:
        if getattr(settings, "OLLAMA_BASE_URL", None):
            raise
        if not getattr(settings, "GEMINI_API_KEY", None) or not _is_rate_limit_or_service_error(e):
            raise
        logger.warning("review_agent.primary_failed_using_gemini", error=str(e))
        raw = await _invoke_gemini_review(messages, max_tokens=2048)
        return _parse_review_result(raw)


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
