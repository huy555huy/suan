"""易经 / 六爻 / 梅花易数 计算引擎。

实现要点：
    1. 64 卦数据：``HEXAGRAMS`` 提供每卦 (id, 卦名, 上卦, 下卦, 6 爻, 卦辞简略, 彖辞)
    2. 起卦法：
        - ``compute_meihua``：梅花易数（数字起卦 / 时间起卦）
        - ``compute_coin``：铜钱起卦（6 次三枚硬币结果，未提供则随机）
    3. 本卦 / 变卦 / 互卦 / 动爻
    4. 京房纳甲：每爻配六亲、六神（按问卦时日干）、世应位置
    5. 用神（按问题类型简单映射）

入口：
    - compute_meihua(question, numbers=None, dt=None) -> HexagramChart
    - compute_coin(question, coin_results=None) -> HexagramChart
"""
from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from core.schemas import HexagramChart
from computation.calendar import (
    DI_ZHI,
    GAN_WUXING,
    TIAN_GAN,
    ZHI_WUXING,
    get_day_pillar,
)


# ── 8 卦基本元素 ────────────────────────────────────────────
# 每卦 3 爻（自下而上），1=阳，0=阴
TRIGRAMS = {
    # 自下而上：(初爻, 中爻, 上爻)，1=阳爻, 0=阴爻
    "乾": (1, 1, 1),  # 天 ☰
    "兑": (1, 1, 0),  # 泽 ☱（下阳中阳上阴）
    "离": (1, 0, 1),  # 火 ☲（下阳中阴上阳）
    "震": (1, 0, 0),  # 雷 ☳（下阳中阴上阴）
    "巽": (0, 1, 1),  # 风 ☴（下阴中阳上阳）
    "坎": (0, 1, 0),  # 水 ☵（下阴中阳上阴）
    "艮": (0, 0, 1),  # 山 ☶（下阴中阴上阳）
    "坤": (0, 0, 0),  # 地 ☷
}

# 先天八卦数（梅花易数用）
TRIGRAM_NUMBER_PRENATAL = {
    1: "乾", 2: "兑", 3: "离", 4: "震",
    5: "巽", 6: "坎", 7: "艮", 8: "坤",
}
TRIGRAM_TO_NUMBER = {v: k for k, v in TRIGRAM_NUMBER_PRENATAL.items()}

TRIGRAM_TO_FIVEELEMENT = {
    "乾": "金", "兑": "金",
    "离": "火",
    "震": "木", "巽": "木",
    "坎": "水",
    "艮": "土", "坤": "土",
}


