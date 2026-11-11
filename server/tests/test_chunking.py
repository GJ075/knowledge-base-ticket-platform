"""L1 单元测试：结构化切分的规则边界。"""

from app.services.chunking import (
    _split_table,
    parse_units,
    split_sentences,
    structure_chunks,
)

BASE = "本制度用于规范公司内部的日常管理流程与审批要求。"


def long_text(tag: str) -> str:
    return (tag + BASE) * 8


def build(text: str, max_len: int = 700):
    return structure_chunks(
        text, target=450, max_len=max_len, min_len=150, overlap=0
    )


def test_heading_path_follows_sections():
    text = (
        "# 制度A\n"
        "## 1. 目的\n" + long_text("目的方面，") + "\n\n"
        "## 2. 范围\n" + long_text("范围方面，")
    )
    chunks = build(text)
    assert len(chunks) == 2
    assert chunks[0].heading_path == ["制度A", "1. 目的"]
    assert chunks[1].heading_path == ["制度A", "2. 范围"]


def test_section_switch_flushes_buffer():
    text = (
        "## 1. 甲\n" + long_text("甲：") + "\n\n"
        "## 2. 乙\n" + long_text("乙：")
    )
    chunks = build(text)
    assert len(chunks) == 2
    assert "乙：" not in chunks[0].content


def test_table_kept_whole():
    text = (
        "## 4. 标准\n"
        "| 城市 | 住宿 |\n"
        "| 一类 | 600 |\n"
        "| 二类 | 450 |\n"
    )
    chunks = build(text)
    tables = [c for c in chunks if c.unit_type == "table"]
    assert len(tables) == 1
    assert "二类" in tables[0].content


def test_long_table_repeats_header():
    rows = "\n".join(f"| 城市{i} | 标准{i} |" for i in range(30))
    block = "| 城市 | 标准 |\n" + rows
    parts = _split_table(block, max_len=120)
    assert len(parts) > 1
    assert all(part.splitlines()[0].startswith("| 城市") for part in parts)


def test_long_paragraph_split_on_sentence():
    text = "这是一个用于测试的句子。" * 50
    parts = split_sentences(text, max_len=100, overlap=0)
    assert len(parts) > 1
    assert all(len(part) <= 100 for part in parts)
    assert all(part.endswith("。") for part in parts)


def test_oversized_single_sentence_hard_split():
    text = "甲" * 250
    parts = split_sentences(text, max_len=100, overlap=0)
    assert all(len(part) <= 100 for part in parts)
    assert "".join(parts) == text


def test_short_first_chunk_merged_forward():
    text = (
        "文档编号：IT-SOP-2026-003　版本：V2.1　责任部门：信息技术部\n\n"
        "## 1. 目的\n" + long_text("目的方面，")
    )
    chunks = build(text)
    assert len(chunks) == 1
    assert "文档编号" in chunks[0].content
    assert "目的方面" in chunks[0].content


def test_duplicate_content_removed():
    duplicate = long_text("重复：")
    text = (
        "## 1. 甲\n" + duplicate + "\n\n"
        "## 2. 乙\n" + duplicate
    )
    assert len(build(text)) == 1


def test_newlines_preserved():
    text = "## 1. 甲\n第一行内容\n第二行内容\n" + long_text("细节：")
    chunks = build(text)
    assert "\n" in chunks[0].content


def test_chinese_numeral_heading():
    units = parse_units("第三章 报销流程\n" + long_text("流程："))
    headings = [unit for unit in units if unit.kind == "heading"]
    assert headings[0].text == "第三章 报销流程"


def test_empty_document_returns_no_chunks():
    assert structure_chunks("   \n\n  ") == []
