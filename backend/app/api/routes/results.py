from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.api.dependencies import CurrentUser, DatabaseSession
from app.core.config import get_settings
from app.core.errors import ResourceNotFoundError
from app.models.analysis import AnalysisResult
from app.repositories.results import get_for_user
from app.schemas.result import AnalysisResultResponse, ResultExportResponse
from app.services.results import export_markdown_report, resolve_result_path

router = APIRouter(prefix="/api/results", tags=["results"])


async def _owned_result(
    task_id: UUID,
    session: DatabaseSession,
    user_id: UUID,
    *,
    for_update: bool = False,
) -> AnalysisResult:
    result = await get_for_user(
        session,
        task_id=task_id,
        user_id=user_id,
        for_update=for_update,
    )
    if result is None:
        raise ResourceNotFoundError("分析结果不存在")
    return result


def _response(result: AnalysisResult) -> AnalysisResultResponse:
    next_actions = [
        line.removeprefix("- ").strip()
        for line in result.next_action_text.splitlines()
        if line.strip()
    ]
    return AnalysisResultResponse(
        id=result.id,
        task_id=result.task_id,
        conversation_id=result.conversation_id,
        problem_definition=result.problem_definition,
        key_metrics=result.key_metrics_json,
        evidence_list=result.evidence_list_json,
        conclusion_text=result.conclusion_text,
        missing_data_text=result.missing_data_text,
        next_actions=next_actions,
        result_markdown=result.result_markdown,
        result_version=result.result_version,
        generated_by=result.generated_by,
        confidence=result.confidence,
        report_available=result.result_file_path is not None,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


@router.get("/{task_id}", response_model=AnalysisResultResponse)
async def get_analysis_result(
    task_id: UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> AnalysisResultResponse:
    return _response(await _owned_result(task_id, session, current_user.id))


@router.post("/{task_id}/export", response_model=ResultExportResponse)
async def export_analysis_result(
    task_id: UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> ResultExportResponse:
    result = await _owned_result(
        task_id,
        session,
        current_user.id,
        for_update=True,
    )
    await export_markdown_report(
        session,
        result,
        storage_root=get_settings().storage_path,
        user_id=current_user.id,
    )
    return ResultExportResponse(
        task_id=task_id,
        file_name="report.md",
        download_path=f"/api/results/{task_id}/download",
    )


@router.get("/{task_id}/download", response_class=FileResponse)
async def download_analysis_result(
    task_id: UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> FileResponse:
    result = await _owned_result(task_id, session, current_user.id)
    if result.result_file_path is None:
        raise ResourceNotFoundError("分析报告尚未生成")
    path = resolve_result_path(get_settings().storage_path, result.result_file_path)
    if not path.is_file():
        raise ResourceNotFoundError("分析报告文件不存在")
    return FileResponse(path, media_type="text/markdown; charset=utf-8", filename="report.md")
