"""Planner-Executor 主循环。

这是 v1.4 设计文档第 7C.5 节的核心实现：让 LLM 在运行时自主决定下一步，
而不是按编译期写死的固定流水线走。

核心机制：
- 每步只决定一个动作（compute_chart / consult_expert / ask_user / cross_link / reflect / synthesize / finalize / stop）
- ask_user 时**暂停 SSE 流**（await message_queue.get()），等用户回答完再继续
- 所有动作都把 thought + result 进 history，下一步 Planner 看得到
- 步数 / token 预算硬上限：MAX_STEPS = 16, MAX_TOKENS_BUDGET ≈ 60k

主循环作为 async generator，yield 出所有事件供 SSE 流推送。
"""
from __future__ import annotations
import asyncio
import time
import uuid
from datetime import datetime
from typing import AsyncIterator

from core.schemas import (
    AgentState, ExpertOpinion, ReasoningTrace, TraceStep,
)
from core.config import settings
from agents.planner import planner_step, PlannerAction
from agents.insights import run_cross_link, run_reflect
from agents.expert import run_expert
from agents.synth import run_synth
from agents.aligner import run_aligner
from agents.judge import run_judge
from agents.narrative import stream_narrative
from agents.safety import apply_safety
from agents.verifier import verify_opinion
from agents.classifier import _keyword_route
from agents.compute_dispatch import dispatch_compute
from knowledge.retrieval import retrieve_classics
from knowledge.rule_engine import find_matching_rules


MAX_STEPS = 16
SAFE_FINALIZE_AT_STEP = 13  # 第 13 步后强制 finalize


def _now_ms() -> int:
    return int(time.time() * 1000)


async def _evt(kind: str, **payload) -> dict:
    return {"type": kind, "ts": _now_ms(), **payload}


def _add_trace(state: AgentState, agent: str, action: str, payload: dict | None = None):
    if not state.trace:
        return
    state.trace.steps.append(TraceStep(
        step_id=len(state.trace.steps) + 1,
        agent=agent,
        action=action,
        payload=payload or {},
    ))


