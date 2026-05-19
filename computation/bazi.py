"""八字 / 子平 + 流年 计算引擎。

依赖：``computation.calendar`` 中已实现的四柱、十神、藏干、五行计数、神煞接口。

实现要点：
    1. 四柱 + 十神 + 藏干 + 神煞 + 五行计数（直接调用 calendar 模块）
    2. 格局判断（``_judge_pattern``）：基于月令旺衰 + 我党/他党得分
    3. 用神 / 喜忌：身强用克泄、身弱用印比；附加调候用神
    4. 大运 10 步：阳男阴女顺、阴男阳女逆，从月柱开始；每步 10 年
    5. 流年（当前年 + 未来 5 年）：流年干支 + 十神 + 与日干互动

入口：``compute_bazi(birth, current_year=2026) -> BaziChart``
"""
from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta, timezone
from typing import Any

from core.schemas import BaziChart, BirthInfo
from computation.calendar import (
    DI_ZHI,
    GAN_WUXING,
    GAN_YINYANG,
    MONTH_ZHI_ORDER,
    TIAN_GAN,
    ZHI_HIDDEN,
    ZHI_WUXING,
    count_five_elements,
    find_shensha,
    get_four_pillars,
    get_hidden_stems_for_pillars,
    get_ten_gods_for_pillars,
    solar_terms_for_year,
    stem_branch_from_index,
    ten_god_relation,
)

# ── 五行生克常量 ───────────────────────────────────────────────
WUXING_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
WUXING_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
WUXING_BEI_KE = {v: k for k, v in WUXING_KE.items()}  # 被克 = 克的反向
WUXING_BEI_SHENG = {v: k for k, v in WUXING_SHENG.items()}
WUXING_CONTROL_CYCLE = {
    "木": ["金", "火", "土"],
    "火": ["水", "土", "金"],
    "土": ["木", "金", "水"],
    "金": ["火", "水", "木"],
    "水": ["土", "木", "火"],
}

STEM_COMBINATIONS = {
    frozenset(("甲", "己")): "合土",
    frozenset(("乙", "庚")): "合金",
    frozenset(("丙", "辛")): "合水",
    frozenset(("丁", "壬")): "合木",
    frozenset(("戊", "癸")): "合火",
}
BRANCH_SIX_COMBINATIONS = {
    frozenset(("子", "丑")): "六合土",
    frozenset(("寅", "亥")): "六合木",
    frozenset(("卯", "戌")): "六合火",
    frozenset(("辰", "酉")): "六合金",
    frozenset(("巳", "申")): "六合水",
    frozenset(("午", "未")): "六合土",
}
BRANCH_CLASHES = {
    frozenset(("子", "午")),
    frozenset(("丑", "未")),
    frozenset(("寅", "申")),
    frozenset(("卯", "酉")),
    frozenset(("辰", "戌")),
    frozenset(("巳", "亥")),
}
BRANCH_HARMS = {
    frozenset(("子", "未")),
    frozenset(("丑", "午")),
    frozenset(("寅", "巳")),
    frozenset(("卯", "辰")),
    frozenset(("申", "亥")),
    frozenset(("酉", "戌")),
}
BRANCH_PUNISHMENTS = {
    frozenset(("寅", "巳", "申")): "无恩刑",
    frozenset(("丑", "戌", "未")): "恃势刑",
    frozenset(("子", "卯")): "无礼刑",
}
BRANCH_SELF_PUNISH = {"辰", "午", "酉", "亥"}

PILLAR_DOMAIN_HINTS = {
    "year": ["家族长辈", "早年背景", "外部名声"],
    "month": ["事业环境", "团队制度", "父母/上级", "工作节奏"],
    "day": ["亲密关系", "居住状态", "合作方式", "身体节奏"],
    "hour": ["长期规划", "子女晚辈", "下属/项目", "晚年安排"],
}
TEN_GOD_DOMAIN_HINTS = {
    "比肩": ["同辈竞争", "自我主张", "合伙关系"],
    "劫财": ["竞争分利", "朋友同事", "资源争夺"],
    "食神": ["表达产出", "技能作品", "稳定发挥"],
    "伤官": ["表达冲突", "规则摩擦", "突破创新"],
    "正财": ["稳定收入", "现实资源", "伴侣议题"],
    "偏财": ["商业机会", "外部资源", "投资往来"],
    "正官": ["职位规则", "责任名分", "上级制度"],
    "七杀": ["压力挑战", "竞争风险", "强执行任务"],
    "正印": ["单位文书", "资质保护", "学习支持"],
    "偏印": ["专业研究", "非标支持", "内在安全感"],
    "日主": ["自我状态", "身体节奏", "主观选择"],
}

# 十神归类
TEN_GODS_SAME_PARTY = {"比肩", "劫财", "正印", "偏印", "日主"}  # 我党
TEN_GODS_OTHER_PARTY = {"食神", "伤官", "正财", "偏财", "正官", "七杀"}

