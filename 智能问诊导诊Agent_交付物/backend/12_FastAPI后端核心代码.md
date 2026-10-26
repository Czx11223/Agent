# FastAPI 后端核心业务代码（智能问诊导诊 Agent）

- 版本：V1.0.0　·　技术栈：FastAPI + sqlite3 + AgentScope + OpenAI 兼容 LLM + SSE
- 表结构：沿用《数据库设计》的 `user / conversation / message / pre_diagnose_report / evaluation`
- Agent：复用《09_Agent编排核心代码》的 `PreConsultAgent` 与《11_话术模板库》`TemplateBank`

> ⚠️ **HTTPS 传输提醒**：本代码注释标记 `[TLS]` 处为安全边界。生产环境**必须**部署在 Nginx 反向代理之后并启用 HTTPS 终截（详见文档 7），API 后端应仅监听内网/本地回环，不直接对外暴露明文 HTTP。

---

## 1. 统一错误码 `app/core/errors.py`

```python
# app/core/errors.py
from fastapi import HTTPException


class Err(Exception):
    """业务异常，含 code/message/http 状态"""

    def __init__(self, code: int, message: str, http: int = 400):
        self.code = code
        self.message = message
        self.http = http
        super().__init__(message)


# 统一错误码表
ERR_SUCCESS       = 0
ERR_BAD_PARAM     = 4001   # 参数错误
ERR_AUTH_FAIL     = 4002   # 用户名或密码错误
ERR_UNAUTHORIZED  = 4003   # 未登录/令牌无效/过期
ERR_FORBIDDEN     = 4004   # 越权访问他人资源
ERR_NOT_FOUND     = 4005   # 资源不存在
ERR_CONFLICT      = 4006   # 数据冲突(如用户名已存在)
ERR_PROMPT_INJECT = 4007   # 检测到提示词注入,已拦截
ERR_LLM           = 5001   # 大模型调用失败
ERR_DB            = 5002   # 数据库异常
ERR_SERVER        = 5000   # 服务器内部错误


def resp_ok(data=None, message="ok"):
    return {"code": ERR_SUCCESS, "message": message, "data": data}


def resp_err(code: int, message: str):
    return {"code": code, "message": message, "data": None}


def raise_err(code: int, message: str, http: int = 400):
    raise HTTPException(status_code=http, detail=resp_err(code, message))
```

---

## 2. 数据库访问 `app/db/db.py`（sqlite3）

```python
# app/db/db.py
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "app.db"
_local = threading.local()   # 每线程独立连接

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    username TEXT NOT NULL UNIQUE,
    phone TEXT UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    avatar_url TEXT,
    role TEXT NOT NULL DEFAULT 'patient',
    status TEXT NOT NULL DEFAULT 'active',
    last_login_at TEXT,
    deleted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES user(id),
    title TEXT,
    status TEXT NOT NULL DEFAULT 'diagnosing',
    started_at TEXT NOT NULL,
    ended_at TEXT,
    slot_state TEXT,
    ask_progress TEXT DEFAULT '{}',
    emergency_flag INTEGER NOT NULL DEFAULT 0,
    deleted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS message (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    conversation_id INTEGER NOT NULL REFERENCES conversation(id),
    sender TEXT NOT NULL,
    content TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'text',
    slot_delta TEXT,
    emotion TEXT,
    emergency_hit INTEGER NOT NULL DEFAULT 0,
    extra TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pre_diagnose_report (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    conversation_id INTEGER NOT NULL UNIQUE REFERENCES conversation(id),
    user_id INTEGER NOT NULL REFERENCES user(id),
    chief_complaint TEXT,
    present_illness TEXT,
    accompanying_symptom TEXT,
    past_history TEXT,
    allergy_history TEXT,
    symptom_json TEXT,
    recommend_dept_top3 TEXT,
    top3_accuracy INTEGER,
    emergency_flag INTEGER NOT NULL DEFAULT 0,
    disclaimer TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    deleted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evaluation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    batch_code TEXT NOT NULL,
    test_case_id TEXT NOT NULL,
    user_id INTEGER REFERENCES user(id),
    conversation_id INTEGER REFERENCES conversation(id),
    report_id INTEGER REFERENCES pre_diagnose_report(id),
    input_text TEXT NOT NULL,
    input_text_enc TEXT,
    expected_dept TEXT NOT NULL,
    expected_fields TEXT,
    top3_accuracy INTEGER NOT NULL DEFAULT 0,
    field_coverage REAL DEFAULT 0,
    report_completeness REAL DEFAULT 0,
    avg_response_time REAL,
    bad_case_flag INTEGER NOT NULL DEFAULT 0,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_username ON user(username);
CREATE INDEX IF NOT EXISTS idx_conv_user_status ON conversation(user_id, status);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON message(conversation_id);
CREATE INDEX IF NOT EXISTS idx_report_user ON pre_diagnose_report(user_id);
CREATE INDEX IF NOT EXISTS idx_eval_batch ON evaluation(batch_code);
"""

def get_conn() -> sqlite3.Connection:
    """每个线程复用一条连接; WAL 提升并发"""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        _local.conn = conn
    return conn


def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as c:
        c.executescript(SCHEMA)


@contextmanager
def tx():
    c = get_conn()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
```

