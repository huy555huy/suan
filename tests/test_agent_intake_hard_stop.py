import asyncio
from types import SimpleNamespace

import pytest

from agents.agent import SYSTEM_PROMPT, run_agent_stream
from agents.tools import TOOL_SCHEMAS, ToolExecutor
from core.schemas import Charts
from core.schemas import BirthInfo


def _tool_call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(
            name=name,
            arguments=arguments,
        ),
    )


class _FakeChoice:
    def __init__(self, content=None, tool_calls=None):
        self.message = SimpleNamespace(
            content=content,
            tool_calls=tool_calls,
        )


class _FakeCompletions:
    def __init__(self, choices):
        self.choices = list(choices)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.choices:
            raise AssertionError("Fake LLM received more calls than expected")
        return SimpleNamespace(choices=[self.choices.pop(0)], usage=SimpleNamespace(total_tokens=1))


class _FakeClient:
    def __init__(self, choices):
        self.completions = _FakeCompletions(choices)
        self.chat = SimpleNamespace(completions=self.completions)


def _ask_choice():
    return _FakeChoice(
        tool_calls=[
            _tool_call(
                "call_ask",
                "ask_user",
                '{"question":"请补充出生时辰","why":"完整八字需要时柱"}',
            )
        ]
    )


def _chart_choice_with_reasoning():
    choice = _FakeChoice(
        tool_calls=[
            _tool_call("call_chart", "compute_chart", '{"chart_type":"bazi"}')
        ]
    )
    choice.message.reasoning_content = "先取八字盘面。"
    return choice


def _birth() -> BirthInfo:
    return BirthInfo(
        gender="female",
        year=1991,
        month=8,
        day=15,
        hour=14,
        minute=30,
        location_name="杭州",
        longitude=120.1551,
        latitude=30.2741,
        timezone_offset=8.0,
        use_true_solar_time=True,
    )


# ── ask_user infrastructure tests ──────────────────────────────

@pytest.mark.asyncio
async def test_agent_stops_when_ask_user_has_no_input_channel(monkeypatch):
    monkeypatch.setattr("agents.agent.get_client", lambda: _FakeClient([_ask_choice()]))

    events = []
    async for event in run_agent_stream(_birth(), "看看命", message_queue=None):
        events.append(event)
        if event["type"] == "error":
            break

    assert any(event["type"] == "ask_user" for event in events)
    assert events[-1]["type"] == "error"
    assert "无法接收用户回复" in events[-1]["message"]


@pytest.mark.asyncio
async def test_agent_stops_when_ask_user_reply_is_blank(monkeypatch):
    monkeypatch.setattr("agents.agent.get_client", lambda: _FakeClient([_ask_choice()]))
    queue = asyncio.Queue()
    await queue.put({"text": "   "})

    events = []
    async for event in run_agent_stream(_birth(), "看看命", message_queue=queue):
        events.append(event)
        if event["type"] == "error":
            break

    assert events[-1]["type"] == "error"
    assert "用户回复为空" in events[-1]["message"]


# ── intake errors flow back to agent as normal tool results ────

@pytest.mark.asyncio
async def test_intake_error_returned_as_normal_tool_result(monkeypatch):
    """Intake errors are regular tool results — agent decides what to do next."""
    choices = [
        _FakeChoice(
            tool_calls=[
                _tool_call("call_feng", "compute_chart", '{"chart_type":"fengshui"}')
            ]
        ),
        _FakeChoice(content="需要补充房屋朝向度数和入住年才能排风水盘，请提供。"),
    ]
    monkeypatch.setattr("agents.agent.get_client", lambda: _FakeClient(choices))

    events = []
    async for event in run_agent_stream(_birth(), "看看家里风水", message_queue=None):
        events.append(event)
        if event["type"] in {"error", "done"}:
            break

    assert events[-1]["type"] == "done"
    tool_results = [e for e in events if e["type"] == "tool_result"]
    assert any("朝向" in e.get("result", "") for e in tool_results)
    assert not any(e["type"] == "ask_user" for e in events)


# ── chart computation and golden cases ─────────────────────────

