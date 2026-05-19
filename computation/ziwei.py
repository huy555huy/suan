"""紫微斗数排盘适配器。

事实排盘交给 ``iztro-py``，本模块只负责：
    1. 把 BirthInfo 的标准时间转换为本项目约定的排盘时间；
    2. 调用 iztro-py 生成紫微盘；
    3. 适配到现有 ZiweiChart schema，并保留原始盘面用于审计。
"""
from __future__ import annotations

from datetime import datetime
from importlib.metadata import version
from typing import Any

from core.schemas import BirthInfo, ZiweiChart
from computation.calendar import to_true_solar_time


GENDER_TO_IZTRO = {
    "male": "男",
    "female": "女",
}


def _translation_maps() -> dict[str, Any]:
    from iztro_py.i18n.locales.zh_CN import translations

    return translations


def _translate_star(name: str, category: str) -> str:
    translations = _translation_maps()
    if category == "major":
        return translations["stars"]["major"].get(name, name)
    if category == "minor":
        return translations["stars"]["minor"].get(name, name)
    return translations.get(name, name)


def _translate_stem(name: str) -> str:
    return _translation_maps()["heavenlyStem"].get(name, name)


def _translate_branch(name: str) -> str:
    return _translation_maps()["earthlyBranch"].get(name, name)


def _translate_palace(name: str) -> str:
    return _translation_maps()["palaces"].get(name, name)


def _effective_datetime(birth: BirthInfo) -> datetime:
    dt = datetime(birth.year, birth.month, birth.day, birth.hour, birth.minute)
    if not birth.use_true_solar_time:
        return dt
    return to_true_solar_time(dt, birth.longitude, birth.timezone_offset)


def _ziwei_time_index(dt: datetime) -> int:
    """iztro-py 时辰索引：0=早子，1=丑，...，11=亥，12=晚子。"""
    if dt.hour == 23:
        return 12
    if dt.hour == 0:
        return 0
    return (dt.hour + 1) // 2


def _star_detail(star: dict[str, Any], category: str) -> dict[str, Any]:
    mutagen = star.get("mutagen")
    return {
        "name": _translate_star(star["name"], category),
        "raw_name": star["name"],
        "category": category,
        "type": star.get("type"),
        "scope": star.get("scope"),
        "brightness": star.get("brightness"),
        "mutagen": mutagen,
        "si_hua": f"化{mutagen}" if mutagen else None,
    }


def _palace_to_schema(palace: dict[str, Any]) -> dict[str, Any]:
    major = [_star_detail(s, "major") for s in palace.get("major_stars", [])]
    minor = [_star_detail(s, "minor") for s in palace.get("minor_stars", [])]
    adjective = [_star_detail(s, "adjective") for s in palace.get("adjective_stars", [])]
    stem = _translate_stem(palace["heavenly_stem"])
    branch = _translate_branch(palace["earthly_branch"])
    si_hua = [
        f'{s["name"]}{s["si_hua"]}'
        for s in major + minor + adjective
        if s.get("si_hua")
    ]
    decadal = palace.get("decadal") or {}
    decadal_range = decadal.get("range") or ()

    return {
        "index": palace.get("index"),
        "name": _translate_palace(palace["name"]),
        "raw_name": palace["name"],
        "branch": branch,
        "stem": stem,
        "ganzhi": f"{stem}{branch}",
        "stars": [s["name"] for s in major],
        "auxiliary": [s["name"] for s in minor + adjective],
        "star_details": {
            "major": major,
            "minor": minor,
            "adjective": adjective,
        },
        "si_hua": si_hua,
        "is_body_palace": palace.get("is_body_palace", False),
        "is_original_palace": palace.get("is_original_palace", False),
        "changsheng12": palace.get("changsheng12"),
        "boshi12": palace.get("boshi12"),
        "jiangqian12": palace.get("jiangqian12"),
        "suiqian12": palace.get("suiqian12"),
        "decadal": {
            "range": list(decadal_range),
            "heavenly_stem": _translate_stem(decadal.get("heavenly_stem", "")),
            "earthly_branch": _translate_branch(decadal.get("earthly_branch", "")),
        },
        "ages": palace.get("ages", []),
    }