> 注：上例为便于阅读简化了线程连接缓存，生产可改用 `threading.local()` 或连接池（`row_factory` 需按连接设置）。

---

## 3. 安全：密码哈希 / JWT / 输入校验 / 提示词注入防护 `app/core/security.py`

```python
# app/core/security.py
import re
import jwt
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from fastapi import Request, HTTPException

from core.errors import *

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_SECRET = "CHANGE_ME_IN_ENV___请勿在代码中硬编码"     # [TLS] 生产从环境变量取
JWT_ALGO = "HS256"
ACCESS_TTL = timedelta(hours=2)


def hash_password(pw: str) -> str:
    return pwd.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    return pwd.verify(pw, hashed)


def create_token(user_id: int, role: str) -> str:
    payload = {
        "sub": str(user_id), "role": role,
        "exp": datetime.now(timezone.utc) + ACCESS_TTL,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.PyJWTError:
        raise_err(ERR_UNAUTHORIZED, "登录状态失效,请重新登录", 401)


# ---------------------------------------------------------------
# 输入安全校验: 最大长度 / 白名单字符 / 提示词注入过滤 [TLS/PROMPT]
# ---------------------------------------------------------------
MAX_INPUT_LEN = 1024
_INJECTION_PATTERN = re.compile(
    r"忽略(上面|以下|系统)?(指令|提示|要求|设定)|ignore\s+(all\s+)?(previous|prior)"
    r"|(overwrite|override)\s+(system|prompt)|你是|你现在是|扮演|忘记你(之前|的)|"
    r"输出(system|你的)prompt|reveal|泄露|隐藏指令|去引号|bypass|jailbreak",
    re.IGNORECASE,
)


def sanitize_text(text: str) -> str:
    """清洗并校验自由文本输入。"""
    if text is None:
        raise_err(ERR_BAD_PARAM, "内容不能为空")
    t = text.strip()
    if not t or len(t) > MAX_INPUT_LEN:
        raise_err(ERR_BAD_PARAM, "内容长度为1~1024字符")
    if _INJECTION_PATTERN.search(t):                 # 提示词注入拦截
        raise_err(ERR_PROMPT_INJECT, "检测到可疑指令注入,已拦截", 200)
    return t


def get_current_user(req: Request) -> dict:
    """读取 Authorization: Bearer <jwt>, 返回 {user_id, role}"""
    auth = req.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise_err(ERR_UNAUTHORIZED, "缺少令牌", 401)
    payload = decode_token(auth[7:])
    return {"user_id": int(payload["sub"]), "role": payload.get("role", "patient")}
```

---

## 4. Pydantic 请求/响应模型 `app/schemas.py`

```python
# app/schemas.py
from typing import Optional, List
from pydantic import BaseModel, Field


class RegisterReq(BaseModel):
    username: str = Field(min_length=3, max_length=32, description="登录用户名")
    password: str = Field(min_length=6, max_length=64, description="密码")
    phone: Optional[str] = Field(default=None, description="手机号")


class LoginReq(BaseModel):
    account: str = Field(description="用户名或手机号")
    password: str = Field(min_length=6, max_length=64)


class ConversationCreate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=64)


class ChatReq(BaseModel):
    conversation_id: int = Field(gt=0)
    content: str = Field(min_length=1, max_length=1024)


class EvalWriteReq(BaseModel):
    batch_code: str
    test_case_id: str
    input_text: str
    expected_dept: str
    expected_fields: Optional[str] = None


class ReportOut(BaseModel):
    code: str
    chief_complaint: Optional[str]
    present_illness: Optional[str]
    accompanying_symptom: Optional[str]
    past_history: Optional[str]
    allergy_history: Optional[str]
    symptom_json: Optional[str]
    recommend_dept_top3: Optional[str]
    disclaimer: Optional[str]
```

