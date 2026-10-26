# -*- coding: utf-8 -*-
"""构建 report 任务的 SFT 样本：患者输入信息充分 → Agent 生成报告并推荐科室。

teacher 逻辑：
- slots = slot_filler.extract_slots(patient_complaint)
- 要求 filled_count(slots) >= 4（主诉+时间+至少2其他要素）
- action = "report"
- question = REPORT_DONE_QUESTION
- recommend_top3 = recommend_top3(slots_text)  # 调用本地科室推荐
"""
import csv
import json
import random

from config import (
    SYSTEM_PROMPT, CLEANED_CSV, N_REPORT, DEPT_KEYWORDS, EMERGENCY_KEYWORDS,
    REPORT_DONE_QUESTION,
)
from slot_filler import extract_slots, filled_count


def recommend_top3(complaint: str, extra: str = "") -> list:
    """与 dept_map.recommend_top3 逻辑一致（内联以避免跨包导入）。"""
    corpus = f"{complaint} {extra}"
    scores: dict[str, int] = {}
    for dept, kws in DEPT_KEYWORDS.items():
        cnt = sum(1 for k in kws if k in corpus)
        if cnt:
            scores[dept] = cnt
    if not scores:
        return [{"dept": "内科全科", "reason": "未能明确指征，建议先挂全科/内科评估"}]
    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:3]
    return [{"dept": d, "reason": f"主诉含与{d}相关的症状（匹配 {c} 项）"} for d, c in ranked]


def is_emergency(text: str) -> bool:
    """与 dept_map.is_emergency 一致。"""
    return any(k in text for k in EMERGENCY_KEYWORDS)


def _build_user_prompt(text: str) -> str:
    return json.dumps(
        {"当前用户消息": text, "目前已采集槽位": {}, "任务": "请按规则继续追问或生成报告"},
        ensure_ascii=False,
    )


def _build_assistant(slots: dict, text: str) -> str:
    # 构造完整报告：slots + recommend_top3
    slots_text = " ".join(v for v in slots.values() if v)
    top3 = recommend_top3(slots_text)
    return json.dumps(
        {
            "action": "report",
            "comfort": "",
            "question": REPORT_DONE_QUESTION,
            "slots": slots,
            "recommend_top3": top3,
        },
        ensure_ascii=False,
    )


def build_report(n: int = N_REPORT, seed: int = 42) -> list[dict]:
    """从 cleaned_dialogue.csv 抽样构建 report 任务样本。"""
    random.seed(seed)
    pool: list[str] = []
    with open(CLEANED_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("filter_reason"):
                continue
            text = (row.get("patient_complaint") or "").strip()
            if len(text) < 10:
                continue
            # 急重症样本不入 report（应走 emergency）
            if is_emergency(text):
                continue
            pool.append(text)

    random.shuffle(pool)
    samples: list[dict] = []
    for text in pool:
        if len(samples) >= n:
            break
        slots = extract_slots(text)
        # report 需要信息充分：至少 4 个槽位（含 main_symptom + duration）
        if filled_count(slots) < 4:
            continue
        if not slots.get("main_symptom") or not slots.get("duration"):
            continue
        samples.append(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": _build_user_prompt(text)},
                    {"role": "assistant", "content": _build_assistant(slots, text)},
                ]
            }
        )
    return samples
