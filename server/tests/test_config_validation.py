"""L1 单元测试：配置不变量。"""

import pytest

from app.services.retrieval import RetrievalConfig


def test_default_config_is_valid():
    config = RetrievalConfig()
    assert config.final_k == 5


def test_threshold_requires_rerank():
    with pytest.raises(ValueError, match="rerank_enabled"):
        RetrievalConfig(rerank_enabled=False, rerank_threshold=0.2)


def test_threshold_out_of_range():
    with pytest.raises(ValueError, match="rerank_threshold"):
        RetrievalConfig(rerank_enabled=True, rerank_threshold=1.5)


def test_final_k_cannot_exceed_fused_k():
    with pytest.raises(ValueError, match="final_k"):
        RetrievalConfig(final_k=50, fused_k=40)


def test_candidate_k_cannot_be_less_than_final_k():
    with pytest.raises(ValueError, match="candidate_k"):
        RetrievalConfig(candidate_k=3, final_k=5)


def test_rerank_top_n_cannot_be_less_than_final_k():
    with pytest.raises(ValueError, match="rerank_top_n"):
        RetrievalConfig(
            rerank_enabled=True, rerank_top_n=2, final_k=5
        )


def test_token_budget_lower_bound():
    with pytest.raises(ValueError, match="context_token_budget"):
        RetrievalConfig(context_token_budget=100)


def test_from_settings_matches_environment_defaults():
    config = RetrievalConfig.from_settings()
    assert config.candidate_k >= config.final_k
    assert config.fused_k >= config.final_k