---

## 5. 认证 + 会话 + 报告 + 评测 路由 `app/routers/`

```python
# app/routers/auth.py
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request
from sqlalchemy_utils import utcnow  # 可选; 此处用 datetime

from db.db import tx
from core.security import *
from core.errors import *
from schemas import RegisterReq, LoginReq

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])


@router.post("/register")
def register(body: RegisterReq):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    pwhash = hash_password(body.password)
    with tx() as c:
        try:
            cur = c.execute(
                "INSERT INTO user(code, username, phone, password_hash, role, created_at, updated_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (gen_code("U"), body.username, body.phone, pwhash, "patient", now, now),
            )
        except sqlite3.IntegrityError:
            raise_err(ERR_CONFLICT, "用户名或手机号已存在", 409)
        uid = cur.lastrowid
    return resp_ok({"user_id": uid, "username": body.username})


@router.post("/login")
def login(body: LoginReq):
    with tx() as c:
        row = c.execute(
            "SELECT * FROM user WHERE (username=? OR phone=?) AND deleted=0",
            (body.account, body.account),
        ).fetchone()
    if not row or not verify_password(body.password, row["password_hash"]):
        raise_err(ERR_AUTH_FAIL, "账号或密码错误", 401)
    token = create_token(row["id"], row["role"])
    with tx() as c:
        c.execute("UPDATE user SET last_login_at=? WHERE id=?",
                  (datetime.now(timezone.utc).isoformat(timespec="seconds"), row["id"]))
    return resp_ok({"token": token, "user": {"id": row["id"], "username": row["username"], "role": row["role"]}})
```

```python
# app/routers/conversation.py
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from db.db import tx
from core.security import get_current_user
from core.errors import *
from schemas import ConversationCreate

router = APIRouter(prefix="/api/v1/conversations", tags=["会话"])


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@router.get("")
def list_conversations(req: Request):
    uid = get_current_user(req)["user_id"]
    with tx() as c:
        rows = c.execute(
            "SELECT * FROM conversation WHERE user_id=? AND deleted=0 ORDER BY id DESC",
            (uid,),
        ).fetchall()
    return resp_ok([dict(r) for r in rows])


@router.post("")
def create_conversation(body: ConversationCreate, req: Request):
    uid = get_current_user(req)["user_id"]
    now = _now()
    with tx() as c:
        cur = c.execute(
            "INSERT INTO conversation(code,user_id,title,status,started_at,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (gen_code("C"), uid, body.title or "新问诊", "diagnosing", now, now, now),
        )
        cid = cur.lastrowid
    return resp_ok({"conversation_id": cid})


@router.get("/{cid}/messages")
def get_messages(cid: int, req: Request):
    uid = get_current_user(req)["user_id"]
    with tx() as c:
        conv = c.execute("SELECT * FROM conversation WHERE id=? AND deleted=0", (cid,)).fetchone()
        if not conv:
            raise_err(ERR_NOT_FOUND, "会话不存在", 404)
        if conv["user_id"] != uid:                       # 越权校验
            raise_err(ERR_FORBIDDEN, "无权访问该会话", 403)
        msgs = c.execute("SELECT * FROM message WHERE conversation_id=? ORDER BY id",
                         (cid,)).fetchall()
    return resp_ok({"conversation": dict(conv), "messages": [dict(m) for m in msgs]})
```