# ── 64 卦数据 ────────────────────────────────────────────────
# 每条：(id, 卦名, 上卦, 下卦, 卦辞, 简短彖辞)
# 顺序按周易通行本顺序（乾、坤、屯、蒙、需、讼...既济、未济）
# 卦辞为公有领域《周易》原文要点 + 简短现代注解，每条均小于 30 字
HEXAGRAMS_RAW = [
    (1,  "乾", "乾", "乾", "元亨利贞,天行健",        "君子自强不息"),
    (2,  "坤", "坤", "坤", "元亨,利牝马之贞",        "厚德载物,顺承天"),
    (3,  "屯", "坎", "震", "元亨利贞,勿用有攸往",   "草木初生,艰难启始"),
    (4,  "蒙", "艮", "坎", "亨,匪我求童蒙",          "山下出泉,启蒙教化"),
    (5,  "需", "坎", "乾", "有孚,光亨贞吉",          "云上于天,等待时机"),
    (6,  "讼", "乾", "坎", "有孚窒,惕中吉",          "天与水违行,慎勿争"),
    (7,  "师", "坤", "坎", "贞,丈人吉无咎",          "地中有水,众望所归"),
    (8,  "比", "坎", "坤", "吉,原筮元永贞",          "亲比辅佐,众星拱月"),
    (9,  "小畜", "巽", "乾", "亨,密云不雨",          "风行天上,小有蓄养"),
    (10, "履", "乾", "兑", "履虎尾,不咥人,亨",       "履行礼仪,谨慎前行"),
    (11, "泰", "坤", "乾", "小往大来,吉亨",           "天地交泰,亨通"),
    (12, "否", "乾", "坤", "之匪人,不利君子",         "天地不交,闭塞"),
    (13, "同人", "乾", "离", "于野,亨",                "上下同心,大同"),
    (14, "大有", "离", "乾", "元亨",                  "火在天上,所有皆备"),
    (15, "谦", "坤", "艮", "亨,君子有终",              "山在地中,谦受益"),
    (16, "豫", "震", "坤", "利建侯行师",                "雷出地奋,顺应而动"),
    (17, "随", "兑", "震", "元亨利贞,无咎",            "随时变通,与时俱进"),
    (18, "蛊", "艮", "巽", "元亨,利涉大川",            "山下有风,整治弊乱"),
    (19, "临", "坤", "兑", "元亨利贞,至于八月有凶",    "君子居上,以临众民"),
    (20, "观", "巽", "坤", "盥而不荐,有孚顒若",        "风行地上,观察风化"),
    (21, "噬嗑", "离", "震", "亨,利用狱",                "明罚敕法,啮合"),
    (22, "贲", "艮", "离", "亨,小利有攸往",              "文饰修养,刚柔相济"),
    (23, "剥", "艮", "坤", "不利有攸往",                "山附于地,剥落衰退"),
    (24, "复", "坤", "震", "亨,出入无疾",                "雷在地中,一阳来复"),
    (25, "无妄", "乾", "震", "元亨利贞",                  "雷动天行,无妄之灾"),
    (26, "大畜", "艮", "乾", "利贞,不家食吉",           "山中藏天,蓄积大才"),
    (27, "颐", "艮", "震", "贞吉,观颐",                  "颐养之道,慎言节食"),
    (28, "大过", "兑", "巽", "栋桡,利有攸往",            "泽灭木,大过非常"),
    (29, "坎", "坎", "坎", "习坎,有孚维心亨",            "水洊至,险中行险"),
    (30, "离", "离", "离", "利贞,亨,畜牝牛吉",           "火光重明,文明附丽"),
    (31, "咸", "兑", "艮", "亨,利贞,取女吉",              "山泽通气,感应"),
    (32, "恒", "震", "巽", "亨,无咎,利贞",                "雷风相济,恒久"),
    (33, "遁", "乾", "艮", "亨,小利贞",                    "天下有山,君子退避"),
    (34, "大壮", "震", "乾", "利贞",                       "雷在天上,壮盛"),
    (35, "晋", "离", "坤", "康侯用锡马蕃庶",                "明出地上,晋升光明"),
    (36, "明夷", "坤", "离", "利艰贞",                      "明入地中,韬光养晦"),
    (37, "家人", "巽", "离", "利女贞",                       "风自火出,家有规矩"),
    (38, "睽", "离", "兑", "小事吉",                          "火上泽下,睽离异向"),
    (39, "蹇", "坎", "艮", "利西南,不利东北",                  "山上有水,行止艰难"),
    (40, "解", "震", "坎", "利西南,无所往",                    "雷雨大作,解散危难"),
    (41, "损", "艮", "兑", "有孚,元吉,无咎",                   "损下益上,自我节制"),
    (42, "益", "巽", "震", "利有攸往,利涉大川",                "损上益下,得众心"),
    (43, "夬", "兑", "乾", "扬于王庭,孚号",                    "决断小人,刚长柔消"),
    (44, "姤", "乾", "巽", "女壮,勿用取女",                     "天下有风,不期而遇"),
    (45, "萃", "兑", "坤", "亨,王假有庙",                       "泽上于地,萃聚人心"),
    (46, "升", "坤", "巽", "元亨,用见大人",                     "地中生木,渐进上升"),
    (47, "困", "兑", "坎", "亨,贞,大人吉,无咎",                 "泽水皆涸,处困之道"),
    (48, "井", "坎", "巽", "改邑不改井",                         "木上有水,井养不穷"),
    (49, "革", "兑", "离", "已日乃孚,元亨利贞",                   "泽火相息,革故鼎新"),
    (50, "鼎", "离", "巽", "元吉,亨",                              "鼎中有食,革命之器"),
    (51, "震", "震", "震", "亨,震来虩虩",                          "雷声震动,警惧修省"),
    (52, "艮", "艮", "艮", "其背,不获其身",                        "兼山,止其所止"),
    (53, "渐", "巽", "艮", "女归吉,利贞",                          "山上有木,循序渐进"),
    (54, "归妹", "震", "兑", "征凶,无攸利",                        "雷动泽随,归宿失正"),
    (55, "丰", "震", "离", "亨,王假之",                             "雷电皆至,丰大盛极"),
    (56, "旅", "离", "艮", "小亨,旅贞吉",                           "山上有火,旅居在外"),
    (57, "巽", "巽", "巽", "小亨,利有攸往",                          "风行而巽顺,谦逊"),
    (58, "兑", "兑", "兑", "亨,利贞",                                "丽泽相对,悦而正"),
    (59, "涣", "巽", "坎", "亨,王假有庙",                            "风行水上,涣散凝聚"),
    (60, "节", "坎", "兑", "亨,苦节不可贞",                          "泽上有水,节制有度"),
    (61, "中孚", "巽", "兑", "豚鱼吉,利涉大川",                       "中心诚信,化及万物"),
    (62, "小过", "震", "艮", "亨,利贞,可小事",                         "山上有雷,小有过度"),
    (63, "既济", "坎", "离", "亨小,利贞,初吉终乱",                     "水火既济,事已成"),
    (64, "未济", "离", "坎", "亨,小狐汔济",                            "水火未济,事将成"),
]


