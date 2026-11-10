"""Import the RGB benchmark (zh split) into the evaluation system.

RGB (Chen et al., arXiv:2309.01431) is distributed under CC BY-NC-SA 4.0:
non-commercial use only.

Steps:
1. upload every positive passage (and a sample of negative passages) as a
   knowledge-base document, one passage per document;
2. wait until all documents are indexed;
3. emit an evaluation JSONL and import it through /eval/import.

Usage (from the project root):
    python tools/import_public_dataset.py --limit 10 --noise 8

Dry run (no HTTP calls, only parsing and JSONL preview):
    python tools/import_public_dataset.py --limit 10 --dry-run
"""

import argparse
import hashlib
import json
import random
import sys
import time
from pathlib import Path

import httpx

BASE = Path(__file__).resolve().parent
TITLE_LIMIT = 2000


def passage_text(item) -> str:
    if isinstance(item, str):
        return item
    for key in ("text", "contents", "passage", "content"):
        if item.get(key):
            return item[key]
    return ""


def title_of(text: str) -> str:
    return "RGB-" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def load_items(
    path: Path,
    limit: int,
    offset: int = 0,
    shuffle: bool = False,
    seed: int = 42,
) -> list[dict]:
    rows: list[dict] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            rows.append(json.loads(line))
    if shuffle:
        random.Random(seed).shuffle(rows)
    rows = rows[offset : offset + limit]

    items: list[dict] = []
    for row in rows:
        question = row.get("query") or row.get("question")
        if not question:
            continue
        answer = row.get("answer")
        if isinstance(answer, list):
            answer = "；".join(str(part) for part in answer)
        positives = [
            passage_text(part) for part in (row.get("positive") or [])
        ]
        negatives = [
            passage_text(part) for part in (row.get("negative") or [])
        ]
        items.append(
            {
                "question": question,
                "answer": answer or "",
                "positives": list(
                    dict.fromkeys(p for p in positives if p.strip())
                ),
                "negatives": [p for p in negatives if p.strip()],
            }
        )
    return items


def planned_documents(
    items: list[dict], noise: int
) -> tuple[list[str], list[str]]:
    positives: list[str] = []
    negatives: list[str] = []
    seen: set[str] = set()
    for item in items:
        for text in item["positives"]:
            if len(text) > TITLE_LIMIT:
                continue
            title = title_of(text)
            if title not in seen:
                seen.add(title)
                positives.append(text)
        for text in item["negatives"][:noise]:
            if len(text) > TITLE_LIMIT:
                continue
            title = title_of(text)
            if title not in seen:
                seen.add(title)
                negatives.append(text)
    return positives, negatives


def upload_text(client: httpx.Client, text: str) -> str:
    title = title_of(text)
    found = client.get("/documents", params={"keyword": title}).json()["items"]
    if any(doc["title"] == title for doc in found):
        return title
    files = {"file": (f"{title}.txt", text.encode("utf-8"), "text/plain")}
    client.post(
        "/documents", files=files, data={"title": title}
    ).raise_for_status()
    return title


def wait_ready(
    client: httpx.Client, titles: set[str], timeout: int = 3600
) -> tuple[set[str], dict[str, str]]:
    ready: set[str] = set()
    failed: dict[str, str] = {}
    started = time.monotonic()
    while True:
        pending = titles - ready - set(failed)
        if not pending:
            break
        if time.monotonic() - started > timeout:
            raise SystemExit("等待索引超时，请检查 worker 日志")
        for title in list(pending):
            docs = client.get(
                "/documents", params={"keyword": title}
            ).json()["items"]
            same = [doc for doc in docs if doc["title"] == title]
            if not same:
                failed[title] = "not found"
                continue
            status = same[0]["index_status"]
            if status == "ready":
                ready.add(title)
            elif status == "failed":
                failed[title] = "index failed"
        print(
            f"  索引进度：ready={len(ready)} "
            f"pending={len(titles) - len(ready) - len(failed)} "
            f"failed={len(failed)}"
        )
        if titles - ready - set(failed):
            time.sleep(10)
    return ready, failed


