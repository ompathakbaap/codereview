from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "CodeReview Agent"
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Neon.tech free PostgreSQL
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost/codereview"

    # Upstash Redis (free tier)
    REDIS_URL: str = "redis://localhost:6379"

    # Groq — free tier, no credit card required
    # Get your key at: https://console.groq.com/keys
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Gemini — hosted API fallback when Groq is rate-limited/unavailable
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash-lite"

    # Optional local/offline LLM backend for development.
    # When set, the review/fix agents use Ollama instead of Groq.
    OLLAMA_BASE_URL: str = ""
    OLLAMA_MODEL: str = "llama3.2"

    FRONTEND_URL: str = "http://localhost:3000"

    # GitHub — optional, needed for private repos + avoids rate limits
    # Get a free classic token at: https://github.com/settings/tokens
    GITHUB_TOKEN: str = ""

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