```python
# app/routers/report.py
from fastapi import APIRouter, Request
from db.db import tx
from core.security import get_current_user
from core.errors import *
from schemas import ReportOut

router = APIRouter(prefix="/api/v1/reports", tags=["报告"])


@router.get("/{conv_id}", response_model=None)
def get_report(conv_id: int, req: Request):
    uid = get_current_user(req)["user_id"]
    with tx() as c:
        conv = c.execute("SELECT * FROM conversation WHERE id=? AND deleted=0", (conv_id,)).fetchone()
        if not conv:
            raise_err(ERR_NOT_FOUND, "会话不存在", 404)
        if conv["user_id"] != uid:
            raise_err(ERR_FORBIDDEN, "无权访问", 403)
        row = c.execute(
            "SELECT * FROM pre_diagnose_report WHERE conversation_id=? AND deleted=0", (conv_id,)
        ).fetchone()
    if not row:
        raise_err(ERR_NOT_FOUND, "报告尚未生成", 404)
    return resp_ok(dict(row))


@router.get("/{conv_id}/export")
def export_report(conv_id: int, req: Request):
    """导出为 Markdown 文本。"""
    # [TLS] 生产需鉴权并记录导出日志(审计)
    uid = get_current_user(req)["user_id"]
    with tx() as c:
        conv = c.execute("SELECT * FROM conversation WHERE id=? AND deleted=0", (conv_id,)).fetchone()
        if not conv or conv["user_id"] != uid:
            raise_err(ERR_NOT_FOUND if not conv else ERR_FORBIDDEN,
                       "报告不存在或无权访问", 404 if not conv else 403)
        row = c.execute("SELECT * FROM pre_diagnose_report WHERE conversation_id=?", (conv_id,)).fetchone()
    md = (f"# 预问诊报告\n\n## 主诉\n{row['chief_complaint'] or ''}\n\n"
          f"## 现病史\n{row['present_illness'] or ''}\n\n## 过敏史\n{row['allergy_history'] or ''}\n\n"
          f"## 既往史\n{row['past_history'] or ''}\n\n## 科室推荐\n{row['recommend_dept_top3'] or ''}\n\n"
          f"> {row['disclaimer'] or ''}")
    return resp_ok({"filename": f"{row['code']}.md", "content": md})
```

```python
# app/routers/evaluation.py
from fastapi import APIRouter, Request
from db.db import tx
from core.security import get_current_user   # 评测写入需登录(建议限 evaluator 角色)
from core.errors import *
from schemas import EvalWriteReq

router = APIRouter(prefix="/api/v1/evaluation", tags=["评测"])


@router.post("/write")
def write_eval(body: EvalWriteReq, req: Request):
    uid = get_current_user(req)["user_id"]
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(timespec="seconds")
    with tx() as c:
        cur = c.execute(
            "INSERT INTO evaluation(code,batch_code,test_case_id,input_text,expected_dept,"
            " expected_fields,user_id,status,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (gen_code("E"), body.batch_code, body.test_case_id, body.input_text,
             body.expected_dept, body.expected_fields, uid, "pending", now, now),
        )
    return resp_ok({"evaluation_id": cur.lastrowid})
```

---

## 6. Agent 服务封装（SSE 流式）`app/services/agent_service.py`

```python
# app/services/agent_service.py
import json
import asyncio
from typing import AsyncIterator

from agent.pre_consult_agent import PreConsultAgent   # 复用《09》核心代码
from agent.templates import TemplateBank              # 复用《11》
from db.db import tx
from core.security import sanitize_text
from core.errors import *


class AgentService:
    def __init__(self, agent: PreConsultAgent, bank: TemplateBank):
        self.agent = agent
        self.bank = bank

    async def stream_chat(self, user_id: int, conversation_id: int, content: str) -> AsyncIterator[str]:
        """
        执行 Agent 问诊逻辑并产出 SSE 事件流。
        事件: token / slot / emergency / question / done / error
        """
        text = sanitize_text(content)          # 输入校验 + 提示词注入拦截
        try:
            # 1) 保存用户消息
            with tx() as c:
                c.execute("INSERT INTO message(code,conversation_id,sender,content,created_at)"
                          " VALUES(?,?,?,?,?)",
                          (gen_code("M"), conversation_id, "user", text, now_iso()))

            # 2) 复用 Agent 编排：急重症/越界/情绪/槽位/完成度 由 agent.reply 处理
            #    这里将 reply 改为"逐步产出事件"的异步生成器
            async for event in self._run_pipeline(user_id, conversation_id, text):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Err as e:
            yield f'event: error\ndata: {json.dumps({"code": e.code, "message": e.message})}\n\n'
        except Exception as e:
            yield f'event: error\ndata: {json.dumps({"code": ERR_LLM, "message": "服务繁忙,请稍后"})}\n\n'

    async def _run_pipeline(self, user_id, convo_id, text):
        # 急重症/越界/情绪 前置(规则)
        if detect_emergency(text):
            self._mark_emergency(convo_id)
            repl = self.bank.emergency()
            yield {"type": "emergency", "flag": True}
            yield {"type": "done", "next": "emergency", "text": repl}
            self._save_agent_msg(convo_id, repl, emergency_hit=1)
            return

        if detect_violation(text):
            repl = self.bank.disclaimer()
            yield {"type": "done", "next": "rejected", "text": repl}
            self._save_agent_msg(convo_id, repl)
            return

        # 槽位填充(LLM)
        emotion = detect_emotion(text)
        if emotion:
            yield {"type": "comfort", "emotion": emotion, "text": self.bank.comfort(emotion)}
        slot_upd = await extract_slots(self.agent.model, self.agent.memory, text)
        if slot_upd:
            self.agent.memory.merge_slots(slot_upd)
            yield {"type": "slot", "updates": slot_upd}

        if self.agent.memory.slots.complete():
            report = await self.agent.generate_report()      # LLM 报告
            depts = self.dept_mapper.top3(self.agent.memory.slots)
            self._save_report(convo_id, report, depts)
            yield {"type": "done", "next": "report_ready",
                   "text": self.bank.report_prefix(report, depts)}
        else:
            missing = next_missing(self.agent.memory)
            follow = self.bank.ask(missing)
            yield {"type": "question", "missing": missing, "text": follow}
            yield {"type": "done", "next": "asking"}
            self._save_agent_msg(convo_id, follow)
```

