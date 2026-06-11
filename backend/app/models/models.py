from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship, DeclarativeBase
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum
from datetime import datetime


class Base(DeclarativeBase):
    pass


class ReviewStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    ERROR = "error"


class IssueSeverity(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    reviews = relationship("Review", back_populates="owner")


class Review(Base):
    __tablename__ = "reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    code = Column(Text, nullable=False)
    language = Column(String(50), default="python")
    status = Column(SAEnum(ReviewStatus), default=ReviewStatus.PENDING)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="reviews")
    issues = relationship("ReviewIssue", back_populates="review", cascade="all, delete-orphan")
    comments = relationship("ReviewComment", back_populates="review", cascade="all, delete-orphan")


class ReviewIssue(Base):
    __tablename__ = "review_issues"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id = Column(UUID(as_uuid=True), ForeignKey("reviews.id"), nullable=False)
    category = Column(String(50), nullable=False)  # bug | security | style | performance
    severity = Column(SAEnum(IssueSeverity), nullable=False)
    line_start = Column(String(10))
    line_end = Column(String(10))
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    suggestion = Column(Text)
    code_snippet = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    review = relationship("Review", back_populates="issues")


class ReviewComment(Base):
    __tablename__ = "review_comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id = Column(UUID(as_uuid=True), ForeignKey("reviews.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    issue_id = Column(UUID(as_uuid=True), ForeignKey("review_issues.id"), nullable=True)
    content = Column(Text, nullable=False)
    line_number = Column(String(10))
    created_at = Column(DateTime, default=datetime.utcnow)

    review = relationship("Review", back_populates="comments")
    user = relationship("User")
