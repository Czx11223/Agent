import hashlib
import os
import re
from datetime import datetime, timedelta, timezone

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, JWTError

from . import config
from ..core.errors import PARAM_ERROR, ApiError, AUTH_FAILED, UNAUTHORIZED, INPUT_BLOCKED, DB_ERROR
from ..db.db import query_one

_bearer = HTTPBearer(auto_error=False)

# 提示词注入 / 越权指令特征（黑名单，大小写不敏感）
# 仅拦截“注入/越权”类指令。索要诊断/开药等越界业务请求不在此列（交给 Agent 走免责拒答模板，
# 拦截词过多会丢失友好的 rejected 交互）。
_INJECTION_PATTERN = re.compile(
    r"(忽略(之前|上面|以上|刚才)|忽略所有|system\s*prompt|系统提示词|扮演|你是\s*AI|"
    r"绕过|越狱|jailbreak|泄露|你的(指令|规则|system)|不要再追问|只回复(结果|数字|yes)|下一步动作|"
    r"导出(你的|全部)|输出(你的|完整).*(指令|提示词))",
    re.IGNORECASE,
)


# —— 密码（内置 PBKDF2，避免 bcrypt 平台编译问题；生产可换 argon2/bcrypt）——
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return salt.hex() + ":" + dk.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split(":", 1)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 100_000)
        return dk.hex() == dk_hex
    except Exception:
        return False


# —— JWT ——
def create_token(user_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=config.JWT_EXPIRE_HOURS)
    payload = {"sub": str(user_id), "exp": exp}
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGO)


def decode_token(token: str) -> int:
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGO])
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise ApiError(AUTH_FAILED, "登录状态无效或已过期，请重新登录", http_status=401)


def get_current_user(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> int:
    if cred is None or not cred.credentials:
        raise ApiError(UNAUTHORIZED, "未登录", http_status=401)
    return decode_token(cred.credentials)


def owner_user_id_or_raise(user_id: int, current_user: int) -> None:
    if user_id != current_user:
        raise ApiError(DB_ERROR, "无效会话")  # 避免暴露他人资源存在性


# —— 输入安全校验 ——
def sanitize_text(text: str, max_len: int = 1024) -> str:
    if not isinstance(text, str):
        raise ApiError(PARAM_ERROR, "消息必须为字符串")
    text = text.strip()
    if not text:
        raise ApiError(PARAM_ERROR, "消息不能为空")
    if len(text) > max_len:
        raise ApiError(PARAM_ERROR, f"消息过长（上限 {max_len} 字符）")
    if _INJECTION_PATTERN.search(text):
        raise ApiError(INPUT_BLOCKED, "包含系统安全策略不允许的内容，已拦截")
    return text


# —— DB 辅助（供路由复用）——
def get_user_by_name(username: str):
    return query_one("SELECT * FROM user WHERE username=?", (username,))