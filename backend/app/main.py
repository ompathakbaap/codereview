from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.db.session import init_db
from app.services.redis_service import close_redis
from app.services.kafka_service import close_producer
from app.api.routes import auth, reviews, ws, fix
import structlog

logger = structlog.get_logger()

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup", model=settings.GROQ_MODEL)
    await init_db()
    yield
    await close_redis()
    await close_producer()
    logger.info("shutdown")


app = FastAPI(
    title="CodeReview Agent API",
    description="AI-powered real-time collaborative code review",
    version="1.0.0",
    lifespan=lifespan,
)

# Rate limiter state + handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://codereview-xi-sepia.vercel.app", "http://localhost:3000", settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(reviews.router)
app.include_router(ws.router)
app.include_router(fix.router)


@app.get("/health")
async def health():
    return {"status": "ok", "model": settings.GROQ_MODEL}
