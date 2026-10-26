# -*- coding: utf-8 -*-
import csv, os, io
root = r"D:\peixunwenjian\2026.10.8-2026.10.23\智能问诊导诊Agent_交付物\语料工程\corpus_raw"
buf = []
csvs = [os.path.join(dp, n) for dp, dirs, fs in os.walk(root) for n in fs if n.lower().endswith(".csv")]
buf.append("CSV_TOTAL=%d" % len(csvs))
for f in csvs:
    try:
        with open(f, encoding="utf-8-sig") as fh:
            rd = csv.DictReader(fh)
            cols = list(rd.fieldnames or [])
            count = sum(1 for _ in rd)
        buf.append(os.path.relpath(f, root) + " | cols=%s | rows=%d" % (cols, count))
    except Exception as e:
        buf.append(os.path.relpath(f, root) + " | ERR " + repr(e)[:120])
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inspect_out.txt")
with io.open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(buf))
print("DONE")