# 月令对各五行旺衰（工程评分表；只进入 metadata，不作为硬断语）
MONTH_ZHI_TO_WUXING_STRENGTH = {
    "寅": {"木": 3, "火": 2, "水": 1, "金": 0.5, "土": 0.5},
    "卯": {"木": 3, "火": 2, "水": 1, "金": 0.5, "土": 0.5},
    "辰": {"土": 3, "木": 2, "水": 1, "火": 0.5, "金": 0.5},
    "巳": {"火": 3, "土": 2, "木": 1, "金": 0.5, "水": 0.5},
    "午": {"火": 3, "土": 2, "木": 1, "金": 0.5, "水": 0.5},
    "未": {"土": 3, "火": 2, "金": 1, "木": 0.5, "水": 0.5},
    "申": {"金": 3, "水": 2, "土": 1, "木": 0.5, "火": 0.5},
    "酉": {"金": 3, "水": 2, "土": 1, "木": 0.5, "火": 0.5},
    "戌": {"土": 3, "金": 2, "火": 1, "水": 0.5, "木": 0.5},
    "亥": {"水": 3, "木": 2, "金": 1, "火": 0.5, "土": 0.5},
    "子": {"水": 3, "木": 2, "金": 1, "火": 0.5, "土": 0.5},
    "丑": {"土": 3, "金": 2, "水": 1, "木": 0.5, "火": 0.5},
}


# ── 工具 ────────────────────────────────────────────────────
def _next_stem(stem: str, step: int = 1) -> str:
    return TIAN_GAN[(TIAN_GAN.index(stem) + step) % 10]


def _next_branch(branch: str, step: int = 1) -> str:
    return DI_ZHI[(DI_ZHI.index(branch) + step) % 12]


def _stem_branch_offset(stem: str, branch: str, step: int) -> tuple[str, str]:
    """六十甲子按 step 步前进/后退。"""
    s_idx = TIAN_GAN.index(stem)
    b_idx = DI_ZHI.index(branch)
    # 找到当前 60 甲子索引
    cur_idx = -1
    for i in range(60):
        if i % 10 == s_idx and i % 12 == b_idx:
            cur_idx = i
            break
    if cur_idx < 0:
        raise ValueError(f"无效干支：{stem}{branch}")
    new_idx = (cur_idx + step) % 60
    return stem_branch_from_index(new_idx)


def _stem_interactions(a: str, b: str) -> list[str]:
    result: list[str] = []
    combo = STEM_COMBINATIONS.get(frozenset((a, b)))
    if combo:
        result.append(combo)
    a_wx = GAN_WUXING[a]
    b_wx = GAN_WUXING[b]
    if WUXING_KE[a_wx] == b_wx:
        result.append(f"{a}克{b}")
    elif WUXING_KE[b_wx] == a_wx:
        result.append(f"{b}克{a}")
    return result


def _branch_interactions(a: str, b: str) -> list[str]:
    pair = frozenset((a, b))
    result: list[str] = []
    combo = BRANCH_SIX_COMBINATIONS.get(pair)
    if combo:
        result.append(combo)
    if pair in BRANCH_CLASHES:
        result.append("六冲")
    if pair in BRANCH_HARMS:
        result.append("六害")
    for members, label in BRANCH_PUNISHMENTS.items():
        if a in members and b in members:
            result.append(label)
    if a == b and a in BRANCH_SELF_PUNISH:
        result.append("自刑")
    return result


def _chart_interactions(four_pillars: dict) -> list[dict[str, Any]]:
    positions = ("year", "month", "day", "hour")
    labels = {"year": "年柱", "month": "月柱", "day": "日柱", "hour": "时柱"}
    interactions: list[dict[str, Any]] = []
    for i, left in enumerate(positions):
        for right in positions[i + 1:]:
            left_p = four_pillars[f"{left}_pillar"]
            right_p = four_pillars[f"{right}_pillar"]
            stems = _stem_interactions(left_p["stem"], right_p["stem"])
            branches = _branch_interactions(left_p["branch"], right_p["branch"])
            if stems or branches:
                interactions.append({
                    "positions": [left, right],
                    "labels": [labels[left], labels[right]],
                    "stems": [left_p["stem"], right_p["stem"]],
                    "branches": [left_p["branch"], right_p["branch"]],
                    "stem_interactions": stems,
                    "branch_interactions": branches,
                })
    return interactions


def _attach_pillar_ten_gods(four_pillars: dict, ten_gods: dict[str, str]) -> dict:
    """把天干十神写回四柱对象，供 chart_ref 精确引用。"""
    annotated = {
        key: dict(value) if isinstance(value, dict) else value
        for key, value in four_pillars.items()
    }
    for pos in ("year", "month", "day", "hour"):
        annotated[f"{pos}_pillar"]["ten_god"] = ten_gods[pos]
    return annotated


def _add_calendar_delta(dt: datetime, years: int = 0, months: int = 0,
                        days: int = 0, hours: int = 0) -> datetime:
    """按历法年月日时累加，用于起运日期。"""
    year = dt.year + years
    month = dt.month + months
    while month > 12:
        year += 1
        month -= 12
    while month < 1:
        year -= 1
        month += 12

    day = min(dt.day, monthrange(year, month)[1])
    shifted = dt.replace(year=year, month=month, day=day)
    return shifted + timedelta(days=days, hours=hours)


