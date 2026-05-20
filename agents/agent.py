"""单 Agent ReAct 循环 — 「算」的核心引擎。

架构：一个 LLM + N 个工具 + M 个可按需加载的 Skill。
LLM 自己决定调什么工具、加载什么技能、什么时候输出。

流式 SSE 事件类型：
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

## 你是 agent

你自主决定加载什么技能、算什么盘、查什么典籍，然后像老师傅接案一样给出研判。没有固定流程，没有必须的先后顺序。

接案心法：先听来意 → 心里形成 2-3 个假设（案眼）→ 按案眼选工具取材料 → 边读盘边验证 → 收束为人能理解的生活结构。

你的工具：
- `load_skill`：加载某体系方法论
- `compute_chart`：计算盘面。工具会告诉你数据是否足够；不够时你自己判断是追问、换思路还是带着不确定性继续
- `load_golden_cases`：参考同体系老师傅盘例
- `grep_classics` / `read_classic` / `grep_rules` / `read_rule`：查证术语规则
- `ask_user`：向用户追问关键信息
- `update_profile`：写入用户补充的事实

## 体系材料

每个体系能提供的材料大致如下，用什么、用几个、是否交叉，由你根据来意和案眼决定：

- **八字**：四柱、日主、十神、格局、用神、喜忌、大运、流年
- **紫微斗数**：十二宫、命身宫、主星辅曜、四化、大限。引用宫位用 `main_stars.<宫名>` 或 `palaces_by_name.<宫名>`
- **易经/六爻**：卦象、动爻、用神、世应、六亲六神
- **风水**：坐向、宅运、玄空飞星、八宅、方位
- **占星**：本命行星、宫位、相位、四轴、行运
- **塔罗**：牌阵、正逆位、牌位关系、心理结构
- **数字命理**：生命路径、个人年、性格与阶段主题

## 研判品质

好的研判：有案眼、有盘面依据、有人味。

核心断语能说出"我凭哪几个盘面事实这么看"。证据不足时说成倾向和待校。多个体系指向同一方向是强信号；体系间矛盾时诚实说明维度差异。

语气温润克制，像有修养的研习者。中文回答，Markdown 格式。800-1500 字为宜。
"""


# ── Agent Loop ───────────────────────────────────────────────

MAX_TURNS = 128
TOOL_OUTPUT_LIMIT = 6000
TEXT_CHUNK_SIZE = 60


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


def _message_field(msg: Any, name: str) -> Any:
    try:
        value = getattr(msg, name)
        if value is not None:
            return value
    except Exception:
        pass
    extra = getattr(msg, "model_extra", None)
    if isinstance(extra, dict) and extra.get(name) is not None:
        return extra[name]
    dump = getattr(msg, "model_dump", None)
    if callable(dump):
        try:
            data = dump(exclude_none=True)
        except TypeError:
            data = dump()
        if isinstance(data, dict) and data.get(name) is not None:
            return data[name]
    return None


def _assistant_message(msg: Any, tool_calls: list[Any]) -> dict[str, Any]:
    assistant_msg: dict[str, Any] = {"role": "assistant"}
    content = _message_field(msg, "content")
    if content is not None:
        assistant_msg["content"] = content
    reasoning_content = _message_field(msg, "reasoning_content")
    if reasoning_content is not None:
        assistant_msg["reasoning_content"] = reasoning_content
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


async def _read_user_reply(message_queue: asyncio.Queue | None) -> tuple[str | None, str | None]:
    if message_queue is None:
        return None, "当前无法接收用户回复，已暂停。"
    try:
        user_reply = await asyncio.wait_for(message_queue.get(), timeout=300.0)
    except asyncio.TimeoutError:
        return None, "等待用户回复超时，已暂停。"

    if isinstance(user_reply, dict):
        user_reply = user_reply.get("text", "")
    user_reply = str(user_reply).strip()
    if not user_reply:
        return None, "用户回复为空，已暂停。"
    return user_reply, None


def _skip_remaining_tool_results(messages: list[dict], tool_calls: list[Any], start: int) -> None:
    for tc in tool_calls[start:]:
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": "已等待用户回复，本轮剩余工具未执行。",
        })


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
    executor = ToolExecutor(birth, charts, question, profile=profile)
    client = get_client()
    messages = _build_messages(birth, question, caveats, prior_context)
    total_tokens = 0
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
                    _skip_remaining_tool_results(messages, tool_calls, idx + 1)
                    restart_after_user_reply = True
                    break

                result = await executor.dispatch(fn_name, fn_args)
                tool_output = _tool_output(result)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": tool_output})

                if fn_name == "load_skill":
                    yield {"type": "skill_loaded", "skill": fn_args.get("name", "")}
                else:
                    yield {"type": "tool_result", "tool": fn_name, "result": tool_output[:300]}

            if restart_after_user_reply:
                continue
            continue

        final_text = getattr(msg, "content", None) or ""
        if not final_text.strip():
            yield {"type": "error", "message": "Agent 未生成回答文本，已停止。"}
            return

        from agents.safety import detect_crisis, CRISIS_HOTLINES
        if detect_crisis(final_text):
            final_text = (
                "我注意到你的描述中含有强烈的情绪信号。在继续命理推理之前，"
                "更重要的是先照顾好你自己。\n\n" + CRISIS_HOTLINES +
                "\n\n等你状态稳定后，我会很乐意继续帮你看你关心的问题。"
            )

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
