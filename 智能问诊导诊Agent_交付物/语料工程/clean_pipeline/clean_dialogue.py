# -*- coding: utf-8 -*-
"""
医疗问诊对话语料清洗
适用数据：天池 Chinese Medical Dialogue 数据集（YouTaoBaBa/Chinese-Dialogue-Dataset 索引指向）
原始字段：department / title / ask / answer（单条问答）
产出：标准化对话样本 CSV（患者主诉 / 医生追问 / 患者补充 / 科室 / 是否急重症）

用法：
    python clean_dialogue.py --input <dir|zip|csv> --out out_cleaned.csv
    python clean_dialogue.py --demo                  # 用内置模拟样例演示
"""
import argparse
import csv
import io
import os
import re
import sys

from blacklist import (
    PRESCRIPTION_WORDS, DIAGNOSIS_WORDS, EMERGENCY_WORDS,
    FOLLOWUP_QUESTION_HINT, PII_PATTERNS, SKIP_MARKERS,
)

OUT_COLS = [
    "case_id", "source_department", "patient_complaint",  # 患者主诉
    "doctor_followup",  # 医生追问
    "patient_fill",     # 患者补充（可为空：原始单轮样本无多轮）
    "is_emergency",     # 1/0
    "filter_reason",    # 空=保留；否则说明被拒原因
]


def desensitize(text: str) -> str:
    """对疑似个人隐私信息做正则脱敏。"""
    for pat, repl in PII_PATTERNS:
        text = re.sub(pat, repl, text)
    return text


def hit_any(text: str, words) -> bool:
    return any(w in text for w in words)


def is_followup(doctor_text: str) -> bool:
    """医生回复是否更像'追问澄清'（问句）而非'医嘱/解答'。"""
    txt = doctor_text.strip()
    if any(h in txt for h in FOLLOWUP_QUESTION_HINT):
        return True
    return False


def extract_complaint(ask: str, max_len: int = 40) -> str:
    """从患者提问里提取主诉短句：优先句号/逗号前的主诉，过长则截断。"""
    t = re.split(r"[。！？!?；;，,]", ask.strip())
    for seg in t:
        seg = seg.strip()
        if 3 <= len(seg) <= max_len:
            return seg
    return ask.strip()[:max_len]


def normalize_csv_reader(lines):
    """尽量按 UTF-8 尝试，失败回退 gbk（国产医患数据常见编码）。"""
    for enc in ("utf-8", "gbk", "utf-8-sig"):
        try:
            text = lines if isinstance(lines, str) else "".join(lines)
            return text, enc
        except Exception:
            continue
    return lines, "utf-8"


def _decode_bytes(raw: bytes) -> str:
    """编码回退：优先严格解码；否则在 utf-8 / gbk 容错解码中选替换字符最少者。

    天池医患数据多为 GBK，但个别文件可能含极少量非法字节（导致整文件严格
    GBK 解码失败）。此时用 errors='replace' 分别尝试，保留损坏最少的解码结果。
    """
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    best, best_err = None, len(raw) + 1
    for enc in ("utf-8", "gbk"):
        s = raw.decode(enc, errors="replace")
        err = s.count("\ufffd")
        if err < best_err:
            best, best_err = s, err
    return best if best is not None else raw.decode("utf-8", errors="replace")


def _read_text(path: str) -> str:
    with open(path, "rb") as f:
        return _decode_bytes(f.read())


def read_records(input_path: str) -> list[dict]:
    """读取 csv/zip/目录下的 csv，返回 {department,title,ask,answer} 字典列表。"""
    streams = []
    if input_path.endswith(".zip"):
        import zipfile
        with zipfile.ZipFile(input_path) as z:
            for n in z.namelist():
                if n.lower().endswith(".csv"):
                    streams.append(io.StringIO(_decode_bytes(z.read(n))))
    elif os.path.isdir(input_path):
        for dp, _, fs in os.walk(input_path):
            for f in fs:
                if f.lower().endswith(".csv"):
                    streams.append(io.StringIO(_read_text(os.path.join(dp, f))))
    elif input_path.lower().endswith(".csv"):
        streams.append(io.StringIO(_read_text(input_path)))
    else:
        raise SystemExit(f"不支持的输入: {input_path}")

    rows = []
    for fh in streams:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append({
                "department": (row.get("department") or "").strip(),
                "title": (row.get("title") or "").strip(),
                "ask": (row.get("ask") or "").strip(),
                "answer": (row.get("answer") or "").strip(),
            })
        fh.close()
    return rows


