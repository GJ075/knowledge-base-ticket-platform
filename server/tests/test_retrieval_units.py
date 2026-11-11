"""L1 单元测试：融合、去重、合并、预算。"""

from app.services.retrieval import (
    RRF_K,
    dedupe,
    fuse_rrf,
    merge_adjacent,
    within_budget,
)


def test_rrf_prefers_items_hit_by_both_routes(make_item):
    dense = [make_item(1), make_item(2)]
    sparse = [make_item(3), make_item(1)]
    fused = fuse_rrf([dense, sparse])
    assert [item.chunk_id for item in fused] == [1, 3, 2]


def test_rrf_single_route_scores_by_rank(make_item):
    fused = fuse_rrf([[make_item(10)], [make_item(20)]])
    assert fused[0].score > 0
    assert abs(fused[0].score - fused[1].score) < 1e-9


def test_rrf_empty_input():
    assert fuse_rrf([]) == []
    assert fuse_rrf([[], []]) == []


def test_rrf_score_formula(make_item):
    fused = fuse_rrf([[make_item(1)]], k=RRF_K)
    assert abs(fused[0].score - 1.0 / (RRF_K + 1)) < 1e-9


def test_dedupe_keeps_first(make_item):
    items = [
        make_item(1, content_hash="same"),
        make_item(2, content_hash="same"),
        make_item(3, content_hash="other"),
    ]
    result = dedupe(items)
    assert [item.chunk_id for item in result] == [1, 3]


def test_merge_adjacent_same_document(make_item):
    doc = make_item(1).document
    items = [
        make_item(1, chunk_index=3, document=doc, content="甲"),
        make_item(2, chunk_index=4, document=doc, content="乙"),
    ]
    merged = merge_adjacent(items)
    assert len(merged) == 1
    assert merged[0].content == "甲\n乙"
    assert merged[0].chunk_index == 4


def test_merge_adjacent_keeps_gap(make_item):
    doc = make_item(1).document
    items = [
        make_item(1, chunk_index=3, document=doc, content="甲"),
        make_item(2, chunk_index=5, document=doc, content="乙"),
    ]
    assert len(merge_adjacent(items)) == 2


def test_merge_adjacent_cross_document(make_item):
    items = [
        make_item(1, chunk_index=3, content="甲"),
        make_item(2, chunk_index=4, content="乙"),
    ]
    assert len(merge_adjacent(items)) == 2


def test_merge_adjacent_respects_size_limit(make_item):
    doc = make_item(1).document
    items = [
        make_item(1, chunk_index=0, document=doc, content="x" * 700),
        make_item(2, chunk_index=1, document=doc, content="y" * 600),
    ]
    assert len(merge_adjacent(items, max_chars=1200)) == 2


def test_within_budget_skips_oversized(make_item):
    items = [
        make_item(1, token_count=100),
        make_item(2, token_count=100),
        make_item(3, token_count=9999),
        make_item(4, token_count=50),
    ]
    result = within_budget(items, budget=300)
    assert [item.chunk_id for item in result] == [1, 2, 4]
