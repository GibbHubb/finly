"""WebSocket endpoint — real-time transaction feed."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status

from app.core.ws_manager import manager
from app.core.security import decode_token

router = APIRouter()


@router.websocket("/ws/transactions")
async def ws_transactions(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
) -> None:
    """Authenticated WebSocket endpoint.

    Connect with: ws://host/ws/transactions?token=<jwt>
    Clients receive JSON objects whenever a new transaction is created.
    """
    # Validate JWT before accepting the connection
    try:
        payload = decode_token(token)
        user_id = int(payload["sub"])
    except (ValueError, KeyError):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(websocket, user_id=user_id)
    try:
        while True:
            # Keep connection alive; we only push server → client
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
