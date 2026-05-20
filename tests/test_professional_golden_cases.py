import json
from datetime import datetime
from pathlib import Path
from typing import Any

from agents.tools import ToolExecutor


def _resolve_json_path(obj: Any, path: str) -> tuple[bool, Any]:
    """解析 JSON path，支持 ``foo.bar[0].baz``。"""
    cur = obj
    for raw_part in path.split("."):
        part = raw_part.strip()
        if not part:
            continue
        while part:
            if part.startswith("["):
                close = part.find("]")
                if close <= 1:
                    return False, None
                index_text = part[1:close].strip()
                if not index_text.isdigit() or not isinstance(cur, list):
                    return False, None
                idx = int(index_text)
                if idx >= len(cur):
                    return False, None
                cur = cur[idx]
                part = part[close + 1:]
                continue
            bracket = part.find("[")
            key = part if bracket == -1 else part[:bracket]
            if key.isdigit() and isinstance(cur, list):
                idx = int(key)
                if idx >= len(cur):
                    return False, None
                cur = cur[idx]
            elif isinstance(cur, dict):
                if key not in cur:
                    return False, None
                cur = cur[key]
            elif hasattr(cur, key):
                cur = getattr(cur, key)
            else:
                return False, None
            if bracket == -1:
                part = ""
            else:
                part = part[bracket:]
    return True, cur
from computation.bazi import compute_bazi
from computation.fengshui import compute_fengshui
from computation.yijing import compute_coin
from computation.ziwei import compute_ziwei
from core.schemas import BirthInfo, Charts


ROOT = Path(__file__).resolve().parent.parent
GOLDEN_PATH = ROOT / "data" / "pro_golden_cases.json"


def _load_cases() -> list[dict[str, Any]]:
    return json.loads(GOLDEN_PATH.read_text("utf-8"))["cases"]


def _birth(data: dict[str, Any]) -> BirthInfo:
    return BirthInfo(**data)


def _chart_for(case: dict[str, Any]) -> Any:
    system = case["system"]
    if system == "bazi":
        return compute_bazi(_birth(case["birth"]), current_year=case.get("current_year", 2026))
    if system == "ziwei":
        return compute_ziwei(_birth(case["birth"]))
    if system == "yijing":
        if case.get("method") != "coin":
            raise AssertionError(f"Unsupported yijing golden method: {case.get('method')}")
        return compute_coin(
            case["question"],
            coin_results=case["coin_results"],
            dt=datetime.fromisoformat(case["divination_time"]),
        )
    if system == "fengshui":
        return compute_fengshui(
            case["facing_degree"],
            _birth(case["birth"]),
            move_in_year=case["move_in_year"],
        )
    raise AssertionError(f"Unsupported golden system: {system}")


def _actual_for_path(chart: Any, path: str) -> Any:
    found, actual = _resolve_json_path(chart.model_dump(), path)
    assert found, f"{path} should exist in golden chart"
    return actual


def _assert_expected(chart: Any, expected: dict[str, Any]) -> None:
    for path, wanted in expected.items():
        assert _actual_for_path(chart, path) == wanted, path


def _frontmatter_system(path: Path) -> str | None:
    lines = path.read_text("utf-8").splitlines()
    assert lines and lines[0].strip() == "---", f"{path} should have frontmatter"
    for line in lines[1:40]:
        stripped = line.strip()
        if stripped == "---":
            return None
        if stripped.startswith("system:"):
            return stripped.split(":", 1)[1].strip().strip("\"'")
    return None


def test_professional_golden_cases_match_manual_chart_facts():
    for case in _load_cases():
        chart = _chart_for(case)
        _assert_expected(chart, case["expected"])


def test_json_path_supports_bracket_indexes_for_agent_refs():
    bazi_case = next(case for case in _load_cases() if case["system"] == "bazi")
    chart = _chart_for(bazi_case)

    assert _actual_for_path(chart, "liu_nian[0].ganzhi") == "丙午"
    assert _actual_for_path(chart, "liu_nian[1].ganzhi") == "丁未"


def test_resolve_json_path_accepts_golden_bracket_paths_with_chart_root():
    bazi_case = next(case for case in _load_cases() if case["system"] == "bazi")
    charts = {"bazi": _chart_for(bazi_case).model_dump()}

    found, actual = _resolve_json_path(charts, "bazi.liu_nian[0].ganzhi")
    assert found
    assert actual == "丙午"


def test_load_golden_cases_returns_same_system_reference_cases():
    bazi_case = next(case for case in _load_cases() if case["system"] == "bazi")
    executor = ToolExecutor(_birth(bazi_case["birth"]), Charts(), bazi_case["question"])

    import asyncio

    result = asyncio.run(executor.dispatch(
        "load_golden_cases",
        {"system": "bazi", "limit": 1},
    ))

    assert "error" not in result
    data = json.loads(result["result"])
    assert len(data["cases"]) == 1
    assert data["cases"][0]["system"] == "bazi"
    assert data["cases"][0]["interpretation_anchors"]
    assert data["cases"][0]["interpretation_anchors"][0]["rule_ref"].startswith("BZ_R_")


def test_load_golden_cases_rejects_system_without_professional_cases():
    bazi_case = next(case for case in _load_cases() if case["system"] == "bazi")
    executor = ToolExecutor(_birth(bazi_case["birth"]), Charts(), bazi_case["question"])

    import asyncio

    result = asyncio.run(executor.dispatch(
        "load_golden_cases",
        {"system": "astrology"},
    ))

    assert "error" in result
    assert "只支持 bazi / ziwei / yijing / fengshui" in result["error"]


def test_interpretation_anchors_have_existing_refs_and_true_chart_refs():
    for case in _load_cases():
        chart = _chart_for(case)
        for anchor in case["interpretation_anchors"]:
            rule_path = ROOT / "knowledge" / "rules" / f"{anchor['rule_ref']}.md"
            source_path = ROOT / "knowledge" / "classics" / f"{anchor['source_ref']}.md"
            assert rule_path.exists()
            assert source_path.exists()
            assert _frontmatter_system(rule_path) == case["system"]
            assert _frontmatter_system(source_path) == case["system"]
            for chart_ref in anchor["chart_refs"]:
                path, expected = chart_ref.split("=", 1)
                actual = _actual_for_path(chart, path)
                if isinstance(actual, bool):
                    expected_value: Any = expected == "True"
                elif isinstance(actual, int):
                    expected_value = int(expected)
                elif isinstance(actual, float):
                    expected_value = float(expected)
                else:
                    expected_value = expected
                assert actual == expected_value, chart_ref
