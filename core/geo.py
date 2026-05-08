"""地名 → 经纬度智能匹配。

策略：分词 + 逐 token 查表 + 取最具体命中。
- 输入 "江苏 泰州 兴化"  → 命中"兴化"（县级）→ 用兴化经纬度
- 输入 "江苏 某不知名乡镇" → 命中"江苏"（省）→ 用省会经纬度（精度退化）
- 输入 "兴化"             → 命中"兴化"
- 输入 "Some Unknown Village" → 命中失败
"""
from __future__ import annotations
import json
from functools import lru_cache
from pathlib import Path
import re


_GEO_PATH = Path(__file__).resolve().parent.parent / "data" / "geo_cn.json"


@lru_cache(maxsize=1)
def _load_geo() -> dict:
    with open(_GEO_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


_SUFFIX_RE = re.compile(r"(省|市|县|区|州|盟|自治区|自治州|自治县|特别行政区|镇|乡|街道|村)$")


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


def resolve_geo(place: str) -> tuple[tuple[float, float], str, str]:
    """返回 ((lng, lat), match_kind, match_name)。

    match_kind:
      - "exact_city"      命中城市/县级表（高精度）
      - "exact_province"  命中省级（精度退化到省会）
      - "exact_overseas"  命中海外
      - "fuzzy_substring" 模糊子串命中
      - "fallback_beijing" 完全没命中（默认北京）

    匹配优先级（重要）：
      最右 token > 左 token，即"江苏 泰州 兴化"中"兴化"最优先（更具体）。
    """
    geo = _load_geo()
    cities = geo.get("cities", {})
    provinces = geo.get("provinces", {})
    overseas = geo.get("overseas", {})

    if not place or not place.strip():
        return (116.4074, 39.9042), "fallback_beijing", "默认北京"

    p_strip = place.strip()

    # 1) 整段原文（保留空格）做精确匹配——处理 "New York" / "Hong Kong" 这种带空格的英文地名
    if p_strip in cities:
        return tuple(cities[p_strip]), "exact_city", p_strip
    if p_strip in overseas:
        return tuple(overseas[p_strip]), "exact_overseas", p_strip
    if p_strip in provinces:
        return tuple(provinces[p_strip]), "exact_province", p_strip

    # 2) 整段去空格再试一次（兼容 "兴化市" / "广东省东莞市"）
    p_compact = re.sub(r"\s+", "", p_strip)
    if p_compact != p_strip:
        if p_compact in cities:
            return tuple(cities[p_compact]), "exact_city", p_compact
        if p_compact in overseas:
            return tuple(overseas[p_compact]), "exact_overseas", p_compact
        if p_compact in provinces:
            return tuple(provinces[p_compact]), "exact_province", p_compact

    # 3) 从右往左切 token：最具体的（最右）优先
    tokens = _tokens_right_to_left(p_strip)
    for tok in tokens:
        if tok in cities:
            return tuple(cities[tok]), "exact_city", tok
        if tok in overseas:
            return tuple(overseas[tok]), "exact_overseas", tok
    # 省级（落后于 city/overseas）
    for tok in tokens:
        if tok in provinces:
            return tuple(provinces[tok]), "exact_province", tok

    # 4) 模糊子串：在 cities/overseas/provinces 里找包含关系，越长越优先
    all_tables = [("city", cities), ("overseas", overseas), ("province", provinces)]
    best: tuple | None = None
    for kind, tbl in all_tables:
        for k, v in tbl.items():
            if len(k) < 2:
                continue
            if k in p_compact or k in p_strip:
                if not best or len(k) > len(best[2]):
                    best = (tuple(v), f"fuzzy_substring_{kind}", k)
    if best:
        return best  # type: ignore

    return (116.4074, 39.9042), "fallback_beijing", "默认北京"


# 测试
if __name__ == "__main__":
    cases = [
        "江苏 泰州 兴化",
        "兴化",
        "江苏",
        "上海",
        "Beijing",
        "纽约",
        "New York",
        "莱比锡",
        "兴化市",
        "某个完全不存在的小乡村",
        "广东省东莞市",
        "陕西西安",
        "江西省赣州市瑞金",  # 瑞金不在表里 → 应退到赣州
    ]
    for c in cases:
        coord, kind, name = resolve_geo(c)
        print(f"  {c:<25} → ({coord[0]:.3f}, {coord[1]:.3f})  [{kind}]  匹配: {name}")
