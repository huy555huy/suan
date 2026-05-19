"""单 Agent ReAct 循环 — 「算」的核心引擎。

架构：一个 LLM + N 个工具 + M 个可按需加载的 Skill。
没有 planner / expert / synth / aligner / judge 等角色，
LLM 自己决定调什么工具、加载什么技能、什么时候输出。

流式 SSE 事件类型（极简）：
  - thought       : agent 的思考过程
  - tool_call     : agent 调用了某个工具
  - tool_result   : 工具返回结果
  - skill_loaded  : 加载了一个技能
  - ask_user      : agent 需要用户补充信息
  - text_delta    : 最终回答的流式文本片段
  - done          : 结束
  - error         : 出错
"""
from __future__ import annotations
import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator

from core.schemas import BirthInfo, Charts
from core.llm_client import get_client
from core.config import settings
from agents.tools import TOOL_SCHEMAS, ToolExecutor

logger = logging.getLogger("suan.agent")

# ── System Prompt ────────────────────────────────────────────

SYSTEM_PROMPT = """你是「算」—— 一个精通中西方命理的 AI 研判师。

你的知识来自八字/紫微斗数/易经/风水（中式）和占星/塔罗/数字命理（西式）七大体系。

## 你的工作方式

你是一个 agent：自主决定需要加载哪些技能、计算哪些盘面、查阅哪些典籍，然后综合研判给出回答。

### 步骤

1. **理解问题** — 判断用户在问什么主题（事业/感情/财运/健康/时机...），需要用到哪些命理体系
2. **确认输入合同** — 只使用用户明示资料；缺出生时辰、地点、朝向、起卦输入、抽牌结果等关键事实时，用 `ask_user` 追问
3. **加载技能** — 用 `load_skill` 加载相关体系的方法论，技能会教你具体怎么做解读
4. **计算盘面** — 用 `compute_chart` 算出需要的盘面数据；工具拒绝时停止追问，不要绕过
5. **参考人工盘例** — 八字/紫微/六爻/风水必须用 `load_golden_cases(system=...)` 拉取同体系专业黄金案例，先看老师傅式解释锚点
6. **查阅典籍** — 用 `grep_classics` + `read_classic` 找引证，用 `grep_rules` + `read_rule` 查规则
7. **校验结论** — 每条核心判断(Tier A)必须用 `verify_claim` 校验三元组（chart_ref + rule_ref + source_ref），REJECTED 必须修正
8. **中西独立推理** — 如果同时用了中式和西式体系，**必须先独立出各自结论再交叉**（见下方"中西交叉纪律"）
9. **安全审查** — 用 `apply_safety` 检查最终输出
10. **回答用户** — 输出最终文本

### 模糊请求的取盘策略

用户经常不会明确说要算什么体系，比如"帮我算个命"、"看看我的运势"、"最近怎么样"。
遇到这类模糊请求时：

1. **资料完整时不要 ask_user 追问体系选择** — 直接开工，用户来算命不是来做选择题的
2. **资料完整时默认核心组合：八字 + 紫微** — 一个看四柱格局/大运流年，一个看命身宫/大限宫位
   - 先 `load_skill("bazi")` + `compute_chart("bazi")` + `load_golden_cases("bazi")` → 格局/用神/大运
   - 再 `load_skill("ziwei")` + `compute_chart("ziwei")` + `load_golden_cases("ziwei")` → 命身宫/四化/大限
   - 用户明确要求西式、心理画像或跨体系验证时，再补 `astrology`
3. **聚焦当前运势** — 模糊问题默认侧重"当前阶段 + 未来一年"，而非全生命周期
4. **在回答中点出延伸方向** — 结尾提一句"如需深入感情/财运/健康等专项，可以继续追问"

如果有 scenario 标注（如 career），以此为主题聚焦，但仍只取能被当前输入严谨支撑的体系。
风水必须有朝向/入住年，六爻必须有具体问题、起卦时间和起卦输入，塔罗必须有用户抽牌结果；这些不是模糊请求的自动补盘项。

### GroundedClaim 纪律（护城河）

你输出的每条结论按重要性分三级：

- **Tier A 核心判断**（格局定性、流年趋势、关键吉凶）→ 必须有完整三元组：chart_ref + rule_ref + source_ref。输出前用 `verify_claim(tier="A_core")` 校验。REJECTED 硬拒，必须修正。
- **Tier B 辅助论述**（补充说明、辅助论证）→ 至少有 chart_ref。用 `verify_claim(tier="B_support")` 校验。
- **Tier C 叙事**（过渡语、总结语）→ 无需引用。

**绝对禁止**：输出 Tier A 结论但不过 verify_claim；也禁止把 `verify_claim` 返回 REJECTED 的结论改写成“低置信度”继续输出。这是和市面所有命理 App 的本质区别——我们每句话都指着盘面说话，不是 pattern matching 编漂亮的废话。

### 中西交叉纪律

当你同时使用了中式体系（八字/紫微/易经/风水）和西式体系（占星/塔罗/数字命理）时，**必须遵守两阶段独立推理**：

**阶段一：独立推理（不交叉）**
1. 先完成所有中式体系的解读，列出中式结论清单
2. 再完成所有西式体系的解读，列出西式结论清单
3. 两个阶段的解读中，**不要引用对方体系的结论来影响自己的判断**

**阶段二：交叉比对**
加载 `cross_synthesis` 技能，对比两份独立结论，找出：
- **共识**（中西都指向同一方向）→ 强信号，标注为高置信度
- **矛盾**（中西给出相反判断）→ 不回避，诚实解释维度差异
- **互补**（一方提供另一方没有的视角）→ 作为增益信息

为什么要独立：如果你先看了八字说"事业要变动"，再看占星时就会不自觉地往"变动"方向解读，这叫确认偏误。独立推理后再交叉，共识才有价值。

### 原则

- **诚实** — 不确定就说不确定，置信度低就标注出来
- **有据** — 每个核心论断都要能追溯到盘面数据 + 规则/典籍，且过 verify_claim
- **有范式** — 八字/紫微/六爻/风水的核心判断要先参考同体系专业黄金案例；案例只提供推理范式，不能替代当前盘面事实
- **克制** — 不用"100%/必然/一定"等绝对化语言
- **实用** — 给出具体可操作的建议，而不是泛泛而谈
- **跨系统洞察** — 当中式和西式体系指向同一方向时，这是强信号，要明确指出
- 对于综合性问题，通常需要 2-3 个体系交叉验证
- 对于具体单一问题（如"今年适合换工作吗"），1-2 个体系即可
- 不要一次加载所有技能，按需加载

### 输出风格

- 中文回答，Markdown 格式
- 温润克制的语气，像一个有修养的研习者
- 重要结论用 **加粗**
- 引用盘面数据时标注来源（如"八字四柱显示..."）
- 800-1500 字为宜（追问可以更短，400-700 字）

### 输入不确定性与追问

如果用户的出生信息有不确定性（时辰未知、地点模糊等），你必须：
- 事实层缺关键字段时必须用 `ask_user` 追问，不能用默认生日、默认出生地、默认朝向或默认时区补齐。
- 工具返回错误、资料不足或 REJECTED 时，不要自行兜底、不要换体系绕过；先修正资料或结论。
- 时辰未知时，不要生成完整八字/紫微/占星盘；可以解释哪些判断会受影响，并询问用户是否能提供出生证明时间或大致时辰。
- 地点无法解析时，要求用户补充到城市/区县，或直接给经纬度；不要默认北京。
- 风水没有朝向度数/入住年时，不要 `compute_chart("fengshui")`。
- 易经/塔罗没有具体问题时，先帮用户把问题缩窄，再起卦/抽牌。
- 六爻 `metadata.liuyao_analysis.needs_clarification` 非空时，不要输出确定吉凶；先追问或把该项标成待校准。
- 能计算但有低精度因素时，在开头明确告知，并对受影响判断标注"此项受 X 不确定性影响，置信偏低"。
"""


