from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from app.models.enums import ConversationStatus, MessageRole, MessageType

ConversationTitle = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]


class ConversationCreateRequest(BaseModel):
    title: ConversationTitle


class ConversationUpdateRequest(BaseModel):
    title: ConversationTitle | None = None
    status: Literal["active", "archived"] | None = None

    @model_validator(mode="after")
    def require_change(self) -> Self:
        if self.title is None and self.status is None:
            raise ValueError("至少需要提供一个要修改的字段")
        return self


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    status: ConversationStatus
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime


MessageContent = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000),
]


class MessageCreateRequest(BaseModel):
    content: MessageContent


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    role: MessageRole
    message_type: MessageType
    content: str
    seq_no: int
    created_at: datetime