def _local_to_utc(local_dt: datetime, tz_offset: float) -> datetime:
    return (local_dt - timedelta(hours=tz_offset)).replace(tzinfo=timezone.utc)


def _subtract_minutes_by_clock(end: datetime, start: datetime) -> int:
    """按日期和 HH:mm 计算分钟差，忽略秒数以贴合常用起运算法口径。"""
    days = (end.date() - start.date()).days
    minutes = end.hour * 60 + end.minute - (start.hour * 60 + start.minute)
    if minutes < 0:
        minutes += 1440
        days -= 1
    return days * 1440 + minutes


# ── 格局 / 旺衰 / 用神 ────────────────────────────────────────
def _calc_day_master_strength(four_pillars: dict, day_stem: str) -> dict:
    """计算日干强度 0-100 + 我党/他党得分。"""
    day_wx = GAN_WUXING[day_stem]
    month_branch = four_pillars["month_pillar"]["branch"]

    # 月令对日干同党 / 他党的影响
    month_strength = MONTH_ZHI_TO_WUXING_STRENGTH[month_branch]
    same_party_wx = {day_wx, WUXING_BEI_SHENG[day_wx]}  # 同我五行 + 生我五行（印）
    other_party_wx = {WUXING_SHENG[day_wx], WUXING_KE[day_wx], WUXING_BEI_KE[day_wx]}

    same_score = 0.0
    other_score = 0.0

    # 月令权重最大（×3）
    for wx, strength in month_strength.items():
        if wx in same_party_wx:
            same_score += strength * 3
        elif wx in other_party_wx:
            other_score += strength * 3

    # 各柱天干（不含日干本身），权重 ×2
    for pos in ("year", "month", "hour"):
        s_wx = GAN_WUXING[four_pillars[f"{pos}_pillar"]["stem"]]
        if s_wx in same_party_wx:
            same_score += 2
        elif s_wx in other_party_wx:
            other_score += 2

    # 各柱地支主气 + 藏干（藏干 0.5 权）
    for pos in ("year", "month", "day", "hour"):
        b = four_pillars[f"{pos}_pillar"]["branch"]
        b_wx = ZHI_WUXING[b]
        if b_wx in same_party_wx:
            same_score += 1.5
        elif b_wx in other_party_wx:
            other_score += 1.5
        # 藏干（除主气外）权重 0.5
        for hidden in ZHI_HIDDEN[b][1:]:
            h_wx = GAN_WUXING[hidden]
            if h_wx in same_party_wx:
                same_score += 0.5
            elif h_wx in other_party_wx:
                other_score += 0.5

    total = same_score + other_score
    pct = (same_score / total * 100.0) if total > 0 else 50.0

    if pct >= 60:
        category = "身强"
    elif pct >= 50:
        category = "中和偏强"
    elif pct >= 40:
        category = "中和偏弱"
    elif pct >= 25:
        category = "身弱"
    else:
        category = "极弱（可能从格）"

    score_0_100 = min(100, max(0, int(round(pct))))
    return {
        "same_party_score": round(same_score, 2),
        "other_party_score": round(other_score, 2),
        "same_party_ratio": round(pct, 2),
        "score_0_100": score_0_100,
        "category": category,
    }


def _judge_pattern(four_pillars: dict, day_stem: str, ten_gods: dict,
                    strength: dict) -> dict:
    """格局判断（精简）。

    返回 dict：``pattern``（主要格局名）、``notes``（其他可能格局/特征）。

    优先顺序：
        1. 极弱：从格（从财/从官/从儿）
        2. 月令偏正官杀 → 正官 / 七杀格
        3. 月令偏正财 → 正财 / 偏财格
        4. 月令食伤 → 食神 / 伤官格
        5. 月令印星 → 正印 / 偏印格
        6. 月令比劫 → 建禄 / 月刃格
    """
    notes: list[str] = []
    cat = strength["category"]

    # 月支主气十神
    month_branch = four_pillars["month_pillar"]["branch"]
    main_hidden = ZHI_HIDDEN[month_branch][0]  # 主气
    month_main_god = ten_god_relation(day_stem, main_hidden)

    pattern = None

    # ── 从格 ──
    if cat == "极弱（可能从格）" and strength["same_party_ratio"] < 20:
        # 看他党最旺者
        other_strong = max(
            ["财", "官杀", "食伤"],
            key=lambda x: 1,
        )
        # 直接根据月令归一化
        if month_main_god in ("正官", "七杀"):
            pattern = "从官杀格"
        elif month_main_god in ("正财", "偏财"):
            pattern = "从财格"
        elif month_main_god in ("食神", "伤官"):
            pattern = "从儿格"
        else:
            pattern = "从弱格"
        notes.append("身极弱，疑似从格，需具体看是否成格")

    # ── 普通格局 ──
    if pattern is None:
        if month_main_god == "正官":
            pattern = "正官格"
        elif month_main_god == "七杀":
            pattern = "七杀格"
        elif month_main_god == "正财":
            pattern = "正财格"
        elif month_main_god == "偏财":
            pattern = "偏财格"
        elif month_main_god == "食神":
            pattern = "食神格"
        elif month_main_god == "伤官":
            pattern = "伤官格"
        elif month_main_god == "正印":
            pattern = "正印格"
        elif month_main_god == "偏印":
            pattern = "偏印格"
        elif month_main_god == "比肩":
            pattern = "建禄格"
        elif month_main_god == "劫财":
            pattern = "月刃格"
        else:
            pattern = "杂气格"

    # 检查特殊格局：三奇、天乙、化气格等（精简提示）
    stems_in_chart = [four_pillars[f"{p}_pillar"]["stem"] for p in ("year", "month", "day", "hour")]
    if set(stems_in_chart) >= {"甲", "戊", "庚"}:
        notes.append("天上三奇（甲戊庚）")
    if set(stems_in_chart) >= {"乙", "丙", "丁"}:
        notes.append("地下三奇（乙丙丁）")
    if set(stems_in_chart) >= {"壬", "癸", "辛"}:
        notes.append("人中三奇（壬癸辛）")

    return {"pattern": pattern, "month_main_god": month_main_god, "notes": notes}


