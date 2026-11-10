"""Generate evaluation case drafts from indexed document chunks.

Usage (inside the api container):
    python -m scripts.generate_eval_drafts --single 30 --multi 10 \
        --out /app/eval-drafts.jsonl

The output is a JSONL file in the evaluation import format. It is NOT
written to the database; review it first and import it from the UI.
"""

import argparse
import asyncio
import json
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models.document import Document, DocumentChunk
from app.services import llm_client

settings = get_settings()

SINGLE_PROMPT = """你是企业知识库的评测数据集编写员。下面是文档《{title}》的一个片段：

{content}

请基于该片段编写 1 个单轮评测用例，要求：
- 问题必须是员工真实可能问的中文问题，答案能且只能从片段中得到；
- 参考答案要简短、准确，不添加片段之外的信息；
- 输出 JSON，不要输出解释或代码块：
{{"title": "用例标题", "question": "问题", "reference_answer": "参考答案"}}
"""

UNANSWERABLE_PROMPT = """你是企业知识库的评测数据集编写员。知识库文档包括：
{titles}

请编写 1 个“知识库无法回答”的中文问题（例如询问具体某天的临时通知、外部信息、个人隐私），
要求问题看起来合理，但无法从上述文档中得到答案。
输出 JSON，不要输出代码块：
{{"title": "用例标题", "question": "问题"}}
"""

MULTI_PROMPT = """你是企业知识库的评测数据集编写员。下面是文档《{title}》的片段：

{content}

请编写 1 个两轮的中文对话评测用例，要求：
- 第一轮问一个能由片段回答的问题；
- 第二轮用指代或追问（如“它”“那需要提前多久”），必须依赖第一轮上下文才能理解；
- 每轮都要有简短、准确的参考答案，且只能来自片段；
- 输出 JSON，不要输出代码块：
{{"title": "用例标题", "turns": [{{"question": "问题1", "reference_answer": "答案1"}}, {{"question": "问题2", "reference_answer": "答案2"}}]}}
"""


def _parse_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    match = re.search(r"\{.*\}", cleaned, re.S)
    if not match:
        raise ValueError("模型输出不是 JSON")
    return json.loads(match.group(0))


async def _ask(prompt: str) -> dict:
    messages = [
        {
            "role": "system",
            "content": "你只输出合法的 JSON，不输出解释。",
        },
        {"role": "user", "content": prompt},
    ]
    text = await llm_client.complete_deepseek(
        messages, temperature=0.3, max_tokens=600
    )
    return _parse_json(text)


async def _load_corpus(db: AsyncSession) -> list[tuple[str, list[str]]]:
    rows = (
        await db.execute(
            select(Document.title, DocumentChunk.content)
            .join(
                DocumentChunk,
                DocumentChunk.document_id == Document.id,
            )
            .where(
                Document.is_deleted.is_(False),
                Document.index_status == "ready",
            )
            .order_by(Document.created_at, DocumentChunk.chunk_index)
        )
    ).all()
    corpus: dict[str, list[str]] = {}
    for title, content in rows:
        corpus.setdefault(title, []).append(content)
    return list(corpus.items())


def _pick_chunk(chunks: list[str], round_index: int) -> str:
    if not chunks:
        return ""
    return chunks[round_index % len(chunks)]


async def _generate_single(
    corpus: list[tuple[str, list[str]]], count: int
) -> list[dict]:
    cases: list[dict] = []
    unanswerable_every = 5
    titles = "、".join(title for title, _ in corpus)
    for index in range(count):
        if index and index % unanswerable_every == 0:
            try:
                data = await _ask(
                    UNANSWERABLE_PROMPT.format(titles=titles)
                )
                cases.append(
                    {
                        "type": "case",
                        "title": str(data.get("title") or f"无答案问题{index}"),
                        "tags": ["single_turn", "unanswerable"],
                        "turns": [
                            {
                                "question": str(data["question"]).strip(),
                                "reference_answer": None,
                                "expected_type": "unanswerable",
                                "required_document_titles": [],
                            }
                        ],
                    }
                )
            except Exception as exc:
                print(f"[skip] unanswerable #{index}: {exc}")
            continue

        title, chunks = corpus[index % len(corpus)]
        chunk = _pick_chunk(chunks, index)
        try:
            data = await _ask(
                SINGLE_PROMPT.format(title=title, content=chunk)
            )
            cases.append(
                {
                    "type": "case",
                    "title": str(data.get("title") or f"单轮用例{index}")[:255],
                    "tags": ["single_turn", "answerable"],
                    "turns": [
                        {
                            "question": str(data["question"]).strip(),
                            "reference_answer": str(
                                data["reference_answer"]
                            ).strip(),
                            "expected_type": "answerable",
                            "required_document_titles": [title],
                        }
                    ],
                }
            )
        except Exception as exc:
            print(f"[skip] single #{index}: {exc}")
    return cases


async def _generate_multi(
    corpus: list[tuple[str, list[str]]], count: int
) -> list[dict]:
    cases: list[dict] = []
    for index in range(count):
        title, chunks = corpus[index % len(corpus)]
        chunk = _pick_chunk(chunks, index + 1)
        try:
            data = await _ask(
                MULTI_PROMPT.format(title=title, content=chunk)
            )
            turns = []
            for turn in data.get("turns", [])[:2]:
                turns.append(
                    {
                        "question": str(turn["question"]).strip(),
                        "reference_answer": str(
                            turn["reference_answer"]
                        ).strip(),
                        "expected_type": "answerable",
                        "required_document_titles": [title],
                    }
                )
            if len(turns) != 2:
                raise ValueError("多轮用例轮次不足")
            cases.append(
                {
                    "type": "case",
                    "title": str(data.get("title") or f"多轮用例{index}")[:255],
                    "tags": ["multi_turn", "answerable"],
                    "turns": turns,
                }
            )
        except Exception as exc:
            print(f"[skip] multi #{index}: {exc}")
    return cases


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--single", type=int, default=30)
    parser.add_argument("--multi", type=int, default=10)
    parser.add_argument("--name", default="RAG 回归集 v1")
    parser.add_argument("--out", default="eval-drafts.jsonl")
    args = parser.parse_args()

    if llm_client.provider() == "mock":
        raise SystemExit(
            "需要配置 DEEPSEEK_API_KEY：草稿生成必须使用模型。"
        )

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    try:
        async with session_factory() as db:
            corpus = await _load_corpus(db)
        if not corpus:
            raise SystemExit("没有可用的已索引文档，先上传并等待索引完成。")
        print(f"语料：{len(corpus)} 个文档")

        single = await _generate_single(corpus, args.single)
        print(f"单轮草稿：{len(single)} 条")
        multi = await _generate_multi(corpus, args.multi)
        print(f"多轮草稿：{len(multi)} 条")

        lines = [
            json.dumps(
                {
                    "type": "dataset",
                    "name": args.name,
                    "description": "由 generate_eval_drafts 生成的草稿，需人工审核",
                },
                ensure_ascii=False,
            )
        ]
        for case in single + multi:
            lines.append(json.dumps(case, ensure_ascii=False))
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        print(f"已写入 {args.out}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
