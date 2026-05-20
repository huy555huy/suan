import pytest

from core.schemas import BirthInfo
from computation.ziwei import compute_ziwei


def _birth(**overrides):
    data = dict(
        gender="female",
        year=1991,
        month=8,
        day=15,
        hour=14,
        minute=30,
        location_name="杭州",
        longitude=120.0,
        latitude=30.0,
        timezone_offset=8.0,
        use_true_solar_time=False,
    )
    data.update(overrides)
    return BirthInfo(**data)


def test_ziwei_uses_iztro_reference_chart():
    chart = compute_ziwei(_birth())

    assert chart.school == "iztro"
    assert chart.metadata["engine"] == "iztro-py"
    assert chart.metadata["raw_lunar_date"] == {
        "year": 1991,
        "month": 7,
        "day": 6,
        "is_leap_month": False,
    }
    assert chart.five_element_bureau == "土五局"
    assert chart.life_palace == "命宫"
    assert chart.body_palace == "福德宫"
    assert chart.metadata["soul_palace_branch"] == "丑"
    assert chart.metadata["body_palace_branch"] == "卯"
    assert chart.metadata["time_index"] == 7
    assert chart.metadata["time"] == "未时"
    assert chart.main_stars["命宫"] == ["天相"]
    assert chart.main_stars["福德宫"] == ["武曲", "七杀"]
    assert chart.main_stars["官禄宫"] == []
    assert chart.palaces_by_name["财帛宫"]["stars"] == ["天府"]
    assert chart.palaces_by_name["官禄宫"]["stars"] == []
    assert chart.si_hua == {
        "化忌": "文昌",
        "化权": "太阳",
        "化科": "文曲",
        "化禄": "巨门",
    }
    assert "life_palace" in chart.metadata["focus"]
    assert "career" in chart.metadata["focus"]["domains"]
    assert chart.metadata["focus"]["life_palace"]["major_stars"]
    assert any(q["field"] == "major_events" for q in chart.metadata["calibration_questions"])


def test_ziwei_rejects_unknown_gender_for_decadal_direction():
    with pytest.raises(ValueError, match="需要明确男/女"):
        compute_ziwei(_birth(gender="other"))


def test_ziwei_true_solar_time_changes_effective_datetime():
    chart = compute_ziwei(_birth(longitude=87.6, use_true_solar_time=True))

    assert chart.metadata["use_true_solar_time"] is True
    assert chart.metadata["effective_datetime"] != chart.metadata["input_datetime"]
