"""涌现性动作（Planner 调用，体现 agent 行为而非死板流水线）。

- cross_link: 当多个独立体系同时点亮同一信号，让 LLM 写一段联结洞察
- reflect: 元认知，对之前某条判断重新审视并修订

这两类输出**直接进入会话气泡**，让用户看见 agent 是真的在思考，而不是在拼模板。
"""
from __future__ import annotations
import json
from typing import Any

from core.schemas import AgentState
from core.llm_client import chat_json


CROSS_LINK_SYSTEM = """你是「算」研判合议的 Planner，正在做 **跨系统涌现联结**。

当你发现两套或以上独立体系（中式 八字/紫微/易经/风水 + 西式 占星/塔罗/数字命理）
同时点亮**同一现象**时，把这条联结写出来给用户。

【输出 JSON】
{
  "headline": "一句话核心洞察（30 字内）",
  "narrative": "120-220 字解读，必须用'我注意到X系统的A + Y系统的B + Z系统的C都在指向...'这种带来源标注的句式",
  "strength": "weak|moderate|strong",
  "implication": "这条联结对用户问题的实际影响（一句话）"
}

【示例】
{
  "headline": "三套体系同时指向"主动求变"",
  "narrative": "我注意到八字（流年甲辰冲申，驿马动）+ 紫微（官禄宫武曲化禄）+ 占星（土星 transit MC）三套独立体系都在指向同一个轴：今年事业上的变动力。这种'三套独立路径在同一处汇合'本身就是强信号——它意味着这不是某次偶然，而是你这一年命局结构里相对稳定的能量方向。",
  "strength": "strong",
  "implication": "你今年的事业核心议题是'怎么变'，而不是'变不变'。"
}

【硬规则】
- 只输出 JSON 对象，不要 markdown 代码块
- 必须明确点出"X 系统的 A"和"Y 系统的 B"是哪两条独立信号
- 不允许说"100%"/"必然"/"一定"
"""


REFLECT_SYSTEM = """你是「算」研判合议的 Planner，正在做 **元认知反思**。

你之前有一条判断，但你对它有疑虑。把这个反思写出来——承认不确定，邀请用户给更多 context。
不要装作笃定。

【输出 JSON】
{
  "headline": "一句话反思（30 字内）",
  "narrative": "100-180 字反思，承认不确定来源 + 给两三种可能解读 + 提醒用户可以补什么 context 帮我收敛",
  "calibrated_confidence": "high|medium|low",
  "needs_followup": true|false
}

【示例】
{
  "headline": "我对'今年换工作'这条只有六成把握",
  "narrative": "我刚才说"今年事业有调动"是基于驿马动 + 流年冲申。但反过来看：你紫微的迁移宫主星很安定，占星侧土星刚过 MC 倾向'压力但不动'。三套体系给我的不是 60% 概率，而是三个不同方向的可能性。要我给单一结论我可以编一个，但不诚实。",
  "calibrated_confidence": "medium",
  "needs_followup": true
}

【硬规则】
- 只输出 JSON
- 反思要诚实——承认不确定不是弱点，是 agent 的诚信
- 如果需要用户补 context 才能收敛，needs_followup=true，由 Planner 下一步决定 ask_user
"""


async def run_cross_link(state: AgentState, args: dict) -> dict:
    """执行跨系统联结。"""
    systems = args.get("systems") or []
    topic = args.get("topic") or ""
    observation = args.get("observation") or ""

    # 把 state 里相关 expert 输出抽出
    relevant_ops = []
    for op in state.expert_opinions:
        if op.expert in systems or not systems:
            relevant_ops.append({
                "expert": op.expert,
                "school": op.school,
                "headline": op.headline,
                "summary": op.summary,
                "confidence": op.confidence,
            })

    user = (
        f"【联结主题】{topic}\n"
        f"【planner 的初始观察】{observation}\n\n"
        f"【参与联结的专家观点】\n" +
        "\n".join(f"- {op['expert']}({op['school']}, {op['confidence']}): {op['headline']}\n  {op['summary'][:240]}"
                  for op in relevant_ops) +
        "\n\n请输出跨系统联结 JSON。"
    )

    parsed, raw, _ = await chat_json(
        [{"role": "system", "content": CROSS_LINK_SYSTEM},
         {"role": "user", "content": user}],
        temperature=0.55,
        max_tokens=900,
        tier="high",
    )
    if not parsed or not isinstance(parsed, dict):
        return {"headline": "联结生成失败", "narrative": raw[:300], "strength": "weak", "implication": ""}
    return {
        "systems": systems,
        "topic": topic,
        "headline": parsed.get("headline", ""),
        "narrative": parsed.get("narrative", ""),
        "strength": parsed.get("strength", "moderate"),
        "implication": parsed.get("implication", ""),
    }


