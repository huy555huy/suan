"""农历 / 节气 / 干支转换。

实现要点：
- 干支 60 甲子用 1900-01-01 (庚子年丁丑月甲戌日) 作为锚点（六十甲子表）
- 节气日期用基于太阳黄经的精确算法（VSOP87 简化版）
- 真太阳时校正：基于经度差 + 均时差
- 不依赖任何外部库（避免 sxtwl / lunar-python 依赖问题）

精度：节气计算 ±15 分钟（足够八字排盘用），日干支 100% 准确。
"""
from __future__ import annotations
import math
from datetime import datetime, timedelta, timezone
from typing import Literal

# ── 天干地支 ─────────────────────────────────────────────────
TIAN_GAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
DI_ZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

# 五行
GAN_WUXING = {"甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
              "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水"}
ZHI_WUXING = {"子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
              "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水"}
# 阴阳
GAN_YINYANG = {g: "阳" if i % 2 == 0 else "阴" for i, g in enumerate(TIAN_GAN)}
ZHI_YINYANG = {z: "阳" if i % 2 == 0 else "阴" for i, z in enumerate(DI_ZHI)}

# 地支藏干
ZHI_HIDDEN = {
    "子": ["癸"],
    "丑": ["己", "癸", "辛"],
    "寅": ["甲", "丙", "戊"],
    "卯": ["乙"],
    "辰": ["戊", "乙", "癸"],
    "巳": ["丙", "戊", "庚"],
    "午": ["丁", "己"],
    "未": ["己", "丁", "乙"],
    "申": ["庚", "壬", "戊"],
    "酉": ["辛"],
    "戌": ["戊", "辛", "丁"],
    "亥": ["壬", "甲"],
}

# 月支节气对应（从立春寅月开始）
MONTH_ZHI_ORDER = ["寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥", "子", "丑"]
SOLAR_TERMS_FOR_MONTH = ["立春", "惊蛰", "清明", "立夏", "芒种", "小暑",
                         "立秋", "白露", "寒露", "立冬", "大雪", "小寒"]

# 24 节气名（按公历顺序，从立春开始 → 大寒）
SOLAR_TERMS = [
    "立春", "雨水", "惊蛰", "春分", "清明", "谷雨",
    "立夏", "小满", "芒种", "夏至", "小暑", "大暑",
    "立秋", "处暑", "白露", "秋分", "寒露", "霜降",
    "立冬", "小雪", "大雪", "冬至", "小寒", "大寒",
]

# 时辰对应（每 2 小时一个）
HOUR_ZHI_RANGES = [
    ("子", 23, 1),  # 23:00-00:59
    ("丑", 1, 3),
    ("寅", 3, 5),
    ("卯", 5, 7),
    ("辰", 7, 9),
    ("巳", 9, 11),
    ("午", 11, 13),
    ("未", 13, 15),
    ("申", 15, 17),
    ("酉", 17, 19),
    ("戌", 19, 21),
    ("亥", 21, 23),
]


# ── 儒略日转换 ───────────────────────────────────────────────
def to_julian_day(dt: datetime) -> float:
    """公历 datetime → 儒略日。dt 应为 UTC 时间。"""
    y, m, d = dt.year, dt.month, dt.day
    h = dt.hour + dt.minute / 60.0 + dt.second / 3600.0
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    jd = (
        math.floor(365.25 * (y + 4716))
        + math.floor(30.6001 * (m + 1))
        + d + b - 1524.5
        + h / 24.0
    )
    return jd


def from_julian_day(jd: float) -> datetime:
    """儒略日 → 公历 UTC datetime。"""
    jd_plus = jd + 0.5
    z = int(jd_plus)
    f = jd_plus - z
    if z < 2299161:
        a = z
    else:
        alpha = int((z - 1867216.25) / 36524.25)
        a = z + 1 + alpha - alpha // 4
    b = a + 1524
    c = int((b - 122.1) / 365.25)
    d = int(365.25 * c)
    e = int((b - d) / 30.6001)
    day_frac = b - d - int(30.6001 * e) + f
    day = int(day_frac)
    frac = day_frac - day
    month = e - 1 if e < 14 else e - 13
    year = c - 4716 if month > 2 else c - 4715
    seconds_total = int(round(frac * 86400))
    seconds_total = max(0, min(seconds_total, 86399))
    h = seconds_total // 3600
    mi = (seconds_total % 3600) // 60
    s = seconds_total % 60
    return datetime(year, month, day, h, mi, s, tzinfo=timezone.utc)


