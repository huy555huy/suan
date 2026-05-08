"""Standardised topic taxonomy for cross-system alignment.

A consultation can touch many surface questions, but every claim is
ultimately routed to one of the topics below so that Chinese and
Western system summaries can be compared on equal footing.

Use :func:`normalize_topic` to map a free-form user question to a
list of topic IDs (longest-match first).
"""
from __future__ import annotations
from typing import Iterable

# 26 standardised topics covering the realistic question space.
STANDARD_TOPICS: dict[str, str] = {
    # ── Self & psychology ────────────────────────────────────
    "personality_core": "性格核心",
    "personality_shadow": "潜在阴影面",
    "self_growth": "成长方向",
    "spirituality": "灵性 / 精神发展",
    # ── Career & work ────────────────────────────────────────
    "career_path": "事业道路",
    "career_short_term": "近期事业",
    "career_change": "跳槽 / 转行",
    "study_exam": "学业 / 考试",
    "creative_work": "创作 / 表达",
    # ── Wealth ───────────────────────────────────────────────
    "wealth_path": "财富道路",
    "wealth_short_term": "近期财运",
    "investment_risk": "投资 / 投机",
    "debt_loan": "债务 / 借贷",
    # ── Relationships ────────────────────────────────────────
    "marriage": "婚姻",
    "love_short_term": "近期感情",
    "compatibility": "感情匹配",
    "family_parents": "父母 / 长辈",
    "children": "子女",
    "friendship": "朋友 / 人际",
    # ── Body & health ────────────────────────────────────────
    "health_general": "健康总论",
    "health_short_term": "近期健康",
    "mental_health": "心理状态",
    # ── Movement & environment ───────────────────────────────
    "relocation_travel": "搬家 / 出行",
    "fengshui_home": "居家风水",
    # ── Time & decision ──────────────────────────────────────
    "timing_decision": "择时 / 决策",
    "year_outlook": "流年总览",
}

# Keyword index used by ``normalize_topic``.
# Each topic ID points at trigger keywords (English + simplified
# Chinese) that should fire it.  Longer / more specific keywords
# rank higher in the resulting list.
_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "personality_core": [
        "性格", "个性", "本性", "我是怎样的", "我是什么样",
        "personality", "character", "who am i", "self",
    ],
    "personality_shadow": [
        "阴影", "缺点", "弱点", "盲点", "shadow", "weakness",
    ],
    "self_growth": [
        "成长", "修行", "提升", "突破", "growth", "self improvement",
        "self-improvement", "潜能",
    ],
    "spirituality": [
        "灵性", "修道", "冥想", "宗教", "信仰", "spirit", "spiritual",
        "灵修", "觉醒",
    ],
    "career_path": [
        "事业", "职业", "工作方向", "天职", "career", "vocation",
        "career path", "适合什么工作", "适合的行业",
    ],
    "career_short_term": [
        "近期事业", "工作运", "今年工作", "本月工作", "下半年工作",
        "升职", "晋升", "promotion", "current job",
    ],
    "career_change": [
        "跳槽", "转行", "换工作", "辞职", "离职", "career change",
        "job change", "switch jobs",
    ],
    "study_exam": [
        "学业", "考试", "高考", "考研", "留学", "学校", "学习",
        "exam", "study", "school", "academic",
    ],
    "creative_work": [
        "创作", "艺术", "写作", "表达", "副业", "creative",
        "artistic", "writing",
    ],
    "wealth_path": [
        "财富", "财运", "正财", "偏财", "财富道路", "wealth",
        "money path", "财源",
    ],
    "wealth_short_term": [
        "近期财运", "今年财运", "最近钱", "短期财", "近期财",
        "current finance", "finance this year",
    ],
    "investment_risk": [
        "投资", "炒股", "股票", "基金", "投机", "彩票", "数字货币",
        "比特币", "investment", "stock", "speculation", "crypto",
    ],
    "debt_loan": [
        "借贷", "贷款", "欠债", "欠钱", "债务", "debt", "loan",
    ],
    "marriage": [
        "婚姻", "结婚", "离婚", "夫妻", "配偶", "marriage", "spouse",
        "divorce", "wedding",
    ],
    "love_short_term": [
        "近期感情", "桃花", "今年感情", "脱单", "恋爱运",
        "love this year", "relationship now", "近期桃花",
    ],
    "compatibility": [
        "合不合", "合婚", "配对", "匹配", "我们合适吗", "compatibility",
        "match", "pair", "synastry",
    ],
    "family_parents": [
        "父母", "家庭", "长辈", "孝顺", "家人", "parents", "family",
        "elder",
    ],
    "children": [
        "子女", "孩子", "怀孕", "生育", "children", "kids",
        "pregnancy", "fertility",
    ],
    "friendship": [
        "朋友", "人际", "社交", "贵人", "小人", "friend",
        "friendship", "social",
    ],
    "health_general": [
        "健康", "身体", "体质", "health", "body", "constitution",
    ],
    "health_short_term": [
        "近期健康", "今年身体", "最近身体", "病情", "current health",
        "illness",
    ],
    "mental_health": [
        "心情", "情绪", "焦虑", "抑郁", "压力", "mental",
        "anxiety", "depression", "mood",
    ],
    "relocation_travel": [
        "搬家", "迁移", "出行", "出差", "出国", "移民", "relocate",
        "move", "travel", "immigrate", "驿马",
    ],
    "fengshui_home": [
        "风水", "家居", "住宅", "办公室", "fengshui", "home",
        "house", "office",
    ],
    "timing_decision": [
        "什么时候", "几月", "择日", "什么时间", "时机", "选时",
        "when", "best time", "timing", "auspicious date",
    ],
    "year_outlook": [
        "今年怎样", "流年", "本年", "下年", "明年", "this year",
        "year ahead", "annual", "yearly",
    ],
}


def normalize_topic(question: str) -> list[str]:
    """Map a free-form question to a list of standard topic IDs.

    Returns topics ordered by descending keyword specificity (longer
    keyword match first).  Empty list if no topic is detected — the
    caller should default to ``personality_core`` or ``year_outlook``
    in that case.
    """
    if not question:
        return []
    q = question.lower()
    matches: list[tuple[int, str]] = []
    seen: set[str] = set()
    for topic_id, keywords in _TOPIC_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in q:
                if topic_id in seen:
                    # already added — keep the longest keyword's score
                    continue
                matches.append((len(kw), topic_id))
                seen.add(topic_id)
                break
    matches.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in matches]


def list_topics() -> Iterable[tuple[str, str]]:
    """Yield ``(topic_id, label_zh)`` for every standard topic."""
    yield from STANDARD_TOPICS.items()


__all__ = ["STANDARD_TOPICS", "normalize_topic", "list_topics"]
