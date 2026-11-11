"""Extract document level metadata from the document header."""

from __future__ import annotations

import re
from datetime import date, datetime

_FIELD_PATTERNS = {
    "version": re.compile(r"版本[：:]\s*(V\d+(?:\.\d+)*)", re.IGNORECASE),
    "department": re.compile(r"责任部门[：:]\s*([^\s　|｜]+)"),
    "effective_date": re.compile(r"生效日期[：:]\s*(\d{4}-\d{2}-\d{2})"),
    "doc_type": re.compile(r"文档类型[：:]\s*([^\s　|｜]+)"),
}

_TYPE_KEYWORDS = (
    ("流程", "流程"),
    ("规范", "制度"),
    ("办法", "制度"),
    ("规定", "制度"),
    ("手册", "制度"),
    ("指引", "指引"),
)


def _infer_type(title: str) -> str | None:
    for keyword, doc_type in _TYPE_KEYWORDS:
        if keyword in title:
            return doc_type
    return None


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def extract_metadata(title: str, text: str) -> dict:
    header = text[:800]
    metadata: dict = {"doc_type": _infer_type(title)}
    for field, pattern in _FIELD_PATTERNS.items():
        match = pattern.search(header)
        if not match:
            continue
        value = match.group(1).strip()
        if field == "effective_date":
            metadata[field] = _parse_date(value)
        else:
            metadata[field] = value
    return {key: value for key, value in metadata.items() if value}
