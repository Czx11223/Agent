# 项目依赖 requirements.txt 与部署说明

- 版本：V1.0.0　·　环境：Python 3.12+

---

## 1. requirements.txt（可直接使用）

```text
# ---- Web 后端框架 ----
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
pydantic>=2.6.0
pydantic-settings>=2.2.0

# ---- 认证与安全 ----
PyJWT>=2.8.0
passlib[bcrypt]>=1.7.4
bcrypt>=4.1.0

# ---- Agent / 大模型 ----
agentscope>=1.0.0
openai>=1.12.0

# ---- 兼容 / 实用 ----
httpx>=0.27.0
python-multipart>=0.0.9
```

> 说明：
> - **实际生效版本以 `backend/requirements.txt` 为准**（已锁定：agentscope==2.0.10、fastapi==0.143.0、uvicorn==0.54.0、openai==3.29.0、httpx==0.28.1、python-jose[cryptography]==3.5.0、python-dotenv==1.2.4）。
> - `agentscope` 2.x 会经 `mcp` 强依赖较新的 `starlette`，需与 `fastapi` 同步升级；模型/接口名以安装的 AgentScope 版本 API 为准。
> - 数据库为 sqlite3（标准库），无需额外 ORM 依赖；如需迁移至关系库可追加 SQLAlchemy。

---

## 2. 安装步骤

```bash
# 创建虚拟环境
python -m venv .venv
# 激活 (Windows PowerShell)
.venv\Scripts\Activate.ps1
# 或 (git-bash/Linux)
# source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

---

## 3. 配置环境变量（[TLS] 安全提示）

```bash
# Windows PowerShell 示例 (生产请用安全的密钥托管)
$env:JWT_SECRET = "请替换成安全的随机长密钥"      # 勿硬编码
$env:LLM_API_KEY = "sk-xxxx"                      # 国内可直连 OpenAI 兼容接口
$env:LLM_BASE_URL = "https://your-llm-endpoint/v1"
$env:LLM_MODEL = "your-model-name"
```

---

## 4. 启动服务

```bash
# 开发模式
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 生产模式(建议交由 Nginx 做 HTTPS 反向代理,后端仅监听内网)
# [TLS] uvicorn 绑定 127.0.0.1,由 Nginx 终止 TLS 并转发
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
```

---

## 5. 目录结构（后端）

```text
backend/
  requirements.txt
  app/
    main.py
    cores/
      config.py      # 读取环境变量(JWT/LLM Key 等)
      errors.py
      security.py
    db/
      db.py
    schemas.py
    routers/
      auth.py
      conversation.py
      chat.py
      report.py
      evaluation.py
    services/
      agent_service.py
    agent/
      pre_consult_agent.py   # 复用《09》核心代码
      templates.py           # 复用《11》话术库
    llm/
      client.py