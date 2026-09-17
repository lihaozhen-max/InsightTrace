from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile

from app.core.errors import AppError, ResourceNotFoundError

ALLOWED_FILE_TYPES: dict[str, set[str]] = {
    ".csv": {"text/csv", "application/csv", "application/vnd.ms-excel", "text/plain"},
    ".xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",
    },
    ".json": {"application/json", "text/json", "text/plain"},
    ".txt": {"text/plain", "application/octet-stream"},
}
UPLOAD_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class StoredUpload:
    file_name: str
    stored_name: str
    relative_path: str
    file_type: str
    file_size: int
    sha256: str
    absolute_path: Path


def _validated_file_metadata(upload: UploadFile) -> tuple[str, str, str]:
    file_name = Path(upload.filename or "").name
    if not file_name or len(file_name) > 255:
        raise AppError(
            code="INVALID_FILE_NAME",
            message="附件名称为空或过长",
            status_code=422,
        )

    extension = Path(file_name).suffix.lower()
    content_type = (upload.content_type or "application/octet-stream").lower()
    if extension not in ALLOWED_FILE_TYPES or content_type not in ALLOWED_FILE_TYPES[extension]:
        raise AppError(
            code="FILE_TYPE_NOT_ALLOWED",
            message="仅支持 CSV、XLSX、JSON 和 TXT 文件",
            status_code=415,
        )
    return file_name, extension, content_type


async def store_upload(
    upload: UploadFile,
    *,
    storage_root: Path,
    user_id: UUID,
    conversation_id: UUID,
    max_file_bytes: int,
    remaining_conversation_bytes: int,
) -> StoredUpload:
    file_name, extension, content_type = _validated_file_metadata(upload)
    if remaining_conversation_bytes <= 0:
        raise AppError(
            code="CONVERSATION_STORAGE_LIMIT",
            message="该会话的附件总大小已达到 100 MB 上限",
            status_code=413,
        )

    destination_directory = storage_root / "uploads" / str(user_id) / str(conversation_id)
    destination_directory.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}{extension}"
    absolute_path = destination_directory / stored_name
    temporary_path = destination_directory / f".{stored_name}.part"
    digest = hashlib.sha256()
    file_size = 0

    try:
        with temporary_path.open("xb") as output:
            while chunk := await upload.read(UPLOAD_CHUNK_SIZE):
                file_size += len(chunk)
                if file_size > max_file_bytes:
                    raise AppError(
                        code="FILE_TOO_LARGE",
                        message="单个附件不能超过 20 MB",
                        status_code=413,
                    )
                if file_size > remaining_conversation_bytes:
                    raise AppError(
                        code="CONVERSATION_STORAGE_LIMIT",
                        message="该附件会使会话附件总大小超过 100 MB",
                        status_code=413,
                    )
                output.write(chunk)
                digest.update(chunk)

        temporary_path.replace(absolute_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        absolute_path.unlink(missing_ok=True)
        raise

    relative_path = absolute_path.relative_to(storage_root).as_posix()
    return StoredUpload(
        file_name=file_name,
        stored_name=stored_name,
        relative_path=relative_path,
        file_type=content_type,
        file_size=file_size,
        sha256=digest.hexdigest(),
        absolute_path=absolute_path,
    )


def resolve_attachment_path(storage_root: Path, relative_path: str) -> Path:
    root = storage_root.resolve()
    candidate = (root / relative_path).resolve()
    if not candidate.is_relative_to(root):
        raise ResourceNotFoundError("附件不存在")
    return candidate