def _judge_yong_shen(four_pillars: dict, day_stem: str, strength: dict,
                      five_counts: dict[str, float]) -> dict:
    """工程评分版用神候选 + 喜忌候选 + 调候候选。

    身强者，泄克为用（食伤、财、官杀）；身弱者，扶抑为用（印、比）。
    调候：夏火炎需水；冬水寒需火；秋金燥需润；春木嫩需暖。
    """
    day_wx = GAN_WUXING[day_stem]
    cat = strength["category"]

    # 我党 / 他党五行
    same_set = {day_wx, WUXING_BEI_SHENG[day_wx]}  # 比 + 印
    other_set = {WUXING_SHENG[day_wx], WUXING_KE[day_wx], WUXING_BEI_KE[day_wx]}

    method = "扶抑"
    if cat in ("身强", "中和偏强"):
        # 用神：克泄
        favorable = [WUXING_SHENG[day_wx], WUXING_KE[day_wx], WUXING_BEI_KE[day_wx]]
        unfavorable = [day_wx, WUXING_BEI_SHENG[day_wx]]
        primary_yong = WUXING_KE[day_wx]  # 优先用财（克我所克）
        # 但若官杀已多则反用印比
        if five_counts.get(WUXING_BEI_KE[day_wx], 0) >= 3:
            primary_yong = WUXING_BEI_SHENG[day_wx]  # 用印化杀
    elif cat in ("中和偏弱", "身弱"):
        favorable = [day_wx, WUXING_BEI_SHENG[day_wx]]
        unfavorable = [WUXING_KE[day_wx], WUXING_BEI_KE[day_wx]]
        primary_yong = WUXING_BEI_SHENG[day_wx]  # 用印
    else:  # 极弱可能从
        favorable = [WUXING_SHENG[day_wx], WUXING_KE[day_wx], WUXING_BEI_KE[day_wx]]
        unfavorable = [day_wx, WUXING_BEI_SHENG[day_wx]]
        primary_yong = WUXING_SHENG[day_wx]
        method = "从势候选"

    # 调候候选（按月令）
    month_branch = four_pillars["month_pillar"]["branch"]
    tiao_hou = None
    if month_branch in ("巳", "午", "未"):  # 夏
        if day_wx == "火":
            tiao_hou = "水"
        elif day_wx == "金":
            tiao_hou = "水"
    elif month_branch in ("亥", "子", "丑"):  # 冬
        if day_wx == "水":
            tiao_hou = "火"
        elif day_wx == "金":
            tiao_hou = "火"
    elif month_branch in ("寅", "卯", "辰"):  # 春
        if day_wx == "木":
            tiao_hou = "火"  # 暖木
    elif month_branch in ("申", "酉", "戌"):  # 秋
        if day_wx == "金":
            tiao_hou = "水"  # 润金

    return {
        "primary": primary_yong,
        "favorable": favorable,
        "unfavorable": unfavorable,
        "tiao_hou": tiao_hou,
        "method": method,
        "explanation": (
            f"日干{day_stem}({day_wx}) 属{cat}, 取{primary_yong}为主用神; "
            f"喜{', '.join(favorable)}, 忌{', '.join(unfavorable)}"
            + (f"; 调候宜{tiao_hou}" if tiao_hou else "")
        ),
    }