# ── Agent Loop ───────────────────────────────────────────────

MAX_TURNS = 128
TOOL_OUTPUT_LIMIT = 6000
TEXT_CHUNK_SIZE = 60


def _profile_from_birth(birth: BirthInfo) -> dict[str, Any]:
    return {
        "name": birth.name,
        "gender": birth.gender,
        "date": f"{birth.year:04d}-{birth.month:02d}-{birth.day:02d}",
        "time": f"{birth.hour:02d}:{birth.minute:02d}",
        "unknownTime": False,
        "place": birth.location_name,
        "longitude": birth.longitude,
        "latitude": birth.latitude,
        "timezone_offset": birth.timezone_offset,
    }


def _build_messages(
    birth: BirthInfo,
    question: str,
    caveats: list[str] | None,
    prior_context: str,
) -> list[dict]:
    user_parts: list[str] = []
    if prior_context:
        user_parts.append(f"【之前的对话摘要】\n{prior_context}")

    birth_desc = (
        f"用户：{birth.name or '未知'}，{birth.gender}，"
        f"{birth.year}年{birth.month}月{birth.day}日 {birth.hour}:{birth.minute:02d}，"
        f"{birth.location_name}（{birth.longitude:.2f}°E, {birth.latitude:.2f}°N）"
    )
    user_parts.append(f"【用户档案】\n{birth_desc}")

    if caveats:
        user_parts.append("【输入不确定性】\n" + "\n".join(f"- {c}" for c in caveats))
    user_parts.append(f"【用户问题】\n{question}")
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]