---

## 7. SSE 对话路由 `app/routers/chat.py`

```python
# app/routers/chat.py
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from core.security import get_current_user
from core.errors import *
from schemas import ChatReq
from services.agent_service import AgentService

router = APIRouter(prefix="/api/v1/chat", tags=["对话"])


@router.post("/stream")
async def stream_chat(body: ChatReq, req: Request, svc: AgentService):
    uid = get_current_user(req)["user_id"]
    # 校验会话归属(越权)  [TLS 建议在更早层记录审计日志]
    with __import__("db.db").db.tx() as c:
        conv = c.execute("SELECT * FROM conversation WHERE id=? AND deleted=0",
                         (body.conversation_id,)).fetchone()
        if not conv:
            raise_err(ERR_NOT_FOUND, "会话不存在", 404)
        if conv["user_id"] != uid:
            raise_err(ERR_FORBIDDEN, "无权访问该会话", 403)
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}  # 关闭代理缓冲
    return StreamingResponse(
        svc.stream_chat(uid, body.conversation_id, body.content),
        media_type="text/event-stream",
        headers=headers,
    )
```

---

## 8. 应用入口 `app/main.py`

```python
# app/main.py
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from db.db import init_db
from core.errors import *
from routers import auth, conversation, report, evaluation, chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()                     # 建表
    yield


app = FastAPI(title="智能问诊导诊Agent API", version="1.0.0", lifespan=lifespan)

# [TLS] 生产 CORS 仅开放可信前端域名; 明确禁止开放所有源
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-frontend.example.com"],   # 替换为真实域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(conversation.router)
app.include_router(chat.router)
app.include_router(report.router)
app.include_router(evaluation.router)


@app.exception_handler(Err)
async def err_handler(_: Request, e: Err):
    return JSONResponse(status_code=e.http, content=resp_err(e.code, e.message))


@app.get("/health")
def health():
    return resp_ok({"status": "ok"})
```

```bash
# 启动(windows 命令行, 示例)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# [TLS] 生产: 交由 Nginx 做 HTTPS 反向代理 + 静态资源, uvicorn 仅监听 127.0.0.1
```

---

## 9. SSE 事件协议汇总

| 事件 | 字段 | 说明 |
| --- | --- | --- |
| `token` | `delta` | 流式增量文本（可并发接入） |
| `slot` | `updates` | 本轮槽位更新回执 |
| `comfort` | `emotion, text` | 情绪安抚（追问前） |
| `emergency` | `flag:true` | 急重症命中 |
| `question` | `missing, text` | 完整追问句 |
| `done` | `next: asking/report_ready/emergency/rejected` | 回合结束状态 |
| `error` | `code, message` | 异常 |

示例：

```text
event: slot    data: {"type":"slot","updates":{"body_part":"胸口"}}
event: comfort data: {"type":"comfort","emotion":"pain","text":"听上去确实很难受，辛苦了。"}
event: token   data: {"delta":"请问"}
event: token   data: {"delta":"疼痛持续多久了？"}
event: done    data: {"type":"done","next":"asking"}
```

---

## 10. 关键安全说明

- **[TLS]**：全部业务接口须经 Nginx HTTPS 终截；JWT Secret、LLM Key 从环境变量注入，禁止硬编码。
- **输入校验**：`sanitize_text` 统一做长度/内容清洗，并对提示词注入关键词做拦截（错误码 `4007`）。
- **越权校验**：会话/报告读取均校验 `user_id` 归属，返回 `403/4004`。
- **错误码统一**：前端按 `code` 分支处理，所有失败响应结构 `{code, message, data:null}`。