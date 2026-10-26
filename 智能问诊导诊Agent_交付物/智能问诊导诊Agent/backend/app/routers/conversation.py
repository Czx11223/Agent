from fastapi import APIRouter, Depends

from ..core.errors import ApiError, FORBIDDEN
from ..core.security import get_current_user
from ..db.db import execute, query, query_one, last_insert_id
from ..schemas import ConversationCreate
from ..services.agent_service import _strip_trailer

router = APIRouter()


def _ensure_owner(cid: int, user_id: int) -> None:
    row = query_one("SELECT id FROM conversation WHERE id=? AND user_id=?", (cid, user_id))
    if not row:
        raise ApiError(FORBIDDEN, "会话不存在或无权限", http_status=403)


@router.get("/conversations")
def list_conversations(user_id: int = Depends(get_current_user)):
    rows = query(
        "SELECT id, title, status FROM conversation WHERE user_id=? ORDER BY id DESC",
        (user_id,),
    )
    return [{"id": r["id"], "title": r["title"], "status": r["status"]} for r in rows]


@router.post("/conversations")
def create_conversation(body: ConversationCreate, user_id: int = Depends(get_current_user)):
    execute("INSERT INTO conversation(user_id, title) VALUES(?,?)", (user_id, body.title))
    return {"conversation_id": last_insert_id()}


@router.get("/conversations/{conversation_id}/messages")
def get_messages(conversation_id: int, user_id: int = Depends(get_current_user)):
    _ensure_owner(conversation_id, user_id)
    rows = query(
        "SELECT id, role, content FROM message WHERE conversation_id=? ORDER BY id",
        (conversation_id,),
    )
    messages = [
        {
            "id": r["id"],
            "sender": "agent" if r["role"] == "agent" else "user",
            "content": _strip_trailer(r["content"]),
        }
        for r in rows
    ]
    return {"messages": messages}