# ── 主循环 ────────────────────────────────────────────────────
async def run_planner_loop(state: AgentState, message_queue: asyncio.Queue,
                            initial_question: str) -> AsyncIterator[dict]:
    """Planner-Executor 主循环。yield 事件给 SSE。

    state: 已注入 birth + caveats 的 AgentState
    message_queue: 多轮对话队列（用户每次发消息 put 进来）
    initial_question: 用户首条消息
    """
    if not state.trace:
        state.trace = ReasoningTrace(
            trace_id=f"tr_{uuid.uuid4().hex[:12]}",
            session_id=state.session_id,
            started_at=datetime.utcnow().isoformat(),
            steps=[],
        )

    history: list[dict] = []
    user_messages: list[str] = [initial_question]
    state.question = initial_question
    started_at = time.time()

    yield await _evt("planner_start",
                     session_id=state.session_id,
                     trace_id=state.trace.trace_id,
                     question=initial_question)

    if state.caveats:
        yield await _evt("input_caveats", caveats=state.caveats)

    # 主循环
    for step_no in range(1, MAX_STEPS + 1):
        # 强制 finalize 收束保护
        if step_no >= SAFE_FINALIZE_AT_STEP and not state.verdict:
            yield await _evt("planner_thought",
                             step=step_no,
                             thought=f"已达第 {step_no} 步，强制收束。",
                             action="finalize",
                             args={"style": "full"})
            async for evt in _execute_finalize(state, history):
                yield evt
            return

        # 1) Planner 思考
        yield await _evt("planner_thinking", step=step_no, message="思考下一步…")

        try:
            action = await planner_step(state, history, user_messages)
        except Exception as e:
            yield await _evt("error", message=f"Planner 失败：{e}",
                             step=step_no, fatal=True)
            return

        # 2) 推 thought + 决定的动作
        yield await _evt("planner_thought",
                         step=step_no,
                         thought=action.thought,
                         action=action.type,
                         args=action.args,
                         expected_outcome=action.expected_outcome)
        _add_trace(state, "planner", f"step_{step_no}_{action.type}",
                   {"thought": action.thought, "args": action.args})

        # 3) 执行动作
        try:
            if action.type == "ask_user":
                # ★ 关键：暂停流，等用户回答（带心跳防 idle 断连）
                question = (action.args or {}).get("question", "请补充更多信息。")
                why = (action.args or {}).get("why", "")
                yield await _evt("ask_user", step=step_no, question=question, why=why)

                # 心跳 + 等用户回答
                got_msg = None
                wait_start = time.time()
                while time.time() - wait_start < 600.0:  # 10 分钟最大等待
                    try:
                        raw = await asyncio.wait_for(message_queue.get(), timeout=15.0)
                        if isinstance(raw, dict):
                            got_msg = raw.get("text", "") or ""
                        else:
                            got_msg = str(raw)
                        break
                    except asyncio.TimeoutError:
                        # 发心跳保活
                        yield await _evt("waiting_user",
                                         elapsed=int(time.time() - wait_start),
                                         step=step_no)
                if got_msg is None:
                    yield await _evt("error", message="等待用户回答超时（10 分钟）",
                                     step=step_no, fatal=True)
                    return

                user_messages.append(got_msg)
                history.append({
                    "action_type": "ask_user_answered",
                    "question": question,
                    "answer": got_msg,
                    "summary": f"问 '{question[:40]}' 用户答 '{got_msg[:80]}'",
                })
                yield await _evt("user_replied", answer=got_msg)
                continue

            if action.type == "compute_chart":
                ct = (action.args or {}).get("chart_type") or (action.args or {}).get("type") or "bazi"
                yield await _evt("planner_executing", action="compute_chart",
                                 chart_type=ct, step=step_no)
                try:
                    await dispatch_compute(ct, state)
                    chart_summary = _chart_brief(state.charts, ct)
                    yield await _evt("chart_ready", chart_type=ct, summary=chart_summary)
                    history.append({
                        "action_type": "compute_chart",
                        "chart_type": ct,
                        "summary": f"算出 {ct}: {chart_summary[:160]}",
                    })
                except Exception as e:
                    yield await _evt("action_error", action="compute_chart",
                                     chart_type=ct, error=str(e))
                    history.append({"action_type": "compute_chart_failed",
                                    "chart_type": ct, "summary": f"算 {ct} 失败：{e}"})
                continue

            if action.type == "consult_expert":
                args = action.args or {}
                expert = args.get("name") or "bazi"
                focus = args.get("focus") or state.question
                depth = args.get("depth") or "normal"

                # 自动确保对应盘面已算
                needed_chart = _expert_to_chart(expert)
                if needed_chart and not _has_chart(state.charts, needed_chart):
                    yield await _evt("planner_executing", action="auto_compute",
                                     chart_type=needed_chart, step=step_no,
                                     reason=f"咨询 {expert} 需要 {needed_chart}，先算")
                    try:
                        await dispatch_compute(needed_chart, state)
                        yield await _evt("chart_ready", chart_type=needed_chart,
                                         summary=_chart_brief(state.charts, needed_chart))
                    except Exception as e:
                        yield await _evt("action_error", action="auto_compute",
                                         chart_type=needed_chart, error=str(e))

                yield await _evt("planner_executing", action="consult_expert",
                                 expert=expert, focus=focus, depth=depth, step=step_no)
                try:
                    # 临时把 focus 注入 state.question 让 expert 看到
                    saved_q = state.question
                    state.question = focus
                    classics = retrieve_classics(focus, system=expert, top_k=5)
                    rules = find_matching_rules(state.charts, system=expert, top_k=12)
                    op = await run_expert(expert, state, classics=classics, rules=rules)
                    state.question = saved_q

                    state.expert_opinions.append(op)
                    # Verifier
                    stats = await verify_opinion(op, state.charts, use_llm=False)
                    yield await _evt("expert_done",
                                     expert=op.expert,
                                     system_group=op.system_group,
                                     school=op.school,
                                     headline=op.headline,
                                     summary=op.summary,
                                     n_points=len(op.points),
                                     confidence=op.confidence,
                                     verifier_stats=_stats_brief(stats))
                    history.append({
                        "action_type": "consult_expert",
                        "expert": expert,
                        "summary": f"{expert}({op.confidence}): {op.headline}",
                    })
                except Exception as e:
                    yield await _evt("action_error", action="consult_expert",
                                     expert=expert, error=str(e))
                    history.append({"action_type": "consult_expert_failed",
                                    "expert": expert, "summary": f"咨询 {expert} 失败：{e}"})
                continue

            if action.type == "cross_link":
                yield await _evt("planner_executing", action="cross_link",
                                 systems=(action.args or {}).get("systems"), step=step_no)
                insight = await run_cross_link(state, action.args or {})
                yield await _evt("cross_link_insight", **insight)
                history.append({
                    "action_type": "cross_link",
                    "summary": f"联结：{insight.get('headline', '')}",
                })
                continue

            if action.type == "reflect":
                yield await _evt("planner_executing", action="reflect", step=step_no)
                reflection = await run_reflect(state, action.args or {})
                yield await _evt("reflection", **reflection)
                history.append({
                    "action_type": "reflect",
                    "summary": f"反思：{reflection.get('headline', '')}",
                })
                continue

            if action.type == "synthesize":
                scope = (action.args or {}).get("scope") or "judge"
                yield await _evt("planner_executing", action="synthesize",
                                 scope=scope, step=step_no)

                if scope in ("chinese", "all"):
                    cn_ops = [op for op in state.expert_opinions
                              if op.system_group == "chinese"]
                    state.cn_synth = await run_synth("chinese", cn_ops)
                    yield await _evt("synth_done", group="chinese",
                                     headline=state.cn_synth.headline,
                                     n_topics=len(state.cn_synth.by_topic),
                                     is_skipped=state.cn_synth.is_skipped)

                if scope in ("western", "all"):
                    wt_ops = [op for op in state.expert_opinions
                              if op.system_group == "western"]
                    state.wt_synth = await run_synth("western", wt_ops)
                    yield await _evt("synth_done", group="western",
                                     headline=state.wt_synth.headline,
                                     n_topics=len(state.wt_synth.by_topic),
                                     is_skipped=state.wt_synth.is_skipped)

                if scope in ("cross", "all"):
                    if not state.cn_synth:
                        cn_ops = [op for op in state.expert_opinions
                                  if op.system_group == "chinese"]
                        state.cn_synth = await run_synth("chinese", cn_ops)
                    if not state.wt_synth:
                        wt_ops = [op for op in state.expert_opinions
                                  if op.system_group == "western"]
                        state.wt_synth = await run_synth("western", wt_ops)
                    state.cross_alignment = await run_aligner(state.cn_synth, state.wt_synth)
                    yield await _evt("aligner_done",
                                     consensus_score=state.cross_alignment.overall_consensus_score,
                                     divergence_score=state.cross_alignment.overall_divergence_score,
                                     n_topics=len(state.cross_alignment.by_topic),
                                     summary=state.cross_alignment.overall_summary,
                                     by_topic={k: v.model_dump() for k, v in
                                               list(state.cross_alignment.by_topic.items())[:6]})

                if scope in ("judge", "all"):
                    if not state.cn_synth:
                        cn_ops = [op for op in state.expert_opinions if op.system_group == "chinese"]
                        state.cn_synth = await run_synth("chinese", cn_ops)
                    if not state.wt_synth:
                        wt_ops = [op for op in state.expert_opinions if op.system_group == "western"]
                        state.wt_synth = await run_synth("western", wt_ops)
                    if not state.cross_alignment and not (state.cn_synth.is_skipped or state.wt_synth.is_skipped):
                        state.cross_alignment = await run_aligner(state.cn_synth, state.wt_synth)
                        yield await _evt("aligner_done",
                                         consensus_score=state.cross_alignment.overall_consensus_score,
                                         divergence_score=state.cross_alignment.overall_divergence_score,
                                         n_topics=len(state.cross_alignment.by_topic),
                                         summary=state.cross_alignment.overall_summary,
                                         by_topic={k: v.model_dump() for k, v in
                                                   list(state.cross_alignment.by_topic.items())[:6]})
                    state.verdict = await run_judge(state)
                    yield await _evt("verdict_done",
                                     confidence=state.verdict.overall_confidence,
                                     consensus=state.verdict.consensus,
                                     conflicts=[c.model_dump() for c in state.verdict.conflicts],
                                     summary=state.verdict.weighted_summary,
                                     advice=state.verdict.actionable_advice,
                                     cautions=state.verdict.cautions)

                history.append({
                    "action_type": "synthesize",
                    "scope": scope,
                    "summary": f"已综合（{scope}）"
                })
                continue

            if action.type == "finalize":
                async for evt in _execute_finalize(state, history):
                    yield evt
                state.latency_ms = int((time.time() - started_at) * 1000)
                return

            if action.type == "stop":
                reason = (action.args or {}).get("reason", "planner_stop")
                yield await _evt("done",
                                 reason=reason,
                                 step=step_no,
                                 narrative_len=len(state.narrative))
                return

            # 未知动作
            yield await _evt("action_error",
                             action=action.type,
                             error=f"未知动作类型 {action.type}")

        except Exception as e:
            yield await _evt("action_error",
                             action=action.type,
                             error=str(e),
                             step=step_no)
            history.append({
                "action_type": f"{action.type}_failed",
                "summary": str(e)[:200],
            })
            # 不中断 — Planner 下一步可以决定如何应对

    # 步数耗尽
    yield await _evt("planner_max_steps", step=MAX_STEPS)
    if not state.verdict:
        async for evt in _execute_finalize(state, history):
            yield evt


