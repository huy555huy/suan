# 算 suan · 中西命理 AI Agent

> 算得准是地板，讲得活才是天花板。

按《中式命理 AI Agent 深度研究设计方案 v1.4》实现的端到端生产级系统：
中式（八字 / 紫微 / 易经 / 风水 / 流年）+ 西式（占星 / 塔罗 / 数字命理）
共 **8 路 Expert Agent 并行**研判，经 **VRP 反思镜验证 → 中西小综合 →
26-topic 交叉对齐 → 综合判官 → 流式叙事 → 合规审查** 输出。

驱动循环是一个真正的 **Planner-Executor**：LLM 每步决定下一个动作
（compute_chart / consult_expert / cross_link / reflect / synthesize /
ask_user / finalize），不是写死的固定流水线。

---

## 一、能力矩阵

| 子系统 | 计算引擎 | 流派 |
|---|---|---|
| 八字 | 纯 Python（农历 / 节气 / 真太阳时 / 干支 / 十神 / 神煞 / 大运 / 流年 / 格局 / 用神） | 子平派 |
| 紫微斗数 | 12 宫安星 / 14 主星 / 四化 / 大限 | 中州派 |
| 易经 / 六爻 / 梅花易数 | 数字 / 时间 / 铜钱起卦 + 京房纳甲 | 京房 + 邵雍 |
| 风水 | 玄空飞星 + 八宅命卦 | 三元玄空 + 八宅明镜 |
| 西方占星 | 自研行星历表（Meeus 简化）+ Placidus / Whole Sign 宫位 + 5 大相位 | 现代心理派 |
| 塔罗 | 78 张韦特牌 + 6 种牌阵 + 600+ 语境牌义 + crypto-random 抽牌 | RWS |
| 数字命理 | 生命数 / 表达数 / 灵魂数 / 性格数 / 个人年数 | 毕达哥拉斯 |
| **中西交叉验证** | 26 标准 topic 归一化 + consensus / divergence / complementary 标记 | — |
| **VRP 反思镜** | chart_ref 真实性硬校验 + 多档软反馈（RULE_NOVEL / SOURCE_SYNTHESIZED / SEMANTIC_WEAK / OVERCLAIM） | — |
| 知识库 / 规则引擎 | 81 条典籍 + 61 条规则 + BM25-lite 检索 + 安全 trigger DSL | — |
| 合规审查 | 红线词替换 / 强动作软化 / 医疗替换 / 自残触发心理援助热线 | — |

---

## 二、架构

```
浏览器 (v2.html / chat.html)
    │
    │  POST /api/v1/sessions      创建档案
    │  POST /sessions/{sid}/messages   投递问题
    │  GET  /sessions/{sid}/stream     SSE 长连接
    ▼
FastAPI (server.py)
    │
    ▼
Planner-Executor 主循环 ──┐
    │                     │ ① compute_chart   → Calculator (7 路盘面 · 纯 Python)
    │                     │ ② consult_expert  → 8 路 Expert Agent (DeepSeek)
    │                     │ ③ cross_link      → 中西交叉涌现
    │                     │ ④ reflect         → VRP 反思镜
    │                     │ ⑤ synthesize      → CN_Synth / WT_Synth / Aligner / Judge
    │                     │ ⑥ ask_user        → 暂停 SSE 等回答
    │                     │ ⑦ finalize        → 流式 Narrative + Safety
    └── 每步 yield 事件给 SSE，前端实时渲染
```

* **L1 计算层**：所有命理盘面由 `computation/*.py` 纯算法生成，**LLM 永不计算**
* **L2 知识层**：81 条公有领域典籍 + 61 条规则 + BM25-lite 检索 + 安全 trigger DSL（不用 eval）
* **L3 推理层**：8 路 Expert 并行，产出 `GroundedClaim`（chart_ref + rule_ref + source_ref 三元组）
* **VRP**：每条 claim 走 Verifier 反思镜——仅 `FACT_VIOLATION` 硬拒绝，其它 5 档作为软反馈喂回 LLM 自己决定是否修订
* **中西交叉**：CN_Synth / WT_Synth 互不可见对方结论，保证独立推理；再由 Aligner 做 26-topic 级对齐
* **不兜底**：LLM 不可达时直接报错给用户。"差兜底是不诚实的设计"

