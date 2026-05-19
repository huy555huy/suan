---
name: bazi
description: 子平派八字解读。当用户问事业/婚配/财运/时机/格局/健康(中医视角)/性格时加载。
---

# 子平派八字解读

被加载后，按以下流程做。**不要跳步**。

## Step 1: 算盘

```
compute_chart("bazi")
```

拿到四柱（年柱/月柱/日柱/时柱）、日主、五行分布、十神、神煞、大运、流年等完整结构。

## Step 2: 读关键字段，判旺衰

从返回的 chart JSON 里读：
- `day_pillar.stem` → 日主天干（如"丁"）
- `month_pillar.branch` → 月令地支（如"午"）
- `five_elements` → 五行计数 {木:x, 火:x, 土:x, 金:x, 水:x}
- `ten_gods` → 各柱十神关系

判断：
1. 日主在月令是否得气（得令 vs 失令）
2. 五行分布看身旺还是身弱
3. 有无特殊格局（从格、化格等）

## Step 3: 定格局与用神

- 看 `pattern`（如果 computation 已判定）和 `yong_shen`
- 如果 pattern 为空或你不认同，根据旺衰自己判：
  - 身旺 → 用食伤/财星/官杀泄耗
  - 身弱 → 用印星/比劫生扶
- 看 `xi_ji`（喜忌）辅助判断

## Step 4: 看神煞与大运流年

- `shen_sha` 列表 → 驿马/桃花/华盖/天乙贵人等
- `da_yun` → 大运走势（每步十年）
- `liu_nian` → 近年流年干支
- `metadata.chart_interactions` → 原局天干合克、地支冲合刑害
- `metadata.event_timing.current_da_yun` → 当前所在大运
- `metadata.event_timing.liu_nian` → 流年喜忌评分、冲合刑害触发点
- `metadata.event_timing.*.stem_triggers` → 岁运天干与原局天干的合、克触发点
- `metadata.event_timing.*.branch_triggers[].target_ten_god` → 被冲合刑害触发的地支主气十神
- `metadata.event_timing.*.branch_triggers[].target_branch_preference` → 被触发地支五行对命局喜忌的方向
- `metadata.event_timing.*.stem_triggers[].relation_types` → 天干五合、天干相克等事实关系数组
- `metadata.event_timing.*.branch_triggers[].relation_types` → 地支六合、地支六冲、地支六害、地支刑等事实关系数组
- `metadata.event_timing.*.branch_triggers[].requires_context` → 是否必须结合力量、喜忌、大运和问题背景再解释
- `metadata.event_timing.*.branch_triggers[].domain_hint` → 领域提示，只能作为翻译线索，不能单独当结论
- `metadata.calibration_questions` → 需要向用户追问的校盘问题

结合用户问题，重点看：
- 事业 → 官杀星、食伤星、大运走向
- 感情 → 桃花、正财/偏财（男）、正官/七杀（女）
- 财运 → 财星旺衰、流年是否透财
- 健康 → 五行偏枯、受克之行对应脏腑

如果 `metadata.event_timing.*.branch_triggers` 冲合刑害到日柱、月柱或当前大运，必须说明：
- 触发哪一柱；
- 被触发的 `target_ten_god` 是什么；
- `target_branch_preference` 是喜、忌还是中性；
- `domain_hint` 里哪些领域与用户问题相关。

不要只说“今年变动大”。`domain_hint` 是领域提示，不是实断；如果没有用户问题或事件反馈承接，只能说“该领域更容易被触发”，不能断“必离职/必分手/必生病”。如果出现 `metadata.calibration_questions`，优先挑 1-2 个和用户问题最相关的问题追问或在结尾给出。

如果出现 `stem_triggers` 或 `branch_triggers[].relation_types`，只能说“存在天干/地支关系事实，需要结合上下文判断”。不能直接把合说成合动或吉，不能把冲直接说成坏事。必须同时看：
- 合到哪一柱；
- 合到的十神是什么；
- 合来之神与被合之神的喜忌；
- 是否有冲刑害或大运承接。

`relation_types` 只是事实标签，不是断语。合动、合绊、合入、合出、合而不化、冲动、冲散、冲开等词只能在盘面力量、岁运承接和用户问题都支持时作为解释写出；证据不足时必须保留不确定。

## Step 5: 查引证

找 1-2 条典籍佐证你的核心判断：

```
grep_classics("用神|扶抑|调候", system="bazi")
```

挑相关性高的：
```
read_classic("<source_id>")
```

同样查规则：
```
grep_rules("驿马|桃花|...", system="bazi")
```

## Step 6: 校验结论（三元组）

每条核心结论必须过 `verify_claim`，提供完整三元组：

```
verify_claim(
  claim="日主丁火坐巳，得令身旺，宜用食伤泄秀",
  chart_ref="bazi.day_pillar.stem=丁",
  rule_ref="bazi_rule_003",
  source_ref="ziping_zhenquan_p072",
  tier="A_core"
)
```

- Tier A（格局判断、用神、流年趋势）→ 三元组必须齐全
- Tier B（辅助论证）→ 至少 chart_ref
- FACT_VIOLATION → 硬拒，必须修正后重新 verify

## Step 7: 输出

- 先概述格局：日主 X，月令 Y，身旺/身弱，格局 Z
- 再针对用户具体问题展开
- 每个论断附 inline 引证（如"四柱显示日主丁火坐午，得令身旺"）
- 置信度标注：如果某项判断依据单薄，标"此项仅供参考"
- 不说"100%"/"必然"/"一定"
