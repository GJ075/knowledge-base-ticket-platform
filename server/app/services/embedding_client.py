import httpx

from app.core.config import get_settings

settings = get_settings()


async def embed_query(text: str) -> list[float]:
    async with httpx.AsyncClient(
        timeout=settings.embedding_timeout_seconds
    ) as client:
        response = await client.post(
            f"{settings.embedding_service_url}/embed",
            json={"texts": [text], "batch_size": 1},
        )
        response.raise_for_status()
        return response.json()["embeddings"][0]


def embed_texts_sync(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    results: list[list[float]] = []
    with httpx.Client(timeout=settings.embedding_timeout_seconds) as client:
        for index in range(0, len(texts), 64):
            batch = texts[index : index + 64]
            response = client.post(
                f"{settings.embedding_service_url}/embed",
                json={
                    "texts": batch,
                    "batch_size": settings.embedding_batch_size,
                },
            )
            response.raise_for_status()
            results.extend(response.json()["embeddings"])
    return results