def _trigram_to_lines(name: str) -> tuple[int, int, int]:
    """返回卦的 3 爻（自下而上）。"""
    return TRIGRAMS[name]


def _build_hexagram_lines(upper: str, lower: str) -> list[int]:
    """6 爻列表（自下而上：初爻、二爻、三爻、四爻、五爻、上爻）。"""
    lower_lines = list(_trigram_to_lines(lower))
    upper_lines = list(_trigram_to_lines(upper))
    return lower_lines + upper_lines  # 下卦在底


def _lookup_hexagram(upper: str, lower: str) -> dict:
    for hid, name, up, dn, gua_ci, tuan in HEXAGRAMS_RAW:
        if up == upper and dn == lower:
            return {
                "id": hid,
                "name": name,
                "upper_trigram": up,
                "lower_trigram": dn,
                "lines": _build_hexagram_lines(up, dn),
                "gua_ci": gua_ci,
                "tuan_ci": tuan,
            }
    raise ValueError(f"未找到卦：{upper}/{lower}")


def _lines_to_trigrams(lines: list[int]) -> tuple[str, str]:
    """6 爻 → (上卦名, 下卦名)。"""
    lower = tuple(lines[0:3])
    upper = tuple(lines[3:6])
    rev = {v: k for k, v in TRIGRAMS.items()}
    return rev[upper], rev[lower]


