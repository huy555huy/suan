"""问题分类 Agent — 决定激活哪些专家。"""
from __future__ import annotations
import re

from core.llm_client import chat_json
from agents.prompts import CLASSIFIER_SYSTEM


# 关键词 → expert 列表的本地启发式（兜底）
KEYWORD_RULES = [
    (r"性格|个性|我是?什么样|画像|认识自己", ["bazi", "ziwei", "astrology", "numerology"]),
    (r"今年|流年|这两年|未来.*年|明年|大运", ["bazi", "ziwei", "liunian", "astrology"]),
    (r"事业|工作|职场|跳槽|升职|换工作|创业", ["bazi", "ziwei", "liunian", "astrology"]),
    (r"财运|赚钱|投资|破财|发财|理财", ["bazi", "ziwei", "liunian", "astrology"]),
    (r"婚|配偶|伴侣|对象|相处|合婚|关系", ["bazi", "ziwei", "astrology", "tarot"]),
    (r"恋爱|分手|暧昧|表白|追求|桃花", ["bazi", "tarot", "astrology", "ziwei"]),
    (r"考试|考研|考公|学业|读书|毕业", ["bazi", "ziwei", "liunian", "tarot"]),
    (r"风水|方位|户型|搬家|装修|办公位|床头", ["fengshui"]),
    (r"该不该|要不要|可不可以|做不做|要不|启动|决定", ["yijing", "tarot", "liunian"]),
    (r"健康|身体|睡眠|焦虑|抑郁|状态", ["bazi", "ziwei", "astrology"]),
    (r"出国|留学|移民|搬迁|远行", ["bazi", "ziwei", "liunian", "astrology"]),
    (r"塔罗|抽牌|抽一张", ["tarot"]),
    (r"占星|星盘|本命盘|行运", ["astrology"]),
    (r"卦|起卦|算卦|周易", ["yijing"]),
    (r"数字命理|生命数", ["numerology"]),
]

DEFAULT_EXPERTS = ["bazi", "ziwei", "astrology", "numerology"]


def _keyword_route(question: str) -> tuple[list[str], str]:
    if not question.strip():
        return DEFAULT_EXPERTS, "空问题：默认综合画像（4 专家）"
    activated = set()
    matched_pats = []
    for pat, experts in KEYWORD_RULES:
        if re.search(pat, question):
            activated.update(experts)
            matched_pats.append(pat)
    if not activated:
        return DEFAULT_EXPERTS, "无关键词命中：默认综合画像（4 专家）"
    return list(activated), f"关键词命中：{', '.join(matched_pats)}"


async def classify_question(question: str, scenario: str = "chat") -> dict:
    """返回 {activated_experts, reasoning, primary_topic}。"""
    kw_experts, kw_reason = _keyword_route(question)

    # 深度报告默认激活全部 8 专家
    if scenario == "report":
        return {
            "activated_experts": ["bazi", "ziwei", "yijing", "fengshui", "liunian",
                                   "astrology", "tarot", "numerology"],
            "reasoning": "深度研报场景：激活全部 8 专家（中西交叉验证完整覆盖）",
            "primary_topic": "comprehensive",
        }

    # Copilot 场景按问题
    user = f"问题文本：{question or '（用户未提具体问题）'}\n场景：{scenario}\n\n请输出 JSON。"

    try:
        parsed, _, _ = await chat_json(
            [{"role": "system", "content": CLASSIFIER_SYSTEM},
             {"role": "user", "content": user}],
            temperature=0.2,
            max_tokens=400,
            tier="low",
        )
    except Exception:
        parsed = None

    if parsed and isinstance(parsed, dict) and parsed.get("activated_experts"):
        # 跟关键词路由的并集（保险）
        merged = list({*parsed["activated_experts"], *kw_experts})
        # 限制到 8 个内
        valid = ["bazi", "ziwei", "yijing", "fengshui", "liunian",
                 "astrology", "tarot", "numerology"]
        merged = [e for e in merged if e in valid][:8]
        return {
            "activated_experts": merged or DEFAULT_EXPERTS,
            "reasoning": parsed.get("reasoning", "") + " | " + kw_reason,
            "primary_topic": parsed.get("primary_topic", "general"),
        }

    return {
        "activated_experts": kw_experts,
        "reasoning": kw_reason + "（LLM classifier 失败，纯关键词兜底）",
        "primary_topic": "general",
    }
