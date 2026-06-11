import uuid
import re
import asyncio
import httpx
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.models import Review, ReviewIssue, ReviewComment, ReviewStatus, IssueSeverity
from app.schemas.schemas import ReviewCreate, ReviewOut, CommentCreate, CommentOut, PRReviewCreate
from app.core.deps import get_current_user, get_current_user_sse
from app.models.models import User
from app.agents.review_agent import run_review
from app.services.redis_service import publish
from app.services.kafka_service import emit_event
from app.core.config import settings
from slowapi import Limiter
from slowapi.util import get_remote_address
import structlog

logger = structlog.get_logger()
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/api/reviews", tags=["reviews"])


# ── Shared: run agent + persist issues + broadcast ─────────────────────────────

async def _run_agent_and_persist(review_id: str, code: str, language: str, db_url: str):
    """Background task: run LangGraph agent, save issues, broadcast via Redis."""
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            result = await run_review(review_id, code, language)

            issues_created = []
            for raw in result.get("issues", []):
                sev_map = {
                    "critical": IssueSeverity.CRITICAL,
                    "high": IssueSeverity.HIGH,
                    "medium": IssueSeverity.MEDIUM,
                    "low": IssueSeverity.LOW,
                    "info": IssueSeverity.INFO,
                }
                severity = sev_map.get(raw.get("severity", "low"), IssueSeverity.LOW)
                issue = ReviewIssue(
                    id=uuid.uuid4(),
                    review_id=uuid.UUID(review_id),
                    category=raw.get("category", "bug"),
                    severity=severity,
                    line_start=raw.get("line_start"),
                    line_end=raw.get("line_end"),
                    title=raw.get("title", "Issue"),
                    description=raw.get("description", ""),
                    suggestion=raw.get("suggestion"),
                    code_snippet=raw.get("code_snippet"),
                )
                db.add(issue)
                issues_created.append(issue)

            review_result = await db.execute(select(Review).where(Review.id == uuid.UUID(review_id)))
            review = review_result.scalar_one_or_none()
            if review:
                review.status = ReviewStatus.COMPLETE
            await db.commit()

            await publish(f"review:{review_id}", {
                "type": "review_complete",
                "review_id": review_id,
                "summary": result.get("structure_summary", ""),
                "issue_count": len(issues_created),
                "issues": [
                    {
                        "id": str(i.id),
                        "category": i.category,
                        "severity": i.severity.value,
                        "line_start": i.line_start,
                        "line_end": i.line_end,
                        "title": i.title,
                        "description": i.description,
                        "suggestion": i.suggestion,
                        "code_snippet": i.code_snippet,
                    }
                    for i in issues_created
                ],
            })

            await emit_event("review_complete", {
                "review_id": review_id,
                "issue_count": len(issues_created),
                "language": language,
            })

        except Exception as e:
            async with AsyncSessionLocal() as err_db:
                r = await err_db.execute(select(Review).where(Review.id == uuid.UUID(review_id)))
                review = r.scalar_one_or_none()
                if review:
                    review.status = ReviewStatus.ERROR
                    await err_db.commit()
            await publish(f"review:{review_id}", {
                "type": "review_error",
                "review_id": review_id,
                "error": str(e),
            })


# ── POST /api/reviews — paste code ────────────────────────────────────────────

