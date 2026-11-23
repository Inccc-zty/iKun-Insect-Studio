# -*- coding: utf-8 -*-
"""在指定的一张表上重拟合裁切系数（v3 形式：cx / cy / log2w，105 项）。

用途：把系数从「4184 张（含白名单外）」换成「范围内 2002 张」，
或者换一个人/换一种构图习惯时整套重标。

    # 只看精度，不写文件
    python refit_crop.py --csv ../assets/data/selftest_crop_4184.csv

    # 换到范围内总表（需要先把 v4 总表转成同格式，见 references/09 §4）
    python refit_crop.py --csv my_scope_2002.csv --out ../assets/data/crop_coef_scope.json

输出 json 的结构与 crop_coef_v3.json 完全一致，可直接被 crop_v3.py 读。
**默认不覆盖**：不加 --write 时只评估、只写 --out 指定的新文件。
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def feats(row, head_key=("hx", "hy"), head_ok_key=None):
    g = lambda k: float(row[k])  # noqa: E731
    cl, ct, cr, cb = g("core_l"), g("core_t"), g("core_r"), g("core_b")
    fl, ft, fr, fb = g("full_l"), g("full_t"), g("full_r"), g("full_b")
    cw, ch = max(cr - cl, 1e-4), max(cb - ct, 1e-4)
    ccx, ccy = (cl + cr) / 2, (ct + cb) / 2
    fcx, fcy = (fl + fr) / 2, (ft + fb) / 2
    D = max((fr - fl) * (fb - ft) / (cw * ch), 1.0)
    multi = (row.get("multi") == "1")
    hx = hy = 0.0
    if not multi:
        try:
            hx = (float(row[head_key[0]]) - ccx) / cw
            hy = (float(row[head_key[1]]) - ccy) / ch
        except (KeyError, ValueError):
            hx = hy = 0.0
    base = [math.log2(D), cw, ch, fr - fl, fb - ft, ccx - 0.5, ccy - 0.5,
            (fcx - ccx) / cw, (fcy - ccy) / ch]
    return base + [hx, hy, hx * (ccx - 0.5), hy * (ccy - 0.5)]


def design(f):
    v = [1.0] + list(f)
    k = len(f)
    for i in range(k):
        for j in range(i, k):
            v.append(f[i] * f[j])
    return np.asarray(v, float)


def ridge(X, y, mu, sd, lam):
    """岭回归，返回 105 维系数（可直接与 design(f) 点乘，bias 已折进第 0 项）。

    第 0 列是常数项 1.0，不参与标准化、也不加正则。
    """
    Xs = (X - mu) / sd
    Xs[:, 0] = 1.0
    A = Xs.T @ Xs
    A[1:, 1:] += lam * np.eye(Xs.shape[1] - 1)
    b = np.linalg.solve(A, Xs.T @ y)
    coef = b / sd
    coef[0] = b[0] - float(mu[1:] @ (b[1:] / sd[1:]))
    return coef


def iou(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def decode(x, coefs):
    cx = float(x @ coefs["cx"])
    cy = float(x @ coefs["cy"])
    w = 2.0 ** float(x @ coefs["log2w"])
    return cx, cy, w


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--write", default="", help="写进这个 json（不填则只评估）")
    ap.add_argument("--lam", type=float, default=0.03)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    rows = list(csv.DictReader(open(a.csv, encoding="utf-8-sig")))
    print(f"读 {len(rows)} 行  {a.csv}")

    F, Y, G, keep = [], [], [], []
    for r in rows:
        try:
            f = feats(r)
            l, t, rr, b = (float(r["crop_l"]), float(r["crop_t"]),
                           float(r["crop_r"]), float(r["crop_b"]))
        except (KeyError, ValueError):
            continue
        w = rr - l
        h = b - t
        if w <= 0.01 or h <= 0.01:
            continue
        F.append(f)
        Y.append([(l + rr) / 2, (t + b) / 2, math.log2(w)])
        G.append(r.get("group", r.get("批次", "x")))
        keep.append((l, t, rr, b))
    F = np.array(F); Y = np.array(Y); G = np.array(G)
    print(f"可用 {len(F)} 行，{len(set(G))} 个批次，{F.shape[1]} 项特征")

    X = np.array([design(f) for f in F])
    mu, sd = X.mean(0), X.std(0) + 1e-9
    mu[0], sd[0] = 0.0, 1.0          # 常数项不动

    coefs = {}
    for j, name in enumerate(("cx", "cy", "log2w")):
        coefs[name] = ridge(X, Y[:, j], mu, sd, a.lam)

    # 样本内
    pred = [decode(x, coefs) for x in X]
    ious_in = [iou((cx - w / 2, cy - w / 2, cx + w / 2, cy + w / 2), gt)
               for (cx, cy, w), gt in zip(pred, keep)]
    print(f"样本内：IoU 中位 {np.median(ious_in):.4f}  均值 {np.mean(ious_in):.4f}")

    # 按批次留出
    rng = np.random.RandomState(a.seed)
    bl = sorted(set(G)); rng.shuffle(bl)
    folds = [set(bl[i::a.folds]) for i in range(a.folds)]
    out_ious = []
    for k in range(a.folds):
        te = np.array([g in folds[k] for g in G]); tr = ~te
        if tr.sum() < 50 or te.sum() < 10:
            continue
        mu_k, sd_k = X[tr].mean(0), X[tr].std(0) + 1e-9
        mu_k[0], sd_k[0] = 0.0, 1.0
        ck = {n: ridge(X[tr], Y[tr, j], mu_k, sd_k, a.lam)
              for j, n in enumerate(("cx", "cy", "log2w"))}
        for x, gt in zip(X[te], [keep[i] for i in np.where(te)[0]]):
            cx, cy, w = decode(x, ck)
            out_ious.append(iou((cx - w / 2, cy - w / 2, cx + w / 2, cy + w / 2), gt))
    print(f"按批次 {a.folds} 折留出：IoU 中位 {np.median(out_ious):.4f}  "
          f"均值 {np.mean(out_ious):.4f}  n={len(out_ious)}")

    if a.out or a.write:
        dst = a.write or a.out
        J = {"version": "v3-refit", "fitted": "refit_crop.py", "n": int(len(F)),
             "groups": sorted(set(G)), "lam": a.lam, "pad_min": 0.03,
             "features": ["bias"] + [f"f{i+1}" for i in range(13)] + ["prod"],
             "coef_cx": coefs["cx"].tolist(),
             "coef_cy": coefs["cy"].tolist(),
             "coef_log2w": coefs["log2w"].tolist(),
             "note": "bias 已折进各系数；与 crop_coef_v3.json 同构"}
        json.dump(J, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"已写 {dst}")
        if not a.write:
            print("注意：这是新文件，未被 crop_v3.py 读取。确认精度后再替换 assets/data/crop_coef_v3.json。")


if __name__ == "__main__":
    main()
