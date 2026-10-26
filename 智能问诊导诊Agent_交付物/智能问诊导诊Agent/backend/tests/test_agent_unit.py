"""Agent 编排离线单测：急重症本地拦截（不触 LLM）、报告构建、科室推荐、SSE 事件。"""
import json

from app.agent.pre_consult_agent import PreConsultAgent
from app.agent import dept_map
from app.services import agent_service
from app.db import db


def test_emergency_short_circuit_local():
    # 本地急重症预检命中，不依赖 LLM
    a = PreConsultAgent()
    d = a.step("我胸口剧烈疼痛，喘不上气")
    assert d["action"] == "emergency"
    assert ("急诊" in d["question"]) or ("120" in d["question"])


def test_emergency_detection_keywords():
    assert dept_map.is_emergency("突然剧烈腹痛，脸色发白")
    assert dept_map.is_emergency("喘不上气")
    assert dept_map.is_emergency("刚才晕倒了，不省人事")
    assert not dept_map.is_emergency("有点咳嗽")


def test_report_build_required_fields():
    a = PreConsultAgent()
    a.slots.update({
        "main_symptom": "咳嗽",
        "duration": "三天",
        "accompanying_symptom": "发热",
        "past_history": "高血压",
        "allergy_history": "青霉素过敏",
    })
    r = a.build_report()
    assert r["chief_complaint"]
    assert r["present_illness"]
    assert r["allergy_history"]
    assert r["past_history"]
    assert r["disclaimer"]
    depts = json.loads(r["recommend_dept_top3"])
    assert isinstance(depts, list) and len(depts) >= 1


def test_dept_recommend_respiratory():
    top = dept_map.recommend_top3("咳嗽咳痰三天，有点发热")
    assert top and top[0]["dept"] == "呼吸内科"


def test_dept_recommend_ortho():
    top = dept_map.recommend_top3("右膝盖下楼时不疼，上楼疼")
    assert top and top[0]["dept"] == "骨科"


def test_dept_recommend_fallback():
    top = dept_map.recommend_top3("就想随便问问")
    assert top  # 兜底内科全科


def test_stream_emergency_persists_messages():
    db.execute("INSERT INTO user(username, password_hash) VALUES(?,?)", ("t_emg", "h"))
    uid = db.query_one("SELECT id FROM user WHERE username=?", ("t_emg",))["id"]
    db.execute("INSERT INTO conversation(user_id, title) VALUES(?,?)", (uid, "急重症"))
    cid = db.last_insert_id()

    events = list(agent_service.run(uid, cid, "胸口剧烈疼痛，喘不上气"))
    types = [e["type"] for e in events]
    assert "emergency" in types

    msgs = db.query("SELECT role FROM message WHERE conversation_id=?", (cid,))
    roles = [m["role"] for m in msgs]
    assert roles.count("user") == 1
    assert roles.count("agent") == 1