# ── 大运 ───────────────────────────────────────────────────
def _start_info_for_da_yun(birth_dt: datetime, year_stem: str, gender: str,
                           longitude: float, tz_offset: float) -> dict[str, Any]:
    """计算起运方向、岁数与日期。

    采用分钟精算法：顺行取出生后下一节，逆行取出生前上一节；
    4320 分钟折 1 年、360 分钟折 1 月、12 分钟折 1 日。
    """
    yang_year = GAN_YINYANG[year_stem] == "阳"
    male = gender == "male"
    forward = (yang_year and male) or ((not yang_year) and (not male))  # 阳男阴女顺

    birth_utc = _local_to_utc(birth_dt.replace(tzinfo=None), tz_offset)

    # 12 节令名（每月节）
    month_terms_names = ["立春", "惊蛰", "清明", "立夏", "芒种", "小暑",
                          "立秋", "白露", "寒露", "立冬", "大雪", "小寒"]
    nodes: list[tuple[str, datetime]] = []
    for cycle_year in range(birth_utc.year - 1, birth_utc.year + 2):
        terms = solar_terms_for_year(cycle_year)
        for name in month_terms_names:
            nodes.append((name, terms[name]))
    nodes.sort(key=lambda item: item[1])

    if forward:
        # 找到下一节令
        target_name, target = next(((name, t) for name, t in nodes if t > birth_utc), nodes[-1])
    else:
        target_name, target = next(((name, t) for name, t in reversed(nodes) if t <= birth_utc), nodes[0])

    if forward:
        delta_minutes = _subtract_minutes_by_clock(target, birth_utc)
    else:
        delta_minutes = _subtract_minutes_by_clock(birth_utc, target)
    years, rem = divmod(delta_minutes, 4320)
    months, rem = divmod(rem, 360)
    days, rem = divmod(rem, 12)
    hours = rem * 2

    start_age_years = years + months / 12 + days / 365.25 + hours / (365.25 * 24)
    start_date = _add_calendar_delta(birth_dt, years=years, months=months, days=days, hours=hours)

    return {
        "forward": forward,
        "target_term": target_name,
        "target_term_utc": target.isoformat(),
        "delta_minutes": delta_minutes,
        "start_years": years,
        "start_months": months,
        "start_days": days,
        "start_hours": hours,
        "start_age_years": start_age_years,
        "start_date": start_date,
        "method": "minute_precise:4320min=1year,360min=1month,12min=1day",
    }


def _build_da_yun(four_pillars: dict, birth_dt: datetime, day_stem: str,
                   year_stem: str, gender: str, longitude: float,
                   tz_offset: float, n_steps: int = 10) -> list[dict]:
    """大运 10 步，从月柱开始按性别+年柱顺逆排。"""
    start_info = _start_info_for_da_yun(birth_dt, year_stem, gender, longitude, tz_offset)
    forward = start_info["forward"]
    start_age = start_info["start_age_years"]
    start_date = start_info["start_date"]

    month_stem = four_pillars["month_pillar"]["stem"]
    month_branch = four_pillars["month_pillar"]["branch"]
    da_yun: list[dict] = []
    for i in range(1, n_steps + 1):
        step = i if forward else -i
        s, b = _stem_branch_offset(month_stem, month_branch, step)
        ten_god = ten_god_relation(day_stem, s)
        age_from = round(start_age + (i - 1) * 10, 1)
        age_to = round(start_age + i * 10, 1)
        step_start_date = _add_calendar_delta(start_date, years=(i - 1) * 10)
        step_end_date = _add_calendar_delta(start_date, years=i * 10) - timedelta(days=1)
        da_yun.append({
            "step": i,
            "stem": s,
            "branch": b,
            "ganzhi": s + b,
            "ten_god": ten_god,
            "wuxing_stem": GAN_WUXING[s],
            "wuxing_branch": ZHI_WUXING[b],
            "age_start": age_from,
            "age_end": age_to,
            "year_start": step_start_date.year,
            "year_end": step_end_date.year,
            "start_date": step_start_date.isoformat(),
            "end_date": step_end_date.isoformat(),
        })

    return da_yun


# ── 流年 ───────────────────────────────────────────────────
def _liu_nian_for_year(year: int, day_stem: str) -> dict:
    """指定节气年的流年柱。"""
    idx = (year - 1984) % 60
    s, b = stem_branch_from_index(idx)
    god = ten_god_relation(day_stem, s)
    branch_god = ten_god_relation(day_stem, ZHI_HIDDEN[b][0])

    # 与日干互动标签
    interaction: list[str] = []
    day_wx = GAN_WUXING[day_stem]
    s_wx = GAN_WUXING[s]
    b_wx = ZHI_WUXING[b]
    if s_wx == day_wx:
        interaction.append("天干比劫")
    if WUXING_KE[day_wx] == s_wx:
        interaction.append("天干财星")
    if WUXING_BEI_KE[day_wx] == s_wx:
        interaction.append("天干官杀")
    if WUXING_SHENG[day_wx] == s_wx:
        interaction.append("天干食伤")
    if WUXING_BEI_SHENG[day_wx] == s_wx:
        interaction.append("天干印")
    if b_wx == day_wx:
        interaction.append("地支同党")
    if WUXING_BEI_KE[day_wx] == b_wx:
        interaction.append("地支官杀")

    return {
        "year": year,
        "stem": s,
        "branch": b,
        "ganzhi": s + b,
        "ten_god_stem": god,
        "ten_god_branch": branch_god,
        "wuxing_stem": GAN_WUXING[s],
        "wuxing_branch": ZHI_WUXING[b],
        "interactions": interaction,
    }


