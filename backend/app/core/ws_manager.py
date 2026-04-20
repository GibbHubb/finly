"""WebSocket connection manager for broadcasting transaction events."""
import json
from collections import defaultdict
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self._user_connections: dict[int, list[WebSocket]] = defaultdict(list)

    async def connect(self, ws: WebSocket, user_id: int | None = None) -> None:
        await ws.accept()
        self._connections.append(ws)
        if user_id is not None:
            self._user_connections[user_id].append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._connections:
            self._connections.remove(ws)
        for uid, conns in self._user_connections.items():
            if ws in conns:
                conns.remove(ws)
                break

    async def broadcast(self, data: dict) -> None:
        dead: list[WebSocket] = []
        message = json.dumps(data)
        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def send_to_user(self, user_id: int, data: dict) -> None:
        dead: list[WebSocket] = []
        message = json.dumps(data)
        for ws in self._user_connections.get(user_id, []):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()
