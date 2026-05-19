"""塔罗牌 (Tarot) 计算引擎。

完全自研。78 张韦特塔罗（RWS）：
- 22 张大阿卡纳 (Major Arcana)
- 56 张小阿卡纳 (Minor Arcana) = 4 元素 × 14 张
  - 权杖 Wands（火）/圣杯 Cups（水）/宝剑 Swords（风）/星币 Pentacles（土）
  - Ace, 2-10, Page, Knight, Queen, King

牌阵：
- single：单牌
- three_card：过去 / 现在 / 未来
- celtic_cross：凯尔特十字 10 张
- relationship_seven：关系七牌阵
- year_twelve：年度 12 宫
- decision_cross：决策十字 5 张

抽牌动作必须来自用户输入；本模块只把用户给出的牌序/正逆位映射为牌阵结构。
"""
from __future__ import annotations

from typing import Literal

from core.schemas import TarotReading

# ════════════════════════════════════════════════════════════
# 大阿卡纳数据库 (22 张)
# ════════════════════════════════════════════════════════════
MAJOR_ARCANA: list[dict] = [
    {
        "id": "major_00_fool",
        "name": "愚人",
        "name_en": "The Fool",
        "arcana": "major",
        "suit": None,
        "number": 0,
        "element": "air",
        "keywords_upright": ["新开始", "纯真", "冒险", "自由", "信任"],
        "keywords_reversed": ["鲁莽", "天真过度", "停滞", "畏惧未知", "决策草率"],
        "meaning_upright": (
            "愚人代表纯粹的开始与无限可能。带着初学者之心面对世界，怀抱信任跨出第一步，"
            "即便前方是悬崖也愿一试。鼓励冒险、保持赤子之心、相信宇宙的引导。"
        ),
        "meaning_reversed": (
            "缺乏审慎的鲁莽与盲目乐观；或恰恰相反，过度恐惧而拒绝出发。需警惕"
            "天真带来的代价，也要警惕因害怕跌落而错过本应启程的旅程。"
        ),
        "image_hint": "悬崖边的青年背着小包、手持白玫瑰，白狗在脚边吠叫，太阳高挂。",
    },
    {
        "id": "major_01_magician",
        "name": "魔术师",
        "name_en": "The Magician",
        "arcana": "major", "suit": None, "number": 1, "element": "air",
        "keywords_upright": ["显化", "意志力", "技艺", "资源整合", "行动"],
        "keywords_reversed": ["操纵", "未充分发挥潜能", "欺骗", "技巧未到位"],
        "meaning_upright": (
            "你拥有把意念化为现实所需的全部工具——风火水土四元素具足。当下"
            "是行动与显化的时刻：聚焦你的意志，把灵感转译为可执行的步骤。"
        ),
        "meaning_reversed": (
            "潜力被荒废，或技艺被用于操纵他人。注意是否在自欺欺人、"
            "或拖延着一件本应立刻执行的事。"
        ),
        "image_hint": "魔术师举手指天，桌上摆放权杖、圣杯、宝剑、星币四元素。",
    },
    {
        "id": "major_02_high_priestess",
        "name": "女祭司",
        "name_en": "The High Priestess",
        "arcana": "major", "suit": None, "number": 2, "element": "water",
        "keywords_upright": ["直觉", "潜意识", "神秘", "内在智慧", "等待"],
        "keywords_reversed": ["秘密被揭", "压抑直觉", "肤浅", "信息阻塞"],
        "meaning_upright": (
            "倾听潜意识的低语。答案在你的内在而非外界喧嚣中。这不是行动的"
            "时刻，而是凝视、感受、等待的时刻。神秘正在揭幕。"
        ),
        "meaning_reversed": (
            "你忽略了自己的直觉，或被表层信息蒙蔽。秘密可能即将曝光，"
            "或者你正逃避必须独自面对的内在真相。"
        ),
        "image_hint": "披月长袍的女祭司端坐于黑白两柱之间，手持卷轴，月在足下。",
    },
    {
        "id": "major_03_empress",
        "name": "皇后",
        "name_en": "The Empress",
        "arcana": "major", "suit": None, "number": 3, "element": "earth",
        "keywords_upright": ["丰饶", "母性", "感官", "自然", "创造力"],
        "keywords_reversed": ["创造力受阻", "依赖过度", "占有欲", "失衡"],
        "meaning_upright": (
            "丰盛与孕育的能量正在流动。无论是孩子、艺术、项目还是关系，"
            "都在生长与盛放之中。允许自己享受感官与美。"
        ),
        "meaning_reversed": (
            "你可能压抑了女性能量，或在关系中陷入控制与共生的不健康模式；"
            "也可能创造力暂时停滞、需要回归自然以重充能量。"
        ),
        "image_hint": "孕妇皇后斜倚于丰收麦田，头戴十二星之冠，金星标志在身侧。",
    },
    {
        "id": "major_04_emperor",
        "name": "皇帝",
        "name_en": "The Emperor",
        "arcana": "major", "suit": None, "number": 4, "element": "fire",
        "keywords_upright": ["权威", "结构", "秩序", "父性", "稳定"],
        "keywords_reversed": ["专横", "僵化", "权力滥用", "缺乏纪律"],
        "meaning_upright": (
            "建立秩序与边界，承担起领导与责任。理性、纪律、长期视角是当下"
            "的关键词。这是用结构化方式落地野心的好时机。"
        ),
        "meaning_reversed": (
            "权力与控制的失衡——可能是你过度专横，也可能是被权威压制。"
            "考虑是否需要松动僵硬的规则、或为自己重新建立边界。"
        ),
        "image_hint": "披甲皇帝端坐石椅，背景为荒山，手持权杖，头戴金冠。",
    },
    {
        "id": "major_05_hierophant",
        "name": "教皇",
        "name_en": "The Hierophant",
        "arcana": "major", "suit": None, "number": 5, "element": "earth",
        "keywords_upright": ["传统", "灵性教导", "婚姻", "团体", "信仰体系"],
        "keywords_reversed": ["反叛", "教条", "非传统", "信念崩塌"],
        "meaning_upright": (
            "在既有体系、传统智慧或灵性导师中寻找答案。或许你正进入婚姻、"
            "宗教、组织。遵循已被验证的路径会带来稳定。"
        ),
        "meaning_reversed": (
            "对传统与权威的反叛，或既有信仰体系正在崩塌。这未必是坏事——"
            "你可能正走向属于自己的非主流之路。"
        ),
        "image_hint": "教皇高坐宝座举手赐福，两位修士跪地，背景为双柱教堂。",
    },
    {
        "id": "major_06_lovers",
        "name": "恋人",
        "name_en": "The Lovers",
        "arcana": "major", "suit": None, "number": 6, "element": "air",
        "keywords_upright": ["爱情", "伴侣", "选择", "结合", "价值观契合"],
        "keywords_reversed": ["关系破裂", "价值冲突", "错误选择", "诱惑"],
        "meaning_upright": (
            "灵魂层面的连接与重要选择。这张牌不仅指爱情，更指出你正面临"
            "一个关于价值观、关于'与谁同行'的关键抉择。"
        ),
        "meaning_reversed": (
            "关系中的不和谐，或你做出了违背真心的选择。可能正面临"
            "诱惑或道德两难——回到内在价值观就能找到方向。"
        ),
        "image_hint": "亚当与夏娃赤裸立于伊甸园，天使在云中赐福，背景双树。",
    },
    {
        "id": "major_07_chariot",
        "name": "战车",
        "name_en": "The Chariot",
        "arcana": "major", "suit": None, "number": 7, "element": "water",
        "keywords_upright": ["胜利", "决心", "意志", "前进", "克服阻碍"],
        "keywords_reversed": ["失控", "侵略性", "方向迷失", "对立未整合"],
        "meaning_upright": (
            "凭借意志力与决心赢得胜利。冲突已被掌控、方向已被锁定。"
            "继续前进，但要双手紧握缰绳——黑白二马代表内在的对立力量。"
        ),
        "meaning_reversed": (
            "失控、侵略或方向迷失。你可能在多线作战却没整合内在矛盾，"
            "导致动力反向消耗。停车、整队，再出发。"
        ),
        "image_hint": "披甲战士驾驭战车，黑白双狮（或斯芬克斯）拉车前行。",
    },
    {
        "id": "major_08_strength",
        "name": "力量",
        "name_en": "Strength",
        "arcana": "major", "suit": None, "number": 8, "element": "fire",
        "keywords_upright": ["内在力量", "勇气", "温柔", "驯服本能", "耐心"],
        "keywords_reversed": ["自我怀疑", "脆弱", "失去耐心", "本能失控"],
        "meaning_upright": (
            "真正的力量是温柔的。以爱与耐心驯服内在的'狮子'——本能、欲望、"
            "愤怒。柔克刚，比硬碰硬更长久。"
        ),
        "meaning_reversed": (
            "自我怀疑或本能失控。你可能压抑了内在野性、或反过来被它支配。"
            "答案永远不是'打败'它，而是与它和解。"
        ),
        "image_hint": "白衣女子温柔地合上狮子之口，头顶有无限符号。",
    },
    {
        "id": "major_09_hermit",
        "name": "隐者",
        "name_en": "The Hermit",
        "arcana": "major", "suit": None, "number": 9, "element": "earth",
        "keywords_upright": ["独处", "内省", "智慧", "寻师", "灵性追求"],
        "keywords_reversed": ["孤立", "退缩过度", "拒绝建议", "沉溺孤独"],
        "meaning_upright": (
            "退到山顶独处。停下外在喧哗，举起内在之灯照亮自己的路。"
            "也可能预示遇到一位智慧导师——或者你成为他人的导师。"
        ),
        "meaning_reversed": (
            "过度孤立、与现实脱节，或拒绝伸出的援手。独处是必要的，"
            "但不能用来逃避所有关系。"
        ),
        "image_hint": "白须隐者立于雪山顶，举起六芒星灯笼，手持长杖。",
    },
    {
        "id": "major_10_wheel_of_fortune",
        "name": "命运之轮",
        "name_en": "Wheel of Fortune",
        "arcana": "major", "suit": None, "number": 10, "element": "fire",
        "keywords_upright": ["转折", "命运", "周期", "好运", "不可控"],
        "keywords_reversed": ["逆境", "命运循环卡住", "厄运", "抗拒变化"],
        "meaning_upright": (
            "命运之轮在转动，一个周期结束、另一个开始。即将迎来转机或重大"
            "变化。提醒：享受幸运时刻，但要记得轮子终会再转。"
        ),
        "meaning_reversed": (
            "暂时的厄运或停滞，或同一种模式不断重演。检视你是否在"
            "无意中维系着轮子的当前位置——主动转动它需要意识与勇气。"
        ),
        "image_hint": "巨大转轮悬于云中，四角有四生灵（人/狮/牛/鹰）持书研读。",
    },
    {
        "id": "major_11_justice",
        "name": "正义",
        "name_en": "Justice",
        "arcana": "major", "suit": None, "number": 11, "element": "air",
        "keywords_upright": ["公正", "因果", "真相", "法律", "平衡"],
        "keywords_reversed": ["不公", "逃避责任", "偏见", "腐败"],
        "meaning_upright": (
            "因果将公平兑现。无论结果是否如你所愿，宇宙都按你过去的选择"
            "回应你。诚实面对自己的责任。也可能涉及法律与契约。"
        ),
        "meaning_reversed": (
            "感受到不公或偏见。也可能你在逃避自己应承担的责任，"
            "或面临自欺欺人的判断。"
        ),
        "image_hint": "正义女神端坐宝座，右手举剑、左手持秤，红袍。",
    },
    {
        "id": "major_12_hanged_man",
        "name": "倒吊人",
        "name_en": "The Hanged Man",
        "arcana": "major", "suit": None, "number": 12, "element": "water",
        "keywords_upright": ["视角转换", "牺牲", "暂停", "顺服", "悟道"],
        "keywords_reversed": ["无谓的牺牲", "卡住", "拒绝放手", "停滞"],
        "meaning_upright": (
            "把世界倒过来看。当下不是行动而是悬置——主动放弃控制，让新的"
            "视角浮现。短期的牺牲会换来更深的洞见。"
        ),
        "meaning_reversed": (
            "你做了不该做的牺牲，或拒绝放下早该放下的事。停滞过久"
            "会变成自我惩罚。该解开绳索了。"
        ),
        "image_hint": "青年倒挂于 T 形十字木架上，头部光环，神情平和。",
    },
    {
        "id": "major_13_death",
        "name": "死神",
        "name_en": "Death",
        "arcana": "major", "suit": None, "number": 13, "element": "water",
        "keywords_upright": ["结束", "转化", "蜕变", "释放", "重生"],
        "keywords_reversed": ["抗拒结束", "停滞", "无法放手", "缓慢转变"],
        "meaning_upright": (
            "一个章节正在彻底落幕——这是必要的死亡，为新生命腾出空间。"
            "并非肉体之死，而是身份、关系、信念层面的根本转化。"
        ),
        "meaning_reversed": (
            "你抗拒一个早该结束的局面，蜕变被拖延。结束不是失败，"
            "拖着不放才是。给自己一场体面的告别。"
        ),
        "image_hint": "白马上的死神骑士手持黑旗白玫瑰，太阳从两塔之间升起。",
    },
    {
        "id": "major_14_temperance",
        "name": "节制",
        "name_en": "Temperance",
        "arcana": "major", "suit": None, "number": 14, "element": "fire",
        "keywords_upright": ["平衡", "调和", "耐心", "中道", "炼金"],
        "keywords_reversed": ["失衡", "极端", "冲突", "缺乏耐心"],
        "meaning_upright": (
            "把对立的两端融合成更高的第三种状态。耐心、试错、调整"
            "比例——你正在进行一场内在或外在的炼金。"
        ),
        "meaning_reversed": (
            "陷入极端或剧烈摆动——不是这边就是那边。提醒自己：中道不是"
            "妥协，而是把两端的精华都吸收。"
        ),
        "image_hint": "天使一脚水中一脚岸上，把水从一只杯子倒入另一只。",
    },
    {
        "id": "major_15_devil",
        "name": "恶魔",
        "name_en": "The Devil",
        "arcana": "major", "suit": None, "number": 15, "element": "earth",
        "keywords_upright": ["束缚", "成瘾", "物欲", "执念", "阴影"],
        "keywords_reversed": ["挣脱束缚", "觉察阴影", "戒除", "重获自由"],
        "meaning_upright": (
            "你被某种东西捆住了——可能是关系、瘾、金钱、权力欲。注意：脖子"
            "上的链条是松的，囚徒是自愿的。看清就是解开的第一步。"
        ),
        "meaning_reversed": (
            "你正在挣脱旧束缚——戒瘾、离开有毒关系、释放执念。这条路"
            "很难，但你已经在路上。"
        ),
        "image_hint": "羊角恶魔立于祭坛，男女赤裸缚于其下，链条松垂可解。",
    },
    {
        "id": "major_16_tower",
        "name": "塔",
        "name_en": "The Tower",
        "arcana": "major", "suit": None, "number": 16, "element": "fire",
        "keywords_upright": ["剧变", "崩塌", "顿悟", "解构", "突发事件"],
        "keywords_reversed": ["延迟的崩塌", "勉强维持", "渐进解构", "避免灾难"],
        "meaning_upright": (
            "建立在虚假根基上的事物轰然倒塌。痛苦但必要——闪电劈开了你"
            "原本不敢面对的真相。废墟之上才能重建。"
        ),
        "meaning_reversed": (
            "你勉强维持着即将倒塌的塔，或刚刚惊险避过一次崩塌。也可能"
            "崩塌在缓慢发生，给你时间准备。"
        ),
        "image_hint": "高塔被闪电击中，王冠飞落，两人从塔上坠下，火焰四射。",
    },
    {
        "id": "major_17_star",
        "name": "星星",
        "name_en": "The Star",
        "arcana": "major", "suit": None, "number": 17, "element": "air",
        "keywords_upright": ["希望", "灵感", "疗愈", "宁静", "信仰"],
        "keywords_reversed": ["失望", "信念动摇", "断开灵感源", "悲观"],
        "meaning_upright": (
            "暴风雨后的宁静与希望。你正被疗愈、被指引。允许自己相信、"
            "允许自己脆弱。星辰为你而亮。"
        ),
        "meaning_reversed": (
            "对未来失去信心，与灵感源失联。可能正经历信念低谷——"
            "这是过程，不是终点。"
        ),
        "image_hint": "裸女单膝跪溪边，左右手各持一壶水，浇地浇水，七星在天。",
    },
    {
        "id": "major_18_moon",
        "name": "月亮",
        "name_en": "The Moon",
        "arcana": "major", "suit": None, "number": 18, "element": "water",
        "keywords_upright": ["幻觉", "潜意识", "恐惧", "梦境", "未知"],
        "keywords_reversed": ["走出幻觉", "真相揭示", "克服恐惧", "情绪回归"],
        "meaning_upright": (
            "你正在迷雾中行走。不是所有看起来真的就是真——潜意识恐惧、"
            "梦境、未澄清的情绪都在影响你的判断。等月落再下结论。"
        ),
        "meaning_reversed": (
            "迷雾消散，真相浮现。你看穿了之前的幻觉，从恐惧中走出来。"
            "或者，需要正视那些一直在逃避的潜意识内容。"
        ),
        "image_hint": "月亮俯瞰大地，狼与狗对月嗥叫，小龙虾从水中爬出。",
    },
    {
        "id": "major_19_sun",
        "name": "太阳",
        "name_en": "The Sun",
        "arcana": "major", "suit": None, "number": 19, "element": "fire",
        "keywords_upright": ["喜悦", "成功", "活力", "纯真", "清明"],
        "keywords_reversed": ["短暂阴霾", "缺乏自信", "成功延迟", "过度乐观"],
        "meaning_upright": (
            "光明、喜悦、清晰。一切照亮，一切丰盛。这是少有的'尽情享受'"
            "的时刻——成功、生命力、纯粹的快乐。"
        ),
        "meaning_reversed": (
            "暂时被云遮挡的太阳。你的光仍在，只是当下被自我怀疑或外在"
            "阻碍蒙尘。或者乐观过头忽视了风险。"
        ),
        "image_hint": "明朗太阳下，赤裸孩童骑白马挥红旗，背景向日葵盛放。",
    },
    {
        "id": "major_20_judgement",
        "name": "审判",
        "name_en": "Judgement",
        "arcana": "major", "suit": None, "number": 20, "element": "fire",
        "keywords_upright": ["觉醒", "召唤", "重生", "宽恕", "总结"],
        "keywords_reversed": ["拒绝召唤", "自我批评", "未化解的过去", "停留"],
        "meaning_upright": (
            "听到内心的召唤——是该升起、整合、重新出发的时候。回顾来路、"
            "宽恕自己与他人，进入下一个层次的人生。"
        ),
        "meaning_reversed": (
            "你听到了召唤却假装没听到，或被过去的内疚困住。该原谅自己了——"
            "审判不是惩罚，是邀请你升华。"
        ),
        "image_hint": "天使吹响号角，墓中人男女老少举手回应，迎向光。",
    },
    {
        "id": "major_21_world",
        "name": "世界",
        "name_en": "The World",
        "arcana": "major", "suit": None, "number": 21, "element": "earth",
        "keywords_upright": ["完成", "圆满", "整合", "成就", "新循环"],
        "keywords_reversed": ["未竟之业", "拖延完成", "缺少最后一步", "停留旧阶段"],
        "meaning_upright": (
            "一个完整的循环抵达终点。所有努力开花结果，你已成为更完整"
            "的自己。庆祝这份圆满，也准备开启下一段旅程。"
        ),
        "meaning_reversed": (
            "差最后一步就完成，却被拖住了。也可能你已完成却拒绝承认、"
            "迟迟不肯进入下一个阶段。"
        ),
        "image_hint": "舞者赤身披紫纱立于花环之中，四角四生灵环绕。",
    },
]


