from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class WebSocketTokenRequest(BaseModel):
    conversation_id: UUID


class WebSocketTokenResponse(BaseModel):
    token: str
    conversation_id: UUID
    expires_at: datetime
    websocket_path: str = "/api/chat/ws/chat"
