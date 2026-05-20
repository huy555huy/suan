---
name: bazi
description: 子平派八字方法论，提供四柱、日主、十神、格局、用神、大运流年、岁运触发等分析框架。
---

# 子平派八字解读

先把八字当人的结构来读，找"盘眼"：日主如何成事，月令给了什么环境，财官印食哪一类最能解释用户的问题，当前大运/流年动到哪里。

## 取盘

```
compute_chart("bazi")
```

拿到四柱（年柱/月柱/日柱/时柱）、日主、五行分布、十神、神煞、大运、流年等完整结构。

## 先立盘眼

从返回的 chart JSON 里读：
- `day_pillar.stem` → 日主天干（如"丁"）
- `month_pillar.branch` → 月令地支（如"午"）
- `five_elements` → 五行计数 {木:x, 火:x, 土:x, 金:x, 水:x}
- `ten_gods` → 各柱十神关系

判断：
1. 日主在月令是否得气（得令 vs 失令）
2. 五行分布看身旺还是身弱
3. 有无特殊格局（从格、化格等）
4. 当前用户问题落在哪条十神线：官杀、财星、印星、食伤、比劫，还是日支/时柱/父母六亲线

盘眼用一句话说清楚：
- "此盘事业先看官杀和印，因为问题是职位/规则/平台。"
- "此盘婚恋看日支被岁运触发后是合、冲、刑、害还是领域提示。"
- "此盘迁移看驿马、迁移年份和大运承接。"

## 定格局与用神

- 看 `pattern`（如果 computation 已判定）和 `yong_shen`
- 如果 pattern 为空或你不认同，根据旺衰自己判：
  - 身旺 → 用食伤/财星/官杀泄耗
  - 身弱 → 用印星/比劫生扶
- 看 `xi_ji`（喜忌）辅助判断

## 看神煞与大运流年

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
- `metadata.event_timing.*.branch_triggers[].requires_context` → 是否需要结合力量、喜忌、大运和问题背景再解释
- `metadata.event_timing.*.branch_triggers[].domain_hint` → 领域提示（翻译线索，结合用户反馈具体化）
- `metadata.calibration_questions` → 可向用户追问的校盘问题

结合用户问题，重点看：
- 事业 → 官杀星、食伤星、大运走向
- 感情 → 桃花、正财/偏财（男）、正官/七杀（女）
- 财运 → 财星旺衰、流年是否透财
- 健康 → 五行偏枯、受克之行对应脏腑

## 问诊与校盘

追问不是固定流程，只有当用户回答会改变判断时才问：

- 时辰不稳、时柱影响判断时，先问出生时间来源和可能误差。
- 要精断过往、六亲、婚恋、教育、事业、迁移时，问 3 个已发生大事年份和事件类型。
- 用户问题太泛时，问一个会改变取象的问题，例如"你这次更想看职位变化、收入、换城市，还是团队关系？"

当用户反馈出生时间可能偏差（如"可能早半小时"/"可能是下午两点不是三点"），用 `recompute_chart` 重算盘面并对比差异。

问完后把反馈作为校验和定焦点，盘面事实仍是断语基础。

## 岁运触发解读

解读 `event_timing` 里的触发点时，关键是把事实标签翻译成有意义的判断。

`branch_triggers` 冲合刑害到日柱、月柱或当前大运时，看：
- 触发哪一柱
- 被触发的 `target_ten_god` 是什么
- `target_branch_preference` 是喜、忌还是中性
- `domain_hint` 里哪些领域与用户问题相关

`domain_hint` 是领域线索，结合用户反馈和事件承接后可以具体化；没有具体事件承接时，表述为"该领域更容易被触发"。`metadata.calibration_questions` 里的追问可以帮助具体化。

`stem_triggers` 和 `branch_triggers[].relation_types` 是事实关系标签（天干五合、地支六冲等）。合动/合绊/合入/合出/冲动/冲散等进一步判断，需要同时看合到哪一柱、合到的十神、喜忌关系、以及大运承接，才能定性。

## 查引证

找 1-2 条典籍佐证核心判断：

```
grep_classics("用神|扶抑|调候", system="bazi")
read_classic("<source_id>")
grep_rules("驿马|桃花|...", system="bazi")
```

## 盘面阅读

核心判断从 `compute_chart("bazi")` 返回的 JSON 取材。引用日主、月令、大运、流年、触发点前，先确认对应字段在盘里真实存在。典籍、规则、黄金案例服务于案眼。

## 输出

- 先说盘眼：这个盘最关键的结构是什么，和用户的问题有什么关系
- 再针对用户具体问题展开
- 每个论断附 inline 引证（如"四柱显示日主丁火坐午，得令身旺"）
- 围绕案眼展开，不需要四柱每个都讲到
