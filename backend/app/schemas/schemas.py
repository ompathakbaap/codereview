from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
import uuid


# ── Auth ──────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ── Review ────────────────────────────────────────────────────────────────────

class ReviewCreate(BaseModel):
    title: str
    code: str
    language: str = "python"


class PRReviewCreate(BaseModel):
    pr_url: str                        # https://github.com/owner/repo/pull/123
    title: Optional[str] = None        # override auto-detected PR title
    language: Optional[str] = None     # override auto-detected language


class IssueOut(BaseModel):
    id: uuid.UUID
    category: str
    severity: str
    line_start: Optional[str]
    line_end: Optional[str]
    title: str
    description: str
    suggestion: Optional[str]
    code_snippet: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ReviewOut(BaseModel):
    id: uuid.UUID
    title: str
    code: str
    language: str
    status: str
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    issues: list[IssueOut] = []

    class Config:
        from_attributes = True


# ── Comments ──────────────────────────────────────────────────────────────────

class CommentCreate(BaseModel):
    content: str
    issue_id: Optional[uuid.UUID] = None
    line_number: Optional[str] = None


class CommentOut(BaseModel):
    id: uuid.UUID
    review_id: uuid.UUID
    user_id: uuid.UUID
    issue_id: Optional[uuid.UUID]
    content: str
    line_number: Optional[str]
    created_at: datetime
    username: Optional[str] = None

    class Config:
        from_attributes = True
