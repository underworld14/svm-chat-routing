from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    email: str
    name: str


class AgentResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    is_online: bool
    current_load: int

    model_config = ConfigDict(from_attributes=True)


class SessionResponse(BaseModel):
    id: int
    user_id: int
    client_id: str
    channel: str = "whatsapp"
    intent_id: int | None = None
    assigned_agent_id: int | None = None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IntentResponse(BaseModel):
    id: int
    name: str
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)


class AdminReplyRequest(BaseModel):
    session_id: int
    agent_id: int | None = None
    content: str = Field(min_length=1, validation_alias="message")
    model_config = ConfigDict(populate_by_name=True)
