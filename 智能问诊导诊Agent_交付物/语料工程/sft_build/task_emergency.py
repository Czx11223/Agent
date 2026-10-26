# -*- coding: utf-8 -*-
"""构建 emergency 任务的 SFT 样本：合成急重症主诉 → Agent 拦截并提示急诊。

teacher 逻辑（全合成）：
- 从 EMERGENCY_KEYWORDS × 场景模板造句
- action = "emergency"
- comfort = "请保持冷静"
- question = EMERGENCY_TEMPLATE
- slots = {}（急诊不采集槽位）
"""
import json
import random

from config import SYSTEM_PROMPT, EMERGENCY_KEYWORDS, EMERGENCY_TEMPLATE, N_EMERGENCY


# 场景模板：{keyword} 占位由急诊关键词填充
SCENE_TEMPLATES = [
    "突然{kw}，已经持续好一会儿了，感觉越来越严重",
    "{kw}，浑身出冷汗，请问我该怎么办",
    "我现在{kw}，很难受，是不是很严重",
    "家人说{kw}，我不确定要不要去医院",
    "{kw}，伴有头晕和心慌，请帮帮我",
    "从刚才开始{kw}，一直没缓解",
    "{kw}，脸色发白，手脚冰凉",
    "老人{kw}，我们很担心",
    "半夜突然{kw}，不知道该不该打120",
    "{kw}，已经持续半小时了没有好转",
]

# 额外合成模板（不用 keyword 占位，直接写场景）
DIRECT_SCENES = [
    "胸口剧烈疼痛，喘不上气，出冷汗",
    "突然肚子剧痛，脸色发白，满腹拒按",
    "咳了不少血，还有头晕",
    "刚才晕倒没意识，醒来很虚弱",
    "吃虾后全身皮疹加呼吸急促",
    "呕吐大量鲜血，人很虚弱",
    "突然昏迷不省人事，叫不醒",
    "心前区压榨样疼痛，向左肩放射",
    "大量便血，头晕心慌",
    "孩子抽搐，意识不清",
]


def _build_user_prompt(text: str) -> str:
    return json.dumps(
        {"当前用户消息": text, "目前已采集槽位": {}, "任务": "请按规则继续追问或生成报告"},
        ensure_ascii=False,
    )


def _build_assistant() -> str:
    return json.dumps(
        {
            "action": "emergency",
            "comfort": "请保持冷静",
            "question": EMERGENCY_TEMPLATE,
            "slots": {
                "main_symptom": "", "body_part": "", "duration": "",
                "accompanying_symptom": "", "past_history": "", "allergy_history": "",
            },
        },
        ensure_ascii=False,
    )


def build_emergency(n: int = N_EMERGENCY, seed: int = 42) -> list[dict]:
    """合成急重症主诉样本。"""
    random.seed(seed)
    texts: list[str] = []
    # 用关键词 × 模板生成
    for kw in EMERGENCY_KEYWORDS:
        for tpl in SCENE_TEMPLATES:
            texts.append(tpl.replace("{kw}", kw))
    # 加入直接场景
    texts.extend(DIRECT_SCENES)

    # 循环采样直到达到 n
    while len(texts) < n:
        kw = random.choice(EMERGENCY_KEYWORDS)
        tpl = random.choice(SCENE_TEMPLATES)
        texts.append(tpl.replace("{kw}", kw))

    random.shuffle(texts)
    samples: list[dict] = []
    for text in texts[:n]:
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
