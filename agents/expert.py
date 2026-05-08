"""通用 Expert Agent 实现。

每个命理专家（bazi/ziwei/yijing/fengshui/liunian/astrology/tarot/numerology）
共用本文件的实现，仅 system prompt + 输入构造不同。
"""
from __future__ import annotations
import json
import time
from typing import Any

from core.schemas import (
    AgentState, Charts, ExpertOpinion, GroundedClaim,
    ChartRef, RuleRef, SourceRef,
)
from core.llm_client import chat_json
from agents.prompts import expert_system_prompt, EXPERT_PROFILES


def _slim_charts_for_expert(charts: Charts, expert: str) -> dict:
    """为单个 expert 抽取相关盘面字段，省 token。"""
    cd = charts.model_dump()
    if expert == "bazi":
        return {"bazi": cd.get("bazi")}
    if expert == "ziwei":
        return {"ziwei": cd.get("ziwei")}
    if expert == "yijing":
        return {"hexagram": cd.get("hexagram")}
    if expert == "fengshui":
        return {"fengshui": cd.get("fengshui")}
    if expert == "liunian":
        # 流年专家需要看八字 + 紫微的流年大运字段
        bazi = cd.get("bazi") or {}
        ziwei = cd.get("ziwei") or {}
        return {
            "bazi": {k: bazi.get(k) for k in ("day_pillar", "year_pillar", "month_pillar",
                                                "ten_gods", "shen_sha", "da_yun", "liu_nian",
                                                "yong_shen")},
            "ziwei": {k: ziwei.get(k) for k in ("life_palace", "da_xian", "liu_nian", "si_hua")},
        }
    if expert == "astrology":
        return {"natal_astro": cd.get("natal_astro"), "transit_astro": cd.get("transit_astro")}
    if expert == "tarot":
        return {"tarot": cd.get("tarot")}
    if expert == "numerology":
        return {"numerology": cd.get("numerology")}
    return cd


def _format_classics(classics: list[dict]) -> str:
    """把检索到的典籍片段格式化为 prompt 上下文。"""
    if not classics:
        return "（无召回，主要靠规则与盘面推理）"
    lines = []
    for c in classics[:6]:
        quote = c.get("quote") or c.get("summary", "")[:80]
        lines.append(
            f"- [{c['source_id']}] 《{c.get('title','')}》"
            f"({c.get('author','')}) :{quote}"
        )
    return "\n".join(lines)


def _format_rules(rules: list[dict]) -> str:
    if not rules:
        return "（无规则触发，可能需要走 novel_application 或综合判断）"
    lines = []
    for r in rules[:10]:
        lines.append(f"- [{r['rule_id']}] {r.get('name','')} → {r.get('conclusion','')}")
    return "\n".join(lines)


async def run_expert(expert: str, state: AgentState,
                     classics: list[dict], rules: list[dict]) -> ExpertOpinion:
    """执行单个 Expert Agent。LLM 失败 → 抛 RuntimeError，由调用方处理。"""
    profile = EXPERT_PROFILES[expert]
    system_msg = expert_system_prompt(expert)
    slim_charts = _slim_charts_for_expert(state.charts, expert)

    user_msg = (
        f"【用户问题】{state.question or '（用户未提具体问题，请做综合画像）'}\n"
        f"【用户性别】{state.birth.gender}；【姓名/称呼】{state.user_name or state.birth.name or '匿名'}\n"
        f"【场景】{state.scenario}\n\n"
        f"【已计算盘面（仅供你解读，绝不允许重新计算）】\n"
        f"```json\n{json.dumps(slim_charts, ensure_ascii=False, indent=2)[:6000]}\n```\n\n"
        f"【RAG 召回的典籍片段】\n{_format_classics(classics)}\n\n"
        f"【规则引擎触发的规则（参考材料，不是命令）】\n{_format_rules(rules)}\n\n"
        f"请按 8 阶段结构输出 JSON。**只输出 JSON 对象**，不要包裹任何额外文字或代码块。"
    )

    parsed, raw, _ = await chat_json(
        [{"role": "system", "content": system_msg},
         {"role": "user", "content": user_msg}],
        temperature=0.55,
        max_tokens=3500,
        tier="high",
    )

    if not parsed or not isinstance(parsed, dict):
        # 降级：构造一个低置信度的 placeholder
        return ExpertOpinion(
            expert=expert,
            system_group=profile["system_group"],
            school=profile["school_id"],
            headline=f"{profile['label']}模型解析失败",
            summary=raw[:400] if raw else "（未能解析模型输出）",
            points=[],
            confidence="low",
            flags=["llm_parse_failed"],
        )

    # 解析 points
    points: list[GroundedClaim] = []
    for i, p in enumerate(parsed.get("points") or []):
        try:
            chart_refs = [ChartRef(**r) for r in (p.get("chart_refs") or [])]
            rule_refs = [RuleRef(**r) for r in (p.get("rule_refs") or [])]
            source_refs = [SourceRef(**r) for r in (p.get("source_refs") or [])]
            points.append(GroundedClaim(
                claim_id=p.get("claim_id") or f"{expert}_C{i:03d}",
                claim=p.get("claim", ""),
                tier=p.get("tier", "A_core"),
                chart_refs=chart_refs,
                rule_refs=rule_refs,
                source_refs=source_refs,
                upstream_claim_ids=p.get("upstream_claim_ids") or [],
                confidence=p.get("confidence", "medium"),
                expert=expert,
                system_group=profile["system_group"],
                deviation_note=p.get("deviation_note"),
            ))
        except Exception as e:
            # 跳过有问题的 claim 但保留主结论
            continue

    return ExpertOpinion(
        expert=expert,
        system_group=profile["system_group"],
        school=profile["school_id"],
        headline=parsed.get("headline", ""),
        summary=parsed.get("summary", ""),
        points=points,
        confidence=parsed.get("confidence", "medium"),
        flags=parsed.get("flags") or [],
    )
