"""独立初始化数据库：python -m app.db.init_db"""
from .db import init_db

if __name__ == "__main__":
    init_db()
    print("[OK] 数据库初始化完成（app.db, WAL）")