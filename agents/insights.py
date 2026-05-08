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


async def run_reflect(state: AgentState, args: dict) -> dict:
    """执行元认知反思。"""
    target = args.get("target") or args.get("claim") or ""
    doubt = args.get("doubt") or ""

    user = (
        f"【你之前的判断】{target}\n"
        f"【你的疑虑】{doubt}\n\n"
        f"【当前已知信息摘要】\n"
        f"- 已咨询专家：{[op.expert for op in state.expert_opinions]}\n"
        f"- 整体判官置信：{state.verdict.overall_confidence if state.verdict else '尚未'}\n"
        f"- 输入 caveats：{state.caveats}\n\n"
        f"请输出元认知反思 JSON。"
    )

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
