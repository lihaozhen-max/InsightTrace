from fastapi import APIRouter, status

from app.api.dependencies import CurrentUser, DatabaseSession
from app.repositories.conversations import create_for_user, list_for_user
from app.schemas.conversation import ConversationCreateRequest, ConversationResponse

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
