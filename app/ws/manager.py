import json
from datetime import date, datetime
from typing import Any

from fastapi import WebSocket


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


class ConnectionManager:
    def __init__(self) -> None:
        self.admin_connections: list[WebSocket] = []

    async def connect_admin(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.admin_connections.append(websocket)

    def disconnect_admin(self, websocket: WebSocket) -> None:
        if websocket in self.admin_connections:
            self.admin_connections.remove(websocket)

    async def safe_send(self, websocket: WebSocket, data: dict[str, Any]) -> bool:
        try:
            await websocket.send_text(json.dumps(data, default=_json_default))
            return True
        except Exception:
            return False

    async def broadcast_admin(self, event: str, payload: dict) -> None:
        message = {"type": event, "payload": payload}
        disconnected: list[WebSocket] = []
        for ws in list(self.admin_connections):
            if not await self.safe_send(ws, message):
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect_admin(ws)


manager = ConnectionManager()