AUTO_EMERGENT_SYSTEM = """你是「算」研判合议的洞察生成器。

任务：从 Aligner 算出的 by_topic 里挑出 2-3 个**最强的双重共识 / 互补**信号，
为用户写**自动涌现**的洞察。这不是 planner 拍脑袋找的，是 26-topic 对齐算法
真的发现的"中式 + 西式同时点亮某一主题"。

【硬规则】
- 必须**真的**指出"X 系统的 A + Y 系统的 B + ...都指向 Z"——不要泛泛说"两套体系吻合"
- 每条洞察 60-150 字，**克制而非渲染**
- 只输出 JSON，不要 markdown 代码块
- 强度 strong = 3+ 体系汇合 + 高 consensus_points；moderate = 2 体系汇合；weak = 不入选

【输出 JSON】
{
  "insights": [
    {
      "topic": "topic key 原样",
      "headline": "30 字内核心洞察",
      "narrative": "60-150 字带'X系统A + Y系统B指向Z'的具体表述",
      "strength": "strong|moderate|weak",
      "implication": "对用户问题的实际意义（一句话）"
    },
    ...
  ]
}

如果没有足够强的信号（即所有 topic 都是 weak / incomparable），返回 {"insights": []} 即可，不强凑。
"""


async def run_auto_emergent(state: AgentState) -> list[dict]:
    """从 cross_alignment.by_topic 自动挖掘强信号涌现洞察。

    这是【真涌现】的实现：不经 Planner 决定，Aligner 算完后直接扫，
    consensus 或 complementary 且 consensus_points ≥ 2 的 topic 入选。
    """
    if not state.cross_alignment or not state.cross_alignment.by_topic:
        return []

    candidates = []
    for topic, ta in state.cross_alignment.by_topic.items():
        n_cons = len(ta.consensus_points or [])
        n_comp = len(ta.complementary_points or [])
        if ta.alignment_type == "consensus" and n_cons >= 2:
            candidates.append((topic, ta, n_cons * 2))
        elif ta.alignment_type == "complementary" and n_comp >= 2:
            candidates.append((topic, ta, n_comp))
    if not candidates:
        return []

    # 按强度排序，取前 3 个最强的
    candidates.sort(key=lambda x: -x[2])
    top = candidates[:3]

    # 收集相关 expert opinions 给 LLM 看
    expert_briefs = "\n".join(
        f"- {op.expert}({op.system_group}, {op.confidence}): {op.headline}"
        for op in state.expert_opinions
    )
    topic_payload = []
    for topic, ta, _ in top:
        topic_payload.append({
            "topic": topic,
            "alignment_type": ta.alignment_type,
            "chinese_view": ta.chinese_view or "",
            "western_view": ta.western_view or "",
            "consensus_points": ta.consensus_points,
            "complementary_points": ta.complementary_points,
            "final_synthesis": ta.final_synthesis or "",
        })

    user = (
        f"【用户问题】{state.question or '综合画像'}\n\n"
        f"【参与的专家观点】\n{expert_briefs}\n\n"
        f"【候选 topic（Aligner 已判定 consensus/complementary 强信号）】\n"
        f"{json.dumps(topic_payload, ensure_ascii=False, indent=2)[:2400]}\n\n"
        f"请生成 2-3 条自动涌现洞察的 JSON。"
    )

    parsed, raw, _ = await chat_json(
        [{"role": "system", "content": AUTO_EMERGENT_SYSTEM},
         {"role": "user", "content": user}],
        temperature=0.5,
        max_tokens=1200,
        tier="high",
    )
    if not parsed or not isinstance(parsed, dict):
        return []
    out = []
    for ins in parsed.get("insights") or []:
        if not isinstance(ins, dict):
            continue
        if ins.get("strength") == "weak":
            continue  # 跳过弱信号，不强凑
        out.append({
            "topic": ins.get("topic", ""),
            "headline": ins.get("headline", "")[:80],
            "narrative": ins.get("narrative", "")[:400],
            "strength": ins.get("strength", "moderate"),
            "implication": ins.get("implication", "")[:120],
            "source": "auto_emergent",  # 标记是自动涌现而非 planner 调的
        })
    return out


