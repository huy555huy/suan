"""最终综合判官 Agent。"""
from __future__ import annotations
import json

from core.schemas import (
    AgentState, JudgeVerdict, ConflictItem, CrossSystemAlignment,
)
from core.llm_client import chat_json
from agents.prompts import JUDGE_SYSTEM


async def run_judge(state: AgentState) -> JudgeVerdict:
    parts = []
    if state.cn_synth and not state.cn_synth.is_skipped:
        parts.append(f"【中式综合】{state.cn_synth.headline}\n"
                     f"{json.dumps({k:v.model_dump() for k,v in state.cn_synth.by_topic.items()}, ensure_ascii=False)[:2500]}")
    if state.wt_synth and not state.wt_synth.is_skipped:
        parts.append(f"【西式综合】{state.wt_synth.headline}\n"
                     f"{json.dumps({k:v.model_dump() for k,v in state.wt_synth.by_topic.items()}, ensure_ascii=False)[:2500]}")
    if state.cross_alignment:
        parts.append(f"【交叉验证】{state.cross_alignment.overall_summary}\n"
                     f"by_topic: {json.dumps({k:v.model_dump() for k,v in state.cross_alignment.by_topic.items()}, ensure_ascii=False)[:2500]}")

    expert_briefs = "\n".join(
        f"- {op.expert}({op.confidence}): {op.headline}"
        for op in state.expert_opinions
    )

    user = (
        f"【用户问题】{state.question or '综合画像'}\n"
        f"【场景】{state.scenario}\n\n"
        f"【专家概览】\n{expert_briefs}\n\n"
        + "\n\n".join(parts) +
        "\n\n请输出 JudgeVerdict 的 JSON，**只输出 JSON 对象**。"
    )

    parsed, raw, _ = await chat_json(
        [{"role": "system", "content": JUDGE_SYSTEM},
         {"role": "user", "content": user}],
        temperature=0.4,
        max_tokens=2500,
        tier="high",
    )
    if not parsed or not isinstance(parsed, dict):
        raise RuntimeError(f"综合判官解析失败：{raw[:200]}")

    conflicts: list[ConflictItem] = []
    for c in parsed.get("conflicts") or []:
        if isinstance(c, dict):
            try:
                conflicts.append(ConflictItem(
                    topic=c.get("topic", ""),
                    side_a=c.get("side_a") or {},
                    side_b=c.get("side_b") or {},
                    arbitration=c.get("arbitration", ""),
                ))
            except Exception:
                continue

    return JudgeVerdict(
        consensus=parsed.get("consensus") or [],
        conflicts=conflicts,
        weighted_summary=parsed.get("weighted_summary", ""),
        overall_confidence=parsed.get("overall_confidence", "medium"),
        cross_alignment=state.cross_alignment,
        actionable_advice=parsed.get("actionable_advice") or [],
        cautions=parsed.get("cautions") or [],
    )
