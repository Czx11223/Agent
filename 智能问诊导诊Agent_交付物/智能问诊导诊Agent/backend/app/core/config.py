import os
from pathlib import Path

from dotenv import load_dotenv

# 读取 backend/.env（若存在）
# config.py 位于 backend/app/core/ 下，需回退 3 层到 backend/
BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(str(BASE_DIR / ".env"), override=True)

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALGO = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "200"))
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "180"))

DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "app.db"))
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]