async def run_reflect(state: AgentState, args: dict) -> dict:
    """执行元认知反思。

    ★ 闭环改进：reflect 不再让 planner 自编 doubt，而是自动从 verifier flags
    和专家间的矛盾里抽出"真的有问题的地方"喂给 LLM 反思。这让 reflect 是
    "agent 看自己输出找漏洞"，而不是"agent 演一个反思"。
    """
    target = args.get("target") or args.get("claim") or ""
    doubt = args.get("doubt") or ""

    # ★ 自动抽取 verifier 抛出的严重 flag，作为反思的真实证据
    verifier_concerns = []
    for op in state.expert_opinions:
        if not op.flags:
            continue
        serious = [f for f in op.flags if any(k in f.upper() for k in
                  ["FACT_VIOLATION", "OVERCLAIM", "RULE_NOVEL", "SOURCE_SYNTHESIZED", "SEMANTIC_WEAK"])]
        if serious:
            verifier_concerns.append(f"{op.expert} 被标 {','.join(serious[:2])}: {op.headline[:60]}")

    # 自动找专家之间的潜在矛盾（同 topic 不同 confidence 或不同方向）
    conflict_hints = []
    if state.verdict and state.verdict.conflicts:
        for c in state.verdict.conflicts[:3]:
            conflict_hints.append(f"{c.topic}: A={c.side_a} vs B={c.side_b}")

    # 输入 caveats 也是反思的天然素材
    caveat_concerns = state.caveats[:3] if state.caveats else []

    user = (
        f"【你之前的判断】{target or '（未指定具体 target，对整体已答内容做反思）'}\n"
        f"【planner 提出的疑虑】{doubt or '（planner 未给具体 doubt，请你从下方证据里自己找）'}\n\n"
        f"【当前已知信息摘要】\n"
        f"- 已咨询专家：{[op.expert for op in state.expert_opinions]}\n"
        f"- 整体判官置信：{state.verdict.overall_confidence if state.verdict else '尚未'}\n"
        f"- 输入 caveats：{caveat_concerns}\n\n"
    )

    if verifier_concerns:
        user += (
            "【★ Verifier 反思镜实测到的薄弱点（必须重点反思这些）】\n" +
            "\n".join(f"  · {c}" for c in verifier_concerns[:6]) + "\n\n"
        )
    if conflict_hints:
        user += (
            "【专家间矛盾点】\n" +
            "\n".join(f"  · {c}" for c in conflict_hints) + "\n\n"
        )

    user += '请输出元认知反思 JSON。**优先承认 verifier flag 指出的具体问题**，不要泛泛说「我有点不确定」。'

    parsed, raw, _ = await chat_json(
        [{"role": "system", "content": REFLECT_SYSTEM},
         {"role": "user", "content": user}],
        temperature=0.5,
        max_tokens=600,
        tier="high",
    )
    if not parsed or not isinstance(parsed, dict):
        return {"headline": "反思失败", "narrative": raw[:300],
                "calibrated_confidence": "low", "needs_followup": False}
    return {
        "target": target,
        "headline": parsed.get("headline", ""),
        "narrative": parsed.get("narrative", ""),
        "calibrated_confidence": parsed.get("calibrated_confidence", "medium"),
        "needs_followup": bool(parsed.get("needs_followup", False)),
    }
