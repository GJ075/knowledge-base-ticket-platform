import asyncio
from collections.abc import AsyncGenerator

from openai import AsyncOpenAI

from app.core.config import get_settings

settings = get_settings()


def provider() -> str:
    configured = settings.llm_provider.lower().strip()
    if configured == "mock":
        return "mock"
    if configured == "deepseek":
        if not settings.deepseek_api_key.strip():
            raise RuntimeError("DEEPSEEK_API_KEY 未配置")
        return "deepseek"
    if settings.deepseek_api_key.strip():
        return "deepseek"
    return "mock"


async def stream_deepseek(
    messages: list[dict],
) -> AsyncGenerator[str, None]:
    client = AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        timeout=settings.llm_timeout_seconds,
    )
    stream = await client.chat.completions.create(
        model=settings.deepseek_model,
        messages=messages,
        stream=True,
        temperature=0.2,
    )
    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content or ""
        if delta:
            yield delta


async def stream_mock(
    citations: list[dict],
) -> AsyncGenerator[str, None]:
    if citations:
        snippets = [
            f"《{citation['document_title']}》：{citation['snippet'][:80]}"
            for citation in citations[:3]
        ]
        answer = (
            "（本地模拟回答，未配置 DeepSeek API Key）"
            "根据知识库资料："
            + "；".join(snippets)
            + "。"
        )
    else:
        answer = "根据现有知识库，我无法回答这个问题。"

    for char in answer:
        yield char
        await asyncio.sleep(0.005)