@router.post("", response_model=ReviewOut, status_code=201)
@limiter.limit("10/minute")
async def create_review(
    request: Request,
    body: ReviewCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    review = Review(
        id=uuid.uuid4(),
        title=body.title,
        code=body.code,
        language=body.language,
        owner_id=current_user.id,
        status=ReviewStatus.RUNNING,
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)

    background_tasks.add_task(_run_agent_and_persist, str(review.id), body.code, body.language, "")

    await emit_event("review_created", {
        "review_id": str(review.id),
        "owner_id": str(current_user.id),
        "language": body.language,
    })

    await session.refresh(review, ["issues"])
    return ReviewOut.model_validate(review)


# ── POST /api/reviews/from-pr — GitHub PR diff ────────────────────────────────

def _parse_pr_url(url: str) -> tuple[str, str, int]:
    """Parse https://github.com/owner/repo/pull/123 → (owner, repo, pr_number)."""
    pattern = r"github\.com/([^/]+)/([^/]+)/pull/(\d+)"
    m = re.search(pattern, url)
    if not m:
        raise ValueError("Invalid GitHub PR URL. Expected: https://github.com/owner/repo/pull/123")
    return m.group(1), m.group(2), int(m.group(3))


async def _fetch_pr_diff(owner: str, repo: str, pr_number: int, github_token: str | None) -> tuple[str, str]:
    """Fetch PR diff from GitHub API. Returns (diff_text, detected_language)."""
    headers = {"Accept": "application/vnd.github.v3.diff"}
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    async with httpx.AsyncClient(timeout=15.0) as client:
        # Get PR metadata for language detection
        meta_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        meta_headers = {"Accept": "application/vnd.github.v3+json"}
        if github_token:
            meta_headers["Authorization"] = f"Bearer {github_token}"

        meta_resp = await client.get(meta_url, headers=meta_headers)
        if meta_resp.status_code == 404:
            raise HTTPException(status_code=404, detail="PR not found. Make sure the repo is public or provide a GitHub token.")
        if meta_resp.status_code == 403:
            raise HTTPException(status_code=403, detail="GitHub rate limit hit. Add a GITHUB_TOKEN to your environment.")
        meta_resp.raise_for_status()
        meta = meta_resp.json()

        # Fetch the actual diff
        diff_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        diff_resp = await client.get(diff_url, headers=headers)
        diff_resp.raise_for_status()
        diff_text = diff_resp.text

    # Detect dominant language from PR title/body or file extensions in diff
    lang = "unknown"
    ext_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".go": "go", ".java": "java", ".rs": "rust", ".cpp": "cpp",
        ".c": "c", ".cs": "csharp", ".rb": "ruby", ".php": "php",
    }
    for ext, lang_name in ext_map.items():
        if f"+++ b/" in diff_text and ext in diff_text:
            lang = lang_name
            break

    pr_title = meta.get("title", "GitHub PR Review")
    return diff_text, lang, pr_title


