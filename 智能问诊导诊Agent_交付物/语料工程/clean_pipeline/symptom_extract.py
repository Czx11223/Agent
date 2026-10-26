# -*- coding: utf-8 -*-
"""
从清洗后的问诊语料抽取症状词表，并统计"症状->科室"共现频次。

用法：
    python symptom_extract.py --input cleaned_dialogue.csv --out symptom_lexicon.csv
"""
import argparse
import csv
import re

# 预置症状词典（按系统可扩充；仅用于演示的种子词表）
SEED_LEXICON = {
    # 通用
    "发热": ["发热", "发烧", "低烧", "高热", "体温高"],
    "头痛": ["头痛", "头疼", "偏头痛", "太阳穴疼"],
    "咳嗽": ["咳嗽", "干咳", "咳痰", "痰多", "夜间咳"],
    "乏力": ["乏力", "没精神", "疲劳", "容易累"],
    # 消化
    "胃痛": ["胃痛", "胃胀", "反酸", "烧心", "恶心", "呕吐", "嗳气"],
    "腹痛": ["腹痛", "肚子疼", "腹部疼痛", "脐周疼"],
    "腹泻": ["腹泻", "拉肚子", "大便稀", "水样便"],
    "便秘": ["便秘", "大便干", "排不出"],
    # 呼吸
    "胸痛": ["胸痛", "胸口疼", "胸闷", "胸前压榨"],
    "呼吸困难": ["呼吸困难", "喘不上气", "气促", "窒息感"],
    # 骨科
    "腰痛": ["腰痛", "腰疼", "腰部疼痛"],
    "关节痛": ["关节痛", "关节疼", "膝痛", "肩膀痛", "颈椎疼"],
    # 皮肤
    "皮疹": ["皮疹", "红疹", "红疙瘩", "红斑", "风团"],
    "瘙痒": ["瘙痒", "很痒", "发痒", "越抓越多"],
    # 眼科
    "眼干涩": ["眼干", "干涩", "眼胀", "眼酸", "视力模糊"],
    "眼红": ["眼红", "结膜充血", "眼红血丝"],
    # 泌尿/男科
    "尿频": ["尿频", "尿急", "小便疼", "排尿痛"],
    # 神经
    "眩晕": ["晕", "头晕", "天旋地转", "眩晕"],
    # 妇科
    "月经不调": ["月经不调", "经期紊乱", "痛经", "月经量少"],
    # 儿科
    "哭闹/吐奶": ["吐奶", "哭闹", "厌奶", "夜啼"],
}


def build_matcher():
    pairs = []
    seen = set()
    for canon, terms in SEED_LEXICON.items():
        for t in terms:
            if t and t not in seen:
                pairs.append((t, canon))
                seen.add(t)
    return pairs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", default="symptom_lexicon.csv")
    ap.add_argument("--map-out", default="symptom_dept_map.csv", help="症状-科室映射表输出")
    args = ap.parse_args()

    matcher = build_matcher()
    # freq[canon] = {"count": , "depts": Counter}
    freq = {}

    with open(args.input, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("filter_reason"):          # 只统计保留样本
                continue
            text = f"{row.get('patient_complaint','')} {row.get('doctor_followup','')} {row.get('patient_fill','')}"
            dept = row.get("source_department", "") or "未知"
            for term, canon in matcher:
                if term in text:
                    d = freq.setdefault(canon, {"count": 0, "depts": {}})
                    d["count"] += 1
                    d["depts"][dept] = d["depts"].get(dept, 0) + 1

    with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["symptom_key", "判定词", "出现次数", "主要关联科室"])
        for canon, d in sorted(freq.items(), key=lambda x: -x[1]["count"]):
            top_dept = max(d["depts"].items(), key=lambda x: x[1])[0]
            terms = [t for t, c in matcher if c == canon]
            w.writerow([canon, "、".join(terms[:4]), d["count"], top_dept])

    # 症状-科室映射表：每个症状给出 Top-3 关联科室及其共现次数
    with open(args.map_out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["symptom_key", "出现次数", "科室_1", "共现_1", "科室_2", "共现_2", "科室_3", "共现_3"])
        for canon, d in sorted(freq.items(), key=lambda x: -x[1]["count"]):
            top = sorted(d["depts"].items(), key=lambda x: -x[1])[:3]
            row = [canon, d["count"]]
            for dept, n in top:
                row += [dept, n]
            while len(row) < 8:
                row += ["", ""]
            w.writerow(row)

    print(f"[done] 症状词表 -> {args.out}，共 {len(freq)} 个症状键")
    print(f"[done] 症状-科室映射 -> {args.map_out}")


if __name__ == "__main__":
    main()