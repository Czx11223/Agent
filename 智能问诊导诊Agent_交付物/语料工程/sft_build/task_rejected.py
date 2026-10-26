# -*- coding: utf-8 -*-
"""构建 rejected 任务的 SFT 样本：合成越界请求 → Agent 拒答并给出免责说明。

teacher 逻辑（全合成）：
- 用 PRESCRIPTION_WORDS / DIAGNOSIS_WORDS 造句
- action = "rejected"
- question = REJECTED_TEMPLATE
- slots = {}
"""
import json
import random

from config import SYSTEM_PROMPT, REJECTED_TEMPLATE, N_REJECTED


# 越界请求模板（处方/用药类）
PRESC_REQUESTS = [
    "帮我开点阿莫西林",
    "我想让你给我开点奥美拉唑",
    "能不能给我开个处方，我想买布洛芬",
    "我应该吃多少对乙酰氨基酚？",
    "请给我开一盒连花清瘟",
    "帮我开点头孢吧",
    "我想开点二甲双胍降糖药",
    "能不能给我开点止疼片",
    "我想让你开点藿香正气水",
    "请给我开点板蓝根冲剂",
    "帮我开一疗程的左氧氟沙星",
    "我想开点降压药",
    "请开点抗病毒药给我",
    "我想让你开中药方",
    "帮我开点阿奇霉素",
    "我想开点胰岛素",
    "能不能给我开一盒莫沙必利",
    "帮我开点吗丁啉",
    "我想开点达喜",
    "请给我开维生素C片",
]

# 越界请求模板（诊断类）
DIAG_REQUESTS = [
    "我是不是得了胃癌？",
    "帮我确诊一下我是什么病",
    "你给我诊断结果是什么？",
    "我这是不是确诊为肺炎？",
    "你告诉我这就是得了什么病",
    "临床上典型症状是这样，我得了这个病对吧？",
    "帮我看看病理结果",
    "你确定我就是得了这个病吗？",
    "我的病灶在哪里？",
    "我是不是就是得了肝癌？",
    "你帮我确诊一下",
    "这个病是不是就是典型的？",
    "我得了什么病你直接告诉我",
    "你给我下个诊断结果",
    "这是不是什么综合征？",
]

# 组合模板（更自然）
COMBO_REQUESTS = [
    "医生我咳嗽三天了，帮我开点药吧",
    "我胃痛反酸，请给我开个处方",
    "孩子发烧了，能不能开点退烧药",
    "我头痛好几天了，帮我看看是不是得了什么病",
    "请帮我确诊是不是高血压",
    "我想开点治咳嗽的药",
    "帮我开点治拉肚子的药",
    "我胸口疼，是不是心梗？帮我确诊",
]


def _build_user_prompt(text: str) -> str:
    return json.dumps(
        {"当前用户消息": text, "目前已采集槽位": {}, "任务": "请按规则继续追问或生成报告"},
        ensure_ascii=False,
    )


def _build_assistant() -> str:
    return json.dumps(
        {
            "action": "rejected",
            "comfort": "",
            "question": REJECTED_TEMPLATE,
            "slots": {
                "main_symptom": "", "body_part": "", "duration": "",
                "accompanying_symptom": "", "past_history": "", "allergy_history": "",
            },
        },
        ensure_ascii=False,
    )


def build_rejected(n: int = N_REJECTED, seed: int = 42) -> list[dict]:
    """合成越界请求样本。"""
    random.seed(seed)
    all_reqs = PRESC_REQUESTS + DIAG_REQUESTS + COMBO_REQUESTS
    # 循环采样到 n
    while len(all_reqs) < n:
        all_reqs = all_reqs * 2
    random.shuffle(all_reqs)

    samples: list[dict] = []
    for text in all_reqs[:n]:
        samples.append(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": _build_user_prompt(text)},
                    {"role": "assistant", "content": _build_assistant()},
                ]
            }
        )
    return samples
