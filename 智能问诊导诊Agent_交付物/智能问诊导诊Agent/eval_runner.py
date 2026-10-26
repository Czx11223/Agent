"""智能问诊导诊 Agent 评测 Runner（工程内可运行）。

用法（在 backend 依赖环境 backend/.venv312 下执行）：
    python eval_runner.py                      # 默认 llm 模式，全量评测集
    python eval_runner.py --mode llm --limit 30
    python eval_runner.py --mode rule          # 离线规则模式（不调用大模型，快）

评测 4 项任务书指标：
    ① 关键信息追问覆盖率   ② 报告字段完整率   ③ 科室推荐 Top3 准确率   ④ 平均响应时间
另附：急重症拦截准确率。
产物：evaluation/reports/metrics.json 与 evaluation/reports/评测报告.md
"""
import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE / "backend"
sys.path.insert(0, str(BACKEND))

from app.agent.pre_consult_agent import PreConsultAgent  # noqa: E402
from app.agent import dept_map  # noqa: E402
from app.core.errors import ApiError, LLM_ERROR  # noqa: E402

DEFAULT_CASES = HERE.parent / "语料工程" / "sft_build" / "output" / "eval_cases.csv"
OUT_DIR = HERE / "evaluation" / "reports"
MAX_TURNS = 10
MAX_PASSES = 6    # 降级用例的最大重跑轮次（等待网络恢复）
RETRY_WAIT = 90   # 每轮重跑前的等待秒数
PLACEHOLDER = {"待追问", "", "—", "-", "无", "未知"}


def _force_rule_mode():
    """把 LLM 调用强制置为失败，触发 Agent 本地规则降级，实现离线评测。"""
    import app.agent.pre_consult_agent as pca

    def _raiser(_msgs):
        raise ApiError(LLM_ERROR, "评测: rule 模式不调用大模型")

    pca.chat_json = _raiser


def _load_cases(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            rows.append({
                "case_id": r["case_id"],
                "category": r["category"],
                "chief_complaint": r["chief_complaint"],
                "expected_slots": json.loads(r["expected_slots"]),
                "expected_top3": json.loads(r["expected_top3"]),
                "emergency": str(r["emergency"]).strip().lower() == "true",
            })
    return rows


def _expected_values(case: dict) -> list[tuple[str, str]]:
    """返回需校验的真实期望槽位（(key, value)），剔除占位值。"""
    out = []
    for k, v in (case["expected_slots"] or {}).items():
        v = (v or "").strip()
        if v not in PLACEHOLDER:
            out.append((k, v))
    return out


def _run_case(case: dict) -> dict:
    agent = PreConsultAgent()
    answers = [v for _, v in _expected_values(case)]
    text = case["chief_complaint"]
    times, turns, action = [], 0, None
    for _ in range(MAX_TURNS):
        t0 = time.perf_counter()
        agent.reply(agent.user_msg(text))
        times.append(time.perf_counter() - t0)
        turns += 1
        action = (agent.last_decision or {}).get("action")
        if action in ("emergency", "rejected", "report"):
            break
        text = answers.pop(0) if answers else "暂时没有其他不舒服了"

    # 急重症/拒答用例：只评「拦截准确率」，不计追问覆盖率/报告完整率/Top3
    applicable = (not case["emergency"]) and action != "rejected"

    # ① 追问覆盖率：期望槽位是否被采集（同义表述与中文数字做等价归一后比对）
    exp = _expected_values(case)
    canon_slots = {k: dept_map.canonical_value(v) for k, v in agent.slots.items()}
    hits = 0
    for k, v in exp:
        cv = dept_map.canonical_value(v)
        if cv and (cv in canon_slots.get(k, "") or any(cv in s for s in canon_slots.values())):
            hits += 1
    coverage = (hits / len(exp)) if (applicable and exp) else None

    # ② 报告字段完整率 + ③ 科室 Top3 准确率（仅常规转诊病例）
    report = agent.build_report()
    fields = ["chief_complaint", "present_illness", "allergy_history", "past_history"]
    rec = json.loads(report["recommend_dept_top3"])
    rec_depts = [d["dept"] for d in rec]
    report_ok = all((report.get(f) or "").strip() for f in fields) if applicable else None
    top3_ok = (bool(case["expected_top3"]) and case["expected_top3"][0] in rec_depts) if applicable else None

    # 急重症拦截准确率
    emergency_ok = (action == "emergency") == case["emergency"]

    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "turns": turns,
        "avg_time": sum(times) / len(times) if times else 0.0,
        "action": action,
        "coverage": coverage,
        "report_ok": report_ok,
        "top3_ok": top3_ok,
        "rec_depts": rec_depts,
        "expected_top3": case["expected_top3"],
        "emergency_ok": emergency_ok,
        "expected_emergency": case["emergency"],
        "slots": dict(agent.slots),
        "degraded": bool(getattr(agent, "degraded", False)),  # 该用例是否发生 LLM 降级
        "_agent": agent,  # 临时持有，聚合后删除
    }


