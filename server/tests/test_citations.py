"""L1 单元测试：引用编号解析、引用选择、阈值与落差过滤。"""

import pytest

from app.services.citations import is_refusal, parse_refs, select_used
from app.services.retrieval import RetrievalConfig, filter_by_relevance


def config(**overrides):
    base = dict(
        candidate_k=10,
        fused_k=10,
        final_k=5,
        rerank_enabled=True,
        rerank_top_n=5,
        rerank_threshold=0.3,
        rerank_delta=0.15,
    )
    base.update(overrides)
    return RetrievalConfig(**base)


def test_parse_refs_keeps_order_and_dedupes():
    refs, invalid = parse_refs("甲[2]乙[1]丙[2]", 3)
    assert refs == [2, 1]
    assert invalid == 0


def test_parse_refs_drops_out_of_range():
    refs, invalid = parse_refs("见[1]与[9]，还有[0]", 3)
    assert refs == [1]
    assert invalid == 2


def test_select_used_maps_indices(make_item):
    items = [make_item(1), make_item(2), make_item(3)]
    used, meta = select_used(items, "结论一[2]，结论二[2]，补充[3]")
    assert [index for index, _ in used] == [2, 3]
    assert [item.chunk_id for _, item in used] == [2, 3]
    assert meta["fallback"] is False
    assert meta["mode"] == "cited"


def test_select_used_fallback_without_markers(make_item):
    items = [make_item(1), make_item(2)]
    used, meta = select_used(items, "这是一段没有编号的回答。")
    assert [item.chunk_id for _, item in used] == [1, 2]
    assert meta["fallback"] is True
    assert meta["mode"] == "fallback"


def test_select_used_refusal_returns_empty(make_item):
    items = [make_item(1)]
    used, meta = select_used(items, "根据现有知识库，我无法回答这个问题。")
    assert used == []
    assert meta["mode"] == "refusal"


def test_is_refusal_detects_empty_answer():
    assert is_refusal("")
    assert is_refusal("资料中没有相关内容")


def test_filter_applies_threshold_and_delta(make_item):
    items = [
        make_item(1, score=0.92),
        make_item(2, score=0.80),
        make_item(3, score=0.50),
        make_item(4, score=0.20),
    ]
    kept = filter_by_relevance(items, config())
    assert [item.chunk_id for item in kept] == [1, 2]


def test_filter_empty_returns_empty():
    assert filter_by_relevance([], config()) == []


def test_threshold_requires_rerank():
    with pytest.raises(ValueError):
        config(rerank_enabled=False)
