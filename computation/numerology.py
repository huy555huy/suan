"""数字命理 (Numerology) 计算引擎。

毕达哥拉斯系统：
- Life Path 生命数：生年 + 生月 + 生日 各位数字相加，归约 1-9（保留大师数 11/22/33）
- Expression 表达数：全名（拼音/英文）所有字母数字相加归约
- Soul Urge 灵魂数：全名元音字母数字相加归约
- Personality 性格数：全名辅音字母数字相加归约
- Destiny = Expression（同一项的别名）
- Personal Year 个人年数：生月 + 生日 + 当前年 各位数字相加归约

Pythagorean 字母表：
A=1 B=2 C=3 D=4 E=5 F=6 G=7 H=8 I=9
J=1 K=2 L=3 M=4 N=5 O=6 P=7 Q=8 R=9
S=1 T=2 U=3 V=4 W=5 X=6 Y=7 Z=8

中文姓名：建议用户先转拼音后传入。无 full_name 时只算 life_path 与 personal_year。

精度：100% 确定性。
"""
from __future__ import annotations

from typing import Literal

from core.schemas import BirthInfo, NumerologyProfile

# ── Pythagorean 字母表 ───────────────────────────────────────
PYTHAGOREAN_TABLE: dict[str, int] = {
    "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8, "I": 9,
    "J": 1, "K": 2, "L": 3, "M": 4, "N": 5, "O": 6, "P": 7, "Q": 8, "R": 9,
    "S": 1, "T": 2, "U": 3, "V": 4, "W": 5, "X": 6, "Y": 7, "Z": 8,
}

# 标准元音；Y 视上下文（首字母 / 词尾 / 单元音词）默认作元音
VOWELS = set("AEIOU")
VOWELS_WITH_Y = set("AEIOUY")

MASTER_NUMBERS = {11, 22, 33}


# ── 归约 ─────────────────────────────────────────────────────
def digit_sum(n: int) -> int:
    """返回 n 各位数字之和。"""
    return sum(int(c) for c in str(abs(n)))


def reduce_number(n: int, keep_master: bool = True) -> int:
    """归约到 1-9，保留大师数 11/22/33。

    举例：34 → 3+4 = 7；29 → 11（master，保留）；38 → 11（master，保留）。
    """
    if n <= 0:
        return 0
    while n > 9:
        if keep_master and n in MASTER_NUMBERS:
            return n
        n = digit_sum(n)
    return n


# ── 字母值 ───────────────────────────────────────────────────
def _letter_value(ch: str) -> int:
    """返回单字母毕达哥拉斯值（非字母返回 0）。"""
    return PYTHAGOREAN_TABLE.get(ch.upper(), 0)


def _is_vowel(ch: str, treat_y_as_vowel: bool = True) -> bool:
    """判断字母是否元音。Y 默认作元音处理。"""
    ch_u = ch.upper()
    if treat_y_as_vowel:
        return ch_u in VOWELS_WITH_Y
    return ch_u in VOWELS


def _clean_name(name: str) -> str:
    """只保留 ASCII 字母（其它统统去掉）。"""
    return "".join(c for c in name if c.isascii() and c.isalpha())


# ── 单项计算 ─────────────────────────────────────────────────
def life_path_number(year: int, month: int, day: int, keep_master: bool = True) -> int:
    """生命数：生年 + 月 + 日 各位数字相加归约。

    例：1991-08-15 → 1+9+9+1+8+1+5 = 34 → 3+4 = 7
    """
    total = digit_sum(year) + digit_sum(month) + digit_sum(day)
    return reduce_number(total, keep_master=keep_master)


def expression_number(full_name: str, keep_master: bool = True) -> int:
    """表达数：全名所有字母数字之和归约。"""
    cleaned = _clean_name(full_name)
    if not cleaned:
        return 0
    total = sum(_letter_value(c) for c in cleaned)
    return reduce_number(total, keep_master=keep_master)


def soul_urge_number(full_name: str, treat_y_as_vowel: bool = True,
                      keep_master: bool = True) -> int:
    """灵魂数：全名元音字母数字之和归约。"""
    cleaned = _clean_name(full_name)
    if not cleaned:
        return 0
    total = sum(
        _letter_value(c) for c in cleaned if _is_vowel(c, treat_y_as_vowel)
    )
    return reduce_number(total, keep_master=keep_master)


