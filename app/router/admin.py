from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.dependencies import get_db
from app.main import manager
from app.models import Agent, ChatSession, Intent, Message, MessageRole, SessionStatus
from app.schemas import AdminReplyRequest

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _session_query(db: Session):
    return db.query(ChatSession).options(
        joinedload(ChatSession.user),
        joinedload(ChatSession.assigned_agent),
        joinedload(ChatSession.intent),
    )


def _serialize_session(session: ChatSession) -> dict[str, object]:
    return {
        "id": session.id,
        "user_id": session.user_id,
        "client_id": session.client_id,
        "intent_id": session.intent_id,
        "assigned_agent_id": session.assigned_agent_id,
        "status": session.status.value if hasattr(session.status, "value") else str(session.status),
        "created_at": session.created_at,
        "user": (
            {
                "id": session.user.id,
                "name": session.user.name,
                "email": session.user.email,
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
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


@router.get("/sessions")
def list_sessions(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    sessions = (
        _session_query(db)
        .filter(ChatSession.status != SessionStatus.archived)
        .order_by(ChatSession.created_at.desc())
        .all()
    )
    return [_serialize_session(session) for session in sessions]


@router.get("/sessions/grouped")
def list_sessions_grouped(db: Session = Depends(get_db)) -> dict[str, list[dict[str, object]]]:
    sessions = (
        _session_query(db)
        .filter(ChatSession.status != SessionStatus.archived)
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

    session.status = SessionStatus.archived
    db.commit()
    db.refresh(session)

    payload = _serialize_session(session)
    await manager.broadcast_admin("session_updated", payload)
    return {"message": "Session archived", "session": payload}


@router.post("/sessions/{session_id}/restore")
async def restore_session(session_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    session = _session_query(db).filter(ChatSession.id == session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status != SessionStatus.archived:
        raise HTTPException(status_code=400, detail="Session is not archived")

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

    agent = None
    if session.assigned_agent_id is not None:
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
    session = db.query(ChatSession).filter(ChatSession.id == payload.session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    reply = Message(
        session_id=session.id,
        role=MessageRole.agent,
        content=payload.content,
    )
    db.add(reply)
    db.commit()
    db.refresh(reply)

    reply_payload = _serialize_message(reply)
    await manager.send_to_client(payload.session_id, "message_new", reply_payload)

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
