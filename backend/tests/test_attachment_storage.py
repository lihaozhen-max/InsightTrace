from io import BytesIO
from uuid import uuid4

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.core.errors import AppError, ResourceNotFoundError
from app.services.attachments import resolve_attachment_path, store_upload


@pytest.mark.asyncio
async def test_store_upload_rejects_files_over_the_configured_limit(tmp_path) -> None:
    upload = UploadFile(
        filename="large.txt",
        file=BytesIO(b"12345"),
        headers=Headers({"content-type": "text/plain"}),
    )

    with pytest.raises(AppError, match="单个附件不能超过") as captured:
        await store_upload(
            upload,
            storage_root=tmp_path,
            user_id=uuid4(),
            conversation_id=uuid4(),
            max_file_bytes=4,
            remaining_conversation_bytes=100,
        )

    assert captured.value.code == "FILE_TOO_LARGE"
    assert not list(tmp_path.rglob("*.part"))
    assert not list(tmp_path.rglob("*.txt"))


def test_resolve_attachment_path_rejects_directory_traversal(tmp_path) -> None:
    with pytest.raises(ResourceNotFoundError):
        resolve_attachment_path(tmp_path, "../outside/secrets.csv")
