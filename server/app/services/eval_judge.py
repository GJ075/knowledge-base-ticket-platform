import json
import logging

from app.services import llm_client

logger = logging.getLogger("app")

REFUSAL_MARKERS = (
    "无法回答",
    "无法确定",
    "没有找到",
    "未找到",
    "知识库中没有",
    "资料中没有",
    "未提供相关信息",
    "无法获取",
    "不清楚",
    "我不知道",
)

JUDGE_PROMPT = """你是企业知识库问答的评分员。请根据给定信息评价“模型回答”。

评分标准（1–5 分）：
- 5 分：与参考答案完全一致或语义等价，关键信息齐全。
- 4 分：核心信息正确，缺少次要细节，但可直接使用。
- 3 分：部分正确，存在遗漏或不够精确。
- 2 分：大部分不正确，仅有少量相关信息。
- 1 分：错误回答或拒答。

当期望类型为 unanswerable 时：模型明确拒答给 5 分；编造答案给 1 分。

只输出 JSON，不要输出解释或代码块：
{"score": 1-5 的整数, "passed": true/false, "refused": true/false, "reason": "不超过 100 字的中文理由"}

其中 passed 为 score >= 4；refused 表示模型是否表示无法回答。
"""

REWRITE_PROMPT = """请把用户的最新问题改写成一句可以独立检索的中文问题。

要求：
- 只输出改写后的问题本身，不要回答问题，不要解释。
- 结合历史对话补全指代（它、这个、那个等）。
- 不要添加知识库没有的信息。
- 如果无法改写，原样输出最新问题。
"""


def is_refusal(answer: str) -> bool:
    text = (answer or "").strip()
    if not text:
        return True
    return any(marker in text for marker in REFUSAL_MARKERS)


def _history_lines(history: list[dict], limit: int = 3) -> str:
    if not history:
        return "无"
    recent = history[-limit * 2 :]
    lines = []
    for message in recent:
        role = "用户" if message.get("role") == "user" else "助手"
        lines.append(f"{role}：{message.get('content', '')[:500]}")
    return "\n".join(lines)


def _parse_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("评分结果不是 JSON")
    return json.loads(cleaned[start : end + 1])


def _mock_judge(
    answer: str, reference: str | None, expected_type: str
) -> dict:
    refused = is_refusal(answer)
    if expected_type == "unanswerable":
        score = 5 if refused else 1
        return {
            "score": score,
            "passed": score >= 4,
            "refused": refused,
            "reason": "本地模拟评分：未配置 DeepSeek API Key",
        }
    if refused:
        return {
            "score": 1,
            "passed": False,
            "refused": True,
            "reason": "回答拒答或为空",
        }
    matched = bool(reference) and reference.strip()[:20] in answer
    score = 4 if matched else 3
    return {
        "score": score,
        "passed": score >= 4,
        "refused": False,
        "reason": "本地模拟评分：未配置 DeepSeek API Key",
    }


async def judge_turn(
    question: str,
    reference: str | None,
    answer: str,
    expected_type: str,
    history: list[dict],
) -> dict:
    if llm_client.provider() == "mock":
        return _mock_judge(answer, reference, expected_type)

    payload = {
        "当前问题": question,
        "期望类型": expected_type,
        "参考答案": reference or "（无）",
        "模型回答": answer,
        "最近对话": _history_lines(history),
    }
    messages = [
        {"role": "system", "content": JUDGE_PROMPT},
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False),
        },
    ]
    last_error: Exception | None = None
    for _ in range(3):
        try:
            text = await llm_client.complete_deepseek(
                messages, temperature=0.0, max_tokens=300
            )
            data = _parse_json(text)
            score = int(data.get("score", 0))
            if not 1 <= score <= 5:
                raise ValueError("评分不在 1–5 范围")
            return {
                "score": score,
                "passed": score >= 4,
                "refused": bool(data.get("refused", False)),
                "reason": str(data.get("reason") or "")[:300],
            }
        except Exception as exc:
            last_error = exc
            logger.warning("eval judge failed: %s", exc)
    raise ValueError(f"评分失败：{last_error}")


async def rewrite_question(
    history: list[dict], question: str
) -> str | None:
    if not history:
        return None
    if llm_client.provider() == "mock":
        return None
    messages = [
        {"role": "system", "content": REWRITE_PROMPT},
        {
            "role": "user",
            "content": (
                f"历史对话：\n{_history_lines(history)}\n\n"
                f"最新问题：{question}"
            ),
        },
    ]
    for _ in range(2):
        try:
            text = await llm_client.complete_deepseek(
                messages, temperature=0.0, max_tokens=100
            )
            rewritten = text.strip().strip("。")
            if rewritten and len(rewritten) <= 500:
                return rewritten
        except Exception as exc:
            logger.warning("eval rewrite failed: %s", exc)
    return None
