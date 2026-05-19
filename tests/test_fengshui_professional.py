import pytest

from core.schemas import BirthInfo
from computation.fengshui import compute_fengshui


def _birth(**overrides):
    data = dict(
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
        use_true_solar_time=False,
    )
    data.update(overrides)
    return BirthInfo(**data)


def test_fengshui_center_nine_degrees_uses_xia_gua():
    chart = compute_fengshui(195.0, _birth(), move_in_year=2024)

    assert chart.period == 9
    assert chart.metadata["period_range"] == "2024-2043 / 2204-2223"
    assert chart.metadata["pan_method"] == "下卦"
    assert chart.metadata["facing_degree_detail"]["shan"] == "丁"
    assert chart.metadata["facing_degree_detail"]["zone"] == "xia_gua"
    assert chart.metadata["flying_trace"]["xiang"]["seed_used"] == chart.metadata["flying_trace"]["xiang"]["yun_star_at_position"]
    assert chart.metadata["palace_priorities"]["wealth_or_opening_priority"]
    assert any(q["field"] == "floor_plan" for q in chart.metadata["site_questions"])


def test_fengshui_side_three_degrees_uses_ti_gua():
    chart = compute_fengshui(200.0, _birth(), move_in_year=2024)

    assert chart.metadata["pan_method"] == "替卦"
    assert chart.metadata["ti_gua_school"] == "shen_shi"
    assert chart.metadata["facing_degree_detail"]["shan"] == "丁"
    assert chart.metadata["facing_degree_detail"]["zone"] == "ti_gua"
    assert chart.metadata["flying_trace"]["xiang"]["yun_star_at_position"] == 4
    assert chart.metadata["flying_trace"]["xiang"]["same_yuan_shan"] == "巳"
    assert chart.metadata["flying_trace"]["xiang"]["seed_used"] == 6
    assert chart.metadata["flying_trace"]["xiang"]["replaced"] is True
    assert any(q["field"] == "degree_recheck" for q in chart.metadata["site_questions"])


def test_fengshui_rejects_boundary_degrees():
    with pytest.raises(ValueError, match="交界"):
        compute_fengshui(187.5, _birth(), move_in_year=2024)
    with pytest.raises(ValueError, match="交界"):
        compute_fengshui(199.5, _birth(), move_in_year=2024)
