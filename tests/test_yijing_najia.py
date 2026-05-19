from datetime import datetime

import pytest

from computation.yijing import compute_coin


DIVINATION_TIME = datetime(2026, 5, 19, 12, 0)


def test_coin_chart_uses_najia_reference_for_qian():
    chart = compute_coin("问工作", [[1, 0, 0]] * 6, DIVINATION_TIME)

    assert chart.metadata["engine"] == "najia"
    assert chart.metadata["params"] == [1, 1, 1, 1, 1, 1]
    assert chart.ben_gua["full_name"] == "乾为天"
    assert chart.ben_gua["name"] == "乾"
    assert chart.ben_gua["palace"] == "乾"
    assert chart.shi_yao == 6
    assert chart.ying_yao == 3
    assert chart.moving_lines == []
    assert chart.six_relatives == ["子孙", "妻财", "父母", "官鬼", "兄弟", "父母"]
    assert chart.ben_gua["line_ganzhi_wuxing"][0] == "甲子水"
    assert chart.metadata["xun_kong"] == "午未"
    assert "乾为天" in chart.metadata["render"]
    analysis = chart.metadata["liuyao_analysis"]
    assert analysis["question_yong_shen"] == "官鬼"
    assert analysis["yong_shen_positions"] == [4]
    assert analysis["yong_shen_source"] == "keyword:工作"
    assert analysis["shi_ying_relation"]["shi_to_ying"] == "比和"


def test_coin_score_maps_old_yin_and_old_yang_to_najia_params():
    chart = compute_coin(
        "问事",
        [
            [1, 0, 0],  # 7 少阳 -> 1
            [0, 0, 0],  # 6 老阴 -> 3
            [1, 1, 0],  # 8 少阴 -> 0
            [1, 1, 1],  # 9 老阳 -> 4
            [1, 0, 1],  # 8 少阴 -> 0
            [0, 1, 0],  # 7 少阳 -> 1
        ],
        DIVINATION_TIME,
    )

    assert chart.metadata["params"] == [1, 3, 0, 4, 0, 1]
    assert chart.moving_lines == [2, 4]
    assert chart.ben_gua["lines_detail"][1]["moving"] is True
    assert chart.ben_gua["lines_detail"][3]["moving"] is True
    assert chart.bian_gua is not None
    assert chart.metadata["liuyao_analysis"]["moving_effects"]


def test_hexagram_flags_relationship_yongshen_needing_identity():
    chart = compute_coin("问感情", [[1, 0, 0]] * 6, DIVINATION_TIME)

    analysis = chart.metadata["liuyao_analysis"]
    assert analysis["question_yong_shen"] is None
    assert analysis["yong_shen_source"] == "relationship_requires_identity"
    assert any("求测者性别" in item for item in analysis["needs_clarification"])


def test_hexagram_relationship_uses_identity_when_present():
    chart = compute_coin("女生问感情", [[1, 0, 0]] * 6, DIVINATION_TIME)

    analysis = chart.metadata["liuyao_analysis"]
    assert analysis["question_yong_shen"] == "官鬼"
    assert analysis["yong_shen_source"] == "relationship_female_self"


def test_hexagram_generic_question_does_not_invent_yongshen():
    chart = compute_coin("问事", [[1, 0, 0]] * 6, DIVINATION_TIME)

    analysis = chart.metadata["liuyao_analysis"]
    assert analysis["question_yong_shen"] is None
    assert analysis["yong_shen_source"] == "unclassified_question"
    assert any("用神未定" in item for item in analysis["needs_clarification"])


def test_coin_requires_user_results_and_time():
    with pytest.raises(ValueError, match="需要用户提供"):
        compute_coin("问事", None, DIVINATION_TIME)
    with pytest.raises(ValueError, match="明确起卦时间"):
        compute_coin("问事", [[1, 0, 0]] * 6, None)
