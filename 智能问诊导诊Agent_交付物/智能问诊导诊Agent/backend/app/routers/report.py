import json

from fastapi import APIRouter, Depends

from ..core.errors import ApiError, NOT_FOUND
from ..core.security import get_current_user
from ..db.db import query_one

router = APIRouter()


def _get_report(cid: int, user_id: int):
    r = query_one(
        "SELECT * FROM pre_diagnose_report WHERE conversation_id=? AND user_id=?",
        (cid, user_id),
    )
    if not r:
        raise ApiError(NOT_FOUND, "报告尚未生成，请先完成问诊", http_status=404)
    return r


@router.get("/reports/{conversation_id}")
def get_report(conversation_id: int, user_id: int = Depends(get_current_user)):
    r = _get_report(conversation_id, user_id)
    return {
        "chief_complaint": r["chief_complaint"],
        "present_illness": r["present_illness"],
        "allergy_history": r["allergy_history"],
        "past_history": r["past_history"],
        "recommend_dept_top3": r["recommend_dept_top3"],
        "disclaimer": r["disclaimer"],
        "created_at": r["created_at"],
    }


@router.get("/reports/{conversation_id}/export")
def export_report(conversation_id: int, user_id: int = Depends(get_current_user)):
    r = _get_report(conversation_id, user_id)
    try:
        depts = json.loads(r["recommend_dept_top3"]) if r["recommend_dept_top3"] else []
    except Exception:
        depts = []
    dept_lines = "\n".join(
        f"{i + 1}. {d.get('dept', '')}" + (f"：{d.get('reason', '')}" if d.get("reason") else "")
        for i, d in enumerate(depts)
    )
    content = (
        "# 预问诊报告\n\n"
        f"## 主诉\n{r['chief_complaint'] or '未提供'}\n\n"
        f"## 现病史\n{r['present_illness'] or '未提供'}\n\n"
        f"## 过敏史\n{r['allergy_history'] or '无已知过敏'}\n\n"
        f"## 既往史\n{r['past_history'] or '未提供'}\n\n"
        f"## 科室推荐\n{dept_lines}\n\n"
        f"> {r['disclaimer'] or ''}\n"
    )
    return {"content": content}