### 文件树

```
suan/
├── server.py                    # FastAPI 入口
├── core/
│   ├── config.py                # 加载 .env
│   ├── llm_client.py            # OpenAI 兼容 client（DeepSeek / Anthropic 代理 / OpenRouter）
│   ├── geo.py                   # 400+ 城市 + 省级 + 海外 + 智能模糊匹配
│   └── schemas.py               # 全局 Pydantic 模型
├── computation/                 # 7 个命理子系统 · 纯 Python · 无外部依赖
│   ├── calendar.py              # 干支 / 节气 / 真太阳时（VSOP87 简化）
│   ├── bazi.py / ziwei.py / yijing.py / fengshui.py
│   └── astrology.py / tarot.py / numerology.py
├── knowledge/
│   ├── classics.json            # 81 条公有领域典籍
│   ├── rules.json               # 61 条规则
│   ├── retrieval.py             # BM25-lite + 关键词
│   ├── rule_engine.py           # 安全 trigger DSL
│   ├── tarot_meanings.py        # 78 × 6 语境牌义
│   └── topics.py                # 26 标准 topic
├── agents/                      # 多 Agent 编排
│   ├── prompts.py               # 所有 system prompt
│   ├── planner.py               # Planner LLM（决定下一步动作）
│   ├── planner_orchestrator.py  # Planner-Executor 主循环（async generator）
│   ├── orchestrator.py          # 旧固定流水线（保留作 fallback 对比）
│   ├── classifier.py            # 问题分类
│   ├── expert.py                # 8 路 Expert 通用实现
│   ├── synth.py                 # CN_Synth / WT_Synth
│   ├── aligner.py               # 中西交叉验证
│   ├── judge.py                 # 综合判官
│   ├── narrative.py             # C 端 / 报告 两种风格
│   ├── verifier.py              # VRP 反思镜
│   ├── insights.py              # cross_link + reflect emergent actions
│   ├── safety.py                # 红线 + 心理风险
│   └── compute_dispatch.py      # 路由到 computation 模块
├── api/
│   └── routes.py                # 所有 HTTP 路由 + SSE
├── storage/
│   └── db.py                    # SQLite（会话 / 盘面 / 反馈 / 推理追溯）
├── web/                         # 前端
│   ├── v2.html                  # ★ 主 UI · 单文件 React 编辑设计杂志风（200KB）
│   ├── index.html               # 老落地页（保留）
│   ├── chat.html                # 老 SSE 对话（保留）
│   ├── report.html              # 深度研报（封面 / 目录 / 8 章节 / PDF 导出）
│   ├── journal.html             # 命理日记 · 召回判词
│   └── static/
│       ├── css/style.css        # 朱砂 / 黛青 / 鎏金 / 印章 / 引用块
│       ├── js/                  # astro_wheel / ziwei_wheel / tarot_flip / share_card / daily / journal / enhance
│       └── img/tarot/           # 78 张 RWS 韦特真扫描图（不入库 · scripts/download_tarot.sh 拉）
├── scripts/
│   └── download_tarot.sh        # 从 Wikimedia Commons 拉公有领域 RWS 塔罗（70MB）
├── data/                        # SQLite + 缓存（运行时生成 · 不入库）
└── 中式命理AI-Agent深度研究设计方案.md   # 4400 行原始设计文档
```

---

## 三、启动

### 1) 安装依赖

```bash
cd /Users/huy/suan
pip3 install -r requirements.txt
```

### 2) 配置 `.env`

```
LLM_BASE_URL="https://api.deepseek.com"
LLM_API_KEY="sk-..."
```

也支持任何 OpenAI 兼容端点（OpenRouter / Anthropic 代理 / 自部署 vLLM 等）。

### 3) 拉塔罗图（一次性，70MB）

```bash
bash scripts/download_tarot.sh
```

78 张 RWS 韦特牌从 Wikimedia Commons 拉到 `web/static/img/tarot/`。
Pamela Colman Smith 1909 绘，2022 进入美国公有领域。仓库不入库这些图。

### 4) 跑服务

```bash
python3 server.py
# 或带 reload：
# python3 -m uvicorn server:app --reload --port 8765
```

服务起在 `http://127.0.0.1:8765`。

### 5) 浏览器打开

* **`http://127.0.0.1:8765/v2`** — ★ 新版主 UI，编辑设计杂志风，React 单文件
* `http://127.0.0.1:8765/chat` — 老 SSE 对话（SaaS 风）
* `http://127.0.0.1:8765/report` — 深度研报生成器
* `http://127.0.0.1:8765/journal` — 命理日记

---

## 四、API

所有路径前缀 `/api/v1/`。

### 会话生命周期

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/sessions` | 创建/更新档案（生辰只入内存 · 不持久化） |
| `POST` | `/sessions/{sid}/messages` | 投递问题（首问或追问或 ask_user 的回答） |
| `GET`  | `/sessions/{sid}/stream` | SSE 长连接，接收 Planner 全过程事件 |
| `GET`  | `/sessions/{sid}` | 取已落库的会话完整结果 |
| `GET`  | `/sessions` | 历史列表（默认 50 条） |
| `DELETE` | `/sessions/{sid}` | 销毁单会话（内存 + DB） |
| `DELETE` | `/sessions` | 清空所有会话 |

### SSE 事件类型

Planner-Executor 主循环每步 yield 一个事件：

| 阶段 | 事件 |
|---|---|
| 启动 | `planner_start` / `input_caveats`（地名退化 / 时辰未知等提示） |
| 思考 | `planner_thinking` / `planner_thought`（含 thought / action / args） |
| 执行 | `planner_executing`（action ∈ compute_chart / consult_expert / cross_link / reflect / synthesize） |
| 排盘 | `chart_ready` / `charts_summary` |
| 专家 | `expert_done`（× N · headline + summary + confidence + verifier_stats） |
| 涌现 | `cross_link_insight` · `reflection` |
| 综合 | `synth_done`（× 2 · chinese + western） · `aligner_done` · `verdict_done` |
| 反问 | `ask_user`（暂停流，等下一条 message）· `waiting_user`（每 15s 心跳）· `user_replied` |
| 撰写 | `narrative_start` · `narrative_chunk`（流式）· `narrative`（replaced 标志 safety 改写过） |
| 收束 | `done` · `error` · `action_error` · `planner_max_steps` |

### 同步 / 工具接口

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/sessions/sync` | 一次性同步跑完整套（不推荐 · 用于深度研报 / 测试） |
| `POST` | `/charts` | 仅算盘面，不调 LLM（毫秒级） |
| `POST` | `/daily` | 当日运势卡 |
| `POST` | `/knowledge/search` | BM25-lite 典籍 / 规则检索 |
| `POST` | `/feedback` | 评分 / 标签 / 自由文本 |
| `GET`  | `/health` | 健康检查 |

---

## 五、端到端实测

### 测试用例：陈书雅，1991-08-15 14:30 北京，问"今年事业怎么走？"

**计算层（毫秒级 · 纯 Python）**
* 八字四柱：辛未 · 丙申 · 丁巳 · 丁未；日主丁火；正财格；用神木；神煞驿马 / 华盖
* 紫微：水二局 / 命宫巳 / 化禄巨门、化忌文昌
* 占星：太阳狮子 21.95° · ASC 射手 9° · 月亮天秤 · 蛾眉月 · 9 宫群星
* 数字命理：生命数 7 · 表达数 1 · 个人年 6

**推理层（约 60-90 秒 · DeepSeek）**
* 5 路 Expert 并行：bazi / ziwei / liunian / astrology / tarot
* CN_Synth / WT_Synth 各自独立
* Aligner 找出 2 项双重共识 + 2 项分歧（关键涌现：中式"火旺喜金水" × 西式"9 宫木火" → 综合为"以教育为本，以科技为器，以学问为远方"）
* Judge 给整体置信度 high
* Narrative 流式输出 1500+ 字克制温暖文本，显式呈现共识 / 分歧 / 建议 / 谨慎

---

## 六、设计哲学

> 这是一个 Agent，不是一个会说话的规则引擎。

| 维度 | 决策 |
|---|---|
| 算盘起卦 / 行星位置 / chart_ref 真实性 / Schema / 红线 / 合规 | **必须硬** |
| 规则怎么应用 / 典籍怎么综合 / 跨系统怎么联结 / 推理流程怎么走 / 何时追问 / 流派如何取舍 | **必须软** |

* **VRP 反思镜**：除 FACT_VIOLATION 外，所有档位作为反思反馈喂回 LLM，由 LLM 自己决定是否修订
* **规则参考化**：规则引擎的输出是参考材料，不是命令；LLM 偏离规则时进 deviation_log 由命理师审核 → 数据飞轮的真实引擎
* **跨系统涌现**：Aligner 不是 topic 表对齐工具，而是"识别中式 / 西式同时点亮的强信号"的发现器
* **不兜底**：LLM 不可达时报错给用户。差的兜底比报错更不诚实
* **Planner 是真的 Planner**：LLM 每一步独立决定下一个动作，不是固定流水线

---

## 七、合规与边界

* 不输出 100% / 一定 / 必然 / 保证 / 改命 / 改运 等承诺性词汇 → 强制软化
* 不给医学诊断 → "建议咨询专业医生"
* 自残 / 自杀关键词 → 立即切到心理援助热线（北京 010-82951332 · 全国 400-161-9995）
* 强行动建议（建议离婚 / 辞职 / 报复）→ 软化或删除
* 所有输出末尾自动追加免责声明

---

## 八、限制与未实现

为了在合理时间内做出生产级 v1，以下采用**可工作的简化**，与原设计文档差异：

* **行星历表**：Meeus 简化算法（±2-5°），未购 Swiss Ephemeris Pro。够 LLM 解读，不够择日 / 卜卦占星精度
* **知识库**：81 条典籍 + 61 条规则。设计文档目标 Stage 0 是 300-500 条，需命理师标注
* **检索**：BM25-lite + 关键词 + topic 加权。未接 BGE-M3 + Qdrant + Neo4j 三路融合
* **部署**：SQLite + 内存。设计文档目标是 PostgreSQL + KMS + Redis + Qdrant + Neo4j + Elasticsearch
* **路由**：单一 OpenAI 兼容端点。生产应按 `user.region + consent_cross_border` 路由境内 / 境外
* **未做**：反幻觉测试套件 / 在线监控 / 数据飞轮 / B 端白标导出 / 流年推送 / 古文 LoRA

完整目标见 `中式命理AI-Agent深度研究设计方案.md`。

---

## 九、致谢

* **计算**：Meeus《Astronomical Algorithms》、《滴天髓》《三命通会》《子平真诠》《紫微斗数全书》《周易》《沈氏玄空学》《Pictorial Key to the Tarot》
* **LLM**：DeepSeek（默认）/ Anthropic / OpenAI 兼容端点
* **塔罗**：Pamela Colman Smith 1909 绘 RWS 韦特塔罗（Wikimedia Commons · 2022 进入美国公有领域）
* **前端 v2**：React 18 + Babel standalone · 单文件 SPA · Noto Serif SC + EB Garamond + JetBrains Mono · oklch() 色彩空间
* **前端老页**：Tailwind CSS + Alpine.js

---

*本系统输出仅供文化参考与自我反思。重大人生决定请结合自身判断与专业人士意见。*
