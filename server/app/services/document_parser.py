from io import BytesIO
from pathlib import Path

from docx import Document as DocxDocument
from pypdf import PdfReader

from app.core.config import get_settings
from app.core.errors import AppError
from app.services.text_cleaner import sanitize_text

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".md", ".markdown", ".txt"}


def validate_upload(filename: str, data: bytes) -> str:
    safe_name = Path(filename or "").name
    if not safe_name:
        raise AppError("DOC_UNSUPPORTED_TYPE", "文件名不能为空", 400)
    if len(safe_name) > 255:
        raise AppError(
            "VALIDATION_ERROR",
            "文件名不能超过 255 个字符",
            422,
        )
    suffix = Path(safe_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise AppError(
            "DOC_UNSUPPORTED_TYPE",
            f"不支持的文件类型：{suffix or '未知'}",
            400,
        )
    if not data:
        raise AppError("DOC_EMPTY", "文件内容为空", 400)
    settings = get_settings()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise AppError(
            "DOC_TOO_LARGE",
            f"文件不能超过 {settings.max_upload_mb}MB",
            400,
        )
    return suffix


def parse_document(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(BytesIO(data))
        text = "\n".join(
            (page.extract_text() or "") for page in reader.pages
        )
    elif suffix == ".docx":
        document = DocxDocument(BytesIO(data))
        text = "\n".join(
            paragraph.text for paragraph in document.paragraphs
        )
    else:
        text = data.decode("utf-8-sig", errors="replace")

    text = sanitize_text(text).strip()
    if not text:
        raise ValueError("文档没有可提取的文本")
    return text
