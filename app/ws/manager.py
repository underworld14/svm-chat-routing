import json
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.admin_connections: list[WebSocket] = []
        self.client_connections: dict[int, WebSocket] = {}

    async def connect_admin(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.admin_connections.append(websocket)

    def disconnect_admin(self, websocket: WebSocket) -> None:
        if websocket in self.admin_connections:
            self.admin_connections.remove(websocket)

    async def connect_client(self, websocket: WebSocket, session_id: int) -> None:
        await websocket.accept()
        self.client_connections[session_id] = websocket

    def disconnect_client(self, session_id: int) -> None:
        self.client_connections.pop(session_id, None)

    async def safe_send(self, websocket: WebSocket, data: dict[str, Any]) -> bool:
        try:
            await websocket.send_text(json.dumps(data))
            return True
        except Exception:
            return False

    async def broadcast_admin(self, event: str, payload: dict) -> None:
        message = {"type": event, "payload": payload}
        disconnected: list[WebSocket] = []
        for ws in self.admin_connections:
            if not await self.safe_send(ws, message):
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect_admin(ws)

    async def send_to_client(self, session_id: int, event: str, payload: dict) -> None:
        ws = self.client_connections.get(session_id)
        if ws is None:
            return
        message = {"type": event, "payload": payload}
        if not await self.safe_send(ws, message):
            self.disconnect_client(session_id)
