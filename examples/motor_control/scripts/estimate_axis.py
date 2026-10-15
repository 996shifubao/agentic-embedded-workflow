#!/usr/bin/env python3
"""Six-pulse 2D current-increment -> continuous axis estimation (demo).

Model:  s_k = a + b*cos(2*phi_k) + c*sin(2*phi_k)
  LS axis estimate : theta = 0.5*atan2(c, b)   (mod 180 deg)
  Max-channel base : phi of the largest s_k     (quantized to 60 deg)

Reads CSV columns: sample_id,true_axis_deg,phi_deg,s
Prints one JSON object on stdout; human-readable detail goes to stderr.
"""

import argparse
import csv
import json
import math
import sys
from collections import defaultdict


def solve3(A, y):
    M = [row[:] + [y[i]] for i, row in enumerate(A)]
    n = 3
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-12:
            return None
        M[col], M[piv] = M[piv], M[col]
        for r in range(n):
            if r != col:
                f = M[r][col] / M[col][col]
                for cc in range(col, n + 1):
                    M[r][cc] -= f * M[col][cc]
    return [M[i][n] / M[i][i] for i in range(n)]


def ls_axis(phis, s):
    A = [[1.0, math.cos(math.radians(2 * p)), math.sin(math.radians(2 * p))] for p in phis]
    AT_A = [[sum(A[k][i] * A[k][j] for k in range(len(A))) for j in range(3)] for i in range(3)]
    AT_y = [sum(A[k][i] * s[k] for k in range(len(A))) for i in range(3)]
    x = solve3(AT_A, AT_y)
    if x is None:
        return None
    _, b, c = x
    return (0.5 * math.degrees(math.atan2(c, b))) % 180.0


def ang_err(a, b):
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--max-mae", type=float, default=None)
    a = ap.parse_args()

    groups, truth = defaultdict(list), {}
    with open(a.csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sid = row["sample_id"].strip()
            groups[sid].append((float(row["phi_deg"]), float(row["s"])))
            truth[sid] = float(row["true_axis_deg"])

    ls_errs, mc_errs, rows = [], [], []
    for sid, pairs in sorted(groups.items(), key=lambda kv: int(kv[0])):
        phis = [p for p, _ in pairs]
        sv = [v for _, v in pairs]
        th_ls = ls_axis(phis, sv)
        th_mc = phis[max(range(len(sv)), key=lambda i: sv[i])] % 180.0
        t = truth[sid]
        e_ls = ang_err(th_ls, t) if th_ls is not None else 180.0
        e_mc = ang_err(th_mc, t)
        ls_errs.append(e_ls)
        mc_errs.append(e_mc)
        rows.append(
            "sample %s true=%6.2f  ls=%6.2f (err %5.2f)  maxch=%6.2f (err %6.2f)"
            % (sid, t, th_ls, e_ls, th_mc, e_mc)
        )

    n = len(ls_errs)
    metrics = {
        "n": n,
        "mae_ls_deg": round(sum(ls_errs) / n, 4),
        "max_ls_err_deg": round(max(ls_errs), 4),
        "mae_maxch_deg": round(sum(mc_errs) / n, 4),
        "max_maxch_err_deg": round(max(mc_errs), 4),
    }
    for line in rows:
        print(line, file=sys.stderr)
    print(json.dumps(metrics, ensure_ascii=False))

    if a.max_mae is not None and metrics["mae_ls_deg"] > a.max_mae:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
