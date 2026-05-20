"""心理危机检测 — 最后安全网。

仅检测自杀/自残等高危关键词并替换为心理援助信息。
不做语言风格修改 — 那是 agent 自己的事。
"""
from __future__ import annotations

CRISIS_HOTLINES = (
    "如果你正在经历强烈情绪困扰或危机，请立即联系：北京心理危机热线 010-82951332，"
    "全国 24 小时心理援助 400-161-9995。"
)

CRISIS_KEYWORDS = [
    "想死", "不想活", "活着没意思", "自杀", "自残", "了结自己",
    "结束生命", "活够了", "没有意义",
]


def detect_crisis(text: str) -> bool:
    return any(kw in text for kw in CRISIS_KEYWORDS)
