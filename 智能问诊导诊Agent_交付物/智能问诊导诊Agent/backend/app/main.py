from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from .core import config
from .core.errors import ApiError
from .db.db import init_db
from .routers import auth, chat, conversation, evaluation, report


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()  # 启动自动建表
    yield


app = FastAPI(title="智能问诊导诊Agent", version="1.0.0", lifespan=lifespan)

# 生产必须启用 HTTPS 终截（[TLS]）；only allow front real origins, not "*" with credentials
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS or ["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API = "/api/v1"
app.include_router(auth.router, prefix=API)
app.include_router(conversation.router, prefix=API)
app.include_router(chat.router, prefix=API)
app.include_router(report.router, prefix=API)
app.include_router(evaluation.router, prefix=API)


@app.exception_handler(ApiError)
async def api_error_handler(_: Request, exc: ApiError):
    return JSONResponse(
        status_code=exc.http_status,
        content={"code": exc.code, "message": exc.message, "data": None},
    )


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health")
def health():
    return {"code": 0, "message": "ok", "data": "ok"}