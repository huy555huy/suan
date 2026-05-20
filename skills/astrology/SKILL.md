---
name: astrology
description: 西洋占星方法论（现代心理占星为主），提供本命行星、宫位、相位、四轴、元素模式与行运分析框架。
---

# 西洋占星解读

## 取盘

```
compute_chart("natal_astro")
```

如果用户问近期运势，还需要：
```
compute_chart("transit_astro")
```

拿到行星位置（星座+宫位+度数）、四轴（ASC/MC/DSC/IC）、宫位、相位、元素/模式分布。

## 核心配置

从 natal chart 读：
- `planets.sun` → 太阳星座+宫位（核心自我）
- `planets.moon` → 月亮星座+宫位（情感模式）
- `planets.mercury/venus/mars` → 内行星（思维/爱/行动）
- `angles.ASC` → 上升点（外在人格面具）
- `angles.MC` → 天顶（事业/社会形象）
- `houses` → 12 宫边界
- `aspects` → 行星间相位（合相/六分/四分/三分/对分）
- `distributions` → 元素(火/土/风/水) + 模式(开创/固定/变动)分布

## 针对问题取材

**事业**: MC 星座 + 10 宫行星 + 土星位置 + 6 宫（日常工作）
**感情**: 金星 + 7 宫 + 月亮 + DSC 星座
**财运**: 2 宫（自我价值/收入）+ 8 宫（他人资源）+ 木星
**性格**: 太阳+月亮+ASC 三位一体 + 元素分布
**健康**: 6 宫 + 火星 + 月亮相位
**人生转折**: 冥王/天王/海王的宫位和相位（世代行星的个人化表达）

## Transit（如果算了）

从 transit chart 读 `aspects_to_natal` 和 `key_transits`：
- 土星 transit → 结构性变化、责任、考验
- 木星 transit → 扩张、机会、过度
- 天王星 transit → 突变、自由、觉醒
- 冥王星 transit → 深层转化、权力
- 看 transit 行星和本命行星形成什么相位

## 查引证

```
grep_classics("太阳|月亮|上升", system="astrology")
grep_rules("transit|相位|合相", system="astrology")
```

## 盘面阅读

引用具体行星、宫位、相位、Transit 触发前，先在 `compute_chart` 返回的 JSON 里找到对应事实。盘面事实提供材料，性格、关系或时机判断结合宫位、相位、问题背景和规则材料。

## 输出

- 用中文名称（太阳在狮子座而非 Sun in Leo）
- 相位用中文（四分相/三分相而非 square/trine）
- 星座特质描述具体到此盘
- Transit 影响标注时间窗口（"土星过天顶的影响期约 2024.3-2025.1"）
