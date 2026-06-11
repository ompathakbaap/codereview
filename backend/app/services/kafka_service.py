"""
Kafka service — stubbed out (no-op).
Kafka has been removed from this project. All calls to emit_event() are safe
no-ops so no other code needs to change.
"""
import structlog

logger = structlog.get_logger()


async def emit_event(event_type: str, payload: dict) -> None:
    """No-op stub — Kafka removed."""
    pass


async def close_producer() -> None:
    """No-op stub — Kafka removed."""
    pass
