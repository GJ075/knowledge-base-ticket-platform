"""Deterministic MIME type resolution for uploaded files."""

import mimetypes
import re
from pathlib import Path

MIME_BY_SUFFIX = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": (
        "application/vnd.openxmlformats-officedocument"
        ".wordprocessingml.document"
    ),
    ".xls": "application/vnd.ms-excel",
    ".xlsx": (
        "application/vnd.openxmlformats-officedocument"
        ".spreadsheetml.sheet"
    ),
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": (
        "application/vnd.openxmlformats-officedocument"
        ".presentationml.presentation"
    ),
    ".odt": "application/vnd.oasis.opendocument.text",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".odp": "application/vnd.oasis.opendocument.presentation",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".csv": "text/csv",
}

_GENERIC_CONTENT_TYPES = {
    "",
    "application/octet-stream",
    "binary/octet-stream",
}
_MAX_CONTENT_TYPE_LENGTH = 128
_MIME_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$"
)


def _clean_content_type(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.split(";", 1)[0].strip().lower()
    if (
        cleaned in _GENERIC_CONTENT_TYPES
        or len(cleaned) > _MAX_CONTENT_TYPE_LENGTH
        or not _MIME_PATTERN.match(cleaned)
    ):
        return None
    return cleaned


def guess_mime_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return (
        MIME_BY_SUFFIX.get(suffix)
        or mimetypes.guess_type(filename)[0]
        or "application/octet-stream"
    )


def resolve_mime_type(
    filename: str, content_type: str | None = None
) -> str:
    """Explicit suffix mapping first, then a meaningful client type."""
    suffix = Path(filename).suffix.lower()
    if suffix in MIME_BY_SUFFIX:
        return MIME_BY_SUFFIX[suffix]
    cleaned = _clean_content_type(content_type)
    if cleaned:
        return cleaned
    return guess_mime_type(filename)
