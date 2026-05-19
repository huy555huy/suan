"""Input contracts for chart computation.

事实层只接受足够的信息。缺字段时返回可追问的问题，不在计算层偷放默认值。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


BIRTH_REQUIRED_CHARTS = {"bazi", "ziwei", "natal_astro", "transit_astro", "numerology"}
TIME_SENSITIVE_CHARTS = {"bazi", "ziwei", "natal_astro", "transit_astro"}
PLACE_SENSITIVE_CHARTS = {"bazi", "ziwei", "natal_astro", "transit_astro"}


@dataclass
class IntakeIssue:
    field: str
    message: str
    blocking: bool = True


@dataclass
class ChartIntake:
    chart_type: str
    ok: bool
    issues: list[IntakeIssue] = field(default_factory=list)

    @property
    def blocking_messages(self) -> list[str]:
        return [i.message for i in self.issues if i.blocking]


class IntakeError(ValueError):
    """Raised when a requested chart lacks mandatory inputs."""

    def __init__(self, chart_type: str, issues: list[IntakeIssue]):
        self.chart_type = chart_type
        self.issues = issues
        super().__init__("；".join(i.message for i in issues if i.blocking))


def _valid_date(date: str | None) -> bool:
    if not date:
        return False
    try:
        datetime.strptime(date, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _valid_time(time_value: str | None) -> bool:
    if not time_value:
        return False
    try:
        datetime.strptime(time_value, "%H:%M")
        return True
    except ValueError:
        return False


def _valid_datetime(value: str | None) -> bool:
    if not value:
        return False
    try:
        datetime.fromisoformat(value)
        return True
    except ValueError:
        return False


def _explicit_timezone(profile: dict[str, Any]) -> bool:
    if profile.get("timezone_offset") is not None:
        return True
    place = (profile.get("place") or "").strip()
    if not place:
        return False
    try:
        from core.geo import infer_timezone_offset, resolve_geo

        (lng, lat), _kind, matched = resolve_geo(place)
        infer_timezone_offset(place, matched, float(lng), float(lat), None)
        return True
    except Exception:
        return False


def validate_profile_for_birthinfo(profile: dict[str, Any]) -> list[IntakeIssue]:
    """Validate the minimum input needed to construct BirthInfo."""
    issues: list[IntakeIssue] = []
    if not _valid_date(profile.get("date")):
        issues.append(IntakeIssue("date", "请补充阳历出生日期，格式为 YYYY-MM-DD。"))
    if not _valid_time(profile.get("time")):
        issues.append(IntakeIssue("time", "请补充出生时间，精确到分钟；未知时辰不能生成完整盘面。"))
    has_place = bool((profile.get("place") or "").strip())
    has_coord = profile.get("longitude") is not None and profile.get("latitude") is not None
    if not has_place and not has_coord:
        issues.append(IntakeIssue("place", "请补充出生地城市/区县，或直接提供经纬度。"))
    if has_coord:
        from core.geo import is_china_coordinate

        if not is_china_coordinate(float(profile["longitude"]), float(profile["latitude"])):
            issues.append(IntakeIssue("place", "当前只支持中国境内出生地；海外出生地暂不计算。"))
    return issues


def validate_chart_request(chart_type: str, profile: dict[str, Any], question: str = "") -> ChartIntake:
    """Return chart-specific intake requirements."""
    issues: list[IntakeIssue] = []

    if chart_type in BIRTH_REQUIRED_CHARTS:
        issues.extend(validate_profile_for_birthinfo(profile))

    if chart_type in TIME_SENSITIVE_CHARTS and profile.get("unknownTime"):
        issues.append(IntakeIssue(
            "time",
            f"{chart_type} 需要出生时辰；未知时辰只能做低精度参考，不应生成完整盘面。",
        ))

    if chart_type in PLACE_SENSITIVE_CHARTS:
        has_place = bool((profile.get("place") or "").strip())
        has_coord = profile.get("longitude") is not None and profile.get("latitude") is not None
        if not has_place and not has_coord:
            issues.append(IntakeIssue(
                "place",
                f"{chart_type} 需要出生地用于真太阳时/时区/宫位校准。",
            ))
        if not _explicit_timezone(profile):
            issues.append(IntakeIssue(
                "timezone_offset",
                f"{chart_type} 需要可验证的出生地时区；请提供 timezone_offset 或更明确的出生地。",
            ))

    if chart_type in {"bazi", "ziwei"} and profile.get("gender") not in ("male", "female"):
        issues.append(IntakeIssue(
            "gender",
            f"{chart_type} 排大运/大限需要明确男/女；请补充 gender=male 或 gender=female。",
        ))

    if chart_type == "hexagram" and not question.strip():
        issues.append(IntakeIssue("question", "易经/六爻需要一个具体问题，不能只问泛泛运势。"))
    if chart_type == "hexagram":
        has_numbers = isinstance(profile.get("hexagram_numbers"), list) and len(profile["hexagram_numbers"]) in (2, 3)
        has_coins = isinstance(profile.get("coin_results"), list) and len(profile["coin_results"]) == 6
        has_divination_time = _valid_datetime(profile.get("divination_time"))
        if not (has_numbers or has_coins or has_divination_time):
            issues.append(IntakeIssue(
                "divination_input",
                "易经起卦需要用户提供数字、六次铜钱结果，或明确起卦时间；不能由系统随机或偷偷取当前时间。",
            ))
        if not has_divination_time:
            issues.append(IntakeIssue(
                "divination_time",
                "易经盘需要明确起卦时间用于日辰/六神计算，不能默认取系统当前时间。",
            ))

    if chart_type == "tarot" and not question.strip():
        issues.append(IntakeIssue("question", "塔罗需要一个具体问题或当下情境。"))
    if chart_type == "tarot":
        if not profile.get("tarot_spread"):
            issues.append(IntakeIssue("tarot_spread", "塔罗需要用户明确牌阵；不能默认使用某个牌阵。"))
        card_indexes = profile.get("tarot_card_indexes")
        if card_indexes is None:
            issues.append(IntakeIssue(
                "tarot_card_indexes",
                "塔罗需要用户抽牌结果；不能由系统代替用户随机抽牌。",
            ))
        elif not isinstance(card_indexes, list) or not card_indexes:
            issues.append(IntakeIssue("tarot_card_indexes", "塔罗抽牌结果格式错误。"))

    if chart_type == "fengshui":
        if profile.get("facing_degree") is None:
            issues.append(IntakeIssue("facing_degree", "风水盘需要房屋朝向度数，不能默认朝南。"))
        if profile.get("move_in_year") is None and profile.get("built_year") is None:
            issues.append(IntakeIssue("move_in_year", "玄空飞星需要入住年或建成年，用于定元运。"))

    return ChartIntake(chart_type=chart_type, ok=not any(i.blocking for i in issues), issues=issues)


def assert_chart_ready(chart_type: str, profile: dict[str, Any], question: str = "") -> None:
    intake = validate_chart_request(chart_type, profile, question)
    if not intake.ok:
        raise IntakeError(chart_type, intake.issues)
