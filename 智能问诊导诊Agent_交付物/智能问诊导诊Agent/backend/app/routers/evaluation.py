from fastapi import APIRouter, Depends

from ..core.security import get_current_user
from ..db.db import execute
from ..schemas import EvaluationIn

router = APIRouter()


@router.post("/evaluation")
def write_evaluation(body: EvaluationIn, user_id: int = Depends(get_current_user)):
    execute(
        "INSERT INTO evaluation(conversation_id, user_id, case_id, judge_result, score, detail) "
        "VALUES(?,?,?,?,?,?)",
        (
            body.conversation_id, user_id, body.case_id,
            body.judge_result, body.score, body.detail,
        ),
    )
    return {"ok": True}