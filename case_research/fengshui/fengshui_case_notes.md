# 风水案例研究笔记

## 研究结论先记

风水案例的专业难点不在“会不会排盘”，而在输入和现场。坐向、元运、门窗、水路、道路、人流、灶厕、形峦缺一块，断语都要降级。

玄空飞星案例常见流程：

1. 定元运与坐向。
2. 排宅盘，分山星/向星/运星。
3. 找动气口：门、路、窗、水、人流。
4. 看星组合在该元运是否当令。
5. 再看形峦是否启动或破坏该星气。

## FS-C01 瑞记洋货店：街角动气与元运转换

- source: https://zenelementsoflife.com/geomancy-feng-shui-%E9%A2%A8%E6%B0%B4/
- source_type: historical flying-star case
- reliability: medium。案例来自宅运新案类资料整理，非现代实测。
- topic: 商铺、街角动气、元运变化、火灾

### 原始输入

- 地点：上海小南门外南仓街瑞记洋货店。
- 一运开业，二运翻造。
- 坐辛向乙，坐西向东。

### 师傅抓手

- 商铺重向星和动气口。
- 街角聚人流、车流，是强动气点。
- 一运时街角星组合可用，二运翻造后同一动气点落 5、7，不吉。
- 后续应事包括经营快速衰落与火灾。

### 对 Agent 的启发

- 风水盘必须标 `active_mouths`，如门、窗、路口、街角。
- 飞星吉凶不能只看宫位，要看是否被动气启动。

## FS-C02 婚姻失和宅：路气入门与灶位 2-5

- source: https://zenelementsoflife.com/geomancy-feng-shui-%E9%A2%A8%E6%B0%B4/
- source_type: historical flying-star case
- reliability: medium
- topic: 住宅、婚姻、健康、灶位

### 原始输入

- 地点：上海大南门外某新造宅。
- 三运宅。
- 坐壬向丙，坐北向南。

### 师傅抓手

- 外路气经入口导入宅门。
- 主入口路径上有吉星组合，说明不是全宅皆坏。
- 灶位落 2、5，且旧式灶产生烟火秽气，触发病气/混乱。
- 应事：母亲长期病，夫妻几近离异。

### 对 Agent 的启发

- 风水断语要允许“一处吉、一处凶”并存。
- 需要输入灶、厕、床、门窗位置，否则不能断健康/婚姻。

## FS-C03 陆稿荐店：同一店铺在不同年份星气转换

- source: https://zenelementsoflife.com/geomancy-feng-shui-%E9%A2%A8%E6%B0%B4/
- source_type: historical flying-star case
- reliability: medium
- topic: 商铺财运、年度飞星、五行生泄

### 原始输入

- 地点：上海北河南路陆稿荐。
- 三运开业，卯山酉向兼甲庚。
- 三运内生意不错，1924 年尤佳，1932 年开始不利。

### 师傅抓手

- 商铺看入口和窗口处的向星/动气。
- 三运入口星 3、窗口星 8 形成木性回路。
- 1924 年同区 1、6 水性生木，财气增强。
- 1932 年 2、7 火性泄木，财气转衰。

### 对 Agent 的启发

- 风水引擎需要把年月飞星叠入宅盘，不能只给本宅盘。
- “财星到向”还要看年月星生泄制化。

## FS-C04 五芳斋连年获利：双星到向、收银台与楼梯动线

- source: https://zenelementsoflife.com/geomancy-feng-shui-%E9%A2%A8%E6%B0%B4/
- source_type: historical flying-star case
- reliability: medium
- topic: 商铺、双星到向、动线、收银台

### 原始输入

- 地点：上海南京路五芳斋。
- 三运，1917 年入宅。
- 丙山壬向，坐南向北，双星到向。
- 反馈：入宅十余年生意旺。

### 师傅抓手

- 向方同时得健康星和财星。
- 收银台所在方有吉星。
- 楼梯和人流动线启动向方星气。
- 小入口反而聚气，不使旺气散泄。

### 对 Agent 的启发

- 商铺风水必须要求收银台、门、楼梯、人流路线。
- 对商铺，`cashier_position` 是核心输入，不是附加信息。

## FS-C05 破墙头女魁元：形峦阻风与 1-4 文昌组合

- source: https://zenelementsoflife.com/geomancy-feng-shui-%E9%A2%A8%E6%B0%B4/
- source_type: historical flying-star case
- reliability: medium
- topic: 学业、1-4、外部形峦

### 原始输入

- 地点：江苏太仓浏河。
- 四运宅。
- 坐寅向申。
- 应事：1928 年夏，小学生会考第一。

### 师傅抓手

- 向方有 1、4 组合，主文名/学业象。
- 月飞星 6 与 1、4 配合，增强权威/考试象。
- 外部破墙阻挡杂风，使东南文气更能收住。

### 对 Agent 的启发

- 学业风水不能只看 1、4，还要看是否有形峦收气。
- 没有户外环境信息时，不能断“必有学业佳绩”。

## FS-C06 本项目黄金例：九运丁向替卦

- source: `data/pro_golden_cases.json`
- source_type: internal engine case
- reliability: high for engine regression
- topic: 替卦、九运、丁向、南方开口

### 盘面事实

- 入住年：2024。
- 元运：九运。
- 朝向：200 度，丁向。
- pan_method：替卦。
- 替卦学派：沈氏。
- 南方离宫为优先开口/财气关注点。

### 师傅抓手

- 200 度落丁向替卦区，不能按下卦排。
- 九运看离火和南方动气，但必须现场复核门窗水路。

### 对 Agent 的启发

- 风水若接近替卦边界，必须要求罗盘复测到 0.1 度。
- 没有户型和开口，不应输出具体催财布局。
