import os
import threading

import torch
from sentence_transformers import SentenceTransformer

MODEL_NAME = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
DEVICE = os.getenv("EMBEDDING_DEVICE") or (
    "cuda" if torch.cuda.is_available() else "cpu"
)

_model: SentenceTransformer | None = None
_lock = threading.Lock()


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                _model = SentenceTransformer(MODEL_NAME, device=DEVICE)
    return _model


def model_loaded() -> bool:
    return _model is not None


def embed_texts(texts: list[str], batch_size: int = 16) -> list[list[float]]:
    model = get_model()
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return vectors.tolist()
