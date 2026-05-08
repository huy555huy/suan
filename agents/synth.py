"""组内小综合 Agent（CN_Synth / WT_Synth）。

把同组所有 Expert 的 opinions 合并为该体系的 SystemSummary，按 26 个标准 topic 归一化。
注意：CN_Synth 与 WT_Synth 互不可见对方结论，保证两套体系真正独立推理。
"""
from __future__ import annotations
import json

from core.schemas import (
    AgentState, ExpertOpinion, SystemSummary, TopicConclusion,
)
from core.llm_client import chat_json
from agents.prompts import SYNTH_SYSTEM


GROUP_LABELS = {"chinese": "中式", "western": "西式"}


async def run_synth(group: str, opinions: list[ExpertOpinion]) -> SystemSummary:
    """对单组的多专家 opinions 做小综合。"""
    if not opinions:
        return SystemSummary(
            system_group=group,  # type: ignore
            is_skipped=True,
            skip_reason="no_active_expert_in_group",
            confidence="low",
            headline=f"{GROUP_LABELS.get(group, group)}组本次无激活专家",
        )

    # 用 .replace 而不是 .format 避免被 JSON 示例中的 { 干扰
    sys_msg = (SYNTH_SYSTEM
               .replace("{{group_label}}", GROUP_LABELS.get(group, group))
               .replace("{{group_id}}", group))

    expert_section = "\n\n".join(
        f"### {op.expert} ({op.school}, confidence={op.confidence})\n"
        f"主结论：{op.headline}\n"
        f"摘要：{op.summary}\n"
        f"主要 claims：\n" +
        "\n".join(f"- [{c.claim_id}] {c.claim} ({c.confidence})"
                  for c in op.points[:6])
        for op in opinions
    )

    user = (
        f"以下是 {GROUP_LABELS.get(group, group)} 组所有专家的输出：\n\n"
        f"{expert_section}\n\n"
        f"请按标准 26 个 topic 归一化输出，**只输出 JSON 对象**。"
    )

    parsed, raw, _ = await chat_json(
        [{"role": "system", "content": sys_msg},
         {"role": "user", "content": user}],
        temperature=0.4,
        max_tokens=3000,
        tier="high",
    )

    if not parsed or not isinstance(parsed, dict):
        raise RuntimeError(f"{GROUP_LABELS.get(group, group)}综合解析失败：{raw[:200]}")

    by_topic: dict[str, TopicConclusion] = {}
    raw_topics = parsed.get("by_topic") or {}
    for topic, payload in raw_topics.items():
        if not isinstance(payload, dict):
            continue
        try:
            by_topic[topic] = TopicConclusion(
                topic=topic,
                tendency=payload.get("tendency", "neutral"),
                timing=payload.get("timing"),
                summary=payload.get("summary", ""),
                risks=payload.get("risks") or [],
                opportunities=payload.get("opportunities") or [],
                supporting_claim_ids=payload.get("supporting_claim_ids") or [],
            )
        except Exception:
            continue

    return SystemSummary(
        system_group=group,  # type: ignore
        by_topic=by_topic,
        confidence=parsed.get("confidence", "medium"),
        headline=parsed.get("headline", ""),
    )
