---
name: astrology
description: 西洋占星解读（现代心理占星为主）。当用户问性格深层、关系动力、人生主题、流年transit时加载。
---

# 西洋占星解读

## Step 1: 算盘

```
compute_chart("natal_astro")
```

如果用户问近期运势，还需要：
```
compute_chart("transit_astro")
```

拿到行星位置（星座+宫位+度数）、四轴（ASC/MC/DSC/IC）、宫位、相位、元素/模式分布。

## Step 2: 读核心配置

从 natal chart 读：
- `planets.sun` → 太阳星座+宫位（核心自我）
- `planets.moon` → 月亮星座+宫位（情感模式）
- `planets.mercury/venus/mars` → 内行星（思维/爱/行动）
- `angles.ASC` → 上升点（外在人格面具）
- `angles.MC` → 天顶（事业/社会形象）
- `houses` → 12 宫边界
- `aspects` → 行星间相位（合相/六分/四分/三分/对分）
- `distributions` → 元素(火/土/风/水) + 模式(开创/固定/变动)分布

## Step 3: 针对问题解读

**事业**: MC 星座 + 10 宫行星 + 土星位置 + 6 宫（日常工作）
**感情**: 金星 + 7 宫 + 月亮 + DSC 星座
**财运**: 2 宫（自我价值/收入）+ 8 宫（他人资源）+ 木星
**性格**: 太阳+月亮+ASC 三位一体 + 元素分布
**健康**: 6 宫 + 火星 + 月亮相位
**人生转折**: 冥王/天王/海王的宫位和相位（世代行星的个人化表达）

## Step 4: 看 Transit（如果算了）

从 transit chart 读 `aspects_to_natal` 和 `key_transits`：
- 土星 transit → 结构性变化、责任、考验
- 木星 transit → 扩张、机会、过度
- 天王星 transit → 突变、自由、觉醒
- 冥王星 transit → 深层转化、权力
- 看 transit 行星和本命行星形成什么相位

## Step 5: 查引证

```
grep_classics("太阳|月亮|上升", system="astrology")
grep_rules("transit|相位|合相", system="astrology")
```

## Step 6: 校验结论（三元组）

每条核心结论必须过 `verify_claim`：

```
verify_claim(
  claim="太阳在狮子座落第十宫，事业心强烈，追求公众认可",
  chart_ref="natal_astro.planets.sun.sign=Leo",
  rule_ref="astro_rule_012",
  source_ref="astro_modern_psych_p034",
  tier="A_core"
)
```

## Step 7: 输出

- 用中文名称（太阳在狮子座，不说 Sun in Leo）
- 相位用中文（四分相/三分相，不说 square/trine）
- 星座特质描述要具体，不要模板化的"你很热情"
- Transit 影响标注时间窗口（"土星过天顶的影响期约 2024.3-2025.1"）
