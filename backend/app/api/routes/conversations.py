from uuid import UUID

from fastapi import APIRouter, Response, status

from app.api.dependencies import CurrentUser, DatabaseSession
from app.core.config import get_settings
from app.core.errors import AppError, ResourceNotFoundError
from app.models.enums import ConversationStatus
from app.repositories.conversations import (
    create_for_user,
    delete_conversation,
    get_for_user,
    list_for_user,
    update_conversation,
)
from app.repositories.messages import create_user_message, list_for_conversation
from app.schemas.conversation import (
    ConversationCreateRequest,
    ConversationResponse,
    ConversationUpdateRequest,
    MessageCreateRequest,
    MessageResponse,
)
from app.services.conversations import clean_up_conversation_files

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    session: DatabaseSession,
    current_user: CurrentUser,
) -> list[ConversationResponse]:
    conversations = await list_for_user(session, current_user.id)
    return [ConversationResponse.model_validate(item) for item in conversations]


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreateRequest,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> ConversationResponse:
    conversation = await create_for_user(
        session,
        user_id=current_user.id,
        title=payload.title,
    )
    return ConversationResponse.model_validate(conversation)


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation_route(
    conversation_id: UUID,
    payload: ConversationUpdateRequest,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> ConversationResponse:
    conversation = await get_for_user(
        session,
        conversation_id=conversation_id,
        user_id=current_user.id,
        for_update=True,
    )
    if conversation is None:
        raise ResourceNotFoundError("会话不存在")

    if payload.title is not None:
        conversation.title = payload.title
    if payload.status is not None:
        conversation.status = ConversationStatus(payload.status)

    updated = await update_conversation(session, conversation)
    return ConversationResponse.model_validate(updated)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation_route(
    conversation_id: UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> Response:
    conversation = await get_for_user(
        session,
        conversation_id=conversation_id,
        user_id=current_user.id,
        for_update=True,
    )
    if conversation is None:
        raise ResourceNotFoundError("会话不存在")

    await delete_conversation(session, conversation)
    settings = get_settings()
    clean_up_conversation_files(
        settings.storage_path,
        user_id=current_user.id,
        conversation_id=conversation_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    conversation_id: UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> list[MessageResponse]:
    conversation = await get_for_user(
        session,
        conversation_id=conversation_id,
        user_id=current_user.id,
    )
    if conversation is None:
        raise ResourceNotFoundError("会话不存在")

    messages = await list_for_conversation(session, conversation.id)
    return [MessageResponse.model_validate(item) for item in messages]


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_message(
    conversation_id: UUID,
    payload: MessageCreateRequest,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> MessageResponse:
    conversation = await get_for_user(
        session,
        conversation_id=conversation_id,
        user_id=current_user.id,
        for_update=True,
    )
    if conversation is None:
        raise ResourceNotFoundError("会话不存在")
    if conversation.status == ConversationStatus.ARCHIVED:
        raise AppError(
            code="CONVERSATION_ARCHIVED",
            message="已归档会话不能新增消息，请先恢复会话",
            status_code=409,
        )

    message = await create_user_message(
        session,
        conversation=conversation,
        content=payload.content,
    )
    return MessageResponse.model_validate(message)
