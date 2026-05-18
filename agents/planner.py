"""Planner Agent —— 运行时决定下一步动作。

设计文档第 7C.5 节"Planner-Executor 模式"的核心实现。

每一步只决定一个动作。Executor 真正调用工具 / 子 Agent。
Reflection 把执行结果带回 Planner，下一步重新决策。

可选动作（与 EXECUTOR 必须严格对齐）：
- compute_chart(chart_type)       触发某个盘面计算（bazi/ziwei/hexagram/fengshui/natal_astro/transit_astro/tarot/numerology）
- consult_expert(name, focus)     让某个命理 expert 介入推理（bazi/ziwei/yijing/fengshui/liunian/astrology/tarot/numerology）
- ask_user(question, why)         **主动追问**：信息不全 / 想深挖具体场景时，把控制权交回用户
- cross_link(systems, observation) 显式做跨系统联结（"中式 X 与西式 Y 同时点亮 Z"——agent 涌现的产物）
- reflect(claim, doubt)           元认知：对自己之前某条判断重新审视，给可信度修订或追加调研
- synthesize(scope)               触发综合："chinese" / "western" / "cross" / "judge"
- finalize                        收束并流式撰写最终回应
- stop                            提前结束（信息严重不足时使用）

输出格式严格 JSON：
{
  "thought": "我先看看用户档案是否完整 / 我想再追问一个具体场景 / ...（一句话，30-80 字）",
  "action": {"type": "ask_user", "args": {"question": "...", "why": "..."}},
  "expected_outcome": "预期会得到什么（用于反思时对照）"
}
"""
from __future__ import annotations
import json
from typing import Any, Literal
from pydantic import BaseModel, Field

from core.schemas import AgentState
from core.llm_client import chat_json


