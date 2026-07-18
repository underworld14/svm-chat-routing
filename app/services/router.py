from sqlalchemy.orm import Session

from app.models import (
    Agent,
    AgentIntent,
    ChatChannel,
    ChatSession,
    Intent,
    Message,
    MessageRole,
    SessionStatus,
    User,
)
from app.services.classifier import IntentClassifier


def find_best_agent(intent_name: str, db: Session) -> Agent | None:
    """Find online agent with matching intent and smallest load."""
    return (
        db.query(Agent)
        .join(AgentIntent, AgentIntent.agent_id == Agent.id)
        .join(Intent, Intent.id == AgentIntent.intent_id)
        .filter(Intent.name == intent_name, Agent.is_online.is_(True))
        .order_by(Agent.current_load.asc())
        .first()
    )


def _is_placeholder_name(name: str | None) -> bool:
    value = (name or "").strip().lower()
    if not value:
        return True
    if value.startswith("wa "):
        return True
    if value in {"lid user", "whatsapp user", "unknown"}:
        return True
    if "@lid" in value or "@c.us" in value:
        return True
    return False


class AgentRouter:
    def find_best_agent(self, intent_name: str, db: Session) -> Agent | None:
        return find_best_agent(intent_name=intent_name, db=db)


class ChatService:
    def __init__(self, classifier: IntentClassifier | None = None) -> None:
        self.classifier = classifier or IntentClassifier()
        self.router = AgentRouter()

    def _resolve_user(
        self,
        db: Session,
        name: str,
        *,
        email: str | None = None,
        phone: str | None = None,
        client_id: str | None = None,
    ) -> User:
        user: User | None = None
        if phone:
            user = db.query(User).filter(User.phone == phone).first()
        elif email:
            user = db.query(User).filter(User.email == email).first()
        elif client_id:
            prev = (
                db.query(ChatSession)
                .filter(ChatSession.client_id == client_id)
                .order_by(ChatSession.created_at.desc())
                .first()
            )
            if prev is not None:
                user = db.query(User).filter(User.id == prev.user_id).first()

        if user is None:
            user = User(name=name, email=email, phone=phone)
            db.add(user)
            db.flush()
        else:
            self.update_user_profile(db, user, name=name, email=email, phone=phone)

        return user

    def update_user_profile(
        self,
        db: Session,
        user: User,
        *,
        name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
    ) -> None:
        changed = False
        clean = (name or "").strip()
        if clean and not _is_placeholder_name(clean) and user.name != clean:
            if _is_placeholder_name(user.name) or user.name != clean:
                user.name = clean
                changed = True
        if email and user.email is None:
            user.email = email
            changed = True
        if phone and user.phone is None:
            user.phone = phone
            changed = True
        if changed:
            db.commit()

    def start_chat(
        self,
        db: Session,
        name: str,
        email: str | None = None,
        *,
        phone: str | None = None,
        channel: ChatChannel = ChatChannel.whatsapp,
        client_id: str | None = None,
    ) -> ChatSession:
        resolved_client_id = client_id or phone or email
        if not resolved_client_id:
            raise ValueError("client_id, phone, or email is required")

        user = self._resolve_user(
            db, name, email=email, phone=phone, client_id=resolved_client_id
        )

        session = ChatSession(
            status=SessionStatus.waiting,
            user_id=user.id,
            client_id=resolved_client_id,
            channel=channel,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    def find_open_session(self, db: Session, client_id: str) -> ChatSession | None:
        return (
            db.query(ChatSession)
            .filter(
                ChatSession.client_id == client_id,
                ChatSession.status.notin_([SessionStatus.archived, SessionStatus.closed]),
            )
            .order_by(ChatSession.created_at.desc())
            .first()
        )

    def find_open_whatsapp_session(
        self,
        db: Session,
        *,
        chat_id: str,
        phone: str | None = None,
        phone_chat_id: str | None = None,
    ) -> ChatSession | None:
        """Find sticky session across LID / phone / legacy client_id shapes."""
        from app.services.waha import normalize_chat_id, to_chat_id

        keys: set[str] = set()
        chat_id = normalize_chat_id(chat_id)
        if chat_id:
            keys.add(chat_id)
        if phone:
            keys.add(phone)
            keys.add(to_chat_id(phone))
        if phone_chat_id:
            keys.add(normalize_chat_id(phone_chat_id))

        if not keys:
            return None

        return (
            db.query(ChatSession)
            .filter(
                ChatSession.channel == ChatChannel.whatsapp,
                ChatSession.status.notin_([SessionStatus.archived, SessionStatus.closed]),
                (
                    ChatSession.client_id.in_(keys)
                    | ChatSession.whatsapp_chat_id.in_(keys)
                ),
            )
            .order_by(ChatSession.created_at.desc())
            .first()
        )

    def append_user_message(
        self,
        db: Session,
        session_id: int,
        message: str,
        *,
        external_id: str | None = None,
        raw_event: str | None = None,
    ) -> dict[str, str | None]:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        if external_id:
            existing = db.query(Message).filter(Message.external_id == external_id).first()
            if existing is not None:
                intent_name = session.intent.name if session.intent else None
                agent_name = session.assigned_agent.name if session.assigned_agent else None
                return {"intent_name": intent_name, "agent_name": agent_name, "duplicate": "1"}

        user_message = Message(
            session_id=session.id,
            role=MessageRole.user,
            content=message,
            external_id=external_id,
            raw_event=raw_event,
        )
        db.add(user_message)
        db.commit()
        db.refresh(session)

        intent_name = session.intent.name if session.intent else None
        agent_name = session.assigned_agent.name if session.assigned_agent else None
        return {"intent_name": intent_name, "agent_name": agent_name}

    def classify_and_route(
        self,
        db: Session,
        session_id: int,
        message: str,
        *,
        external_id: str | None = None,
        raw_event: str | None = None,
    ) -> dict[str, str | None]:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        if external_id:
            existing = db.query(Message).filter(Message.external_id == external_id).first()
            if existing is not None:
                intent_name = session.intent.name if session.intent else None
                agent_name = session.assigned_agent.name if session.assigned_agent else None
                return {"intent_name": intent_name, "agent_name": agent_name, "duplicate": "1"}

        # Sticky: once classified/activated, keep the same agent for the session lifetime.
        already_routed = session.intent_id is not None or session.status == SessionStatus.active
        if already_routed:
            return self.append_user_message(
                db,
                session_id,
                message,
                external_id=external_id,
                raw_event=raw_event,
            )

        intent_name = self.classifier.predict(message)
        intent = db.query(Intent).filter(Intent.name == intent_name).first()
        agent = self.router.find_best_agent(intent_name=intent_name, db=db)

        if intent is not None:
            session.intent_id = intent.id

        if agent is not None:
            session.assigned_agent_id = agent.id
            agent.current_load += 1

        user_message = Message(
            session_id=session.id,
            role=MessageRole.user,
            content=message,
            external_id=external_id,
            raw_event=raw_event,
        )
        db.add(user_message)

        session.status = SessionStatus.active
        db.commit()
        db.refresh(session)

        return {
            "intent_name": intent_name,
            "agent_name": agent.name if agent is not None else None,
        }
