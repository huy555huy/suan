"""风水计算引擎：玄空飞星（下卦） + 八宅。

实现要点：
    1. 三元九运：1864-1883=1运、... 8运=2004-2023、9运=2024-2043、1运=2044-2063
    2. 24 山方位：壬子癸 / 丑艮寅 / 甲卯乙 / 辰巽巳 / 丙午丁 / 未坤申 / 庚酉辛 / 戌乾亥
    3. 玄空下卦：
        - 运盘：当令运星入中宫，洛书顺飞 9 宫
        - 山盘：从运盘"坐山位"取数入中宫；按坐山阴阳决顺/逆飞
        - 向盘：从运盘"向首位"取数入中宫；按向首阴阳决顺/逆飞
    4. 旺衰：当运为旺；下一运为生气；上一运为衰；衰退之衰为死气
    5. 八宅命卦：
        - 男：(100 - 出生年末两位) % 9，结果 0 视为 9
        - 女：(出生年末两位 - 4) % 9，结果 0 视为 9
        - 命卦数 → 八卦名（坎离震兑乾坤艮巽 + 5寄坤/艮）
    6. 四吉位（生气、天医、延年、伏位）/ 四凶位（绝命、五鬼、六煞、祸害）按八宅游年表

入口：``compute_fengshui(facing_degree, birth, move_in_year=2024)``
"""
from __future__ import annotations

from typing import Any

from core.schemas import BirthInfo, FengshuiChart


# ── 24 山 ────────────────────────────────────────────────────
# 24 山按角度划分，每山 15°，从北方 0°/360° 起顺时针
# 标准排列：北方壬(337.5-352.5)、子(352.5-7.5)、癸(7.5-22.5)；
# 东北 丑(22.5-37.5)、艮(37.5-52.5)、寅(52.5-67.5)；
# 东 甲(67.5-82.5)、卯(82.5-97.5)、乙(97.5-112.5)；
# 东南 辰(112.5-127.5)、巽(127.5-142.5)、巳(142.5-157.5)；
# 南 丙(157.5-172.5)、午(172.5-187.5)、丁(187.5-202.5)；
# 西南 未(202.5-217.5)、坤(217.5-232.5)、申(232.5-247.5)；
# 西 庚(247.5-262.5)、酉(262.5-277.5)、辛(277.5-292.5)；
# 西北 戌(292.5-307.5)、乾(307.5-322.5)、亥(322.5-337.5)
SHAN_24 = [
    "壬", "子", "癸",
    "丑", "艮", "寅",
    "甲", "卯", "乙",
    "辰", "巽", "巳",
    "丙", "午", "丁",
    "未", "坤", "申",
    "庚", "酉", "辛",
    "戌", "乾", "亥",
]

# 24 山阴阳（决定飞星顺/逆）
# 标准：壬阳子阴癸阴；丑阴艮阳寅阳；甲阳卯阴乙阴；辰阴巽阳巳阳；丙阳午阴丁阴；
#       未阴坤阳申阳；庚阳酉阴辛阴；戌阴乾阳亥阳
SHAN_YINYANG = {
    "壬": "阳", "子": "阴", "癸": "阴",
    "丑": "阴", "艮": "阳", "寅": "阳",
    "甲": "阳", "卯": "阴", "乙": "阴",
    "辰": "阴", "巽": "阳", "巳": "阳",
    "丙": "阳", "午": "阴", "丁": "阴",
    "未": "阴", "坤": "阳", "申": "阳",
    "庚": "阳", "酉": "阴", "辛": "阴",
    "戌": "阴", "乾": "阳", "亥": "阳",
}

# 8 卦方位 → 在 9 宫格中的位置（洛书数）
# 洛书：4 9 2 / 3 5 7 / 8 1 6
# 对应：巽 离 坤 / 震 中 兑 / 艮 坎 乾
LUOSHU_NUM_TO_BAGUA = {
    1: "坎", 2: "坤", 3: "震", 4: "巽",
    5: "中", 6: "乾", 7: "兑", 8: "艮", 9: "离",
}
BAGUA_TO_LUOSHU_NUM = {v: k for k, v in LUOSHU_NUM_TO_BAGUA.items()}

