"""主编排（Orchestrator）— 串起整个流程。

模式：
- 默认走"固定流水线"（fanout-then-barrier）—— 稳定、可观测、cost 可控
- 启用 ENABLE_PLANNER 时切到 Planner-Executor 旗舰模式
- 全程发出事件（async generator），由 API 层映射成 SSE
"""
from __future__ import annotations
import asyncio
import json
import time
import uuid
from datetime import datetime
from typing import AsyncIterator

from core.schemas import (
    AgentState, BirthInfo, Charts, ExpertOpinion,
    SystemSummary, CrossSystemAlignment, JudgeVerdict, ReasoningTrace, TraceStep,
)
from core.config import settings
from agents.expert import run_expert
from agents.synth import run_synth
from agents.aligner import run_aligner
from agents.judge import run_judge
from agents.narrative import run_narrative
from agents.safety import apply_safety
from agents.verifier import verify_opinion
from agents.classifier import classify_question
from agents.compute_dispatch import dispatch_compute
from knowledge.retrieval import retrieve_classics
from knowledge.rule_engine import find_matching_rules


CN_EXPERTS = {"bazi", "ziwei", "yijing", "fengshui", "liunian"}
WT_EXPERTS = {"astrology", "tarot", "numerology"}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _new_trace(session_id: str) -> ReasoningTrace:
    return ReasoningTrace(
        trace_id=f"tr_{uuid.uuid4().hex[:12]}",
        session_id=session_id,
        started_at=datetime.utcnow().isoformat(),
        steps=[],
    )


def _add_step(trace: ReasoningTrace, agent: str, action: str, payload: dict | None = None):
    trace.steps.append(TraceStep(
        step_id=len(trace.steps) + 1,
        agent=agent,
        action=action,
        payload=payload or {},
    ))


def _new_state(session_id: str, birth: BirthInfo, question: str, scenario: str,
               user_name: str | None) -> AgentState:
    return AgentState(
        session_id=session_id,
        user_name=user_name,
        birth=birth,
        question=question,
        scenario=scenario,  # type: ignore
        trace=_new_trace(session_id),
    )


async def event(kind: str, **payload) -> dict:
    """构造一条事件 dict，用于 yield 给上层。"""
    return {"type": kind, "ts": _now_ms(), **payload}