def personality_number(full_name: str, treat_y_as_vowel: bool = True,
                        keep_master: bool = True) -> int:
    """性格数：全名辅音字母数字之和归约。"""
    cleaned = _clean_name(full_name)
    if not cleaned:
        return 0
    total = sum(
        _letter_value(c) for c in cleaned if not _is_vowel(c, treat_y_as_vowel)
    )
    return reduce_number(total, keep_master=keep_master)


def personal_year_number(month: int, day: int, current_year: int,
                          keep_master: bool = True) -> int:
    """个人年数：生月 + 生日 + 当前年 各位数字相加归约。"""
    total = digit_sum(month) + digit_sum(day) + digit_sum(current_year)
    return reduce_number(total, keep_master=keep_master)


# ── 解读钩子（供 LLM prompt 使用） ───────────────────────────
NUMBER_INTERPRETATION_HOOKS: dict[int, str] = {
    1: "领导/独立/开创：原创力强、自我驱动，但要警惕固执与孤立。",
    2: "合作/敏感/外交：擅长人际平衡与共情，但需克服过度依赖。",
    3: "创造/表达/喜悦：充满艺术感染力，需避免分散与浮躁。",
    4: "稳定/秩序/勤勉：可靠的建设者，注意僵化与抗拒变革。",
    5: "自由/变化/冒险：天生的探索者，注意冲动与无常。",
    6: "责任/家庭/和谐：天然的照顾者与教师，警惕牺牲过度。",
    7: "智慧/内省/灵性：深度思考者与求道者，避免疏离与多疑。",
    8: "权力/财富/掌控：擅长在物质世界落地野心，注意物欲与失衡。",
    9: "博爱/完成/利他：人道主义者与艺术家，避免自我牺牲与情绪化。",
    11: "灵感/直觉（大师数）：高敏感与精神导师潜质，注意焦虑与神经紧绷。",
    22: "大师建造者：把愿景落地成宏大事业的能力，承担巨大压力。",
    33: "大师教师：以无条件的爱去教化与疗愈他人，需稳固自我。",
}


def hook_for(n: int) -> str:
    """返回某数字的解读钩子（找不到则返回空字符串）。"""
    return NUMBER_INTERPRETATION_HOOKS.get(n, "")


# ── 主入口 ───────────────────────────────────────────────────
def compute_numerology(
    birth: BirthInfo,
    current_year: int = 2026,
    full_name_pinyin: str | None = None,
    treat_y_as_vowel: bool = True,
    keep_master: bool = True,
) -> NumerologyProfile:
    """计算完整数字命理画像。

    Args:
        birth: BirthInfo（仅使用 year/month/day）
        current_year: 用于个人年数（默认 2026）
        full_name_pinyin: 拼音 / 英文全名（含空格与大小写均可）。若为 None 或空字符串，
            表达数 / 灵魂数 / 性格数将为 0，仅返回 life_path / personal_year。
        treat_y_as_vowel: Y 是否作元音（默认 True）
        keep_master: 是否保留大师数 11/22/33（默认 True）

    Returns:
        NumerologyProfile
    """
    # 1. 生命数（永远可算）
    life_path = life_path_number(birth.year, birth.month, birth.day, keep_master)

    # 2. 个人年数（永远可算）
    personal_year = personal_year_number(birth.month, birth.day, current_year, keep_master)

    # 3. 姓名相关三数
    name = full_name_pinyin or birth.name or ""
    cleaned_name = _clean_name(name)

    if cleaned_name:
        expression = expression_number(cleaned_name, keep_master)
        soul_urge = soul_urge_number(cleaned_name, treat_y_as_vowel, keep_master)
        personality = personality_number(cleaned_name, treat_y_as_vowel, keep_master)
    else:
        expression = 0
        soul_urge = 0
        personality = 0

    destiny = expression  # destiny 是 expression 的别名

    # 4. 大师数标记
    master_flag = any(
        v in MASTER_NUMBERS
        for v in (life_path, expression, soul_urge, personality, personal_year)
    )

    # 5. interpretation_hooks
    hooks: list[str] = []
    seen: set[int] = set()
    for label, val in [
        ("life_path", life_path), ("expression", expression),
        ("soul_urge", soul_urge), ("personality", personality),
        ("personal_year", personal_year),
    ]:
        if val and val not in seen:
            seen.add(val)
            text = hook_for(val)
            if text:
                hooks.append(f"{label}={val}: {text}")

    metadata = {
        "system": "pythagorean",
        "name_used": cleaned_name or None,
        "name_provided": bool(cleaned_name),
        "current_year": current_year,
        "treat_y_as_vowel": treat_y_as_vowel,
        "keep_master": keep_master,
        "raw_sums": {
            # 提供原始未归约的总和便于调试
            "life_path_raw": digit_sum(birth.year) + digit_sum(birth.month) + digit_sum(birth.day),
            "personal_year_raw": digit_sum(birth.month) + digit_sum(birth.day) + digit_sum(current_year),
        },
        "notes": [],
    }
    if not cleaned_name:
        metadata["notes"].append(
            "未提供拼音/英文姓名，仅生成 life_path 与 personal_year；"
            "如需 expression/soul_urge/personality，请将中文姓名转写为拼音后重算。"
        )

    return NumerologyProfile(
        life_path=life_path,
        expression=expression,
        soul_urge=soul_urge,
        personality=personality,
        destiny=destiny,
        personal_year=personal_year,
        master_number_flag=master_flag,
        interpretation_hooks=hooks,
        metadata=metadata,
    )


