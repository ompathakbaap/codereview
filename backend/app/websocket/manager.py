"""
WebSocket connection manager + Redis Pub/Sub bridge.

Each review room has a channel: "review:{review_id}"
- When a user joins, they subscribe to that channel
- All events (new issue found, comment added, user joined) are published to Redis
- Redis fan-out delivers to ALL connected WebSocket clients in that room
"""
import asyncio
import json
from fastapi import WebSocket
from typing import DefaultDict
from collections import defaultdict
from app.services.redis_service import publish, get_redis
import structlog

logger = structlog.get_logger()


class ConnectionManager:
    def __init__(self):
        # room_id → set of (websocket, user_id)
        self.rooms: DefaultDict[str, set] = defaultdict(set)
        # Track which rooms are already being subscribed
        self._listener_tasks: dict[str, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket, review_id: str, user_id: str, username: str):
        await websocket.accept()
        self.rooms[review_id].add((websocket, user_id))

        # Start Redis subscriber for this room if not already running
        if review_id not in self._listener_tasks:
            task = asyncio.create_task(self._redis_listener(review_id))
            self._listener_tasks[review_id] = task

        # Announce join to room
        await publish(f"review:{review_id}", {
            "type": "user_joined",
            "user_id": user_id,
            "username": username,
            "active_users": self._active_users(review_id),
        })
        logger.info("ws.connected", review_id=review_id, user_id=user_id)

    async def disconnect(self, websocket: WebSocket, review_id: str, user_id: str, username: str):
        self.rooms[review_id].discard((websocket, user_id))
        if not self.rooms[review_id]:
            # Cancel listener if room is empty
            task = self._listener_tasks.pop(review_id, None)
            if task:
                task.cancel()
            del self.rooms[review_id]
        else:
            await publish(f"review:{review_id}", {
                "type": "user_left",
                "user_id": user_id,
                "username": username,
                "active_users": self._active_users(review_id),
            })
        logger.info("ws.disconnected", review_id=review_id, user_id=user_id)

    async def broadcast_to_room(self, review_id: str, message: dict):
        """Publish to Redis → fan-out to all WS clients via _redis_listener."""
        await publish(f"review:{review_id}", message)

    async def _redis_listener(self, review_id: str):
        """Subscribe to Redis channel and push messages to all WS clients in room."""
        r = await get_redis()
        pubsub = r.pubsub()
        channel = f"review:{review_id}"
        await pubsub.subscribe(channel)
        try:
            async for raw in pubsub.listen():
                if raw["type"] != "message":
                    continue
                try:
                    data = json.loads(raw["data"])
                except json.JSONDecodeError:
                    continue
                # Send to all WebSocket clients in this room
                dead = set()
                for ws, uid in list(self.rooms.get(review_id, [])):
                    try:
                        await ws.send_json(data)
                    except Exception:
                        dead.add((ws, uid))
                for item in dead:
                    self.rooms[review_id].discard(item)
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    def _active_users(self, review_id: str) -> list[str]:
        return [uid for _, uid in self.rooms.get(review_id, [])]

    def get_room_count(self, review_id: str) -> int:
        return len(self.rooms.get(review_id, []))


manager = ConnectionManager()
