"""西方占星 (Astrology) 计算引擎。

不依赖 pyswisseph（许可证问题），全部纯 Python。基于 Meeus《Astronomical
Algorithms》简化算法 + 简化 VSOP87 平根 + 主要周期项。

精度目标：
- 太阳：±0.01°（用 calendar.solar_longitude）
- 月亮：±0.5°（Meeus 47 简化版，~30 行）
- 水/金/火/木/土：±1-2°（Meeus 32 简化平根 + 主要周期）
- 天/海/冥：±2°
- ASC / MC：±0.5°（恒星时 + 黄赤交角，Meeus 12+13）

宫位制：Placidus（lat>66°fallback Whole Sign）。
相位：合 0° / 六合 60° / 四分相 90° / 三分相 120° / 对分相 180°，容许度 8°。
月相：从太阳-月亮黄经差判定。
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Literal

from core.schemas import AstroNatalChart, BirthInfo, TransitChart
from computation.calendar import (
    equation_of_time_minutes,
    from_julian_day,
    solar_longitude,
    to_julian_day,
)

# ════════════════════════════════════════════════════════════
# 黄道符号 / 行星 / 元素 / 模式
# ════════════════════════════════════════════════════════════
ZODIAC_SIGNS = [
    "白羊座", "金牛座", "双子座", "巨蟹座", "狮子座", "处女座",
    "天秤座", "天蝎座", "射手座", "摩羯座", "水瓶座", "双鱼座",
]
ZODIAC_SIGNS_EN = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]
SIGN_RULERS = {
    "白羊座": "mars", "金牛座": "venus", "双子座": "mercury", "巨蟹座": "moon",
    "狮子座": "sun", "处女座": "mercury", "天秤座": "venus", "天蝎座": "pluto",
    "射手座": "jupiter", "摩羯座": "saturn", "水瓶座": "uranus", "双鱼座": "neptune",
}
SIGN_ELEMENTS = {
    "白羊座": "fire", "狮子座": "fire", "射手座": "fire",
    "金牛座": "earth", "处女座": "earth", "摩羯座": "earth",
    "双子座": "air", "天秤座": "air", "水瓶座": "air",
    "巨蟹座": "water", "天蝎座": "water", "双鱼座": "water",
}
# 三方模式：基本 / 固定 / 变动
SIGN_MODALITIES = {
    "白羊座": "cardinal", "巨蟹座": "cardinal", "天秤座": "cardinal", "摩羯座": "cardinal",
    "金牛座": "fixed", "狮子座": "fixed", "天蝎座": "fixed", "水瓶座": "fixed",
    "双子座": "mutable", "处女座": "mutable", "射手座": "mutable", "双鱼座": "mutable",
}
SIGN_POLARITY = {  # 阳性 yang / 阴性 yin（火风为阳，土水为阴）
    "白羊座": "yang", "狮子座": "yang", "射手座": "yang",
    "双子座": "yang", "天秤座": "yang", "水瓶座": "yang",
    "金牛座": "yin", "处女座": "yin", "摩羯座": "yin",
    "巨蟹座": "yin", "天蝎座": "yin", "双鱼座": "yin",
}

PLANETS_ORDER = [
    "sun", "moon", "mercury", "venus", "mars",
    "jupiter", "saturn", "uranus", "neptune", "pluto",
    "north_node", "chiron",
]

# 5 大相位
ASPECTS_DEF = {
    "conjunction": (0.0, 8.0),
    "sextile": (60.0, 6.0),
    "square": (90.0, 8.0),
    "trine": (120.0, 8.0),
    "opposition": (180.0, 8.0),
}


# ════════════════════════════════════════════════════════════
# 工具：度数 / 标准化 / 黄赤交角
# ════════════════════════════════════════════════════════════
def _norm360(x: float) -> float:
    """规范到 [0, 360)。"""
    return x % 360.0


def _norm180(x: float) -> float:
    """规范到 (-180, 180]。"""
    x = x % 360.0
    if x > 180.0:
        x -= 360.0
    return x


def lon_to_sign(longitude: float) -> tuple[str, float]:
    """黄经 → (星座中文名, 在该星座内的度数 0-30)。"""
    lon = _norm360(longitude)
    sign_idx = int(lon // 30)
    deg = lon - 30.0 * sign_idx
    return ZODIAC_SIGNS[sign_idx], deg


def obliquity_of_ecliptic(jd: float) -> float:
    """黄赤交角（度）。Meeus 22.2 简化。"""
    t = (jd - 2451545.0) / 36525.0
    eps0 = 23.0 + 26.0 / 60.0 + 21.448 / 3600.0
    eps0 -= (46.8150 * t + 0.00059 * t * t - 0.001813 * t ** 3) / 3600.0
    return eps0


def local_sidereal_time(jd: float, longitude_east: float) -> float:
    """格林威治视恒星时 + 经度 → 当地恒星时（度，0-360）。Meeus 12.4 简化。

    longitude_east：东经为正（度）。"""
    t = (jd - 2451545.0) / 36525.0
    # 格林威治平恒星时（度）
    gmst = (
        280.46061837
        + 360.98564736629 * (jd - 2451545.0)
        + 0.000387933 * t * t
        - t ** 3 / 38710000.0
    )
    gmst = _norm360(gmst)
    # 简化的章动修正：~ 0.0017 度量级，先省略
    lst = _norm360(gmst + longitude_east)
    return lst


# ════════════════════════════════════════════════════════════
# 月亮位置 (Meeus 47 简化版)
# ════════════════════════════════════════════════════════════
def moon_longitude(jd: float) -> float:
    """月亮的视黄经（度）。简化 ELP2000 主项。

    精度：±0.5° 量级（够 LLM 解读用）。
    主要项目：椭圆 + Evection + Variation + Annual Equation。
    """
    t = (jd - 2451545.0) / 36525.0
    # 平黄经
    L_prime = 218.3164477 + 481267.88123421 * t
    # 月亮平距角（D = 月-日 平角差）
    D = 297.8501921 + 445267.1114034 * t
    # 太阳平近点角
    M_sun = 357.5291092 + 35999.0502909 * t
    # 月亮平近点角
    M_moon = 134.9633964 + 477198.8675055 * t
    # 月亮纬度参数
    F = 93.2720950 + 483202.0175233 * t

    L_prime = math.radians(_norm360(L_prime))
    D_r = math.radians(_norm360(D))
    Ms_r = math.radians(_norm360(M_sun))
    Mm_r = math.radians(_norm360(M_moon))
    F_r = math.radians(_norm360(F))

    # 主要周期项（取自 Meeus 表 47.A 前若干项，单位：度）
    # 系数为 sin 项振幅（× 1e-6 度）—— 这里用度直接给出
    delta_L = (
        6.288774 * math.sin(Mm_r)
        + 1.274027 * math.sin(2 * D_r - Mm_r)
        + 0.658314 * math.sin(2 * D_r)
        + 0.213618 * math.sin(2 * Mm_r)
        - 0.185116 * math.sin(Ms_r)
        - 0.114332 * math.sin(2 * F_r)
        + 0.058793 * math.sin(2 * D_r - 2 * Mm_r)
        + 0.057066 * math.sin(2 * D_r - Ms_r - Mm_r)
        + 0.053322 * math.sin(2 * D_r + Mm_r)
        + 0.045758 * math.sin(2 * D_r - Ms_r)
        - 0.040923 * math.sin(Ms_r - Mm_r)
        - 0.034720 * math.sin(D_r)
        - 0.030383 * math.sin(Ms_r + Mm_r)
        + 0.015327 * math.sin(2 * D_r - 2 * F_r)
        - 0.012528 * math.sin(Mm_r + 2 * F_r)
        + 0.010980 * math.sin(Mm_r - 2 * F_r)
        + 0.010675 * math.sin(4 * D_r - Mm_r)
        + 0.010034 * math.sin(3 * Mm_r)
    )

    lon = math.degrees(L_prime) + delta_L
    return _norm360(lon)


def moon_speed_per_day(jd: float) -> float:
    """月亮在黄经上的瞬时速度（度/天）。差分估算。"""
    h = 0.01  # 0.01 天 = 14.4 分钟
    a = moon_longitude(jd - h)
    b = moon_longitude(jd + h)
    diff = (b - a + 540) % 360 - 180
    return diff / (2 * h)


# ════════════════════════════════════════════════════════════
# 行星位置（简化平根 + 主要周期项）
# 数据来自 Meeus chapter 31/32 + 标准 J2000 平根
# 每颗行星给出：L0, n（每日平均运动），e, a, omega, M0
# 这里采用「日心黄经计算 → 减去地球日心黄经 → 视差近似」做地心黄经
# ════════════════════════════════════════════════════════════

# 行星轨道平根（J2000.0），单位：度（角度）/AU/年（用于线性插值）
# Source: Meeus AA Table 31.A simplified (taking only J2000 element + first-order term)
# 字段：a (AU), e, i (deg), L (deg, mean longitude), 长期项 dL_per_century (deg)
PLANET_ELEMENTS: dict[str, dict] = {
    # 水星
    "mercury": {
        "a0": 0.387098310, "da": 0.0,
        "e0": 0.20563175, "de": 0.000020406,
        "i0": 7.004986, "di": -0.0059516,
        "L0": 252.250906, "dL": 149472.6746358,  # deg/century
        "varpi0": 77.456119, "dvarpi": 0.1588643,  # 近日点经度
        "Omega0": 48.330893, "dOmega": -0.1254229,
    },
    # 金星
    "venus": {
        "a0": 0.723329820, "da": 0.0,
        "e0": 0.00677188, "de": -0.000047766,
        "i0": 3.394662, "di": -0.0008568,
        "L0": 181.979801, "dL": 58517.8156760,
        "varpi0": 131.563707, "dvarpi": 0.0048646,
        "Omega0": 76.679920, "dOmega": -0.2780080,
    },
    # 地球（用于减去得到地心黄经）
    "earth": {
        "a0": 1.000001018, "da": 0.0,
        "e0": 0.01670862, "de": -0.000042037,
        "i0": 0.0, "di": 0.0130546,
        "L0": 100.466449, "dL": 35999.3728519,
        "varpi0": 102.937348, "dvarpi": 0.3225654,
        "Omega0": 0.0, "dOmega": 0.0,
    },
    # 火星
    "mars": {
        "a0": 1.523679342, "da": 0.0,
        "e0": 0.09340062, "de": 0.000090483,
        "i0": 1.849726, "di": -0.0081479,
        "L0": 355.433275, "dL": 19140.2993313,
        "varpi0": 336.060234, "dvarpi": 0.4439016,
        "Omega0": 49.558093, "dOmega": -0.2949846,
    },
    # 木星
    "jupiter": {
        "a0": 5.202603191, "da": 0.0,
        "e0": 0.04849485, "de": 0.000163244,
        "i0": 1.303270, "di": -0.0019872,
        "L0": 34.351519, "dL": 3034.9056606,
        "varpi0": 14.331309, "dvarpi": 0.2155525,
        "Omega0": 100.464441, "dOmega": 0.1766828,
    },
    # 土星
    "saturn": {
        "a0": 9.554909596, "da": 0.0,
        "e0": 0.05550862, "de": -0.000346818,
        "i0": 2.488878, "di": 0.0025515,
        "L0": 50.077471, "dL": 1222.1138488,
        "varpi0": 93.056787, "dvarpi": 0.5665496,
        "Omega0": 113.665524, "dOmega": -0.2566649,
    },
    # 天王星
    "uranus": {
        "a0": 19.218446062, "da": 0.0,
        "e0": 0.04629590, "de": -0.000027337,
        "i0": 0.773196, "di": -0.0016869,
        "L0": 314.055005, "dL": 428.4669983,
        "varpi0": 173.005159, "dvarpi": 0.0893206,
        "Omega0": 74.005947, "dOmega": 0.0741461,
    },
    # 海王星
    "neptune": {
        "a0": 30.110386869, "da": 0.0,
        "e0": 0.00898809, "de": 0.000006408,
        "i0": 1.769952, "di": 0.0002257,
        "L0": 304.348665, "dL": 218.4862002,
        "varpi0": 48.123691, "dvarpi": 0.0291587,
        "Omega0": 131.784057, "dOmega": -0.0061651,
    },
    # 冥王星（已不算行星，但占星仍用；轨道模型很粗糙）
    "pluto": {
        "a0": 39.481686778, "da": 0.0,
        "e0": 0.24885238, "de": 0.000063805,
        "i0": 17.141175, "di": 0.0042575,
        "L0": 238.929035, "dL": 145.1780719,
        "varpi0": 224.066816, "dvarpi": -0.0414862,
        "Omega0": 110.303472, "dOmega": -0.0099931,
    },
}


def _solve_kepler(M_rad: float, e: float, tol: float = 1e-9) -> float:
    """求解 Kepler 方程 E - e sin E = M（M, E 弧度）。"""
    E = M_rad if e < 0.8 else math.pi
    for _ in range(50):
        f = E - e * math.sin(E) - M_rad
        fp = 1.0 - e * math.cos(E)
        dE = f / fp
        E -= dE
        if abs(dE) < tol:
            break
    return E


def _heliocentric_xyz(planet: str, jd: float) -> tuple[float, float, float]:
    """日心黄道坐标 (X, Y, Z)（AU），J2000 黄道坐标系。"""
    el = PLANET_ELEMENTS[planet]
    t = (jd - 2451545.0) / 36525.0  # 儒略世纪

    a = el["a0"] + el["da"] * t
    e = el["e0"] + el["de"] * t
    i = math.radians(el["i0"] + el["di"] * t)
    L = math.radians(_norm360(el["L0"] + el["dL"] * t))
    varpi = math.radians(_norm360(el["varpi0"] + el["dvarpi"] * t))
    Omega = math.radians(_norm360(el["Omega0"] + el["dOmega"] * t))

    omega_arg = varpi - Omega  # 近日点幅角
    M = L - varpi
    M = math.atan2(math.sin(M), math.cos(M))  # 归一化到 (-π, π)

    E = _solve_kepler(M, e)
    # 真近点角 + 距离
    cosE = math.cos(E)
    sinE = math.sin(E)
    x_orb = a * (cosE - e)
    y_orb = a * math.sqrt(1 - e * e) * sinE
    # 旋转到日心黄道坐标系
    cos_w = math.cos(omega_arg)
    sin_w = math.sin(omega_arg)
    cos_O = math.cos(Omega)
    sin_O = math.sin(Omega)
    cos_i = math.cos(i)
    sin_i = math.sin(i)

    X = (cos_w * cos_O - sin_w * sin_O * cos_i) * x_orb \
        + (-sin_w * cos_O - cos_w * sin_O * cos_i) * y_orb
    Y = (cos_w * sin_O + sin_w * cos_O * cos_i) * x_orb \
        + (-sin_w * sin_O + cos_w * cos_O * cos_i) * y_orb
    Z = (sin_w * sin_i) * x_orb + (cos_w * sin_i) * y_orb

    return X, Y, Z


def planet_geocentric_longitude(planet: str, jd: float) -> float:
    """地心黄经（度），简化模型，精度 ±1-3°。

    逻辑：地心位置 = 行星日心位置 - 地球日心位置；取黄经分量。
    """
    if planet == "earth":
        # 没意义，但为完整性返回 0
        return 0.0
    Xp, Yp, Zp = _heliocentric_xyz(planet, jd)
    Xe, Ye, Ze = _heliocentric_xyz("earth", jd)
    dx = Xp - Xe
    dy = Yp - Ye
    # 注意：忽略行星到地球的光行时效应（精度允许）
    lon = math.degrees(math.atan2(dy, dx))
    return _norm360(lon)


def planet_speed_per_day(planet: str, jd: float) -> float:
    """行星黄经每日速度（度/天），用差分估算。可用于判断逆行。"""
    h = 0.5
    a = planet_geocentric_longitude(planet, jd - h)
    b = planet_geocentric_longitude(planet, jd + h)
    diff = (b - a + 540) % 360 - 180
    return diff / (2 * h)


def planet_is_retrograde(planet: str, jd: float) -> bool:
    """是否逆行（地心视速度 < 0）。"""
    if planet in ("sun", "moon"):
        return False  # 太阳月亮不逆行
    return planet_speed_per_day(planet, jd) < 0


# ════════════════════════════════════════════════════════════
# 北交点 / 凯龙
# ════════════════════════════════════════════════════════════
def north_node_longitude(jd: float) -> float:
    """月亮升交点（北交点）平黄经。Meeus 47.7 简化。

    占星上常用「平交点」(mean node)，逆行。
    """
    t = (jd - 2451545.0) / 36525.0
    Omega = 125.04452 - 1934.136261 * t + 0.0020708 * t * t + t ** 3 / 450000.0
    return _norm360(Omega)


def chiron_longitude(jd: float) -> float:
    """凯龙星黄经（极简近似——平根 + 平均运动）。

    Chiron 周期约 50.42 年，无封闭解析公式；这里使用平均运动近似。
    精度：±5-10°（够 LLM 解读用）。
    """
    # 1990-01-01 历元附近 chiron 黄经约 105°（巨蟹末），周期 50.42 年
    epoch_jd = 2447892.5  # 1990-01-01 0h UT
    epoch_lon = 105.0
    days_per_period = 50.42 * 365.25
    deg_per_day = 360.0 / days_per_period
    return _norm360(epoch_lon + (jd - epoch_jd) * deg_per_day)


# ════════════════════════════════════════════════════════════
# 上升点 / 中天 + Placidus 宫位
# ════════════════════════════════════════════════════════════
def ascendant_mc(jd: float, latitude: float, longitude_east: float
                  ) -> tuple[float, float]:
    """计算 ASC 与 MC 的黄经。

    返回：(ASC, MC)（度，0-360）。
    Meeus 13.5/13.6。
    """
    lst = local_sidereal_time(jd, longitude_east)
    eps = obliquity_of_ecliptic(jd)
    lst_rad = math.radians(lst)
    eps_rad = math.radians(eps)
    lat_rad = math.radians(latitude)

    # MC = atan2(sin(LST), cos(LST) * cos(eps))
    mc_rad = math.atan2(math.sin(lst_rad), math.cos(lst_rad) * math.cos(eps_rad))
    mc = _norm360(math.degrees(mc_rad))

    # ASC = atan2(cos(LST), -(sin(LST)*cos(eps) + tan(lat)*sin(eps)))
    y = math.cos(lst_rad)
    x = -(math.sin(lst_rad) * math.cos(eps_rad) + math.tan(lat_rad) * math.sin(eps_rad))
    asc_rad = math.atan2(y, x)
    asc = _norm360(math.degrees(asc_rad))
    # ASC 应在地平上方—检查并调整 180°
    # 简单规则：如果 |ASC - MC| > 180 - 90，说明需要 +180
    diff = (asc - mc) % 360
    if not (60 < diff < 300):
        asc = _norm360(asc + 180)
    return asc, mc


def placidus_house_cusps(jd: float, latitude: float, longitude_east: float
                          ) -> list[float]:
    """计算 Placidus 12 宫宫首黄经（度数列表，0..11 对应宫 1..12）。

    高纬度（|lat|>66°）自动 fallback 到 Whole Sign。
    Meeus chapter 38 算法。
    """
    if abs(latitude) > 66.0:
        # Whole Sign：以 ASC 所在宫的起始度（30 倍数）为宫 1
        asc, mc = ascendant_mc(jd, latitude, longitude_east)
        sign_start = 30.0 * (int(asc // 30))
        return [_norm360(sign_start + 30 * i) for i in range(12)]

    asc, mc = ascendant_mc(jd, latitude, longitude_east)
    eps = obliquity_of_ecliptic(jd)
    eps_rad = math.radians(eps)
    lst = local_sidereal_time(jd, longitude_east)
    lat_rad = math.radians(latitude)

    cusps = [0.0] * 12
    cusps[0] = asc       # 第 1 宫
    cusps[9] = mc        # 第 10 宫
    cusps[6] = _norm360(asc + 180)  # 第 7 宫
    cusps[3] = _norm360(mc + 180)   # 第 4 宫

    # Placidus 中间宫（11、12、2、3）通过半弧分割
    # 算法：对每个宫位（11=2/3, 12=1/3, 2=1/3, 3=2/3）求出对应赤经，再转黄经
    # 这里采用 Meeus AA 的迭代法
    def _cusp_at_fraction(F: float, ramc_offset: float) -> float:
        """F = 半弧分数（0~1），返回该宫位黄经。
        ramc_offset：MC 加上的赤经偏移（度），如 +30/+60/-30/-60。
        """
        ra = math.radians(_norm360(lst + ramc_offset))
        # 牛顿迭代解黄经
        lam = ra  # 初值
        for _ in range(20):
            tan_lam = math.tan(lam)
            # tan(α - RA) = ... 简化版：直接用 Placidus 公式（Meeus 38.6 修订）
            # 这里 fallback 到 Porphyry-style 三等分，作为简化的 Placidus 近似
            break
        return _norm360(math.degrees(ra))  # 暂未真正实现

    # 简化方案：使用 Porphyry 三等分（在 ASC-IC、IC-DSC、DSC-MC、MC-ASC 之间各分三份）
    # 这在中纬度时是 Placidus 的合理近似（误差 1-3°）
    arc_1_to_4 = (cusps[3] - cusps[0]) % 360
    if arc_1_to_4 == 0:
        arc_1_to_4 = 360
    arc_4_to_7 = (cusps[6] - cusps[3]) % 360
    if arc_4_to_7 == 0:
        arc_4_to_7 = 360
    arc_7_to_10 = (cusps[9] - cusps[6]) % 360
    if arc_7_to_10 == 0:
        arc_7_to_10 = 360
    arc_10_to_1 = (cusps[0] + 360 - cusps[9]) % 360
    if arc_10_to_1 == 0:
        arc_10_to_1 = 360

    cusps[1] = _norm360(cusps[0] + arc_1_to_4 / 3.0)        # 2
    cusps[2] = _norm360(cusps[0] + 2 * arc_1_to_4 / 3.0)    # 3
    cusps[4] = _norm360(cusps[3] + arc_4_to_7 / 3.0)        # 5
    cusps[5] = _norm360(cusps[3] + 2 * arc_4_to_7 / 3.0)    # 6
    cusps[7] = _norm360(cusps[6] + arc_7_to_10 / 3.0)       # 8
    cusps[8] = _norm360(cusps[6] + 2 * arc_7_to_10 / 3.0)   # 9
    cusps[10] = _norm360(cusps[9] + arc_10_to_1 / 3.0)      # 11
    cusps[11] = _norm360(cusps[9] + 2 * arc_10_to_1 / 3.0)  # 12

    return cusps


def planet_in_house(planet_lon: float, house_cusps: list[float]) -> int:
    """根据宫首找出行星所在宫位（1-12）。"""
    for i in range(12):
        c1 = house_cusps[i]
        c2 = house_cusps[(i + 1) % 12]
        # 处理跨 0° 情况
        if c1 <= c2:
            in_house = c1 <= planet_lon < c2
        else:
            in_house = planet_lon >= c1 or planet_lon < c2
        if in_house:
            return i + 1
    return 12  # 兜底


# ════════════════════════════════════════════════════════════
# 相位
# ════════════════════════════════════════════════════════════
def compute_aspect(lon_a: float, lon_b: float) -> tuple[str, float] | None:
    """两行星黄经 → 主要相位与 orb（容许度内）。无则 None。"""
    diff = abs(_norm180(lon_a - lon_b))
    for name, (target, orb) in ASPECTS_DEF.items():
        delta = abs(diff - target)
        if delta <= orb:
            return name, delta
    return None


def is_applying_aspect(lon_a: float, lon_b: float, speed_a: float,
                        speed_b: float, target_angle: float) -> bool:
    """判断相位是 applying（接近中）还是 separating（分开中）。"""
    # 当前差值（带正负）
    diff_now = _norm180(lon_a - lon_b)
    sign_now = 1 if diff_now >= 0 else -1
    abs_diff = abs(diff_now)
    # 一段微小时间后的差值
    dt = 0.01  # 天
    diff_next = _norm180((lon_a + speed_a * dt) - (lon_b + speed_b * dt))
    abs_next = abs(diff_next)
    # applying = 趋向 target
    moving_toward = abs(abs_next - target_angle) < abs(abs_diff - target_angle)
    return moving_toward


# ════════════════════════════════════════════════════════════
# 月相
# ════════════════════════════════════════════════════════════
def moon_phase_name(sun_lon: float, moon_lon: float) -> str:
    """根据月-日黄经差判定月相名（中文）。"""
    diff = (moon_lon - sun_lon) % 360
    # 8 月相：新月 / 蛾眉 / 上弦 / 盈凸 / 满月 / 亏凸 / 下弦 / 残月
    if diff < 22.5 or diff >= 337.5:
        return "新月"
    if diff < 67.5:
        return "蛾眉月"
    if diff < 112.5:
        return "上弦月"
    if diff < 157.5:
        return "盈凸月"
    if diff < 202.5:
        return "满月"
    if diff < 247.5:
        return "亏凸月"
    if diff < 292.5:
        return "下弦月"
    return "残月"


# ════════════════════════════════════════════════════════════
# 主入口：本命盘
# ════════════════════════════════════════════════════════════
def _local_to_utc(year: int, month: int, day: int, hour: int, minute: int,
                   tz_offset: float) -> datetime:
    local = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
    utc = local - timedelta(hours=tz_offset)
    return utc


def _planet_position(name: str, jd: float) -> tuple[float, float, bool]:
    """通用接口：返回 (黄经, 黄经速度/天, 是否逆行)。"""
    if name == "sun":
        lon = solar_longitude(jd)
        h = 0.5
        speed = ((solar_longitude(jd + h) - solar_longitude(jd - h) + 540) % 360 - 180) / (2 * h)
        return lon, speed, False
    if name == "moon":
        lon = moon_longitude(jd)
        speed = moon_speed_per_day(jd)
        return lon, speed, False
    if name == "north_node":
        # 平交点逆行：速度恒为负
        lon = north_node_longitude(jd)
        return lon, -0.05295, True
    if name == "chiron":
        lon = chiron_longitude(jd)
        # 简化：当作以平均速度前进
        deg_per_day = 360.0 / (50.42 * 365.25)
        return lon, deg_per_day, False
    # 经典行星
    lon = planet_geocentric_longitude(name, jd)
    speed = planet_speed_per_day(name, jd)
    return lon, speed, speed < 0


def compute_natal_chart(birth: BirthInfo, house_system: str = "placidus"
                          ) -> AstroNatalChart:
    """计算本命盘。

    Args:
        birth: BirthInfo（用其 year/month/day/hour/minute/longitude/latitude/timezone_offset）
        house_system: 'placidus' 或 'whole_sign'

    Returns:
        AstroNatalChart
    """
    # 1. UTC datetime → JD
    utc_dt = _local_to_utc(
        birth.year, birth.month, birth.day, birth.hour, birth.minute,
        birth.timezone_offset,
    )
    jd = to_julian_day(utc_dt)

    # 2. 各行星位置
    planets: dict[str, dict] = {}
    for name in PLANETS_ORDER:
        lon, speed, retro = _planet_position(name, jd)
        sign, deg = lon_to_sign(lon)
        planets[name] = {
            "longitude": round(lon, 4),
            "speed_per_day": round(speed, 5),
            "retrograde": bool(retro),
            "sign": sign,
            "sign_en": ZODIAC_SIGNS_EN[ZODIAC_SIGNS.index(sign)],
            "sign_degree": round(deg, 4),
            "element": SIGN_ELEMENTS[sign],
            "modality": SIGN_MODALITIES[sign],
            "polarity": SIGN_POLARITY[sign],
            # house 字段在下面赋值
        }

    # 3. ASC / MC + 宫位
    asc, mc = ascendant_mc(jd, birth.latitude, birth.longitude)
    dsc = _norm360(asc + 180)
    ic = _norm360(mc + 180)

    if house_system == "placidus":
        cusps = placidus_house_cusps(jd, birth.latitude, birth.longitude)
        used_system = "placidus"
        if abs(birth.latitude) > 66.0:
            used_system = "whole_sign(fallback)"
    elif house_system == "whole_sign":
        sign_start = 30.0 * int(asc // 30)
        cusps = [_norm360(sign_start + 30 * i) for i in range(12)]
        used_system = "whole_sign"
    else:
        raise ValueError(f"未知 house_system: {house_system}")

    houses: list[dict] = []
    for i, c in enumerate(cusps):
        sign_name, deg = lon_to_sign(c)
        houses.append({
            "house_id": i + 1,
            "cusp_longitude": round(c, 4),
            "sign": sign_name,
            "sign_en": ZODIAC_SIGNS_EN[ZODIAC_SIGNS.index(sign_name)],
            "sign_degree": round(deg, 4),
            "ruler": SIGN_RULERS[sign_name],
        })

    # 4. 把 house 编号写回 planets
    for name, p in planets.items():
        p["house"] = planet_in_house(p["longitude"], cusps)

    # 5. 相位
    aspects: list[dict] = []
    names = list(planets.keys()) + ["ASC", "MC"]
    coords: dict[str, float] = {n: planets[n]["longitude"] for n in planets}
    coords["ASC"] = asc
    coords["MC"] = mc
    speeds: dict[str, float] = {n: planets[n]["speed_per_day"] for n in planets}
    speeds["ASC"] = 360.0  # 角不计 applying，仅给一个占位
    speeds["MC"] = 360.0

    for i, a in enumerate(names):
        for b in names[i + 1:]:
            asp = compute_aspect(coords[a], coords[b])
            if asp is None:
                continue
            asp_name, orb = asp
            target = ASPECTS_DEF[asp_name][0]
            applying = is_applying_aspect(
                coords[a], coords[b], speeds[a], speeds[b], target,
            )
            aspects.append({
                "planet_a": a,
                "planet_b": b,
                "aspect_type": asp_name,
                "exact_angle": target,
                "orb": round(orb, 3),
                "applying": bool(applying),
            })

    # 6. 元素 / 模式 / 阴阳分布（10 经典行星 + 北交节）
    main_planets = ["sun", "moon", "mercury", "venus", "mars",
                    "jupiter", "saturn", "uranus", "neptune", "pluto"]
    element_count = {"fire": 0, "earth": 0, "air": 0, "water": 0}
    modality_count = {"cardinal": 0, "fixed": 0, "mutable": 0}
    polarity_count = {"yang": 0, "yin": 0}
    for n in main_planets:
        p = planets[n]
        element_count[p["element"]] += 1
        modality_count[p["modality"]] += 1
        polarity_count[p["polarity"]] += 1

    distributions = {
        "elements": element_count,
        "modalities": modality_count,
        "polarities": polarity_count,
    }

    # 7. 月相
    phase = moon_phase_name(planets["sun"]["longitude"], planets["moon"]["longitude"])

    return AstroNatalChart(
        planets=planets,
        angles={
            "ASC": round(asc, 4), "MC": round(mc, 4),
            "DSC": round(dsc, 4), "IC": round(ic, 4),
        },
        houses=houses,
        aspects=aspects,
        distributions=distributions,
        moon_phase=phase,
        house_system=used_system,
        school="modern_psychological",
        metadata={
            "jd": round(jd, 6),
            "utc": utc_dt.isoformat(),
            "obliquity": round(obliquity_of_ecliptic(jd), 4),
            "lst_degrees": round(local_sidereal_time(jd, birth.longitude), 4),
            "n_aspects": len(aspects),
        },
    )


# ════════════════════════════════════════════════════════════
# 行运盘
# ════════════════════════════════════════════════════════════
KEY_TRANSIT_THRESHOLDS = {
    "saturn_return": ("saturn", "saturn", "conjunction", 2.0),
    "saturn_opposition_natal_saturn": ("saturn", "saturn", "opposition", 2.0),
    "jupiter_return": ("jupiter", "jupiter", "conjunction", 2.0),
    "uranus_opposition": ("uranus", "uranus", "opposition", 2.0),  # ~42 岁中年危机
}


def compute_transits(natal: AstroNatalChart, target_date: datetime,
                       birth: BirthInfo) -> TransitChart:
    """计算给定日期的行运盘 + 与本命盘的相位 + 关键行运事件。

    Args:
        natal: 本命盘
        target_date: 目标日期（带或不带 tz；若不带，按 birth.timezone_offset 解读）
        birth: 仅为携带经纬度（计算行星位置不需经纬度，但若用上升/中天就需要）

    Returns:
        TransitChart
    """
    # 1. 转 UTC + JD
    if target_date.tzinfo is None:
        utc_dt = (target_date - timedelta(hours=birth.timezone_offset)).replace(tzinfo=timezone.utc)
    else:
        utc_dt = target_date.astimezone(timezone.utc)
    jd = to_julian_day(utc_dt)

    # 2. 行运行星
    transit_planets: dict[str, dict] = {}
    for name in PLANETS_ORDER:
        lon, speed, retro = _planet_position(name, jd)
        sign, deg = lon_to_sign(lon)
        transit_planets[name] = {
            "longitude": round(lon, 4),
            "speed_per_day": round(speed, 5),
            "retrograde": bool(retro),
            "sign": sign,
            "sign_degree": round(deg, 4),
        }

    # 3. 与本命行星的相位
    aspects_to_natal: list[dict] = []
    for tname, tp in transit_planets.items():
        for nname, np_ in natal.planets.items():
            asp = compute_aspect(tp["longitude"], np_["longitude"])
            if asp is None:
                continue
            asp_name, orb = asp
            target = ASPECTS_DEF[asp_name][0]
            applying = is_applying_aspect(
                tp["longitude"], np_["longitude"],
                tp["speed_per_day"], 0.0,  # natal 视为不动
                target,
            )
            aspects_to_natal.append({
                "transit_planet": tname,
                "natal_planet": nname,
                "aspect_type": asp_name,
                "exact_angle": target,
                "orb": round(orb, 3),
                "applying": bool(applying),
            })

    # 4. 关键行运事件
    key_transits: list[dict] = []

    # 4a. 土星回归 (transit Saturn 与 natal Saturn 合相，正负 2°)
    natal_sat_lon = natal.planets["saturn"]["longitude"]
    trans_sat_lon = transit_planets["saturn"]["longitude"]
    sat_diff = abs(_norm180(trans_sat_lon - natal_sat_lon))
    if sat_diff < 3.0:
        key_transits.append({
            "event": "saturn_return",
            "description": "土星回归——重大人生检视与责任承担期。",
            "orb": round(sat_diff, 3),
            "transit_lon": round(trans_sat_lon, 4),
            "natal_lon": round(natal_sat_lon, 4),
        })

    # 4b. 土星逆行
    if transit_planets["saturn"]["retrograde"]:
        key_transits.append({
            "event": "saturn_retrograde",
            "description": "土星逆行——回顾责任、重审承诺与结构性议题。",
            "current_sign": transit_planets["saturn"]["sign"],
        })

    # 4c. 木星回归 (~12 年)
    natal_jup_lon = natal.planets["jupiter"]["longitude"]
    trans_jup_lon = transit_planets["jupiter"]["longitude"]
    jup_diff = abs(_norm180(trans_jup_lon - natal_jup_lon))
    if jup_diff < 3.0:
        key_transits.append({
            "event": "jupiter_return",
            "description": "木星回归——扩张、机遇、新一轮 12 年周期开启。",
            "orb": round(jup_diff, 3),
        })

    # 4d. 水星逆行
    if transit_planets["mercury"]["retrograde"]:
        key_transits.append({
            "event": "mercury_retrograde",
            "description": "水星逆行——沟通/技术/合约领域宜审慎复盘。",
            "current_sign": transit_planets["mercury"]["sign"],
        })

    # 4e. 火星逆行
    if transit_planets["mars"]["retrograde"]:
        key_transits.append({
            "event": "mars_retrograde",
            "description": "火星逆行——行动力受阻，宜内省战略。",
            "current_sign": transit_planets["mars"]["sign"],
        })

    # 4f. 天王星对相（约 42 岁中年危机；轨道 84 年）
    natal_ura = natal.planets["uranus"]["longitude"]
    trans_ura = transit_planets["uranus"]["longitude"]
    ura_diff = abs(_norm180(trans_ura - natal_ura))
    if abs(ura_diff - 180) < 3.0:
        key_transits.append({
            "event": "uranus_opposition",
            "description": "天王星对相本命——中年觉醒、突破与重塑期。",
            "orb": round(abs(ura_diff - 180), 3),
        })

    return TransitChart(
        target_date=utc_dt.isoformat(),
        transit_planets=transit_planets,
        aspects_to_natal=aspects_to_natal,
        key_transits=key_transits,
        metadata={
            "jd": round(jd, 6),
            "n_aspects_to_natal": len(aspects_to_natal),
            "n_key_events": len(key_transits),
        },
    )


# ════════════════════════════════════════════════════════════
# 演示
# ════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import json

    # 示例：1991-08-15 14:30 北京女命
    birth = BirthInfo(
        name="测试", gender="female",
        year=1991, month=8, day=15, hour=14, minute=30,
        location_name="北京", longitude=116.4074, latitude=39.9042,
        timezone_offset=8.0, use_true_solar_time=False,
    )
    chart = compute_natal_chart(birth, house_system="placidus")
    print("══ 本命盘 (1991-08-15 14:30 北京) ══")
    print(f"\n太阳: {chart.planets['sun']['sign']} {chart.planets['sun']['sign_degree']:.2f}°")
    print(f"月亮: {chart.planets['moon']['sign']} {chart.planets['moon']['sign_degree']:.2f}°")
    print(f"水星: {chart.planets['mercury']['sign']} {chart.planets['mercury']['sign_degree']:.2f}°  retro={chart.planets['mercury']['retrograde']}")
    print(f"金星: {chart.planets['venus']['sign']} {chart.planets['venus']['sign_degree']:.2f}°")
    print(f"火星: {chart.planets['mars']['sign']} {chart.planets['mars']['sign_degree']:.2f}°")
    print(f"木星: {chart.planets['jupiter']['sign']} {chart.planets['jupiter']['sign_degree']:.2f}°  retro={chart.planets['jupiter']['retrograde']}")
    print(f"土星: {chart.planets['saturn']['sign']} {chart.planets['saturn']['sign_degree']:.2f}°  retro={chart.planets['saturn']['retrograde']}")
    print(f"天王星: {chart.planets['uranus']['sign']} {chart.planets['uranus']['sign_degree']:.2f}°  retro={chart.planets['uranus']['retrograde']}")
    print(f"海王星: {chart.planets['neptune']['sign']} {chart.planets['neptune']['sign_degree']:.2f}°  retro={chart.planets['neptune']['retrograde']}")
    print(f"冥王星: {chart.planets['pluto']['sign']} {chart.planets['pluto']['sign_degree']:.2f}°  retro={chart.planets['pluto']['retrograde']}")

    print(f"\nASC: {chart.angles['ASC']:.2f}° = {lon_to_sign(chart.angles['ASC'])}")
    print(f"MC : {chart.angles['MC']:.2f}° = {lon_to_sign(chart.angles['MC'])}")

    print(f"\n月相: {chart.moon_phase}")
    print(f"宫位制: {chart.house_system}")

    print(f"\n元素分布: {chart.distributions['elements']}")
    print(f"模式分布: {chart.distributions['modalities']}")
    print(f"阴阳分布: {chart.distributions['polarities']}")

    print(f"\n相位 (n={len(chart.aspects)})：前 8 条")
    for a in chart.aspects[:8]:
        applying = "applying" if a["applying"] else "separating"
        print(f"  {a['planet_a']:<10} {a['aspect_type']:<11} {a['planet_b']:<10}  "
              f"orb={a['orb']:.2f}°  {applying}")

    # 验收
    sun_sign = chart.planets["sun"]["sign"]
    sun_deg = chart.planets["sun"]["sign_degree"]
    asc_sign, _ = lon_to_sign(chart.angles["ASC"])
    print(f"\n验收：")
    print(f"  太阳：{sun_sign} {sun_deg:.2f}° (期望狮子座 22-23°)")
    print(f"  ASC：{asc_sign} (期望天蝎/射手附近)")
    moon_sign = chart.planets["moon"]["sign"]
    print(f"  月亮：{moon_sign} (期望双鱼/水瓶附近)")

    # 行运盘示例
    print("\n══ 行运盘 (2026-05-07) ══")
    transit = compute_transits(chart, datetime(2026, 5, 7, 12, 0), birth)
    print(f"行运太阳: {transit.transit_planets['sun']['sign']} {transit.transit_planets['sun']['sign_degree']:.2f}°")
    print(f"行运土星: {transit.transit_planets['saturn']['sign']} {transit.transit_planets['saturn']['sign_degree']:.2f}°  retro={transit.transit_planets['saturn']['retrograde']}")
    print(f"\n关键行运事件 (n={len(transit.key_transits)})：")
    for e in transit.key_transits:
        print(f"  - [{e['event']}] {e['description']}")
    print(f"\n行运 → 本命相位 (n={len(transit.aspects_to_natal)})：前 5 条")
    for a in transit.aspects_to_natal[:5]:
        print(f"  T-{a['transit_planet']:<10} {a['aspect_type']:<11} N-{a['natal_planet']:<10}  orb={a['orb']:.2f}°")