# ════════════════════════════════════════════════════════════
# 小阿卡纳数据库 (4 元素 × 14 张 = 56 张)
# ════════════════════════════════════════════════════════════
SUIT_INFO = {
    "wands": {
        "name": "权杖", "name_en": "Wands", "element": "fire",
        "theme": "热情、行动、灵感、事业、创造、勇气",
    },
    "cups": {
        "name": "圣杯", "name_en": "Cups", "element": "water",
        "theme": "情感、关系、直觉、爱、内在体验",
    },
    "swords": {
        "name": "宝剑", "name_en": "Swords", "element": "air",
        "theme": "思想、沟通、冲突、决策、真相",
    },
    "pentacles": {
        "name": "星币", "name_en": "Pentacles", "element": "earth",
        "theme": "物质、金钱、工作、健康、实际",
    },
}

# 小阿卡纳数字 + 宫廷牌的「主题」描述（按数字归类，4 元素共享主题骨架）
NUMBER_THEMES_UPRIGHT: dict[str | int, dict[str, str]] = {
    1: {  # Ace
        "wands": "新事业的火花，灵感与冲动；点燃野心的瞬间。",
        "cups": "新感情、新连接的开端；情感纯粹涌出。",
        "swords": "清晰的洞见，新想法或决心；真相的利剑。",
        "pentacles": "新机会、新资源、新工作；一颗稳健的种子。",
    },
    2: {
        "wands": "规划与权衡，握着世界的两端；是稳守还是远征？",
        "cups": "心与心的连接，伴侣关系与共鸣。",
        "swords": "僵局与抉择，蒙眼之间难以决断。",
        "pentacles": "在多重责任间走钢丝，保持流动平衡。",
    },
    3: {
        "wands": "扩张视野，事业初见成效，等待远船归来。",
        "cups": "庆祝、友谊、社群欢聚，情谊满杯。",
        "swords": "心痛、分离、失落；穿心剑下的清晰与悲伤。",
        "pentacles": "团队协作，技艺被认可，匠人的初步成就。",
    },
    4: {
        "wands": "稳定的庆典与归属——家、毕业、完成阶段。",
        "cups": "情感的倦怠与冷漠，对现有的感到不满。",
        "swords": "休整与冥思，从冲突中暂时撤退恢复。",
        "pentacles": "守财与抓紧，过度依恋安全感。",
    },
    5: {
        "wands": "竞争与冲突，混乱中各自为战。",
        "cups": "悲伤与遗憾，看不到杯中尚存的部分。",
        "swords": "胜利的代价，不光彩的得手或被孤立。",
        "pentacles": "物质或精神匮乏，被排除在温暖之外。",
    },
    6: {
        "wands": "凯旋与公开认可，骑马归来的胜利者。",
        "cups": "怀旧、童年、单纯的相遇与温情。",
        "swords": "渡过艰难，向更平静水域航行。",
        "pentacles": "慷慨、给予与接收，资源的健康流动。",
    },
    7: {
        "wands": "守住高地，捍卫立场，逆风也站稳。",
        "cups": "幻象与抉择，太多选择反而迷失。",
        "swords": "策略性逃避或机谋，需诚实面对自己。",
        "pentacles": "评估投入与收获，耐心等待果实成熟。",
    },
    8: {
        "wands": "迅猛的进展，箭离弦——讯息、行动、节奏加速。",
        "cups": "离开看似圆满的现状，去寻找更深的意义。",
        "swords": "自我设限的枷锁，眼前并无真正的牢笼。",
        "pentacles": "勤勉精进，匠人专注磨练手艺。",
    },
    9: {
        "wands": "战伤累累但仍站立，最后一关的坚持。",
        "cups": "愿望成真，物质与情感双重满足。",
        "swords": "深夜焦虑，被想象中的剑刺中而非现实。",
        "pentacles": "独立与丰盛，自给自足的优雅。",
    },
    10: {
        "wands": "重担压身，承担过多，需学会放下或委派。",
        "cups": "家庭圆满与情感大丰收，彩虹高悬。",
        "swords": "终结性的重击，痛苦的彻底完结，黎明就在前方。",
        "pentacles": "家族传承、长期富足、跨代的稳固。",
    },
    "page": {
        "wands": "充满热情的信使或学徒，跃跃欲试的灵感少年。",
        "cups": "敏感而富艺术气息的年轻人，带来情感讯息。",
        "swords": "好奇而锋利的探究者，带来新思想或挑战。",
        "pentacles": "踏实的学习者，正在打基础的实务新兵。",
    },
    "knight": {
        "wands": "热血冲锋的骑士，直率而急躁。",
        "cups": "浪漫的追求者，怀着理想前行。",
        "swords": "雷厉风行的冲锋者，言行如刀。",
        "pentacles": "稳健踏实的行者，慢但极可靠。",
    },
    "queen": {
        "wands": "自信温暖的领袖女性，热情而有边界。",
        "cups": "深情共感的疗愈者，情感丰沛而成熟。",
        "swords": "理性独立的女王，看穿一切的清醒。",
        "pentacles": "丰盛慷慨的母亲，把家与事业都打理得井井有条。",
    },
    "king": {
        "wands": "远见的领袖与开拓者，以热情驾驭权力。",
        "cups": "情感成熟的智者，平衡心与脑。",
        "swords": "公正而冷峻的决策者，以真理立法。",
        "pentacles": "成功而慷慨的实业家，掌控物质王国。",
    },
}