def _build_liu_nian(day_stem: str, current_year: int, n_years: int = 6) -> list[dict]:
    """当前年 + 未来 n_years - 1 年的流年。"""
    return [_liu_nian_for_year(current_year + i, day_stem) for i in range(n_years)]


def _current_da_yun(da_yun: list[dict[str, Any]], current_year: int) -> dict[str, Any] | None:
    for item in da_yun:
        if item["year_start"] <= current_year <= item["year_end"]:
            return item
    return None


def _score_ganzhi_against_preferences(stem: str, branch: str,
                                      favorable: list[str], unfavorable: list[str]) -> int:
    score = 0
    for wx in (GAN_WUXING[stem], ZHI_WUXING[branch]):
        if wx in favorable:
            score += 1
        if wx in unfavorable:
            score -= 1
    return score


def _classify_preference(score: int) -> str:
    if score >= 2:
        return "喜用得力"
    if score == 1:
        return "略偏喜"
    if score == 0:
        return "中性"
    if score == -1:
        return "略偏忌"
    return "忌神偏重"


def _element_preference(element: str, favorable: list[str], unfavorable: list[str]) -> str:
    if element in favorable:
        return "favorable"
    if element in unfavorable:
        return "unfavorable"
    return "neutral"


def _domain_hints_for_trigger(pos: str, stem_ten_god: str, branch_ten_god: str) -> list[str]:
    hints: list[str] = []
    for hint in PILLAR_DOMAIN_HINTS.get(pos, []):
        if hint not in hints:
            hints.append(hint)
    for god in (stem_ten_god, branch_ten_god):
        for hint in TEN_GOD_DOMAIN_HINTS.get(god, []):
            if hint not in hints:
                hints.append(hint)
    return hints


def _relation_types(interactions: list[str]) -> list[str]:
    relation_types: list[str] = []

    def add(label: str) -> None:
        if label not in relation_types:
            relation_types.append(label)

    if any(item.startswith("合") for item in interactions):
        add("天干五合")
    if any(item.startswith("六合") for item in interactions):
        add("地支六合")
    if any(item == "六冲" for item in interactions):
        add("地支六冲")
    if any("克" in item for item in interactions):
        add("天干相克")
    if any(item == "六害" for item in interactions):
        add("地支六害")
    if any(item.endswith("刑") or item == "自刑" for item in interactions):
        add("地支刑")
    if not relation_types:
        add("待判断")
    return relation_types


def _stem_trigger_against_chart(stem: str, four_pillars: dict, favorable: list[str],
                                unfavorable: list[str]) -> list[dict[str, Any]]:
    labels = {"year": "年柱", "month": "月柱", "day": "日柱", "hour": "时柱"}
    triggers: list[dict[str, Any]] = []
    incoming_wuxing = GAN_WUXING[stem]
    for pos in ("year", "month", "day", "hour"):
        pillar = four_pillars[f"{pos}_pillar"]
        natal_stem = pillar["stem"]
        interactions = _stem_interactions(stem, natal_stem)
        if not interactions:
            continue
        target_wuxing = GAN_WUXING[natal_stem]
        target_ten_god = pillar["ten_god"]
        triggers.append({
            "target": pos,
            "target_label": labels[pos],
            "target_stem": natal_stem,
            "target_ten_god": target_ten_god,
            "target_stem_wuxing": target_wuxing,
            "target_stem_preference": _element_preference(target_wuxing, favorable, unfavorable),
            "target_is_favorable": target_wuxing in favorable,
            "target_is_unfavorable": target_wuxing in unfavorable,
            "incoming_stem": stem,
            "incoming_stem_wuxing": incoming_wuxing,
            "incoming_stem_preference": _element_preference(incoming_wuxing, favorable, unfavorable),
            "interactions": interactions,
            "relation_types": _relation_types(interactions),
            "requires_context": True,
            "domain_hint": _domain_hints_for_trigger(pos, target_ten_god, target_ten_god),
        })
    return triggers


def _branch_trigger_against_chart(branch: str, four_pillars: dict, day_stem: str,
                                  favorable: list[str], unfavorable: list[str]) -> list[dict[str, Any]]:
    labels = {"year": "年柱", "month": "月柱", "day": "日柱", "hour": "时柱"}
    triggers: list[dict[str, Any]] = []
    for pos in ("year", "month", "day", "hour"):
        pillar = four_pillars[f"{pos}_pillar"]
        natal_branch = pillar["branch"]
        interactions = _branch_interactions(branch, natal_branch)
        if interactions:
            target_stem = pillar["stem"]
            target_stem_ten_god = pillar["ten_god"]
            hidden_stems = ZHI_HIDDEN[natal_branch]
            main_hidden = hidden_stems[0]
            main_hidden_ten_god = ten_god_relation(day_stem, main_hidden)
            branch_element = ZHI_WUXING[natal_branch]
            triggers.append({
                "target": pos,
                "target_label": labels[pos],
                "target_stem": target_stem,
                "target_stem_ten_god": target_stem_ten_god,
                "natal_branch": natal_branch,
                "target_branch_wuxing": branch_element,
                "target_branch_preference": _element_preference(branch_element, favorable, unfavorable),
                "target_branch_hidden_stems": hidden_stems,
                "target_main_hidden": main_hidden,
                "target_main_hidden_ten_god": main_hidden_ten_god,
                "target_ten_god": main_hidden_ten_god,
                "target_is_favorable": branch_element in favorable,
                "target_is_unfavorable": branch_element in unfavorable,
                "incoming_branch": branch,
                "incoming_branch_wuxing": ZHI_WUXING[branch],
                "incoming_branch_preference": _element_preference(ZHI_WUXING[branch], favorable, unfavorable),
                "interactions": interactions,
                "relation_types": _relation_types(interactions),
                "requires_context": True,
                "domain_hint": _domain_hints_for_trigger(pos, target_stem_ten_god, main_hidden_ten_god),
            })
    return triggers