# ── 系统 Prompt ──────────────────────────────────────────────
PLANNER_SYSTEM = """你是「算」研判合议的 **Planner Agent**。

你站在主位，调度 7 路命理代理（八字/紫微/易经/风水/占星/塔罗/数字命理）+ 计算工具 + 知识库 +
**用户对话**作为你的工具与协作对象。

每一步你只决定一个动作。Executor 会真正去执行。结果会作为 reflection 反馈给你，
你再决定下一步。

【硬规则】
1. 你绝对不计算或推断任何盘面元素（干支/星曜/相位/卦爻/塔罗牌/数字命理结果）。
   所有这些数值都已由确定性算法库计算并提供给你。你只读盘 / 解释 / 综合 / 决策下一步。
2. 严禁使用："100%" / "一定" / "必然" / "保证" / "改命/改运" 等绝对化用词。
3. 严禁医学诊断 / 自残建议 / 极端行为建议。

【可选动作（每步只能选一个）】
- compute_chart(chart_type): 触发某个盘面计算
  chart_type ∈ {bazi, ziwei, hexagram, fengshui, natal_astro, transit_astro, tarot, numerology}
- consult_expert(name, focus, depth): 让某个命理 expert 推理
  name ∈ {bazi, ziwei, yijing, fengshui, liunian, astrology, tarot, numerology}
  focus: 一句话告诉 expert 重点看哪一块（如 "夫妻宫与桃花" / "9 宫与土星行运"）
  depth ∈ {brief, normal, deep}
- ask_user(question, why): **主动追问用户**——信息不全、场景不明、想深挖具体情境时使用
  question: 一句具体的问题
  why: 一句解释"为什么我需要知道这个"
- cross_link(systems, topic, observation): 显式做跨系统联结
  当你发现两套或以上独立体系同时指向同一信号时，用这个动作把它写出来给用户看
  systems: 比如 ["bazi", "astrology"] 或 ["bazi", "ziwei", "astrology"]
  observation: 你看到的"奇妙交集"或"启发性反差"
- reflect(target, doubt): 元认知，对自己之前的判断重新审视
  target: 之前 claim 的内容摘要
  doubt: 你对这条结论的疑虑
- synthesize(scope): 触发综合
  scope ∈ {chinese, western, cross, judge}
- finalize(style): 收束并流式撰写最终回应
  style ∈ {brief, full}
- stop(reason): 提前结束（仅当信息严重不全且用户无法补充时使用）

【判断启发】
- 用户档案有 caveats（时辰未知 / 地名未识）→ 必要时 ask_user 让用户补充，或在结论里显式标注"此项受 X 影响"
- 用户问"我该不该 X"但缺关键背景（行业 / 关系状态 / 时间段）→ ask_user 主动追问 1-2 个关键问题
- 已 consult 多路专家、看到 ≥2 个体系点亮同一信号 → cross_link 把这个发现写出来
- 某条结论你不太有把握 → reflect，给一个不确定性修订
- 已咨询了主要专家（≥3）+ 信息基本齐 → synthesize, 然后 finalize

【ask_user 硬上限 — 严格遵守】
- 全程 ask_user 最多 2 次。第 3 次想追问时，**必须把"想问的问题"作为 narrative 中的反问留给读者**，而不是阻塞流。
- **已发出 verdict_done（即调用过 synthesize(judge) 或 synthesize(all)）之后，禁止再 ask_user**。
  此时只能 finalize 或 stop —— 用户已经看到主综合，再问会让他觉得啰嗦。
- 已 ask_user 过 2 次的情况下，下一步必须是 synthesize 或 finalize，不能再 ask_user。

【多轮对话 — 跨轮记忆处理】
- 如果状态摘要里有【上一轮已答】section，说明这是**追问**，不是首问。
- 你的核心任务：用最少的步数回答 NEW 问题，**建立在上轮答案之上，不要从头重做**。
- 决策启发：
  · 新问题是上轮答案的**引申 / 细化**（"那具体几月？" "为什么不能去远方？"）
    → 直接 `consult_expert` 1-2 个最相关的专家深挖 → `synthesize(judge)` → `finalize`。**3-4 步内收束**。
  · 新问题是**完全新主题**（首问"事业"，追问"婚姻怎么样"）
    → 可以走原 5-7 步流程，但**保留前轮 verdict 作背景**，在 narrative 里桥接两个话题。
  · 新问题是**确认 / 复述**（"你说的'下半年得禄'是几月开始？"）
    → 不需要 consult 专家，直接 `finalize(brief)` 把已有信息精确化即可。**1 步收束**。
- 在 narrative 里**不要重复**说"丁火日主 / 正财格 / 9 宫狮子群星"等用户上轮已看过的盘面背景。专注新问题。
- 如果发现上轮判断和新问题/新信息有矛盾，先 `reflect`，再 `finalize` 给修订版结论。

【cross_link 启发 — 涌现性是产品差异化】
- 至少咨询 1 路西式专家（astrology / tarot / numerology），让中西能交叉。
  纯中式 3 路也能做 cross_link，但带上西式才有"两灯互照"。
- 任何时候你看到 2+ 体系给同一信号 → 立刻 cross_link，不要等。
- cross_link 之后再 finalize，narrative 里会自动呈现这条联结。

【典型路径示例】
新对话 + 用户问"我今年事业怎么走"：
  step 1: compute_chart(bazi)        ← 不需要 LLM，必跑
  step 2: compute_chart(natal_astro)
  step 3: consult_expert(bazi, focus="官杀格局 + 流年甲辰", depth=normal)
  step 4: consult_expert(astrology, focus="土星 transit + 10宫", depth=normal)
  step 5: cross_link(["bazi","astrology"], topic="career", observation="八字流年驿马动 + 占星土星过 MC")
  step 6: ask_user("你现在的工作大致是哪个领域？这会影响我把建议落到具体方向", why="缺这个我只能给 generic 建议")
  ⟨用户回答⟩
  step 7: consult_expert(ziwei, focus="官禄宫，结合用户提到的 IT 行业", depth=normal)
  step 8: synthesize(judge)
  step 9: finalize(full)

【反思 / 修订】
你看到 reflection 里有：
- expert 说 "用户档案有时辰未知 caveat" → ask_user("能补一下大概时辰吗？连'下午/晚上'都行") + why
- expert 给的 confidence 偏低或互相矛盾 → reflect 或追加 cross_link
- 已 8 步还没 finalize → 最多再 2-3 步必须收束

【输出 — 严格 JSON，不要包裹 markdown 代码块】
{
  "thought": "30-80 字思考",
  "action": { "type": "...", "args": {...} },
  "expected_outcome": "预期"
}
"""


