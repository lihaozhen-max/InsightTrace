import os
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.core.errors import AppError
from app.db.session import SessionLocal
from app.models.conversation import Attachment, Conversation
from app.models.enums import AttachmentParseStatus
from app.models.identity import User
from app.tools.attachment_content import AttachmentContentTool, iter_content_items


def test_iterates_supported_parsed_content_shapes() -> None:
    table = {
        "kind": "table",
        "rows": [{"商品": "咖啡", "销量": 12}, {"商品": "茶", "销量": 8}],
    }
    assert list(iter_content_items(table)) == [
        ("row:1", "商品=咖啡 | 销量=12"),
        ("row:2", "商品=茶 | 销量=8"),
    ]
    workbook = {"kind": "workbook", "sheets": [{"name": "华东", "rows": [{"收入": 99}]}]}
    assert list(iter_content_items(workbook)) == [("sheet:华东/row:1", "收入=99")]
    text = {"kind": "text", "content": "第一行\n第二行"}
    assert list(iter_content_items(text)) == [("line:1", "第一行"), ("line:2", "第二行")]
    data = {"kind": "json", "data": {"region": "华南", "items": [1, 2]}}
    assert list(iter_content_items(data)) == [
        ("$.region", "华南"),
        ("$.items[0]", "1"),
        ("$.items[1]", "2"),
    ]


@pytest.mark.asyncio
async def test_rejects_empty_search_before_database_access() -> None:
    tool = AttachmentContentTool(None)  # type: ignore[arg-type]
    with pytest.raises(AppError) as error:
        await tool.search(
            attachment_id=uuid4(),
            conversation_id=uuid4(),
            user_id=uuid4(),
            query="  ",
        )
    assert error.value.code == "SEARCH_QUERY_EMPTY"


@pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 to run attachment content integration tests",
)
@pytest.mark.asyncio
async def test_searches_owned_parsed_attachment_and_hides_other_users() -> None:
    marker = uuid4().hex
    async with SessionLocal() as session:
        owner = User(
            external_user_id=f"attachment-owner-{marker}",
            username=f"attachment-owner-{marker}",
            display_name="附件所有者",
        )
        stranger = User(
            external_user_id=f"attachment-stranger-{marker}",
            username=f"attachment-stranger-{marker}",
            display_name="其他用户",
        )
        session.add_all([owner, stranger])
        await session.flush()
        conversation = Conversation(user_id=owner.id, title="附件检索测试")
        session.add(conversation)
        await session.flush()
        attachment = Attachment(
            conversation_id=conversation.id,
            file_name="sales.csv",
            stored_name=f"{marker}.csv",
            file_path=f"uploads/{marker}.csv",
            file_type="text/csv",
            file_size=42,
            sha256="0" * 64,
            parse_status=AttachmentParseStatus.SUCCESS,
            parsed_content_json={
                "kind": "table",
                "source_format": "csv",
                "columns": ["商品", "地区", "销量"],
                "row_count": 2,
                "rows": [
                    {"商品": "咖啡", "地区": "华东", "销量": 12},
                    {"商品": "茶", "地区": "华南", "销量": 8},
                ],
            },
        )
        session.add(attachment)
        await session.commit()

        tool = AttachmentContentTool(session)
        summary = await tool.describe(
            attachment_id=attachment.id,
            conversation_id=conversation.id,
            user_id=owner.id,
        )
        assert summary.row_count == 2
        assert summary.columns == ["商品", "地区", "销量"]
        result = await tool.search(
            attachment_id=attachment.id,
            conversation_id=conversation.id,
            user_id=owner.id,
            query="咖啡 华东",
        )
        assert result.scanned_items == 2
        assert result.hits[0].location == "row:1"
        assert result.hits[0].score == 2

        with pytest.raises(AppError) as error:
            await tool.search(
                attachment_id=attachment.id,
                conversation_id=conversation.id,
                user_id=stranger.id,
                query="咖啡",
            )
        assert error.value.status_code == 404

        await session.execute(delete(User).where(User.id.in_([owner.id, stranger.id])))
        await session.commit()
