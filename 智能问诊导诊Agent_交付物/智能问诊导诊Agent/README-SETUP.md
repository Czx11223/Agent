# 智能问诊导诊 Agent · 快速启动

前端 React(Vite) + 后端 FastAPI(sqlite3) + AgentScope 编排（Msg 消息模型） + OpenAI 兼容 LLM。

## 1. 后端

```powershell
cd backend
python -m venv .venv          # 需 Python 3.12+（本项目在 Python 3.12.14 下验证）
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env     # 编辑 .env：LLM_API_KEY / LLM_BASE_URL / LLM_MODEL / JWT_SECRET
python -m app.db.init_db        # 初始化 app.db（启动时也会自动建表）
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# 接口文档: http://127.0.0.1:8000/docs
```

## 2. 前端

```powershell
cd frontend
npm install
npm run dev      # http://127.0.0.1:5173  (/api 已代理到后端)
```

> 生产构建：`npm run build` → `dist/`，用 `deploy/nginx.conf` 托管并 HTTPS 反代 `/api`。

## 3. 主要接口

| 接口 | 说明 |
| --- | --- |
| `POST /api/v1/auth/register` | 注册 |
| `POST /api/v1/auth/login` | 登录 |
| `GET/POST /api/v1/conversations` | 会话列表 / 新建 |
| `GET /api/v1/conversations/{id}/messages` | 历史消息 |
| `POST /api/v1/chat/stream` | SSE 流式对话 |
| `GET /api/v1/reports/{id}` | 预问诊报告 |
| `GET /api/v1/reports/{id}/export` | 报告导出 |
| `POST /api/v1/evaluation` | 评测写入 |

## 4. 目录结构

```
frontend/  React 18 + Vite + Tailwind + AntD
backend/
  app/
    main.py            应用入口/路由挂载
    core/              配置、统一错误码、安全(JWT/密码/输入过滤)
    db/                sqlite3 访问层 + 建表
    llm/               OpenAI 兼容客户端
    agent/             pre_consult_agent 编排 + 症状-科室映射
    services/          agent_service（SSE 事件、消息/报告落库）
    routers/           auth/conversation/chat/report/evaluation
deploy/nginx.conf      生产 Nginx + HTTPS + SSE 禁用缓冲
```