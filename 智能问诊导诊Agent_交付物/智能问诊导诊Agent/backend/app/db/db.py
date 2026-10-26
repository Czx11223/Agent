"""sqlite3 访问层：WAL、每线程独立连接、参数化查询、事务上下文。"""
import sqlite3
import threading
from contextlib import contextmanager

from ..core import config
from ..core.errors import DB_ERROR, ApiError

_conns: dict[int, sqlite3.Connection] = {}
_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    phone TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS conversation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (user_id) REFERENCES user(id)
);

CREATE TABLE IF NOT EXISTS message (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role TEXT NOT NULL,           -- user / agent
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (conversation_id) REFERENCES conversation(id)
);

CREATE TABLE IF NOT EXISTS pre_diagnose_report (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL UNIQUE,
    user_id INTEGER NOT NULL,
    chief_complaint TEXT,
    present_illness TEXT,
    allergy_history TEXT,
    past_history TEXT,
    recommend_dept_top3 TEXT,
    disclaimer TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (conversation_id) REFERENCES conversation(id)
);

CREATE TABLE IF NOT EXISTS evaluation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER,
    user_id INTEGER,
    case_id TEXT,
    judge_result TEXT,
    score REAL,
    detail TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (conversation_id) REFERENCES conversation(id)
);

CREATE INDEX IF NOT EXISTS idx_msg_conv ON message(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conv_user ON conversation(user_id);
"""


def init_db() -> None:
    """建表。可在启动 lifespan 自动调用，也可用 python -m app.db.init_db 手动执行。"""
    conn = _get_conn()
    with _write(conn):
        conn.executescript(_SCHEMA)


def _get_conn() -> sqlite3.Connection:
    tid = threading.get_ident()
    with _lock:
        conn = _conns.get(tid)
        if conn is None:
            conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            _conns[tid] = conn
        return conn


@contextmanager
def _write(conn: sqlite3.Connection):
    try:
        yield conn
        conn.commit()
    except Exception as e:  # noqa
        conn.rollback()
        raise ApiError(DB_ERROR, f"数据库错误: {e}")


def execute(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    conn = _get_conn()
    with _write(conn):
        return conn.execute(sql, params)


def executemany(sql: str, seq) -> None:
    conn = _get_conn()
    with _write(conn):
        conn.executemany(sql, seq)


def query(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    conn = _get_conn()
    cur = conn.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return rows


def query_one(sql: str, params: tuple = ()):
    rows = query(sql, params)
    return rows[0] if rows else None


def last_insert_id() -> int:
    conn = _get_conn()
    with _write(conn):
        cur = conn.execute("SELECT last_insert_rowid() AS id")
        val = cur.fetchone()["id"]
        cur.close()
        return val