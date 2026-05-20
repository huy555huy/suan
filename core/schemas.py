"""全局 Pydantic Schema 定义 — 精简版（单 Agent 架构）。

保留：BirthInfo + 各类盘面 Chart + Charts 容器 + Feedback
删除：ExpertOpinion / SystemSummary / CrossSystemAlignment / JudgeVerdict / AgentState 等旧多 agent 产物
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


# ── 全局枚举 ────────────────────────────────────────────────
CHART_TYPES = Literal[
    "bazi", "ziwei", "hexagram", "fengshui",
    "natal_astro", "transit_astro",
    "tarot", "numerology",
]


# ── 用户与盘面 ──────────────────────────────────────────────
class BirthInfo(BaseModel):
    name: str | None = None
    gender: Literal["male", "female", "other"] = "other"
    year: int
    month: int
    day: int
    hour: int
    minute: int = 0
    location_name: str
    longitude: float
    latitude: float
    timezone_offset: float
    use_true_solar_time: bool = True


class BaziChart(BaseModel):
    year_pillar: dict
    month_pillar: dict
    day_pillar: dict
    hour_pillar: dict
    day_master: str
    five_elements: dict[str, int]
    ten_gods: dict[str, str]
    hidden_stems: dict[str, list[str]]
    shen_sha: list[str] = Field(default_factory=list)
    pattern: str | None = None
    yong_shen: str | None = None
    xi_ji: dict[str, list[str]] = Field(default_factory=dict)
    da_yun: list[dict] = Field(default_factory=list)
    liu_nian: list[dict] = Field(default_factory=list)
    solar_term: str | None = None
    lunar_date: str | None = None
    true_solar_time: str | None = None
    school: str = "zi_ping"
    metadata: dict = Field(default_factory=dict)


class ZiweiChart(BaseModel):
    palaces: list[dict]
    palaces_by_name: dict[str, dict] = Field(default_factory=dict)
    main_stars: dict[str, list[str]]
    body_palace: str
    life_palace: str
    five_element_bureau: str
    si_hua: dict[str, str]
    da_xian: list[dict]
    liu_nian: dict | None = None
    school: str = "zhongzhou"
    metadata: dict = Field(default_factory=dict)


class HexagramChart(BaseModel):
    method: Literal["coin", "meihua", "time"] = "meihua"
    question: str = ""
    ben_gua: dict
    bian_gua: dict | None = None
    hu_gua: dict | None = None
    moving_lines: list[int] = Field(default_factory=list)
    yong_shen: str | None = None
    shi_yao: int | None = None
    ying_yao: int | None = None
    six_relatives: list[str] = Field(default_factory=list)
    six_gods: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class FengshuiChart(BaseModel):
    facing_direction: str
    sitting_direction: str
    period: int
    flying_stars: list[list[int]]
    ba_zhai: dict
    ming_gua: str | None = None
    favorable_directions: list[str] = Field(default_factory=list)
    unfavorable_directions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class AstroNatalChart(BaseModel):
    planets: dict[str, dict]
    angles: dict[str, float]
    houses: list[dict]
    aspects: list[dict]
    distributions: dict
    moon_phase: str
    house_system: str = "placidus"
    school: str = "modern_psychological"
    metadata: dict = Field(default_factory=dict)


class TransitChart(BaseModel):
    target_date: str
    transit_planets: dict[str, dict]
    aspects_to_natal: list[dict]
    key_transits: list[dict]
    metadata: dict = Field(default_factory=dict)


class TarotReading(BaseModel):
    spread: str
    deck: str = "rws"
    question: str = ""
    drawn_cards: list[dict]
    metadata: dict = Field(default_factory=dict)


class NumerologyProfile(BaseModel):
    life_path: int
    expression: int
    soul_urge: int
    personality: int
    destiny: int
    personal_year: int
    master_number_flag: bool
    interpretation_hooks: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class Charts(BaseModel):
    bazi: BaziChart | None = None
    ziwei: ZiweiChart | None = None
    hexagram: HexagramChart | None = None
    fengshui: FengshuiChart | None = None
    natal_astro: AstroNatalChart | None = None
    transit_astro: TransitChart | None = None
    tarot: TarotReading | None = None
    numerology: NumerologyProfile | None = None


# ── 反馈 ────────────────────────────────────────────────────
class Feedback(BaseModel):
    session_id: str
    rating: int = 5
    tags: list[str] = Field(default_factory=list)
    text: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
