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


ALIGNER_BATCH_SIZE = 4
VIEW_LIMIT = 120
POINT_LIMIT = 48
SYNTHESIS_LIMIT = 160


def _compact_topic(payload) -> dict:
    return {
        "tendency": payload.tendency,
        "timing": payload.timing,
        "summary": payload.summary,
        "risks": payload.risks[:2],
        "opportunities": payload.opportunities[:2],
    }


def _topic_batches(topics: list[str], size: int = ALIGNER_BATCH_SIZE):
    for i in range(0, len(topics), size):
        yield topics[i:i + size]


def _clip_text(value, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[:limit - 1].rstrip() + "…"


def _clip_list(values, limit: int, max_items: int = 2) -> list[str]:
    return [
        clipped for clipped in (_clip_text(v, limit) for v in (values or [])[:max_items])
        if clipped
    ]


async def run_aligner(cn: SystemSummary, wt: SystemSummary) -> CrossSystemAlignment:
    """跑中西交叉验证。结构化输出失败仍抛错，避免产生假对齐结果。"""
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

    by_topic: dict[str, TopicAlignment] = {}
    scores: list[tuple[float, float]] = []
    summaries: list[str] = []
    topics = sorted(set(cn.by_topic) | set(wt.by_topic))

    for batch in _topic_batches(topics):
        cn_topics = {
            k: _compact_topic(cn.by_topic[k])
            for k in batch if k in cn.by_topic
        }
        wt_topics = {
            k: _compact_topic(wt.by_topic[k])
            for k in batch if k in wt.by_topic
        }
        user = (
            f"【本批 topic】{', '.join(batch)}\n\n"
            f"【中式综合】\n标题: {cn.headline}\n"
            f"by_topic: {json.dumps(cn_topics, ensure_ascii=False)}\n\n"
            f"【西式综合】\n标题: {wt.headline}\n"
            f"by_topic: {json.dumps(wt_topics, ensure_ascii=False)}\n\n"
            f"请只对本批 topic 输出 CrossSystemAlignment JSON，by_topic 只包含本批 topic。"
        )

        parsed, raw, usage = await chat_json(
            [{"role": "system", "content": ALIGNER_SYSTEM},
             {"role": "user", "content": user}],
            temperature=0.2,
            max_tokens=1800,
            tier="high",
        )
        if not parsed or not isinstance(parsed, dict):
            raise RuntimeError(
                "中西交叉对齐解析失败："
                f"topics={batch}, finish_reason={usage.finish_reason or 'unknown'}, "
                f"raw={raw[:200]}"
            )

        for topic, payload in (parsed.get("by_topic") or {}).items():
            if topic not in batch:
                continue
            aligned = _parse_topic_alignment(topic, payload)
            if aligned:
                by_topic[topic] = aligned
        scores.append((
            float(parsed.get("overall_consensus_score") or 0.0),
            float(parsed.get("overall_divergence_score") or 0.0),
        ))
        summary = parsed.get("overall_summary")
        if isinstance(summary, str) and summary:
            summaries.append(summary)

    consensus_score = sum(s[0] for s in scores) / len(scores) if scores else 0.0
    divergence_score = sum(s[1] for s in scores) / len(scores) if scores else 0.0
    overall_summary = "；".join(summaries[:4])
    if len(summaries) > 4:
        overall_summary += "。其余 topic 多为单方覆盖或弱互补。"

    return CrossSystemAlignment(
        by_topic=by_topic,
        overall_consensus_score=consensus_score,
        overall_divergence_score=divergence_score,
        overall_summary=overall_summary,
    )


def _parse_topic_alignment(topic: str, payload) -> TopicAlignment | None:
    if not isinstance(payload, dict):
        return None
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
        return TopicAlignment(
            topic=topic,
            chinese_view=_clip_text(payload.get("chinese_view"), VIEW_LIMIT),
            western_view=_clip_text(payload.get("western_view"), VIEW_LIMIT),
            alignment_type=payload.get("alignment_type", "incomparable"),
            consensus_points=_clip_list(payload.get("consensus_points"), POINT_LIMIT),
            divergence_points=divergences,
            complementary_points=_clip_list(payload.get("complementary_points"), POINT_LIMIT),
            final_synthesis=_clip_text(payload.get("final_synthesis"), SYNTHESIS_LIMIT) or "",
            confidence_uplift=float(payload.get("confidence_uplift") or 0.0),
        )
    except Exception:
        return None
