# -*- coding: utf-8 -*-
"""SFT 数据集质量校验：黑名单复核 / JSONL 合法性 / 槽位一致性 / 隐私扫描 / 配比校验。

用法：
    python validate_jsonl.py --input output/sft_train.jsonl --report output/build_report.json
"""
import argparse
import json
import os
import re
import sys

# 引入黑名单（添加 clean_pipeline 到 path）
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "clean_pipeline"))
from blacklist import (
    PRESCRIPTION_WORDS, DIAGNOSIS_WORDS, PII_PATTERNS, SKIP_MARKERS,
)  # noqa: E402

from config import SLOT_KEYS  # noqa: E402

VALID_ACTIONS = {"ask", "emergency", "rejected", "report"}
PRESC_SET = set(PRESCRIPTION_WORDS)
DIAG_SET = set(DIAGNOSIS_WORDS)
PII_COMPILED = [(re.compile(p), r) for p, r in PII_PATTERNS]


def validate_line(line: str, line_no: int) -> dict:
    """校验单行 JSONL，返回 {ok: bool, errors: [str], warnings: [str], task: str}。"""
    result = {"ok": True, "errors": [], "warnings": [], "task": "?"}
    line = line.strip()
    if not line:
        return {**result, "ok": False, "errors": ["空行"]}

    # 1) JSON 解析
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as e:
        return {**result, "ok": False, "errors": [f"JSON解析失败: {e}"]}

    # 2) messages 结构
    msgs = obj.get("messages")
    if not isinstance(msgs, list) or len(msgs) != 3:
        return {**result, "ok": False, "errors": ["messages 不是3元素列表"]}

    roles = [m.get("role") for m in msgs]
    if roles != ["system", "user", "assistant"]:
        return {**result, "ok": False, "errors": [f"角色顺序错误: {roles}"]}

    user_text = msgs[1].get("content", "")
    asst_text = msgs[2].get("content", "")

    # 3) assistant 输出是合法 JSON
    try:
        asst = json.loads(asst_text)
    except json.JSONDecodeError as e:
        return {**result, "ok": False, "errors": [f"assistant 内容非合法JSON: {e}"]}

    # 4) action 合法
    action = asst.get("action", "")
    if action not in VALID_ACTIONS:
        return {**result, "ok": False, "errors": [f"action={action} 不在 {VALID_ACTIONS}"]}
    result["task"] = action

    # 5) slots 含全部 6 key
    slots = asst.get("slots", {})
    if not isinstance(slots, dict):
        return {**result, "ok": False, "errors": ["slots 不是 dict"]}
    for k in SLOT_KEYS:
        if k not in slots:
            result["ok"] = False
            result["errors"].append(f"slots 缺 key: {k}")
    # emergency/rejected 允许 slots={} 或全空
    if action in ("emergency", "rejected"):
        pass  # slots 可空
    # ask/report 的 question 非空
    if action in ("ask", "report") and not asst.get("question", "").strip():
        result["ok"] = False
        result["errors"].append("question 为空")

    # 6) 黑名单复核：assistant 内容不得含处方/诊断词
    for w in PRESC_SET:
        if w in asst_text:
            # rejected 任务本身就是越界拒答，允许"阿莫西林"等在 user 里，但 assistant 不应含
            result["ok"] = False
            result["errors"].append(f"assistant 命中处方词: {w}")
            break
    for w in DIAG_SET:
        if w in asst_text:
            result["ok"] = False
            result["errors"].append(f"assistant 命中诊断词: {w}")
            break

    # 7) 隐私扫描：user/assistant 不得含明文隐私
    for content_label, content in [("user", user_text), ("assistant", asst_text)]:
        for pat, repl in PII_COMPILED:
            if pat.search(content):
                result["ok"] = False
                result["errors"].append(f"{content_label} 命中隐私: {pat.pattern[:20]}")
                break

    return result


def validate_file(path: str) -> dict:
    """校验整个 JSONL 文件，返回统计报告。"""
    stats = {
        "total": 0, "ok": 0, "bad": 0,
        "task_counts": {"ask": 0, "report": 0, "emergency": 0, "rejected": 0},
        "errors_by_type": {},
        "bad_lines": [],
    }
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            r = validate_line(line, i)
            stats["total"] += 1
            stats["task_counts"][r["task"]] = stats["task_counts"].get(r["task"], 0) + 1
            if r["ok"]:
                stats["ok"] += 1
            else:
                stats["bad"] += 1
                for e in r["errors"][:1]:  # 只记第一个错误
                    stats["errors_by_type"][e] = stats["errors_by_type"].get(e, 0) + 1
                if len(stats["bad_lines"]) < 10:
                    stats["bad_lines"].append({"line": i, "errors": r["errors"]})
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--report", default=None)
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"[error] 文件不存在: {args.input}")
        sys.exit(1)

    print(f"[validate] 校验 {args.input} ...")
    stats = validate_file(args.input)

    print(f"\n=== 校验报告 ===")
    print(f"总行数: {stats['total']}")
    print(f"合法:   {stats['ok']}")
    print(f"非法:   {stats['bad']}")
    print(f"任务分布: {stats['task_counts']}")
    if stats["bad"] > 0:
        print(f"\n错误类型分布:")
        for e, c in sorted(stats["errors_by_type"].items(), key=lambda x: -x[1]):
            print(f"  {c}x  {e}")
        print(f"\n前10条坏样本行号: {[b['line'] for b in stats['bad_lines']]}")

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        print(f"\n[done] 报告 -> {args.report}")

    if stats["bad"] > 0:
        print(f"\n[warn] 有 {stats['bad']} 条非法样本，请检查")
        sys.exit(1)
    else:
        print(f"\n[ok] 全部 {stats['ok']} 条样本合法")


if __name__ == "__main__":
    main()
