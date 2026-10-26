"""数据库层：五张表 CRUD 冒烟 + 报告/评测写入。"""
from app.db import db


def _mk_user(name: str, pw: str = "hash") -> int:
    db.execute("INSERT INTO user(username, password_hash) VALUES(?,?)", (name, pw))
    return db.query_one("SELECT id FROM user WHERE username=?", (name,))["id"]


def test_user_crud():
    uid = _mk_user("db_user")
    row = db.query_one("SELECT * FROM user WHERE id=?", (uid,))
    assert row is not None and row["username"] == "db_user"


def test_conversation_insert_and_query():
    uid = _mk_user("db_conv")
    db.execute("INSERT INTO conversation(user_id, title) VALUES(?,?)", (uid, "会话A"))
    cid = db.last_insert_id()
    rows = db.query("SELECT id, status FROM conversation WHERE user_id=?", (uid,))
    assert any(r["id"] == cid for r in rows)


def test_message_insert_and_index():
    uid = _mk_user("db_msg")
    db.execute("INSERT INTO conversation(user_id) VALUES(?)", (uid,))
    cid = db.last_insert_id()
    db.execute("INSERT INTO message(conversation_id, role, content) VALUES(?,?,?)", (cid, "user", "咳嗽"))
    db.execute("INSERT INTO message(conversation_id, role, content) VALUES(?,?,?)", (cid, "agent", "多久了"))
    msgs = db.query("SELECT role FROM message WHERE conversation_id=?", (cid,))
    assert len(msgs) == 2


def test_report_write_read():
    uid = _mk_user("db_rep")
    db.execute("INSERT INTO conversation(user_id) VALUES(?)", (uid,))
    cid = db.last_insert_id()
    db.execute(
        "INSERT INTO pre_diagnose_report(conversation_id, user_id, chief_complaint, present_illness, "
        "allergy_history, past_history, recommend_dept_top3, disclaimer) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (cid, uid, "咳嗽", "三天伴发热", "无", "无", '[{"dept":"呼吸内科"}]', "免责"),
    )
    r = db.query_one("SELECT * FROM pre_diagnose_report WHERE conversation_id=? AND user_id=?", (cid, uid))
    assert r and r["chief_complaint"] == "咳嗽"


def test_evaluation_write():
    uid = _mk_user("db_eval")
    db.execute(
        "INSERT INTO evaluation(conversation_id, user_id, case_id, judge_result, score) "
        "VALUES(?,?,?,?,?)",
        (None, uid, "TC-0001", "pass", 0.95),
    )
    rows = db.query("SELECT score FROM evaluation WHERE case_id=?", ("TC-0001",))
    assert rows and len(rows) == 1