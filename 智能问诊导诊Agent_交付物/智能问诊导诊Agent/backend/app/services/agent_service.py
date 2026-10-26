"""Agent 编排与业务服务：把对话推进、槽位/消息/报告落库封装为 SSE 事件生成器。"""
import json
import time

from ..db.db import execute, query
from ..agent.pre_consult_agent import PreConsultAgent
# import 触发 dept_map 副作用? 不，仅预请求常量
from ..agent import dept_map  # noqa: F401

SLOTS_TAG = "[[SLOTS]]"


def _strip_trailer(content: str) -> str:
    return content.split(SLOTS_TAG, 1)[0] if SLOTS_TAG in content else content


def load_slots(cid: int) -> dict:
    rows = query(
        "SELECT content FROM message WHERE conversation_id=? AND role='agent' ORDER BY id",
        (cid,),
    )
    slots: dict = {}
    for r in rows:
        c = r["content"]
        if SLOTS_TAG in c:
            try:
                slots = json.loads(c.split(SLOTS_TAG, 1)[1])
            except Exception:
                pass
    return slots


def load_history(cid: int) -> list[dict]:
    rows = query("SELECT role, content FROM message WHERE conversation_id=? ORDER BY id", (cid,))
    return [{"role": r["role"], "content": _strip_trailer(r["content"])} for r in rows]


def _chunks(s: str, n: int = 5):
    for i in range(0, len(s), n):
        yield s[i : i + n]


def run(uid: int, cid: int, user_text: str):
    """处理一轮用户消息，产出 SSE 事件 dict 序列。"""
    execute(
        "INSERT INTO message(conversation_id, role, content) VALUES(?,?,?)",
        (cid, "user", user_text),
    )
    slots = load_slots(cid)
    history = load_history(cid)
    agent = PreConsultAgent(slots, history)
    try:
        # 通过 AgentScope Msg 接口推进一轮对话（内部维护消息记忆与槽位状态）
        agent.reply(agent.user_msg(user_text))
        decision = agent.last_decision
    except Exception:
        # 兜底：任何未知异常也不静默断流，改为下发 error 事件
        execute("UPDATE conversation SET updated_at=datetime('now','localtime') WHERE id=?", (cid,))
        yield {"type": "error", "text": "服务暂时不可用，请稍后重试。"}
        return
    q = decision["question"]

    # 落库 agent 消息（trailer 携带最新槽位，便于多轮恢复）
    content = q + "\n" + SLOTS_TAG + json.dumps(agent.slots, ensure_ascii=False)
    execute(
        "INSERT INTO message(conversation_id, role, content) VALUES(?,?,?)",
        (cid, "agent", content),
    )

    if decision.get("comfort"):
        yield {"type": "comfort", "text": decision["comfort"]}

    # 流式：将整段回复切块按 token 事件下发，营造流式渲染
    for tok in _chunks(q):
        yield {"type": "token", "delta": tok}
        time.sleep(0.02)

    action = decision["action"]
    if action == "emergency":
        execute("UPDATE conversation SET status='emergency', updated_at=datetime('now','localtime') WHERE id=?", (cid,))
        yield {"type": "emergency", "text": q}
    elif action == "rejected":
        execute("UPDATE conversation SET updated_at=datetime('now','localtime') WHERE id=?", (cid,))
        yield {"type": "rejected", "text": q}
    elif action == "report":
        report = agent.build_report()
        execute(
            "INSERT INTO pre_diagnose_report(conversation_id, user_id, chief_complaint, present_illness, "
            "allergy_history, past_history, recommend_dept_top3, disclaimer) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                cid, uid, report["chief_complaint"], report["present_illness"],
                report["allergy_history"], report["past_history"],
                report["recommend_dept_top3"], report["disclaimer"],
            ),
        )
        execute("UPDATE conversation SET status='completed', updated_at=datetime('now','localtime') WHERE id=?", (cid,))
        yield {"type": "done", "next": "report_ready", "text": q}
    else:
        execute("UPDATE conversation SET updated_at=datetime('now','localtime') WHERE id=?", (cid,))
        yield {"type": "question", "text": q}