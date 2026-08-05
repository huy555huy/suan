"""地名 → 经纬度智能匹配。

策略：优先用 cpca 解析中国行政区划 adcode，再查本地坐标表。
本项目当前只做国内出生地与国内风水，不接海外出生地。事实层不做静默
代入：无法解析时抛出明确错误，让上层追问城市/区县或经纬度。
"""
from __future__ import annotations
import json
from functools import lru_cache
from pathlib import Path
import re
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


_GEO_PATH = Path(__file__).resolve().parent.parent / "data" / "geo_cn.json"
_ADMIN_GEO_PATH = Path(__file__).resolve().parent.parent / "data" / "geo_admin_cn.json"


class GeoResolutionError(ValueError):
    """Raised when a place name cannot be resolved without guessing."""


class TimezoneResolutionError(ValueError):
    """Raised when timezone cannot be inferred without guessing."""


@lru_cache(maxsize=1)
def _load_geo() -> dict:
    with open(_GEO_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _load_admin_geo() -> dict:
    if not _ADMIN_GEO_PATH.exists():
        return {"items": {}}
    with open(_ADMIN_GEO_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


_SUFFIX_RE = re.compile(r"(特别行政区|自治区|自治州|自治县|新区|地区|省|市|县|区|州|盟|镇|乡|街道|村)$")
_ASCII_RE = re.compile(r"[A-Za-z]")
_OVERSEAS_MARKERS = (
    "海外", "国外", "美国", "加拿大", "英国", "法国", "德国", "意大利", "西班牙",
    "澳大利亚", "新西兰", "日本", "韩国", "新加坡", "马来西亚", "泰国",
    "纽约", "洛杉矶", "旧金山", "西雅图", "芝加哥", "波士顿", "伯克利",
    "加州", "伦敦", "巴黎", "柏林", "东京", "大阪", "首尔", "悉尼",
)


def is_china_coordinate(longitude: float, latitude: float) -> bool:
    """粗边界校验：当前只接受中国境内常见经纬范围。"""
    return 73.0 <= float(longitude) <= 135.5 and 18.0 <= float(latitude) <= 54.5


def is_outside_domestic_place_text(place: str) -> bool:
    """Return True for place text that is outside the current domestic scope."""
    p = (place or "").strip()
    return bool(p) and (_ASCII_RE.search(p) is not None or any(marker in p for marker in _OVERSEAS_MARKERS))

_ALIASES = {
    "海淀": (116.298, 39.9593),
    "朝阳区": (116.4431, 39.9219),
    "朝阳": (116.4431, 39.9219),
    "浦东": (121.5447, 31.2222),
    "浦东新区": (121.5447, 31.2222),
    "西湖": (120.1303, 30.2592),
    "南山": (113.9304, 22.5333),
    "天河": (113.3612, 23.1247),
    "越秀": (113.267, 23.1291),
    "福田": (114.055, 22.5215),
    "罗湖": (114.1312, 22.5484),
}

_COMPACT_ALIASES = {
    "北京海淀": "海淀",
    "上海浦东": "浦东",
    "上海浦东新区": "浦东新区",
}


def _offset_for_zone(tz_name: str, local_dt: datetime | None = None) -> float:
    ref_dt = local_dt or datetime.now()
    try:
        zone = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise TimezoneResolutionError(
            f"运行环境缺少 IANA 时区数据库，无法读取 {tz_name}；请安装 tzdata。"
        ) from exc
    offset = ref_dt.replace(tzinfo=zone).utcoffset()
    if offset is None:
        raise TimezoneResolutionError(f"无法读取 {tz_name} 的历史时区偏移。")
    return offset.total_seconds() / 3600


def _tokens_right_to_left(place: str) -> list[str]:
    """把原文按分隔符切成 token，从右到左排（中文地名通常从大到小：省→市→县）。
    每个 token 同时返回去后缀的版本。"""
    s = re.sub(r"[\t　·,，/、\\\-]+", " ", place)
    raw_parts = [p for p in s.split() if p]
    out: list[str] = []
    seen: set[str] = set()
    for p in reversed(raw_parts):
        if p not in seen:
            out.append(p); seen.add(p)
        c = _SUFFIX_RE.sub("", p)
        if c and c != p and c not in seen:
            out.append(c); seen.add(c)
    return out


def _candidate_names(place: str) -> list[str]:
    p_strip = place.strip()
    p_compact = re.sub(r"\s+", "", p_strip)
    candidates: list[str] = []

    def add(value: str | None):
        if value and value not in candidates:
            candidates.append(value)

    add(p_strip)
    add(p_compact)
    add(_COMPACT_ALIASES.get(p_compact))

    for tok in _tokens_right_to_left(p_strip):
        add(tok)
        add(_COMPACT_ALIASES.get(tok))

    for alias, canonical in _COMPACT_ALIASES.items():
        if alias in p_compact:
            add(canonical)
    for alias in sorted(_ALIASES, key=len, reverse=True):
        if alias and alias in p_compact:
            add(alias)

    # 连续中文地名没有空格时，从右往左尝试最长后缀：江西省赣州市瑞金 -> 瑞金 / 赣州市瑞金...
    if re.search(r"[\u4e00-\u9fff]", p_compact):
        for i in range(len(p_compact)):
            suffix = p_compact[i:]
            add(suffix)
            add(_SUFFIX_RE.sub("", suffix))

    return candidates


def _lookup_name(name: str, cities: dict, provinces: dict) -> tuple[tuple[float, float], str, str] | None:
    if name in _ALIASES:
        coord = tuple(_ALIASES[name])
        if not is_china_coordinate(coord[0], coord[1]):
            raise GeoResolutionError("暂不支持海外出生地；请提供中国境内城市/区县，或只做不依赖出生地的项目。")
        return coord, "alias", name
    if name in cities:
        return tuple(cities[name]), "exact_city", name
    if name in provinces:
        return tuple(provinces[name]), "exact_province", name
    return None


def _resolve_cn_admin(place: str) -> tuple[tuple[float, float], str, str] | None:
    """Use cpca + local adcode coordinate table for Chinese administrative names."""
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import cpca
        df = cpca.transform([place])
        row = df.iloc[0]
    except Exception:
        return None

    adcode = row.get("adcode")
    if adcode is None:
        return None
    try:
        if adcode != adcode:  # NaN
            return None
    except Exception:
        return None

    code = str(int(adcode)) if isinstance(adcode, float) else str(adcode)
    items = _load_admin_geo().get("items", {})
    item = items.get(code)
    if not item:
        return None

    name = item["name"]
    return (float(item["lng"]), float(item["lat"])), "admin_adcode", name


def resolve_geo(place: str) -> tuple[tuple[float, float], str, str]:
    """返回 ((lng, lat), match_kind, match_name)。

    match_kind:
      - "admin_adcode"    命中中国行政区划 adcode（优先）
      - "exact_city"      命中城市/县级表（高精度）
      - "fuzzy_substring" 模糊子串命中

    匹配优先级（重要）：
      最右 token > 左 token，即"江苏 泰州 兴化"中"兴化"最优先（更具体）。
    """
    geo = _load_geo()
    cities = geo.get("cities", {})
    provinces = geo.get("provinces", {})

    if not place or not place.strip():
        raise GeoResolutionError("出生地未填写；需要城市/区县，或直接提供经纬度。")

    p_strip = place.strip()
    p_compact = re.sub(r"\s+", "", p_strip)
    if is_outside_domestic_place_text(p_strip):
        raise GeoResolutionError("暂不支持海外出生地；当前仅接受中国境内中文城市/区县，或中国境内经纬度。")

    admin_result = _resolve_cn_admin(p_strip)
    if admin_result:
        return admin_result

    for candidate in _candidate_names(p_strip):
        result = _lookup_name(candidate, cities, provinces)
        if result:
            if result[1] == "exact_province":
                raise GeoResolutionError(
                    f"出生地「{place}」只到省级（{result[2]}）；请补充城市/区县，或直接提供经纬度。"
                )
            return result

    # 4) 模糊子串：在 cities/provinces 里找包含关系，越长越优先
    all_tables = [("city", cities), ("province", provinces)]
    best: tuple | None = None
    for kind, tbl in all_tables:
        for k, v in tbl.items():
            if len(k) < 2:
                continue
            if k in p_compact or k in p_strip:
                if not best or len(k) > len(best[2]):
                    best = (tuple(v), f"fuzzy_substring_{kind}", k)
    if best:
        if best[1] == "fuzzy_substring_province":
            raise GeoResolutionError(
                f"出生地「{place}」只匹配到省级（{best[2]}）；请补充城市/区县，或直接提供经纬度。"
            )
        return best  # type: ignore

    raise GeoResolutionError(f"无法识别出生地「{place}」；请补充城市/区县，或直接提供经纬度。")


def infer_timezone_offset(place: str, matched_name: str, longitude: float, latitude: float,
                          local_dt: datetime | None = None) -> tuple[float, str, str]:
    """根据地点推断出生地时区偏移。

    返回 (offset_hours, confidence, source)，confidence 为 exact。
    无法可靠推断时抛出 TimezoneResolutionError，不默认按 UTC+8。
    """
    if not is_china_coordinate(longitude, latitude):
        raise TimezoneResolutionError("暂不支持海外出生地时区推断；本项目当前只处理中国境内出生地。")

    geo = _load_geo()
    admin_items = _load_admin_geo().get("items", {})
    if matched_name in geo.get("cities", {}) or matched_name in geo.get("provinces", {}):
        return _offset_for_zone("Asia/Shanghai", local_dt), "exact", "Asia/Shanghai"
    if any(item.get("name") == matched_name for item in admin_items.values()):
        return _offset_for_zone("Asia/Shanghai", local_dt), "exact", "Asia/Shanghai"
    return _offset_for_zone("Asia/Shanghai", local_dt), "exact", "Asia/Shanghai"


# 测试
if __name__ == "__main__":
    cases = [
        "江苏 泰州 兴化",
        "兴化",
        "江苏",
        "上海",
        "兴化市",
        "某个完全不存在的小乡村",
        "广东省东莞市",
        "陕西西安",
        "江西省赣州市瑞金",  # 瑞金不在表里 → 应退到赣州
    ]
    for c in cases:
        coord, kind, name = resolve_geo(c)
        print(f"  {c:<25} → ({coord[0]:.3f}, {coord[1]:.3f})  [{kind}]  匹配: {name}")