# ── 演示 ─────────────────────────────────────────────────────
if __name__ == "__main__":
    import json

    # 示例 1：1991-08-15 + 拼音名 "Zhang San"
    birth = BirthInfo(
        name="Zhang San", gender="female",
        year=1991, month=8, day=15, hour=14, minute=30,
        location_name="北京", longitude=116.4074, latitude=39.9042,
        timezone_offset=8.0,
    )
    profile = compute_numerology(birth, current_year=2026, full_name_pinyin="Zhang San")
    print("── 数字命理示例 (1991-08-15, Zhang San) ──")
    print(json.dumps(profile.model_dump(), ensure_ascii=False, indent=2))
    print()

    # 验收：life_path 应 = 7
    assert profile.life_path == 7, f"期望 life_path=7, 实际 {profile.life_path}"
    print(f"验收通过：life_path = {profile.life_path}")

    # 示例 2：仅生日，无姓名（使用一个无 name 字段的 BirthInfo）
    birth_noname = BirthInfo(
        year=1991, month=8, day=15, hour=14, minute=30,
        location_name="北京", longitude=116.4074, latitude=39.9042,
        timezone_offset=8.0,
    )
    profile2 = compute_numerology(birth_noname, current_year=2026, full_name_pinyin=None)
    print("\n── 仅生日 (无姓名) ──")
    print(f"life_path = {profile2.life_path}, personal_year = {profile2.personal_year}")
    print(f"expression = {profile2.expression} (无姓名时为 0)")

    # 示例 3：含大师数测试
    # 1992-11-29 → 1+9+9+2+1+1+2+9 = 34 → 7（不触发 11）
    # 1980-02-29 → 1+9+8+0+2+2+9 = 31 → 4
    # 找一个 life_path = 11 的：1990-02-09 → 1+9+9+0+2+9 = 30 → 3
    # 1989-12-29 → 1+9+8+9+1+2+2+9 = 41 → 5
    # 1991-04-29 → 1+9+9+1+4+2+9 = 35 → 8
    # 1990-12-29 → 1+9+9+0+1+2+2+9 = 33 (master!)
    test_birth = BirthInfo(
        year=1990, month=12, day=29, hour=12,
        location_name="北京", longitude=116.4074, latitude=39.9042,
        timezone_offset=8.0,
    )
    test_profile = compute_numerology(test_birth, current_year=2026, full_name_pinyin="Test Name")
    print(f"\n── 大师数测试 1990-12-29 ──")
    print(f"life_path = {test_profile.life_path} (应为 33 大师数)")
    print(f"master_flag = {test_profile.master_number_flag}")
