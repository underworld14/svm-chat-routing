from sqlalchemy.orm import Session

from app.models import (
    Agent,
    AgentIntent,
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


class AgentRouter:
    def find_best_agent(self, intent_name: str, db: Session) -> Agent | None:
        return find_best_agent(intent_name=intent_name, db=db)


class ChatService:
    def __init__(self, classifier: IntentClassifier | None = None) -> None:
        self.classifier = classifier or IntentClassifier()
        self.router = AgentRouter()

    def start_chat(self, db: Session, name: str, email: str) -> ChatSession:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            user = User(name=name, email=email)
            db.add(user)
            db.flush()

        session = ChatSession(
            status=SessionStatus.waiting,
            user_id=user.id,
            client_id=email,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    def classify_and_route(self, db: Session, session_id: int, message: str) -> dict[str, str | None]:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

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
        )
        db.add(user_message)

        session.status = SessionStatus.active
        db.commit()
        db.refresh(session)

        return {
            "intent_name": intent_name,
            "agent_name": agent.name if agent is not None else None,
        }
