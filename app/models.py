import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class SessionStatus(str, enum.Enum):
    waiting = "waiting"
    active = "active"
    closed = "closed"
    archived = "archived"


class MessageRole(str, enum.Enum):
    user = "user"
    agent = "agent"
    system = "system"


class ChatChannel(str, enum.Enum):
    whatsapp = "whatsapp"
    # Legacy value kept for existing SQLite rows only — new code always uses whatsapp.
    web = "web"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=True)
    phone = Column(String(32), unique=True, index=True, nullable=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    sessions = relationship("ChatSession", back_populates="user")


class Intent(Base):
    __tablename__ = "intents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(500), nullable=True)

    agent_intents = relationship("AgentIntent", back_populates="intent")
    sessions = relationship("ChatSession", back_populates="intent")


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    role = Column(String(100), nullable=False)
    is_online = Column(Boolean, default=True, nullable=False)
    current_load = Column(Integer, default=0, nullable=False)

    intents = relationship("AgentIntent", back_populates="agent")
    assigned_sessions = relationship("ChatSession", back_populates="assigned_agent")


class AgentIntent(Base):
    __tablename__ = "agent_intents"

    agent_id = Column(Integer, ForeignKey("agents.id"), primary_key=True)
    intent_id = Column(Integer, ForeignKey("intents.id"), primary_key=True)

    agent = relationship("Agent", back_populates="intents")
    intent = relationship("Intent", back_populates="agent_intents")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    client_id = Column(String(100), nullable=False, index=True)
    channel = Column(
        Enum(ChatChannel, name="chat_channel", native_enum=False),
        default=ChatChannel.whatsapp,
        nullable=False,
    )
    whatsapp_chat_id = Column(String(128), nullable=True, index=True)
    auto_ack_sent = Column(Boolean, default=False, nullable=False)
    intent_id = Column(Integer, ForeignKey("intents.id"), nullable=True)
    assigned_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    status = Column(
        Enum(SessionStatus, name="session_status", native_enum=False),
        default=SessionStatus.waiting,
        nullable=False,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="sessions")
    intent = relationship("Intent", back_populates="sessions")
    assigned_agent = relationship("Agent", back_populates="assigned_sessions")
    messages = relationship("Message", back_populates="session")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    role = Column(
        Enum(MessageRole, name="message_role", native_enum=False),
        nullable=False,
    )
    content = Column(Text, nullable=False)
    external_id = Column(String(255), unique=True, nullable=True, index=True)
    # Full WAHA webhook JSON for this inbound message (debug / future use).
    raw_event = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("ChatSession", back_populates="messages")