# ── 辅助 ────────────────────────────────────────────────────
async def _wait_for_next_user_message(queue: asyncio.Queue,
                                       timeout: float = 600.0) -> str:
    """阻塞等下一条用户消息（10 分钟上限）。"""
    msg = await asyncio.wait_for(queue.get(), timeout=timeout)
    if isinstance(msg, dict):
        return msg.get("text", "") or ""
    return str(msg)


async def _execute_finalize(state: AgentState, history: list[dict]) -> AsyncIterator[dict]:
    """收束：确保有 verdict → 流式 narrative → safety → done。"""
    # 确保有综合判断
    if not state.cn_synth:
        cn_ops = [op for op in state.expert_opinions if op.system_group == "chinese"]
        if cn_ops:
            state.cn_synth = await run_synth("chinese", cn_ops)
            yield await _evt("synth_done", group="chinese",
                             headline=state.cn_synth.headline,
                             n_topics=len(state.cn_synth.by_topic),
                             is_skipped=state.cn_synth.is_skipped)
    if not state.wt_synth:
        wt_ops = [op for op in state.expert_opinions if op.system_group == "western"]
        if wt_ops:
            state.wt_synth = await run_synth("western", wt_ops)
            yield await _evt("synth_done", group="western",
                             headline=state.wt_synth.headline,
                             n_topics=len(state.wt_synth.by_topic),
                             is_skipped=state.wt_synth.is_skipped)
    if (not state.cross_alignment and state.cn_synth and state.wt_synth
        and not state.cn_synth.is_skipped and not state.wt_synth.is_skipped):
        state.cross_alignment = await run_aligner(state.cn_synth, state.wt_synth)
        yield await _evt("aligner_done",
                         consensus_score=state.cross_alignment.overall_consensus_score,
                         divergence_score=state.cross_alignment.overall_divergence_score,
                         n_topics=len(state.cross_alignment.by_topic),
                         summary=state.cross_alignment.overall_summary,
                         by_topic={k: v.model_dump() for k, v in
                                   list(state.cross_alignment.by_topic.items())[:6]})
    if not state.verdict:
        state.verdict = await run_judge(state)
        yield await _evt("verdict_done",
                         confidence=state.verdict.overall_confidence,
                         consensus=state.verdict.consensus,
                         conflicts=[c.model_dump() for c in state.verdict.conflicts],
                         summary=state.verdict.weighted_summary,
                         advice=state.verdict.actionable_advice,
                         cautions=state.verdict.cautions)

    # 流式 narrative
    yield await _evt("narrative_start")
    text = ""
    try:
        async for chunk in stream_narrative(state):
            if chunk:
                text += chunk
                yield await _evt("narrative_chunk", text=chunk)
    except Exception as e:
        yield await _evt("error", message=f"撰写失败：{e}")
        return

    # Safety
    safe_text, triggers = apply_safety(text)
    state.narrative = safe_text
    state.safety_passed = "crisis" not in triggers
    state.safety_notes = triggers
    if safe_text != text:
        yield await _evt("narrative", text=safe_text, replaced=True,
                         safety_triggers=triggers)
    yield await _evt("done",
                     session_id=state.session_id,
                     narrative_len=len(state.narrative),
                     n_experts=len(state.expert_opinions))