@pytest.mark.asyncio
async def test_agent_allows_final_after_chinese_chart_without_runtime_golden_case_gate(monkeypatch):
    choices = [
        _FakeChoice(
            tool_calls=[
                _tool_call("call_chart", "compute_chart", '{"chart_type":"bazi"}')
            ]
        ),
        _FakeChoice(content="八字已经排出，先按盘面给出可继续校盘的研判。"),
    ]
    monkeypatch.setattr("agents.agent.get_client", lambda: _FakeClient(choices))

    events = []
    async for event in run_agent_stream(_birth(), "看看命", message_queue=None):
        events.append(event)
        if event["type"] in {"error", "done"}:
            break

    assert events[-1]["type"] == "done"
    assert any(event["type"] == "text_delta" for event in events)


@pytest.mark.asyncio
async def test_agent_preserves_reasoning_content_for_thinking_models(monkeypatch):
    fake_client = _FakeClient([
        _chart_choice_with_reasoning(),
        _FakeChoice(content="八字盘已排出。"),
    ])
    monkeypatch.setattr("agents.agent.get_client", lambda: fake_client)

    events = []
    async for event in run_agent_stream(_birth(), "看看命", message_queue=None):
        events.append(event)
        if event["type"] in {"error", "done"}:
            break

    assert events[-1]["type"] == "done"
    second_messages = fake_client.completions.calls[1]["messages"]
    assistant_messages = [m for m in second_messages if m["role"] == "assistant"]
    assert assistant_messages
    assert assistant_messages[-1]["reasoning_content"] == "先取八字盘面。"


@pytest.mark.asyncio
async def test_agent_allows_final_after_chinese_chart_with_golden_cases(monkeypatch):
    choices = [
        _FakeChoice(
            tool_calls=[
                _tool_call("call_chart", "compute_chart", '{"chart_type":"bazi"}'),
                _tool_call("call_golden", "load_golden_cases", '{"system":"bazi","limit":1}'),
            ]
        ),
        _FakeChoice(content="八字显示日主为丁，先按丁火日主作基础判断。"),
    ]
    monkeypatch.setattr("agents.agent.get_client", lambda: _FakeClient(choices))

    events = []
    async for event in run_agent_stream(_birth(), "看看命", message_queue=None):
        events.append(event)
        if event["type"] in {"error", "done"}:
            break

    assert events[-1]["type"] == "done"
    assert any(event["type"] == "tool_call" and event["tool"] == "load_golden_cases" for event in events)
    assert any(event["type"] == "text_delta" for event in events)


@pytest.mark.asyncio
async def test_agent_allows_multiple_chinese_systems_after_golden_cases_without_judgement_gate(monkeypatch):
    choices = [
        _FakeChoice(
            tool_calls=[
                _tool_call("call_bazi", "compute_chart", '{"chart_type":"bazi"}'),
                _tool_call("call_ziwei", "compute_chart", '{"chart_type":"ziwei"}'),
                _tool_call("call_golden_bazi", "load_golden_cases", '{"system":"bazi","limit":1}'),
                _tool_call("call_golden_ziwei", "load_golden_cases", '{"system":"ziwei","limit":1}'),
            ]
        ),
        _FakeChoice(content="以八字定格局，以紫微看宫位呼应，先给出可校盘的研判。"),
    ]
    monkeypatch.setattr("agents.agent.get_client", lambda: _FakeClient(choices))

    events = []
    async for event in run_agent_stream(_birth(), "看看事业", message_queue=None):
        events.append(event)
        if event["type"] in {"error", "done"}:
            break

    assert events[-1]["type"] == "done"
    assert any(event["type"] == "text_delta" for event in events)


# ── output integrity ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_final_text_streams_without_modification(monkeypatch):
    """Agent output streams directly — no regex replacement, no forced disclaimer."""
    monkeypatch.setattr("agents.agent.get_client", lambda: _FakeClient([
        _FakeChoice(content="这件事一定会成功。")
    ]))

    chunks = []
    async for event in run_agent_stream(_birth(), "看看事业", message_queue=None):
        if event["type"] == "text_delta":
            chunks.append(event["delta"])
        if event["type"] == "done":
            break

    final_text = "".join(chunks)
    assert "一定会" in final_text
    assert "仅供参考" not in final_text


