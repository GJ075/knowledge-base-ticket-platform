"""L1 单元测试：文档头元数据提取。"""

from datetime import date

from app.services.document_metadata import extract_metadata

HEADER = (
    "文档编号：IT-SOP-2026-003　版本：V2.1　生效日期：2026-01-01　"
    "密级：内部公开　责任部门：信息技术部\n"
    "## 1. 目的\n本流程规定公司信息系统账号的管理要求。"
)


def test_extract_all_fields():
    metadata = extract_metadata("IT权限与账号管理流程", HEADER)
    assert metadata["version"] == "V2.1"
    assert metadata["department"] == "信息技术部"
    assert metadata["effective_date"] == date(2026, 1, 1)


def test_infer_doc_type_from_title():
    assert extract_metadata("IT权限与账号管理流程", HEADER)["doc_type"] == "流程"
    assert extract_metadata("费用报销管理规范", HEADER)["doc_type"] == "制度"
    assert extract_metadata("会议室与办公资源预订管理办法", HEADER)["doc_type"] == "制度"


def test_missing_fields_are_omitted():
    metadata = extract_metadata("未知文档", "只有正文，没有文档头。")
    assert "version" not in metadata
    assert "effective_date" not in metadata


def test_invalid_date_ignored():
    metadata = extract_metadata("文档", "生效日期：2026/01/01")
    assert "effective_date" not in metadata