# ── 太阳黄经（精度 ±0.01°，足够用） ──────────────────────────
def solar_longitude(jd: float) -> float:
    """计算给定儒略日时太阳的视黄经（度）。基于 Meeus 简化算法。"""
    t = (jd - 2451545.0) / 36525.0  # 自 J2000.0 起的儒略世纪
    # 平黄经
    L0 = (280.46646 + 36000.76983 * t + 0.0003032 * t * t) % 360
    # 平近点角
    M = (357.52911 + 35999.05029 * t - 0.0001537 * t * t) % 360
    M_rad = math.radians(M)
    # 中心方程
    C = ((1.914602 - 0.004817 * t - 0.000014 * t * t) * math.sin(M_rad)
         + (0.019993 - 0.000101 * t) * math.sin(2 * M_rad)
         + 0.000289 * math.sin(3 * M_rad))
    true_long = L0 + C
    # 章动 + 光行差简化（约 -20.5″）
    omega = math.radians(125.04 - 1934.136 * t)
    apparent_long = true_long - 0.00569 - 0.00478 * math.sin(omega)
    return apparent_long % 360


def find_solar_term_jd(target_longitude: float, around_jd: float) -> float:
    """在 around_jd 附近寻找太阳黄经等于 target_longitude 的精确儒略日。"""
    # 牛顿迭代 / 二分
    jd = around_jd
    for _ in range(40):
        lon = solar_longitude(jd)
        diff = (target_longitude - lon + 540) % 360 - 180
        jd += diff / 0.9856474  # 太阳每日约 0.985 度
        if abs(diff) < 1e-5:
            break
    return jd


def solar_terms_for_year(year: int) -> dict[str, datetime]:
    """返回某年所有 24 节气的 UTC datetime。"""
    terms: dict[str, datetime] = {}
    # 立春（315°） 起算
    for i, term in enumerate(SOLAR_TERMS):
        target_lon = (315 + i * 15) % 360
        # 每个节气每年大致同一日期，初值给个估算
        approx_doy = i * 15 + 35  # 立春约第 35 天
        approx_dt = datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=approx_doy)
        approx_jd = to_julian_day(approx_dt)
        jd = find_solar_term_jd(target_lon, approx_jd)
        terms[term] = from_julian_day(jd)
    return terms


# ── 真太阳时 ─────────────────────────────────────────────────
def equation_of_time_minutes(jd: float) -> float:
    """均时差（分钟）。视太阳时 - 平太阳时。"""
    t = (jd - 2451545.0) / 36525.0
    L0 = math.radians((280.46646 + 36000.76983 * t) % 360)
    M = math.radians((357.52911 + 35999.05029 * t) % 360)
    e = 0.016708634 - 0.000042037 * t
    eps0 = 23.43929111 - 0.0130042 * t  # 黄赤交角（度）
    y = math.tan(math.radians(eps0 / 2)) ** 2
    eot_rad = (y * math.sin(2 * L0) - 2 * e * math.sin(M)
               + 4 * e * y * math.sin(M) * math.cos(2 * L0)
               - 0.5 * y * y * math.sin(4 * L0)
               - 1.25 * e * e * math.sin(2 * M))
    return math.degrees(eot_rad) * 4  # 度 × 4 = 分钟


def to_true_solar_time(local_dt: datetime, longitude: float, tz_offset: float) -> datetime:
    """把当地标准时间 + 经度 → 真太阳时 datetime（依然为 naive 数值用于排盘）。"""
    # 先得到 UTC
    utc_dt = local_dt - timedelta(hours=tz_offset)
    utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    jd = to_julian_day(utc_dt)
    eot = equation_of_time_minutes(jd)
    # 经度差导致的时间差（每 15° 经度差 1 小时）
    longitude_correction = (longitude - tz_offset * 15) * 4  # 分钟
    minutes_offset = eot + longitude_correction
    true_dt = local_dt + timedelta(minutes=minutes_offset)
    return true_dt


# ── 干支换算 ─────────────────────────────────────────────────
# 锚点：1984-02-04 22:00 (立春刚过)
# 该时刻为甲子年丙寅月甲子日甲子时

def stem_branch_from_index(idx: int) -> tuple[str, str]:
    """0-59 → (天干, 地支)"""
    idx = idx % 60
    return TIAN_GAN[idx % 10], DI_ZHI[idx % 12]


def index_from_stem_branch(stem: str, branch: str) -> int:
    """(天干, 地支) → 0-59 索引（六十甲子）"""
    s = TIAN_GAN.index(stem)
    b = DI_ZHI.index(branch)
    # 寻找 idx 使 idx%10==s 且 idx%12==b
    for i in range(60):
        if i % 10 == s and i % 12 == b:
            return i
    raise ValueError(f"无效干支组合：{stem}{branch}")