def _collect_si_hua(palaces: list[dict[str, Any]]) -> dict[str, str]:
    si_hua: dict[str, str] = {}
    for palace in palaces:
        for group_name in ("major_stars", "minor_stars", "adjective_stars"):
            category = "adjective"
            if group_name == "major_stars":
                category = "major"
            elif group_name == "minor_stars":
                category = "minor"
            for star in palace.get(group_name, []):
                mutagen = star.get("mutagen")
                if mutagen:
                    si_hua[f"化{mutagen}"] = _translate_star(star["name"], category)
    return si_hua


def _find_palace_by_branch(palaces: list[dict[str, Any]], raw_branch: str) -> str:
    branch = _translate_branch(raw_branch)
    for palace in palaces:
        if palace["branch"] == branch:
            return palace["name"]
    raise ValueError(f"紫微盘缺少地支 {branch} 对应宫位")


def _translate_raw_star(name: str | None) -> str | None:
    if not name:
        return None
    translations = _translation_maps()
    return (
        translations["stars"]["major"].get(name)
        or translations["stars"]["minor"].get(name)
        or translations.get(name)
        or name
    )


def _palace_lookup(palaces: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {p["name"]: p for p in palaces}


def _branch_lookup(palaces: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {p["branch"]: p for p in palaces}


def _opposite_branch(branch: str) -> str:
    branches = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
    return branches[(branches.index(branch) + 6) % 12]


def _trine_branches(branch: str) -> list[str]:
    groups = [
        {"申", "子", "辰"},
        {"寅", "午", "戌"},
        {"巳", "酉", "丑"},
        {"亥", "卯", "未"},
    ]
    for group in groups:
        if branch in group:
            return [b for b in ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"] if b in group]
    return [branch]


def _san_fang_si_zheng(palace: dict[str, Any], branch_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    branch = palace["branch"]
    trine = _trine_branches(branch)
    opposite = _opposite_branch(branch)
    related_branches = list(dict.fromkeys(trine + [opposite]))
    related_palaces = [branch_map[b] for b in related_branches if b in branch_map]
    return {
        "palace": palace["name"],
        "branch": branch,
        "trine_branches": trine,
        "opposite_branch": opposite,
        "related": [
            {
                "name": p["name"],
                "branch": p["branch"],
                "stars": p["stars"],
                "si_hua": p["si_hua"],
                "auxiliary": p["auxiliary"],
            }
            for p in related_palaces
        ],
        "major_stars": [
            star
            for p in related_palaces
            for star in p["stars"]
        ],
        "si_hua": [
            hua
            for p in related_palaces
            for hua in p["si_hua"]
        ],
    }


def _domain_palace_map() -> dict[str, list[str]]:
    return {
        "self": ["命宫", "福德宫", "迁移宫"],
        "career": ["官禄宫", "命宫", "迁移宫", "财帛宫"],
        "wealth": ["财帛宫", "田宅宫", "官禄宫"],
        "relationship": ["夫妻宫", "福德宫", "迁移宫"],
        "health": ["疾厄宫", "福德宫", "命宫"],
        "family": ["父母宫", "兄弟宫", "子女宫", "田宅宫"],
    }


def _build_ziwei_focus(palaces: list[dict[str, Any]], life_palace: str,
                       body_palace: str) -> dict[str, Any]:
    name_map = _palace_lookup(palaces)
    branch_map = _branch_lookup(palaces)
    palace_focus = {}
    for palace_name, palace in name_map.items():
        palace_focus[palace_name] = _san_fang_si_zheng(palace, branch_map)
    domain_focus = {}
    for domain, palace_names in _domain_palace_map().items():
        domain_focus[domain] = {
            name: palace_focus[name]
            for name in palace_names
            if name in palace_focus
        }
    return {
        "life_palace": palace_focus.get(life_palace),
        "body_palace": palace_focus.get(body_palace),
        "domains": domain_focus,
    }


def _ziwei_calibration_questions(life_palace: str, body_palace: str) -> list[dict[str, str]]:
    return [
        {
            "field": "birth_time_source",
            "question": "出生时间来自医院记录还是家人记忆？是否可能有 30 分钟以上误差？",
            "why": "紫微命宫、身宫和主星落宫对时辰非常敏感。",
        },
        {
            "field": "major_events",
            "question": "请给出 3 个已发生的大事年份，例如搬家、升学、入职、分手、结婚或家中变故。",
            "why": "用大限/流年事件回看，可以验证命宫与身宫是否吻合。",
        },
        {
            "field": "life_body_feedback",
            "question": f"你更像{life_palace}的先天性格，还是{body_palace}对应的后天行为模式？",
            "why": "命宫看底色，身宫看后天着力点；反馈可帮助校盘。",
        },
    ]


def compute_ziwei(birth: BirthInfo) -> ZiweiChart:
    """计算紫微斗数命盘。"""
    if birth.gender not in GENDER_TO_IZTRO:
        raise ValueError("紫微斗数排大限需要明确男/女；请补充 gender=male 或 gender=female。")

    from iztro_py import astro

    input_dt = datetime(birth.year, birth.month, birth.day, birth.hour, birth.minute)
    effective_dt = _effective_datetime(birth)
    time_index = _ziwei_time_index(effective_dt)
    solar_date = effective_dt.strftime("%Y-%m-%d")
    chart = astro.by_solar(solar_date, time_index, GENDER_TO_IZTRO[birth.gender], True, "zh-CN")
    raw = chart.model_dump()

    palaces = [_palace_to_schema(p) for p in raw["palaces"]]
    main_stars = {p["name"]: list(p["stars"]) for p in palaces if p["stars"]}
    da_xian: list[dict[str, Any]] = []
    for palace in palaces:
        decadal_range = palace["decadal"]["range"]
        if len(decadal_range) == 2:
            da_xian.append({
                "palace_name": palace["name"],
                "branch": palace["branch"],
                "stem": palace["stem"],
                "age_start": decadal_range[0],
                "age_end": decadal_range[1],
            })

    life_palace = _find_palace_by_branch(palaces, raw["earthly_branch_of_soul_palace"])
    body_palace = _find_palace_by_branch(palaces, raw["earthly_branch_of_body_palace"])

    metadata: dict[str, Any] = {
        "engine": "iztro-py",
        "engine_version": version("iztro-py"),
        "input_datetime": input_dt.isoformat(),
        "effective_datetime": effective_dt.isoformat(),
        "use_true_solar_time": birth.use_true_solar_time,
        "timezone_offset": birth.timezone_offset,
        "longitude": birth.longitude,
        "time_index": time_index,
        "time": raw.get("time"),
        "time_range": raw.get("time_range"),
        "solar_date": raw.get("solar_date"),
        "lunar_date": raw.get("lunar_date"),
        "chinese_date": raw.get("chinese_date"),
        "raw_lunar_date": raw.get("raw_lunar_date"),
        "raw_chinese_date": raw.get("raw_chinese_date"),
        "lunar_year_used": raw.get("raw_lunar_date", {}).get("year"),
        "lunar_month_used": raw.get("raw_lunar_date", {}).get("month"),
        "lunar_day_used": raw.get("raw_lunar_date", {}).get("day"),
        "lunar_is_leap_month": raw.get("raw_lunar_date", {}).get("is_leap_month"),
        "zodiac": raw.get("zodiac"),
        "sign": raw.get("sign"),
        "soul_palace_branch": _translate_branch(raw["earthly_branch_of_soul_palace"]),
        "body_palace_branch": _translate_branch(raw["earthly_branch_of_body_palace"]),
        "soul_star": _translate_raw_star(raw.get("soul")),
        "body_star": _translate_raw_star(raw.get("body")),
        "focus": _build_ziwei_focus(palaces, life_palace, body_palace),
        "calibration_questions": _ziwei_calibration_questions(life_palace, body_palace),
        "raw_chart": raw,
    }

    return ZiweiChart(
        palaces=palaces,
        main_stars=main_stars,
        body_palace=body_palace,
        life_palace=life_palace,
        five_element_bureau=raw["five_elements_class"],
        si_hua=_collect_si_hua(raw["palaces"]),
        da_xian=da_xian,
        liu_nian=None,
        school="iztro",
        metadata=metadata,
    )


if __name__ == "__main__":
    import json

    demo_birth = BirthInfo(
        name="测试",
        gender="female",
        year=1991,
        month=8,
        day=15,
        hour=14,
        minute=30,
        location_name="北京",
        longitude=116.4074,
        latitude=39.9042,
        timezone_offset=8.0,
        use_true_solar_time=True,
    )
    print(json.dumps(compute_ziwei(demo_birth).model_dump(), ensure_ascii=False, indent=2))