# 牌面图像简短提示（按花色 + 数字组合，可省略）
IMAGE_HINTS: dict[tuple[str, str | int], str] = {
    ("wands", 1): "云中之手握着新生权杖，绿芽萌发。",
    ("cups", 1): "云中之手托圣杯，鸽子衔圣饼降下。",
    ("swords", 1): "云中之手握剑刺穿王冠，剑尖光芒。",
    ("pentacles", 1): "云中之手托金币，下方玫瑰花园。",
    ("wands", 10): "弯腰背着十根权杖的人艰难前行。",
    ("cups", 10): "夫妇与孩童在彩虹下欢庆，远处家园。",
    ("swords", 10): "尸体伏地背插十剑，黎明前的黑暗。",
    ("pentacles", 10): "祖孙三代与狗在丰盛家园，金币组成生命树。",
}

COURT_RANKS = ["page", "knight", "queen", "king"]
COURT_NAMES_CN = {"page": "侍从", "knight": "骑士", "queen": "皇后", "king": "国王"}


def _build_minor_card(suit: str, rank: str | int) -> dict:
    """构造一张小阿卡纳数据。rank 为 1-10 整数或 page/knight/queen/king 字符串。"""
    info = SUIT_INFO[suit]
    if isinstance(rank, int):
        if rank == 1:
            display_num = "Ace"
            cn_num = "Ace"
        else:
            display_num = str(rank)
            cn_num = str(rank)
        rank_key = rank
        rank_label_en = display_num
        # 正逆位关键词（基于花色 + 数字）
        upright_themes = {
            1: ["新开始", "纯粹潜能", "机遇"],
            2: ["平衡", "选择", "二元"],
            3: ["发展", "团队", "成长"],
            4: ["稳定", "结构", "停顿"],
            5: ["挑战", "失衡", "冲突"],
            6: ["和谐", "成就", "给予"],
            7: ["评估", "策略", "幻象"],
            8: ["行动", "进步", "积累"],
            9: ["接近圆满", "独立", "韧性"],
            10: ["完成", "极致", "新循环开始"],
        }[rank]
        reversed_themes = [w + "（受阻）" for w in upright_themes]
    else:
        rank_key = rank
        rank_label_en = rank.capitalize()
        cn_num = COURT_NAMES_CN[rank]
        display_num = rank_label_en
        upright_themes = {
            "page": ["学习", "讯息", "新阶段"],
            "knight": ["行动", "追求", "热情"],
            "queen": ["成熟", "滋养", "内在掌握"],
            "king": ["权威", "掌控", "精通"],
        }[rank]
        reversed_themes = [w + "（失衡）" for w in upright_themes]

    upright_text = NUMBER_THEMES_UPRIGHT[rank_key][suit]
    reversed_text = (
        f"{upright_text[:-1] if upright_text.endswith('。') else upright_text}"
        f" 当其逆位时，呈现为：被压抑、错位或夸大的同一主题——"
        f"{info['theme']}领域出现停滞或扭曲。"
    )

    card_id = (
        f"{suit}_{rank:02d}" if isinstance(rank, int)
        else f"{suit}_{rank}"
    )
    cn_name = f"{info['name']}{cn_num}"
    image_hint = IMAGE_HINTS.get(
        (suit, rank),
        f"{info['name']}画面：{rank_label_en}，主题为{info['theme']}。",
    )

    return {
        "id": card_id,
        "name": cn_name,
        "name_en": f"{rank_label_en} of {info['name_en']}",
        "arcana": "minor",
        "suit": suit,
        "number": rank_key,
        "element": info["element"],
        "keywords_upright": upright_themes + [info["element"]],
        "keywords_reversed": reversed_themes,
        "meaning_upright": upright_text,
        "meaning_reversed": reversed_text,
        "image_hint": image_hint,
    }