def _chart_brief(charts, chart_type: str) -> str:
    """对应盘面的一句话摘要。"""
    if chart_type == "bazi" and charts.bazi:
        bz = charts.bazi
        return (f"{bz.year_pillar['stem']}{bz.year_pillar['branch']}/"
                f"{bz.month_pillar['stem']}{bz.month_pillar['branch']}/"
                f"{bz.day_pillar['stem']}{bz.day_pillar['branch']}/"
                f"{bz.hour_pillar['stem']}{bz.hour_pillar['branch']} 日主{bz.day_master} {bz.pattern or ''}")
    if chart_type == "ziwei" and charts.ziwei:
        zw = charts.ziwei
        return f"命宫{zw.life_palace} 五行局{zw.five_element_bureau}"
    if chart_type == "natal_astro" and charts.natal_astro:
        na = charts.natal_astro
        return (f"太阳{na.planets.get('sun',{}).get('sign')} "
                f"月亮{na.planets.get('moon',{}).get('sign')} "
                f"月相{na.moon_phase}")
    if chart_type == "transit_astro" and charts.transit_astro:
        ts = charts.transit_astro
        return f"行运 · 关键事件 {len(ts.key_transits)} 个"
    if chart_type == "tarot" and charts.tarot:
        t = charts.tarot
        cards = "/".join(c.get("card_name", "") for c in t.drawn_cards[:3])
        return f"{t.spread} · {cards}"
    if chart_type == "numerology" and charts.numerology:
        nu = charts.numerology
        return f"生命数{nu.life_path} 表达数{nu.expression} 个人年{nu.personal_year}"
    if chart_type == "hexagram" and charts.hexagram:
        hx = charts.hexagram
        return (f"本卦{hx.ben_gua.get('name')} "
                f"变卦{hx.bian_gua.get('name') if hx.bian_gua else '—'} "
                f"动爻{hx.moving_lines}")
    if chart_type == "fengshui" and charts.fengshui:
        fs = charts.fengshui
        return f"朝向{fs.facing_direction} 运{fs.period} 命卦{fs.ming_gua}"
    return "已计算"


def _expert_to_chart(expert: str) -> str | None:
    return {
        "bazi": "bazi",
        "ziwei": "ziwei",
        "yijing": "hexagram",
        "fengshui": "fengshui",
        "liunian": "bazi",
        "astrology": "natal_astro",
        "tarot": "tarot",
        "numerology": "numerology",
    }.get(expert)


def _has_chart(charts, chart_type: str) -> bool:
    return getattr(charts, chart_type, None) is not None


def _stats_brief(stats: dict) -> dict:
    return {
        "total": stats.get("total", 0),
        "by_verdict": stats.get("by_verdict", {}),
        "fact_violations": len(stats.get("fact_violations", [])),
        "kept": len(stats.get("kept", [])),
    }