def _annotate_da_yun_and_liu_nian(da_yun: list[dict[str, Any]], liu_nian: list[dict[str, Any]],
                                  four_pillars: dict, yong_shen: dict[str, Any],
                                  current_year: int) -> dict[str, Any]:
    favorable = yong_shen["favorable"]
    unfavorable = yong_shen["unfavorable"]
    annotated_da_yun = []
    for item in da_yun:
        score = _score_ganzhi_against_preferences(item["stem"], item["branch"], favorable, unfavorable)
        annotated_da_yun.append({
            **item,
            "preference_score": score,
            "preference_label": _classify_preference(score),
            "stem_triggers": _stem_trigger_against_chart(item["stem"], four_pillars, favorable, unfavorable),
            "branch_triggers": _branch_trigger_against_chart(
                item["branch"], four_pillars, four_pillars["day_pillar"]["stem"], favorable, unfavorable
            ),
        })

    current = _current_da_yun(annotated_da_yun, current_year)
    annotated_years = []
    for year_item in liu_nian:
        score = _score_ganzhi_against_preferences(year_item["stem"], year_item["branch"], favorable, unfavorable)
        da_yun_pair = []
        if current:
            da_yun_pair = (
                _stem_interactions(current["stem"], year_item["stem"])
                + _branch_interactions(current["branch"], year_item["branch"])
            )
        annotated_years.append({
            **year_item,
            "preference_score": score,
            "preference_label": _classify_preference(score),
            "stem_triggers": _stem_trigger_against_chart(year_item["stem"], four_pillars, favorable, unfavorable),
            "branch_triggers": _branch_trigger_against_chart(
                year_item["branch"], four_pillars, four_pillars["day_pillar"]["stem"], favorable, unfavorable
            ),
            "current_da_yun_interactions": da_yun_pair,
        })

    return {
        "current_da_yun": current,
        "da_yun": annotated_da_yun,
        "liu_nian": annotated_years,
    }


def _calibration_questions(four_pillars: dict, shen_sha: list[str], pattern_info: dict[str, Any],
                           yong_shen: dict[str, Any]) -> list[dict[str, str]]:
    questions = [
        {
            "field": "birth_time_source",
            "question": "出生时间来自医院记录、户口/家人记忆，还是只记得大概时辰？",
            "why": "八字时柱、紫微命身宫和占星宫位都会被分钟级出生时间影响。",
        },
        {
            "field": "major_events",
            "question": "请列 3 个已发生的大事年份，例如升学、搬家、入职、分手、结婚、重大病伤或家中变故。",
            "why": "用已发生事件反推大运流年触发点，可校正时辰和用神取法。",
        },
    ]
    if "驿马" in shen_sha:
        questions.append({
            "field": "mobility_history",
            "question": "过去是否有明显搬迁、长期出差、异地求学或工作调动？分别发生在哪几年？",
            "why": "命带驿马时，迁移事件是校盘的重要锚点。",
        })
    if "桃花" in shen_sha:
        questions.append({
            "field": "relationship_years",
            "question": "重要恋爱、分手、订婚/结婚年份分别是什么？",
            "why": "感情年份常能验证桃花、配偶宫和流年冲合。",
        })
    if pattern_info.get("pattern") in ("七杀格", "伤官格", "正官格"):
        questions.append({
            "field": "career_turning_points",
            "question": "职业上升、换赛道、被提拔、与上级冲突或制度压力明显的年份有哪些？",
            "why": "官杀/伤官相关格局需要用实际事业节点验证成格与用忌。",
        })
    if yong_shen.get("tiao_hou"):
        questions.append({
            "field": "climate_health_feedback",
            "question": "你对冷热湿燥环境的体感如何，是否有明显怕冷/怕热、睡眠、皮肤、脾胃或上火问题？",
            "why": "调候用神要结合体感和健康反馈，不宜只看五行数字。",
        })
    return questions