def _build_minor_arcana() -> list[dict]:
    """生成全部 56 张小阿卡纳。"""
    cards = []
    for suit in ["wands", "cups", "swords", "pentacles"]:
        for rank in list(range(1, 11)) + COURT_RANKS:
            cards.append(_build_minor_card(suit, rank))
    return cards


MINOR_ARCANA: list[dict] = _build_minor_arcana()
TAROT_DECK: list[dict] = MAJOR_ARCANA + MINOR_ARCANA


# ════════════════════════════════════════════════════════════
# 牌阵定义
# ════════════════════════════════════════════════════════════
SPREADS: dict[str, dict] = {
    "single": {
        "name_cn": "单牌",
        "name_en": "Single Card",
        "description": "针对一个具体问题快速取得指引。",
        "positions": [
            {"position_id": 1, "position_name": "答案", "position_meaning": "对问题的核心指引。"},
        ],
    },
    "three_card": {
        "name_cn": "三张牌（过去-现在-未来）",
        "name_en": "Three Card",
        "description": "经典时间轴牌阵：过去 → 现在 → 未来。",
        "positions": [
            {"position_id": 1, "position_name": "过去", "position_meaning": "对当前局面起作用的过去因素。"},
            {"position_id": 2, "position_name": "现在", "position_meaning": "当下你所处的核心状态。"},
            {"position_id": 3, "position_name": "未来", "position_meaning": "如果维持当前轨迹会去向何处。"},
        ],
    },
    "celtic_cross": {
        "name_cn": "凯尔特十字",
        "name_en": "Celtic Cross",
        "description": "10 张全方位透视：内在 / 外在 / 过去 / 未来 / 期望 / 结果。",
        "positions": [
            {"position_id": 1, "position_name": "现状",
             "position_meaning": "你目前处于什么样的核心情境。"},
            {"position_id": 2, "position_name": "挑战 / 障碍",
             "position_meaning": "横亘在前的核心障碍或助力（横放在第一张上）。"},
            {"position_id": 3, "position_name": "潜意识根源 / 基础",
             "position_meaning": "事件深层的根、潜意识因素、基础环境。"},
            {"position_id": 4, "position_name": "近期过去",
             "position_meaning": "刚刚过去、正在退出舞台的影响。"},
            {"position_id": 5, "position_name": "可能的目标 / 显意识期望",
             "position_meaning": "你意识层面的目标或所追求的结果。"},
            {"position_id": 6, "position_name": "近期未来",
             "position_meaning": "即将进入舞台、影响接下来几周的因素。"},
            {"position_id": 7, "position_name": "你自己（自我形象 / 立场）",
             "position_meaning": "你目前的态度、自我认知与立场。"},
            {"position_id": 8, "position_name": "外在影响 / 他人态度",
             "position_meaning": "他人或环境对此事件的态度与影响。"},
            {"position_id": 9, "position_name": "希望与恐惧",
             "position_meaning": "你内心潜在的渴望或畏惧。"},
            {"position_id": 10, "position_name": "最终结果",
             "position_meaning": "如果当前轨迹延续将抵达的结局。"},
        ],
    },
    "relationship_seven": {
        "name_cn": "关系七牌阵",
        "name_en": "Relationship Seven",
        "description": "7 张牌深度透视一段关系。",
        "positions": [
            {"position_id": 1, "position_name": "你的状态",
             "position_meaning": "你在这段关系中的当下状态与核心心境。"},
            {"position_id": 2, "position_name": "对方的状态",
             "position_meaning": "对方在这段关系中的当下状态。"},
            {"position_id": 3, "position_name": "关系的基础",
             "position_meaning": "把你们连在一起的根本元素。"},
            {"position_id": 4, "position_name": "挑战 / 阻碍",
             "position_meaning": "关系中正在出现的核心冲突或考验。"},
            {"position_id": 5, "position_name": "你需要学习的功课",
             "position_meaning": "通过此关系你被邀请去成长的方向。"},
            {"position_id": 6, "position_name": "对方需要学习的功课",
             "position_meaning": "对方在此关系中需要面对的功课。"},
            {"position_id": 7, "position_name": "可能的走向",
             "position_meaning": "如果当前模式延续，关系将去向何处。"},
        ],
    },
    "year_twelve": {
        "name_cn": "年度十二宫",
        "name_en": "Year Twelve",
        "description": "12 张牌对应未来 12 个月，逐月透视。",
        "positions": [
            {"position_id": i + 1, "position_name": f"第 {i + 1} 个月",
             "position_meaning": f"未来第 {i + 1} 个月的能量主题与提示。"}
            for i in range(12)
        ],
    },
    "decision_cross": {
        "name_cn": "决策十字",
        "name_en": "Decision Cross",
        "description": "5 张牌帮助在两条道路之间作出选择。",
        "positions": [
            {"position_id": 1, "position_name": "当前情境",
             "position_meaning": "你正面临的核心情境。"},
            {"position_id": 2, "position_name": "选择 A 的走向",
             "position_meaning": "选 A 路径将带来的能量与结果。"},
            {"position_id": 3, "position_name": "选择 B 的走向",
             "position_meaning": "选 B 路径将带来的能量与结果。"},
            {"position_id": 4, "position_name": "需要考虑的因素",
             "position_meaning": "做选择前你必须先看清的隐藏因素。"},
            {"position_id": 5, "position_name": "建议",
             "position_meaning": "塔罗给予你的核心建议。"},
        ],
    },
}