def _assistant_message(msg: Any, tool_calls: list[Any]) -> dict[str, Any]:
    assistant_msg: dict[str, Any] = {"role": "assistant"}
    content = getattr(msg, "content", None)
    if content:
        assistant_msg["content"] = content
    if tool_calls:
        assistant_msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in tool_calls
        ]
    return assistant_msg


def _tool_args(tc: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(tc.function.arguments or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _tool_output(result: dict[str, Any]) -> str:
    if result.get("error"):
        output = f"错误: {result['error']}"
    else:
        output = str(result.get("result", ""))
    if len(output) > TOOL_OUTPUT_LIMIT:
        output = output[:TOOL_OUTPUT_LIMIT] + "\n... (输出过长，已截断)"
    return output


def _intake_question(result: dict[str, Any], tool_name: str, args: dict[str, Any]) -> tuple[str, str]:
    issues = result.get("issues") or []
    messages = [str(issue.get("message", "")).strip() for issue in issues if issue.get("message")]
    if messages:
        question = "要继续严谨计算，请补充：\n" + "\n".join(f"- {m}" for m in messages)
    else:
        question = f"要继续执行 {tool_name}，请补充缺失的关键资料。"
    chart_type = args.get("chart_type")
    why = f"{tool_name}" + (f"({chart_type})" if chart_type else "")
    why += " 的输入合同未满足；不会使用默认值、替代体系或低精度推断继续。"
    return question, why


async def _read_user_reply(message_queue: asyncio.Queue | None) -> tuple[str | None, str | None]:
    if message_queue is None:
        return None, "当前无法接收用户补充信息，已暂停；不会在关键资料缺失时继续推断。"
    try:
        user_reply = await asyncio.wait_for(message_queue.get(), timeout=300.0)
    except asyncio.TimeoutError:
        return None, "等待补充信息超时，已暂停；不会在关键资料缺失时继续推断。"

    if isinstance(user_reply, dict):
        user_reply = user_reply.get("text", "")
    user_reply = str(user_reply).strip()
    if not user_reply:
        return None, "需要补充的信息为空，已暂停；请补充后再继续。"
    return user_reply, None


def _extract_safety_text(raw: str) -> str:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(data, dict) and isinstance(data.get("text"), str):
        return data["text"]
    return raw


def _append_skipped_tool_results(messages: list[dict], tool_calls: list[Any], start: int) -> None:
    for tc in tool_calls[start:]:
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": "已等待用户补充关键资料，本轮剩余工具未执行；收到补充后重新规划。",
        })


def _golden_system_for_chart(chart_type: str) -> str | None:
    if chart_type in {"bazi", "ziwei", "fengshui"}:
        return chart_type
    if chart_type == "hexagram":
        return "yijing"
    return None