def build_jsonl(
    items: list[dict],
    ready: set[str],
    dataset_name: str,
) -> tuple[str, int]:
    lines = [
        json.dumps(
            {
                "type": "dataset",
                "name": dataset_name,
                "description": "RGB 中文子集（CC BY-NC-SA 4.0，非商业用途）",
            },
            ensure_ascii=False,
        )
    ]
    imported = 0
    skipped = 0
    for index, item in enumerate(items, start=1):
        titles = [title_of(text) for text in item["positives"]]
        missing = [title for title in titles if title not in ready]
        if not item["answer"] or missing or not titles:
            skipped += 1
            print(
                f"  跳过第 {index} 题："
                f"{'缺少必引文档' if missing else '缺少参考答案'}"
            )
            continue
        lines.append(
            json.dumps(
                {
                    "type": "case",
                    "title": f"RGB-{index}",
                    "tags": ["rgb", "single_turn"],
                    "turns": [
                        {
                            "question": item["question"],
                            "reference_answer": item["answer"],
                            "expected_type": "answerable",
                            "required_document_titles": titles,
                        }
                    ],
                },
                ensure_ascii=False,
            )
        )
        imported += 1
    return "\n".join(lines) + "\n", skipped


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(BASE / "data" / "zh.json"))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--offset", type=int, default=0, help="跳过前 N 条样本"
    )
    parser.add_argument(
        "--shuffle", action="store_true", help="随机抽样而不是取前 N 条"
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--noise", type=int, default=8, help="每题上传的干扰段落数"
    )
    parser.add_argument("--dataset-name", default="")
    parser.add_argument("--api", default="http://localhost:8000/api/v1")
    parser.add_argument("--username", default="leader")
    parser.add_argument("--password", default="Leader@123")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = BASE / input_path
    if not input_path.exists():
        raise SystemExit(f"找不到数据文件：{input_path}")

    items = load_items(
        input_path,
        args.limit,
        args.offset,
        args.shuffle,
        args.seed,
    )
    if not items:
        raise SystemExit("没有解析到样本")
    positives, negatives = planned_documents(items, args.noise)
    ready_titles = {title_of(text) for text in positives + negatives}

    dataset_name = args.dataset_name or (
        f"RGB-zh-{len(items)}-{'s' + str(args.seed) if args.shuffle else 'o' + str(args.offset)}"
    )
    print(
        f"样本 {len(items)} 条；正例文档 {len(positives)} 篇，"
        f"噪声文档 {len(negatives)} 篇，合计 {len(ready_titles)} 篇"
    )

    if args.dry_run:
        content, skipped = build_jsonl(
            items, ready_titles, dataset_name
        )
        print(f"dry-run：将导入 {len(items) - skipped} 条用例")
        print(content.splitlines()[0])
        print(content.splitlines()[1][:300])
        return

    with httpx.Client(base_url=args.api, timeout=120) as client:
        client.post(
            "/auth/login",
            json={"username": args.username, "password": args.password},
        ).raise_for_status()

        uploaded = 0
        for text in positives + negatives:
            upload_text(client, text)
            uploaded += 1
            if uploaded % 20 == 0:
                print(f"  已提交 {uploaded}/{len(ready_titles)} 篇")
        print(f"上传完成：{uploaded} 篇")

        ready, failed = wait_ready(client, ready_titles)
        if failed:
            print(f"索引失败 {len(failed)} 篇（不会作为必引文档）：")
            for title, reason in list(failed.items())[:10]:
                print(f"  {title}: {reason}")

        content, skipped = build_jsonl(items, ready, dataset_name)
        output = BASE / "data" / f"rgb-zh-{len(items)}.jsonl"
        output.write_text(content, encoding="utf-8")
        print(f"JSONL 已写入 {output}")

        if skipped == len(items):
            raise SystemExit("没有可导入的用例，检查文档索引状态")

        response = client.post(
            "/eval/import",
            files={
                "file": (
                    output.name,
                    content.encode("utf-8"),
                    "application/jsonl",
                )
            },
        )
        if response.status_code >= 400:
            print(response.status_code, response.text)
            sys.exit(1)
        print("导入结果：", response.json())


if __name__ == "__main__":
    main()
