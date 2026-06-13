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

import json
import re
import difflib
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
        max_retries=2,
        request_timeout=60,
        max_tokens=max_tokens,
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

_MAX_CODE_LINES = 80


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
      "fix_summary": "<one sentence: what was changed>",
      "priority": "critical|high|medium|low"
    }
  ],
  "explanations": {
    "<issue_id>": "<2-3 sentence explanation: what was wrong, what changed, why it matters>"
  }
}

Rules:
- fixed_code must be the COMPLETE corrected file, not a snippet
- Fix every issue in the list
- Do not add new features, only fix what is listed
- Do not wrap fixed_code in markdown code fences
- Include an explanation for every issue id
- Return ONLY the JSON object, nothing before or after it"""


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

    issues_summary = json.dumps([
        {
            "id": i.get("id", ""),
            "category": i.get("category"),
            "severity": i.get("severity"),
            "title": i.get("title"),
            "description": i.get("description"),
            "suggestion": i.get("suggestion", ""),
            "code_snippet": i.get("code_snippet", ""),
        }
        for i in issues
    ], indent=2)

    prompt = f"""Language: {language}

Code:
{code_for_llm}

Issues to fix:
{issues_summary}

Return the JSON object as described."""

    try:
        llm = get_llm(max_tokens=4096)
        response = await llm.ainvoke([
            SystemMessage(content=FIX_SYSTEM),
            HumanMessage(content=prompt),
        ])

        raw = response.content.strip()
        # Strip accidental markdown fences
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw).strip()

        result = json.loads(raw)

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

    plan = result.get("plan", [])
    explanations = result.get("explanations", {})

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