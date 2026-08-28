# 教育智能客服系统

面向在线教育行业的智能客服系统：识别学员意图，提供课程咨询、订单查询、学习进度查询等信息检索能力，并通过多轮任务型对话完成退款申请、工单提交等售后流程。

本项目由三个子项目组成：

| 目录 | 说明 | 技术栈 | 端口 |
|---|---|---|---|
| `customer-service-frontend` | 前端演示/调试页（含文本聊天与数字人） | Vue 3 + Vite + `lm-avatar-chat-sdk` | 5174 |
| `customer-service-backend` | 智能客服 Agent（对话引擎 / 意图路由 / 多轮流程） | FastAPI + LangChain + SQLAlchemy | 18082 |
| `edu-data` | 在线教育业务数据服务（课程 / 订单 / 学习 / 工单等 12 大模块） | FastAPI + SQLAlchemy + MySQL | 8000 |

## 架构与调用链路

```text
 浏览器前端 (5174)
     │  /api/chat、/api/chat/stream、/api/chat/history、/api/chat/session...
     ▼
 customer-service-backend (18082)  ──►  LLM（OpenAI 兼容，qwen3.7-plus）
     │  /api/v1/**（X-User-Id 标识当前学员）
     ▼
 edu-data (8000)  ──►  MySQL `edu`
     │
 back 端自身状态 ──►  MySQL `customer_service`（dialogue_states 持久化会话）
```

- 前端通过 Vite 代理将 `/api`、`/ws`、`/health` 转发到后端（18082），将 `/api/v1` 转发到 edu-data（8000）。
- 后端使用 LangChain 调用 LLM 进行意图路由；路由结果决定进入 **task（业务任务）**、**knowledge（信息检索）** 或 **chitchat（闲聊）** 轨道。
- 后端的业务动作（查订单 / 查进度 / 退款 / 工单）通过 HTTP 调用 edu-data 接口。

## 快速启动

### 前置条件

- Python ≥ 3.12（后端与 edu-data 均使用 `uv` 管理依赖）
- Node.js（前端）
- MySQL 数据库：`edu` 与 `customer_service` 两个库
- 一个 OpenAI 兼容的 LLM 接口地址与 Key（后端 `.env` 中配置）

3 个 `.env` 都已包含本机配置，按需修改：

| 文件 | 关键项 |
|---|---|
| `edu-data/.env` | `DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME=edu`、`APP_PORT=8000` |
| `customer-service-backend/.env` | `LLM_*`（模型 / 地址 / Key）、`EDU_API_BASE_URL=http://127.0.0.1:8000`、`DATABASE_URL=mysql+aiomysql://.../customer_service`、`APP_PORT=18082` |

### 1) 启动 edu-data（教育数据服务）

```bash
cd edu-data
uv sync
uv run init_db.py                    # 初始化数据库表
uv run -m generate.main --profile full   # 灌入业务样本数据
uv run -m app.main                   # 启动，端口 8000
```

启动后可访问 Swagger：`http://127.0.0.1:8000/docs`。

### 2) 启动客服后端

```bash
cd customer-service-backend
uv sync
python -m atguigu.main               # 启动，端口 18082
```

### 3) 启动前端

```bash
cd customer-service-frontend
npm install
npm run dev                          # 启动，端口 5174
```

浏览器访问 `http://127.0.0.1:5174`，在页面顶部输入 `sender_id`（纯数字会作为 edu-data 的 `X-User-Id`，非数字使用后端 `EDU_USER_ID` 兜底）。

## 后端接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/chat` | 非流式对话，返回完整回复 |
| POST | `/api/chat/stream` | SSE 流式对话（逐字返回） |
| GET | `/api/chat/history?sender_id=` | 拉取当前会话历史消息 |
| GET | `/api/chat/state?sender_id=` | 查询当前激活流程、已收集槽位、被挂起流程 |
| POST | `/api/chat/session?sender_id=&close_current=` | 显式开启新会话 |
| GET | `/api/chat/sessions?sender_id=` | 列出全部历史会话摘要 |
| POST | `/api/chat/session/switch?sender_id=&session_id=` | 切换 / 恢复到一个历史会话 |
| GET | `/`、`/test` | 健康检查与示例接口 |

> 说明：`/api/chat/session` 的 `close_current` 默认 `true`，会关闭当前会话并新建；若期望“保留当前会话另起一个”，传 `close_current=false`。

## 业务对话流程

后端通过 `flow_config/user_flows.yml` 以配置方式声明流程，新增任务流程无需改核心代码：

- `onboarding` 欢迎引导
- `order_status_query` 订单状态查询
- `learning_progress_query` 学习进度查询
- `refund_application` 退款申请
- `ticket_submission` 工单提交（售后 / 投诉 / 退款）
- `human_handoff` 人工客服转接

系统流程位于 `flow_config/system_flows.yml`，负责过场白、槽位追问、中断/恢复/取消等对话管控。

## 知识库与信息检索

- FAQ / 平台规则 / 使用指南数据存放在 `customer-service-backend/knowledge_base/faq_entries.json`，可直接增删改。
- `FaqDefaultProvider` 检索 FAQ（政策）类条目；`RagDefaultProvider` 跨 FAQ / 规则 / 指南做关键词检索，后续可无缝升级为向量检索。
- 课程、订单、班次等实时业务数据由后端调用 edu-data 获取，保证信息基于最新数据。

## 可观测性

- 后端每次对话都会输出一条带 `trace_id`（即 `message_id`）的轨迹日志，覆盖：turn 开始、意图 / 轨道路由（task / knowledge / chitchat）、澄清、动作执行与耗时、回复结果与整轮耗时。
- 日志格式示例：`[trace=abc123] turn_start sender_id='281' type='text' text='...'`。
- 可在启动日志（`simserver.log`）或 stdout 中按 `trace=` 聚合检索一次对话的完整链路。

## 可靠性

- 会话状态读取失败时降级为全新状态，保存失败时仅记录告警，均不影响本次回复返回。
- 对外部 edu-data 的调用设置了 15 秒超时，并对失败记录告警日志。

## 其它说明

- 前端数字人（avatar）依赖 `/api/avatar/session`、`/ws/avatar/chat` 等接口，当前后端尚未实现（需求文档未强制要求，且需第三方灵眸凭证）。纯文本对话链路不受影响。
- 数据库连接地址 `192.168.10.188:3307` 为示例 VM，请按实际环境修改。
- 仓库未纳入 Git 管理；涉及真实 LLM Key 与数据库密码，请勿提交到公开仓库。
