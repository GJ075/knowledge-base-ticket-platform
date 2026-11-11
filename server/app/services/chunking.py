"""Structure-aware chunking.

Splits documents on structural boundaries (headings, paragraphs, lists,
tables) instead of fixed character counts, and keeps a heading path so
retrieval can report where a chunk came from.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from app.core.config import get_settings

_HEADING_MD = re.compile(r"^(#{1,6})\s*(.+?)\s*$")
_HEADING_CN = re.compile(r"^(第[一二三四五六七八九十百零〇\d]+[章节部分篇])\s*(.*)$")
_HEADING_NUM = re.compile(r"^(\d+(?:\.\d+){1,3})\.?\s+(\S.*)$")
_LIST_LINE = re.compile(
    r"^\s*(?:[-*+]\s+|\d+[.、．)]\s*|[（(]\d+[)）]\s*|[一二三四五六七八九十]+、)"
)
_TABLE_LINE = re.compile(r"^\s*\|.*\|\s*$")
_SENTENCE_END = re.compile(r"(?<=[。！？；!?;])")
_MULTI_BLANK = re.compile(r"\n{3,}")
_TOKEN_RATIO = 0.7


@dataclass
class TextUnit:
    text: str
    kind: str
    level: int = 0


@dataclass
class ChunkDraft:
    content: str
    heading_path: list[str] = field(default_factory=list)
    unit_type: str = "paragraph"

    @property
    def char_count(self) -> int:
        return len(self.content)

    @property
    def token_count(self) -> int:
        return int(len(self.content) * _TOKEN_RATIO)

    @property
    def content_hash(self) -> str:
        normalized = re.sub(r"\s+", "", self.content)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _match_heading(line: str) -> tuple[int, str] | None:
    match = _HEADING_MD.match(line)
    if match:
        return len(match.group(1)), match.group(2).strip()
    match = _HEADING_CN.match(line)
    if match:
        return 1, line.strip()
    match = _HEADING_NUM.match(line)
    if match and len(line.strip()) <= 40:
        return match.group(1).count(".") + 2, line.strip()
    return None


def _is_table(line: str) -> bool:
    return bool(_TABLE_LINE.match(line))


def _is_list(line: str) -> bool:
    return bool(_LIST_LINE.match(line))


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _MULTI_BLANK.sub("\n\n", text)
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def parse_units(text: str) -> list[TextUnit]:
    lines = _normalize(text).split("\n")
    units: list[TextUnit] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue

        heading = _match_heading(line)
        if heading:
            level, title = heading
            units.append(TextUnit(title, "heading", level))
            index += 1
            continue

        if _is_table(line):
            block = []
            while index < len(lines) and _is_table(lines[index]):
                block.append(lines[index])
                index += 1
            units.append(TextUnit("\n".join(block), "table"))
            continue

        kind = "list" if _is_list(line) else "paragraph"
        block = []
        while index < len(lines):
            current = lines[index]
            if not current.strip():
                break
            if _match_heading(current) or _is_table(current):
                break
            current_kind = "list" if _is_list(current) else "paragraph"
            if block and current_kind != kind:
                break
            block.append(current)
            index += 1
        units.append(TextUnit("\n".join(block), kind))
    return units


def split_sentences(text: str, max_len: int, overlap: int = 0) -> list[str]:
    parts = [part for part in _SENTENCE_END.split(text) if part.strip()]
    merged: list[str] = []
    buffer = ""
    for part in parts:
        if buffer and len(buffer) + len(part) > max_len:
            merged.append(buffer)
            buffer = (buffer[-overlap:] if overlap else "") + part
        else:
            buffer += part
    if buffer.strip():
        merged.append(buffer)

    result: list[str] = []
    for item in merged:
        while len(item) > max_len:
            result.append(item[:max_len].strip())
            item = item[max_len:]
        if item.strip():
            result.append(item.strip())
    return result


def _split_table(block: str, max_len: int) -> list[str]:
    rows = [row for row in block.split("\n") if row.strip()]
    if not rows:
        return []
    header = rows[0] if _is_table(rows[0]) else ""
    body = rows[1:] if header else rows
    chunks: list[str] = []
    buffer = [header] if header else []
    for row in body:
        candidate = "\n".join(buffer + [row])
        if buffer and len(candidate) > max_len:
            chunks.append("\n".join(buffer))
            buffer = [header, row] if header else [row]
        else:
            buffer.append(row)
    if buffer:
        chunks.append("\n".join(buffer))
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def structure_chunks(
    text: str,
    target: int | None = None,
    max_len: int | None = None,
    min_len: int | None = None,
    overlap: int | None = None,
) -> list[ChunkDraft]:
    settings = get_settings()
    target = target or settings.chunk_target
    max_len = max_len or settings.chunk_max
    min_len = min_len or settings.chunk_min
    overlap = overlap if overlap is not None else settings.chunk_overlap

    units = parse_units(text)
    drafts: list[ChunkDraft] = []
    heading_stack: list[tuple[int, str]] = []
    buffer: list[TextUnit] = []

    def heading_path() -> list[str]:
        return [title for _, title in heading_stack]

    def flush() -> None:
        if not buffer:
            return
        content = "\n".join(unit.text for unit in buffer).strip()
        buffer.clear()
        if content:
            drafts.append(
                ChunkDraft(content, heading_path(), "paragraph")
            )

    def emit(content: str, kind: str) -> None:
        if content.strip():
            drafts.append(ChunkDraft(content.strip(), heading_path(), kind))

    for unit in units:
        if unit.kind == "heading":
            flush()
            while heading_stack and heading_stack[-1][0] >= unit.level:
                heading_stack.pop()
            heading_stack.append((unit.level, unit.text))
            continue

        if unit.kind == "table":
            flush()
            for part in _split_table(unit.text, max_len):
                emit(part, "table")
            continue

        pending = len("\n".join(item.text for item in buffer)) if buffer else 0
        if buffer and pending + len(unit.text) > max_len:
            flush()

        if len(unit.text) > max_len:
            for part in split_sentences(unit.text, max_len, overlap):
                emit(part, unit.kind)
            continue

        buffer.append(unit)
        if len("\n".join(item.text for item in buffer)) >= target:
            flush()

    flush()

    merged: list[ChunkDraft] = []
    for draft in drafts:
        mergeable = (
            merged
            and draft.char_count < min_len
            and draft.unit_type != "table"
            and merged[-1].unit_type != "table"
        )
        if mergeable:
            merged[-1].content = f"{merged[-1].content}\n{draft.content}"
        else:
            merged.append(draft)

    if (
        len(merged) > 1
        and merged[0].char_count < min_len
        and merged[0].unit_type != "table"
        and merged[1].unit_type != "table"
    ):
        merged[1].content = f"{merged[0].content}\n{merged[1].content}"
        merged.pop(0)

    seen: set[str] = set()
    unique: list[ChunkDraft] = []
    for draft in merged:
        digest = draft.content_hash
        if digest in seen:
            continue
        seen.add(digest)
        unique.append(draft)
    return unique