def clean_one(idx: int, r: dict) -> dict:
    """清洗单条记录：黑名单过滤 + 脱敏 + 主诉/追问拆分 + 急重症标记。"""
    ask = desensitize(r["ask"])
    answer = desensitize(r["answer"])
    reason = ""

    emergency = "1" if hit_any((ask or "") + " " + (answer or ""), EMERGENCY_WORDS) else "0"

    if not ask or not answer or any(m in ask or m in answer for m in SKIP_MARKERS):
        reason = "empty_or_broken"
    elif emergency == "0":
        # 急重症样本豁免处方/诊断过滤（用于急诊识别），仅非急重症才执行
        if hit_any(answer, PRESCRIPTION_WORDS):
            reason = "prescription"          # 含处方/用药，禁止入库
        elif hit_any(answer, DIAGNOSIS_WORDS):
            reason = "diagnosis"             # 含有诊断断言，禁止入库
    if len(answer) < 4 or len(ask) < 2:
        reason = "too_short"

    if reason:
        return dict(case_id=f"dropped_{idx:06d}", source_department=r["department"],
                    patient_complaint=ask, doctor_followup=answer, patient_fill="",
                    is_emergency=emergency, filter_reason=reason)

    complaint = extract_complaint(ask)
    if is_followup(answer):
        followup, fill = answer, ""       # 医生在追问 → 归医生追问
    else:
        # 无追问句的医生回复：作为可参考说明放入补充栏，但不当作多轮追问样本
        followup, fill = "", answer
    return dict(case_id=f"C{idx:06d}", source_department=r["department"],
                patient_complaint=complaint, doctor_followup=followup, patient_fill=fill,
                is_emergency=emergency, filter_reason=reason)


def write_out(rows, out_path):
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=OUT_COLS)
        w.writeheader()
        w.writerows(rows)
    kept = [x for x in rows if not x["filter_reason"]]
    reasons = {}
    for x in rows:
        if x["filter_reason"]:
            reasons[x["filter_reason"]] = reasons.get(x["filter_reason"], 0) + 1
    print(f"[done] 输出 {out_path}")
    print(f"[stat] 总记录={len(rows)}  保留(可入库)={len(kept)}  急重症标记={sum(r['is_emergency']=='1' for r in kept)}")
    print(f"[stat] 拒绝分布={reasons or '无'}")


def demo_rows():
    """内置模拟样例（非真实患者数据）：用于演示清洗效果与格式。"""
    d = [
        ("内科", "反复头痛", "我最近三天总是头痛，特别是右边太阳穴，还有一点恶心", "你好，请问头痛是持续性的还是阵发性的？每次大概持续多久？有没有发烧或呕吐？"),
        ("消化内科", "胃不舒服", "吃饭后胃胀、反酸，已经一个多月了，晚上睡不好", "建议口服奥美拉唑胶囊，一天一次，饭前服用。"),
        ("骨科", "腰疼", "搬东西后腰部疼痛，弯腰时更明显", "请问疼痛有向腿部放射吗？之前拍过片子吗？平时有没有久坐？"),
        ("皮肤科", "起红疹", "胳膊上起了一片红疹，很痒，越抓越多", "红疹出现多久了？最近有没有接触过过敏原或吃过海鲜？"),
        ("急诊", "胸口疼", "胸口剧烈疼痛，喘不上气，出冷汗", "你的情况属于高危症状，请立即前往急诊或拨打120，不要自行活动。"),
        ("内科", "尿路不舒服", "我妈她最近2天总说小便疼，尿频，要不要紧", "可能是尿路感染，先多喝水，如症状持续可去泌尿科复查，暂不用药。"),
        ("儿科", "小孩咳嗽", "孩子咳嗽三天了，夜里咳得厉害，睡不好", "请问孩子体温多少？咳嗽是干咳还是有痰？做过过敏原检测吗？"),
        ("呼吸内科", "感冒流鼻涕", "流清鼻涕、打喷嚏两天，轻微低烧", "建议多休息多喝水；若体温持续超过38.5℃需复查。"),
        ("不明", "不知道", "", "你好，请问有什么可以帮您？"),
    ]
    return [dict(department=a, title=t, ask=b, answer=c) for a, t, b, c in d]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", help="csv / zip / 目录")
    ap.add_argument("--out", default="cleaned_dialogue.csv")
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()

    if args.demo:
        rows = [clean_one(i, r) for i, r in enumerate(demo_rows())]
        write_out(rows, args.out)
    else:
        if not args.input:
            raise SystemExit("请提供 --input 或使用 --demo")
        write_out([clean_one(i, r) for i, r in enumerate(read_records(args.input))], args.out)


if __name__ == "__main__":
    main()