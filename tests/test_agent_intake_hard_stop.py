import asyncio
from types import SimpleNamespace

import pytest

from agents.agent import run_agent_stream
from agents.agent import SYSTEM_PROMPT
from agents.tools import ToolExecutor
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

    async def create(self, **_kwargs):
        if not self.choices:
            raise AssertionError("Fake LLM received more calls than expected")
        return SimpleNamespace(choices=[self.choices.pop(0)], usage=SimpleNamespace(total_tokens=1))


class _FakeClient:
    def __init__(self, choices):
        self.chat = SimpleNamespace(completions=_FakeCompletions(choices))


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
    assert "不会在关键资料缺失时继续推断" in events[-1]["message"]


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
    assert "补充的信息为空" in events[-1]["message"]


@pytest.mark.asyncio
async def test_agent_intake_error_asks_user_and_does_not_continue_without_channel(monkeypatch):
    choice = _FakeChoice(
        tool_calls=[
            _tool_call("call_feng", "compute_chart", '{"chart_type":"fengshui"}')
        ]
    )
    monkeypatch.setattr("agents.agent.get_client", lambda: _FakeClient([choice]))

    events = []
    async for event in run_agent_stream(_birth(), "看看家里风水", message_queue=None):
        events.append(event)
        if event["type"] == "error":
            break

    assert any(event["type"] == "ask_user" and "房屋朝向度数" in event["question"] for event in events)
    assert events[-1]["type"] == "error"
    assert "不会在关键资料缺失时继续推断" in events[-1]["message"]


@pytest.mark.asyncio
async def test_agent_blocks_final_text_after_rejected_tier_a_claim(monkeypatch):
    rejected_then_final = [
        _FakeChoice(
            tool_calls=[
                _tool_call(
                    "call_verify",
                    "verify_claim",
                    (
                        '{"claim":"这是核心判断",'
                        '"chart_ref":"bazi.day_master=甲",'
                        '"rule_ref":"none",'
                        '"source_ref":"none",'
                        '"tier":"A_core"}'
                    ),
                )
            ]
        ),
        _FakeChoice(content="这是不该直接输出的最终回答。"),
    ]
    monkeypatch.setattr("agents.agent.get_client", lambda: _FakeClient(rejected_then_final))

    events = []
    async for event in run_agent_stream(_birth(), "看看命", message_queue=None):
        events.append(event)
        if event["type"] in {"error", "done"}:
            break

    assert any(event["type"] == "tool_result" and "REJECTED" in event.get("result", "") for event in events)
    assert events[-1]["type"] == "error"
    assert "未通过 verify_claim" in events[-1]["message"]
    assert not any(event["type"] == "text_delta" for event in events)


@pytest.mark.asyncio
async def test_agent_blocks_final_after_chinese_chart_without_golden_cases(monkeypatch):
    choices = [
        _FakeChoice(
            tool_calls=[
                _tool_call("call_chart", "compute_chart", '{"chart_type":"bazi"}')
            ]
        ),
        _FakeChoice(
            tool_calls=[
                _tool_call(
                    "call_verify",
                    "verify_claim",
                    (
                        '{"claim":"2026 丙午流年喜用得力",'
                        '"chart_ref":"bazi.liu_nian[0].ganzhi=丙午; bazi.metadata.event_timing.liu_nian[0].preference_label=喜用得力",'
                        '"rule_ref":"BZ_R_0081",'
                        '"source_ref":"smtonghui_v6_p089",'
                        '"tier":"A_core"}'
                    ),
                )
            ]
        ),
        _FakeChoice(content="最终回答不该输出。"),
    ]
    monkeypatch.setattr("agents.agent.get_client", lambda: _FakeClient(choices))

    events = []
    async for event in run_agent_stream(_birth(), "看看命", message_queue=None):
        events.append(event)
        if event["type"] in {"error", "done"}:
            break

    assert events[-1]["type"] == "error"
    assert "尚未读取同体系专业黄金案例" in events[-1]["message"]
    assert not any(event["type"] == "text_delta" for event in events)


