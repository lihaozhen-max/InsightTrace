import json
from datetime import date

import pytest
from openpyxl import Workbook

from app.services.attachment_parsing import (
    AttachmentParsingError,
    ParsingLimits,
    parse_attachment_file,
)


@pytest.fixture
def parsing_limits() -> ParsingLimits:
    return ParsingLimits(
        max_rows=10,
        max_columns=5,
        max_sheets=2,
        max_text_chars=1_000,
        max_cell_chars=100,
        max_json_depth=4,
    )


def test_parse_csv_normalizes_duplicate_headers(tmp_path, parsing_limits) -> None:
    path = tmp_path / "sales.csv"
    path.write_text("商品,收入,收入\nA,120,100\n", encoding="utf-8")

    parsed = parse_attachment_file(path, parsing_limits)

    assert parsed["columns"] == ["商品", "收入", "收入_2"]
    assert parsed["rows"] == [{"商品": "A", "收入": "120", "收入_2": "100"}]
    assert parsed["row_count"] == 1


def test_parse_xlsx_preserves_sheets_and_dates(tmp_path, parsing_limits) -> None:
    path = tmp_path / "catalog.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "商品"
    worksheet.append(["商品", "上架日期", "销售额"])
    worksheet.append(["A", date(2026, 9, 17), 1200])
    workbook.create_sheet("空表")
    workbook.save(path)
    workbook.close()

    parsed = parse_attachment_file(path, parsing_limits)

    assert parsed["sheet_count"] == 2
    assert parsed["row_count"] == 1
    assert parsed["sheets"][0]["rows"][0] == {
        "商品": "A",
        "上架日期": "2026-09-17T00:00:00",
        "销售额": 1200,
    }


def test_parse_json_rejects_excessive_nesting(tmp_path, parsing_limits) -> None:
    path = tmp_path / "nested.json"
    path.write_text(json.dumps({"a": {"b": {"c": {"d": 1}}}}), encoding="utf-8")

    with pytest.raises(AttachmentParsingError, match="嵌套层级"):
        parse_attachment_file(path, parsing_limits)


def test_parse_txt_supports_gb18030(tmp_path, parsing_limits) -> None:
    path = tmp_path / "notes.txt"
    path.write_bytes("经营分析说明".encode("gb18030"))

    parsed = parse_attachment_file(path, parsing_limits)

    assert parsed["content"] == "经营分析说明"
    assert parsed["encoding"] == "gb18030"
