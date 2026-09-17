import logging
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Response, UploadFile, status
from fastapi.responses import FileResponse

from app.api.dependencies import CurrentUser, DatabaseSession
from app.core.config import get_settings
from app.core.errors import AppError, ResourceNotFoundError
from app.models.conversation import Attachment
from app.models.enums import ConversationStatus
from app.repositories.attachments import (
    create_attachment,
    delete_attachment,
    get_for_conversation,
    list_for_conversation,
    total_size_for_conversation,
)
from app.repositories.conversations import get_for_user
from app.schemas.attachment import AttachmentResponse
from app.services.attachments import resolve_attachment_path, store_upload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/conversations/{conversation_id}/attachments", tags=["attachments"])


async def _owned_conversation(
    conversation_id: UUID,
    session: DatabaseSession,
    user_id: UUID,
    *,
    for_update: bool = False,
):
    conversation = await get_for_user(
        session,
        conversation_id=conversation_id,
        user_id=user_id,
        for_update=for_update,
    )
    if conversation is None:
        raise ResourceNotFoundError("会话不存在")
    return conversation


async def _owned_attachment(
    attachment_id: UUID,
    conversation_id: UUID,
    session: DatabaseSession,
    user_id: UUID,
) -> Attachment:
    await _owned_conversation(conversation_id, session, user_id)
    attachment = await get_for_conversation(
        session,
        attachment_id=attachment_id,
        conversation_id=conversation_id,
    )
    if attachment is None:
        raise ResourceNotFoundError("附件不存在")
    return attachment


@router.get("", response_model=list[AttachmentResponse])
async def list_attachments(
    conversation_id: UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> list[AttachmentResponse]:
    await _owned_conversation(conversation_id, session, current_user.id)
    attachments = await list_for_conversation(session, conversation_id)
    return [AttachmentResponse.model_validate(item) for item in attachments]


@router.post("", response_model=AttachmentResponse, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    conversation_id: UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
    file: Annotated[UploadFile, File()],
) -> AttachmentResponse:
    conversation = await _owned_conversation(
        conversation_id,
        session,
        current_user.id,
        for_update=True,
    )
    if conversation.status == ConversationStatus.ARCHIVED:
        raise AppError(
            code="CONVERSATION_ARCHIVED",
            message="已归档会话不能上传附件，请先恢复会话",
            status_code=409,
        )

    settings = get_settings()
    current_size = await total_size_for_conversation(session, conversation_id)
    stored = None
    try:
        stored = await store_upload(
            file,
            storage_root=settings.storage_path,
            user_id=current_user.id,
            conversation_id=conversation_id,
            max_file_bytes=settings.attachment_max_file_bytes,
            remaining_conversation_bytes=settings.attachment_max_conversation_bytes - current_size,
        )
        attachment = await create_attachment(
            session,
            Attachment(
                conversation_id=conversation_id,
                file_name=stored.file_name,
                stored_name=stored.stored_name,
                file_path=stored.relative_path,
                file_type=stored.file_type,
                file_size=stored.file_size,
                sha256=stored.sha256,
            ),
        )
    except Exception:
        if stored is not None:
            stored.absolute_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    return AttachmentResponse.model_validate(attachment)


@router.get("/{attachment_id}/download", response_class=FileResponse)
async def download_attachment(
    conversation_id: UUID,
    attachment_id: UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> FileResponse:
    attachment = await _owned_attachment(
        attachment_id,
        conversation_id,
        session,
        current_user.id,
    )
    path = resolve_attachment_path(get_settings().storage_path, attachment.file_path)
    if not path.is_file():
        raise ResourceNotFoundError("附件文件不存在")
    return FileResponse(path, media_type=attachment.file_type, filename=attachment.file_name)


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_attachment(
    conversation_id: UUID,
    attachment_id: UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> Response:
    attachment = await _owned_attachment(
        attachment_id,
        conversation_id,
        session,
        current_user.id,
    )
    path = resolve_attachment_path(get_settings().storage_path, attachment.file_path)
    await delete_attachment(session, attachment)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Attachment file cleanup failed: %s", Path(attachment.file_path))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
