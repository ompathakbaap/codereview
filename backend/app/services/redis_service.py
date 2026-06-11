import json
import redis.asyncio as aioredis
from typing import AsyncIterator
from app.core.config import settings
import structlog

logger = structlog.get_logger()

_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def publish(channel: str, message: dict) -> None:
    """Publish a message to a Redis channel (review room)."""
    r = await get_redis()
    await r.publish(channel, json.dumps(message))
    logger.info("redis.publish", channel=channel, event=message.get("type"))


async def subscribe(channel: str) -> AsyncIterator[dict]:
    """Subscribe to a Redis channel and yield messages."""
    r = await get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(channel)
    try:
        async for raw in pubsub.listen():
            if raw["type"] == "message":
                try:
                    yield json.loads(raw["data"])
                except json.JSONDecodeError:
                    pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()


async def close_redis():
    global _redis
    if _redis:
        await _redis.close()
        _redis = None
