# -*- coding: utf-8 -*-
"""构建 ask 任务的 SFT 样本：患者输入主诉 → Agent 追问下一个缺失槽位。

teacher 逻辑：
- slots = slot_filler.extract_slots(patient_complaint)
- question = slot_filler.pick_next_question(slots)  # 按规则选下一个缺失项模板
- comfort = 安抚语 if SOOTHE_RE 命中 else ""
- action = "ask"
"""
import csv
import json
import random

from config import SYSTEM_PROMPT, SOOTHE_RE, CLEANED_CSV, N_ASK
from slot_filler import extract_slots, pick_next_question, filled_count


SOOTHE_TEXT = "听到您的不适，先别着急，我们一步一步来。"


def _build_user_prompt(text: str) -> str:
    return json.dumps(
        {"当前用户消息": text, "目前已采集槽位": {}, "任务": "请按规则继续追问或生成报告"},
        ensure_ascii=False,
    )


def _build_assistant(slots: dict, text: str) -> str:
    comfort = SOOTHE_TEXT if SOOTHE_RE.search(text) else ""
    question = pick_next_question(slots)
    return json.dumps(
        {
            "action": "ask",
            "comfort": comfort,
            "question": question,
            "slots": slots,
        },
        ensure_ascii=False,
    )


def build_ask(n: int = N_ASK, seed: int = 42) -> list[dict]:
    """从 cleaned_dialogue.csv 抽样构建 ask 任务样本。"""
    random.seed(seed)
    pool: list[str] = []
    with open(CLEANED_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("filter_reason"):
                continue
            text = (row.get("patient_complaint") or "").strip()
            if len(text) < 10:
                continue
            pool.append(text)

    random.shuffle(pool)
    samples: list[dict] = []
    for text in pool:
        if len(samples) >= n:
            break
        slots = extract_slots(text)
        # 至少要有 1 个槽位可抽（否则主诉太模糊，放残缺用例）
        if filled_count(slots) < 1:
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
