"""
Fix-It Agent — Groq-powered code fixer.

Given original code + list of issues from the review agent, this agent:
  1. Streams a complete fixed version of the code
  2. For each issue, streams a targeted explanation of what changed and why
  3. Emits a unified diff so the frontend can render a side-by-side view

Graph flow:
  START → plan_fixes → generate_fixed_code → explain_changes → END

All nodes use Groq (llama-3.3-70b-versatile), same as review_agent.
"""

import json
import re
import difflib
from typing import TypedDict, Annotated, List
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from app.core.config import settings
import structlog

logger = structlog.get_logger()


# ── Helpers ────────────────────────────────────────────────────────────────────

def get_llm(streaming: bool = False) -> ChatGroq:
    return ChatGroq(
        api_key=settings.GROQ_API_KEY,
        model=settings.GROQ_MODEL,
        temperature=0.15,
        streaming=streaming,
    )


def compute_unified_diff(original: str, fixed: str, language: str) -> str:
    """Compute a unified diff between original and fixed code."""
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
    """
    Returns a summary of which lines changed:
      { "added": [line_numbers], "removed": [line_numbers], "total_added": n, "total_removed": n }
    """
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


# ── Prompts ────────────────────────────────────────────────────────────────────

PLAN_SYSTEM = """You are a senior software engineer performing a code fix review.

Given a list of issues found in code, output a concise JSON array describing the fixes you will make.
Each element must be:
{
  "issue_id": "the issue id from input",
  "fix_summary": "one sentence: what will be changed",
  "priority": "critical|high|medium|low"
}

Order by priority (critical first). Return ONLY the JSON array, no markdown, no explanation."""


FIX_SYSTEM = """You are an expert software engineer. You are given code with known issues and a fix plan.

Your job: output ONLY the complete corrected version of the code — nothing else.
- Fix ALL issues listed in the plan
- Preserve the overall structure, variable names, and logic that are not broken
- Do not add new features; only fix what is listed
- Do not wrap in markdown code fences
- Do not explain anything — output ONLY the raw fixed code"""


EXPLAIN_SYSTEM = """You are a code review mentor explaining fixes to a developer.

Given the original code, the fixed code, and a specific issue, explain clearly:
1. What was wrong (1-2 sentences)
2. What was changed to fix it (1-2 sentences, referencing line numbers if possible)
3. Why this matters (1 sentence on impact/risk)

Be specific and direct. No fluff. Output plain text, no markdown headers."""


# ── Streaming Generator ────────────────────────────────────────────────────────

async def stream_fix_progress(review_id: str, code: str, language: str, issues: list[dict]):
    """
    Main async generator for the Fix-It SSE endpoint.

    Emits events:
      {"type": "fix_start", "issue_count": n}
      {"type": "plan_done", "plan": [...]}
      {"type": "fix_token", "text": "..."}          — fixed code tokens
      {"type": "fix_code_done", "fixed_code": "...","diff": "...", "line_changes": {...}}
      {"type": "explain_start", "issue_id": "..."}
      {"type": "explain_token", "issue_id": "...", "text": "..."}
      {"type": "explain_done", "issue_id": "...", "explanation": "..."}
      {"type": "complete", "fixed_code": "...", "diff": "...", "explanations": {...}}
      {"type": "error", "message": "..."}
    """
    import asyncio

    llm = get_llm()
    llm_stream = get_llm(streaming=True)

    yield {"type": "fix_start", "issue_count": len(issues)}

    # ── Step 1: Plan ───────────────────────────────────────────────────────────
    issues_summary = json.dumps([
        {"id": i.get("id", ""), "category": i.get("category"), "severity": i.get("severity"),
         "title": i.get("title"), "description": i.get("description")}
        for i in issues
    ], indent=2)

    plan_resp = await llm.ainvoke([
        SystemMessage(content=PLAN_SYSTEM),
        HumanMessage(content=f"Language: {language}\n\nCode:\n```\n{code}\n```\n\nIssues:\n{issues_summary}"),
    ])

    plan = []
    try:
        raw = plan_resp.content.strip()
        raw = re.sub(r"```json\s*|```\s*", "", raw).strip()
        plan = json.loads(raw)
    except Exception as e:
        logger.warning("fix_plan_parse_failed", error=str(e))
        # Fallback: make a generic plan from all issues
        plan = [{"issue_id": i.get("id", ""), "fix_summary": i.get("suggestion", "Fix this issue"), "priority": i.get("severity", "medium")} for i in issues]

    yield {"type": "plan_done", "plan": plan}

    # ── Step 2: Generate fixed code (streaming) ────────────────────────────────
    fix_prompt = f"""Language: {language}

Original code:
{code}

Issues to fix:
{json.dumps([{"id": p["issue_id"], "fix": p["fix_summary"]} for p in plan], indent=2)}

Output ONLY the complete corrected code:"""

    fixed_code_parts = []

    async for chunk in llm_stream.astream([
        SystemMessage(content=FIX_SYSTEM),
        HumanMessage(content=fix_prompt),
    ]):
        token = chunk.content
        if token:
            fixed_code_parts.append(token)
            yield {"type": "fix_token", "text": token}

    fixed_code = "".join(fixed_code_parts).strip()
    # Strip accidental markdown fences
    fixed_code = re.sub(r"^```[\w]*\n?", "", fixed_code)
    fixed_code = re.sub(r"\n?```$", "", fixed_code).strip()

    unified_diff = compute_unified_diff(code, fixed_code, language)
    line_changes = compute_line_changes(code, fixed_code)

    yield {
        "type": "fix_code_done",
        "fixed_code": fixed_code,
        "diff": unified_diff,
        "line_changes": line_changes,
    }

    # ── Step 3: Explain each issue's fix (streaming, sequential) ───────────────
    explanations = {}
    issue_map = {i.get("id", ""): i for i in issues}

    for plan_item in plan:
        issue_id = plan_item.get("issue_id", "")
        issue = issue_map.get(issue_id)
        if not issue:
            continue

        yield {"type": "explain_start", "issue_id": issue_id}

        explain_prompt = f"""Language: {language}

Original code:
{code}

Fixed code:
{fixed_code}

Issue being explained:
Title: {issue.get("title")}
Category: {issue.get("category")}
Severity: {issue.get("severity")}
Description: {issue.get("description")}
Original suggestion: {issue.get("suggestion", "N/A")}
Fix applied: {plan_item.get("fix_summary")}

Explain the fix:"""

        explanation_parts = []
        async for chunk in llm_stream.astream([
            SystemMessage(content=EXPLAIN_SYSTEM),
            HumanMessage(content=explain_prompt),
        ]):
            token = chunk.content
            if token:
                explanation_parts.append(token)
                yield {"type": "explain_token", "issue_id": issue_id, "text": token}

        explanation = "".join(explanation_parts).strip()
        explanations[issue_id] = explanation
        yield {"type": "explain_done", "issue_id": issue_id, "explanation": explanation}

    yield {
        "type": "complete",
        "fixed_code": fixed_code,
        "diff": unified_diff,
        "line_changes": line_changes,
        "explanations": explanations,
    }