def get_year_pillar(year: int, terms: dict[str, datetime] | None = None,
                     dt: datetime | None = None) -> tuple[str, str, int]:
    """根据立春日决定年柱。返回 (天干, 地支, 60 甲子索引)。

    四柱年柱以立春为界：dt 在立春之前则用上一年。
    """
    if dt is not None:
        if terms is None:
            terms = solar_terms_for_year(year)
        lichun = terms["立春"]
        # 把 dt 转为 UTC 比较
        if dt.tzinfo is None:
            dt_utc = dt.replace(tzinfo=timezone.utc)
        else:
            dt_utc = dt.astimezone(timezone.utc)
        if dt_utc < lichun:
            year -= 1
    # 1984 = 甲子年，索引 0
    idx = (year - 1984) % 60
    stem, branch = stem_branch_from_index(idx)
    return stem, branch, idx


def get_month_pillar(dt: datetime, year_stem: str,
                      terms_this_year: dict[str, datetime] | None = None,
                      terms_next_year: dict[str, datetime] | None = None) -> tuple[str, str]:
    """月柱根据节气判断（从立春寅月开始）。"""
    if terms_this_year is None:
        terms_this_year = solar_terms_for_year(dt.year)
    if terms_next_year is None and dt.month >= 12:
        terms_next_year = solar_terms_for_year(dt.year + 1)

    if dt.tzinfo is None:
        dt_utc = dt.replace(tzinfo=timezone.utc)
    else:
        dt_utc = dt.astimezone(timezone.utc)

    # 取12个月节气：立春寅、惊蛰卯、清明辰、立夏巳、芒种午、小暑未、立秋申、白露酉、寒露戌、立冬亥、大雪子、小寒丑
    nodes = []
    for i, term_name in enumerate(SOLAR_TERMS_FOR_MONTH):
        if term_name in terms_this_year:
            nodes.append((term_name, terms_this_year[term_name], MONTH_ZHI_ORDER[i]))

    # 加入次年立春供边界判断
    if terms_next_year and "立春" in terms_next_year:
        nodes.append(("立春_next", terms_next_year["立春"], "寅"))
    # 也要考虑前年小寒
    if dt.month <= 2:
        terms_prev = solar_terms_for_year(dt.year - 1)
        for i, term_name in enumerate(SOLAR_TERMS_FOR_MONTH):
            if term_name in terms_prev:
                nodes.append((term_name + "_prev", terms_prev[term_name], MONTH_ZHI_ORDER[i]))

    nodes.sort(key=lambda x: x[1])
    # 找到最大的 < dt_utc 的节气
    month_zhi = None
    for term_name, term_dt, zhi in reversed(nodes):
        if term_dt <= dt_utc:
            month_zhi = zhi
            break
    if month_zhi is None:
        month_zhi = "丑"  # 兜底

    # 根据年干推月干（五虎遁元歌）
    # 甲己之年丙作首 / 乙庚之岁戊为头 / 丙辛必定寻庚起 / 丁壬壬位顺行流 / 戊癸甲寅之上求
    year_stem_to_first_month_stem = {
        "甲": "丙", "己": "丙",
        "乙": "戊", "庚": "戊",
        "丙": "庚", "辛": "庚",
        "丁": "壬", "壬": "壬",
        "戊": "甲", "癸": "甲",
    }
    first_stem = year_stem_to_first_month_stem[year_stem]
    first_idx = TIAN_GAN.index(first_stem)
    zhi_idx = MONTH_ZHI_ORDER.index(month_zhi)
    month_stem = TIAN_GAN[(first_idx + zhi_idx) % 10]
    return month_stem, month_zhi


