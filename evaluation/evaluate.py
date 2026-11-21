"""Score DINOv2 against the OpenCV baseline on labeled reference/capture pairs.

    python -m evaluation.evaluate data/eval/synthetic
    python -m evaluation.evaluate data/eval/real --out results.md

A pair folder holds reference.jpg + capture.jpg; labels.csv lists pair_id,label
(label = obstructed | clear). Add real pairs from the neighborhood the same way.

Reports, per method: accuracy of the obstructed/clear call, precision and recall
for "obstructed", how often clear paths with shadows were wrongly flagged, how
well the score separates the two classes (AUC), and time per pair.
"""
from __future__ import annotations

import argparse
import csv
import tempfile
import time
from pathlib import Path

import numpy as np

from clearpath.vision import baseline, dino, verdict
from clearpath.vision.align import align, load_rgb


def auc(scores_pos, scores_neg) -> float:
    if not scores_pos or not scores_neg:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in scores_pos for n in scores_neg)
    return wins / (len(scores_pos) * len(scores_neg))


def run(root: Path, methods):
    rows = list(csv.DictReader(open(root / "labels.csv", encoding="utf-8")))
    out = {m: [] for m in methods}
    for r in rows:
        d = root / r["pair_id"]
        ref, cap = load_rgb(d / "reference.jpg"), load_rgb(d / "capture.jpg")
        t0 = time.perf_counter()
        cap_al, valid, _ = align(ref, cap)
        t_align = time.perf_counter() - t0
        for m in methods:
            t = time.perf_counter()
            res = (dino if m == "dinov2" else baseline).compare(ref, cap_al, valid)
            out[m].append({**r, "frac": res["largest_region"],
                           "verdict": verdict(m, res["largest_region"]),
                           "secs": time.perf_counter() - t + t_align})
    return out


def summarise(method, items):
    pos = [i for i in items if i["label"] == "obstructed"]
    neg = [i for i in items if i["label"] == "clear"]
    called = lambda i: i["verdict"] == "obstructed"
    tp = sum(called(i) for i in pos)
    fp = sum(called(i) for i in neg)
    # "uncertain" goes to a human; count it as not-obstructed for accuracy
    correct = tp + sum(not called(i) for i in neg)
    shadows = [i for i in neg if i["hard_case"]]
    uncertain = sum(i["verdict"] == "uncertain" for i in items)
    return {
        "Method": method,
        "Accuracy": f"{correct / len(items):.0%}",
        "Precision (obstructed)": f"{tp / max(tp + fp, 1):.0%}",
        "Recall (obstructed)": f"{tp / max(len(pos), 1):.0%}",
        "Clear paths with shadows flagged": f"{sum(called(i) for i in shadows)} of {len(shadows)}",
        "Sent to human as uncertain": f"{uncertain} of {len(items)}",
        "AUC": f"{auc([i['frac'] for i in pos], [i['frac'] for i in neg]):.2f}",
        "Seconds per pair": f"{np.mean([i['secs'] for i in items]):.2f}",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path)
    ap.add_argument("--methods", default="opencv,dinov2")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--per-pair", action="store_true", help="print each pair's changed fraction")
    args = ap.parse_args(argv)
    methods = [m for m in args.methods.split(",") if m != "dinov2" or dino.available()]
    res = run(args.root, methods)
    if args.per_pair:
        for m in methods:
            for i in res[m]:
                print(f"{m:7s} {i['pair_id']} {i['label']:10s} {i['hard_case'] or '-':6s} largest={i['frac']:.3f} -> {i['verdict']}")
    summaries = [summarise(m, res[m]) for m in methods]
    keys = list(summaries[0])
    lines = ["| " + " | ".join(keys) + " |", "|" + " --- |" * len(keys)]
    lines += ["| " + " | ".join(s[k] for k in keys) + " |" for s in summaries]
    md = f"Evaluation on `{args.root}` ({len(res[methods[0]])} pairs)\n\n" + "\n".join(lines) + "\n"
    print(md)
    if args.out:
        args.out.write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
