from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.models.enums import ConversationStatus

ConversationTitle = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]


class ConversationCreateRequest(BaseModel):
    title: ConversationTitle


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    status: ConversationStatus
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime
