import math
import os
import threading

import torch
from sentence_transformers import CrossEncoder, SentenceTransformer

MODEL_NAME = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
RERANK_MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
DEVICE = os.getenv("EMBEDDING_DEVICE") or (
    "cuda" if torch.cuda.is_available() else "cpu"
)

_model: SentenceTransformer | None = None
_reranker: CrossEncoder | None = None
_lock = threading.Lock()


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                _model = SentenceTransformer(MODEL_NAME, device=DEVICE)
    return _model


def get_reranker() -> CrossEncoder:
    global _reranker
    if _reranker is None:
        with _lock:
            if _reranker is None:
                _reranker = CrossEncoder(
                    RERANK_MODEL, device=DEVICE, max_length=512
                )
    return _reranker


def model_loaded() -> bool:
    return _model is not None


def reranker_loaded() -> bool:
    return _reranker is not None


def embed_texts(texts: list[str], batch_size: int = 16) -> list[list[float]]:
    model = get_model()
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return vectors.tolist()


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def rerank(
    query: str,
    passages: list[str],
    batch_size: int = 16,
) -> list[float]:
    if not passages:
        return []
    model = get_reranker()
    pairs = [(query, passage) for passage in passages]
    raw = model.predict(
        pairs,
        batch_size=batch_size,
        show_progress_bar=False,
    )
    scores = [float(value) for value in raw]
    # bge-reranker emits logits; normalize to [0, 1] when values fall outside.
    if any(score < 0.0 or score > 1.0 for score in scores):
        scores = [_sigmoid(score) for score in scores]
    return scores
