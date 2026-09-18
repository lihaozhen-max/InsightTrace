from uuid import UUID

from fastapi import APIRouter, status

from app.api.dependencies import CurrentUser, DatabaseSession
from app.core.config import get_settings
from app.core.errors import AppError, ResourceNotFoundError
from app.models.enums import AnalysisMode, AttachmentParseStatus, ConversationStatus, TaskStatus
from app.repositories.attachments import list_selected_for_conversation
from app.repositories.conversations import get_for_user as get_conversation_for_user
from app.repositories.tasks import (
    cancel_task,
    create_task,
    get_for_user,
    list_for_conversation,
    list_logs,
)
from app.schemas.task import (
    TaskCreateRequest,
    TaskCreateResponse,
    TaskLogResponse,
    TaskResponse,
)

router = APIRouter(prefix="/api", tags=["tasks"])


async def _owned_task(
    task_id: UUID,
    session: DatabaseSession,
    user_id: UUID,
    *,
    for_update: bool = False,
):
    task = await get_for_user(
        session,
        task_id=task_id,
        user_id=user_id,
        for_update=for_update,
    )
    if task is None:
        raise ResourceNotFoundError("分析任务不存在")
    return task


async def _validate_attachments(
    session: DatabaseSession,
    *,
    conversation_id: UUID,
    attachment_ids: list[UUID],
) -> None:
    if len(set(attachment_ids)) != len(attachment_ids):
        raise AppError(
            code="DUPLICATE_ATTACHMENT",
            message="附件列表中不能包含重复项目",
            status_code=422,
        )
    attachments = await list_selected_for_conversation(
        session,
        conversation_id=conversation_id,
        attachment_ids=attachment_ids,
    )
    if len(attachments) != len(attachment_ids):
        raise ResourceNotFoundError("一个或多个附件不存在")
    if any(item.parse_status != AttachmentParseStatus.SUCCESS for item in attachments):
        raise AppError(
            code="ATTACHMENT_NOT_READY",
            message="所选附件尚未解析成功",
            status_code=409,
        )


@router.post("/tasks", response_model=TaskCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_analysis_task(
    payload: TaskCreateRequest,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> TaskCreateResponse:
    conversation = await get_conversation_for_user(
        session,
        conversation_id=payload.conversation_id,
        user_id=current_user.id,
        for_update=True,
    )
    if conversation is None:
        raise ResourceNotFoundError("会话不存在")
    if conversation.status == ConversationStatus.ARCHIVED:
        raise AppError(
            code="CONVERSATION_ARCHIVED",
            message="已归档会话不能创建分析任务，请先恢复会话",
            status_code=409,
        )
    await _validate_attachments(
        session,
        conversation_id=conversation.id,
        attachment_ids=payload.attachment_ids,
    )
    task = await create_task(
        session,
        conversation=conversation,
        user_id=current_user.id,
        input_text=payload.input_text,
        attachment_ids=payload.attachment_ids,
        analysis_mode=AnalysisMode(payload.analysis_mode or get_settings().analysis_mode),
    )
    return TaskCreateResponse.model_validate(task)


@router.get("/conversations/{conversation_id}/tasks", response_model=list[TaskResponse])
async def list_conversation_tasks(
    conversation_id: UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> list[TaskResponse]:
    conversation = await get_conversation_for_user(
        session,
        conversation_id=conversation_id,
        user_id=current_user.id,
    )
    if conversation is None:
        raise ResourceNotFoundError("会话不存在")
    tasks = await list_for_conversation(
        session,
        conversation_id=conversation_id,
        user_id=current_user.id,
    )
    return [TaskResponse.model_validate(item) for item in tasks]


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_analysis_task(
    task_id: UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> TaskResponse:
    return TaskResponse.model_validate(
        await _owned_task(task_id, session, current_user.id)
    )


@router.post("/tasks/{task_id}/cancel", response_model=TaskResponse)
async def cancel_analysis_task(
    task_id: UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> TaskResponse:
    task = await _owned_task(task_id, session, current_user.id, for_update=True)
    return TaskResponse.model_validate(await cancel_task(session, task))


@router.post(
    "/tasks/{task_id}/retry",
    response_model=TaskCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def retry_analysis_task(
    task_id: UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> TaskCreateResponse:
    original = await _owned_task(task_id, session, current_user.id)
    if original.task_status not in (TaskStatus.FAILED, TaskStatus.CANCELLED):
        raise AppError(
            code="TASK_NOT_RETRYABLE",
            message="只有失败或已取消的任务可以重新分析",
            status_code=409,
        )
    conversation = await get_conversation_for_user(
        session,
        conversation_id=original.conversation_id,
        user_id=current_user.id,
        for_update=True,
    )
    if conversation is None:
        raise ResourceNotFoundError("会话不存在")
    if conversation.status == ConversationStatus.ARCHIVED:
        raise AppError(
            code="CONVERSATION_ARCHIVED",
            message="已归档会话不能重新创建分析任务，请先恢复会话",
            status_code=409,
        )
    attachment_ids = [UUID(item) for item in original.input_payload_json.get("attachment_ids", [])]
    await _validate_attachments(
        session,
        conversation_id=conversation.id,
        attachment_ids=attachment_ids,
    )
    task = await create_task(
        session,
        conversation=conversation,
        user_id=current_user.id,
        input_text=original.input_text,
        attachment_ids=attachment_ids,
        analysis_mode=original.analysis_mode,
        retry_of_task_id=original.id,
        save_user_message=False,
    )
    return TaskCreateResponse.model_validate(task)


@router.get("/tasks/{task_id}/logs", response_model=list[TaskLogResponse])
async def get_task_logs(
    task_id: UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> list[TaskLogResponse]:
    task = await _owned_task(task_id, session, current_user.id)
    logs = await list_logs(session, task.id)
    return [TaskLogResponse.model_validate(item) for item in logs]
