# LangGraph Multi-Agent SQL Analyst

面向结构化业务数据的自然语言分析系统。用户用自然语言提出分析需求，由 **Supervisor Agent** 动态调度 **SQL Agent**、**Analysis Agent**、**Visualization Agent** 与 **Reviewer Agent**，自动完成 SQL 生成与执行、数据分析、图表生成和结果校验，形成「生成与验证分离 + 失败重试闭环」的多 Agent 工作流。

> 本仓库**只有后端、无前端**。所有演示都在编辑器/终端里完成，不依赖浏览器页面。

## 架构总览

```
User
  │
  ▼
Supervisor Agent  ──▶ 任务理解 → 任务拆解 → 调度
  │
  ├──────────────┬──────────────┐
  ▼              ▼              ▼
SQL Agent    Analysis      Chart Agent
(SubGraph)     Agent
  │              │              │
  └──────────────┼──────────────┘
                 ▼
          Reviewer Agent
          ┌───────┴────────┐
        不通过             通过
          │                │
          ▼                ▼
    指定 Agent 重试       Final Agent
                            │
                            ▼
                          END
```

核心闭环（面试重点）：`Reviewer` 发现问题 → `Supervisor` → 指定 `Agent` 重试 → `Reviewer` 复检 → `Final`。

## 功能与技术点

| 能力 | 实现 |
| --- | --- |
| Multi-Agent | Supervisor / SQL / Analysis / Chart / Reviewer 五类职责分离 Agent |
| 动态工作流 | `StateGraph` + `Conditional Edge` + Loop，按 `State` 动态路由 |
| 共享状态 | 显式 `AnalysisState`（业务字段，而非只堆 `messages`） |
| SQL SubGraph | 嵌套子图：`schema → generate → validate → execute → rewrite` |
| SQL 自动修复 | 数据库错误反馈 → 重写 SQL → 重试（`MAX_SQL_RETRIES` 限流） |
| 安全控制 | 只读校验：仅允许 `SELECT/WITH`，拦截 `INSERT/UPDATE/DELETE/DROP` 等 |
| 敏感拦截 | 检测 `customer_email/salary/phone` 等字段，触发 human-in-the-loop |
| Reviewer 校验 | 对 SQL、结果、分析结论、图表做一致性校验，独立于生成 |
| Structured Output | Analysis / Reviewer / Chart 返回 JSON |
| Checkpoint | `InMemorySaver` 按 `thread_id` 持久化 Graph State |
| Human-in-the-loop | `interrupt()` 暂停敏感 SQL，`Command(resume=...)` 恢复 |
| CLI 演示 | 终端实时打印 Agent 执行过程、SQL、数据表、图表路径与结论（无前端） |
| 追踪 | LangSmith tracing（`.env` 开启） |

## 目录结构

```
multi-agent-sql-analyst/
├── app/
│   ├── agents/            # 5 个 Agent + mock LLM 应答器
│   ├── graph/             # state / router / sql_subgraph / workflow
│   ├── tools/             # sql_tools / analysis_tools / chart_tools
│   ├── database/          # connection / schema.sql / seed
│   ├── api/               # FastAPI 路由（analyze / approve，可选）
│   ├── llm.py             # LLM 工厂（mock / openai / fake）
│   ├── config.py
│   └── main.py
├── data/sales.db          # 生成的销售数据库（约 7 万订单）
├── charts/                # 生成的图表 PNG（可在编辑器直接打开）
├── scripts/demo.py        # CLI 演示（唯一入口，无前端）
├── tests/                 # test_sql / test_analysis_tools / test_graph
├── requirements.txt
├── .env.example
├── Dockerfile
└── docker-compose.yml
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. CLI 演示（推荐，无前端/浏览器）

默认 mock LLM，无需 API Key。全部在编辑器终端里完成：

```bash
python -m scripts.demo                      # 跑全部 10 个问题
python -m scripts.demo 6                    # 只跑第 6 题
python -m scripts.demo 10 --interactive     # 演示 human-in-the-loop 终端审批
```

每题实时打印：

```text
[Supervisor Agent] 任务拆解 -> ...
[SQL Agent] 生成 SQL -> ...
[Analysis Agent] 结论 -> ...
[Chart Agent] 图表 -> /charts/xxx.png
[Reviewer Agent] 通过/未通过 -> ...
[Final Agent] 报告生成完成

[SQL]     生成的只读 SQL
[数据]    查询结果表格
[图表]    图表 URL（对应 charts/ 目录下的本地 PNG 文件，可直接打开）
[分析结论] 摘要 + 关键发现 + 异常
[最终报告] 最终答案
[校验]    Reviewer 判定
```

### 3. （可选）JSON API

仅用于程序化调用，不面向页面：

```bash
uvicorn app.main:app --reload --port 8000
```

接口文档：<http://localhost:8000/docs>

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/analyze` | 同步分析（返回 JSON） |
| POST | `/api/approve` | human-in-the-loop 审批恢复 |

示例请求：

```json
POST /api/analyze
{"query": "分析2025年销售额下降最明显的月份，并生成图表", "thread_id": "user-001"}
```

### 4. 使用真实 LLM

复制 `.env.example` 为 `.env`，配置：

```ini
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.deepseek.com/v1   # 可选
LLM_MODEL=deepseek-chat
```

### 5. 测试

```bash
pytest -q
```

## 数据库

6 张表：`customers`、`products`、`regions`、`employees`、`orders`、`order_items`。种子脚本生成 **2024–2025 约 7 万条订单**，含月度季节性、区域/产品分布，并刻意埋入 **2025 年 8 月销售回落**（华东 -23%、产品A -18%），便于演示「下降原因」类分析。

重新生成数据库：

```bash
python -m app.database.seed
```

## 安全模型

- 数据库连接仅授予只读权限。
- `validate_sql` 先去注释/字符串再校验关键字，仅放行 `SELECT/WITH`。
- 查询结果截断（前 50 行），防止上下文被灌爆。
- 敏感列（如 `customer_email`）命中即触发人工确认。

## 常见问题（面试）

- **为什么用 LangGraph 而不是 LangChain Agent？** 需要多 Agent 共享状态、动态路由、循环重试与人工干预，Graph 层显式编排，Agent 只作为节点内部实现。
- **Agent 之间如何共享数据？** 通过 `AnalysisState`，SQL Agent 写入 `sql_query/sql_result`，Analysis Agent 从中读取。
- **SQL 错了怎么办？** 执行失败把错误写入 `sql_error`，经条件边重新进入 SQL Agent 自动改写，受 `MAX_SQL_RETRIES` 限制。
- **为什么需要 Reviewer？** LLM 生成正确不等于分析正确，Reviewer 独立校验，形成生成与验证分离。
- **Multi-Agent 与单 Agent Tool Calling 区别？** 单 Agent 决策仍由同一 Agent 承担；本项目把职责拆给独立 Agent，由 Supervisor 协调，可针对不同任务使用不同 Prompt/Tool/模型。

## Docker

```bash
docker-compose up --build
```
