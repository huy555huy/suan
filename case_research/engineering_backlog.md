# 案例研究转工程 Backlog

目标：把项目推进到“举世皆知的老师傅”级别。工程验收不看功能堆叠，看三件事：算盘事实准、断法路径像内行、强结论可被盘面/规则/案例同时追溯。

## Done

### BZ-D01 八字 branch_triggers 补十神与喜忌

已完成：

- `target_ten_god`
- `target_branch_hidden_stems`
- `target_main_hidden_ten_god`
- `target_is_favorable`
- `target_is_unfavorable`
- `target_branch_preference`
- `domain_hint`

### BZ-D02 干支触发事实结构化

已完成：

- `stem_triggers` / `branch_triggers`
- `interactions`
- `relation_types`
- `requires_context`

纪律：

- `relation_types` 只表示事实关系。
- 合动、合绊、合入、合出、合而不化等必须留在解释层，不能作为事实字段。

## P0 先做

### Golden-E01 黄金案例扩容格式

在 `data/pro_golden_cases.json` 中新增字段：

- `reasoning_steps`
- `counter_signals`
- `required_questions`
- `forbidden_claims`
- `pattern_refs`

目的：

- 让黄金集从事实回归升级为断法回归。
- 把“老师傅为什么这么断”压成可测试材料。

### Golden-E02 专业黄金案例扩容

需要按体系补真实/人工盘例：

- 八字：婚恋应期、病伤应期、财运破财、迁移调动、从格真伪。
- 紫微：大限流年四化、夫妻宫、迁移/官禄联动。
- 六爻：财务占、感情占、失物占、疾病占。
- 风水：完整户型、门向/水口应期、下卦与替卦对照。

目的：

- 用案例数量校正“像老师傅”的判断节奏。

### LY-E01 六爻问题焦点分类

现状：

- 工作类问题容易直接取官鬼。

需要：

- intake 或 yijing analyzer 先分类：
  - position：官鬼
  - salary：妻财
  - contract/unit：父母
  - boss/rules：官鬼 + 应爻
- 焦点不清时 `needs_clarification`。

目的：

- 避免“问工资却取官鬼”的用神错误。

### FS-E01 风水输入合同升级

现状：

- 可用 facing_degree + move_in_year 排盘。

需要：

- 若用户要具体布局/吉凶应事，必须补：
  - 户型图或至少门窗方位
  - 灶、厕、床、书桌/收银台
  - 道路/水路/人流方向
- 缺现场输入时只输出“盘法分析/待现场复核”。

目的：

- 防止风水脱离现场乱断。

## P1 做

### ZW-E01 紫微 career_axis

需要从 `palaces` 中结构化抽取：

- 命宫主星
- 官禄宫主星
- 财帛宫主星
- 迁移宫主星
- 四化落宫
- 命财官迁闭环摘要

目的：

- 避免紫微只看命宫。

### LY-E02 六爻动爻作用结构化

需要：

- moving_effects 明确动爻对用神是生、克、冲、合、墓、空、化退、化进。
- response_timing_candidates 给出应期候选。

目的：

- 输出“有阻但何时解”。

## P2 做

### FS-E02 年月飞星叠盘

需要：

- annual_flying_stars
- monthly_flying_stars
- 与本宅盘宫位组合。

目的：

- 风水具体年份应事。
