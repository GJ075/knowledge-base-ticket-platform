import asyncio
import os

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.model import (
    DEVICE,
    MODEL_NAME,
    RERANK_MODEL,
    embed_texts,
    model_loaded,
    rerank,
    reranker_loaded,
)

app = FastAPI(title="BGE-M3 Embedding Service", version="0.2.0")


class EmbedRequest(BaseModel):
    texts: list[str] = Field(min_length=1)
    batch_size: int | None = None


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]
    dimension: int
    model: str


class RerankRequest(BaseModel):
    query: str = Field(min_length=1)
    passages: list[str] = Field(min_length=1)
    batch_size: int | None = None


class RerankResponse(BaseModel):
    scores: list[float]
    model: str


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "device": DEVICE,
        "model": MODEL_NAME,
        "model_loaded": model_loaded(),
        "rerank_model": RERANK_MODEL,
        "reranker_loaded": reranker_loaded(),
    }


@app.post("/rerank", response_model=RerankResponse)
async def rerank_passages(payload: RerankRequest) -> RerankResponse:
    batch_size = payload.batch_size or int(
        os.getenv("EMBEDDING_BATCH_SIZE", "16")
    )
    scores = await asyncio.to_thread(
        rerank, payload.query, payload.passages, batch_size
    )
    return RerankResponse(scores=scores, model=RERANK_MODEL)


@app.post("/embed", response_model=EmbedResponse)
async def embed(payload: EmbedRequest) -> EmbedResponse:
    batch_size = payload.batch_size or int(
        os.getenv("EMBEDDING_BATCH_SIZE", "16")
    )
    vectors = await asyncio.to_thread(
        embed_texts, payload.texts, batch_size
    )
    dimension = len(vectors[0]) if vectors else 0
    return EmbedResponse(
        embeddings=vectors,
        dimension=dimension,
        model=MODEL_NAME,
    )
