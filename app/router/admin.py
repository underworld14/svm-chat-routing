from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exists
from sqlalchemy.orm import Session, joinedload

from app.dependencies import get_db
from app.models import (
    Agent,
    AgentIntent,
    ChatSession,
    Intent,
    Message,
    MessageRole,
    SessionStatus,
)
from app.schemas import AdminReplyRequest
from app.services.waha import WahaClient, WahaError, extract_outbound_id, to_chat_id
from app.ws.manager import manager

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _session_query(db: Session):
    return db.query(ChatSession).options(
        joinedload(ChatSession.user),
        joinedload(ChatSession.assigned_agent),
        joinedload(ChatSession.intent),
    )


def _serialize_session(session: ChatSession) -> dict[str, object]:
    channel = session.channel.value if hasattr(session.channel, "value") else str(session.channel)
    return {
        "id": session.id,
        "user_id": session.user_id,
        "client_id": session.client_id,
        "channel": channel,
        "whatsapp_chat_id": session.whatsapp_chat_id,

        "intent_id": session.intent_id,
        "assigned_agent_id": session.assigned_agent_id,
        "status": session.status.value if hasattr(session.status, "value") else str(session.status),
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "user": (
            {
                "id": session.user.id,
                "name": session.user.name,
                "email": session.user.email,
                "phone": session.user.phone,
            }
            if session.user is not None
            else None
        ),
        "intent": (
            {
                "id": session.intent.id,
                "name": session.intent.name,
                "description": session.intent.description,
            }
            if session.intent is not None
            else None
        ),
        "assigned_agent": (
            {
                "id": session.assigned_agent.id,
                "name": session.assigned_agent.name,
                "email": session.assigned_agent.email,
                "role": session.assigned_agent.role,
                "is_online": session.assigned_agent.is_online,
                "current_load": session.assigned_agent.current_load,
            }
            if session.assigned_agent is not None
            else None
        ),
    }


