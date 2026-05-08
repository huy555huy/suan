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

# 十神归类
TEN_GODS_SAME_PARTY = {"比肩", "劫财", "正印", "偏印", "日主"}  # 我党
TEN_GODS_OTHER_PARTY = {"食神", "伤官", "正财", "偏财", "正官", "七杀"}

# 月令对各五行旺衰（简化：节令所属五行同党最旺）
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
    """简化用神 + 喜忌 + 调候用神判定。

    身强者，泄克为用（食伤、财、官杀）；身弱者，扶抑为用（印、比）。
    调候：夏火炎需水；冬水寒需火；秋金燥需润；春木嫩需暖。
    """
    day_wx = GAN_WUXING[day_stem]
    cat = strength["category"]

    # 我党 / 他党五行
    same_set = {day_wx, WUXING_BEI_SHENG[day_wx]}  # 比 + 印
    other_set = {WUXING_SHENG[day_wx], WUXING_KE[day_wx], WUXING_BEI_KE[day_wx]}

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

    # 调候用神（简化，按月令）
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
        "explanation": (
            f"日干{day_stem}({day_wx}) 属{cat}, 取{primary_yong}为主用神; "
            f"喜{', '.join(favorable)}, 忌{', '.join(unfavorable)}"
            + (f"; 调候宜{tiao_hou}" if tiao_hou else "")
        ),
    }


# ── 大运 ───────────────────────────────────────────────────
def _start_age_for_da_yun(birth_dt: datetime, year_stem: str, gender: str,
                            longitude: float, tz_offset: float) -> tuple[float, datetime]:
    """计算起运岁数与起运日期。

    简化算法：
      - 阳男阴女顺行，求生日距下一节令（中气前的节令）的天数
      - 阴男阳女逆行，求距上一节令的天数
      - 起运岁数 = 天数 / 3（一天折合 4 个月，三天折合 1 年）
    """
    yang_year = GAN_YINYANG[year_stem] == "阳"
    male = gender == "male"
    forward = (yang_year and male) or ((not yang_year) and (not male))  # 阳男阴女顺

    # UTC 化生日
    if birth_dt.tzinfo is None:
        birth_utc = (birth_dt - timedelta(hours=tz_offset)).replace(tzinfo=timezone.utc)
    else:
        birth_utc = birth_dt.astimezone(timezone.utc)

    terms_this = solar_terms_for_year(birth_dt.year)
    terms_prev = solar_terms_for_year(birth_dt.year - 1)
    terms_next = solar_terms_for_year(birth_dt.year + 1)

    # 12 节令名（每月节）
    month_terms_names = ["立春", "惊蛰", "清明", "立夏", "芒种", "小暑",
                          "立秋", "白露", "寒露", "立冬", "大雪", "小寒"]
    nodes: list[datetime] = []
    for n in month_terms_names:
        if n in terms_prev:
            nodes.append(terms_prev[n])
        if n in terms_this:
            nodes.append(terms_this[n])
        if n in terms_next:
            nodes.append(terms_next[n])
    nodes.sort()

    if forward:
        # 找到下一节令
        target = next((t for t in nodes if t > birth_utc), nodes[-1])
    else:
        target = next((t for t in reversed(nodes) if t < birth_utc), nodes[0])

    delta_days = abs((target - birth_utc).total_seconds()) / 86400.0
    start_age_years = delta_days / 3.0  # 3 天 = 1 年

    # 起运公历日期（生日 + start_age_years）
    start_date = birth_dt + timedelta(days=start_age_years * 365.25)
    return start_age_years, start_date


def _build_da_yun(four_pillars: dict, birth_dt: datetime, day_stem: str,
                   year_stem: str, gender: str, longitude: float,
                   tz_offset: float, n_steps: int = 10) -> list[dict]:
    """大运 10 步，从月柱开始按性别+年柱顺逆排。"""
    yang_year = GAN_YINYANG[year_stem] == "阳"
    male = gender == "male"
    forward = (yang_year and male) or ((not yang_year) and (not male))

    start_age, start_date = _start_age_for_da_yun(birth_dt, year_stem, gender,
                                                    longitude, tz_offset)

    month_stem = four_pillars["month_pillar"]["stem"]
    month_branch = four_pillars["month_pillar"]["branch"]
    da_yun: list[dict] = []
    for i in range(1, n_steps + 1):
        step = i if forward else -i
        s, b = _stem_branch_offset(month_stem, month_branch, step)
        ten_god = ten_god_relation(day_stem, s)
        age_from = round(start_age + (i - 1) * 10, 1)
        age_to = round(start_age + i * 10, 1)
        year_from = birth_dt.year + int(age_from)
        year_to = birth_dt.year + int(age_to)
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
            "year_start": year_from,
            "year_end": year_to,
        })

    return da_yun


# ── 流年 ───────────────────────────────────────────────────
def _liu_nian_for_year(year: int, day_stem: str) -> dict:
    """指定公历年的流年柱（以立春为界，简化用 (year-1984)%60 索引）。"""
    idx = (year - 1984) % 60
    s, b = stem_branch_from_index(idx)
    god = ten_god_relation(day_stem, s)
    branch_god = ten_god_relation(day_stem, ZHI_HIDDEN[b][0])

    # 与日干互动判定（简化）
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
    gender = birth.gender if birth.gender in ("male", "female") else "male"
    da_yun = _build_da_yun(
        four_pillars, birth_dt, day_stem, year_stem, gender,
        birth.longitude, birth.timezone_offset, n_steps=10,
    )
    liu_nian = _build_liu_nian(day_stem, current_year, n_years=6)

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
        "yong_shen_detail": yong_shen,
        "five_elements_raw": {k: float(v) for k, v in five_counts.items()},
        "five_elements_balance_pct": balance,
        "five_elements_most": most_wx,
        "five_elements_least": least_wx,
        "gender": gender,
        "current_year": current_year,
        "longitude": birth.longitude,
        "tz_offset": birth.timezone_offset,
        "note": "大运起运日采用简化 3 天=1 年算法; 真太阳时已校正; "
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
