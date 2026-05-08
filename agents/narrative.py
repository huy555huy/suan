"""Narrative Agent — 把判官裁决改写为不同形态的最终输出。"""
from __future__ import annotations
import json

from core.schemas import AgentState
from core.llm_client import chat, chat_stream
from agents.prompts import (
    NARRATIVE_C_SYSTEM, NARRATIVE_REPORT_SYSTEM, NARRATIVE_COPILOT_SYSTEM,
)


def _select_system(scenario: str) -> str:
    if scenario == "report":
        return NARRATIVE_REPORT_SYSTEM
    if scenario == "copilot":
        return NARRATIVE_COPILOT_SYSTEM
    return NARRATIVE_C_SYSTEM


def _build_user_input(state: AgentState) -> str:
    verdict = state.verdict
    if not verdict:
        return "（无判官输出）"
    parts = [
        f"【用户问题】{state.question or '综合画像'}",
        f"【主综合】{verdict.weighted_summary}",
        f"【整体置信度】{verdict.overall_confidence}",
    ]

    # ★ 输入不确定性 caveats — 必须显式带入回应
    if state.caveats:
        parts.append(
            "【输入不确定性 · 必须在最终回应里显式提及】\n" +
            "\n".join(f"- {c}" for c in state.caveats) +
            "\n\n** 你必须在结论起首或末段用一段话明确告知用户这些不确定性如何影响本次结论的可信度，**"
            "**不能装作输入完整无误。** 同时，对于受不确定性影响最大的判断，请显式标注「此项受 X 不确定性影响，置信偏低」。"
        )

    if verdict.consensus:
        parts.append(f"【双重共识点】\n" + "\n".join(f"- {c}" for c in verdict.consensus))
    if verdict.conflicts:
        parts.append(
            f"【矛盾点】\n" + "\n".join(
                f"- {c.topic}: A={c.side_a} | B={c.side_b} → {c.arbitration}"
                for c in verdict.conflicts
            )
        )
    if verdict.actionable_advice:
        parts.append("【建议清单】\n" + "\n".join(f"- {a}" for a in verdict.actionable_advice))
    if verdict.cautions:
        parts.append("【需谨慎】\n" + "\n".join(f"- {c}" for c in verdict.cautions))
    if verdict.cross_alignment and verdict.cross_alignment.overall_summary:
        parts.append(f"【交叉验证总览】{verdict.cross_alignment.overall_summary}")
    parts.append("\n请按你的角色风格生成最终输出文本（Markdown）。")
    return "\n\n".join(parts)


async def run_narrative(state: AgentState) -> str:
    sys_msg = _select_system(state.scenario)
    user = _build_user_input(state)
    text, _ = await chat(
        [{"role": "system", "content": sys_msg},
         {"role": "user", "content": user}],
        temperature=0.65,
        max_tokens=3500,
        tier="high",
    )
    return text.strip()


async def stream_narrative(state: AgentState):
    """流式输出最终文本。"""
    sys_msg = _select_system(state.scenario)
    user = _build_user_input(state)
    async for chunk in chat_stream(
        [{"role": "system", "content": sys_msg},
         {"role": "user", "content": user}],
        temperature=0.65,
        max_tokens=3500,
        tier="high",
    ):
        yield chunk
