"""重跑三项核心分析，出中英双语图，写 numbers.json。

数据源（全部只读）：
    裁切真值   work_crop/拟合样本_裁切真值.csv        （4184 行，含 K: 路径，仅作索引）
    裁切系数   skill/insect-auto-post-v2/assets/data/crop_coef_v3.json
    曝光表     work_crop/曝光盒内外_范围内.csv        （2241 行，EV + 掩膜内外 p95）

不跑模型：裁切用系数直接算，曝光用表里的 p95 直接拟合。目的是**可复现地把数字重新算一遍**，
并让图能出中文 / 英文两版。
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)              # 仓库根
WORK = os.path.abspath(os.path.join(ROOT, "..", ".."))   # O:/ai修图
sys.path.insert(0, os.path.join(WORK, "skill", "insect-auto-post-v2", "scripts"))

import crop_v3  # noqa: E402

OUT_ZH = os.path.join(ROOT, "figures", "zh")
OUT_EN = os.path.join(ROOT, "figures", "en")
REP = os.path.join(ROOT, "reports")
for d in (OUT_ZH, OUT_EN, REP):
    os.makedirs(d, exist_ok=True)

TRUTH = os.path.join(WORK, "work_crop", "拟合样本_裁切真值.csv")
COEF = os.path.join(WORK, "skill", "insect-auto-post-v2", "assets", "data", "crop_coef_v3.json")
EXPO = os.path.join(WORK, "work_crop", "曝光盒内外_范围内.csv")

PAD_MIN = 0.03


# --------------------------------------------------------------------- 工具
def setup_mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def cjk(plt, on=True):
    if on:
        plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    else:
        # 英文图里仍有中文批次名，直接用雅黑（含拉丁）避免豆腐块
        plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def save(plt, fig, name: str, lang: str):
    d = OUT_ZH if lang == "zh" else OUT_EN
    fp = os.path.join(d, f"{name}.{lang}.png")
    fig.tight_layout()
    fig.savefig(fp, dpi=150, facecolor="white")
    plt.close(fig)
    return fp


def iou(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    iw = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    ih = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = iw * ih
    ua = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / ua if ua > 0 else 0.0


# --------------------------------------------------------------------- 裁切
def load_truth():
    df = pd.read_csv(TRUTH, encoding="utf-8-sig")
    need = ["crop_l", "crop_t", "crop_r", "crop_b", "core_l", "core_t", "core_r",
            "core_b", "full_l", "full_t", "full_r", "full_b", "group"]
    df = df.dropna(subset=need)
    return df


def row_inputs(r):
    core = (r.core_l, r.core_t, r.core_r, r.core_b)
    full = (r.full_l, r.full_t, r.full_r, r.full_b)
    hx, hy = getattr(r, "hx", None), getattr(r, "hy", None)
    head = None if (hx is None or pd.isna(hx) or pd.isna(hy)) else (float(hx), float(hy))
    mv = getattr(r, "multi", None)
    multi = bool(int(mv)) if (mv is not None and not pd.isna(mv)) else False
    return core, full, head, multi


def crop_eval(df, J):
    ious = []
    for r in df.itertuples(index=False):
        core, full, head, multi = row_inputs(r)
        out = crop_v3.compute_crop(core, full, head, multi, J=J)
        ious.append(iou(out["crop"], (r.crop_l, r.crop_t, r.crop_r, r.crop_b)))
    return np.asarray(ious)


def fit_coef(X, Y, lam):
    n = X.shape[0]
    A = X.T @ X + lam * np.eye(X.shape[1])
    return np.linalg.solve(A, X.T @ Y)


def build_design(df):
    """4184 × 105 设计矩阵 + 每列对应的基础特征下标（用于消融）。"""
    cols, ys, groups = [], [], []
    term_idx = []          # 每个乘积列对应的 (i, j)
    for r in df.itertuples(index=False):
        core, full, head, multi = row_inputs(r)
        f, _ = crop_v3.features(core, full, head, multi)
        x = crop_v3.design(f)
        cols.append(x)
        y = r.crop_b - r.crop_t            # 正方形边（归一化高度空间）
        ys.append((np.log2(max(y, 1e-6)),
                   (r.crop_l + r.crop_r) / 2.0,
                   (r.crop_t + r.crop_b) / 2.0))
        groups.append(r.group)
    # 列 → 基础特征
    k = 13
    term_idx.append(())                    # bias
    for i in range(k):
        term_idx.append((i,))
    for i in range(k):
        for j in range(i, k):
            term_idx.append((i, j))
    Y = np.array([y[0] for y in ys]), np.array([y[1] for y in ys]), np.array([y[2] for y in ys])
    return np.asarray(cols), Y, np.asarray(groups), term_idx


def fit_variant(X, Y_logw, Y_cx, Y_cy, term_idx, allowed, lam=0.03):
    mask = np.array([all(t in allowed for t in terms) for terms in term_idx], bool)
    Xs = X[:, mask]
    co = np.zeros((X.shape[1], 3))
    co[mask, 0] = fit_coef(Xs, Y_logw, lam)
    co[mask, 1] = fit_coef(Xs, Y_cx, lam)
    co[mask, 2] = fit_coef(Xs, Y_cy, lam)
    J = {"coef_log2w": co[:, 0].tolist(), "coef_cx": co[:, 1].tolist(),
         "coef_cy": co[:, 2].tolist(), "pad_min": PAD_MIN}
    return J


def iou_with_J(X, base_dir, J, lam=0.03):
    """用变体系数算 IoU：J 直接喂 compute_crop（列已按 mask 置零）。"""
    return crop_eval(base_dir, J)


# --------------------------------------------------------------------- 主流程
def main():
    plt = setup_mpl()
    numbers = {}
    J0 = json.load(open(COEF, encoding="utf-8"))

    # ---------- 1. 全量裁切指标（用现行系数）
    df = load_truth()
    print(f"[crop] 真值行 {len(df)}")
    ious = crop_eval(df, J0)
    numbers["crop"] = {
        "n": int(len(ious)),
        "iou_median": float(np.median(ious)),
        "iou_mean": float(ious.mean()),
        "ge_0.8": float((ious >= 0.8).mean()),
        "lt_0.5": float((ious < 0.5).mean()),
        "batches": int(df.group.nunique()),
    }
    print("[crop]", numbers["crop"])

    for lang in ("zh", "en"):
        cjk(plt, lang == "zh")
        fig, ax = plt.subplots(figsize=(6.6, 4.0))
        ax.hist(ious, bins=50, range=(0, 1), color="#3f8f6b", alpha=.85)
        ax.axvline(np.median(ious), color="#c0392b", lw=1.6,
                   label=("中位 %.3f" % np.median(ious)) if lang == "zh"
                   else ("median %.3f" % np.median(ious)))
        ax.set_xlabel("IoU" if lang == "en" else "IoU（预测框 ∩ 真值框）")
        ax.set_ylabel("photos" if lang == "en" else "张数")
        ax.set_title("Crop IoU, 4,184 photos / 11 batches" if lang == "en"
                     else "裁切 IoU 分布 · 4,184 张 / 11 批")
        ax.legend(frameon=False)
        ax.grid(alpha=.25)
        save(plt, fig, "F11-crop-iou-hist", lang)

        # 按批次中位
        d = pd.DataFrame({"g": df.group.values, "iou": ious})
        m = d.groupby("g").iou.median().sort_values()
        fig, ax = plt.subplots(figsize=(7.2, 4.2))
        ax.barh(range(len(m)), m.values, color="#3f8f6b", alpha=.9)
        ax.set_yticks(range(len(m)))
        ax.set_yticklabels(m.index, fontsize=8)
        ax.axvline(np.median(ious), color="#c0392b", lw=1.2, ls="--")
        ax.set_xlabel("median IoU" if lang == "en" else "批次 IoU 中位")
        ax.set_title("Per-batch crop IoU" if lang == "en" else "各批次裁切 IoU 中位")
        ax.grid(axis="x", alpha=.25)
        save(plt, fig, "F11b-crop-by-batch", lang)

    # ---------- 2. 消融（同口径：5 折按批次留出）
    X, Y, G, term_idx = build_design(df)
    print(f"[ablate] 设计矩阵 {X.shape}")
    batches = sorted(set(G))
    folds = {b: i % 5 for i, b in enumerate(batches)}
    fold_id = np.array([folds[b] for b in G])
    Ylog, Ycx, Ycy = Y

    base_feats = list(range(13))
    groups = {
        "body": [1, 2, 5, 6],
        "limb": [3, 4, 7, 8],
        "head": [9, 10, 11, 12],
        "disp": [0],
    }
    labels = {
        "zh": {"body": "虫体框", "limb": "附肢框", "head": "头点", "disp": "离散度"},
        "en": {"body": "body box", "limb": "limb box", "head": "head point", "disp": "dispersion"},
    }

    def cv_median(allowed):
        pred_logw = np.zeros(len(df))
        pred_cx = np.zeros(len(df))
        pred_cy = np.zeros(len(df))
        for f in range(5):
            tr = fold_id != f
            te = ~tr
            J = fit_variant(X[tr], Ylog[tr], Ycx[tr], Ycy[tr], term_idx, allowed)
            co = np.stack([J["coef_log2w"], J["coef_cx"], J["coef_cy"]], 1)
            pred_logw[te] = X[te] @ co[:, 0]
            pred_cx[te] = X[te] @ co[:, 1]
            pred_cy[te] = X[te] @ co[:, 2]
        # 用预测值直接算 IoU（不经过 compute_crop 的硬约束，保持可比）
        out = []
        for i, r in enumerate(df.itertuples(index=False)):
            w = 2.0 ** pred_logw[i]
            cx, cy = pred_cx[i], pred_cy[i]
            a = (cx - w / 2, cy - w / 2, cx + w / 2, cy + w / 2)
            out.append(iou(a, (r.crop_l, r.crop_t, r.crop_r, r.crop_b)))
        return float(np.median(out))

    full_set = set(base_feats)
    abl = {}
    abl["full"] = cv_median(full_set)
    for key, idx in groups.items():
        abl[f"only_{key}"] = cv_median(set(idx))
        abl[f"drop_{key}"] = cv_median(full_set - set(idx))
    numbers["ablation"] = abl
    print("[ablate]", {k: round(v, 4) for k, v in abl.items()})

    for lang in ("zh", "en"):
        cjk(plt, lang == "zh")
        fig, ax = plt.subplots(figsize=(7.4, 3.8))
        keys = ["only_body", "only_limb", "only_head", "only_disp"]
        vals = [abl[k] for k in keys]
        names = [labels[lang][k.split("_")[1]] for k in keys]
        ax.bar(names, vals, color=["#4f86b8", "#4f86b8", "#c98a2a", "#8a8f93"])
        for i, v in enumerate(vals):
            ax.text(i, v + .004, f"{v:.3f}", ha="center", fontsize=9)
        ax.set_ylim(min(vals) - .06, max(vals) + .03)
        ax.set_ylabel("median IoU" if lang == "en" else "IoU 中位")
        ax.set_title("Each group alone (5-fold by batch)" if lang == "en"
                     else "四组参数单独使用（按批次 5 折）")
        ax.grid(axis="y", alpha=.25)
        save(plt, fig, "F10a-ablation-only", lang)

        fig, ax = plt.subplots(figsize=(7.4, 3.8))
        keys = ["drop_head", "drop_limb", "drop_body", "drop_disp"]
        vals = [abl[k] for k in keys]
        names = [labels[lang][k.split("_")[1]] for k in keys]
        drop = [abl["full"] - v for v in vals]
        ax.bar(names, drop, color=["#c98a2a", "#4f86b8", "#4f86b8", "#8a8f93"])
        for i, v in enumerate(drop):
            ax.text(i, v + 0.0003, f"{v:+.4f}", ha="center", fontsize=9)
        ax.axhline(0, color="#333", lw=.8)
        ax.set_ylabel("IoU drop" if lang == "en" else "IoU 下降")
        ax.set_title("Removed from the full model" if lang == "en"
                     else "从满配里挖掉一组，掉多少")
        ax.grid(axis="y", alpha=.25)
        save(plt, fig, "F10b-ablation-drop", lang)

    # ---------- 3. 曝光
    ex = pd.read_csv(EXPO, encoding="utf-8-sig")
    ex = ex.dropna(subset=["EV", "in_p95", "bg_p95", "批次"])
    print(f"[expo] 行 {len(ex)}")
    L_in = ex.in_p95.values.astype(float)
    L_box = ex.bg_p95.values.astype(float)
    Y_ev = ex.EV.values.astype(float)
    gb = ex["批次"].values

    def fit_ev(tr):
        Xa = np.stack([np.ones(tr.sum()), L_in[tr], L_box[tr]], 1)
        b, *_ = np.linalg.lstsq(Xa, Y_ev[tr], rcond=None)
        return b

    # 5 折按批次
    ub = sorted(set(gb))
    fm = {b: i % 5 for i, b in enumerate(ub)}
    fid = np.array([fm[b] for b in gb])
    pred = np.zeros(len(ex))
    for f in range(5):
        tr = fid != f
        te = ~tr
        b = fit_ev(tr)
        pred[te] = b[0] + b[1] * L_in[te] + b[2] * L_box[te]
    b_all = fit_ev(np.ones(len(ex), bool))
    mae = float(np.mean(np.abs(pred - Y_ev)))
    mae_const = float(np.mean(np.abs(Y_ev - Y_ev.mean())))
    numbers["exposure"] = {
        "n": int(len(ex)), "b0": float(b_all[0]), "b1": float(b_all[1]),
        "b2": float(b_all[2]), "mae_holdout": mae, "mae_const": mae_const,
        "batches": int(len(ub)),
    }
    print("[expo]", numbers["exposure"])

    for lang in ("zh", "en"):
        cjk(plt, lang == "zh")
        fig, ax = plt.subplots(figsize=(6.0, 4.6))
        sc = ax.scatter(L_in, L_box, c=Y_ev, s=9, cmap="viridis", alpha=.8)
        cb = fig.colorbar(sc, ax=ax)
        cb.set_label("EV")
        ax.set_xlabel("L_in (p95 inside mask)" if lang == "en" else "L_in（掩膜内 p95）")
        ax.set_ylabel("L_box (p95 background in box)" if lang == "en"
                      else "L_box（框内掩膜外 p95）")
        ax.set_title("Exposure label space" if lang == "en" else "曝光样本分布")
        save(plt, fig, "F14-exposure-space", lang)

        fig, ax = plt.subplots(figsize=(6.6, 3.8))
        ax.hist(pred - Y_ev, bins=50, color="#4f86b8", alpha=.85)
        ax.axvline(0, color="#333", lw=.8)
        ax.set_xlabel("residual (EV)" if lang == "en" else "残差（EV）")
        ax.set_ylabel("photos" if lang == "en" else "张数")
        ax.set_title(f"Hold-out residual · MAE {mae:.3f} EV" if lang == "en"
                     else f"留出残差 · MAE {mae:.3f} EV")
        ax.grid(alpha=.25)
        save(plt, fig, "F15-exposure-residual", lang)

        fig, ax = plt.subplots(figsize=(4.6, 3.8))
        vals = [mae_const, mae]
        names = ["constant" if lang == "en" else "常数", "two-term" if lang == "en" else "双参数"]
        ax.bar(names, vals, color=["#8a8f93", "#3f8f6b"])
        for i, v in enumerate(vals):
            ax.text(i, v + .008, f"{v:.3f}", ha="center", fontsize=10)
        ax.set_ylabel("MAE (EV)")
        ax.set_title("Baseline vs model" if lang == "en" else "常数基线 vs 双参数")
        ax.set_ylim(0, max(vals) * 1.25)
        ax.grid(axis="y", alpha=.25)
        save(plt, fig, "F16-exposure-baseline", lang)

    json.dump(numbers, open(os.path.join(REP, "numbers.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("[done] numbers.json")


if __name__ == "__main__":
    main()