def _aggregate(records: list[dict], mode: str) -> dict:
    cov = [r["coverage"] for r in records if r["coverage"] is not None]
    coverage = sum(cov) / len(cov) if cov else 0.0
    rep = [r for r in records if r["report_ok"] is not None]
    report_rate = (sum(1 for r in rep if r["report_ok"]) / len(rep)) if rep else 0.0
    tp = [r for r in records if r["top3_ok"] is not None]
    top3_rate = (sum(1 for r in tp if r["top3_ok"]) / len(tp)) if tp else 0.0
    emg_rate = sum(1 for r in records if r["emergency_ok"]) / len(records) if records else 0.0
    all_times = [r["avg_time"] for r in records]
    avg_time = sum(all_times) / len(all_times) if all_times else 0.0

    by_cat = defaultdict(lambda: {"n": 0, "cov": [], "rep": [0, 0], "top3": [0, 0], "emg": [0, 0]})
    for r in records:
        c = by_cat[r["category"]]
        c["n"] += 1
        if r["coverage"] is not None:
            c["cov"].append(r["coverage"])
        if r["report_ok"] is not None:
            c["rep"][1] += 1
            c["rep"][0] += 1 if r["report_ok"] else 0
        if r["top3_ok"] is not None:
            c["top3"][1] += 1
            c["top3"][0] += 1 if r["top3_ok"] else 0
        c["emg"][1] += 1
        c["emg"][0] += 1 if r["emergency_ok"] else 0
    cats = {k: {
        "n": v["n"],
        "coverage": round(sum(v["cov"]) / len(v["cov"]), 4) if v["cov"] else None,
        "report_rate": round(v["rep"][0] / v["rep"][1], 4) if v["rep"][1] else None,
        "top3_accuracy": round(v["top3"][0] / v["top3"][1], 4) if v["top3"][1] else None,
        "emergency_accuracy": round(v["emg"][0] / v["emg"][1], 4) if v["emg"][1] else None,
    } for k, v in by_cat.items()}

    return {
        "mode": mode,
        "cases": len(records),
        "降级用例数": (sum(1 for r in records if r.get("degraded")) if mode == "llm" else 0),
        "追问覆盖率": round(coverage, 4),
        "报告字段完整率": round(report_rate, 4),
        "科室Top3准确率": round(top3_rate, 4),
        "急重症拦截准确率": round(emg_rate, 4),
        "平均响应时间(s)": round(avg_time, 3),
        "by_category": cats,
        "targets": {"追问覆盖率>=0.9": coverage >= 0.9, "报告完整率>=0.9": report_rate >= 0.9,
                    "Top3准确率>=0.8": top3_rate >= 0.8, "平均响应<=5s": avg_time <= 5.0},
    }


