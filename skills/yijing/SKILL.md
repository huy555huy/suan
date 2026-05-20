---
name: yijing
description: 易经/六爻方法论（梅花易数与铜钱卦），提供卦象、动爻、用神、世应、六亲六神与事件占断框架。
---

# 易经占卜解读

易经/六爻是针对具体事件的占断工具。起卦输入来自用户明示：数字、六次铜钱结果，或明确起卦时间。

## 取卦

```
compute_chart("hexagram")
```

拿到本卦/变卦/互卦、动爻、世爻/应爻、六亲、六神等。

## 先定占事与用神

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

`needs_clarification` 非空时，说明用神尚未落定，断语宜带"待校准"标记或先追问。

## 断卦

1. **看体用关系**（梅花易数核心）：
   - 动爻所在的卦为"用"，不动的为"体"
   - 用生体 → 吉（外来助力）
   - 体生用 → 耗（付出精力）
   - 用克体 → 凶（受阻/受损）
   - 体克用 → 可得但费力
   - 比和 → 平稳

2. **看用神旺衰**：
   - 先确认 `question_yong_shen` 是否已定
   - 看 `metadata.liuyao_analysis.yong_shen_lines`
   - `strength_label` 为旺/有气则用神可用；偏弱/空弱则事情不稳
   - `moving_effects` 看动爻生扶用神还是克制用神

3. **看世应**：
   - 读 `metadata.liuyao_analysis.shi_ying_relation`
   - 世应比和/相生 → 合作较顺
   - 世应相克/被克 → 立场冲突或外部阻力

4. **看变卦**：
   - 变卦代表事情的最终走向
   - 变卦生本卦 → 结果有回转
   - 变卦克本卦 → 需要注意后果

## 问诊

- 问工作时先问清焦点：职位、录用、薪资、合同、领导关系、调动——不同焦点用神不同。
- 问感情/婚姻先确认求测者身份与所问对象；男问伴侣多取妻财，女问伴侣多取官鬼。
- 问失物、疾病、官司、财务时，先定用神和主体。
- 卦义服从用神、月日、世应和动爻，而非卦名直断。

## 查引证

```
grep_classics("体用|梅花|动爻", system="yijing")
grep_rules("六亲|用神|世应", system="yijing")
```

## 盘面阅读

输出前回到 `compute_chart("hexagram")` 的 JSON：看本卦/变卦、动爻、用神、世应、六亲六神和 `metadata.liuyao_analysis`。卦象是材料，断事服务于用户的具体问题。

## 输出

- 先报占事焦点和用神；用神不稳时带"待校准"标记
- 再报卦象："起卦得 X 之 Y（本卦 之 变卦），动 N 爻"
- 再断趋势：用神 → 月日旺衰 → 世应 → 动爻作用 → 变卦趋势
- 给出时间参考（如"近一个月内"/"三个月周期"）
- 用户问题太泛时，建议缩窄到具体事件再占断
