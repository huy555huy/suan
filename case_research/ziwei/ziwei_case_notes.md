# 紫微斗数案例研究笔记

## 研究结论先记

紫微公开资料里，真实带回验的盘例较少，教学型命例较多。因此本批笔记分两类：

- teaching_case：可抽方法，不能当实证。
- engine_case：项目内可复算，可做回归。

紫微职业判断的核心不是“命宫某星等于某职业”，而是命宫、官禄、财帛、迁移、大限流年一起看。

## ZW-C01 事业命例标准切入：命宫、官禄、财帛、迁移、大限

- source: https://wiki.tianjiyao.com/ziwei/career-case-studies.html
- source_type: teaching cases
- reliability: method-only
- topic: 事业判断流程

### 方法摘记

该资料把事业判断拆成五步：

1. 命宫看主轴与承压方式。
2. 官禄宫看职业角色结构。
3. 财帛宫看回报闭环。
4. 迁移宫看外部平台。
5. 大限流年看何时显化。

### 对 Agent 的启发

- 紫微不能只读 `life_palace` 和 `main_stars.命宫`。
- 需要引擎暴露官禄、财帛、迁移三宫的主星和四化。
- 若缺大限流年，不应断具体年份，只能断结构倾向。

## ZW-C02 命财官迁闭环完整：稳步上升型

- source: https://wiki.tianjiyao.com/ziwei/career-case-studies.html
- source_type: teaching case
- reliability: method-only
- topic: 事业闭环

### 盘面结构

- 命宫紫微。
- 官禄宫天府。
- 财帛宫武曲。
- 迁移宫天相。

### 师傅抓手

- 命宫紫微：有中心感、统筹意识。
- 官禄天府：长期经营、管理、资源配置。
- 财帛武曲：回报结构清楚。
- 迁移天相：外部平台和组织关系可承接。

### 推理链

- 主证据不是单星，而是命财官迁闭环。
- 结论是“结构完整、慢慢做大”，不是突然爆发。

### 对 Agent 的启发

- 需要构建 `metadata.career_axis`：
  - life_palace_stars
  - career_palace_stars
  - wealth_palace_stars
  - migration_palace_stars
  - axis_completeness

## ZW-C03 官禄强但命宫承接不足：有位置也有压力

- source: https://wiki.tianjiyao.com/ziwei/career-case-studies.html
- source_type: teaching case
- reliability: method-only
- topic: 官禄强、命宫弱承接

### 盘面结构

- 命宫天同。
- 官禄宫七杀。
- 财帛宫一般。
- 迁移宫火铃会照。

### 师傅抓手

- 命宫天同偏缓冲、舒适、和气。
- 官禄七杀代表高压、竞争、责任锋面。
- 机会可能不低，但命主主观感受是压力与节奏过快。

### 推理链

- 主证据：命宫气质与官禄角色不匹配。
- 辅证：财帛、迁移承接不足。
- 结论：有位置不等于稳定舒服。

### 对 Agent 的启发

- 紫微职业解读要比较“命宫承接力 vs 官禄压力”。
- 不能只因官禄强就说事业顺。

## ZW-C04 官禄一般但财迁强：靠平台与资源起势

- source: https://wiki.tianjiyao.com/ziwei/career-case-studies.html
- source_type: teaching case
- reliability: method-only
- topic: 迁移/财帛补足官禄

### 盘面结构

- 命宫天机。
- 官禄宫平。
- 财帛宫贪狼。
- 迁移宫太阳。

### 师傅抓手

- 命宫天机适合动态环境、策划、信息流。
- 官禄不强，说明固定组织位置未必是最大优势。
- 财帛贪狼和迁移太阳提供机会、人脉、曝光、外部平台。

### 对 Agent 的启发

- 事业不是只看“职业宫强不强”；有些盘靠项目、平台、人脉、资源整合成事。
- 需要避免把官禄宫弱等同于事业差。

## ZW-C05 本项目黄金例：命宫天相 + 福德武曲七杀

- source: `data/pro_golden_cases.json`
- source_type: internal engine case
- reliability: high for engine regression
- topic: 天相入命、武曲七杀落福德

### 盘面事实

- 命宫：天相。
- 身宫：福德宫。
- 福德宫：武曲、七杀。
- 四化：巨门化禄、太阳化权、文曲化科、文昌化忌。

### 师傅抓手

- 命宫天相：先看秩序、协作、规则、平台，不按强攻型主星断。
- 武曲七杀在福德：压力承载、结果导向、内在执行感强，但要按福德宫主题转译，不可直接说命宫武杀。

### 对 Agent 的启发

- `main_stars.*` 的星曜断语必须带宫位。
- 同一星组合落命宫、福德、官禄、财帛，解释完全不同。