# ════════════════════════════════════════════════════════════
# 抽牌结果映射
# ════════════════════════════════════════════════════════════
def draw_tarot(
    question: str = "",
    spread: str = "celtic_cross",
    deck: str = "rws",
    card_indexes: list[int] | None = None,
    reversed_flags: list[bool] | None = None,
    allow_reversed: bool = True,
) -> TarotReading:
    """把用户抽出的牌映射到指定牌阵。

    Args:
        question: 占卜的问题
        spread: 牌阵 ID（single / three_card / celtic_cross / relationship_seven /
                year_twelve / decision_cross）
        deck: 牌组（默认 'rws' = Rider-Waite-Smith）
        card_indexes: 用户抽出的牌在 TAROT_DECK 中的 0-based 索引
        reversed_flags: 每张牌是否逆位；不传则全部正位
        allow_reversed: 是否读取逆位标记

    Returns:
        TarotReading
    """
    if spread not in SPREADS:
        raise ValueError(
            f"未知牌阵 '{spread}'，可选：{list(SPREADS.keys())}"
        )

    spread_def = SPREADS[spread]
    positions = spread_def["positions"]
    n_cards = len(positions)

    if n_cards > len(TAROT_DECK):
        raise ValueError(
            f"牌阵 {spread} 需要 {n_cards} 张，但牌组只有 {len(TAROT_DECK)} 张。"
        )
    if card_indexes is None:
        raise ValueError("塔罗需要用户抽牌结果 card_indexes；不能由系统代替用户随机抽牌。")
    if len(card_indexes) != n_cards:
        raise ValueError(f"牌阵 {spread} 需要 {n_cards} 张牌，实际收到 {len(card_indexes)} 张。")
    if len(set(card_indexes)) != len(card_indexes):
        raise ValueError("塔罗抽牌结果有重复牌。")
    invalid = [i for i in card_indexes if not isinstance(i, int) or i < 0 or i >= len(TAROT_DECK)]
    if invalid:
        raise ValueError(f"塔罗牌索引超出范围：{invalid}")
    if reversed_flags is None:
        reversed_flags = [False] * n_cards
    if len(reversed_flags) != n_cards:
        raise ValueError(f"逆位标记数量应为 {n_cards}，实际收到 {len(reversed_flags)}。")

    drawn_cards: list[dict] = []
    for i, card_idx in enumerate(card_indexes):
        card = TAROT_DECK[card_idx]
        is_reversed = bool(reversed_flags[i]) if allow_reversed else False
        position = positions[i]

        drawn_cards.append({
            "position_id": position["position_id"],
            "position_name": position["position_name"],
            "position_meaning": position["position_meaning"],
            "card_id": card["id"],
            "card_name": card["name"],
            "card_name_en": card.get("name_en"),
            "arcana": card["arcana"],
            "suit": card["suit"],
            "number": card["number"],
            "element": card["element"],
            "orientation": "reversed" if is_reversed else "upright",
            "keywords": (
                card["keywords_reversed"] if is_reversed else card["keywords_upright"]
            ),
            "meaning": (
                card["meaning_reversed"] if is_reversed else card["meaning_upright"]
            ),
            "image_hint": card.get("image_hint", ""),
        })

    metadata = {
        "spread_name_cn": spread_def["name_cn"],
        "spread_name_en": spread_def["name_en"],
        "spread_description": spread_def["description"],
        "n_cards": n_cards,
        "deck_size": len(TAROT_DECK),
        "allow_reversed": allow_reversed,
        "card_indexes": card_indexes,
        "draw_source": "user_supplied",
    }

    return TarotReading(
        spread=spread,
        deck=deck,
        question=question,
        drawn_cards=drawn_cards,
        metadata=metadata,
    )


