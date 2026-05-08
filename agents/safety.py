"""合规 / 红线 / 心理风险审查。

设计要点：
- 高危词（自杀 / 自残）触发立即软切，输出心理援助热线
- 红线词替换：100%/一定/必然/保证/改命/改运
- 强动作建议软化：建议离婚 / 辞职 / 报复
- 医学诊断 → 改为"建议咨询专业医生"
- 不进 LLM 也能执行最低限度合规
"""
from __future__ import annotations
import re

CRISIS_HOTLINES = (
    "如果你正在经历强烈情绪困扰或危机，请立即联系：北京心理危机热线 010-82951332，"
    "全国 24 小时心理援助 400-161-9995。"
)

# 高危触发词
CRISIS_KEYWORDS = ["想死", "不想活", "活着没意思", "自杀", "自残", "了结自己",
                    "结束生命", "活够了", "没有意义"]

# 红线词替换表
RED_WORD_RULES: list[tuple[str, str]] = [
    (r"100[\s%]?", "较大可能"),
    (r"百分之百", "较大可能"),
    (r"绝对(?!不)", "倾向于"),
    (r"一定会(?!不)", "倾向于"),
    (r"必然(?!性)", "倾向于"),
    (r"必定", "较大可能"),
    (r"保证(?!金)", "倾向于"),
    (r"改命", "调整"),
    (r"改运", "调适"),
]

# 强行动建议软化
STRONG_ACTION_RULES: list[tuple[str, str]] = [
    (r"建议你?离婚", "可考虑就关系状态做更深入沟通"),
    (r"必须辞职", "可考虑评估当前职业适配度"),
    (r"建议(?:报复|断绝)", "建议先观察并寻求理性解决"),
]

# 医学相关
MEDICAL_RULES: list[tuple[str, str]] = [
    (r"会得[一-龥]{1,4}病", "在健康方面需多加留意"),
    (r"诊断为", "可能涉及"),
    (r"治疗方法", "应对方向"),
]


def detect_crisis(text: str) -> bool:
    return any(kw in text for kw in CRISIS_KEYWORDS)


def apply_safety(text: str) -> tuple[str, list[str]]:
    """返回 (修订后的文本, 触发列表)。"""
    triggers: list[str] = []
    if detect_crisis(text):
        triggers.append("crisis")
        return (
            "我注意到你的描述中含有强烈的情绪信号。在继续命理推理之前，"
            "更重要的是先照顾好你自己。\n\n" + CRISIS_HOTLINES +
            "\n\n等你状态稳定后，我会很乐意继续帮你看你关心的问题。",
            triggers,
        )

    out = text
    for pat, repl in RED_WORD_RULES:
        if re.search(pat, out):
            triggers.append(f"red_word:{pat}")
            out = re.sub(pat, repl, out)

    for pat, repl in STRONG_ACTION_RULES:
        if re.search(pat, out):
            triggers.append(f"strong_action:{pat}")
            out = re.sub(pat, repl, out)

    for pat, repl in MEDICAL_RULES:
        if re.search(pat, out):
            triggers.append(f"medical:{pat}")
            out = re.sub(pat, repl, out)

    # 末尾确保有 disclaimer（如果还没有）
    if "本内容基于" not in out and "仅供参考" not in out:
        out += (
            "\n\n---\n*本内容基于传统命理理论生成，仅供参考与启发，"
            "不构成医学、法律、财务或情感关系的专业建议。重大决定请结合自身判断与专业人士意见。*"
        )

    return out, triggers
