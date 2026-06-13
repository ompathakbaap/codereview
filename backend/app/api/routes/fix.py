"""
Fix-It API routes.

GET  /api/fix/{review_id}/stream  — SSE: streams fix progress (plan → code tokens → explanations)
GET  /api/fix/{review_id}         — Returns stored fixed code if already generated
POST /api/fix/{review_id}/save    — Saves the accepted fixed code back to the review record
"""

import uuid
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.models import Review, ReviewIssue
from app.core.deps import get_current_user, get_current_user_sse
from app.models.models import User
from app.agents.fix_agent import stream_fix_progress
import structlog

logger = structlog.get_logger()

router = APIRouter(prefix="/api/fix", tags=["fix"])


def _safe_error_message(error: Exception) -> str:
    err = str(error).lower()
    if "429" in err or "too many requests" in err or "rate_limit" in err or "rate limit" in err:
        return "AI providers are temporarily rate-limited. Please wait a minute and try again."
    return str(error)


@router.get("/{review_id}/stream")
async def stream_fix(
    review_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_sse),
):
    """
    SSE endpoint — streams the Fix-It agent progress for a completed review.

    Events:
      data: {"type": "fix_start", "issue_count": n}
      data: {"type": "plan_done", "plan": [...]}
      data: {"type": "fix_token", "text": "..."}
      data: {"type": "fix_code_done", "fixed_code": "...", "diff": "...", "line_changes": {...}}
      data: {"type": "explain_start", "issue_id": "..."}
      data: {"type": "explain_token", "issue_id": "...", "text": "..."}
      data: {"type": "explain_done", "issue_id": "...", "explanation": "..."}
      data: {"type": "complete", "fixed_code": "...", "diff": "...", "explanations": {...}}
      data: {"type": "error", "message": "..."}
    """
    result = await db.execute(
        select(Review)
        .options(selectinload(Review.issues))
        .where(Review.id == review_id)
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    if review.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your review")
    if review.status != "complete":
        raise HTTPException(status_code=400, detail="Review must be complete before running Fix-It")
    if not review.issues:
        raise HTTPException(status_code=400, detail="No issues found to fix")

    # Serialize issues for the agent
    issues = [
        {
            "id": str(i.id),
            "category": i.category,
            "severity": i.severity.value,
            "title": i.title,
            "description": i.description,
            "suggestion": i.suggestion,
            "code_snippet": i.code_snippet,
            "line_start": i.line_start,
            "line_end": i.line_end,
        }
        for i in review.issues
    ]

    async def event_generator():
        try:
            async for event in stream_fix_progress(
                str(review_id), review.code, review.language, issues
            ):
                if await request.is_disconnected():
                    break
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            logger.error("fix_stream_error", review_id=str(review_id), error=str(e))
            yield f"data: {json.dumps({'type': 'error', 'message': _safe_error_message(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{review_id}")
async def get_fix_info(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return review + issues so the Fix-It page can initialize."""
    result = await db.execute(
        select(Review)
        .options(selectinload(Review.issues))
        .where(Review.id == review_id)
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    if review.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your review")

    return {
        "id": str(review.id),
        "title": review.title,
        "code": review.code,
        "language": review.language,
        "status": review.status.value,
        "issue_count": len(review.issues),
        "issues": [
            {
                "id": str(i.id),
                "category": i.category,
                "severity": i.severity.value,
                "title": i.title,
                "description": i.description,
                "suggestion": i.suggestion,
                "line_start": i.line_start,
                "line_end": i.line_end,
            }
            for i in review.issues
        ],
    }