def _write_report(agg: dict, records: list[dict], out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.json").write_text(
        json.dumps({"summary": agg, "records": [{k: v for k, v in r.items() if k != "_agent"} for r in records]},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 智能问诊导诊 Agent 评测报告", "",
        f"- 评测模式：`{agg['mode']}`", f"- 用例数：{agg['cases']}",
    ]
    if agg.get("降级用例数"):
        lines.append(f"- ⚠️ LLM 降级用例数：{agg['降级用例数']}（本次含规则回退，指标不纯，仅供参考）")
    lines.append("- 备注：平均响应时间为单轮端到端耗时（含网络重试等待），网络抖动时该值会偏高；追问覆盖率比对时对同义表述与中文数字做了等价归一（如 腰痛/腰疼、四个月/4个月）。")
    lines += [
        "", "## 一、指标结果", "",
        "| 指标 | 目标 | 实测 | 达标 |", "| --- | --- | --- | --- |",
    ]
    t = agg["targets"]
    rows = [
        ("关键信息追问覆盖率", "≥90%", agg["追问覆盖率"], t["追问覆盖率>=0.9"]),
        ("报告字段完整率", "≥90%", agg["报告字段完整率"], t["报告完整率>=0.9"]),
        ("科室推荐 Top3 准确率", "≥80%", agg["科室Top3准确率"], t["Top3准确率>=0.8"]),
        ("平均响应时间", "≤5s", f"{agg['平均响应时间(s)']}s", t["平均响应<=5s"]),
        ("急重症拦截准确率", "—", agg["急重症拦截准确率"], None),
    ]
    for name, goal, val, ok in rows:
        shown = f"{val:.2%}" if isinstance(val, float) and name != "平均响应时间" else val
        mark = "✅" if ok else ("—" if ok is None else "❌")
        lines.append(f"| {name} | {goal} | {shown} | {mark} |")
    lines += ["", "## 二、分类别表现", "", "| 类别 | 用例数 | 追问覆盖率 | 报告完整率 | Top3准确率 | 急重症准确率 |",
              "| --- | --- | --- | --- | --- | --- |"]
    pct = lambda x: f"{x:.2%}" if x is not None else "—"
    for cat, m in agg["by_category"].items():
        lines.append(f"| {cat} | {m['n']} | {pct(m['coverage'])} | {pct(m['report_rate'])} | {pct(m['top3_accuracy'])} | {pct(m['emergency_accuracy'])} |")
    lines += ["", "## 三、未达标 BadCase（追问覆盖率<100% 或 Top3 未命中）", ""]
    bad = [r for r in records if (r["coverage"] is not None and r["coverage"] < 1.0) or r["top3_ok"] is False]
    if bad:
        lines += ["| 用例 | 类别 | 覆盖率 | 期望科室 | 实际Top3 |", "| --- | --- | --- | --- | --- |"]
        for r in bad[:40]:
            cov = f"{r['coverage']:.0%}" if r["coverage"] is not None else "—"
            lines.append(f"| {r['case_id']} | {r['category']} | {cov} | {','.join(r['expected_top3'])} | {','.join(r['rec_depts'])} |")
    else:
        lines.append("无。")
    (out_dir / "评测报告.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(DEFAULT_CASES))
    ap.add_argument("--mode", choices=["llm", "rule"], default="llm")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=str(OUT_DIR))
    args = ap.parse_args()

    if args.mode == "rule":
        _force_rule_mode()

    cases = _load_cases(Path(args.cases))
    if args.limit:
        cases = cases[:args.limit]
    print(f"[eval] mode={args.mode} cases={len(cases)}")

    records: dict[str, dict] = {}
    pending = list(cases)
    for attempt in range(1, MAX_PASSES + 1):
        for i, case in enumerate(pending, 1):
            try:
                rec = _run_case(case)
                records[rec["case_id"]] = rec
            except Exception as e:  # 单例失败不影响整体
                print(f"  [warn] {case['case_id']} 失败: {e}", file=sys.stderr)
            if args.mode == "llm":
                time.sleep(0.5)  # 降低请求密度，规避限流与瞬时网络抖动
            if i % 10 == 0:
                print(f"  ... {i}/{len(pending)} (pass {attempt})")
        # 网络抖动会让 LLM 调用降级为规则模式；对降级用例等待网络恢复后重跑，
        # 直到取得纯净的 LLM 结果（降级用例数=0）或达到最大轮次。
        degraded = [c for c in cases if (records.get(c["case_id"]) or {}).get("degraded")]
        if args.mode != "llm" or not degraded:
            break
        if attempt >= MAX_PASSES:
            print(f"[eval] 已达最大重跑轮次，仍有 {len(degraded)} 个降级用例", file=sys.stderr)
            break
        print(f"[eval] 检测到 {len(degraded)} 个降级用例，等待 {RETRY_WAIT}s 后第 {attempt + 1} 轮重跑")
        time.sleep(RETRY_WAIT)
        pending = degraded

    ordered = [records[c["case_id"]] for c in cases if c["case_id"] in records]
    agg = _aggregate(ordered, args.mode)
    _write_report(agg, ordered, Path(args.out))
    keys = ["mode", "cases", "降级用例数", "追问覆盖率", "报告字段完整率", "科室Top3准确率", "急重症拦截准确率", "平均响应时间(s)"]
    print(json.dumps({k: agg[k] for k in keys}, ensure_ascii=False, indent=2))
    print(f"[eval] 报告已写出 -> {Path(args.out) / '评测报告.md'}")


if __name__ == "__main__":
    main()
