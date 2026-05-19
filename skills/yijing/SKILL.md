---
name: yijing
description: 易经占卜（梅花易数为主）。当用户问具体决策的吉凶、时机选择、事件走向时加载。
---

# 易经占卜解读

## Step 1: 算卦

```
compute_chart("hexagram")
```

梅花易数根据问题和时间起卦，拿到本卦/变卦/互卦、动爻、世爻/应爻、六亲、六神等。

## Step 2: 读卦象

- `ben_gua` → 本卦（当前状态）：卦名、上卦、下卦
- `bian_gua` → 变卦（趋势/结果）
- `hu_gua` → 互卦（过程/中间状态）
- `moving_lines` → 动爻位置（变化的关键点）
- `yong_shen` → 用神
- `shi_yao` / `ying_yao` → 世爻(自己)/应爻(对方/事物)
- `six_relatives` → 六亲（父母/兄弟/子孙/妻财/官鬼）
- `six_gods` → 六神（青龙/朱雀/勾陈/螣蛇/白虎/玄武）
- `metadata.liuyao_analysis` → 用神落爻、月令旺衰、旬空、世应关系、动爻作用
- `metadata.liuyao_analysis.yong_shen_source` / `yong_shen_confidence` → 用神来源与置信
- `metadata.liuyao_analysis.needs_clarification` → 用神未定、身份未明、伏神/飞神待查等追问项

## Step 3: 断卦

1. **看体用关系**（梅花易数核心）：
   - 动爻所在的卦为"用"，不动的为"体"
   - 用生体 → 吉（外来助力）
   - 体生用 → 耗（付出精力）
   - 用克体 → 凶（受阻/受损）
   - 体克用 → 可得但费力
   - 比和 → 平稳

2. **看用神旺衰**：
   - 先确认 `question_yong_shen` 不是 `null`
   - 如果 `needs_clarification` 非空，不要下确定吉凶，先追问或明确标记"用神待定"
   - 先看 `metadata.liuyao_analysis.yong_shen_lines`
   - `strength_label` 为旺/有气则用神可用；偏弱/空弱则事情不稳
   - `moving_effects` 看动爻生扶用神还是克制用神

3. **看世应**：
   - 读 `metadata.liuyao_analysis.shi_ying_relation`
   - 世应比和/相生 → 合作较顺
   - 世应相克/被克 → 立场冲突或外部阻力
   - 用神不上卦或在 `needs_clarification` 有提示时，必须说明需要补充身份/性别/占事细节

4. **看变卦**：
   - 变卦代表事情的最终走向
   - 变卦生本卦 → 结果有回转
   - 变卦克本卦 → 需要注意后果

## Step 4: 查引证

```
grep_classics("体用|梅花|动爻", system="yijing")
grep_rules("六亲|用神|世应", system="yijing")
```

## Step 5: 校验

```
verify_chart_ref(path="hexagram.ben_gua.name", expected="...")
verify_chart_ref(path="hexagram.moving_lines", expected="...")
```

## Step 6: 输出

- 先报卦象："起卦得 X 之 Y（本卦 之 变卦），动 N 爻"
- 再断吉凶：体用关系 → 世应 → 用神 → 变卦趋势
- 给出时间参考（如"近一个月内"/"三个月周期"）
- 易经占卜是**针对具体事件**的，不要泛泛说运势
- 如果用户问的太泛（"我今年怎样"），建议他缩窄到具体问题
- 感情/婚姻占必须确认求测者身份与所问对象；男问伴侣多取妻财，女问伴侣多取官鬼，不能一律按妻财断。
