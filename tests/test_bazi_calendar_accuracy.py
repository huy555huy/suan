from datetime import datetime

from core.schemas import BirthInfo
from computation.bazi import compute_bazi
from computation.calendar import get_four_pillars
from computation.ziwei import compute_ziwei


def _pillars_at(year, month, day, hour, minute):
    four = get_four_pillars(
        datetime(year, month, day, hour, minute),
        longitude=120.0,
        tz_offset=8.0,
        use_true_solar_time=False,
    )
    return {
        pos: four[f"{pos}_pillar"]["stem"] + four[f"{pos}_pillar"]["branch"]
        for pos in ("year", "month", "day", "hour")
    }


def test_modern_chart_matches_reference_case():
    assert _pillars_at(1991, 8, 15, 14, 30) == {
        "year": "辛未",
        "month": "丙申",
        "day": "丁巳",
        "hour": "丁未",
    }


def test_january_uses_previous_solar_term_year_and_local_day():
    assert _pillars_at(2000, 1, 1, 0, 0) == {
        "year": "己卯",
        "month": "丙子",
        "day": "戊午",
        "hour": "壬子",
    }


def test_li_chun_boundary_uses_exact_term_time():
    before = _pillars_at(2024, 2, 4, 16, 26)
    after = _pillars_at(2024, 2, 4, 16, 28)

    assert before["year"] == "癸卯"
    assert before["month"] == "乙丑"
    assert after["year"] == "甲辰"
    assert after["month"] == "丙寅"


def test_zi_hour_counts_as_next_day_for_default_school():
    assert _pillars_at(2023, 10, 17, 22, 30) == {
        "year": "癸卯",
        "month": "壬戌",
        "day": "戊申",
        "hour": "癸亥",
    }
    assert _pillars_at(2023, 10, 17, 23, 30) == {
        "year": "癸卯",
        "month": "壬戌",
        "day": "己酉",
        "hour": "甲子",
    }


def test_da_yun_start_uses_precise_jie_distance_forward():
    chart = compute_bazi(
        BirthInfo(
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
    )

    assert chart.metadata["da_yun_start"]["forward"] is True
    assert chart.metadata["da_yun_start"]["target_term"] == "白露"
    assert chart.metadata["da_yun_start"]["start_date"] == "1999-07-30T08:30:00"
    assert chart.da_yun[0]["ganzhi"] == "丁酉"
    assert chart.da_yun[0]["start_date"] == "1999-07-30T08:30:00"


def test_da_yun_start_uses_precise_jie_distance_reverse():
    chart = compute_bazi(
        BirthInfo(
            gender="male",
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
    )

    assert chart.metadata["da_yun_start"]["forward"] is False
    assert chart.metadata["da_yun_start"]["target_term"] == "立秋"
    assert chart.metadata["da_yun_start"]["start_date"] == "1994-01-14T00:30:00"
    assert chart.da_yun[0]["ganzhi"] == "乙未"
    assert chart.da_yun[0]["start_date"] == "1994-01-14T00:30:00"


def test_bazi_rejects_unknown_gender_for_da_yun_direction():
    birth = BirthInfo(
        gender="other",
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

    import pytest

    with pytest.raises(ValueError, match="大运顺逆需要明确男/女"):
        compute_bazi(birth)


def test_ziwei_lunar_date_uses_lunar_python():
    chart = compute_ziwei(
        BirthInfo(
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
    )

    assert chart.metadata["lunar_year_used"] == 1991
    assert chart.metadata["lunar_month_used"] == 7
    assert chart.metadata["lunar_day_used"] == 6
    assert chart.metadata["lunar_is_leap_month"] is False
