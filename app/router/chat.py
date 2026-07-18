from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.main import manager
from app.models import ChatSession, Message
from app.schemas import ChatSendRequest, ChatSendResponse, ChatStartRequest, ChatStartResponse
from app.services.router import ChatService

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/start", response_model=ChatStartResponse)
def start_chat(payload: ChatStartRequest, db: Session = Depends(get_db)) -> ChatStartResponse:
    session = ChatService().start_chat(db, payload.name, payload.email)
    return ChatStartResponse(session_id=session.id, user_id=session.user_id)


@router.post("/send", response_model=ChatSendResponse)
def send_chat(
    payload: ChatSendRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ChatSendResponse:
    session = db.query(ChatSession).filter(ChatSession.id == payload.session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    result = ChatService().classify_and_route(db, session.id, payload.message)
    intent = result.get("intent_name")
    assigned_agent = result.get("agent_name")

    user_message = (
        db.query(Message)
        .filter(Message.session_id == session.id)
        .order_by(Message.created_at.desc())
        .first()
    )

    ws_payload: dict[str, object] = {
        "session_id": session.id,
        "content": payload.message,
        "role": "user",
        "intent": intent if isinstance(intent, str) else "unknown",
        "assigned_agent": assigned_agent if isinstance(assigned_agent, str) else None,
    }
    if user_message is not None:
        ws_payload["id"] = user_message.id
        ws_payload["created_at"] = user_message.created_at.isoformat()

    background_tasks.add_task(manager.broadcast_admin, "message_new", ws_payload)

    return ChatSendResponse(
        message="Message routed successfully",
        intent=intent if isinstance(intent, str) else "unknown",
        assigned_agent=assigned_agent if isinstance(assigned_agent, str) else None,
    )
