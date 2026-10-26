# -*- coding: utf-8 -*-
"""SFT 数据集构建主入口：拼接 4 类任务样本 → 切分 train/dev → 输出 JSONL。

用法：
    python build_sft.py --input ../cleaned_dialogue.csv \
        --out output/sft_train.jsonl \
        --dev-out output/sft_dev.jsonl \
        --eval-out output/eval_cases.csv
"""
import argparse
import json
import os
import random
import sys

from config import (
    N_ASK, N_REPORT, N_EMERGENCY, N_REJECTED, DEV_RATIO,
    OUTPUT_DIR, ensure_output_dir,
)
from task_ask import build_ask
from task_report import build_report
from task_emergency import build_emergency
from task_rejected import build_rejected


def write_jsonl(samples: list[dict], path: str):
    with open(path, "w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")


def split_dev(samples: list[dict], dev_ratio: float = DEV_RATIO) -> tuple[list[dict], list[dict]]:
    """按比例切分 train / dev。"""
    n_dev = int(len(samples) * dev_ratio)
    if n_dev < 1:
        return samples, []
    random.shuffle(samples)
    return samples[n_dev:], samples[:n_dev]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=None, help="（保留参数，输入路径已内联在 config）")
    ap.add_argument("--out", default=os.path.join(OUTPUT_DIR, "sft_train.jsonl"))
    ap.add_argument("--dev-out", default=os.path.join(OUTPUT_DIR, "sft_dev.jsonl"))
    ap.add_argument("--eval-out", default=os.path.join(OUTPUT_DIR, "eval_cases.csv"))
    ap.add_argument("--n-ask", type=int, default=N_ASK)
    ap.add_argument("--n-report", type=int, default=N_REPORT)
    ap.add_argument("--n-emergency", type=int, default=N_EMERGENCY)
    ap.add_argument("--n-rejected", type=int, default=N_REJECTED)
    args = ap.parse_args()

    ensure_output_dir()

    print("[1/4] 构建 ask 任务样本...")
    ask_samples = build_ask(n=args.n_ask)
    print(f"      ask: {len(ask_samples)} 条")

    print("[2/4] 构建 report 任务样本...")
    report_samples = build_report(n=args.n_report)
    print(f"      report: {len(report_samples)} 条")

    print("[3/4] 构建 emergency 任务样本...")
    emergency_samples = build_emergency(n=args.n_emergency)
    print(f"      emergency: {len(emergency_samples)} 条")

    print("[4/4] 构建 rejected 任务样本...")
    rejected_samples = build_rejected(n=args.n_rejected)
    print(f"      rejected: {len(rejected_samples)} 条")

    # 各任务切分 train/dev
    all_train: list[dict] = []
    all_dev: list[dict] = []
    for name, samples in [
        ("ask", ask_samples),
        ("report", report_samples),
        ("emergency", emergency_samples),
        ("rejected", rejected_samples),
    ]:
        train, dev = split_dev(samples)
        all_train.extend(train)
        all_dev.extend(dev)
        print(f"  {name}: train={len(train)} dev={len(dev)}")

    random.shuffle(all_train)
    random.shuffle(all_dev)

    write_jsonl(all_train, args.out)
    write_jsonl(all_dev, args.dev_out)

    print(f"\n[done] 训练集 -> {args.out} ({len(all_train)} 行)")
    print(f"[done] 验证集 -> {args.dev_out} ({len(all_dev)} 行)")

    # 构建报告
    report = {
        "task_counts": {
            "ask": len(ask_samples),
            "report": len(report_samples),
            "emergency": len(emergency_samples),
            "rejected": len(rejected_samples),
        },
        "total_train": len(all_train),
        "total_dev": len(all_dev),
    }
    report_path = os.path.join(OUTPUT_DIR, "build_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[done] 构建报告 -> {report_path}")


if __name__ == "__main__":
    main()