@pytest.mark.asyncio
async def test_crisis_detection_replaces_output(monkeypatch):
    """Crisis keywords in final output are replaced with hotline info."""
    monkeypatch.setattr("agents.agent.get_client", lambda: _FakeClient([
        _FakeChoice(content="从命盘来看活着没意思的感觉可以理解。")
    ]))

    chunks = []
    async for event in run_agent_stream(_birth(), "最近很难受", message_queue=None):
        if event["type"] == "text_delta":
            chunks.append(event["delta"])
        if event["type"] in {"done", "error"}:
            break

    final_text = "".join(chunks)
    assert "活着没意思" not in final_text
    assert "心理援助" in final_text


# ── tool & schema assertions ───────────────────────────────────

@pytest.mark.asyncio
async def test_grep_rules_keeps_system_filter_strict():
    executor = ToolExecutor(_birth(), SimpleNamespace(model_dump=lambda: {}))
    result = await executor.dispatch("grep_rules", {"pattern": "七杀", "system": "ziwei"})

    assert "error" not in result
    assert "BZ_R_0011" not in result["result"]


@pytest.mark.asyncio
async def test_compute_ziwei_returns_semantic_view_to_agent():
    executor = ToolExecutor(_birth(), Charts())
    result = await executor.dispatch("compute_chart", {"chart_type": "ziwei"})

    assert "error" not in result
    assert '"palaces_by_name"' in result["result"]
    assert '"main_stars"' in result["result"]
    assert '"palaces":' not in result["result"]


def test_public_tools_do_not_expose_mechanical_judgement_or_safety_tools():
    tool_names = {schema["function"]["name"] for schema in TOOL_SCHEMAS}
    removed_tool = "verify_" + "claim"

    assert removed_tool not in tool_names
    assert "apply_safety" not in tool_names
    assert "verify_chart_ref" not in tool_names
    assert "read_chart_ref" not in tool_names


@pytest.mark.asyncio
async def test_dispatch_rejects_removed_mechanical_judgement_tool():
    executor = ToolExecutor(_birth(), SimpleNamespace(model_dump=lambda: {"bazi": {"day_master": "甲"}}))
    removed_tool = "verify_" + "claim"
    result = await executor.dispatch(removed_tool, {"claim": "日主为甲"})

    assert result["error"] == f"未知工具: {removed_tool}"


# ── system prompt assertions ───────────────────────────────────

def test_system_prompt_is_agent_oriented():
    assert "agent" in SYSTEM_PROMPT
    assert "自主决定" in SYSTEM_PROMPT
    assert "案眼" in SYSTEM_PROMPT
    assert "老师傅" in SYSTEM_PROMPT


def test_system_prompt_lists_tools_and_systems():
    assert "load_skill" in SYSTEM_PROMPT
    assert "compute_chart" in SYSTEM_PROMPT
    assert "ask_user" in SYSTEM_PROMPT
    assert "八字" in SYSTEM_PROMPT
    assert "紫微斗数" in SYSTEM_PROMPT


def test_system_prompt_has_no_prohibition_lists():
    old_prohibitions = [
        "不做冷读式",
        "不要默认北京",
        "不要生成完整",
        "不要堆材料",
        "不要把数组下标",
        "不要用默认值",
        "不能由系统随机",
        "必须用 `ask_user`",
    ]
    for phrase in old_prohibitions:
        assert phrase not in SYSTEM_PROMPT, f"Found old prohibition: {phrase}"


def test_system_prompt_no_longer_requires_mechanical_judgement_verification():
    forbidden = [
        "verify_" + "claim",
        "Grounded" + "Claim",
        "Tier A",
        "Tier B",
        "REJECTED",
        "停止输出",
        "verify_chart_ref",
        "read_chart_ref",
        "事实核盘纪律",
    ]
    for text in forbidden:
        assert text not in SYSTEM_PROMPT
