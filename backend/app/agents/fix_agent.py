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
    return any(token in err for token in ["429", "rate_limit", "rate limit", "503", "overloaded", "timeout", "service busy"])


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
        return await _invoke_gemini_fix(messages, max_tokens=max_tokens)


_MAX_CODE_LINES = 300
_MAX_FIX_ISSUES = 12
_FIX_MAX_TOKENS = 8192
_POLISH_MAX_ISSUES = 6


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


POLISH_REVIEW_SYSTEM = """You are auditing code that was already auto-fixed.

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

Report at most 6 serious remaining bugs/security/performance issues. Ignore style-only issues. If the code is acceptable, return {"issues":[]}.
"""


async def _audit_fixed_code(code: str, language: str) -> list[dict]:
    code_for_llm, _ = _truncate_code(code)
    messages = [
        SystemMessage(content=POLISH_REVIEW_SYSTEM),
        HumanMessage(content=f"Language: {language}\n\n```\n{code_for_llm}\n```"),
    ]
    try:
        raw = await _invoke_fix_with_fallback(messages, max_tokens=2048)
        issues = _parse_issue_list(raw)
        return issues[:_POLISH_MAX_ISSUES]
    except Exception as e:
        logger.warning("fix_agent.polish_audit_failed", error=str(e))
        return []


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

Return the JSON object as described. Preserve the complete current fixed file and only repair the listed remaining issues."""

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
            raw = await _invoke_gemini_fix([
                SystemMessage(content=FIX_SYSTEM),
                HumanMessage(content=prompt),
            ], max_tokens=_FIX_MAX_TOKENS)
            result = _parse_fix_result(raw)

    except json.JSONDecodeError as e:
        logger.error("fix_agent.parse_failed", review_id=review_id, error=str(e))
        yield {"type": "error", "message": "Fix agent returned malformed JSON. Please try again."}
        return
    except Exception as e:
        logger.error("fix_agent.failed", review_id=review_id, error=str(e))
        yield {"type": "error", "message": str(e)}
        return

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
            raw = await _invoke_gemini_fix([
                SystemMessage(content=FIX_SYSTEM),
                HumanMessage(content=retry_prompt),
            ], max_tokens=_FIX_MAX_TOKENS)
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
        remaining_issues = await _audit_fixed_code(fixed_code, language)
        if remaining_issues:
            logger.info(
                "fix_agent.polish_refine_start",
                review_id=review_id,
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
                    logger.info("fix_agent.polish_refine_done", review_id=review_id)
                else:
                    logger.warning("fix_agent.polish_refine_partial_or_empty", review_id=review_id)
            except Exception as e:
                logger.warning("fix_agent.polish_refine_failed", review_id=review_id, error=str(e))

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