@pytest.mark.asyncio
async def test_agent_allows_final_after_chinese_chart_with_golden_cases(monkeypatch):
    choices = [
        _FakeChoice(
            tool_calls=[
                _tool_call("call_chart", "compute_chart", '{"chart_type":"bazi"}'),
                _tool_call("call_golden", "load_golden_cases", '{"system":"bazi","limit":1}'),
            ]
        ),
        _FakeChoice(
            tool_calls=[
                _tool_call(
                    "call_verify",
                    "verify_claim",
                    (
                        '{"claim":"2026 丙午流年喜用得力",'
                        '"chart_ref":"bazi.liu_nian[0].ganzhi=丙午; bazi.metadata.event_timing.liu_nian[0].preference_label=喜用得力",'
                        '"rule_ref":"BZ_R_0081",'
                        '"source_ref":"smtonghui_v6_p089",'
                        '"tier":"A_core"}'
                    ),
                )
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
async def test_agent_applies_safety_before_streaming_final(monkeypatch):
    monkeypatch.setattr("agents.agent.get_client", lambda: _FakeClient([_FakeChoice(content="这件事一定会成功。")]))

    chunks = []
    events = []
    async for event in run_agent_stream(_birth(), "看看事业", message_queue=None):
        events.append(event)
        if event["type"] == "text_delta":
            chunks.append(event["delta"])
        if event["type"] == "done":
            break

    assert any(event["type"] == "tool_call" and event["tool"] == "apply_safety" for event in events)
    final_text = "".join(chunks)
    assert "一定会" not in final_text
    assert "倾向于" in final_text
    assert "仅供参考" in final_text


@pytest.mark.asyncio
async def test_verify_claim_rejects_missing_tier_a_refs():
    executor = ToolExecutor(_birth(), SimpleNamespace(model_dump=lambda: {"bazi": {"day_master": "甲"}}))
    result = await executor.dispatch(
        "verify_claim",
        {
            "claim": "日主为甲",
            "chart_ref": "bazi.day_master=甲",
            "rule_ref": "none",
            "source_ref": "none",
            "tier": "A_core",
        },
    )

    assert "error" not in result
    assert "REJECTED" in result["result"]
    assert "缺少 rule_ref" in result["result"]
    assert "缺少 source_ref" in result["result"]


@pytest.mark.asyncio
async def test_grep_rules_keeps_system_filter_strict():
    executor = ToolExecutor(_birth(), SimpleNamespace(model_dump=lambda: {}))
    result = await executor.dispatch("grep_rules", {"pattern": "七杀", "system": "ziwei"})

    assert "error" not in result
    assert "BZ_R_0011" not in result["result"]


@pytest.mark.asyncio
async def test_verify_claim_rejects_cross_system_rule_refs():
    executor = ToolExecutor(_birth(), SimpleNamespace(model_dump=lambda: {"bazi": {"day_master": "丁"}}))
    result = await executor.dispatch(
        "verify_claim",
        {
            "claim": "丁火日主按天相入命判断",
            "chart_ref": "bazi.day_master=丁",
            "rule_ref": "ZW_R_0080",
            "source_ref": "ziwei_quanshu_p157",
            "tier": "A_core",
        },
    )

    assert "error" not in result
    assert "REJECTED" in result["result"]
    assert "RULE_SYSTEM_MISMATCH" in result["result"]
    assert "SOURCE_SYSTEM_MISMATCH" in result["result"]


@pytest.mark.asyncio
async def test_verify_claim_accepts_multiple_same_system_chart_refs():
    executor = ToolExecutor(
        _birth(),
        SimpleNamespace(model_dump=lambda: {
            "bazi": {
                "day_master": "丁",
                "liu_nian": [{"ganzhi": "丙午"}],
            }
        }),
    )
    result = await executor.dispatch(
        "verify_claim",
        {
            "claim": "丁火日主逢丙午流年火势得力",
            "chart_ref": "bazi.day_master=丁; bazi.liu_nian[0].ganzhi=丙午",
            "rule_ref": "BZ_R_0081",
            "source_ref": "smtonghui_v6_p089",
            "tier": "A_core",
        },
    )

    assert "error" not in result
    assert "VERIFIED" in result["result"]
    assert "bazi.day_master=丁" in result["result"]
    assert "bazi.liu_nian[0].ganzhi=丙午" in result["result"]


@pytest.mark.asyncio
async def test_verify_claim_rejects_mixed_chart_system_refs():
    executor = ToolExecutor(
        _birth(),
        SimpleNamespace(model_dump=lambda: {
            "bazi": {"day_master": "丁"},
            "ziwei": {"life_palace": "命宫"},
        }),
    )
    result = await executor.dispatch(
        "verify_claim",
        {
            "claim": "混合体系一句断语",
            "chart_ref": "bazi.day_master=丁; ziwei.life_palace=命宫",
            "rule_ref": "BZ_R_0081",
            "source_ref": "smtonghui_v6_p089",
            "tier": "A_core",
        },
    )

    assert "error" not in result
    assert "REJECTED" in result["result"]
    assert "CHART_SYSTEM_MISMATCH" in result["result"]


def test_system_prompt_requires_golden_cases_for_core_chinese_systems():
    assert "load_golden_cases(system=...)" in SYSTEM_PROMPT
    assert 'load_golden_cases("bazi")' in SYSTEM_PROMPT
    assert 'load_golden_cases("ziwei")' in SYSTEM_PROMPT
    assert "案例只提供推理范式，不能替代当前盘面事实" in SYSTEM_PROMPT