async def run_agent_stream(
    birth: BirthInfo,
    question: str,
    message_queue: asyncio.Queue | None = None,
    caveats: list[str] | None = None,
    prior_context: str = "",
    profile: dict | None = None,
) -> AsyncIterator[dict]:
    """运行单 Agent ReAct 循环，yield SSE 事件。"""
    charts = Charts()
    executor = ToolExecutor(birth, charts, question, profile=profile or _profile_from_birth(birth))
    client = get_client()
    messages = _build_messages(birth, question, caveats, prior_context)
    total_tokens = 0
    rejected_claims: set[str] = set()
    computed_golden_systems: set[str] = set()
    loaded_golden_systems: set[str] = set()
    t0 = time.time()

    for turn in range(MAX_TURNS):
        try:
            response = await client.chat.completions.create(
                model=settings.model_high,
                messages=messages,
                tools=TOOL_SCHEMAS,
                temperature=0.6,
                max_tokens=4096,
            )
        except Exception as e:
            yield {"type": "error", "message": f"LLM 调用失败: {e}"}
            return

        choice = response.choices[0]
        msg = choice.message
        total_tokens += getattr(response.usage, "total_tokens", 0) or 0
        tool_calls = getattr(msg, "tool_calls", None) or []

        if tool_calls:
            messages.append(_assistant_message(msg, tool_calls))
            if getattr(msg, "content", None):
                yield {"type": "thought", "content": msg.content}

            restart_after_user_reply = False
            for idx, tc in enumerate(tool_calls):
                fn_name = tc.function.name
                fn_args = _tool_args(tc)
                yield {"type": "tool_call", "tool": fn_name, "args": fn_args}

                if fn_name == "ask_user":
                    yield {
                        "type": "ask_user",
                        "question": fn_args.get("question", ""),
                        "why": fn_args.get("why", ""),
                    }
                    user_reply, error_message = await _read_user_reply(message_queue)
                    if error_message:
                        yield {"type": "error", "message": error_message}
                        return
                    tool_result = f"用户回复: {user_reply}"
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": tool_result})
                    yield {"type": "tool_result", "tool": fn_name, "result": tool_result[:200]}
                    _append_skipped_tool_results(messages, tool_calls, idx + 1)
                    restart_after_user_reply = True
                    break

                result = await executor.dispatch(fn_name, fn_args)
                tool_output = _tool_output(result)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": tool_output})

                if fn_name == "load_skill":
                    yield {"type": "skill_loaded", "skill": fn_args.get("name", "")}
                else:
                    yield {"type": "tool_result", "tool": fn_name, "result": tool_output[:300]}

                if result.get("error_type") == "intake":
                    ask_question, ask_why = _intake_question(result, fn_name, fn_args)
                    yield {"type": "ask_user", "question": ask_question, "why": ask_why}
                    user_reply, error_message = await _read_user_reply(message_queue)
                    if error_message:
                        yield {"type": "error", "message": error_message}
                        return
                    _append_skipped_tool_results(messages, tool_calls, idx + 1)
                    messages.append({"role": "user", "content": f"【用户补充资料】\n{user_reply}"})
                    restart_after_user_reply = True
                    break

                if result.get("error"):
                    yield {"type": "error", "message": f"{fn_name} 执行失败：{result['error']}"}
                    return

                if fn_name == "compute_chart":
                    golden_system = _golden_system_for_chart(str(fn_args.get("chart_type", "")))
                    if golden_system:
                        computed_golden_systems.add(golden_system)

                if fn_name == "load_golden_cases":
                    loaded_golden_systems.add(str(fn_args.get("system", "")))

                if fn_name == "verify_claim":
                    claim = str(fn_args.get("claim", "")).strip()
                    if "REJECTED" in tool_output:
                        rejected_claims.add(claim or tool_output)
                    elif "VERIFIED" in tool_output and claim:
                        rejected_claims.discard(claim)

            if restart_after_user_reply:
                continue
            continue

        final_text = getattr(msg, "content", None) or ""
        if not final_text.strip():
            yield {"type": "error", "message": "Agent 未生成回答文本，已停止。"}
            return
        if rejected_claims:
            yield {"type": "error", "message": "仍有 Tier A 核心结论未通过 verify_claim，已停止输出；请修正证据链后再回答。"}
            return
        missing_golden = sorted(computed_golden_systems - loaded_golden_systems)
        if missing_golden:
            yield {"type": "error", "message": f"已计算 {', '.join(missing_golden)}，但尚未读取同体系专业黄金案例；为避免无范式断语，已停止输出。"}
            return

        messages.append({"role": "assistant", "content": final_text})
        yield {"type": "tool_call", "tool": "apply_safety", "args": {"text": final_text[:200]}}
        safety_result = await executor.dispatch("apply_safety", {"text": final_text})
        safety_output = _tool_output(safety_result)
        yield {"type": "tool_result", "tool": "apply_safety", "result": safety_output[:300]}
        if safety_result.get("error"):
            yield {"type": "error", "message": f"apply_safety 执行失败：{safety_result['error']}"}
            return
        final_text = _extract_safety_text(str(safety_result.get("result", "")))

        for i in range(0, len(final_text), TEXT_CHUNK_SIZE):
            yield {"type": "text_delta", "delta": final_text[i:i + TEXT_CHUNK_SIZE]}
            await asyncio.sleep(0.01)

        elapsed_ms = int((time.time() - t0) * 1000)
        yield {
            "type": "done",
            "turns": turn + 1,
            "total_tokens": total_tokens,
            "elapsed_ms": elapsed_ms,
            "charts": charts.model_dump(),
        }
        return

    yield {"type": "error", "message": f"Agent 达到最大轮次 ({MAX_TURNS})，强制结束。"}