class PlannerAction(BaseModel):
    type: Literal[
        "compute_chart", "consult_expert", "ask_user", "cross_link",
        "reflect", "synthesize", "finalize", "stop"
    ]
    args: dict[str, Any] = Field(default_factory=dict)
    thought: str = ""
    expected_outcome: str = ""


def _summarize_state_for_planner(state: AgentState, history: list[dict],
                                  user_messages: list[str]) -> str:
    """把当前状态压缩成 prompt 输入。"""
    lines = []

    # 用户档案
    bi = state.birth
    lines.append(f"【用户档案】{state.user_name or bi.name or '匿名'}（{bi.gender}）"
                 f" {bi.year}-{bi.month:02d}-{bi.day:02d}"
                 f" {bi.hour:02d}:{bi.minute:02d}（{bi.location_name}）")
    if state.caveats:
        lines.append(f"【输入不确定性】" + " | ".join(state.caveats))

    # ★ 跨轮记忆 — 让 planner 知道上次说过什么，避免重复
    if state.prior_round:
        pr = state.prior_round
        lines.append("【上一轮已答】")
        lines.append(f"  · 上轮问：{pr.question[:200]}")
        if pr.verdict_summary:
            lines.append(f"  · 上轮答（置信 {pr.verdict_confidence}）：{pr.verdict_summary[:300]}")
        if pr.consensus_points:
            lines.append(f"  · 双重共识：" + " / ".join(c[:60] for c in pr.consensus_points[:4]))
        if pr.expert_headlines:
            lines.append(f"  · 上轮 expert 已说：" +
                         " | ".join(f"{e}「{h[:50]}」" for e, h in list(pr.expert_headlines.items())[:5]))
        if pr.emergent_insights:
            lines.append(f"  · 上轮涌现：" + " / ".join(ei[:60] for ei in pr.emergent_insights[:3]))
        lines.append('  ↑ **本次是追问，不要从头重做。按 prompt 里「多轮对话」段执行。**')

    # 用户问答历史
    if user_messages:
        lines.append("【对话历史】")
        for i, m in enumerate(user_messages):
            role = "用户" if i % 2 == 0 else "用户（追加）"
            lines.append(f"  · {role}：{m[:300]}")

    # 已算盘面
    computed = []
    if state.charts.bazi: computed.append("bazi")
    if state.charts.ziwei: computed.append("ziwei")
    if state.charts.hexagram: computed.append("hexagram")
    if state.charts.fengshui: computed.append("fengshui")
    if state.charts.natal_astro: computed.append("natal_astro")
    if state.charts.transit_astro: computed.append("transit_astro")
    if state.charts.tarot: computed.append("tarot")
    if state.charts.numerology: computed.append("numerology")
    lines.append(f"【已算盘面】{', '.join(computed) if computed else '(空)'}")

    # 盘面摘要
    if state.charts.bazi:
        bz = state.charts.bazi
        lines.append(
            f"  bazi: {bz.year_pillar['stem']}{bz.year_pillar['branch']}/"
            f"{bz.month_pillar['stem']}{bz.month_pillar['branch']}/"
            f"{bz.day_pillar['stem']}{bz.day_pillar['branch']}/"
            f"{bz.hour_pillar['stem']}{bz.hour_pillar['branch']}"
            f" 日主{bz.day_master} {bz.pattern or ''} 神煞{bz.shen_sha}"
        )
    if state.charts.ziwei:
        zw = state.charts.ziwei
        lines.append(f"  ziwei: 命宫{zw.life_palace} 五行局{zw.five_element_bureau}")
    if state.charts.natal_astro:
        na = state.charts.natal_astro
        sun = na.planets.get("sun", {})
        moon = na.planets.get("moon", {})
        lines.append(f"  natal: 太阳{sun.get('sign')} 月亮{moon.get('sign')} 月相{na.moon_phase}")
    if state.charts.numerology:
        nu = state.charts.numerology
        lines.append(f"  numerology: 生命数{nu.life_path} 个人年{nu.personal_year}")

    # 已咨询的专家（含 verifier flags 让 planner 看到自己输出的薄弱点）
    if state.expert_opinions:
        lines.append("【已咨询专家】")
        for op in state.expert_opinions:
            flag_str = ""
            if op.flags:
                # 突出真的有问题的 flag
                serious = [f for f in op.flags if any(k in f.upper() for k in
                          ["FACT_VIOLATION", "OVERCLAIM", "RULE_NOVEL", "SOURCE_SYNTHESIZED", "SEMANTIC_WEAK"])]
                if serious:
                    flag_str = f"  [⚠ verifier flags: {','.join(serious[:3])}]"
            lines.append(f"  · {op.expert}({op.confidence}): {op.headline}{flag_str}")
            lines.append(f"    {op.summary[:160]}")

    # 涌现性洞察（auto-emergent，不经 planner 决定）
    if state.emergent_insights:
        lines.append("【自动涌现】")
        for ei in state.emergent_insights[-3:]:
            lines.append(f"  · {ei.get('headline','')}（强度 {ei.get('strength','')}）")

    # 综合状态
    if state.cn_synth and not state.cn_synth.is_skipped:
        lines.append(f"【中式综合】{state.cn_synth.headline}")
    if state.wt_synth and not state.wt_synth.is_skipped:
        lines.append(f"【西式综合】{state.wt_synth.headline}")
    if state.cross_alignment:
        lines.append(f"【交叉验证】共识 {state.cross_alignment.overall_consensus_score:.0%} / "
                     f"分歧 {state.cross_alignment.overall_divergence_score:.0%}")
    if state.verdict:
        lines.append(f"【判官】已成 ({state.verdict.overall_confidence})")

    # 历史动作
    if history:
        lines.append("【已执行动作（最近 8 个）】")
        for h in history[-8:]:
            lines.append(f"  · {h.get('action_type')}: {h.get('summary', '')[:140]}")

    lines.append(f"【步数】已 {len(history)} 步")
    return "\n".join(lines)


