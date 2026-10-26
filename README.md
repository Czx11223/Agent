# 智能问诊导诊 Agent 🩺

基于 **AgentScope** 与 **DeepSeek/大模型** 构建的多轮智能预问诊导诊系统。患者以自然语言描述不适后，系统通过多轮追问逐步采集「主诉 / 部位 / 持续时间 / 伴随症状 / 既往史 / 过敏史」六要素，自动生成结构化预问诊报告，并给出 **Top3 就诊科室推荐** 与 **急重症拦截** 提示。

> 定位：预问诊医助。**严禁诊断、不开药、不给治疗方案**，仅收集症状信息并指引就诊方向。

---

## 目录

- [功能特性](#功能特性)
- [技术栈](#技术栈)
- [系统架构](#系统架构)
- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [一键启动 / 停止](#一键启动--停止)
- [接口文档](#接口文档)
- [目录结构](#目录结构)
- [评测与指标](#评测与指标)
- [配置说明](#配置说明)

---

## 功能特性

- **多轮自然对话问诊**：LLM 驱动，按优先级追问（主诉→部位→时间→伴随→既往→过敏），临近收尾自动给出安抚语。
- **结构化预问诊报告**：后台自动整理六大要素，生成清晰、可读的报告。
- **Top3 科室推荐**：基于症状关键词映射，推荐最可能的 3 个就诊科室。
- **急重症识别与拦截**：命中急重症关键词（如剧烈胸痛、呼吸困难、昏迷、大出血等）立即提示就医，不继续常规追问。
- **拒答处理**：用户索要诊断 / 开药时，明确拒绝并给出免责说明。
- **指代消解**：支持「这里 / 那里也是这里疼」等地点指代绑定到上文部位。
- **容错降级**：未配置 LLM 或调用失败时，自动回退本地规则，保证多轮追问与报告不中断。
- **用户体系**：JWT 登录/注册，多会话历史管理与报告留存。

---

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | React 18 · TypeScript · Vite 5 · TailwindCSS 3 · Ant Design 5 |
| 后端 | FastAPI 0.143 · Uvicorn · Python 3.12+ |
| Agent 框架 | **AgentScope 2.0.10**（`Msg` 消息模型编排多轮对话） |
| LLM 接入 | SiliconFlow 平台 · `deepseek-ai/DeepSeek-V3`（OpenAI 兼容接口，httpx 直连，SSE 流式） |
| 数据存储 | SQLite（`app.db`） |
| 认证 | python-jose（JWT） |

---

## 系统架构

```
┌────────────────────────────────────────────┐
│              前端 (Vite, :5173)             │
│  AuthPage / ChatPage / ChatWindow /         │
│  ConversationList / ReportPanel             │
└───────────────┬────────────────────────────┘
                │  /api  代理
┌───────────────▼────────────────────────────┐
│            后端 (FastAPI, :8000)            │
│  routers/auth·chat·conversations·reports   │
│  services/agent_service  (SSE 流式)         │
│  ┌──────────────────────────────────────┐   │
│  │   PreConsultAgent (AgentScope 编排)  │   │
│  │   指代消解 · 槽位抽兜底 · 降级规则     │   │
│  └──────────────────────────────────────┘   │
│  db (sqlite) · llm/client (httpx+SSE)       │
└───────────────┬────────────────────────────┘
                │
       ┌────────▼────────┐
       │ SiliconFlow API │  deepseek-ai/DeepSeek-V3
       └─────────────────┘
```

核心编排位于：`backend/app/agent/pre_consult_agent.py`（AgentScope `Msg` 维护消息记忆与槽位状态）；`backend/app/agent/dept_map.py`（科室 关键词 映射、急重症识别、指代部位与既往史抽取、口语归一）。

---

## 环境要求

- **Python 3.12+**（后端，必须，满足任务书要求）
- **Node.js 18+**（前端）
- npm / pip（网络需可访问 pip 镜像与 SiliconFlow API）

---

## 快速开始

> 以下路径均相对项目根目录 `智能问诊导诊Agent_交付物/智能问诊导诊Agent/`。

### 1. 后端

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

启动后：

- 接口文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/health

### 2. 前端

```bash
cd frontend
npm install
npm.cmd run dev
```

打开 http://localhost:5173（`/api` 已代理到后端）。

---

## 一键启动 / 停止

在**项目根目录**双击即可（已包含前后端两条命令的封装）：

| 脚本 | 作用 |
|------|------|
| `一键启动.bat` | 校验 `.venv` 存在后，分别打开后端(8000)、前端(5173)两个独立运行窗口 |
| `一键停止.bat` | 按端口 8000 / 5173 定位进程并强杀整棵进程树，同时关闭残留运行窗口 |

> 说明：`.bat` 不受 PowerShell 执行策略影响，可直接双击运行。

---

## 接口文档

启动后端后，Swagger 交互式文档位于：http://127.0.0.1:8000/docs

主要接口（`/api/v1`）：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/register` | 注册用户 |
| POST | `/auth/login` | 登录，返回 JWT |
| GET  | `/conversations` | 会话列表 |
| POST | `/conversations` | 新建会话 |
| GET  | `/conversations/{id}/messages` | 会话消息 |
| POST | `/chat/stream` | 问诊对话（SSE 流式返回 token / comfort / emergency / report 事件） |
| GET  | `/reports/{id}` | 预问诊报告 |

---

## 目录结构

```
├─ backend/
│  ├─ app/
│  │  ├─ main.py            # FastAPI 入口，'/' 重定向到 /docs
│  │  ├─ config.py          # 环境配置（读取 backend/.env）
│  │  ├─ agent/
│  │  │  ├─ pre_consult_agent.py  # AgentScope 编排：多轮追问/槽位/报告/降级
│  │  │  └─ dept_map.py           # 科室映射、急重症、指代与既往史抽取、口语归一
│  │  ├─ llm/client.py      # httpx 直连 SiliconFlow，SSE 流式 + 指数退避重试
│  │  ├─ services/agent_service.py  # SSE 事件业务编排
│  │  ├─ routers/           # 认证/会话/对话/报告 路由
│  │  └─ db/                # sqlite 访问层
│  ├─ requirements.txt
│  └─ .env.example          # LLM Key / 模型等配置样例
├─ frontend/
│  └─ src/
│     ├─ pages/             # AuthPage / ChatPage
│     ├─ components/        # ChatWindow / ConversationList / ReportPanel
│     └─ services/          # api.ts / sse.ts
├─ evaluation/
│  ├─ reports/              # 真实 LLM 评测报告 + metrics.json
│  └─ reports_rule/         # 离线规则对照评测
├─ eval_runner.py           # 评测运行器（--mode llm|rule，降级自愈重跑）
├─ deploy/                  # 部署相关
├─ 一键启动.bat
└─ 一键停止.bat
```

---

## 评测与指标

评测运行器 `eval_runner.py` 支持 in-process 导入 Agent 跑 120 例病历用例，LLM 调用失败时静默降级并自愈重跑至降级用例数为 0 后输出报告。

**真实 LLM 全量 120 例实测**（详见 `evaluation/reports/评测报告.md`）：

| 指标 | 实测值 | 任务书要求 | 状态 |
|------|--------|-----------|------|
| 追问覆盖率 | 95.63% | ≥90% | ✅ |
| 报告字段完整率 | 100% | ≥90% | ✅ |
| 科室 Top3 准确率 | 93.33% | ≥80% | ✅ |
| 急重症拦截准确率 | 98.33% | —— | ✅ |
| 平均响应时间 | 约 3.9s | ≤5s | ✅ |

> 说明：急重症 / 拒答用例只计入拦截准确率，不计入追问覆盖率与报告完整率。

---

## 配置说明

环境变量在 `backend/.env`（参照 `backend/.env.example`）：

| 变量 | 说明 |
|------|------|
| `LLM_API_KEY` | SiliconFlow / OpenAI 兼容 API Key，**留空则走本地规则降级模式** |
| `LLM_BASE_URL` | 默认 `https://api.siliconflow.cn/v1` |
| `LLM_MODEL` | 默认 `deepseek-ai/DeepSeek-V3` |
| `LLM_MAX_TOKENS` | 默认 `200`（问诊回复较短，压缩响应时间） |
| `LLM_TIMEOUT` | 默认 `180` 秒 |
| `JWT_SECRET` | 生产环境务必改为足够长的随机串 |

两种运行模式：

- **LLM 模式**：配置有效 `LLM_API_KEY` 后启用，多轮追问更自然、支持情绪安抚。
- **规则降级模式**：未配置或调用失败时，自动回退本地确定性追问与报告生成，功能不中断。

---

## License

内部教学 / 交付项目。请勿用于真实医疗场景；本系统不构成任何医学建议、诊断或治疗方案。