# ── 京房纳甲 ────────────────────────────────────────────────
# 京房八宫：每宫 8 卦，配地支与五行
# 这里采用简化纳甲：按上卦/下卦 8 卦各自的纳甲规律
# 乾（金）：内卦 子寅辰、外卦 午申戌
# 坤（土）：内卦 未巳卯、外卦 丑亥酉
# 震（木）：内卦 子寅辰、外卦 午申戌
# 巽（木）：内卦 丑亥酉、外卦 未巳卯
# 坎（水）：内卦 寅辰午、外卦 申戌子
# 离（火）：内卦 卯丑亥、外卦 酉未巳
# 艮（土）：内卦 辰午申、外卦 戌子寅
# 兑（金）：内卦 巳卯丑、外卦 亥酉未
NA_JIA_TABLE = {
    "乾": {"inner": ["子", "寅", "辰"], "outer": ["午", "申", "戌"]},
    "坤": {"inner": ["未", "巳", "卯"], "outer": ["丑", "亥", "酉"]},
    "震": {"inner": ["子", "寅", "辰"], "outer": ["午", "申", "戌"]},
    "巽": {"inner": ["丑", "亥", "酉"], "outer": ["未", "巳", "卯"]},
    "坎": {"inner": ["寅", "辰", "午"], "outer": ["申", "戌", "子"]},
    "离": {"inner": ["卯", "丑", "亥"], "outer": ["酉", "未", "巳"]},
    "艮": {"inner": ["辰", "午", "申"], "outer": ["戌", "子", "寅"]},
    "兑": {"inner": ["巳", "卯", "丑"], "outer": ["亥", "酉", "未"]},
}

# 京房八宫所属五行（用于六亲判定时的"我"五行）
# 八宫宫主：乾(金)、震(木)、坎(水)、艮(土)、坤(土)、巽(木)、离(火)、兑(金)
PALACE_OF_HEXAGRAM = {
    # 乾宫
    "乾": "乾", "姤": "乾", "遁": "乾", "否": "乾",
    "观": "乾", "剥": "乾", "晋": "乾", "大有": "乾",
    # 震宫
    "震": "震", "豫": "震", "解": "震", "恒": "震",
    "升": "震", "井": "震", "大过": "震", "随": "震",
    # 坎宫
    "坎": "坎", "节": "坎", "屯": "坎", "既济": "坎",
    "革": "坎", "丰": "坎", "明夷": "坎", "师": "坎",
    # 艮宫
    "艮": "艮", "贲": "艮", "大畜": "艮", "损": "艮",
    "睽": "艮", "履": "艮", "中孚": "艮", "渐": "艮",
    # 坤宫
    "坤": "坤", "复": "坤", "临": "坤", "泰": "坤",
    "大壮": "坤", "夬": "坤", "需": "坤", "比": "坤",
    # 巽宫
    "巽": "巽", "小畜": "巽", "家人": "巽", "益": "巽",
    "无妄": "巽", "噬嗑": "巽", "颐": "巽", "蛊": "巽",
    # 离宫
    "离": "离", "旅": "离", "鼎": "离", "未济": "离",
    "蒙": "离", "涣": "离", "讼": "离", "同人": "离",
    # 兑宫
    "兑": "兑", "困": "兑", "萃": "兑", "咸": "兑",
    "蹇": "兑", "谦": "兑", "小过": "兑", "归妹": "兑",
}

# 世应表：京房八宫每宫第 i 卦（从 0=本宫到 7=归魂）的世爻位置
# 位置编号 1-6（1=初爻，6=上爻）
SHI_YAO_BY_INDEX_IN_PALACE = [6, 1, 2, 3, 4, 5, 4, 3]  # 本/一/二/三/四/五/游/归


def _palace_index(hex_name: str) -> tuple[str, int]:
    """返回卦所属宫名 + 在宫中的索引 0-7。

    简化：用顺序词典。如果不在表中，按"乾"宫处理。
    """
    palace = PALACE_OF_HEXAGRAM.get(hex_name, "乾")
    palace_order = {
        "乾": ["乾", "姤", "遁", "否", "观", "剥", "晋", "大有"],
        "震": ["震", "豫", "解", "恒", "升", "井", "大过", "随"],
        "坎": ["坎", "节", "屯", "既济", "革", "丰", "明夷", "师"],
        "艮": ["艮", "贲", "大畜", "损", "睽", "履", "中孚", "渐"],
        "坤": ["坤", "复", "临", "泰", "大壮", "夬", "需", "比"],
        "巽": ["巽", "小畜", "家人", "益", "无妄", "噬嗑", "颐", "蛊"],
        "离": ["离", "旅", "鼎", "未济", "蒙", "涣", "讼", "同人"],
        "兑": ["兑", "困", "萃", "咸", "蹇", "谦", "小过", "归妹"],
    }
    seq = palace_order[palace]
    if hex_name in seq:
        return palace, seq.index(hex_name)
    return palace, 0


