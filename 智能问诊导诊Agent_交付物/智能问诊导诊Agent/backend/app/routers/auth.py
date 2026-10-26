from fastapi import APIRouter

from ..core import security
from ..core.errors import ApiError, AUTH_FAILED, DUPLICATE
from ..db.db import execute, query_one, last_insert_id
from ..schemas import LoginIn, RegisterIn

router = APIRouter()


@router.post("/auth/register")
def register(body: RegisterIn):
    if query_one("SELECT id FROM user WHERE username=?", (body.username,)):
        raise ApiError(DUPLICATE, "账号已存在")
    pw = security.hash_password(body.password)
    execute(
        "INSERT INTO user(username, password_hash, phone) VALUES(?,?,?)",
        (body.username, pw, body.phone),
    )
    uid = last_insert_id()
    return {"user_id": uid, "token": security.create_token(uid)}


@router.post("/auth/login")
def login(body: LoginIn):
    row = query_one("SELECT * FROM user WHERE username=?", (body.account,))
    if not row or not security.verify_password(body.password, row["password_hash"]):
        raise ApiError(AUTH_FAILED, "账号或密码错误", http_status=401)
    return {"user_id": row["id"], "token": security.create_token(row["id"])}