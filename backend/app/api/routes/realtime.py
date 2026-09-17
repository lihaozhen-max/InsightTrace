import asyncio
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.api.dependencies import CurrentUser, DatabaseSession
from app.core.config import get_settings
from app.core.errors import ResourceNotFoundError
from app.db.session import SessionLocal
from app.models.analysis import AnalysisTask
from app.models.enums import TaskStatus
from app.repositories.conversations import get_for_user as get_conversation_for_user
from app.repositories.tasks import get_latest_for_conversation
from app.repositories.websocket_tokens import consume_token, create_token
from app.schemas.realtime import WebSocketTokenRequest, WebSocketTokenResponse

router = APIRouter(prefix="/api/chat", tags=["realtime"])


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _event(
    event_type: str,
    *,
    conversation_id: UUID,
    sequence_no: int,
    task: AnalysisTask | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "event_id": str(uuid4()),
        "event_type": event_type,
        "task_id": str(task.id) if task is not None else None,
        "conversation_id": str(conversation_id),
        "seq_no": sequence_no,
        "timestamp": datetime.now(UTC).isoformat(),
        "payload": payload or {},
    }


@router.post("/ws-token", response_model=WebSocketTokenResponse)
async def issue_websocket_token(
    payload: WebSocketTokenRequest,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> WebSocketTokenResponse:
    conversation = await get_conversation_for_user(
        session,
        conversation_id=payload.conversation_id,
        user_id=current_user.id,
    )
    if conversation is None:
        raise ResourceNotFoundError("会话不存在")

    settings = get_settings()
    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.websocket_token_ttl_seconds)
    await create_token(
        session,
        user_id=current_user.id,
        conversation_id=conversation.id,
        token_hash=_token_hash(raw_token),
        expires_at=expires_at,
    )
    return WebSocketTokenResponse(
        token=raw_token,
        conversation_id=conversation.id,
        expires_at=expires_at,
    )


@router.websocket("/ws/chat")
async def realtime_chat(
    websocket: WebSocket,
    websocket_token: Annotated[str, Query(min_length=20)],
    conversation_id: Annotated[UUID, Query()],
) -> None:
    await websocket.accept()
    async with SessionLocal() as session:
        token = await consume_token(
            session,
            token_hash=_token_hash(websocket_token),
            conversation_id=conversation_id,
        )
        if token is None:
            await websocket.send_json(
                _event(
                    "error",
                    conversation_id=conversation_id,
                    sequence_no=0,
                    payload={
                        "error_code": "WEBSOCKET_TOKEN_INVALID",
                        "error_message": "实时连接令牌无效、过期或已使用",
                        "retryable": True,
                    },
                )
            )
            await websocket.close(code=4401)
            return

        sequence_no = 0
        await websocket.send_json(
            _event(
                "connected",
                conversation_id=conversation_id,
                sequence_no=sequence_no,
                payload={"connection_id": str(uuid4())},
            )
        )
        observed: tuple[UUID, int, TaskStatus, str | None] | None = None
        try:
            while True:
                task = await get_latest_for_conversation(
                    session,
                    conversation_id=conversation_id,
                    user_id=token.user_id,
                )
                if task is not None:
                    current = (task.id, task.version, task.task_status, task.current_step)
                    if current != observed:
                        sequence_no += 1
                        await websocket.send_json(
                            _event(
                                "task_status",
                                conversation_id=conversation_id,
                                sequence_no=sequence_no,
                                task=task,
                                payload={
                                    "task_status": task.task_status.value,
                                    "current_step": task.current_step,
                                    "cancel_requested": task.cancel_requested_at is not None,
                                },
                            )
                        )
                        observed = current
                    if task.task_status in (
                        TaskStatus.SUCCESS,
                        TaskStatus.FAILED,
                        TaskStatus.CANCELLED,
                    ):
                        sequence_no += 1
                        await websocket.send_json(
                            _event(
                                "done",
                                conversation_id=conversation_id,
                                sequence_no=sequence_no,
                                task=task,
                                payload={
                                    "final_status": task.task_status.value,
                                    "finished_at": (
                                        task.finished_at.isoformat() if task.finished_at else None
                                    ),
                                },
                            )
                        )
                        await websocket.close(code=1000)
                        return
                await asyncio.sleep(1)
                session.expire_all()
        except WebSocketDisconnect:
            return