def find_card_by_id(card_id: str) -> dict | None:
    """按 id 查询单张牌（如 'major_00_fool' 或 'wands_07'）。"""
    for c in TAROT_DECK:
        if c["id"] == card_id:
            return c
    return None


# ════════════════════════════════════════════════════════════
# 演示
# ════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import json

    print(f"塔罗牌总数：{len(TAROT_DECK)}")
    print(f"  大阿卡纳：{len(MAJOR_ARCANA)}")
    print(f"  小阿卡纳：{len(MINOR_ARCANA)}")
    print()

    # 单牌
    r1 = draw_tarot(question="今天我应该关注什么？", spread="single", card_indexes=[0])
    print("── 单牌（用户抽牌示例）──")
    for c in r1.drawn_cards:
        print(f"  [{c['position_name']}] {c['card_name']} ({c['orientation']})")
    print()

    # 三张牌
    r2 = draw_tarot(
        question="我目前的事业方向？",
        spread="three_card",
        card_indexes=[1, 12, 35],
        reversed_flags=[False, True, False],
    )
    print("── 三张牌（用户抽牌示例）──")
    for c in r2.drawn_cards:
        print(f"  [{c['position_name']}] {c['card_name']} ({c['orientation']})")
    print()

    # 凯尔特十字
    r3 = draw_tarot(
        question="未来三个月感情走向如何？",
        spread="celtic_cross",
        card_indexes=list(range(10)),
    )
    print("── 凯尔特十字（用户抽牌示例）──")
    for c in r3.drawn_cards:
        print(f"  [{c['position_id']:2d}. {c['position_name']}] "
              f"{c['card_name']} ({c['orientation']}) - {c['keywords'][:2]}")
    print()

    # 关系七牌阵
    r4 = draw_tarot(
        question="我和 X 的关系发展？",
        spread="relationship_seven",
        card_indexes=list(range(7)),
    )
    print("── 关系七牌阵（用户抽牌示例）──")
    for c in r4.drawn_cards:
        print(f"  [{c['position_id']}. {c['position_name']}] "
              f"{c['card_name']} ({c['orientation']})")
    print()

    # 年度 12 宫
    r5 = draw_tarot(spread="year_twelve", card_indexes=list(range(12)), question="2026 年怎么走？")
    print("── 年度十二宫（用户抽牌示例）──")
    for c in r5.drawn_cards:
        print(f"  [{c['position_id']:2d}月] {c['card_name']} ({c['orientation']})")
    print()

    # 决策十字
    r6 = draw_tarot(spread="decision_cross", card_indexes=list(range(5)),
                    question="该选择 A 公司还是 B 公司？")
    print("── 决策十字（用户抽牌示例）──")
    for c in r6.drawn_cards:
        print(f"  [{c['position_id']}. {c['position_name']}] "
              f"{c['card_name']} ({c['orientation']})")
    print()

    # 验证可复现：相同用户抽牌结果两次映射一致
    r_a = draw_tarot(spread="single", card_indexes=[42])
    r_b = draw_tarot(spread="single", card_indexes=[42])
    assert r_a.drawn_cards[0]["card_id"] == r_b.drawn_cards[0]["card_id"]
    assert r_a.drawn_cards[0]["orientation"] == r_b.drawn_cards[0]["orientation"]
    print("可复现验证通过：同一抽牌结果两次映射一致。")

    # 查找单张
    fool = find_card_by_id("major_00_fool")
    print(f"\n查询 major_00_fool: {fool['name']} ({fool['name_en']})")
    seven_wands = find_card_by_id("wands_07")
    print(f"查询 wands_07: {seven_wands['name']} - {seven_wands['meaning_upright'][:40]}...")
