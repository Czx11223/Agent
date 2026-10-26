import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..core.errors import ApiError, FORBIDDEN
from ..core.security import get_current_user, sanitize_text
from ..db.db import query_one
from ..schemas import ChatIn
from ..services import agent_service

router = APIRouter()


def _sse(ev: dict) -> str:
    name = ev["type"]
    body = {k: v for k, v in ev.items() if k != "type"}
    lines = [f"event: {name}", f"data: {json.dumps(body, ensure_ascii=False)}"]
    return "\n".join(lines) + "\n\n"


@router.post("/chat/stream")
def chat_stream(body: ChatIn, user_id: int = Depends(get_current_user)):
    row = query_one("SELECT id FROM conversation WHERE id=? AND user_id=?", (body.conversation_id, user_id))
    if not row:
        raise ApiError(FORBIDDEN, "会话不存在或无权限", http_status=403)
    # 输入安全校验：长度、空、提示词注入/危险词拦截（拦截时抛 4007）
    text = sanitize_text(body.content, max_len=1024)

    def gen():
        for ev in agent_service.run(user_id, body.conversation_id, text):
            yield _sse(ev)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )