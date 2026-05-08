# 算 suan · 中西命理 AI Agent

> 严肃的工程，敬畏的工艺。

按《中式命理 AI Agent 深度研究设计方案 v1.4》实现的端到端生产级系统。
中式（八字 / 紫微 / 易经 / 风水 / 流年）+ 西式（占星 / 塔罗 / 数字命理）共 8 路 Expert Agent 并行研判，
经独立的中西小综合 → 中西交叉验证 Aligner → 综合判官 → Narrative → 合规审查输出。

**重点不是"算得准"，而是"讲得活、看得透、问得深、合得对"** —— 算得准是地板，agency 才是天花板。

---

## 一、能力矩阵

| 子系统 | 计算引擎 | 流派 | 已实现 |
|---|---|---|---|
| 八字 | 纯 Python（农历 / 节气 / 真太阳时 / 干支 / 十神 / 神煞 / 大运 / 流年 / 格局 / 用神） | 子平派 | ✅ |
| 紫微斗数 | 12 宫安星 / 14 主星 / 四化 / 大限 | 中州派 | ✅ |
| 易经 / 六爻 / 梅花易数 | 数字 / 时间 / 铜钱起卦 + 京房纳甲 | 京房 + 邵雍 | ✅ |
| 风水 | 玄空飞星 + 八宅命卦 | 三元玄空 + 八宅明镜 | ✅ |
| 西方占星 | 自研行星历表（Meeus 简化）+ Placidus / Whole Sign 宫位 + 5 大相位 | 现代心理派 | ✅ |
| 塔罗 | 78 张韦特牌 + 6 种牌阵 + 600+ 语境牌义 + cryptographically random 抽牌 | RWS | ✅ |
| 数字命理 | 生命数 / 表达数 / 灵魂数 / 性格数 / 个人年数 | 毕达哥拉斯 | ✅ |
| **中西交叉验证** | 26 标准 topic 归一化 + consensus / divergence / complementary 标记 | — | ✅ |
| **VRP 反思镜验证** | chart_ref 真实性硬校验 + 多档软反馈（RULE_NOVEL / SOURCE_SYNTHESIZED / SEMANTIC_WEAK / OVERCLAIM） | — | ✅ |
| 知识库 / 规则引擎 | 81 条典籍 + 61 条规则 + BM25-lite 检索 + 安全 trigger DSL | — | ✅ |
| 合规审查 | 红线词替换 / 强动作软化 / 医疗替换 / 自残触发心理援助热线 | — | ✅ |

---

## 二、架构

```
浏览器 ──→ FastAPI (server.py) ──→ Orchestrator ──→ ┌── Calculator (7 路盘面)
                                                    ├── Classifier (Haiku 轻量)
                                                    ├── 8 Expert Agents (并行 · DeepSeek)
                                                    ├── Verifier (反思镜模式)
                                                    ├── CN_Synth + WT_Synth (各自独立)
                                                    ├── Cross-System Aligner (产品级核心)
                                                    ├── Synthesis Judge
                                                    ├── Narrative
                                                    └── Safety
```

* **L1 计算层**：所有命理盘面由 `computation/*.py` 纯 Python 算法库精确生成，**LLM 永不计算**
* **L2 知识层**：`knowledge/classics.json`（81 条公有领域典籍）+ `knowledge/rules.json`（61 条规则）+ BM25-lite 检索
* **L3 推理层**：8 路 Expert Agent 并行推理，产出 `GroundedClaim`（chart_ref + rule_ref + source_ref 三元组）
* **VRP**：每条 claim 走 Verifier 反思镜 — 仅 FACT_VIOLATION 硬拒绝，其它 5 档软反馈
* **中西交叉**：CN_Synth 与 WT_Synth 互不可见对方结论，保证两套体系真正独立推理；再由 Aligner 做 topic 级对齐
* **Planner-Executor**（已留出口）：通过 `ENABLE_PLANNER=1` 切换旗舰模式（默认走稳态固定流水线）

### 文件树

```
suan/
├── server.py                    # FastAPI 入口
├── core/
│   ├── config.py                # 加载 .env
│   ├── llm_client.py            # OpenAI 兼容 client（DeepSeek / Anthropic 代理 / OpenRouter / ccvibe 等）
│   └── schemas.py               # 全局 Pydantic 模型
├── computation/                 # 7 个命理子系统 · 纯 Python · 无外部依赖
│   ├── calendar.py              # 干支 / 节气 / 真太阳时（VSOP87 简化）
│   ├── bazi.py / ziwei.py / yijing.py / fengshui.py
│   └── astrology.py / tarot.py / numerology.py
├── knowledge/
│   ├── classics.json            # 81 条公有领域典籍
│   ├── rules.json               # 61 条规则
│   ├── retrieval.py             # BM25-lite + 关键词
│   ├── rule_engine.py           # 安全 trigger DSL（不用 eval）
│   ├── tarot_meanings.py        # 78×6 语境牌义
│   └── topics.py                # 26 标准 topic
├── agents/                      # 多 Agent 编排
│   ├── prompts.py               # 所有 system prompt
│   ├── orchestrator.py          # 主流水线（async generator yield 事件）
│   ├── classifier.py            # 问题分类
│   ├── expert.py                # 8 路 Expert 通用实现
│   ├── synth.py                 # CN_Synth / WT_Synth
│   ├── aligner.py               # 中西交叉验证
│   ├── judge.py                 # 综合判官
│   ├── narrative.py             # C 端 / 报告 / Copilot 三种风格
│   ├── verifier.py              # VRP 反思镜
│   ├── safety.py                # 红线 + 心理风险
│   ├── compute_dispatch.py      # 路由到 computation 模块
│   └── fallback.py              # LLM 不可达时的规则兜底（设计文档外，工程容错）
├── api/
│   └── routes.py                # 所有 HTTP 路由
├── storage/
│   └── db.py                    # SQLite（会话 / 盘面 / 反馈 / 推理追溯）
├── web/                         # 4 个页面 + 静态资源
│   ├── index.html               # 落地页
│   ├── chat.html                # C 端对话（SSE 流式）
│   ├── report.html              # 深度研报（封面 / 目录 / 8 章节 / 中西对齐板 / PDF 导出）
│   ├── copilot.html             # B 端 Copilot（客户管理 / 草稿 / 知识速查）
│   └── static/
│       ├── css/style.css        # 800+ 行命理元素 CSS（朱砂 / 黛青 / 鎏金 / 印章 / 引用块）
│       ├── js/app.js            # 600+ 行 Alpine.js 应用逻辑（SSE / Mock / 三种页面共享）
│       └── img/                 # 6 个 SVG（logo / 八卦 / 占星轮 / 塔罗背 / 牌框）
├── data/                        # SQLite + 缓存
└── 中式命理AI-Agent深度研究设计方案.md   # 4400 行原始设计方案
```

---

## 三、启动

### 1) 安装依赖

```bash
cd /Users/huy/suan
pip3 install -r requirements.txt
```

### 2) 配置 .env

`.env` 已配置好 DeepSeek 端点：

```
LLM_BASE_URL="https://api.deepseek.com"
LLM_API_KEY="sk-..."
```

也支持任何 OpenAI 兼容端点（OpenRouter / Anthropic 代理 / 自部署 vLLM 等）。

### 3) 跑服务

```bash
python3 server.py
# 或 uvicorn 模式：
# python3 -m uvicorn server:app --reload --port 8765
```

服务起在 `http://127.0.0.1:8765`。

### 4) 浏览器打开

* `http://127.0.0.1:8765/` — 落地页
* `http://127.0.0.1:8765/chat` — C 端对话
* `http://127.0.0.1:8765/report` — 深度研报生成器
* `http://127.0.0.1:8765/copilot` — B 端 Copilot

### 5) 不启动服务也能预览前端

`web/index.html` / `chat.html` / `report.html` / `copilot.html` 直接 `file://` 打开即可（Tailwind / Alpine 走 CDN，会自动检测后端状态）。

---

## 四、API

### `POST /api/v1/sessions`
注册档案（前端用）。Body: `{name, gender, date, time, place, scenario}`。返回 `{session_id}`。

### `POST /api/v1/sessions/{sid}/messages`
投递问题。Body: `{text}`。

### `GET /api/v1/sessions/{sid}/stream`
SSE 流式接收所有 Agent 事件。事件类型：
* `start` / `phase` / `classifier_done` / `chart_ready` / `charts_summary`
* `expert_done` (× N，每个 expert 完成时一次)
* `verifier_log` (× N)
* `synth_done` (× 2，中式 + 西式)
* `aligner_done` (双系统时；单系统时为 `aligner_skipped`)
* `verdict_done` / `narrative` / `done`

### `POST /api/v1/sessions/sync`
同步执行整套流程并一次性返回完整 JSON。Body: `{profile, question}`。
返回结构：`{session_id, narrative, verdict, charts, expert_opinions, cn_synth, wt_synth, cross_alignment, trace}`。
深度研报和 B 端草稿用此接口。

### `POST /api/v1/charts`
**仅算盘面**，不调 LLM（毫秒级返回）。前端用户输入档案后立即展示盘面。

### 历史 / 反馈
* `GET /api/v1/sessions` — 历史会话列表
* `GET /api/v1/sessions/{sid}` — 单会话完整资料
* `POST /api/v1/feedback` — 评分 / 标签 / 自由文本

---

## 五、端到端实测

### 测试用例：陈书雅，1991-08-15 14:30 北京，问"今年事业怎么走？"

**计算层（毫秒级）**：
* 八字四柱：辛未 · 丙申 · 丁巳 · 丁未；日主丁火；正财格；用神木；神煞驿马 / 华盖
* 紫微：水二局 / 命宫巳 / 化禄巨门、化忌文昌
* 占星：太阳狮子 21.95° · ASC 射手 9° · 月亮天秤 · 蛾眉月 · 9 宫群星
* 数字命理：生命数 7 · 表达数 1 · 个人年 6
* 触发规则：8 条八字 + 5 条占星 + 1 条数字命理 + 2 条紫微

**推理层（约 90-150 秒）**：
* 5 路 Expert Agent 并行推理（bazi / ziwei / liunian / astrology / tarot）
* CN_Synth 与 WT_Synth 各自独立
* Aligner 找到 2 项双重共识 + 2 项分歧（关键涌现：中式"火旺喜金水" vs 占星"9 宫木火" → 综合为"用科技赋能教育"的交叉点）
* Judge 给整体置信度 high
* Narrative 输出 1500+ 字克制温暖文本，显式呈现共识 / 分歧 / 建议 / 谨慎

**SSE 事件流**：30 个事件、12 种类型、约 113 秒跑完。

---

## 六、设计哲学（来自原 v1.4 设计文档）

> 这是一个 Agent，不是一个会说话的规则引擎。

| 维度 | 决策 |
|---|---|
| 算盘起卦 / 行星位置 / chart_ref 真实性 / Schema / 红线 / 合规 | **必须硬** |
| 规则怎么应用 / 典籍怎么综合 / 跨系统怎么联结 / 推理流程怎么走 / 何时追问 / 流派如何取舍 | **必须软** |

* **VRP 反思镜**：除 FACT_VIOLATION 外，所有档位作为反思反馈喂回 LLM，由 LLM 自己决定是否修订
* **规则参考化**：规则引擎的输出是参考材料，不是命令；LLM 偏离规则时进 deviation_log 由命理师审核 → 数据飞轮的真实引擎
* **跨系统涌现**：Aligner 不是 topic 表对齐工具，而是"识别中式 / 西式同时点亮的强信号"的发现器

---

## 七、合规与风险边界

* 不输出 100% / 一定 / 必然 / 保证 / 改命 / 改运 等承诺性词汇 → 强制软化
* 不给医学诊断，触发"建议咨询专业医生"
* 用户提及自残 / 自杀关键词时 → 立即切到心理援助热线（北京 010-82951332 · 全国 400-161-9995）
* 强行动建议（建议离婚 / 辞职 / 报复）→ 软化或删除
* 所有输出末尾自动追加免责声明

---

## 八、限制与未实现

为了在合理时间内完成生产级 v1，以下采用了**可工作的简化方案**，与原设计文档差异：

* 计算层：未购买 Swiss Ephemeris Professional License — 用 Meeus 简化算法（行星精度 ±2-5°，足够 LLM 解读，不够择日 / 卜卦占星精度）
* 知识库：81 条典籍 + 61 条规则（设计文档目标 Stage 0 是 300-500 条，需命理师标注产出）
* 嵌入：BM25-lite + 关键词 + topic_tags 加权（无 BGE-M3 + Qdrant + Neo4j 三路融合）
* 部署：SQLite + 内存（设计文档目标是 PostgreSQL + KMS + Redis + Qdrant + Neo4j + Elasticsearch）
* 双轨路由：单一 OpenAI 兼容端点（生产应按 user.region + consent_cross_border 路由境内 / 境外）
* 反幻觉测试套件 / 在线监控 / 数据飞轮 / B 端白标导出 / 流年推送 / 古文 LoRA — 留作未来工作

完整设计目标见 `中式命理AI-Agent深度研究设计方案.md`。

---

## 九、致谢

* 计算引擎：Meeus《Astronomical Algorithms》、《滴天髓》《三命通会》《子平真诠》《紫微斗数全书》《周易》《沈氏玄空学》《Pictorial Key to the Tarot》
* LLM：DeepSeek（默认）/ Anthropic Claude / OpenAI GPT 兼容端点
* 前端：Tailwind CSS + Alpine.js + 系统字体（Source Han Serif / PingFang / Lora / Inter）

---

*本系统输出仅供文化参考与自我反思。重大人生决定请结合自身判断与专业人士意见。*