def _serialize_message(message: Message) -> dict[str, object]:
    return {
        "id": message.id,
        "session_id": message.session_id,
        "role": message.role.value if hasattr(message.role, "value") else str(message.role),
        "content": message.content,
        "external_id": message.external_id,
        "raw_event": message.raw_event,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


_LIVE_STATUSES = (SessionStatus.waiting, SessionStatus.active)


def _has_user_message():
    """Hide empty / ghost sessions (e.g. test pollution) from the live board."""
    return exists().where(
        Message.session_id == ChatSession.id,
        Message.role == MessageRole.user,
    )


@router.get("/sessions")
def list_sessions(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    sessions = (
        _session_query(db)
        .filter(ChatSession.status.in_(_LIVE_STATUSES), _has_user_message())
        .order_by(ChatSession.created_at.desc())
        .all()
    )
    return [_serialize_session(session) for session in sessions]


@router.get("/sessions/grouped")
def list_sessions_grouped(db: Session = Depends(get_db)) -> dict[str, list[dict[str, object]]]:
    sessions = (
        _session_query(db)
        .filter(ChatSession.status.in_(_LIVE_STATUSES), _has_user_message())
        .order_by(ChatSession.created_at.desc())
        .all()
    )

    grouped_sessions: dict[str, list[dict[str, object]]] = {}
    for session in sessions:
        role = session.assigned_agent.role if session.assigned_agent is not None else "unassigned"
        grouped_sessions.setdefault(role, []).append(_serialize_session(session))

    return grouped_sessions


@router.get("/sessions/archived")
def list_archived_sessions(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    sessions = (
        _session_query(db)
        .filter(ChatSession.status == SessionStatus.archived)
        .order_by(ChatSession.created_at.desc())
        .all()
    )
    return [_serialize_session(session) for session in sessions]


@router.get("/sessions/{session_id}/messages")
def list_session_messages(session_id: int, db: Session = Depends(get_db)) -> list[dict[str, object]]:
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return [_serialize_message(message) for message in messages]


@router.post("/sessions/{session_id}/archive")
async def archive_session(session_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    session = _session_query(db).filter(ChatSession.id == session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status == SessionStatus.archived:
        raise HTTPException(status_code=400, detail="Session already archived")

    if session.assigned_agent_id is not None:
        agent = db.query(Agent).filter(Agent.id == session.assigned_agent_id).first()
        if agent is not None and agent.current_load > 0:
            agent.current_load -= 1

    session.status = SessionStatus.archived
    db.commit()
    db.refresh(session)

    payload = _serialize_session(session)
    await manager.broadcast_admin("session_updated", payload)
    return {"message": "Session archived and closed", "session": payload}


@router.post("/sessions/{session_id}/restore")
async def restore_session(session_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    session = _session_query(db).filter(ChatSession.id == session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status != SessionStatus.archived:
        raise HTTPException(status_code=400, detail="Session is not archived")

    # Archive decremented load; restore returns the session to the live board.
    if session.assigned_agent_id is not None:
        agent = db.query(Agent).filter(Agent.id == session.assigned_agent_id).first()
        if agent is not None:
            agent.current_load += 1

    session.status = (
        SessionStatus.active if session.assigned_agent_id is not None else SessionStatus.waiting
    )
    db.commit()
    db.refresh(session)

    payload = _serialize_session(session)
    await manager.broadcast_admin("session_updated", payload)
    return {"message": "Session restored", "session": payload}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Only live sessions still count toward load (archive already decremented).
    was_live = session.status in (SessionStatus.waiting, SessionStatus.active)
    agent = None
    if was_live and session.assigned_agent_id is not None:
        agent = db.query(Agent).filter(Agent.id == session.assigned_agent_id).first()

    db.query(Message).filter(Message.session_id == session_id).delete(synchronize_session=False)

    if agent is not None and agent.current_load > 0:
        agent.current_load -= 1

    db.delete(session)
    db.commit()

    payload = {"id": session_id}
    await manager.broadcast_admin("session_deleted", payload)
    return {"message": "Session deleted", "id": session_id}


@router.post("/reply")
async def admin_reply(
    payload: AdminReplyRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    session = (
        db.query(ChatSession)
        .options(joinedload(ChatSession.user))
        .filter(ChatSession.id == payload.session_id)
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Always send via WAHA first — never persist an orphan dashboard-only reply.
    # Prefer stored WAHA chatId (@lid or @c.us) — never rebuild LID digits as @c.us.
    phone = session.user.phone if session.user is not None else None
    chat_id = session.whatsapp_chat_id
    if not chat_id and phone:
        chat_id = to_chat_id(phone)
    if not chat_id and session.client_id and "@" in session.client_id:
        chat_id = session.client_id
    if not chat_id:
        raise HTTPException(
            status_code=400,
            detail="WhatsApp session has no chat id; wait for an inbound message first",
        )

    try:
        client = WahaClient()
        client.send_seen(chat_id)
        send_result = client.send_text(chat_id, payload.content)
    except WahaError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"WhatsApp send failed: {exc}",
        ) from exc

    outbound_id = extract_outbound_id(send_result if isinstance(send_result, dict) else None)
    reply = Message(
        session_id=session.id,
        role=MessageRole.agent,
        content=payload.content,
        external_id=outbound_id,
    )
    db.add(reply)
    db.commit()
    db.refresh(reply)

    reply_payload = _serialize_message(reply)
    await manager.broadcast_admin("message_new", reply_payload)

    return {"message": "Reply sent", "reply": reply_payload}


@router.get("/agents")
def list_agents(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    agents = db.query(Agent).order_by(Agent.role.asc(), Agent.name.asc()).all()
    return [
        {
            "id": agent.id,
            "name": agent.name,
            "email": agent.email,
            "role": agent.role,
            "is_online": agent.is_online,
            "current_load": agent.current_load,
        }
        for agent in agents
    ]


@router.get("/role-intents")
def list_role_intents(db: Session = Depends(get_db)) -> dict[str, list[str]]:
    """Intents handled by each agent role (for admin board headers)."""
    rows = (
        db.query(Agent.role, Intent.name)
        .join(AgentIntent, AgentIntent.agent_id == Agent.id)
        .join(Intent, Intent.id == AgentIntent.intent_id)
        .order_by(Agent.role.asc(), Intent.name.asc())
        .all()
    )
    grouped: dict[str, list[str]] = {}
    for role, intent_name in rows:
        bucket = grouped.setdefault(str(role), [])
        if intent_name not in bucket:
            bucket.append(intent_name)
    return grouped


@router.get("/intents")
def list_intents(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    intents = db.query(Intent).order_by(Intent.name.asc()).all()
    return [
        {
            "id": intent.id,
            "name": intent.name,
            "description": intent.description,
        }
        for intent in intents
    ]


# ── WhatsApp (WAHA) proxy ───────────────────────────────────


@router.get("/whatsapp/status")
def whatsapp_status() -> dict[str, object]:
    client = WahaClient()
    try:
        session = client.get_session()
    except WahaError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"WAHA unreachable: {exc}",
        ) from exc

    if session is None:
        return {
            "configured": True,
            "exists": False,
            "name": client.session_name,
            "status": "MISSING",
            "me": None,
        }

    return {
        "configured": True,
        "exists": True,
        "name": session.get("name") or client.session_name,
        "status": session.get("status") or "UNKNOWN",
        "me": session.get("me"),
    }


@router.get("/whatsapp/qr")
def whatsapp_qr() -> dict[str, object]:
    client = WahaClient()
    try:
        session = client.get_session()
        if session is None:
            raise HTTPException(status_code=404, detail="WhatsApp session not found. Start it first.")
        status = str(session.get("status") or "").upper()
        if status == "WORKING":
            return {"status": status, "qr": None, "message": "Already connected"}
        qr = client.get_qr_base64()
    except WahaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "status": status,
        "qr": qr,
        "mime": "image/png",
    }


@router.post("/whatsapp/session/start")
def whatsapp_session_start() -> dict[str, object]:
    client = WahaClient()
    try:
        session = client.ensure_session()
    except WahaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "name": session.get("name") or client.session_name,
        "status": session.get("status") or "UNKNOWN",
        "me": session.get("me"),
    }
