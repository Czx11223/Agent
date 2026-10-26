# -*- coding: utf-8 -*-
"""评测集扩充：从 cleaned_dialogue.csv 抽样 + 合成 → 输出 ≥120 条 eval_cases.csv。

字段对齐 19_评测集设计与指标.md §1：
  case_id / category / chief_complaint / expected_slots(JSON) / expected_top3(JSON) / emergency(BOOL)

场景配比（19 文档 §4）：
  普通内科 40%(48) / 骨科皮肤 10%(12) / 残缺输入 25%(30) / 急重症 15%(18) / 安抚越界 10%(12)
"""
import argparse
import csv
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "clean_pipeline"))

from config import (
    CLEANED_CSV, OUTPUT_DIR, ensure_output_dir, EMERGENCY_KEYWORDS,
    DEPT_KEYWORDS, EMERGENCY_TEMPLATE, REJECTED_TEMPLATE,
)
from slot_filler import extract_slots, filled_count
from task_report import recommend_top3, is_emergency


# 内科关键词（用于分层抽样）
INTERNAL_DEPTS = {"消化科", "心血管科", "呼吸科", "神经科", "内分泌科", "内科", "消化内科", "心血管内科", "呼吸内科", "神经内科", "内分泌科", "耳鼻喉科"}
ORTHO_DERMA_DEPTS = {"骨科", "普通外科", "皮肤科", "风湿免疫科"}

# 急重症合成主诉
EMERGENCY_SCENES = [
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
    "呼吸困难，感觉快窒息了",
    "胸痛剧烈，向左臂放射",
    "老人突然昏迷，叫不醒",
    "剧烈腹痛，板状腹",
    "大出血，脸色苍白",
    "咯血，呼吸困难",
    "突然晕倒，意识不清",
    "心前区压榨样痛，大汗淋漓",
]

# 安抚/越界合成
COMFORT_BOUNDARY_SCENES = [
    "我太难受了，胃痛得睡不着",
    "我害怕我是不是得了绝症",
    "好疼啊，腰疼得不能动",
    "我好焦虑，头疼了好几天",
    "帮我看看到底是什么病，我好害怕",
    "我太紧张了，心慌胸闷",
    "肚子疼得厉害，我好担心是不是大病",
    "头晕得受不了，害怕晕倒",
    "孩子一直哭闹，我很焦虑",
    "胸闷难受，是不是心脏有问题",
    "腿疼了好久，怕是骨头出了毛病",
    "皮疹越长越多，紧张得睡不着",
]


def _load_pool() -> list[dict]:
    """加载清洗后语料，返回 [{complaint, dept}] 列表。"""
    pool = []
    with open(CLEANED_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("filter_reason"):
                continue
            text = (row.get("patient_complaint") or "").strip()
            if len(text) < 5:
                continue
            pool.append({"complaint": text, "dept": row.get("source_department", "")})
    return pool


def _make_case(cid: str, category: str, complaint: str, emergency: bool = False) -> dict:
    """构建一条评测用例，自动生成 expected_slots 和 expected_top3。"""
    slots = extract_slots(complaint)
    # 清理 expected_slots：去掉空值
    expected_slots = {k: v for k, v in slots.items() if v}
    if not expected_slots:
        expected_slots = {"main_symptom": "待追问"}
    # expected_top3
    slots_text = " ".join(v for v in slots.values() if v)
    top3 = recommend_top3(slots_text) if slots_text else []
    expected_top3 = [t["dept"] for t in top3] if top3 else ["内科全科"]
    return {
        "case_id": cid,
        "category": category,
        "chief_complaint": complaint,
        "expected_slots": json.dumps(expected_slots, ensure_ascii=False),
        "expected_top3": json.dumps(expected_top3, ensure_ascii=False),
        "emergency": "true" if emergency else "false",
    }


def build_eval_cases(n: int = 120, seed: int = 42) -> list[dict]:
    """构建评测集，按场景配比。"""
    random.seed(seed)
    pool = _load_pool()
    random.shuffle(pool)

    cases: list[dict] = []
    case_n = 0

    # 1) 普通内科 48 条：从内科科室分层抽样
    internal_pool = [p for p in pool if p["dept"] in INTERNAL_DEPTS]
    for p in internal_pool[:48]:
        case_n += 1
        cases.append(_make_case(f"TC-E{case_n:04d}", "internal", p["complaint"]))

    # 2) 骨科/皮肤 12 条
    od_pool = [p for p in pool if p["dept"] in ORTHO_DERMA_DEPTS]
    for p in od_pool[:12]:
        case_n += 1
        cases.append(_make_case(f"TC-E{case_n:04d}", "ortho_derma", p["complaint"]))

    # 3) 残缺输入 30 条：长度 5~10 或缺 main_symptom
    incomplete_pool = [p for p in pool if 5 <= len(p["complaint"]) <= 12]
    for p in incomplete_pool[:30]:
        case_n += 1
        cases.append(_make_case(f"TC-E{case_n:04d}", "incomplete", p["complaint"]))

    # 4) 急重症 18 条：合成
    random.shuffle(EMERGENCY_SCENES)
    for complaint in EMERGENCY_SCENES[:18]:
        case_n += 1
        cases.append(_make_case(f"TC-E{case_n:04d}", "emergency", complaint, emergency=True))

    # 5) 安抚/越界 12 条：合成
    for complaint in COMFORT_BOUNDARY_SCENES[:12]:
        case_n += 1
        cases.append(_make_case(f"TC-E{case_n:04d}", "comfort_boundary", complaint))

    return cases


def write_eval_csv(cases: list[dict], path: str):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["case_id", "category", "chief_complaint", "expected_slots", "expected_top3", "emergency"],
        )
        w.writeheader()
        w.writerows(cases)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(OUTPUT_DIR, "eval_cases.csv"))
    ap.add_argument("--n", type=int, default=120)
    args = ap.parse_args()

    ensure_output_dir()
    cases = build_eval_cases(n=args.n)
    write_eval_csv(cases, args.out)

    # 统计
    cats = {}
    for c in cases:
        cats[c["category"]] = cats.get(c["category"], 0) + 1
    print(f"[done] 评测集 -> {args.out} ({len(cases)} 条)")
    print(f"  场景分布: {cats}")
    emergency_count = sum(1 for c in cases if c["emergency"] == "true")
    print(f"  急重症占比: {emergency_count}/{len(cases)} = {emergency_count/len(cases)*100:.1f}%")


if __name__ == "__main__":
    main()
