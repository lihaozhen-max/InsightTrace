from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import AttachmentParseStatus


class AttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    file_name: str
    file_type: str
    file_size: int
    sha256: str
    parse_status: AttachmentParseStatus
    parse_error: str | None
    created_at: datetime
