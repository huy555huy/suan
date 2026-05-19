from core.schemas import BirthInfo
from computation.bazi import compute_bazi


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


def test_bazi_exposes_event_timing_and_calibration_questions():
    chart = compute_bazi(_birth(), current_year=2026)

    assert chart.metadata["chart_interactions"]
    assert chart.metadata["event_timing"]["current_da_yun"]["ganzhi"] == "己亥"
    assert chart.metadata["event_timing"]["current_da_yun"]["branch_triggers"]
    first_year = chart.metadata["event_timing"]["liu_nian"][0]
    assert first_year["year"] == 2026
    assert first_year["preference_label"]
    assert "branch_triggers" in first_year
    assert any(q["field"] == "major_events" for q in chart.metadata["calibration_questions"])


def test_bazi_branch_triggers_expose_ten_god_preference_and_domain_hints():
    chart = compute_bazi(_birth(), current_year=2026)
    current_triggers = chart.metadata["event_timing"]["current_da_yun"]["branch_triggers"]
    day_trigger = next(t for t in current_triggers if t["target"] == "day")

    assert day_trigger["target_ten_god"] == "劫财"
    assert day_trigger["target_main_hidden"] == "丙"
    assert day_trigger["target_branch_hidden_stems"] == ["丙", "戊", "庚"]
    assert day_trigger["target_branch_preference"] == "favorable"
    assert day_trigger["target_is_favorable"] is True
    assert "亲密关系" in day_trigger["domain_hint"]
    assert "身体节奏" in day_trigger["domain_hint"]

    first_year_trigger = chart.metadata["event_timing"]["liu_nian"][0]["branch_triggers"][1]
    assert first_year_trigger["target"] == "hour"
    assert first_year_trigger["target_ten_god"] == "食神"
    assert "长期规划" in first_year_trigger["domain_hint"]


def test_bazi_event_timing_exposes_neutral_stem_and_branch_relations():
    chart = compute_bazi(_birth(), current_year=2026)
    first_year = chart.metadata["event_timing"]["liu_nian"][0]

    stem_trigger = first_year["stem_triggers"][0]
    assert stem_trigger["target"] == "year"
    assert stem_trigger["target_stem"] == "辛"
    assert stem_trigger["target_ten_god"] == "偏财"
    assert stem_trigger["interactions"] == ["合水", "丙克辛"]
    assert stem_trigger["relation_types"] == ["天干五合", "天干相克"]
    assert stem_trigger["requires_context"] is True

    assert first_year["branch_triggers"][0]["interactions"] == ["六合土"]
    assert first_year["branch_triggers"][0]["relation_types"] == ["地支六合"]
    assert first_year["branch_triggers"][0]["requires_context"] is True


def test_bazi_pillars_expose_ten_gods_for_agent_chart_refs():
    chart = compute_bazi(_birth(), current_year=2026)

    assert chart.month_pillar["ten_god"] == chart.ten_gods["month"]
    assert chart.hour_pillar["ten_god"] == chart.ten_gods["hour"]
