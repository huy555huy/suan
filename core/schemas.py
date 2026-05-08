"""全局 Pydantic Schema 定义。

参考设计文档第 6.1 节 + 7B.5.2 节。
为保持简洁，把所有命理盘面、专家观点、综合结论、对齐结果、
最终判官、追溯数据集中在此文件。
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# ── 全局枚举 ────────────────────────────────────────────────
EXPERT_NAMES = Literal[
    "bazi", "ziwei", "yijing", "fengshui", "liunian",
    "astrology", "tarot", "numerology",
]
SYSTEM_GROUP = Literal["chinese", "western"]
CHART_TYPES = Literal[
    "bazi", "ziwei", "hexagram", "fengshui",
    "natal_astro", "transit_astro",
    "tarot", "numerology",
]
TIER = Literal["A_core", "B_support", "C_narrative"]
CONFIDENCE = Literal["high", "medium", "low"]


# ── VRP 三元组 ─────────────────────────────────────────────
class ChartRef(BaseModel):
    chart_type: CHART_TYPES
    json_path: str
    expected_value: Any
    semantic: str = ""


class RuleRef(BaseModel):
    rule_id: str
    rule_text: str = ""
    triggered_by: list[str] = Field(default_factory=list)
    school: str | None = None


class SourceRef(BaseModel):
    source_type: Literal["classic", "modern", "case"] = "classic"
    source_id: str
    quote: str | None = None
    chunk_id: str | None = None


class GroundedClaim(BaseModel):
    claim_id: str
    claim: str
    tier: TIER = "A_core"
    chart_refs: list[ChartRef] = Field(default_factory=list)
    rule_refs: list[RuleRef] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    upstream_claim_ids: list[str] = Field(default_factory=list)
    confidence: CONFIDENCE = "medium"
    expert: EXPERT_NAMES | str = "bazi"
    system_group: SYSTEM_GROUP = "chinese"
    deviation_note: str | None = None  # LLM 偏离规则时的说明
    verifier_verdict: str | None = None  # ACCEPT / RULE_NOVEL / SOURCE_SYNTHESIZED / SEMANTIC_WEAK / OVERCLAIM / FACT_VIOLATION


# ── 用户与盘面 ──────────────────────────────────────────────
class BirthInfo(BaseModel):
    name: str | None = None
    gender: Literal["male", "female", "other"] = "other"
    # 阳历生日
    year: int
    month: int
    day: int
    hour: int
    minute: int = 0
    # 出生地
    location_name: str = "北京"
    longitude: float = 116.4074
    latitude: float = 39.9042
    timezone_offset: float = 8.0  # 小时
    use_true_solar_time: bool = True


class BaziChart(BaseModel):
    year_pillar: dict
    month_pillar: dict
    day_pillar: dict
    hour_pillar: dict
    day_master: str  # 日干
    five_elements: dict[str, int]  # 五行计数
    ten_gods: dict[str, str]  # 各柱十神
    hidden_stems: dict[str, list[str]]
    shen_sha: list[str] = Field(default_factory=list)
    pattern: str | None = None  # 格局
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
    palaces: list[dict]  # 12 宫位
    main_stars: dict[str, list[str]]  # 各宫位主星
    body_palace: str  # 身宫
    life_palace: str  # 命宫
    five_element_bureau: str  # 五行局
    si_hua: dict[str, str]  # 四化（化禄/化权/化科/化忌）
    da_xian: list[dict]  # 大限
    liu_nian: dict | None = None
    school: str = "zhongzhou"
    metadata: dict = Field(default_factory=dict)


class HexagramChart(BaseModel):
    method: Literal["coin", "meihua", "time"] = "meihua"
    question: str = ""
    ben_gua: dict  # 本卦
    bian_gua: dict | None = None  # 变卦
    hu_gua: dict | None = None  # 互卦
    moving_lines: list[int] = Field(default_factory=list)
    yong_shen: str | None = None
    shi_yao: int | None = None  # 世爻
    ying_yao: int | None = None  # 应爻
    six_relatives: list[str] = Field(default_factory=list)
    six_gods: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class FengshuiChart(BaseModel):
    facing_direction: str  # 朝向 (degrees + name)
    sitting_direction: str
    period: int  # 三元九运
    flying_stars: list[list[int]]  # 9x3 (山盘/向盘/运盘)
    ba_zhai: dict  # 八宅
    ming_gua: str | None = None  # 命卦
    favorable_directions: list[str] = Field(default_factory=list)
    unfavorable_directions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class AstroNatalChart(BaseModel):
    planets: dict[str, dict]
    angles: dict[str, float]  # ASC, MC, DSC, IC
    houses: list[dict]  # 12 houses
    aspects: list[dict]
    distributions: dict  # 元素 / 模式
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


# ── 专家与综合输出 ───────────────────────────────────────────
class ExpertOpinion(BaseModel):
    expert: EXPERT_NAMES
    system_group: SYSTEM_GROUP
    school: str | None = None
    headline: str = ""  # 一句话主结论
    summary: str = ""
    points: list[GroundedClaim] = Field(default_factory=list)
    confidence: CONFIDENCE = "medium"
    flags: list[str] = Field(default_factory=list)


class TopicConclusion(BaseModel):
    topic: str
    tendency: Literal["positive", "neutral", "negative", "mixed"] = "neutral"
    timing: str | None = None
    risks: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    summary: str = ""
    supporting_claim_ids: list[str] = Field(default_factory=list)


class SystemSummary(BaseModel):
    system_group: SYSTEM_GROUP
    by_topic: dict[str, TopicConclusion] = Field(default_factory=dict)
    confidence: CONFIDENCE = "medium"
    is_skipped: bool = False
    skip_reason: str | None = None
    headline: str = ""


class ConflictItem(BaseModel):
    topic: str
    side_a: dict
    side_b: dict
    arbitration: str = ""


class TopicAlignment(BaseModel):
    topic: str
    chinese_view: str | None = None
    western_view: str | None = None
    alignment_type: Literal["consensus", "divergence", "complementary", "incomparable"] = "incomparable"
    consensus_points: list[str] = Field(default_factory=list)
    divergence_points: list[ConflictItem] = Field(default_factory=list)
    complementary_points: list[str] = Field(default_factory=list)
    final_synthesis: str = ""
    confidence_uplift: float = 0.0


class CrossSystemAlignment(BaseModel):
    by_topic: dict[str, TopicAlignment] = Field(default_factory=dict)
    overall_consensus_score: float = 0.0
    overall_divergence_score: float = 0.0
    overall_summary: str = ""


class JudgeVerdict(BaseModel):
    consensus: list[str] = Field(default_factory=list)
    conflicts: list[ConflictItem] = Field(default_factory=list)
    weighted_summary: str = ""
    overall_confidence: CONFIDENCE = "medium"
    cross_alignment: CrossSystemAlignment | None = None
    actionable_advice: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)


# ── 推理追溯 ───────────────────────────────────────────────
class TraceStep(BaseModel):
    step_id: int
    agent: str
    action: str
    payload: dict = Field(default_factory=dict)
    duration_ms: int = 0
    cost_usd: float = 0.0


class ReasoningTrace(BaseModel):
    trace_id: str
    session_id: str
    started_at: str
    steps: list[TraceStep] = Field(default_factory=list)


# ── 顶层 AgentState ─────────────────────────────────────────
class AgentState(BaseModel):
    session_id: str
    user_name: str | None = None
    birth: BirthInfo
    question: str = ""
    scenario: Literal["chat", "report", "copilot"] = "chat"

    # 计算结果
    charts: Charts = Field(default_factory=Charts)

    # 路由
    activated_experts: list[str] = Field(default_factory=list)
    routing_reason: str = ""

    # 中间产物
    expert_opinions: list[ExpertOpinion] = Field(default_factory=list)
    cn_synth: SystemSummary | None = None
    wt_synth: SystemSummary | None = None
    cross_alignment: CrossSystemAlignment | None = None
    verdict: JudgeVerdict | None = None

    # Verifier 产物
    verifier_log: dict = Field(default_factory=dict)
    requires_expert_retry: bool = False

    # 终态
    narrative: str = ""
    safety_passed: bool = True
    safety_notes: list[str] = Field(default_factory=list)

    # 元数据
    trace: ReasoningTrace | None = None
    cost_usd: float = 0.0
    latency_ms: int = 0
    errors: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)  # 输入不确定性（时辰/地名等）


# ── 反馈 ────────────────────────────────────────────────────
class Feedback(BaseModel):
    session_id: str
    rating: int = 5
    tags: list[str] = Field(default_factory=list)
    text: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