BAGUA_DIRECTIONS = {
    "坎": "北", "坤": "西南", "震": "东", "巽": "东南",
    "中": "中宫", "乾": "西北", "兑": "西", "艮": "东北", "离": "南",
}

# 24 山 → 8 卦
SHAN_TO_BAGUA = {
    "壬": "坎", "子": "坎", "癸": "坎",
    "丑": "艮", "艮": "艮", "寅": "艮",
    "甲": "震", "卯": "震", "乙": "震",
    "辰": "巽", "巽": "巽", "巳": "巽",
    "丙": "离", "午": "离", "丁": "离",
    "未": "坤", "坤": "坤", "申": "坤",
    "庚": "兑", "酉": "兑", "辛": "兑",
    "戌": "乾", "乾": "乾", "亥": "乾",
}

# 9 宫位置编号（行 row=0..2 自上 → 下，col=0..2 自左 → 右）
# 洛书：4 9 2 / 3 5 7 / 8 1 6
LUOSHU_DEFAULT = [
    [4, 9, 2],
    [3, 5, 7],
    [8, 1, 6],
]
# 反查：数字 → (row, col)
LUOSHU_NUM_POS: dict[int, tuple[int, int]] = {}
for r, row in enumerate(LUOSHU_DEFAULT):
    for c, n in enumerate(row):
        LUOSHU_NUM_POS[n] = (r, c)

# 飞星顺序（顺飞）：5 中宫起，6 西北、7 西、8 东北、9 南、1 北、2 西南、3 东、4 东南
# 标准飞星路径：中 → 西北 → 西 → 东北 → 南 → 北 → 西南 → 东 → 东南
FLYING_PATH = [
    (1, 1),  # 中
    (2, 0),  # 西北? 实际是 6 落西北。这里给出顺飞路径的位置序列
    (0, 2),  # 西? 不对 — 让我们重新定义。
]
# 上面的简单定义有错，下面用直接公式法：

# 标准玄空顺飞表：当某数 N 入中宫时，N+0=中、N+1=西北、N+2=西、N+3=东北、N+4=南、N+5=北、N+6=西南、N+7=东、N+8=东南
# 反映到行列：中(1,1) → 西北(0,0)? 错。
# 正确的洛书飞星顺序（按中宫为起点的运行轨迹）：
#   1. 中宫(1,1)
#   2. 西北(0,0) -- 乾
#   错！实际是西北 = 在洛书中数字 6 的位置 = (2,2)！
# 让我重新查一下洛书排布：
#   北 = 1 = 底中 = (2,1)
#   东北 = 8 = 底左 = (2,0)
#   东 = 3 = 中左 = (1,0)
#   东南 = 4 = 上左 = (0,0)
#   南 = 9 = 上中 = (0,1)
#   西南 = 2 = 上右 = (0,2)
#   西 = 7 = 中右 = (1,2)
#   西北 = 6 = 底右 = (2,2)
#   中宫 = 5 = (1,1)
# 所以正确洛书：
#   row 0: 4 9 2  (东南 / 南 / 西南)
#   row 1: 3 5 7  (东   / 中 / 西)
#   row 2: 8 1 6  (东北 / 北 / 西北)

# 顺飞路径（中宫起，按"中→乾(西北)→兑(西)→艮(东北)→离(南)→坎(北)→坤(西南)→震(东)→巽(东南)"）:
FLYING_ORDER_POSITIONS = [
    (1, 1),  # 中宫 5
    (2, 2),  # 西北 6
    (1, 2),  # 西 7
    (2, 0),  # 东北 8
    (0, 1),  # 南 9
    (2, 1),  # 北 1
    (0, 2),  # 西南 2
    (1, 0),  # 东 3
    (0, 0),  # 东南 4
]


