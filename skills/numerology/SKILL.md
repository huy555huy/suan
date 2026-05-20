---
name: numerology
description: 生命灵数/数字命理方法论，提供生命路径、表达数、灵魂数、人格数、个人年与阶段主题分析框架。
---

# 数字命理解读

## 取数

```
compute_chart("numerology")
```

拿到生命路径数、表达数、灵魂冲动数、人格数、命运数、个人年数等。

## 核心数字

- `life_path` → 生命路径数（最重要，从生日算出，代表人生主线）
- `expression` → 表达数（从全名算出，代表天赋才能）
- `soul_urge` → 灵魂冲动数（内心深层渴望）
- `personality` → 人格数（外在呈现）
- `destiny` → 命运数
- `personal_year` → 个人年数（今年的主题）
- `master_number_flag` → 是否有大师数字（11/22/33）

## 各数字含义

**生命路径数**（1-9 + 大师数）：
- 1: 独立开创、领导力
- 2: 合作、敏感、平衡
- 3: 表达、创意、社交
- 4: 稳定、实际、建设
- 5: 自由、变化、冒险
- 6: 责任、家庭、和谐
- 7: 内省、分析、灵性
- 8: 权力、物质、成就
- 9: 人道、智慧、完成
- 11: 直觉、灵性导师
- 22: 大师建造者
- 33: 大师教师

结合用户问题，侧重看：
- 性格 → life_path + personality
- 事业 → expression + life_path
- 感情 → soul_urge + personality
- 今年 → personal_year（1=新开始，9=完成期，5=变动期）

## 查引证

```
grep_classics("生命路径|灵数", system="numerology")
grep_rules("个人年|大师数字", system="numerology")
```

## 输出

- 数字命理相对"轻量"，适合作为辅助印证
- 重点看数字之间的呼应（如 life_path=1 + personal_year=1 → 强烈的开创能量叠加）
- 个人年周期（1-9 循环）是实用的时间框架
- 大师数字要特别说明其"双面性"（高振动 vs 压力）
