"""中西交叉验证 Aligner Agent — 产品级核心节点（设计文档第 2C 章）。

输入：CN_Synth + WT_Synth
输出：CrossSystemAlignment（按 topic 对齐，标注 consensus / divergence / complementary / incomparable）
"""
from __future__ import annotations
import json

from core.schemas import (
    SystemSummary, CrossSystemAlignment, TopicAlignment, ConflictItem,
)
from core.llm_client import chat_json
from agents.prompts import ALIGNER_SYSTEM


async def run_aligner(cn: SystemSummary, wt: SystemSummary) -> CrossSystemAlignment:
    """跑中西交叉验证。LLM 失败抛错。"""
    if (cn is None or cn.is_skipped) and (wt is None or wt.is_skipped):
        return CrossSystemAlignment(overall_summary="双方均为空，无交叉验证可做。")
    if cn is None or cn.is_skipped:
        return CrossSystemAlignment(
            overall_summary=f"本次仅西式体系参与（{wt.headline}），未做交叉验证。"
        )
    if wt is None or wt.is_skipped:
        return CrossSystemAlignment(
            overall_summary=f"本次仅中式体系参与（{cn.headline}），未做交叉验证。"
        )

    user = (
        f"【中式综合】\n标题: {cn.headline}\n"
        f"by_topic: {json.dumps({k: v.model_dump() for k, v in cn.by_topic.items()}, ensure_ascii=False)[:3500]}\n\n"
        f"【西式综合】\n标题: {wt.headline}\n"
        f"by_topic: {json.dumps({k: v.model_dump() for k, v in wt.by_topic.items()}, ensure_ascii=False)[:3500]}\n\n"
        f"请按要求输出 CrossSystemAlignment 的 JSON，**只输出 JSON 对象**。"
    )

    parsed, raw, _ = await chat_json(
        [{"role": "system", "content": ALIGNER_SYSTEM},
         {"role": "user", "content": user}],
        temperature=0.45,
        max_tokens=3500,
        tier="high",
    )
    if not parsed or not isinstance(parsed, dict):
        raise RuntimeError(f"中西交叉对齐解析失败：{raw[:200]}")

    by_topic: dict[str, TopicAlignment] = {}
    for topic, payload in (parsed.get("by_topic") or {}).items():
        if not isinstance(payload, dict):
            continue
        divergences: list[ConflictItem] = []
        for d in payload.get("divergence_points") or []:
            if isinstance(d, dict):
                try:
                    divergences.append(ConflictItem(
                        topic=d.get("topic", topic),
                        side_a=d.get("side_a") or {},
                        side_b=d.get("side_b") or {},
                        arbitration=d.get("arbitration", ""),
                    ))
                except Exception:
                    continue
        try:
            by_topic[topic] = TopicAlignment(
                topic=topic,
                chinese_view=payload.get("chinese_view"),
                western_view=payload.get("western_view"),
                alignment_type=payload.get("alignment_type", "incomparable"),
                consensus_points=payload.get("consensus_points") or [],
                divergence_points=divergences,
                complementary_points=payload.get("complementary_points") or [],
                final_synthesis=payload.get("final_synthesis", ""),
                confidence_uplift=float(payload.get("confidence_uplift") or 0.0),
            )
        except Exception:
            continue

    return CrossSystemAlignment(
        by_topic=by_topic,
        overall_consensus_score=float(parsed.get("overall_consensus_score") or 0.0),
        overall_divergence_score=float(parsed.get("overall_divergence_score") or 0.0),
        overall_summary=parsed.get("overall_summary", ""),
    )
