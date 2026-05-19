"""西方占星计算引擎。

只使用 Swiss Ephemeris (`pyswisseph`)。缺少 Swiss Ephemeris 数据文件时直接
报错，不用 Moshier 或自写天文近似替代。
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.schemas import AstroNatalChart, BirthInfo, TransitChart

try:
    import swisseph as swe
except Exception as exc:  # pragma: no cover - dependency guard
    swe = None
    _SWISSEPH_IMPORT_ERROR = exc
else:
    _SWISSEPH_IMPORT_ERROR = None


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
SIGN_MODALITIES = {
    "白羊座": "cardinal", "巨蟹座": "cardinal", "天秤座": "cardinal", "摩羯座": "cardinal",
    "金牛座": "fixed", "狮子座": "fixed", "天蝎座": "fixed", "水瓶座": "fixed",
    "双子座": "mutable", "处女座": "mutable", "射手座": "mutable", "双鱼座": "mutable",
}
SIGN_POLARITY = {
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
SWISSEPH_BODIES = {
    "sun": "SUN",
    "moon": "MOON",
    "mercury": "MERCURY",
    "venus": "VENUS",
    "mars": "MARS",
    "jupiter": "JUPITER",
    "saturn": "SATURN",
    "uranus": "URANUS",
    "neptune": "NEPTUNE",
    "pluto": "PLUTO",
    "north_node": "MEAN_NODE",
    "chiron": "CHIRON",
}

ASPECTS_DEF = {
    "conjunction": (0.0, 8.0),
    "sextile": (60.0, 6.0),
    "square": (90.0, 8.0),
    "trine": (120.0, 8.0),
    "opposition": (180.0, 8.0),
}

EPHE_PATH = Path(__file__).resolve().parent.parent / "data" / "swisseph"
REQUIRED_EPHE_FILES = {
    "sepl_18.se1": {
        "size": 484061,
        "sha256": "b8e657c1f5a9c51821ef973baf233a3c07137101e35b95e00ac0e9eeea7fbeb8",
    },
    "semo_18.se1": {
        "size": 1304771,
        "sha256": "7034c7825a0fef2f660d99161aa8e60429adfa315d269ac68042ef5a5e6319bf",
    },
    "seas_18.se1": {
        "size": 223004,
        "sha256": "6559b0fc637eaed42ae747187cfd1426540d12b08114603bc39fd13f3bf80c83",
    },
}
_EPHEMERIS_VERIFIED_SIGNATURE: tuple[tuple[str, int, int, str, int], ...] | None = None


class EphemerisError(RuntimeError):
    """Swiss Ephemeris cannot compute the requested chart."""


def _require_swe():
    global _EPHEMERIS_VERIFIED_SIGNATURE
    if swe is None:
        raise EphemerisError(f"pyswisseph 未安装或加载失败：{_SWISSEPH_IMPORT_ERROR}")
    missing = [name for name in REQUIRED_EPHE_FILES if not (EPHE_PATH / name).is_file()]
    if missing:
        raise EphemerisError(f"Swiss Ephemeris 数据文件缺失：{', '.join(missing)}")

    signature = tuple(
        (
            name,
            int(expected["size"]),
            int((EPHE_PATH / name).stat().st_size),
            str(expected["sha256"]),
            int((EPHE_PATH / name).stat().st_mtime_ns),
        )
        for name, expected in sorted(REQUIRED_EPHE_FILES.items())
    )
    if signature != _EPHEMERIS_VERIFIED_SIGNATURE:
        mismatched: list[str] = []
        for name, expected in REQUIRED_EPHE_FILES.items():
            path = EPHE_PATH / name
            if path.stat().st_size != expected["size"]:
                mismatched.append(f"{name}(size)")
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != expected["sha256"]:
                mismatched.append(f"{name}(sha256)")
        if mismatched:
            raise EphemerisError(f"Swiss Ephemeris 数据文件校验失败：{', '.join(mismatched)}")
        _EPHEMERIS_VERIFIED_SIGNATURE = signature
    swe.set_ephe_path(str(EPHE_PATH))
    return swe


def _norm360(x: float) -> float:
    return x % 360.0


def _norm180(x: float) -> float:
    x = x % 360.0
    if x > 180.0:
        x -= 360.0
    return x


def lon_to_sign(longitude: float) -> tuple[str, float]:
    lon = _norm360(longitude)
    sign_idx = int(lon // 30)
    return ZODIAC_SIGNS[sign_idx], lon - 30.0 * sign_idx


def _local_to_utc(year: int, month: int, day: int, hour: int, minute: int,
                  tz_offset: float) -> datetime:
    local = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
    return local - timedelta(hours=tz_offset)


def _swe_julday(dt_utc: datetime) -> float:
    s = _require_swe()
    hour = dt_utc.hour + dt_utc.minute / 60 + dt_utc.second / 3600 + dt_utc.microsecond / 3_600_000_000
    return s.julday(dt_utc.year, dt_utc.month, dt_utc.day, hour)


def _planet_position(name: str, jd_ut: float) -> tuple[float, float, bool]:
    s = _require_swe()
    body = getattr(s, SWISSEPH_BODIES[name])
    try:
        values, _retflags = s.calc_ut(jd_ut, body, s.FLG_SWIEPH | s.FLG_SPEED)
    except Exception as exc:
        raise EphemerisError(
            "Swiss Ephemeris 数据文件缺失或不可用，无法计算占星盘；"
            "请安装官方 ephemeris files 并配置 swisseph path。"
        ) from exc
    lon = _norm360(values[0])
    speed = values[3]
    retro = speed < 0 and name not in ("sun", "moon")
    return lon, speed, retro


def _houses(jd_ut: float, latitude: float, longitude: float,
            house_system: str) -> tuple[list[float], dict[str, float], str]:
    s = _require_swe()
    code = {"placidus": b"P", "whole_sign": b"W"}.get(house_system)
    if code is None:
        raise ValueError(f"未知 house_system: {house_system}")

    try:
        cusps_raw, ascmc = s.houses_ex(jd_ut, latitude, longitude, code)
        cusps = [_norm360(float(c)) for c in cusps_raw[:12]]
        used_system = house_system
    except Exception as exc:
        raise EphemerisError(f"Swiss Ephemeris 无法计算 {house_system} 宫位。") from exc

    angles = {
        "ASC": _norm360(float(ascmc[0])),
        "MC": _norm360(float(ascmc[1])),
        "ARMC": _norm360(float(ascmc[2])),
        "Vertex": _norm360(float(ascmc[3])),
    }
    angles["DSC"] = _norm360(angles["ASC"] + 180)
    angles["IC"] = _norm360(angles["MC"] + 180)
    return cusps, angles, used_system


def planet_in_house(planet_lon: float, house_cusps: list[float]) -> int:
    for i in range(12):
        c1 = house_cusps[i]
        c2 = house_cusps[(i + 1) % 12]
        if c1 <= c2:
            in_house = c1 <= planet_lon < c2
        else:
            in_house = planet_lon >= c1 or planet_lon < c2
        if in_house:
            return i + 1
    raise ValueError(f"行星黄经 {planet_lon} 无法落入宫位。")


def compute_aspect(lon_a: float, lon_b: float) -> tuple[str, float] | None:
    diff = abs(_norm180(lon_a - lon_b))
    for name, (target, orb) in ASPECTS_DEF.items():
        delta = abs(diff - target)
        if delta <= orb:
            return name, delta
    return None


def is_applying_aspect(lon_a: float, lon_b: float, speed_a: float,
                       speed_b: float, target_angle: float) -> bool:
    diff_now = abs(_norm180(lon_a - lon_b))
    diff_next = abs(_norm180((lon_a + speed_a * 0.01) - (lon_b + speed_b * 0.01)))
    return abs(diff_next - target_angle) < abs(diff_now - target_angle)


def moon_phase_name(sun_lon: float, moon_lon: float) -> str:
    diff = (moon_lon - sun_lon) % 360
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


def compute_natal_chart(birth: BirthInfo, house_system: str = "placidus") -> AstroNatalChart:
    utc_dt = _local_to_utc(
        birth.year, birth.month, birth.day, birth.hour, birth.minute,
        birth.timezone_offset,
    )
    jd = _swe_julday(utc_dt)

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
        }

    cusps, angles_all, used_system = _houses(jd, birth.latitude, birth.longitude, house_system)
    houses: list[dict] = []
    for i, cusp in enumerate(cusps):
        sign, deg = lon_to_sign(cusp)
        houses.append({
            "house_id": i + 1,
            "cusp_longitude": round(cusp, 4),
            "sign": sign,
            "sign_en": ZODIAC_SIGNS_EN[ZODIAC_SIGNS.index(sign)],
            "sign_degree": round(deg, 4),
            "ruler": SIGN_RULERS[sign],
        })

    for planet in planets.values():
        planet["house"] = planet_in_house(planet["longitude"], cusps)

    aspects: list[dict] = []
    names = list(planets.keys()) + ["ASC", "MC"]
    coords = {name: planets[name]["longitude"] for name in planets}
    coords["ASC"] = angles_all["ASC"]
    coords["MC"] = angles_all["MC"]
    speeds = {name: planets[name]["speed_per_day"] for name in planets}
    speeds["ASC"] = 360.0
    speeds["MC"] = 360.0
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            asp = compute_aspect(coords[a], coords[b])
            if asp is None:
                continue
            asp_name, orb = asp
            target = ASPECTS_DEF[asp_name][0]
            aspects.append({
                "planet_a": a,
                "planet_b": b,
                "aspect_type": asp_name,
                "exact_angle": target,
                "orb": round(orb, 3),
                "applying": is_applying_aspect(coords[a], coords[b], speeds[a], speeds[b], target),
            })

    main_planets = ["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto"]
    distributions = {
        "elements": {"fire": 0, "earth": 0, "air": 0, "water": 0},
        "modalities": {"cardinal": 0, "fixed": 0, "mutable": 0},
        "polarities": {"yang": 0, "yin": 0},
    }
    for name in main_planets:
        planet = planets[name]
        distributions["elements"][planet["element"]] += 1
        distributions["modalities"][planet["modality"]] += 1
        distributions["polarities"][planet["polarity"]] += 1

    return AstroNatalChart(
        planets=planets,
        angles={
            "ASC": round(angles_all["ASC"], 4),
            "MC": round(angles_all["MC"], 4),
            "DSC": round(angles_all["DSC"], 4),
            "IC": round(angles_all["IC"], 4),
        },
        houses=houses,
        aspects=aspects,
        distributions=distributions,
        moon_phase=moon_phase_name(planets["sun"]["longitude"], planets["moon"]["longitude"]),
        house_system=used_system,
        school="modern_psychological",
        metadata={
            "jd": round(jd, 6),
            "utc": utc_dt.isoformat(),
            "ephemeris": "swisseph",
            "swisseph_version": getattr(_require_swe(), "version", ""),
            "armc": round(angles_all["ARMC"], 4),
            "vertex": round(angles_all["Vertex"], 4),
            "n_aspects": len(aspects),
        },
    )


def compute_transits(natal: AstroNatalChart, target_date: datetime,
                     birth: BirthInfo) -> TransitChart:
    if target_date.tzinfo is None:
        utc_dt = (target_date - timedelta(hours=birth.timezone_offset)).replace(tzinfo=timezone.utc)
    else:
        utc_dt = target_date.astimezone(timezone.utc)
    jd = _swe_julday(utc_dt)

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

    aspects_to_natal: list[dict] = []
    for tname, tp in transit_planets.items():
        for nname, np_ in natal.planets.items():
            asp = compute_aspect(tp["longitude"], np_["longitude"])
            if asp is None:
                continue
            asp_name, orb = asp
            target = ASPECTS_DEF[asp_name][0]
            aspects_to_natal.append({
                "transit_planet": tname,
                "natal_planet": nname,
                "aspect_type": asp_name,
                "exact_angle": target,
                "orb": round(orb, 3),
                "applying": is_applying_aspect(tp["longitude"], np_["longitude"], tp["speed_per_day"], 0.0, target),
            })

    key_transits: list[dict] = []
    sat_diff = abs(_norm180(transit_planets["saturn"]["longitude"] - natal.planets["saturn"]["longitude"]))
    if sat_diff < 3.0:
        key_transits.append({"event": "saturn_return", "orb": round(sat_diff, 3)})
    if transit_planets["saturn"]["retrograde"]:
        key_transits.append({"event": "saturn_retrograde", "current_sign": transit_planets["saturn"]["sign"]})
    jup_diff = abs(_norm180(transit_planets["jupiter"]["longitude"] - natal.planets["jupiter"]["longitude"]))
    if jup_diff < 3.0:
        key_transits.append({"event": "jupiter_return", "orb": round(jup_diff, 3)})
    if transit_planets["mercury"]["retrograde"]:
        key_transits.append({"event": "mercury_retrograde", "current_sign": transit_planets["mercury"]["sign"]})
    if transit_planets["mars"]["retrograde"]:
        key_transits.append({"event": "mars_retrograde", "current_sign": transit_planets["mars"]["sign"]})
    ura_diff = abs(_norm180(transit_planets["uranus"]["longitude"] - natal.planets["uranus"]["longitude"]))
    if abs(ura_diff - 180) < 3.0:
        key_transits.append({"event": "uranus_opposition", "orb": round(abs(ura_diff - 180), 3)})

    return TransitChart(
        target_date=utc_dt.isoformat(),
        transit_planets=transit_planets,
        aspects_to_natal=aspects_to_natal,
        key_transits=key_transits,
        metadata={
            "jd": round(jd, 6),
            "ephemeris": "swisseph",
            "swisseph_version": getattr(_require_swe(), "version", ""),
            "n_aspects_to_natal": len(aspects_to_natal),
            "n_key_events": len(key_transits),
        },
    )
