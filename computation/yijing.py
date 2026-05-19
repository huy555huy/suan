"""易经 / 六爻 / 梅花易数 计算引擎。

实现要点：
    1. 64 卦数据：``HEXAGRAMS`` 提供每卦 (id, 卦名, 上卦, 下卦, 6 爻, 卦辞简略, 彖辞)
    2. 起卦法：
        - ``compute_meihua``：梅花易数（数字起卦 / 时间起卦）
        - ``compute_coin``：铜钱起卦（6 次三枚硬币结果）
    3. 本卦 / 变卦 / 互卦 / 动爻
    4. 京房纳甲：六爻盘由 najia 计算纳甲、六亲、伏神、世应、六神
    5. 用神（按问题类型简单映射）

入口：
    - compute_meihua(question, numbers=None, dt) -> HexagramChart
    - compute_coin(question, coin_results) -> HexagramChart
"""
from __future__ import annotations

from datetime import datetime
from importlib.metadata import version
from typing import Any

from core.schemas import HexagramChart
from computation.calendar import (
    DI_ZHI,
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
WUXING_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
WUXING_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
MONTH_BRANCH_BY_GANZHI_MONTH = {
    "寅": {"旺": {"木"}, "相": {"火"}, "休": {"水"}, "囚": {"金"}, "死": {"土"}},
    "卯": {"旺": {"木"}, "相": {"火"}, "休": {"水"}, "囚": {"金"}, "死": {"土"}},
    "辰": {"旺": {"土"}, "相": {"金"}, "休": {"火"}, "囚": {"木"}, "死": {"水"}},
    "巳": {"旺": {"火"}, "相": {"土"}, "休": {"木"}, "囚": {"水"}, "死": {"金"}},
    "午": {"旺": {"火"}, "相": {"土"}, "休": {"木"}, "囚": {"水"}, "死": {"金"}},
    "未": {"旺": {"土"}, "相": {"金"}, "休": {"火"}, "囚": {"木"}, "死": {"水"}},
    "申": {"旺": {"金"}, "相": {"水"}, "休": {"土"}, "囚": {"火"}, "死": {"木"}},
    "酉": {"旺": {"金"}, "相": {"水"}, "休": {"土"}, "囚": {"火"}, "死": {"木"}},
    "戌": {"旺": {"土"}, "相": {"金"}, "休": {"火"}, "囚": {"木"}, "死": {"水"}},
    "亥": {"旺": {"水"}, "相": {"木"}, "休": {"金"}, "囚": {"土"}, "死": {"火"}},
    "子": {"旺": {"水"}, "相": {"木"}, "休": {"金"}, "囚": {"土"}, "死": {"火"}},
    "丑": {"旺": {"土"}, "相": {"金"}, "休": {"火"}, "囚": {"木"}, "死": {"水"}},
}
RELATIVE_HINTS = {
    "妻财": "钱财、资源、交易、男命感情对象",
    "官鬼": "工作、职位、规则压力、女命感情对象、疾病忧患",
    "父母": "文书、证件、房屋、长辈、考试资料",
    "子孙": "结果、产出、子女、医药、解忧",
    "兄弟": "同辈、竞争、耗财、朋友同事",
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
# 按上卦/下卦 8 卦各自的纳甲规律
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

    使用完整八宫顺序表；卦名缺失视为数据错误。
    """
    palace = PALACE_OF_HEXAGRAM[hex_name]
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
    raise ValueError(f"京房八宫顺序表缺少卦名：{hex_name}")


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
    "财": "妻财", "求财": "妻财", "投资": "妻财", "收入": "妻财",
    "事业": "官鬼", "工作": "官鬼", "职位": "官鬼", "升职": "官鬼",
    "学业": "父母", "考试": "父母", "合同": "父母", "房": "父母",
    "健康": "子孙", "疾病": "官鬼", "病": "官鬼",
    "出行": "父母", "诉讼": "官鬼", "子女": "子孙", "合作": "应爻",
}
RELATIONSHIP_KEYWORDS = ("婚姻", "感情", "恋爱", "复合", "对象", "伴侣", "男友", "女友", "丈夫", "妻子")
MALE_SELF_HINTS = ("男", "男方", "男生", "男性", "丈夫", "老公", "我追她", "女友", "女朋友", "妻子")
FEMALE_SELF_HINTS = ("女", "女方", "女生", "女性", "妻", "太太", "我追他", "男友", "男朋友", "丈夫")


def _infer_yong_shen(question: str) -> dict[str, Any]:
    q = question or ""
    if any(keyword in q for keyword in RELATIONSHIP_KEYWORDS):
        male_hit = any(keyword in q for keyword in MALE_SELF_HINTS)
        female_hit = any(keyword in q for keyword in FEMALE_SELF_HINTS)
        if male_hit and not female_hit:
            return {
                "value": "妻财",
                "source": "relationship_male_self",
                "confidence": "medium",
                "needs_clarification": [],
            }
        if female_hit and not male_hit:
            return {
                "value": "官鬼",
                "source": "relationship_female_self",
                "confidence": "medium",
                "needs_clarification": [],
            }
        return {
            "value": None,
            "source": "relationship_requires_identity",
            "confidence": "low",
            "needs_clarification": ["感情/婚姻占需确认求测者性别与所问对象；男问伴侣多取妻财，女问伴侣多取官鬼。"],
        }
    for k, v in QUESTION_TO_YONGSHEN.items():
        if k in q:
            return {
                "value": v,
                "source": f"keyword:{k}",
                "confidence": "medium",
                "needs_clarification": [],
            }
    return {
        "value": None,
        "source": "unclassified_question",
        "confidence": "low",
        "needs_clarification": ["问题未能归入财、官、父母、子孙等明确占事；请补充具体所问对象，再定用神。"],
    }


def _month_state_for_wuxing(month_branch: str, wuxing: str | None) -> str | None:
    if not wuxing:
        return None
    table = MONTH_BRANCH_BY_GANZHI_MONTH.get(month_branch)
    if not table:
        return None
    for state, elements in table.items():
        if wuxing in elements:
            return state
    return None


def _relation_between_elements(source: str | None, target: str | None) -> str:
    if not source or not target:
        return "未知"
    if source == target:
        return "比和"
    if WUXING_SHENG[source] == target:
        return "生"
    if WUXING_KE[source] == target:
        return "克"
    if WUXING_SHENG[target] == source:
        return "被生"
    if WUXING_KE[target] == source:
        return "被克"
    return "无直接生克"


def _line_by_position(lines: list[dict[str, Any]], position: int) -> dict[str, Any] | None:
    for line in lines:
        if line["position"] == position:
            return line
    return None


def _analyze_liuyao(question: str, yong_shen_info: dict[str, Any], data: dict[str, Any],
                    ben_lines_detail: list[dict[str, Any]]) -> dict[str, Any]:
    gz = data["lunar"]["gz"]
    month_branch = gz["month"][1]
    day_branch = gz["day"][1]
    xun_kong = set(data["lunar"]["xkong"])
    yong_shen = yong_shen_info.get("value")
    yong_lines = [
        line for line in ben_lines_detail
        if yong_shen is not None and line["six_relative"] == yong_shen
    ]
    shi = _line_by_position(ben_lines_detail, data["shiy"][0])
    ying = _line_by_position(ben_lines_detail, data["shiy"][1])
    moving = [line for line in ben_lines_detail if line["moving"]]

    enriched_yong_lines: list[dict[str, Any]] = []
    for line in yong_lines:
        month_state = _month_state_for_wuxing(month_branch, line["wuxing"])
        score = 0
        if month_state in ("旺", "相"):
            score += 1
        if line["branch"] == day_branch:
            score += 1
        if line["branch"] in xun_kong:
            score -= 1
        if line["moving"]:
            score += 1
        enriched_yong_lines.append({
            **line,
            "month_state": month_state,
            "day_same_branch": line["branch"] == day_branch,
            "is_xun_kong": line["branch"] in xun_kong,
            "strength_score": score,
            "strength_label": "旺" if score >= 2 else "有气" if score == 1 else "偏弱" if score == 0 else "空弱",
        })

    yong_positions = [line["position"] for line in enriched_yong_lines]
    moving_effects = []
    for line in moving:
        effect = {
            "from_position": line["position"],
            "from_relative": line["six_relative"],
            "from_wuxing": line["wuxing"],
            "to_yong_shen": [],
            "to_shi": _relation_between_elements(line["wuxing"], shi["wuxing"] if shi else None),
            "to_ying": _relation_between_elements(line["wuxing"], ying["wuxing"] if ying else None),
        }
        for yong_line in enriched_yong_lines:
            effect["to_yong_shen"].append({
                "target_position": yong_line["position"],
                "relation": _relation_between_elements(line["wuxing"], yong_line["wuxing"]),
            })
        moving_effects.append(effect)

    shi_ying_relation = {
        "shi": shi,
        "ying": ying,
        "shi_to_ying": _relation_between_elements(shi["wuxing"] if shi else None, ying["wuxing"] if ying else None),
        "ying_to_shi": _relation_between_elements(ying["wuxing"] if ying else None, shi["wuxing"] if shi else None),
    }
    missing_required = []
    missing_required = list(yong_shen_info.get("needs_clarification", []))
    if yong_shen is None:
        missing_required.append("用神未定，不应输出确定吉凶；需先补清占事对象。")
    elif not yong_lines:
        missing_required.append("用神不上卦，需看伏神/飞神，当前应标为隐伏或事象不明。")

    return {
        "question_yong_shen": yong_shen,
        "yong_shen_source": yong_shen_info.get("source"),
        "yong_shen_confidence": yong_shen_info.get("confidence"),
        "yong_shen_hint": RELATIVE_HINTS.get(yong_shen),
        "month_branch": month_branch,
        "day_branch": day_branch,
        "xun_kong": data["lunar"]["xkong"],
        "yong_shen_positions": yong_positions,
        "yong_shen_lines": enriched_yong_lines,
        "shi_ying_relation": shi_ying_relation,
        "moving_effects": moving_effects,
        "hidden_spirits": data.get("hide"),
        "needs_clarification": missing_required,
    }


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
    from lunar_python import Solar

    # 年支序号：子=1, 丑=2, ..., 亥=12，按节气精确年柱取值。
    lunar = Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second).getLunar()
    year_zhi = lunar.getYearZhiExact()
    year_num = DI_ZHI.index(year_zhi) + 1
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


def _line_param_to_line(param: int) -> int:
    return int(param) % 2


def _line_param_to_transformed_line(param: int) -> int:
    return 1 if int(param) in (1, 4) else 0


def _params_to_lines(params: list[int]) -> tuple[list[int], list[int], list[int]]:
    if len(params) != 6:
        raise ValueError("六爻参数必须为 6 爻，自初爻到上爻。")
    ben = [_line_param_to_line(v) for v in params]
    bian = [_line_param_to_transformed_line(v) for v in params]
    moving = [i + 1 for i, v in enumerate(params) if int(v) > 2]
    return ben, bian, moving


def _coin_results_to_najia_params(coin_results: list[list[int]]) -> list[int]:
    """三枚铜钱 → najia 参数，自初爻到上爻。

    1=少阳，0=少阴，3=老阴动化阳，4=老阳动化阴。
    coin_results 中 1 计 3 分、0 计 2 分。
    """
    if len(coin_results) != 6:
        raise ValueError("铜钱起卦需要 6 次掷币结果")
    params: list[int] = []
    score_to_param = {6: 3, 7: 1, 8: 0, 9: 4}
    for coins in coin_results:
        if len(coins) != 3:
            raise ValueError("每次需 3 枚铜钱")
        if any(c not in (0, 1) for c in coins):
            raise ValueError("铜钱结果只能使用 1=正、0=反")
        score = sum(3 if c == 1 else 2 for c in coins)
        params.append(score_to_param[score])
    return params


def _lines_to_najia_params(ben_lines: list[int], moving_lines: list[int]) -> list[int]:
    moving = set(moving_lines)
    params: list[int] = []
    for idx, line in enumerate(ben_lines, start=1):
        if line == 1:
            params.append(4 if idx in moving else 1)
        elif line == 0:
            params.append(3 if idx in moving else 0)
        else:
            raise ValueError(f"爻值必须为 0/1，收到 {line!r}")
    return params


def _split_qinx(value: str) -> dict[str, str | None]:
    if not value:
        return {"stem": None, "branch": None, "wuxing": None, "ganzhi": None, "text": value}
    return {
        "stem": value[0] if len(value) >= 1 else None,
        "branch": value[1] if len(value) >= 2 else None,
        "wuxing": value[2:] or None,
        "ganzhi": value[:2] if len(value) >= 2 else None,
        "text": value,
    }


def _enrich_lines(mark: str, qin6: list[str], qinx: list[str],
                  gods: list[str] | tuple[str, ...] | None = None,
                  moving: list[int] | None = None) -> list[dict[str, Any]]:
    moving_set = set(moving or [])
    result: list[dict[str, Any]] = []
    for idx, raw_line in enumerate(mark, start=1):
        parsed = _split_qinx(qinx[idx - 1])
        result.append({
            "position": idx,
            "line": int(raw_line),
            "yin_yang": "阳" if raw_line == "1" else "阴",
            "six_relative": qin6[idx - 1],
            "ganzhi_wuxing": qinx[idx - 1],
            "stem": parsed["stem"],
            "branch": parsed["branch"],
            "wuxing": parsed["wuxing"],
            "six_god": gods[idx - 1] if gods else None,
            "moving": idx - 1 in moving_set,
        })
    return result


def _hexagram_from_najia_name(name: str, mark: str) -> dict[str, Any]:
    if name.endswith("为天"):
        simple_name = "乾"
    elif name.endswith("为泽"):
        simple_name = "兑"
    elif name.endswith("为火"):
        simple_name = "离"
    elif name.endswith("为雷"):
        simple_name = "震"
    elif name.endswith("为风"):
        simple_name = "巽"
    elif name.endswith("为水"):
        simple_name = "坎"
    elif name.endswith("为山"):
        simple_name = "艮"
    elif name.endswith("为地"):
        simple_name = "坤"
    else:
        simple_name = name[-1] if len(name) >= 3 and name[1] in "天地风雷水火山泽" else name
    try:
        base = _hexagram_from_lines([int(x) for x in mark])
    except Exception:
        base = {"name": simple_name, "lines": [int(x) for x in mark]}
    base["full_name"] = name
    return base


def _compile_najia(params: list[int], dt: datetime, question: str):
    from najia import Najia

    return Najia(0).compile(params=params, date=dt, title=question)


def _build_chart_from_najia(method: str, question: str, params: list[int],
                            dt: datetime, hu_lines: list[int] | None = None) -> HexagramChart:
    gua = _compile_najia(params, dt, question)
    data = gua.data
    if data is None:
        raise ValueError("najia 未返回排盘数据")

    ben_lines, bian_lines, moving_lines = _params_to_lines(params)
    ben = _hexagram_from_najia_name(data["name"], data["mark"])
    bian = None
    transformed_mark = "".join(str(x) for x in bian_lines)
    if data.get("bian"):
        bian_raw = data["bian"]
        bian = _hexagram_from_najia_name(bian_raw["name"], bian_raw["mark"])
        bian.update({
            "mark": bian_raw["mark"],
            "palace": bian_raw.get("gong"),
            "line_relatives": bian_raw.get("qin6", []),
            "line_ganzhi_wuxing": bian_raw.get("qinx", []),
            "lines_detail": _enrich_lines(
                bian_raw["mark"],
                bian_raw.get("qin6", []),
                bian_raw.get("qinx", []),
            ),
        })
    elif transformed_mark != data["mark"]:
        bian = _hexagram_from_lines(bian_lines)
        bian.update({"mark": transformed_mark})

    hu_source = hu_lines if hu_lines is not None else _hu_gua(ben_lines)
    hu = _hexagram_from_lines(hu_source)

    shi_yao, ying_yao, palace_index = data["shiy"]
    six_gods = list(data["god6"])
    six_relatives = list(data["qin6"])
    qinx = list(data["qinx"])
    ben_lines_detail = _enrich_lines(data["mark"], six_relatives, qinx, six_gods, data["dong"])
    ben.update({
        "mark": data["mark"],
        "palace": data["gong"],
        "palace_index": palace_index,
        "line_relatives": six_relatives,
        "line_gods": six_gods,
        "line_ganzhi_wuxing": qinx,
        "lines_detail": ben_lines_detail,
        "shi_yao": shi_yao,
        "ying_yao": ying_yao,
        "xun_kong": data["lunar"]["xkong"],
        "gan_zhi": data["lunar"]["gz"],
    })
    hu.update({
        "mark": "".join(str(x) for x in hu_source),
    })

    yong_shen_info = _infer_yong_shen(question)
    yong_shen = yong_shen_info.get("value")
    liuyao_analysis = _analyze_liuyao(question, yong_shen_info, data, ben_lines_detail)
    metadata: dict[str, Any] = {
        "engine": "najia",
        "engine_version": version("najia"),
        "params": list(params),
        "line_encoding": "0=少阴, 1=少阳, 3=老阴动化阳, 4=老阳动化阴",
        "ben_gua_id": ben.get("id"),
        "bian_gua_id": bian.get("id") if bian else None,
        "hu_gua_id": hu.get("id"),
        "palace": data["gong"],
        "palace_index": palace_index,
        "xun_kong": data["lunar"]["xkong"],
        "gan_zhi": data["lunar"]["gz"],
        "hide": data.get("hide"),
        "liuyao_analysis": liuyao_analysis,
        "render": gua.render(),
        "yong_shen_note": "用神按明确占事关键词给候选；感情等涉及身份的问题若缺求测者信息，会标记 needs_clarification，不输出确定吉凶。",
    }

    return HexagramChart(
        method=method,
        question=question,
        ben_gua=ben,
        bian_gua=bian,
        hu_gua=hu,
        moving_lines=moving_lines,
        yong_shen=yong_shen,
        shi_yao=shi_yao,
        ying_yao=ying_yao,
        six_relatives=six_relatives,
        six_gods=six_gods,
        metadata=metadata,
    )


# ── 综合输出 ─────────────────────────────────────────────────
def _build_chart(method: str, question: str, ben_lines: list[int],
                  bian_lines: list[int], moving_lines: list[int],
                  dt: datetime | None = None) -> HexagramChart:
    if dt is None:
        raise ValueError("起卦时间缺失；请提供明确起卦时间。")
    params = _lines_to_najia_params(ben_lines, moving_lines)
    return _build_chart_from_najia(method, question, params, dt, hu_lines=_hu_gua(ben_lines))


# ── 入口函数 ────────────────────────────────────────────────
def compute_meihua(question: str = "", numbers: tuple[int, int] | None = None,
                    dt: datetime | None = None) -> HexagramChart:
    """梅花易数。

    参数：
        question: 问题文本（用于简易用神判定）
        numbers: 可选 (a, b)，两数法；为空则用时间起卦
        dt: 时间起卦的时间；时间起卦必须显式提供
    """
    if numbers is not None:
        a, b = numbers
        ben, bian, mv = _meihua_from_numbers(a, b, a + b)
        moving = [mv]
    else:
        if dt is None:
            raise ValueError("梅花时间起卦需要明确起卦时间；不能默认使用系统当前时间。")
        ben, bian, mv = _meihua_from_time(dt)
        moving = [mv]
    return _build_chart("meihua", question, ben, bian, moving, dt)


def compute_coin(question: str = "",
                 coin_results: list[list[int]] | None = None,
                 dt: datetime | None = None) -> HexagramChart:
    """铜钱起卦。

    参数：
        question: 问题文本
        coin_results: 6 次掷币结果，每次 3 枚 (1=正/0=反)
        dt: 起卦时间；用于日辰/六神
    """
    if coin_results is None:
        raise ValueError("铜钱起卦需要用户提供 6 次掷币结果；不能由系统随机生成。")
    if dt is None:
        raise ValueError("铜钱起卦需要明确起卦时间；不能默认使用系统当前时间。")
    ben, bian, moving = _coin_results_to_lines(coin_results)
    return _build_chart("coin", question, ben, bian, moving, dt=dt)


# ── CLI 测试 ────────────────────────────────────────────────
if __name__ == "__main__":
    import json

    # 1. 梅花数字起卦
    print("=== 梅花数字起卦 (3, 5) ===")
    chart1 = compute_meihua("我今年事业如何？", numbers=(3, 5), dt=datetime(2026, 5, 19, 12, 0))
    print(json.dumps(chart1.model_dump(), default=str, ensure_ascii=False, indent=2))

    print("\n\n=== 铜钱起卦（固定结果示例）===")
    chart2 = compute_coin(
        "近期感情走向？",
        coin_results=[
            [1, 1, 0],
            [1, 0, 0],
            [1, 1, 1],
            [0, 0, 0],
            [1, 0, 1],
            [0, 1, 0],
        ],
        dt=datetime(2026, 5, 19, 12, 0),
    )
    print(json.dumps(chart2.model_dump(), default=str, ensure_ascii=False, indent=2))