# ── 主入口 ────────────────────────────────────────────────
def compute_bazi(birth: BirthInfo, current_year: int = 2026) -> BaziChart:
    """计算八字命盘 + 大运 + 流年。

    返回 ``BaziChart`` Pydantic 模型实例。
    """
    birth_dt = datetime(birth.year, birth.month, birth.day, birth.hour, birth.minute)

    four_pillars = get_four_pillars(
        birth_dt,
        longitude=birth.longitude,
        tz_offset=birth.timezone_offset,
        use_true_solar_time=birth.use_true_solar_time,
    )
    ten_gods = get_ten_gods_for_pillars(four_pillars)
    four_pillars = _attach_pillar_ten_gods(four_pillars, ten_gods)
    hidden_stems = get_hidden_stems_for_pillars(four_pillars)
    five_counts = count_five_elements(four_pillars)
    shen_sha = find_shensha(four_pillars)

    day_stem = four_pillars["day_pillar"]["stem"]
    year_stem = four_pillars["year_pillar"]["stem"]

    # 强弱 / 格局 / 用神
    strength = _calc_day_master_strength(four_pillars, day_stem)
    pattern_info = _judge_pattern(four_pillars, day_stem, ten_gods, strength)
    yong_shen = _judge_yong_shen(four_pillars, day_stem, strength, five_counts)

    # 五行平衡度
    fc_total = sum(five_counts.values()) or 1
    balance: dict[str, float] = {wx: round(v / fc_total * 100, 2) for wx, v in five_counts.items()}
    most_wx = max(five_counts, key=lambda k: five_counts[k])
    least_wx = min(five_counts, key=lambda k: five_counts[k])

    # 大运 / 流年
    if birth.gender not in ("male", "female"):
        raise ValueError("八字大运顺逆需要明确男/女；请补充 gender=male 或 gender=female。")
    gender = birth.gender
    da_yun = _build_da_yun(
        four_pillars, birth_dt, day_stem, year_stem, gender,
        birth.longitude, birth.timezone_offset, n_steps=10,
    )
    da_yun_start = _start_info_for_da_yun(
        birth_dt, year_stem, gender, birth.longitude, birth.timezone_offset
    )
    liu_nian = _build_liu_nian(day_stem, current_year, n_years=6)
    event_timing = _annotate_da_yun_and_liu_nian(
        da_yun, liu_nian, four_pillars, yong_shen, current_year
    )
    chart_interactions = _chart_interactions(four_pillars)
    calibration_questions = _calibration_questions(four_pillars, shen_sha, pattern_info, yong_shen)

    # xi_ji
    xi_ji = {
        "favorable": yong_shen["favorable"],
        "unfavorable": yong_shen["unfavorable"],
        "tiao_hou": [yong_shen["tiao_hou"]] if yong_shen["tiao_hou"] else [],
    }

    # metadata
    metadata: dict[str, Any] = {
        "strength": strength,
        "pattern_info": pattern_info,
        "yong_shen_candidates": yong_shen,
        "five_elements_raw": {k: float(v) for k, v in five_counts.items()},
        "five_elements_balance_pct": balance,
        "five_elements_most": most_wx,
        "five_elements_least": least_wx,
        "chart_interactions": chart_interactions,
        "event_timing": event_timing,
        "calibration_questions": calibration_questions,
        "gender": gender,
        "current_year": current_year,
        "longitude": birth.longitude,
        "tz_offset": birth.timezone_offset,
        "day_boundary": four_pillars.get("day_boundary"),
        "da_yun_start": {
            **{k: v for k, v in da_yun_start.items() if k != "start_date"},
            "start_date": da_yun_start["start_date"].isoformat(),
        },
        "note": "大运起运采用分钟精算法; 真太阳时已校正; "
                "日柱按 23:00 子初换日; "
                "pattern/yong_shen/xi_ji 是工程评分候选，核心断语必须结合原局、岁运与典籍规则复核; "
                "five_elements 已四舍五入为 int, 详细含藏干浮点计数见 metadata.five_elements_raw",
    }

    chart = BaziChart(
        year_pillar=four_pillars["year_pillar"],
        month_pillar=four_pillars["month_pillar"],
        day_pillar=four_pillars["day_pillar"],
        hour_pillar=four_pillars["hour_pillar"],
        day_master=day_stem,
        # BaziChart.five_elements 声明为 dict[str,int]；藏干带 0.5 的细粒度计数
        # 我们存放在 metadata.five_elements_raw 里。
        five_elements={k: int(round(v)) for k, v in five_counts.items()},
        ten_gods=ten_gods,
        hidden_stems=hidden_stems,
        shen_sha=shen_sha,
        pattern=pattern_info["pattern"],
        yong_shen=yong_shen["primary"],
        xi_ji=xi_ji,
        da_yun=da_yun,
        liu_nian=liu_nian,
        solar_term=four_pillars.get("solar_term"),
        lunar_date=None,
        true_solar_time=four_pillars.get("true_solar_time"),
        school="zi_ping",
        metadata=metadata,
    )
    return chart


# ── CLI 测试 ────────────────────────────────────────────────
if __name__ == "__main__":
    import json

    demo_birth = BirthInfo(
        name="测试",
        gender="female",
        year=1991, month=8, day=15, hour=14, minute=30,
        location_name="北京", longitude=116.4074, latitude=39.9042,
        timezone_offset=8.0, use_true_solar_time=True,
    )
    chart = compute_bazi(demo_birth, current_year=2026)
    print(json.dumps(chart.model_dump(), default=str, ensure_ascii=False, indent=2))