async def planner_step(state: AgentState, history: list[dict],
                       user_messages: list[str]) -> PlannerAction:
    """请求 Planner LLM 决定下一步。"""
    state_summary = _summarize_state_for_planner(state, history, user_messages)

    user_prompt = (
        state_summary +
        "\n\n请决定下一步动作。**只输出一个 JSON 对象**，不要包裹任何额外文字或代码块。"
    )

    parsed, raw, _ = await chat_json(
        [
            {"role": "system", "content": PLANNER_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
        max_tokens=600,
        tier="high",
    )

    if not parsed or not isinstance(parsed, dict):
        # 解析失败 → 给一个 finalize 兜底（不算 fallback，是 planner 自己决定）
        return PlannerAction(
            type="finalize",
            args={"style": "brief"},
            thought="解析 planner 输出失败，强制收束。",
            expected_outcome="给用户一个最小可用回应",
        )

    action = parsed.get("action") or {}
    if not isinstance(action, dict):
        action = {}
    a_type = action.get("type") or "finalize"
    if a_type not in {"compute_chart", "consult_expert", "ask_user", "cross_link",
                      "reflect", "synthesize", "finalize", "stop"}:
        a_type = "finalize"

    return PlannerAction(
        type=a_type,  # type: ignore
        args=action.get("args") or {},
        thought=parsed.get("thought") or "",
        expected_outcome=parsed.get("expected_outcome") or "",
    )
