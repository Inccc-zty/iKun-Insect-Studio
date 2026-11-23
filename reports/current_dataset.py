"""用**当前数据集**（2280 张带 RAW、38 批）重做裁切与曝光的两件事：

1. 出厂系数在这 2280 张上表现如何（和 4184 那张老表比）；
2. 只在这 2280 张上重拟合（按批次 5 折留出），得到一套"当前数据集专属"系数，
   与出厂系数逐项对比。

产出：reports/numbers_2280.json、figures/{zh,en}/F12-*.png、F17-*.png
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORK = os.path.abspath(os.path.join(ROOT, "..", ".."))
sys.path.insert(0, os.path.join(WORK, "skill", "insect-auto-post-v2", "scripts"))

import crop_v3  # noqa: E402

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

MASTER = os.path.join(WORK, "work_crop", "昆虫总表_v4_范围内.csv")
EXPO = os.path.join(WORK, "work_crop", "曝光盒内外_范围内.csv")
SHIPPED = os.path.join(WORK, "skill", "insect-auto-post-v2", "assets", "data", "crop_coef_v3.json")
OUT_JSON = os.path.join(HERE, "numbers_2280.json")
LAM = 0.03


def iou(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    iw = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    ih = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = iw * ih
    ua = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / ua if ua > 0 else 0.0


def design_rows(df):
    X, Y, G = [], [], []
    for r in df.itertuples(index=False):
        core = (r.core_l, r.core_t, r.core_r, r.core_b)
        full = (r.full_l, r.full_t, r.full_r, r.full_b)
        hx, hy = r.hcx, r.hcy
        head = None if (pd.isna(hx) or pd.isna(hy)) else (float(hx), float(hy))
        multi = bool(int(r.multi)) if not pd.isna(getattr(r, "multi", np.nan)) else False
        f, _ = crop_v3.features(core, full, head, multi)
        X.append(crop_v3.design(f))
        w = r.CropBottom - r.CropTop
        Y.append((np.log2(max(w, 1e-6)),
                  (r.CropLeft + r.CropRight) / 2, (r.CropTop + r.CropBottom) / 2))
        G.append(os.path.dirname(str(r.nef).replace("/", "\\")))
    return np.asarray(X), np.array(Y), np.asarray(G)


def fit(X, Y, lam=LAM):
    """标准化后解岭回归，再把系数换算回原始特征空间（否则 105 项高度相关会数值崩）。"""
    mu = X.mean(0)
    sd = X.std(0)
    sd[sd < 1e-9] = 1.0
    mu[0] = 0.0                 # 第 0 列是常数 1，不能被中心化掉（否则整列变 0，等于没截距）
    sd[0] = 1.0
    Xs = (X - mu) / sd
    p = X.shape[1]
    co = np.zeros((p, 3))
    A = Xs.T @ Xs + lam * np.eye(p)
    for k in range(3):
        c = np.linalg.solve(A, Xs.T @ Y[:, k])
        coef = c / sd
        coef[0] -= float((mu / sd) @ c)      # 常数项归到 bias
        co[:, k] = coef
    return {"coef_log2w": co[:, 0].tolist(), "coef_cx": co[:, 1].tolist(),
            "coef_cy": co[:, 2].tolist(), "pad_min": 0.03,
            "version": "2280-refit", "n": int(X.shape[0])}


def eval_J(df, J):
    out = []
    for r in df.itertuples(index=False):
        core = (r.core_l, r.core_t, r.core_r, r.core_b)
        full = (r.full_l, r.full_t, r.full_r, r.full_b)
        hx, hy = r.hcx, r.hcy
        head = None if (pd.isna(hx) or pd.isna(hy)) else (float(hx), float(hy))
        multi = bool(int(r.multi)) if not pd.isna(getattr(r, "multi", np.nan)) else False
        p = crop_v3.compute_crop(core, full, head, multi, J=J)
        out.append(iou(p["crop"], (r.CropLeft, r.CropTop, r.CropRight, r.CropBottom)))
    return np.asarray(out)


def save(fig, name, zh):
    d = os.path.join(ROOT, "figures", "zh" if zh else "en")
    os.makedirs(d, exist_ok=True)
    fig.tight_layout()
    fig.savefig(os.path.join(d, f"{name}.{'zh' if zh else 'en'}.png"),
                dpi=150, facecolor="white")
    plt.close(fig)


def main():
    df = pd.read_csv(MASTER, encoding="utf-8-sig")
    df = df.dropna(subset=["CropLeft", "CropTop", "CropRight", "CropBottom",
                        "core_l", "core_t", "core_r", "core_b",
                        "full_l", "full_t", "full_r", "full_b"])
    print("主表可用行:", len(df), "目录数:", df["nef"].map(
        lambda p: os.path.dirname(str(p).replace("/", "\\"))).nunique())

    X, Y, G = design_rows(df)
    if not np.isfinite(X).all():
        bad = ~np.isfinite(X).all(axis=1)
        print("设计矩阵有非有限值，剔除", int(bad.sum()))
        X, Y, G = X[~bad], Y[~bad], G[~bad]
        df = df[~bad].reset_index(drop=True)
    J0 = json.load(open(SHIPPED, encoding="utf-8"))
    i_ship = eval_J(df, J0)

    # 按批次 5 折
    batches = sorted(set(G))
    fold = {b: i % 5 for i, b in enumerate(batches)}
    fid = np.array([fold[b] for b in G])
    pred = np.zeros(len(df))
    for f in range(5):
        tr, te = fid != f, fid == f
        J = fit(X[tr], Y[tr])
        co = np.stack([J["coef_log2w"], J["coef_cx"], J["coef_cy"]], 1)
        pred[te] = X[te] @ co[:, 0]          # 先用 log2 宽比较（快）
    J_new = fit(X, Y)
    i_new_in = eval_J(df, J_new)

    # 留出口径：用留出折拟合的 J 逐折评估（严格，但慢；这里只算中位）
    hold = []
    for f in range(5):
        tr, te = fid != f, fid == f
        Jf = fit(X[tr], Y[tr])
        sub = df[te]
        hold.extend(eval_J(sub, Jf).tolist())
    i_new_hold = np.asarray(hold)

    res = {
        "n": int(len(df)),
        "dirs": int(len(set(G))),
        "shipped_on_2280": {
            "median": float(np.median(i_ship)), "mean": float(i_ship.mean()),
            "ge_0.8": float((i_ship >= 0.8).mean()),
        },
        "refit_2280_in": {
            "median": float(np.median(i_new_in)), "mean": float(i_new_in.mean()),
            "ge_0.8": float((i_new_in >= 0.8).mean()),
        },
        "refit_2280_holdout": {
            "median": float(np.median(i_new_hold)), "mean": float(i_new_hold.mean()),
            "ge_0.8": float((i_new_hold >= 0.8).mean()),
        },
    }
    print(json.dumps(res, ensure_ascii=False, indent=1))

    for zh in (True, False):
        fig, ax = plt.subplots(figsize=(6.8, 3.9))
        names = ([("出厂系数\n(4184 老表)", "样本内"),
                  ("重拟合\n(2280)", "样本内"),
                  ("重拟合\n(2280)", "按批次留出")] if zh else
                 [("shipped\n(4,184)", "in-sample"),
                  ("refit\n(2,280)", "in-sample"),
                  ("refit\n(2,280)", "hold-out")])
        # 重拟合那两档暂不发布：样本内 R² 与 IoU 自相矛盾，等排查完再上图
        vals = [0.8756, res["shipped_on_2280"]["median"]]
        labels = [("出厂系数\n(4184 老表)", "出厂系数\n(2280 当前)") if zh
                  else ("shipped\n(4,184)", "shipped\n(2,280)")]
        labels = [f"{a}\n{b}" for a, b in labels]
        ax.bar(labels, vals, color=["#8a8f93", "#3f8f6b", "#4f86b8"])
        for i, v in enumerate(vals):
            ax.text(i, v + .002, f"{v:.4f}", ha="center", fontsize=9)
        ax.set_ylim(min(vals) - .03, max(vals) + .02)
        ax.set_ylabel("IoU median" if not zh else "IoU 中位")
        ax.set_title("Crop on the current dataset (2,280)" if not zh
                     else "当前数据集（2280 张）上的裁切表现")
        ax.grid(axis="y", alpha=.25)
        plt.setp(ax.get_xticklabels(), fontsize=8)
        save(fig, "F12-crop-2280", zh)

        fig, ax = plt.subplots(figsize=(6.6, 3.8))
        ax.hist(i_ship, bins=50, range=(0, 1), alpha=.65, label=("出厂系数" if zh else "shipped"))
        ax.hist(i_new_hold, bins=50, range=(0, 1), alpha=.65,
                label=("重拟合·留出" if zh else "refit · hold-out"))
        ax.set_xlabel("IoU")
        ax.set_ylabel("photos" if not zh else "张数")
        ax.legend(frameon=False)
        ax.set_title("Old model vs current-dataset model" if not zh
                     else "老系数 vs 当前数据集重拟合")
        ax.grid(alpha=.25)
        save(fig, "F12b-crop-2280-hist", zh)

    json.dump(res, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(J_new, open(os.path.join(HERE, "crop_coef_2280.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("saved", OUT_JSON)


if __name__ == "__main__":
    main()
