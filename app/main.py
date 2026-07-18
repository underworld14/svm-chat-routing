from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import models  # noqa: F401
from app.config import settings
from app.database import Base, engine
from app.ws.manager import ConnectionManager

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
ASSETS_DIR = STATIC_DIR / "assets"
INDEX_HTML = STATIC_DIR / "index.html"

manager = ConnectionManager()

app = FastAPI(
    title="POC Chat Routing API",
    description="FastAPI backend for POC chat routing with SVM intent classification.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


# ── API Routes ──────────────────────────────────────────────

from app.router import admin_router, chat_router  # noqa: E402

app.include_router(chat_router)
app.include_router(admin_router)


# ── WebSocket Routes ────────────────────────────────────────

@app.websocket("/ws/admin")
async def ws_admin(websocket: WebSocket) -> None:
    await manager.connect_admin(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_admin(websocket)


@app.websocket("/ws/client/{session_id}")
async def ws_client(websocket: WebSocket, session_id: int) -> None:
    await manager.connect_client(websocket, session_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_client(session_id)


# ── Production: serve built frontend from app/static ─────────

def _spa_ready() -> bool:
    return settings.is_production and INDEX_HTML.exists()


if _spa_ready() and ASSETS_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


@app.middleware("http")
async def spa_fallback_middleware(request: Request, call_next):
    response = await call_next(request)
    if not _spa_ready() or response.status_code != 404:
        return response

    path = request.url.path
    if path.startswith("/api/") or path.startswith("/ws/") or path.startswith("/assets/"):
        return response

    # Serve real files from app/static (favicon.svg, etc.) when present.
    candidate = (STATIC_DIR / path.lstrip("/")).resolve()
    if candidate.is_file() and STATIC_DIR.resolve() in candidate.parents:
        return FileResponse(candidate)

    return FileResponse(INDEX_HTML)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {
        "message": "Chat routing backend is running",
        "env": settings.APP_ENV,
        "spa": str(_spa_ready()).lower(),
    }


@app.get("/")
async def root():
    if _spa_ready():
        return FileResponse(INDEX_HTML)
    return {
        "message": "Chat routing backend is running",
        "env": settings.APP_ENV,
        "hint": "Set APP_ENV=production and run `cd frontend && npm run build` to serve the SPA.",
    }