@router.post("/from-pr", response_model=ReviewOut, status_code=201)
@limiter.limit("5/minute")
async def create_review_from_pr(
    request: Request,
    body: PRReviewCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Fetch a GitHub PR diff and run the AI agent on it.
    Works on public repos without a token; private repos need GITHUB_TOKEN env var.
    """
    try:
        owner, repo, pr_number = _parse_pr_url(body.pr_url)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    diff_text, detected_language, pr_title = await _fetch_pr_diff(
        owner, repo, pr_number, settings.GITHUB_TOKEN
    )

    if not diff_text.strip():
        raise HTTPException(status_code=422, detail="PR diff is empty — nothing to review.")

    # Truncate very large diffs to avoid token limits
    max_chars = 12_000
    if len(diff_text) > max_chars:
        diff_text = diff_text[:max_chars] + f"\n\n... [diff truncated at {max_chars} chars] ..."

    title = body.title or pr_title or f"PR #{pr_number} — {owner}/{repo}"
    language = body.language or detected_language

    review = Review(
        id=uuid.uuid4(),
        title=title,
        code=diff_text,
        language=language,
        owner_id=current_user.id,
        status=ReviewStatus.RUNNING,
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)

    background_tasks.add_task(_run_agent_and_persist, str(review.id), diff_text, language, "")

    await emit_event("pr_review_created", {
        "review_id": str(review.id),
        "pr_url": body.pr_url,
        "owner": owner,
        "repo": repo,
        "pr_number": pr_number,
    })

    logger.info("pr_review.created", review_id=str(review.id), pr=f"{owner}/{repo}#{pr_number}")
    return ReviewOut.model_validate(review)


# ── GET /api/reviews ───────────────────────────────────────────────────────────

@router.get("", response_model=list[ReviewOut])
async def list_reviews(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Review)
        .options(selectinload(Review.issues))
        .where(Review.owner_id == current_user.id)
        .order_by(Review.created_at.desc())
    )
    return [ReviewOut.model_validate(r) for r in result.scalars().all()]


# ── GET /api/reviews/stats ─────────────────────────────────────────────────────

@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns trend metrics for the authenticated user's reviews:
    - Total reviews + issues
    - Issues by category and severity
    - Top languages reviewed
    - Daily review counts (last 14 days)
    """
    # Total counts
    total_reviews = await db.scalar(
        select(func.count(Review.id)).where(Review.owner_id == current_user.id)
    )
    total_issues = await db.scalar(
        select(func.count(ReviewIssue.id))
        .join(Review, ReviewIssue.review_id == Review.id)
        .where(Review.owner_id == current_user.id)
    )

    # Issues by category
    cat_rows = await db.execute(
        select(ReviewIssue.category, func.count(ReviewIssue.id).label("cnt"))
        .join(Review, ReviewIssue.review_id == Review.id)
        .where(Review.owner_id == current_user.id)
        .group_by(ReviewIssue.category)
    )
    issues_by_category = {row.category: row.cnt for row in cat_rows}

    # Issues by severity
    sev_rows = await db.execute(
        select(ReviewIssue.severity, func.count(ReviewIssue.id).label("cnt"))
        .join(Review, ReviewIssue.review_id == Review.id)
        .where(Review.owner_id == current_user.id)
        .group_by(ReviewIssue.severity)
    )
    issues_by_severity = {row.severity.value: row.cnt for row in sev_rows}

    # Top languages (up to 6)
    lang_rows = await db.execute(
        select(Review.language, func.count(Review.id).label("cnt"))
        .where(Review.owner_id == current_user.id)
        .group_by(Review.language)
        .order_by(func.count(Review.id).desc())
        .limit(6)
    )
    top_languages = [{"language": r.language, "count": r.cnt} for r in lang_rows]

    # Recent reviews (last 15 for timeline)
    recent_rows = await db.execute(
        select(Review.created_at, Review.status)
        .where(Review.owner_id == current_user.id)
        .order_by(Review.created_at.desc())
        .limit(15)
    )
    recent_reviews = [
        {"date": r.created_at.isoformat(), "status": r.status.value}
        for r in recent_rows
    ]

    return {
        "total_reviews": total_reviews or 0,
        "total_issues": total_issues or 0,
        "issues_by_category": issues_by_category,
        "issues_by_severity": issues_by_severity,
        "top_languages": top_languages,
        "recent_reviews": recent_reviews,
    }


# ── GET /api/reviews/{id} ──────────────────────────────────────────────────────

@router.get("/{review_id}", response_model=ReviewOut)
async def get_review(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Review)
        .options(selectinload(Review.issues))
        .where(Review.id == review_id)
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return ReviewOut.model_validate(review)


# ── GET /api/reviews/{id}/stream — SSE streaming ──────────────────────────────

@router.get("/{review_id}/stream")
async def stream_review(
    review_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_sse),
):
    """
    Server-Sent Events endpoint. Streams real-time agent progress tokens
    directly to the browser as the LLM generates them, so users see
    analysis building live instead of staring at a spinner.

    Events emitted:
      data: {"type": "token", "node": "bug_check", "text": "..."}
      data: {"type": "node_start", "node": "security_check"}
      data: {"type": "node_done", "node": "bug_check", "issue_count": 3}
      data: {"type": "complete", "issue_count": 12}
      data: {"type": "error", "message": "..."}
    """
    import json

    # Verify review belongs to user
    result = await db.execute(select(Review).where(Review.id == review_id))
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    async def event_generator():
        from app.agents.review_agent import stream_review_progress
        try:
            async for event in stream_review_progress(str(review_id), review.code, review.language):
                if await request.is_disconnected():
                    break
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering on Railway
        },
    )


# ── POST /api/reviews/{id}/comments ───────────────────────────────────────────

@router.post("/{review_id}/comments", response_model=CommentOut, status_code=201)
async def add_comment(
    review_id: uuid.UUID,
    body: CommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    comment = ReviewComment(
        id=uuid.uuid4(),
        review_id=review_id,
        user_id=current_user.id,
        issue_id=body.issue_id,
        content=body.content,
        line_number=body.line_number,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    await publish(f"review:{review_id}", {
        "type": "new_comment",
        "comment_id": str(comment.id),
        "user_id": str(current_user.id),
        "username": current_user.username,
        "content": body.content,
        "issue_id": str(body.issue_id) if body.issue_id else None,
        "line_number": body.line_number,
    })

    out = CommentOut.model_validate(comment)
    out.username = current_user.username
    return out


# ── GET /api/reviews/{id}/comments ────────────────────────────────────────────

@router.get("/{review_id}/comments", response_model=list[CommentOut])
async def get_comments(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ReviewComment)
        .where(ReviewComment.review_id == review_id)
        .order_by(ReviewComment.created_at.asc())
    )
    comments = result.scalars().all()
    out = []
    for c in comments:
        item = CommentOut.model_validate(c)
        user_result = await db.execute(select(User).where(User.id == c.user_id))
        user = user_result.scalar_one_or_none()
        if user:
            item.username = user.username
        out.append(item)
    return out
