"""pytest 离线冒烟测试。

运行前先把本地包路径加入 sys.path，并把测试库指向临时文件（不触碰本地 app.db）。
不依赖 LLM：所有用例走本地规则/预检/DB/安全逻辑。
"""
import sys
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]  # backend/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core import config  # noqa: E402
import app.db.db as db_mod  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _isolated_db(tmp_path_factory):
    """会话级：把 DB_PATH 指向临时文件并初始化表结构。"""
    db_path = tmp_path_factory.mktemp("testdb") / "app_test.db"
    config.DB_PATH = str(db_path)
    db_mod.init_db()
    yield
    # 线程级连接缓存在测试进程结束时会释放，无需显式清理