# ── 主流程 ────────────────────────────────────────────────────
async def run_pipeline(state: AgentState, *, stream: bool = True) -> AsyncIterator[dict]:
    """跑完整流程，作为 async generator yield 事件。"""
    yield await event("start", session_id=state.session_id, scenario=state.scenario)

    # 1) Classifier 决定激活哪些专家
    yield await event("phase", phase="classifier", message="正在分析问题，决定激活的专家组合…")
    cls_result = await classify_question(state.question, state.scenario)
    state.activated_experts = cls_result["activated_experts"]
    state.routing_reason = cls_result["reasoning"]
    _add_step(state.trace, "classifier", "decide", cls_result)
    yield await event("classifier_done",
                      activated=state.activated_experts,
                      reason=state.routing_reason,
                      primary_topic=cls_result.get("primary_topic"))

    # 2) Calculator: 触发所有需要的盘面计算
    yield await event("phase", phase="calculator", message="正在排盘…")
    needed_charts = set()
    for exp in state.activated_experts:
        needed_charts.update(_charts_needed_for_expert(exp))
    # 默认始终算 bazi 和 numerology 作为基础画像
    needed_charts.update({"bazi", "numerology"})
    if any(e in WT_EXPERTS for e in state.activated_experts):
        needed_charts.add("natal_astro")

    for chart_type in needed_charts:
        try:
            await dispatch_compute(chart_type, state)
            _add_step(state.trace, "calculator", f"compute:{chart_type}")
            yield await event("chart_ready", chart_type=chart_type)
        except Exception as e:
            state.errors.append(f"compute_{chart_type}_failed: {e}")
            yield await event("chart_failed", chart_type=chart_type, error=str(e))

    yield await event("charts_summary", charts=_charts_summary(state.charts))

    # 3) Expert Agents — 并行
    yield await event("phase", phase="experts",
                      message=f"启动 {len(state.activated_experts)} 个专家并行推理…")

    # 为每个 expert 准备 RAG + Rule
    expert_tasks = []
    for exp in state.activated_experts:
        expert_tasks.append(_run_one_expert(exp, state))

    # 用 as_completed 模式逐个上报
    done_count = 0
    for fut in asyncio.as_completed(expert_tasks):
        opinion: ExpertOpinion = await fut
        state.expert_opinions.append(opinion)
        _add_step(state.trace, opinion.expert, "expert_done",
                  {"headline": opinion.headline, "confidence": opinion.confidence,
                   "n_points": len(opinion.points)})
        done_count += 1
        yield await event("expert_done",
                          expert=opinion.expert,
                          system_group=opinion.system_group,
                          school=opinion.school,
                          headline=opinion.headline,
                          summary=opinion.summary,
                          n_points=len(opinion.points),
                          confidence=opinion.confidence,
                          progress=f"{done_count}/{len(state.activated_experts)}")

    # 4) Verifier — 反思镜（不阻断；Tier A 启用 LLM 语义校验）
    yield await event("phase", phase="verifier", message="VRP 校验中（反思镜：Tier A 启用语义校验）…")
    for op in state.expert_opinions:
        stats = await verify_opinion(op, state.charts, use_llm=True)
        _add_step(state.trace, "verifier", "check", {"expert": op.expert, "stats": stats})
        yield await event("verifier_log",
                          expert=op.expert,
                          stats=_stats_brief(stats))

    # 5) CN_Synth + WT_Synth — 并行
    yield await event("phase", phase="synth", message="组内综合（中式 ✕ 西式 各自独立）…")
    cn_ops = [op for op in state.expert_opinions if op.system_group == "chinese"]
    wt_ops = [op for op in state.expert_opinions if op.system_group == "western"]

    cn_task = run_synth("chinese", cn_ops) if cn_ops else _make_skipped("chinese")
    wt_task = run_synth("western", wt_ops) if wt_ops else _make_skipped("western")
    cn_synth, wt_synth = await asyncio.gather(cn_task, wt_task)
    state.cn_synth = cn_synth
    state.wt_synth = wt_synth
    _add_step(state.trace, "cn_synth", "done", {"headline": cn_synth.headline})
    _add_step(state.trace, "wt_synth", "done", {"headline": wt_synth.headline})
    yield await event("synth_done", group="chinese", headline=cn_synth.headline,
                      n_topics=len(cn_synth.by_topic), is_skipped=cn_synth.is_skipped)
    yield await event("synth_done", group="western", headline=wt_synth.headline,
                      n_topics=len(wt_synth.by_topic), is_skipped=wt_synth.is_skipped)

    # 6) Cross Aligner — 中西交叉验证
    cn_alive = cn_synth and not cn_synth.is_skipped
    wt_alive = wt_synth and not wt_synth.is_skipped
    if cn_alive and wt_alive:
        yield await event("phase", phase="aligner",
                          message="中西交叉验证（产品级核心节点）…")
        alignment = await run_aligner(cn_synth, wt_synth)
        state.cross_alignment = alignment
        _add_step(state.trace, "aligner", "done",
                  {"consensus": alignment.overall_consensus_score,
                   "divergence": alignment.overall_divergence_score})
        yield await event("aligner_done",
                          consensus_score=alignment.overall_consensus_score,
                          divergence_score=alignment.overall_divergence_score,
                          n_topics=len(alignment.by_topic),
                          summary=alignment.overall_summary,
                          by_topic={k: v.model_dump() for k, v in list(alignment.by_topic.items())[:6]})
    else:
        yield await event("aligner_skipped",
                          reason="单体系路径（无需交叉验证）")

    # 7) Synthesis Judge — 最终判官
    yield await event("phase", phase="judge", message="最终判官裁决中…")
    verdict = await run_judge(state)
    state.verdict = verdict
    _add_step(state.trace, "judge", "done",
              {"confidence": verdict.overall_confidence,
               "n_consensus": len(verdict.consensus),
               "n_conflicts": len(verdict.conflicts)})
    yield await event("verdict_done",
                      confidence=verdict.overall_confidence,
                      consensus=verdict.consensus,
                      conflicts=[c.model_dump() for c in verdict.conflicts],
                      summary=verdict.weighted_summary,
                      advice=verdict.actionable_advice,
                      cautions=verdict.cautions)

    # 8) Narrative — 流式生成最终文本（stream_narrative）
    yield await event("phase", phase="narrative", message="撰写最终回应…")

    from agents.narrative import stream_narrative as _stream_narr

    text = ""
    async for chunk in _stream_narr(state):
        if not chunk:
            continue
        text += chunk
        yield await event("narrative_chunk", text=chunk)

    # 9) Safety — 红线 / 心理风险审查（在完整文本上做）
    safe_text, triggers = apply_safety(text)
    state.narrative = safe_text
    state.safety_passed = "crisis" not in triggers
    state.safety_notes = triggers
    _add_step(state.trace, "safety", "done", {"triggers": triggers})

    # 如果 safety 改了文本（红线词替换），用 narrative 事件覆盖最终版
    if safe_text != text:
        yield await event("narrative", text=safe_text, safety_triggers=triggers, replaced=True)
    else:
        # 没有改动就只发一次完整 text 作收尾（前端可在没收到 chunk 时兜底）
        yield await event("narrative", text=safe_text, safety_triggers=triggers, replaced=False)

    yield await event("done",
                      session_id=state.session_id,
                      trace_id=state.trace.trace_id if state.trace else None,
                      n_experts=len(state.expert_opinions),
                      cost_usd=state.cost_usd,
                      narrative_len=len(safe_text))


