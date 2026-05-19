import pytest

from core.intake import IntakeError, assert_chart_ready, validate_chart_request


def _profile(**overrides):
    data = {
        "name": "A",
        "gender": "female",
        "date": "1991-08-15",
        "time": "14:30",
        "unknownTime": False,
        "place": "北京",
    }
    data.update(overrides)
    return data


def test_bazi_requires_precise_birth_time_and_place():
    intake = validate_chart_request("bazi", _profile(time="", unknownTime=True), "看看运势")
    assert not intake.ok
    assert any(issue.field == "time" for issue in intake.issues)

    with pytest.raises(IntakeError, match="出生时辰"):
        assert_chart_ready("bazi", _profile(time="", unknownTime=True), "看看运势")


def test_birthinfo_rejects_overseas_coordinates():
    intake = validate_chart_request(
        "bazi",
        _profile(place="", longitude=-122.2727, latitude=37.8715),
        "看看运势",
    )
    assert not intake.ok
    assert any("海外" in issue.message or "中国境内" in issue.message for issue in intake.issues)


def test_ziwei_requires_binary_gender_for_decadal_cycle():
    intake = validate_chart_request("ziwei", _profile(gender="other"), "看紫微")
    assert not intake.ok
    assert any(issue.field == "gender" for issue in intake.issues)


def test_bazi_requires_binary_gender_for_luck_cycle():
    intake = validate_chart_request("bazi", _profile(gender="other"), "看大运")
    assert not intake.ok
    assert any(issue.field == "gender" for issue in intake.issues)


def test_fengshui_requires_house_facts():
    intake = validate_chart_request("fengshui", _profile(), "看看家里布局")
    assert not intake.ok
    assert {issue.field for issue in intake.issues} == {"facing_degree", "move_in_year"}


def test_hexagram_requires_specific_question():
    intake = validate_chart_request("hexagram", _profile(), "")
    assert not intake.ok
    assert any(issue.field == "question" for issue in intake.issues)


def test_hexagram_requires_user_divination_inputs_and_time():
    intake = validate_chart_request("hexagram", _profile(), "问工作")
    assert not intake.ok
    assert {"divination_input", "divination_time"} <= {issue.field for issue in intake.issues}

    intake = validate_chart_request(
        "hexagram",
        _profile(hexagram_numbers=[3, 5], divination_time="2026-05-19T12:00:00"),
        "问工作",
    )
    assert intake.ok


def test_tarot_requires_user_drawn_cards():
    intake = validate_chart_request("tarot", _profile(), "问工作")
    assert not intake.ok
    assert any(issue.field == "tarot_card_indexes" for issue in intake.issues)
    assert any(issue.field == "tarot_spread" for issue in intake.issues)

    intake = validate_chart_request(
        "tarot",
        _profile(tarot_spread="celtic_cross", tarot_card_indexes=list(range(10))),
        "问工作",
    )
    assert intake.ok