def _na_jia_for_hexagram(upper: str, lower: str) -> list[str]:
    """6 爻的地支（自下而上）。"""
    inner = NA_JIA_TABLE[lower]["inner"]
    outer = NA_JIA_TABLE[upper]["outer"]
    return list(inner) + list(outer)


def _six_relatives_for_lines(zhi_per_line: list[str], palace_wuxing: str) -> list[str]:
    """根据每爻地支对照宫主五行得到六亲。"""
    sheng = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
    ke = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

    def relation(my: str, other: str) -> str:
        if my == other:
            return "兄弟"
        if sheng[my] == other:
            return "子孙"
        if ke[my] == other:
            return "妻财"
        if ke[other] == my:
            return "官鬼"
        if sheng[other] == my:
            return "父母"
        return "未知"

    return [relation(palace_wuxing, ZHI_WUXING[z]) for z in zhi_per_line]


# 六神（青龙、朱雀、勾陈、腾蛇、白虎、玄武）按起卦日干起爻
SIX_GODS_ORDER = ["青龙", "朱雀", "勾陈", "腾蛇", "白虎", "玄武"]
SIX_GODS_START_BY_DAY_STEM = {
    "甲": 0, "乙": 0,  # 青龙
    "丙": 1, "丁": 1,  # 朱雀
    "戊": 2,  # 勾陈
    "己": 3,  # 腾蛇
    "庚": 4, "辛": 4,  # 白虎
    "壬": 5, "癸": 5,  # 玄武
}


def _six_gods_for_lines(day_stem: str) -> list[str]:
    """6 爻的六神，自初爻起。"""
    start = SIX_GODS_START_BY_DAY_STEM[day_stem]
    return [SIX_GODS_ORDER[(start + i) % 6] for i in range(6)]


# ── 用神简易判定 ─────────────────────────────────────────────
QUESTION_TO_YONGSHEN = {
    "财": "妻财", "求财": "妻财", "事业": "官鬼", "工作": "官鬼",
    "婚姻": "妻财", "感情": "妻财",  # 男看妻财，女看官鬼（粗略）
    "学业": "父母", "考试": "父母",
    "健康": "子孙", "疾病": "子孙",
    "出行": "父母", "诉讼": "官鬼", "子女": "子孙",
}


def _guess_yong_shen(question: str) -> str:
    for k, v in QUESTION_TO_YONGSHEN.items():
        if k in question:
            return v
    return "妻财"


# ── 互卦 ──────────────────────────────────────────────────
def _hu_gua(lines: list[int]) -> list[int]:
    """互卦：取本卦 2~4 爻为下卦，3~5 爻为上卦。"""
    lower = lines[1:4]   # 二、三、四
    upper = lines[2:5]   # 三、四、五
    return list(lower) + list(upper)


# ── 起卦法 ────────────────────────────────────────────────
def _hexagram_from_lines(lines: list[int]) -> dict:
    upper, lower = _lines_to_trigrams(lines)
    return _lookup_hexagram(upper, lower)