# ── 辅助 ─────────────────────────────────────────────────────
def _charts_needed_for_expert(expert: str) -> set[str]:
    return {
        "bazi": {"bazi"},
        "ziwei": {"ziwei"},
        "yijing": {"hexagram"},
        "fengshui": {"fengshui"},
        "liunian": {"bazi", "ziwei"},
        "astrology": {"natal_astro", "transit_astro"},
        "tarot": {"tarot"},
        "numerology": {"numerology"},
    }.get(expert, set())


def _charts_summary(charts: Charts) -> dict:
    """供 UI 显示的盘面摘要。"""
    summary = {}
    if charts.bazi:
        bz = charts.bazi
        summary["bazi"] = {
            "year": f"{bz.year_pillar['stem']}{bz.year_pillar['branch']}",
            "month": f"{bz.month_pillar['stem']}{bz.month_pillar['branch']}",
            "day": f"{bz.day_pillar['stem']}{bz.day_pillar['branch']}",
            "hour": f"{bz.hour_pillar['stem']}{bz.hour_pillar['branch']}",
            "day_master": bz.day_master,
            "pattern": bz.pattern,
            "yong_shen": bz.yong_shen,
            "five_elements": bz.five_elements,
            "shen_sha": bz.shen_sha,
            "solar_term": bz.solar_term,
        }
    if charts.ziwei:
        zw = charts.ziwei
        summary["ziwei"] = {
            "life_palace": zw.life_palace,
            "body_palace": zw.body_palace,
            "five_element_bureau": zw.five_element_bureau,
        }
    if charts.natal_astro:
        na = charts.natal_astro
        summary["natal_astro"] = {
            "sun": na.planets.get("sun", {}).get("sign"),
            "moon": na.planets.get("moon", {}).get("sign"),
            "asc": na.planets.get("ascendant") or {"sign": _sign_from_deg(na.angles.get("ASC", 0))},
            "moon_phase": na.moon_phase,
            "distributions": na.distributions,
        }
    if charts.tarot:
        summary["tarot"] = {
            "spread": charts.tarot.spread,
            "cards": [c.get("card_name") for c in charts.tarot.drawn_cards],
        }
    if charts.numerology:
        nu = charts.numerology
        summary["numerology"] = {
            "life_path": nu.life_path,
            "expression": nu.expression,
            "personal_year": nu.personal_year,
        }
    if charts.hexagram:
        hx = charts.hexagram
        summary["hexagram"] = {
            "ben_gua": hx.ben_gua.get("name"),
            "bian_gua": hx.bian_gua.get("name") if hx.bian_gua else None,
            "moving_lines": hx.moving_lines,
        }
    if charts.fengshui:
        fs = charts.fengshui
        summary["fengshui"] = {
            "facing": fs.facing_direction,
            "period": fs.period,
            "ming_gua": fs.ming_gua,
        }
    return summary


def _sign_from_deg(deg: float) -> str:
    signs = ["白羊", "金牛", "双子", "巨蟹", "狮子", "处女",
             "天秤", "天蝎", "射手", "摩羯", "水瓶", "双鱼"]
    return signs[int(deg // 30) % 12]


def _stats_brief(stats: dict) -> dict:
    return {
        "total": stats["total"],
        "by_verdict": stats["by_verdict"],
        "fact_violations": len(stats["fact_violations"]),
        "kept": len(stats["kept"]),
    }


async def _make_skipped(group: str) -> SystemSummary:
    return SystemSummary(
        system_group=group,  # type: ignore
        is_skipped=True,
        skip_reason="no_active_expert_in_group",
        confidence="low",
        headline=f"{group} 组本次未激活",
    )


async def _run_one_expert(expert: str, state: AgentState) -> ExpertOpinion:
    """运行单个 expert，包括 RAG 检索 + Rule 触发 + Expert LLM 推理。"""
    # RAG: 召回典籍
    query = f"{state.question} {expert}"
    classics = retrieve_classics(query, system=expert, top_k=5)

    # Rule Engine: 找触发的规则
    rules = find_matching_rules(state.charts, system=expert, top_k=12)

    # Expert LLM
    try:
        return await run_expert(expert, state, classics=classics, rules=rules)
    except Exception as e:
        return ExpertOpinion(
            expert=expert,  # type: ignore
            system_group="chinese" if expert in CN_EXPERTS else "western",
            school=None,
            headline=f"{expert} 推理失败",
            summary=f"内部错误：{e}",
            points=[],
            confidence="low",
            flags=["exception"],
        )
