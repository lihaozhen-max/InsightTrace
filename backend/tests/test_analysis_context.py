import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.db.session import SessionLocal
from app.models.analysis import AnalysisTask
from app.models.conversation import ContextSummary, Conversation, Message
from app.models.enums import AnalysisMode, MessageRole, MessageType, TaskStatus
from app.models.identity import User
from app.schemas.context import AnalysisContext, ContextAttachment
from app.services.analysis_context import (
    assemble_analysis_context,
    build_attachment_excerpt,
    omit_attachment_rows_for_grounded_model,
    summarize_messages,
)


def test_summarize_messages_obeys_character_limit() -> None:
    messages = [
        Message(conversation_id=uuid4(), role=MessageRole.USER, message_type=MessageType.TEXT,
                content="第一条问题 " * 20, seq_no=1),
        Message(conversation_id=uuid4(), role=MessageRole.ASSISTANT,
                message_type=MessageType.TEXT, content="第一条回答", seq_no=2),
    ]
    summary = summarize_messages(messages, max_chars=50)
    assert len(summary) <= 50
    assert summary.startswith("用户[1]：")


def test_builds_bounded_workbook_excerpt_with_real_rows() -> None:
    excerpt, truncated = build_attachment_excerpt(
        {
            "kind": "workbook",
            "sheets": [
                {
                    "name": "商品漏斗",
                    "columns": ["月份", "渠道", "下单量"],
                    "row_count": 2,
                    "rows": [
                        {"月份": "2026-07", "渠道": "organic", "下单量": 10},
                        {"月份": "2026-08", "渠道": "paid_social", "下单量": 4},
                    ],
                }
            ],
        },
        max_rows=10,
        max_chars=10_000,
    )

    assert truncated is False
    assert isinstance(excerpt, dict)
    assert excerpt["sheets"][0]["rows"][1]["下单量"] == 4


def test_marks_attachment_excerpt_as_truncated() -> None:
    excerpt, truncated = build_attachment_excerpt(
        {"kind": "table", "columns": ["值"], "row_count": 2, "rows": [{"值": 1}, {"值": 2}]},
        max_rows=1,
        max_chars=1_000,
    )

    assert truncated is True
    assert isinstance(excerpt, dict)
    assert excerpt["rows"] == [{"值": 1}]


def test_omits_raw_rows_after_deterministic_grounding() -> None:
    context = AnalysisContext(
        conversation_id=uuid4(),
        task_id=uuid4(),
        current_question="为什么下降？",
        earlier_summary=None,
        recent_messages=[],
        previous_analysis=None,
        attachments=[
            ContextAttachment(
                attachment_id=uuid4(),
                file_name="funnel.xlsx",
                content_kind="table",
                source_format="xlsx",
                data_excerpt={"kind": "table", "rows": [{"订单量": 10}] * 100},
            )
        ],
    )

    compact = omit_attachment_rows_for_grounded_model(context)

    assert context.attachments[0].data_excerpt is not None
    assert compact.attachments[0].data_excerpt is None
    assert compact.attachments[0].data_omitted_reason is not None
    assert len(compact.model_dump_json()) < len(context.model_dump_json()) / 2


@pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 to run context assembly integration tests",
)
@pytest.mark.asyncio
async def test_assembles_recent_messages_and_reuses_persisted_summary() -> None:
    marker = uuid4().hex
    async with SessionLocal() as session:
        user = User(
            external_user_id=f"context-{marker}",
            username=f"context-{marker}",
            display_name="上下文测试用户",
        )
        session.add(user)
        await session.flush()
        conversation = Conversation(user_id=user.id, title="上下文测试")
        session.add(conversation)
        await session.flush()
        session.add_all(
            [
                Message(
                    conversation_id=conversation.id,
                    role=MessageRole.USER if index % 2 else MessageRole.ASSISTANT,
                    message_type=MessageType.TEXT,
                    content=f"历史消息 {index}",
                    seq_no=index,
                )
                for index in range(1, 7)
            ]
        )
        task = AnalysisTask(
            conversation_id=conversation.id,
            user_id=user.id,
            input_text="为什么转化下降？",
            input_payload_json={"attachment_ids": []},
            analysis_mode=AnalysisMode.DEMO,
            task_status=TaskStatus.RUNNING,
        )
        session.add(task)
        await session.commit()

        context = await assemble_analysis_context(session, task, recent_message_limit=2)
        assert context.current_question == "为什么转化下降？"
        assert [item.seq_no for item in context.recent_messages] == [5, 6]
        assert context.earlier_summary is not None
        assert "历史消息 1" in context.earlier_summary
        await session.commit()

        repeated = await assemble_analysis_context(session, task, recent_message_limit=2)
        assert repeated.earlier_summary == context.earlier_summary
        summary_count = await session.scalar(
            select(func.count(ContextSummary.id)).where(
                ContextSummary.conversation_id == conversation.id
            )
        )
        assert summary_count == 1

        await session.execute(delete(AnalysisTask).where(AnalysisTask.id == task.id))
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()
