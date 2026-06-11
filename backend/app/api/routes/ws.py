from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.websocket.manager import manager
from app.core.security import decode_token
import structlog

router = APIRouter()
logger = structlog.get_logger()


@router.websocket("/ws/review/{review_id}")
async def review_websocket(
    websocket: WebSocket,
    review_id: str,
    token: str = Query(...),
):
    """
    WebSocket endpoint for real-time collaborative code review.
    
    Connect: ws://host/ws/review/{review_id}?token=<jwt>
    
    Incoming events from client:
      { "type": "cursor_move", "line": 42 }
      { "type": "ping" }
    
    Outgoing events to all room clients (via Redis Pub/Sub):
      { "type": "user_joined", "username": "...", "active_users": [...] }
      { "type": "user_left", ... }
      { "type": "review_complete", "issues": [...] }
      { "type": "new_comment", "content": "...", "username": "..." }
      { "type": "cursor_move", "user_id": "...", "line": 42 }
    """
    # Authenticate via token query param (WS can't send headers easily)
    try:
        payload = decode_token(token)
        user_id = payload.get("sub", "anonymous")
        username = payload.get("username", user_id[:8])
    except Exception:
        await websocket.close(code=4001)
        return

    await manager.connect(websocket, review_id, user_id, username)

    try:
        while True:
            data = await websocket.receive_json()
            event_type = data.get("type")

            if event_type == "cursor_move":
                await manager.broadcast_to_room(review_id, {
                    "type": "cursor_move",
                    "user_id": user_id,
                    "username": username,
                    "line": data.get("line"),
                })
            elif event_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        await manager.disconnect(websocket, review_id, user_id, username)
    except Exception as e:
        logger.error("ws.error", review_id=review_id, error=str(e))
        await manager.disconnect(websocket, review_id, user_id, username)