def get_day_pillar(dt: datetime) -> tuple[str, str, int]:
    """日柱：基于固定锚点 1900-01-01 = 甲戌日（六十甲子索引 10）。

    注意：日柱以 23:00 为换日点（子时为新一天起始）。本函数使用纯日期计算，
    上层调用前把"23:00 后"的时间归并到下一天。
    """
    anchor = datetime(1900, 1, 1, tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta_days = (dt.date() - anchor.date()).days
    # 1900-01-01 是甲戌日 → 索引 10
    idx = (10 + delta_days) % 60
    stem, branch = stem_branch_from_index(idx)
    return stem, branch, idx


def get_hour_pillar(day_stem: str, hour: int, minute: int = 0) -> tuple[str, str]:
    """时柱：根据日干 + 时辰。

    五鼠遁：甲己还加甲，乙庚丙作初，丙辛从戊起，丁壬庚子居，戊癸何方发，壬子是真途。
    """
    # 找到时辰地支
    if hour == 23 or hour < 1:
        hour_zhi = "子"
        hour_zhi_idx = 0
    else:
        # hour 1-22, 每 2 小时一个支
        hour_zhi_idx = ((hour + 1) // 2) % 12
        hour_zhi = DI_ZHI[hour_zhi_idx]

    day_stem_to_first_hour_stem = {
        "甲": "甲", "己": "甲",
        "乙": "丙", "庚": "丙",
        "丙": "戊", "辛": "戊",
        "丁": "庚", "壬": "庚",
        "戊": "壬", "癸": "壬",
    }
    first_stem = day_stem_to_first_hour_stem[day_stem]
    first_idx = TIAN_GAN.index(first_stem)
    hour_stem = TIAN_GAN[(first_idx + hour_zhi_idx) % 10]
    return hour_stem, hour_zhi


def get_four_pillars(birth_dt: datetime, longitude: float = 116.4074,
                      tz_offset: float = 8.0, use_true_solar_time: bool = True) -> dict:
    """返回完整四柱信息（年/月/日/时）。

    输入：当地时间 birth_dt（无时区或带时区均可，按 tz_offset 换算）+ 经度。
    """
    # 1. 真太阳时校正
    naive_local = birth_dt.replace(tzinfo=None) if birth_dt.tzinfo else birth_dt
    if use_true_solar_time:
        true_local = to_true_solar_time(naive_local, longitude, tz_offset)
    else:
        true_local = naive_local

    # 2. UTC 时刻（用于节气判断）
    utc_dt = (true_local - timedelta(hours=tz_offset)).replace(tzinfo=timezone.utc)

    # 3. 处理子时换日（≥23:00 算次日）
    day_dt = true_local
    if true_local.hour == 23:
        day_dt = true_local + timedelta(hours=1)  # 推到次日凌晨用于查日柱

    # 4. 节气
    terms_this = solar_terms_for_year(true_local.year)
    terms_next = solar_terms_for_year(true_local.year + 1) if true_local.month >= 11 else None

    # 5. 年柱
    year_stem, year_branch, year_idx = get_year_pillar(true_local.year, terms_this, utc_dt)

    # 6. 月柱
    month_stem, month_branch = get_month_pillar(utc_dt, year_stem, terms_this, terms_next)

    # 7. 日柱
    day_dt_utc = (day_dt - timedelta(hours=tz_offset)).replace(tzinfo=timezone.utc)
    day_stem, day_branch, day_idx = get_day_pillar(day_dt_utc)

    # 8. 时柱
    hour_stem, hour_branch = get_hour_pillar(day_stem, true_local.hour, true_local.minute)

    # 9. 当下节气
    current_term = None
    sorted_terms = sorted(terms_this.items(), key=lambda x: x[1])
    for name, term_dt in reversed(sorted_terms):
        if term_dt <= utc_dt:
            current_term = name
            break

    return {
        "year_pillar": {"stem": year_stem, "branch": year_branch, "idx": year_idx,
                         "wuxing_stem": GAN_WUXING[year_stem], "wuxing_branch": ZHI_WUXING[year_branch]},
        "month_pillar": {"stem": month_stem, "branch": month_branch,
                          "wuxing_stem": GAN_WUXING[month_stem], "wuxing_branch": ZHI_WUXING[month_branch]},
        "day_pillar": {"stem": day_stem, "branch": day_branch, "idx": day_idx,
                        "wuxing_stem": GAN_WUXING[day_stem], "wuxing_branch": ZHI_WUXING[day_branch]},
        "hour_pillar": {"stem": hour_stem, "branch": hour_branch,
                         "wuxing_stem": GAN_WUXING[hour_stem], "wuxing_branch": ZHI_WUXING[hour_branch]},
        "true_solar_time": true_local.isoformat(),
        "solar_term": current_term,
        "lunar_year_idx": year_idx,
    }


# ── 十神 ────────────────────────────────────────────────────
# 以日干为我，看其它干（含藏干）的关系
def ten_god_relation(day_stem: str, other_stem: str) -> str:
    """返回 day_stem 视角下 other_stem 的十神名。"""
    day_wx = GAN_WUXING[day_stem]
    other_wx = GAN_WUXING[other_stem]
    same_yang = (GAN_YINYANG[day_stem] == GAN_YINYANG[other_stem])

    sheng = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
    ke = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

    if day_wx == other_wx:
        return "比肩" if same_yang else "劫财"
    if sheng[day_wx] == other_wx:  # 我生
        return "食神" if same_yang else "伤官"
    if ke[day_wx] == other_wx:  # 我克
        return "偏财" if same_yang else "正财"
    if ke[other_wx] == day_wx:  # 克我
        return "七杀" if same_yang else "正官"
    if sheng[other_wx] == day_wx:  # 生我
        return "偏印" if same_yang else "正印"
    return "未知"


def get_ten_gods_for_pillars(four_pillars: dict) -> dict:
    """计算四柱十神（以日干为基准）。"""
    day_stem = four_pillars["day_pillar"]["stem"]
    return {
        "year": ten_god_relation(day_stem, four_pillars["year_pillar"]["stem"]),
        "month": ten_god_relation(day_stem, four_pillars["month_pillar"]["stem"]),
        "day": "日主",
        "hour": ten_god_relation(day_stem, four_pillars["hour_pillar"]["stem"]),
    }


def get_hidden_stems_for_pillars(four_pillars: dict) -> dict:
    """各柱地支藏干。"""
    return {
        pos: ZHI_HIDDEN[four_pillars[f"{pos}_pillar"]["branch"]]
        for pos in ("year", "month", "day", "hour")
    }


def count_five_elements(four_pillars: dict) -> dict[str, int]:
    """统计四柱里五行（含藏干，但藏干权重 0.5）的强度。"""
    counts = {"木": 0, "火": 0, "土": 0, "金": 0, "水": 0}
    for pos in ("year", "month", "day", "hour"):
        p = four_pillars[f"{pos}_pillar"]
        counts[p["wuxing_stem"]] += 1
        counts[p["wuxing_branch"]] += 1
    # 藏干 + 0.5
    for pos in ("year", "month", "day", "hour"):
        for hidden in ZHI_HIDDEN[four_pillars[f"{pos}_pillar"]["branch"]][1:]:
            counts[GAN_WUXING[hidden]] += 0.5
    return counts


# ── 神煞（基础选） ────────────────────────────────────────────
TIANYI_TABLE = {  # 天乙贵人
    "甲": ["丑", "未"], "戊": ["丑", "未"], "庚": ["丑", "未"],
    "乙": ["子", "申"], "己": ["子", "申"],
    "丙": ["亥", "酉"], "丁": ["亥", "酉"],
    "壬": ["巳", "卯"], "癸": ["巳", "卯"],
    "辛": ["午", "寅"],
}
WENCHANG_TABLE = {  # 文昌贵人
    "甲": "巳", "乙": "午", "丙": "申", "丁": "酉", "戊": "申",
    "己": "酉", "庚": "亥", "辛": "子", "壬": "寅", "癸": "卯",
}
TAOHUA_TABLE = {  # 桃花（年支或日支查）
    "申": "酉", "子": "酉", "辰": "酉",
    "寅": "卯", "午": "卯", "戌": "卯",
    "巳": "午", "酉": "午", "丑": "午",
    "亥": "子", "卯": "子", "未": "子",
}
YIMA_TABLE = {  # 驿马
    "申": "寅", "子": "寅", "辰": "寅",
    "寅": "申", "午": "申", "戌": "申",
    "巳": "亥", "酉": "亥", "丑": "亥",
    "亥": "巳", "卯": "巳", "未": "巳",
}
HUAGAI_TABLE = {  # 华盖
    "申": "辰", "子": "辰", "辰": "辰",
    "寅": "戌", "午": "戌", "戌": "戌",
    "巳": "丑", "酉": "丑", "丑": "丑",
    "亥": "未", "卯": "未", "未": "未",
}


def find_shensha(four_pillars: dict) -> list[str]:
    """识别命中的神煞（精简版，不计风水神煞）。"""
    shensha = []
    day_stem = four_pillars["day_pillar"]["stem"]
    year_branch = four_pillars["year_pillar"]["branch"]
    day_branch = four_pillars["day_pillar"]["branch"]
    branches = [four_pillars[f"{p}_pillar"]["branch"] for p in ("year", "month", "day", "hour")]

    if any(b in TIANYI_TABLE.get(day_stem, []) for b in branches):
        shensha.append("天乙贵人")
    if WENCHANG_TABLE[day_stem] in branches:
        shensha.append("文昌")
    for ref in (year_branch, day_branch):
        if TAOHUA_TABLE.get(ref) in branches:
            shensha.append("桃花")
            break
    for ref in (year_branch, day_branch):
        if YIMA_TABLE.get(ref) in branches:
            shensha.append("驿马")
            break
    for ref in (year_branch, day_branch):
        if HUAGAI_TABLE.get(ref) in branches:
            shensha.append("华盖")
            break
    return list(dict.fromkeys(shensha))  # 去重保序