def _flying_pan(seed: int, forward: bool = True) -> list[list[int]]:
    """以 seed 入中宫，按 forward (True 顺飞 / False 逆飞) 排出 9 宫。

    返回 3x3 数字矩阵，每数 1-9，9 之后回到 1。
    """
    pan = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
    delta = 1 if forward else -1
    for i, (r, c) in enumerate(FLYING_ORDER_POSITIONS):
        n = ((seed - 1 + i * delta) % 9) + 1
        pan[r][c] = n
    return pan


# ── 三元九运 ─────────────────────────────────────────────────
# 1运 1864-1883, 2运 1884-1903, ..., 9运 2024-2043
def _period_of_year(year: int) -> int:
    """返回某年所属三元九运（1-9）。"""
    base = 1864
    period = ((year - base) // 20) % 9 + 1
    return period


def _shan_at_degree(degree: float) -> str:
    """根据角度获取 24 山名。"""
    deg = degree % 360
    # 起始位置：壬山 = 337.5°
    idx = int(((deg - 337.5 + 360) % 360) // 15)
    return SHAN_24[idx]


def _opposite_shan(shan: str) -> str:
    """相对的山（朝向 ↔ 坐山）。"""
    idx = SHAN_24.index(shan)
    return SHAN_24[(idx + 12) % 24]


# ── 山向飞星 ────────────────────────────────────────────────
def _calc_yun_pan(period: int) -> list[list[int]]:
    """运盘：当运数入中宫顺飞。"""
    return _flying_pan(period, forward=True)


def _calc_shan_xiang_pan(period: int, sitting_shan: str, facing_shan: str) -> tuple[list[list[int]], list[list[int]]]:
    """山盘 + 向盘。

    山盘种子：运盘上"坐山位"那一格的数字
    向盘种子：运盘上"向首位"那一格的数字
    顺逆飞：以"该数字所在山"的阴阳决定（阳顺，阴逆）。
    """
    yun = _calc_yun_pan(period)
    sit_bagua = SHAN_TO_BAGUA[sitting_shan]
    face_bagua = SHAN_TO_BAGUA[facing_shan]

    sit_num = BAGUA_TO_LUOSHU_NUM[sit_bagua]
    face_num = BAGUA_TO_LUOSHU_NUM[face_bagua]

    # 找运盘对应卦位上的数字（即该卦位现在落的"运星数"）
    # 在 LUOSHU_DEFAULT 中坎=1的位置 (2,1)；当前 yun 在该位置的数 = ...
    # 用洛书"卦→默认位置"再读 yun 上的数
    sit_pos = LUOSHU_NUM_POS[sit_num]
    face_pos = LUOSHU_NUM_POS[face_num]
    shan_seed = yun[sit_pos[0]][sit_pos[1]]
    xiang_seed = yun[face_pos[0]][face_pos[1]]

    # 山盘顺逆：根据"坐山"24 山阴阳，以及种子数对应的"对应山"组（每数对应 3 山，由具体坐山阴阳决定）
    # 简化规则（玄空通用）：以坐山的阴阳为顺逆飞依据
    sit_yang = SHAN_YINYANG[sitting_shan] == "阳"
    face_yang = SHAN_YINYANG[facing_shan] == "阳"

    shan_pan = _flying_pan(shan_seed, forward=sit_yang)
    xiang_pan = _flying_pan(xiang_seed, forward=face_yang)
    return shan_pan, xiang_pan


# ── 八宅命卦 ────────────────────────────────────────────────
# 命卦数 → 卦名
GUA_BY_NUM = {1: "坎", 2: "坤", 3: "震", 4: "巽",
               5: "坤", 6: "乾", 7: "兑", 8: "艮", 9: "离"}
# （5 男寄坤，5 女寄艮）

# 东四命：坎、离、震、巽；西四命：乾、坤、艮、兑
EAST_GROUP = {"坎", "离", "震", "巽"}
WEST_GROUP = {"乾", "坤", "艮", "兑"}


def _ming_gua(year: int, gender: str) -> str:
    """八宅命卦计算。

    男：(100 - YY) mod 9
    女：(YY - 4) mod 9
    YY = 出生年末 2 位数字之和（含跨千年简化）
    """
    # 用简单方式取末两位
    yy = year % 100
    # 处理出生年份为 2000 后：部分流派用 (10-YY/10) 然后再 mod；这里用经典口诀：
    # 方法：取出生年末两位数字相加直至个位 (例如 1991 → 9+1=10 → 1+0=1)
    s = sum(int(c) for c in str(yy).zfill(2))
    while s >= 10:
        s = sum(int(c) for c in str(s))
    if gender == "male":
        num = 11 - s
        if num >= 10:
            num -= 9
        if num == 5:
            return "坤"  # 男 5 寄坤
    else:
        num = s + 4
        while num > 9:
            num -= 9
        if num == 5:
            return "艮"  # 女 5 寄艮
    return GUA_BY_NUM.get(num, "坎")


# ── 八宅游年（以命卦为中心的 8 个方位吉凶） ────────────────────
# 表内每条："命卦": {方位卦: 吉凶名}
# 方位卦不含中宫。
BA_ZHAI_GAME = {
    "坎": {"坎": "伏位", "巽": "生气", "震": "天医", "离": "延年",
           "坤": "绝命", "艮": "五鬼", "兑": "祸害", "乾": "六煞"},
    "离": {"离": "伏位", "震": "生气", "巽": "天医", "坎": "延年",
           "乾": "绝命", "兑": "五鬼", "艮": "祸害", "坤": "六煞"},
    "震": {"震": "伏位", "离": "生气", "坎": "天医", "巽": "延年",
           "兑": "绝命", "乾": "五鬼", "坤": "祸害", "艮": "六煞"},
    "巽": {"巽": "伏位", "坎": "生气", "离": "天医", "震": "延年",
           "艮": "绝命", "坤": "五鬼", "乾": "祸害", "兑": "六煞"},
    "乾": {"乾": "伏位", "兑": "生气", "艮": "天医", "坤": "延年",
           "离": "绝命", "震": "五鬼", "巽": "祸害", "坎": "六煞"},
    "坤": {"坤": "伏位", "艮": "生气", "兑": "天医", "乾": "延年",
           "坎": "绝命", "巽": "五鬼", "震": "祸害", "离": "六煞"},
    "艮": {"艮": "伏位", "坤": "生气", "乾": "天医", "兑": "延年",
           "震": "绝命", "离": "五鬼", "坎": "祸害", "巽": "六煞"},
    "兑": {"兑": "伏位", "乾": "生气", "坤": "天医", "艮": "延年",
           "巽": "绝命", "坎": "五鬼", "离": "祸害", "震": "六煞"},
}

GOOD_LABELS = {"生气", "天医", "延年", "伏位"}
BAD_LABELS = {"绝命", "五鬼", "六煞", "祸害"}


# ── 旺衰判定 ────────────────────────────────────────────────
def _star_status(star_num: int, current_period: int) -> str:
    """星数对当令的旺衰判定。
    旺 = 当令; 生气 = 下一运; 衰 = 上一运; 死气 = 相对方; 退气 = 上 2 运; 进气 = 下 2 运
    简化：只判断旺/生/退/衰/死。
    """
    diff = (star_num - current_period) % 9
    if diff == 0:
        return "旺"
    if diff == 1:
        return "生气"
    if diff == 2:
        return "进气"
    if diff == 8:
        return "退气"  # 上一运
    if diff == 7:
        return "衰"
    return "煞"


# ── 化煞建议（基于飞星组合） ─────────────────────────────────
# 简化：根据飞星组合常见凶吉给出建议
def _build_remedies(combined_pan: list[dict], current_period: int) -> list[str]:
    """对每个 9 宫位置看山+向飞星组合，输出化煞 / 旺位建议。"""
    advice: list[str] = []
    for cell in combined_pan:
        ss = cell["shan_star"]
        xs = cell["xiang_star"]
        bagua = cell["bagua"]
        if ss == current_period and xs == current_period:
            advice.append(f"{bagua}({BAGUA_DIRECTIONS[bagua]})为山向双星到，旺财旺丁的关键位")
        elif xs == current_period:
            advice.append(f"{bagua}({BAGUA_DIRECTIONS[bagua]})为向星当令位，宜见水或开门")
        elif ss == current_period:
            advice.append(f"{bagua}({BAGUA_DIRECTIONS[bagua]})为山星当令位，宜见高大物或卧床")
        # 5 黄煞
        if ss == 5 or xs == 5:
            advice.append(f"{bagua}({BAGUA_DIRECTIONS[bagua]})有 5 黄煞，宜静不宜动；置铜器化解")
        # 2 黑病符
        if ss == 2 and xs == 2:
            advice.append(f"{bagua}({BAGUA_DIRECTIONS[bagua]})2 黑病符重叠，避免久居；可用六帝钱化解")
        # 三七叠临 / 二五交加（典型凶组合）
        if {ss, xs} == {2, 5}:
            advice.append(f"{bagua}({BAGUA_DIRECTIONS[bagua]})二五交加损主，宜挂铜葫芦或六帝钱")
        if {ss, xs} == {3, 7}:
            advice.append(f"{bagua}({BAGUA_DIRECTIONS[bagua]})三七叠临，主官非斗争；宜放红色物化解")
        if {ss, xs} == {1, 4}:
            advice.append(f"{bagua}({BAGUA_DIRECTIONS[bagua]})一四同宫，文昌位，利读书功名")
    # 去重保序
    return list(dict.fromkeys(advice))


# ── 主入口 ───────────────────────────────────────────────────
def compute_fengshui(facing_degree: float, birth: BirthInfo,
                      move_in_year: int = 2024) -> FengshuiChart:
    """计算风水盘（玄空下卦 + 八宅）。

    参数：
        facing_degree: 房屋朝向角度 (0-360°，正北=0)
        birth: 户主出生信息（用于八宅命卦）
        move_in_year: 入住公历年（决定运盘）
    """
    period = _period_of_year(move_in_year)

    # 朝向 + 坐山
    facing_shan = _shan_at_degree(facing_degree)
    sitting_shan = _opposite_shan(facing_shan)
    facing_bagua = SHAN_TO_BAGUA[facing_shan]
    sitting_bagua = SHAN_TO_BAGUA[sitting_shan]

    # 飞星 3 盘
    yun_pan = _calc_yun_pan(period)
    shan_pan, xiang_pan = _calc_shan_xiang_pan(period, sitting_shan, facing_shan)

    # 9 宫每位的合盘
    combined: list[dict] = []
    for r in range(3):
        for c in range(3):
            yun_n = yun_pan[r][c]
            shan_n = shan_pan[r][c]
            xiang_n = xiang_pan[r][c]
            # 对应卦位（按洛书默认数字）
            default_num = LUOSHU_DEFAULT[r][c]
            bagua = LUOSHU_NUM_TO_BAGUA[default_num]
            combined.append({
                "row": r, "col": c,
                "bagua": bagua, "direction": BAGUA_DIRECTIONS[bagua],
                "yun_star": yun_n,
                "shan_star": shan_n,
                "xiang_star": xiang_n,
                "shan_status": _star_status(shan_n, period),
                "xiang_status": _star_status(xiang_n, period),
            })

    # ── 八宅 ──
    ming_gua = _ming_gua(birth.year, birth.gender if birth.gender in ("male", "female") else "male")
    game = BA_ZHAI_GAME[ming_gua]
    favorable_dirs: list[str] = []
    unfavorable_dirs: list[str] = []
    ba_zhai_detail: dict[str, dict] = {}
    for bagua, label in game.items():
        ba_zhai_detail[bagua] = {
            "direction": BAGUA_DIRECTIONS[bagua],
            "label": label,
            "is_good": label in GOOD_LABELS,
        }
        text = f"{BAGUA_DIRECTIONS[bagua]}({label})"
        if label in GOOD_LABELS:
            favorable_dirs.append(text)
        else:
            unfavorable_dirs.append(text)

    east_west = "东四命" if ming_gua in EAST_GROUP else "西四命"

    # 化煞建议
    notes = _build_remedies(combined, period)

    # 朝向描述（含角度）
    facing_desc = f"{facing_degree:.1f}°/{facing_shan}({SHAN_TO_BAGUA[facing_shan]}/{BAGUA_DIRECTIONS[SHAN_TO_BAGUA[facing_shan]]})"
    sitting_desc = f"{sitting_shan}({sitting_bagua}/{BAGUA_DIRECTIONS[sitting_bagua]})"

    flying_stars: list[list[int]] = []
    # 输出格式：每行为 [运星, 山星, 向星]，按 9 宫顺序（北、东北、东、东南、南、西南、西、西北、中）
    order = ["坎", "艮", "震", "巽", "离", "坤", "兑", "乾", "中"]
    for bagua in order:
        if bagua == "中":
            r, c = 1, 1
        else:
            num = BAGUA_TO_LUOSHU_NUM[bagua]
            r, c = LUOSHU_NUM_POS[num]
        flying_stars.append([yun_pan[r][c], shan_pan[r][c], xiang_pan[r][c]])

    metadata: dict[str, Any] = {
        "period": period,
        "period_name": f"{period}运",
        "period_range": _period_range(period),
        "facing_shan": facing_shan,
        "sitting_shan": sitting_shan,
        "facing_bagua": facing_bagua,
        "sitting_bagua": sitting_bagua,
        "yun_pan": yun_pan,
        "shan_pan": shan_pan,
        "xiang_pan": xiang_pan,
        "nine_palace_detail": combined,
        "flying_stars_order": order,
        "ming_gua_group": east_west,
        "ba_zhai_detail": ba_zhai_detail,
        "move_in_year": move_in_year,
        "note": (
            "玄空下卦顺/逆飞按 24 山阴阳判定; 山盘种子=运盘坐山位数; "
            "向盘种子=运盘向首位数; 八宅命卦男减女加规则; "
            "替卦/兼向情况未实现; 远程化煞建议为常规通用规则"
        ),
    }

    return FengshuiChart(
        facing_direction=facing_desc,
        sitting_direction=sitting_desc,
        period=period,
        flying_stars=flying_stars,
        ba_zhai=ba_zhai_detail,
        ming_gua=ming_gua,
        favorable_directions=favorable_dirs,
        unfavorable_directions=unfavorable_dirs,
        notes=notes,
        metadata=metadata,
    )


def _period_range(period: int) -> str:
    """返回某运的年份范围，例如 9 → '2024-2043'。"""
    starts = {
        1: 2044, 2: 1864, 3: 1884, 4: 1904,
        5: 1924, 6: 1944, 7: 1964, 8: 1984, 9: 2004,
    }
    # 实际 1864-1883=1, 但 1运还有 2044-2063
    # 简化：只展示当前流行的范围（8运/9运）
    if period == 8:
        return "2004-2023"
    if period == 9:
        return "2024-2043"
    if period == 1:
        return "2044-2063"
    if period == 2:
        return "1864-1883"
    if period == 3:
        return "1884-1903"
    if period == 4:
        return "1904-1923"
    if period == 5:
        return "1924-1943"
    if period == 6:
        return "1944-1963"
    if period == 7:
        return "1964-1983"
    return "未知"


# ── CLI 测试 ────────────────────────────────────────────────
if __name__ == "__main__":
    import json

    demo_birth = BirthInfo(
        name="测试", gender="female",
        year=1991, month=8, day=15, hour=14, minute=30,
    )
    # 例：朝南偏西 (面朝丁山，约 200°)
    chart = compute_fengshui(facing_degree=200.0, birth=demo_birth, move_in_year=2024)
    print(json.dumps(chart.model_dump(), default=str, ensure_ascii=False, indent=2))