def _meihua_from_numbers(num1: int, num2: int, num3: int) -> tuple[list[int], list[int], int]:
    """梅花易数（3 数法）：num1 取上卦、num2 取下卦、num3 决定动爻。
    返回 (本卦 6 爻, 变卦 6 爻, 动爻位置 1-6)。
    """
    upper_idx = num1 % 8 or 8
    lower_idx = num2 % 8 or 8
    moving_line = num3 % 6 or 6
    upper_name = TRIGRAM_NUMBER_PRENATAL[upper_idx]
    lower_name = TRIGRAM_NUMBER_PRENATAL[lower_idx]
    ben_lines = _build_hexagram_lines(upper_name, lower_name)
    bian_lines = list(ben_lines)
    bian_lines[moving_line - 1] ^= 1  # 反转动爻
    return ben_lines, bian_lines, moving_line


def _meihua_from_time(dt: datetime) -> tuple[list[int], list[int], int]:
    """时间起卦：年支号 + 月 + 日 取上卦；上数加时辰序号取下卦；总和取动爻。"""
    # 年支序号：子=1, 丑=2, ..., 亥=12
    # 这里用阳历年序号简化：(year - 1900) % 12 + 1
    year_num = (dt.year - 1900) % 12 + 1
    month = dt.month
    day = dt.day
    # 时辰序：子=1...亥=12
    hour = dt.hour
    if hour == 23 or hour < 1:
        hour_num = 1
    else:
        hour_num = ((hour + 1) // 2) % 12 + 1

    upper_total = year_num + month + day
    lower_total = upper_total + hour_num
    moving = (upper_total + hour_num) % 6 or 6
    return _meihua_from_numbers(upper_total, lower_total, moving)


def _coin_throw() -> int:
    """单次掷三枚硬币 → 老阴(6)/少阳(7)/少阴(8)/老阳(9)。
    每枚正面记 3 分、反面记 2 分；3 枚相加 6/7/8/9。
    """
    coins = [secrets.randbelow(2) for _ in range(3)]  # 0=反 1=正
    score = sum(3 if c == 1 else 2 for c in coins)
    return score


def _coin_results_to_lines(coin_results: list[list[int]]) -> tuple[list[int], list[int], list[int]]:
    """coin_results: 6 次每次三枚硬币（1=正、0=反），自初爻到上爻。
    返回 (本卦 6 爻, 变卦 6 爻, 动爻位置列表 1-6)。
    """
    if len(coin_results) != 6:
        raise ValueError("铜钱起卦需要 6 次掷币结果")
    ben: list[int] = []
    bian: list[int] = []
    moving: list[int] = []
    for i, coins in enumerate(coin_results):
        if len(coins) != 3:
            raise ValueError("每次需 3 枚硬币")
        score = sum(3 if c == 1 else 2 for c in coins)  # 6/7/8/9
        if score == 6:  # 老阴 → 阴 → 变阳
            ben.append(0); bian.append(1); moving.append(i + 1)
        elif score == 7:  # 少阳
            ben.append(1); bian.append(1)
        elif score == 8:  # 少阴
            ben.append(0); bian.append(0)
        elif score == 9:  # 老阳 → 阳 → 变阴
            ben.append(1); bian.append(0); moving.append(i + 1)
    return ben, bian, moving


# ── 综合输出 ─────────────────────────────────────────────────
def _build_chart(method: str, question: str, ben_lines: list[int],
                  bian_lines: list[int], moving_lines: list[int],
                  dt: datetime | None = None) -> HexagramChart:
    """根据本/变/动爻构造完整 HexagramChart。"""
    ben = _hexagram_from_lines(ben_lines)
    bian = _hexagram_from_lines(bian_lines)
    hu_lines = _hu_gua(ben_lines)
    hu = _hexagram_from_lines(hu_lines)

    # 京房纳甲：每爻地支
    line_zhi = _na_jia_for_hexagram(ben["upper_trigram"], ben["lower_trigram"])

    # 宫主五行
    palace_name, in_palace_idx = _palace_index(ben["name"])
    palace_wx = TRIGRAM_TO_FIVEELEMENT[palace_name]
    six_relatives = _six_relatives_for_lines(line_zhi, palace_wx)

    # 世应
    shi_yao = SHI_YAO_BY_INDEX_IN_PALACE[in_palace_idx]
    ying_yao = ((shi_yao - 1 + 3) % 6) + 1

    # 六神（按起卦日干）
    if dt is None:
        dt = datetime.now()
    day_stem, _, _ = get_day_pillar(dt)
    six_gods = _six_gods_for_lines(day_stem)

    # 用神
    yong_shen = _guess_yong_shen(question)

    # 增强本/变卦字段
    ben_full = {
        **ben,
        "line_branches": line_zhi,
        "line_relatives": six_relatives,
        "line_gods": six_gods,
        "palace": palace_name,
        "palace_wuxing": palace_wx,
        "shi_yao": shi_yao,
        "ying_yao": ying_yao,
    }
    bian_full = {
        **bian,
        "line_branches": _na_jia_for_hexagram(bian["upper_trigram"], bian["lower_trigram"]),
    }
    hu_full = {
        **hu,
        "line_branches": _na_jia_for_hexagram(hu["upper_trigram"], hu["lower_trigram"]),
    }

    metadata: dict[str, Any] = {
        "ben_gua_id": ben["id"],
        "bian_gua_id": bian["id"],
        "hu_gua_id": hu["id"],
        "palace": palace_name,
        "palace_index": in_palace_idx,
        "day_stem_used": day_stem,
        "note": (
            "本卦/变卦/互卦+京房纳甲+世应+六神计算完整; "
            "用神按问题关键词简单匹配; 男女六亲细分需上层补充"
        ),
    }

    return HexagramChart(
        method=method,
        question=question,
        ben_gua=ben_full,
        bian_gua=bian_full,
        hu_gua=hu_full,
        moving_lines=moving_lines,
        yong_shen=yong_shen,
        shi_yao=shi_yao,
        ying_yao=ying_yao,
        six_relatives=six_relatives,
        six_gods=six_gods,
        metadata=metadata,
    )


# ── 入口函数 ────────────────────────────────────────────────
def compute_meihua(question: str = "", numbers: tuple[int, int] | None = None,
                    dt: datetime | None = None) -> HexagramChart:
    """梅花易数。

    参数：
        question: 问题文本（用于简易用神判定）
        numbers: 可选 (a, b)，两数法；为空则用时间起卦
        dt: 时间起卦的时间，默认 now()
    """
    if dt is None:
        dt = datetime.now()
    if numbers is not None:
        a, b = numbers
        ben, bian, mv = _meihua_from_numbers(a, b, a + b)
        moving = [mv]
    else:
        ben, bian, mv = _meihua_from_time(dt)
        moving = [mv]
    return _build_chart("meihua", question, ben, bian, moving, dt)


def compute_coin(question: str = "",
                  coin_results: list[list[int]] | None = None) -> HexagramChart:
    """铜钱起卦。

    参数：
        question: 问题文本
        coin_results: 6 次掷币结果，每次 3 枚 (1=正/0=反)；为空则随机
    """
    if coin_results is None:
        # 随机生成
        coin_results = [[secrets.randbelow(2) for _ in range(3)] for _ in range(6)]
    ben, bian, moving = _coin_results_to_lines(coin_results)
    return _build_chart("coin", question, ben, bian, moving, datetime.now())


# ── CLI 测试 ────────────────────────────────────────────────
if __name__ == "__main__":
    import json

    # 1. 梅花数字起卦
    print("=== 梅花数字起卦 (3, 5) ===")
    chart1 = compute_meihua("我今年事业如何？", numbers=(3, 5))
    print(json.dumps(chart1.model_dump(), default=str, ensure_ascii=False, indent=2))

    print("\n\n=== 铜钱起卦（随机模拟）===")
    chart2 = compute_coin("近期感情走向？")
    print(json.dumps(chart2.model_dump(), default=str, ensure_ascii=False, indent=2))
