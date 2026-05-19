---
name: fengshui
description: 风水解读（玄空飞星+八宅）。当用户问居家/办公布局、方位吉凶、搬家择向时加载。
---

# 风水解读

## Step 1: 算盘

```
compute_chart("fengshui")
```

拿到坐向、运盘、飞星分布、八宅、命卦、吉凶方位等。

## Step 2: 读关键数据

- `facing_direction` → 朝向（度数 + 名称）
- `sitting_direction` → 坐向
- `period` → 当前元运（如九运 2024-2043）
- `flying_stars` → 九宫飞星（山盘/向盘/运盘）
- `ba_zhai` → 八宅（东四命/西四命，各方位吉凶）
- `ming_gua` → 命卦
- `favorable_directions` → 吉方
- `unfavorable_directions` → 凶方
- `metadata.pan_method` → 下卦/替卦
- `metadata.facing_degree_detail` → 朝向落山、离中心度数、是否替卦
- `metadata.palace_priorities` → 旺财、卧床稳定、需谨慎方位
- `metadata.site_questions` → 断门床灶前必须追问的现场事实

## Step 3: 玄空飞星分析

飞星组合（山盘+向盘）的核心含义：
- 1-1: 桃花水、聪明
- 2-5 / 5-2: 大凶（病符+五黄）
- 6-8 / 8-6: 大吉（武曲+左辅）
- 1-4 / 4-1: 文昌、学业
- 2-3 / 3-2: 斗牛煞（口舌）
- 6-7 / 7-6: 交剑煞
- 8-8: 当运旺星，大利财

看用户关心的方位对应哪个宫位的飞星组合。

如果没有户型图，不能断具体门、床、灶吉凶，只能说明方位层面的候选；必须引用 `metadata.site_questions` 追问户型、测量方法、外局形势。若 `metadata.pan_method == "替卦"`，要提醒用户复测罗盘度数。

## Step 4: 八宅辅助

八宅把八个方位分为四吉四凶：
- 生气/天医/延年/伏位 → 吉
- 绝命/五鬼/六煞/祸害 → 凶

结合命卦看用户是东四命还是西四命，对应吉方不同。

## Step 5: 查引证

```
grep_classics("飞星|玄空|八宅", system="fengshui")
grep_rules("飞星组合|方位", system="fengshui")
```

## Step 6: 校验

```
verify_chart_ref(path="fengshui.period", expected="9")
verify_chart_ref(path="fengshui.ming_gua", expected="...")
```

## Step 7: 输出

- 先报基本盘面："坐 X 朝 Y，X 运盘"
- 各方位吉凶要具体到飞星组合
- 给出**可操作**的建议（如"卧室宜设在 X 方位"/"Y 方位宜放铜器化煞"）
- 风水建议要务实，不要夸大
- 注意：如果用户没提供户型图和门床灶位置，不要输出具体布局结论。
