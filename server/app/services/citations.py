"""Parse inline citation markers and decide which passages were used."""

from __future__ import annotations

import re

from app.services.retrieval import Retrieved

REF_PATTERN = re.compile(r"\[(\d{1,3})\]")
REFUSAL_MARKERS = (
    "无法回答",
    "无法确定",
    "没有找到",
    "资料不足",
    "未提供",
    "无法获取",
    "不清楚",
)


def is_refusal(answer: str) -> bool:
    text = (answer or "").strip()
    if not text:
        return True
    return any(marker in text for marker in REFUSAL_MARKERS)


def parse_refs(answer: str, count: int) -> tuple[list[int], int]:
    """Return (valid unique 1-based indices, invalid marker count)."""
    refs: list[int] = []
    invalid = 0
    for match in REF_PATTERN.finditer(answer or ""):
        index = int(match.group(1))
        if 1 <= index <= count:
            if index not in refs:
                refs.append(index)
        else:
            invalid += 1
    return refs, invalid


def select_used(
    items: list[Retrieved], answer: str, citation_required: bool = True
) -> tuple[list[tuple[int, Retrieved]], dict]:
    """Map the answer to the passages it cites.

    Returns ([(index, item), ...], meta). When the model omits markers, all
    kept items are returned as a fallback and meta.fallback is True.
    """
    meta: dict = {
        "candidate_count": len(items),
        "fallback": False,
        "invalid_refs": 0,
        "mode": "cited",
    }
    if not items:
        meta["mode"] = "empty"
        return [], meta
    if is_refusal(answer):
        meta["mode"] = "refusal"
        return [], meta

    refs, invalid = parse_refs(answer, len(items))
    meta["invalid_refs"] = invalid
    if refs:
        return [(index, items[index - 1]) for index in refs], meta

    meta["fallback"] = True
    meta["mode"] = "fallback" if citation_required else "all"
    return list(enumerate(items, start=1)), meta


def strip_markers(answer: str) -> str:
    return REF_PATTERN.sub("", answer or "")
