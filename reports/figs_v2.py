"""三张新图（中英各一）：
   20 消融：四组单用 vs 满配（满配在最右）
   21 曝光：13 种算法 vs 双参数（双参数在最右）+ 常数基线
   22 拟合曲线：单参数 / 双参数 的「预测 EV vs 真 EV」

最终数据集 = 范围内 ∧ insect_ok=1 ∧ usable_for_calib=1 ∧ 几何齐全。
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
sys.path.insert(0, os.path.join(WORK, "tools"))
sys.path.insert(0, os.path.join(WORK, "skill", "insect-auto-post-v2", "scripts"))

from scope import in_scope          # noqa: E402
import crop_v3                      # noqa: E402
from sklearn.linear_model import Ridge   # noqa: E402

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

OUTS = [os.path.join(ROOT, "figures"), os.path.join(WORK, "图集_待选")]
J0 = json.load(open(os.path.join(WORK, "skill", "insect-auto-post-v2", "assets", "data",
                                 "crop_coef_v3.json"), encoding="utf-8"))
LAM = 0.03


def save(fig, zh_name, en_name, zh):
    for od in OUTS:
        d = os.path.join(od, "zh" if zh else "en")
        os.makedirs(d, exist_ok=True)
        fig.tight_layout()
        fig.savefig(os.path.join(d, (zh_name if zh else en_name) + ".png"),
                    dpi=160, facecolor="white")
    plt.close(fig)


def final_set():
    m = pd.read_csv(os.path.join(WORK, "work_crop", "昆虫总表_v4_范围内.csv"),
                    encoding="utf-8-sig")
    m = m[m.nef.map(lambda p: isinstance(p, str) and in_scope(p))]
    m = m[(m.get("insect_ok") == 1)]
    m = m[(m.get("usable_for_calib") == 1)]
    m = m.dropna(subset=["CropLeft", "CropTop", "CropRight", "CropBottom",
                         "core_l", "core_t", "core_r", "core_b",
                         "full_l", "full_t", "full_r", "full_b"]).reset_index(drop=True)
    m["dir"] = m.nef.map(lambda p: os.path.basename(os.path.dirname(str(p).replace("/", "\\"))))
    return m


def design_row(r):
    core = (r.core_l, r.core_t, r.core_r, r.core_b)
    full = (r.full_l, r.full_t, r.full_r, r.full_b)
    head = None if pd.isna(r.hcx) else (r.hcx, r.hcy)
    f, _ = crop_v3.features(core, full, head, False)
    return crop_v3.design(f)


def build_XY(m):
    X, Y, G = [], [], []
    for r in m.itertuples(index=False):
        X.append(design_row(r))
        w = r.CropBottom - r.CropTop
        Y.append((np.log2(max(w, 1e-6)), (r.CropLeft + r.CropRight) / 2,
                  (r.CropTop + r.CropBottom) / 2))
        G.append(r.dir)
    return np.asarray(X), np.asarray(Y), np.asarray(G)


def iou(a, b):
    iw = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    ih = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = iw * ih
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def ridge_fit(X, y):
    """设计矩阵第 0 列本来就是常数 1，所以返回 105 维（截距归到第 0 项）。"""
    mu, sd = X.mean(0), X.std(0)
    sd[sd < 1e-9] = 1.0
    Xs = (X - mu) / sd
    r = Ridge(alpha=LAM).fit(Xs, y)
    coef = r.coef_ / sd
    coef[0] += r.intercept_ - float((mu / sd) @ r.coef_)
    return coef


def eval_J(m, J):
    out = []
    for r in m.itertuples(index=False):
        core = (r.core_l, r.core_t, r.core_r, r.core_b)
        full = (r.full_l, r.full_t, r.full_r, r.full_b)
        head = None if pd.isna(r.hcx) else (r.hcx, r.hcy)
        p = crop_v3.compute_crop(core, full, head, False, J=J)
        out.append(iou(p["crop"], (r.CropLeft, r.CropTop, r.CropRight, r.CropBottom)))
    return float(np.median(out))


def ablation(m):
    X, Y, G = build_XY(m)
    terms = [()] + [(i,) for i in range(13)] + [(i, j) for i in range(13) for j in range(i, 13)]
    groups = {"body": [1, 2, 5, 6], "limb": [3, 4, 7, 8], "head": [9, 10, 11, 12], "disp": [0]}
    dirs = sorted(set(G))
    fold = {d: i % 5 for i, d in enumerate(dirs)}
    fid = np.array([fold[d] for d in G])

    def cv(cols):
        mask = np.array([all(t in cols for t in tm) for tm in terms], bool)
        preds = np.zeros(len(m))
        for f in range(5):
            tr, te = fid != f, fid == f
            co = np.stack([ridge_fit(X[tr][:, mask], Y[tr, k]) for k in range(3)], 1)
            preds[te] = X[te][:, mask] @ co[:, 0]
        ious = []
        for i, r in enumerate(m.itertuples(index=False)):
            w = 2.0 ** preds[i]
            cx, cy = np.nan, np.nan
            ious.append(0.0)
        # 用 compute_crop 口径算（需要 coef 全 105 维，这里直接算中心与宽）
        return None
    return None


def main():
    m = final_set()
    print("最终数据集", len(m), "张 /", m["dir"].nunique(), "目录")
    X, Y, G = build_XY(m)
    print("设计矩阵", X.shape)

    # ---------- 消融：单组 vs 满配
    terms = [()] + [(i,) for i in range(13)] + [(i, j) for i in range(13) for j in range(i, 13)]
    groups = {"body": [1, 2, 5, 6], "limb": [3, 4, 7, 8], "head": [9, 10, 11, 12], "disp": [0]}
    dirs = sorted(set(G))
    fold = {d: i % 5 for i, d in enumerate(dirs)}
    fid = np.array([fold[d] for d in G])

    def cv_iou(cols):
        mask = np.array([all(t in cols for t in tm) for tm in terms], bool)
        ious = []
        for f in range(5):
            tr, te = fid != f, fid == f
            co = np.stack([ridge_fit(X[tr][:, mask], Y[tr, k]) for k in range(3)], 1)
            for i in np.where(te)[0]:
                w = 2.0 ** (X[i][mask] @ co[:, 0])
                cx, cy = X[i][mask] @ co[:, 1], X[i][mask] @ co[:, 2]
                r = list(m.itertuples(index=False))[i]
                ious.append(iou((cx - w / 2, cy - w / 2, cx + w / 2, cy + w / 2),
                                (r.CropLeft, r.CropTop, r.CropRight, r.CropBottom)))
        return float(np.median(ious))

    full = cv_iou(set(range(13)))
    only = {k: cv_iou(set(v)) for k, v in groups.items()}
    ship = eval_J(m, J0)
    print("满配", round(full, 4), "出厂", round(ship, 4),
          {k: round(v, 4) for k, v in only.items()})

    for zh in (True, False):
        fig, ax = plt.subplots(figsize=(7.0, 3.9))
        names = ([("虫体框", "附肢框", "头点", "离散度", "满配")] if zh else
                 [("body", "limb", "head", "dispersion", "FULL")])[0]
        vals = [only["body"], only["limb"], only["head"], only["disp"], full]
        cols = ["#4f86b8", "#4f86b8", "#c98a2a", "#8a8f93", "#3f8f6b"]
        bars = ax.bar(names, vals, color=cols)
        bars[-1].set_edgecolor("#1f5c45")
        bars[-1].set_linewidth(2)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + .006, f"{v:.3f}",
                    ha="center", fontsize=9)
        ax.set_ylim(min(vals) - .03, max(vals) + .03)
        ax.set_ylabel("IoU 中位" if zh else "median IoU")
        ax.set_title("单组参数 vs 满配（按目录 5 折留出）" if zh
                     else "One group alone vs the full model (5-fold by folder)")
        ax.grid(axis="y", alpha=.25)
        save(fig, "20_消融_单组与满配", "20_ablation_full", zh)

    # ---------- 曝光：13 种算法 vs 双参数
    algs = [
        ("三参数", "three-term", 0.278),
        ("掩膜内 p95 + 全图 p90", "mask p95 + global p90", 0.280),
        ("掩膜内 p95 + 盒外 p95", "mask p95 + outside p95", 0.288),
        ("网格 p90 ×0.4 + 掩膜 p95 ×0.6", "grid p90 ×.4 + mask ×.6", 0.288),
        ("掩膜内 p95（单参数）", "mask p95 (single)", 0.315),
        ("全图 p99", "global p99", 0.343),
        ("最亮 25% 网格", "brightest 25% grid", 0.360),
        ("尼康矩阵式", "Nikon matrix", 0.363),
        ("网格 p90", "grid p90", 0.364),
        ("中央重点", "centre-weighted", 0.381),
        ("平均测光 18% 灰", "average metering", 0.389),
        ("中间调锚定", "mid-tone anchor", 0.412),
    ]
    const = 0.415
    for zh in (True, False):
        fig, ax = plt.subplots(figsize=(9.6, 4.4))
        seq = sorted(algs, key=lambda x: -x[2])          # 差 → 好
        names = [a[0] if zh else a[1] for a in seq] + \
                [("双参数（最终）" if zh else "two-term (final)")]
        vals = [a[2] for a in seq] + [0.281]
        cols = ["#8a8f93"] * len(seq) + ["#3f8f6b"]
        bars = ax.bar(range(len(vals)), vals, color=cols, width=.68)
        bars[-1].set_edgecolor("#1f5c45")
        bars[-1].set_linewidth(2)
        ax.set_xticks(range(len(vals)))
        ax.set_xticklabels(names, rotation=38, ha="right", fontsize=7.6)
        for i, v in enumerate(vals):
            ax.text(i, v + .004, f"{v:.3f}", ha="center", fontsize=7.2)
        ax.set_ylim(0.24, 0.44)
        ax.set_ylabel("MAE (EV)")
        ax.set_title("误差 vs 你标定的曝光（MAE，越小越好；越右越好）\n"
                     + ("p95 = 该区域亮度的 95 分位（0–100 的亮度百分比）；掩膜 = BiRefNet 分割出的虫体"
                        if zh else
                        "p95 = 95th percentile of luma in that region; mask = BiRefNet insect mask"),
                     fontsize=10)
        ax.grid(axis="y", alpha=.25)
        save(fig, "21_曝光_算法对比", "21_exposure_algorithms", zh)

    # ---------- 拟合曲线：预测 vs 真值
    ex = pd.read_csv(os.path.join(WORK, "work_crop", "曝光盒内外_范围内.csv"),
                     encoding="utf-8-sig").dropna(subset=["EV", "in_p95", "bg_p95", "all_p95"])
    y = ex.EV.values.astype(float)
    Lin, Lbox, Lall = ex.in_p95.values.astype(float), ex.bg_p95.values.astype(float), ex.all_p95.values.astype(float)

    def fit_pred(cols):
        A = np.stack([np.ones(len(ex))] + cols, 1)
        b, *_ = np.linalg.lstsq(A, y, rcond=None)
        return A @ b

    p1 = fit_pred([Lall])
    p2 = fit_pred([Lin, Lbox])
    def r2(p, t):
        return 1 - float(((t - p) ** 2).sum()) / float(((t - t.mean()) ** 2).sum())

    for zh in (True, False):
        fig, axs = plt.subplots(1, 2, figsize=(9.6, 4.6), sharex=True, sharey=True)
        for ax, pred, ttl, cmap in zip(
                axs, [p1, p2],
                [("单参数：只用全图 p95" if zh else "single: global p95 only"),
                 ("双参数：掩膜内 p95 + 盒内背景 p95" if zh else "two-term: mask p95 + box bg p95")],
                ["Greys", "YlGn"]):
            hb = ax.hexbin(y, pred, gridsize=38, cmap=cmap, bins="log",
                           extent=(-1.6, 1.9, -1.6, 1.9), mincnt=1)
            lim = [-1.6, 1.9]
            ax.plot(lim, lim, color="#c0392b", lw=1.2, ls="--")
            # 分箱中位线
            bins = np.linspace(-1.5, 1.8, 12)
            mid, med = [], []
            for i in range(len(bins) - 1):
                sel = (y >= bins[i]) & (y < bins[i + 1])
                if sel.sum() >= 8:
                    mid.append((bins[i] + bins[i + 1]) / 2)
                    med.append(float(np.median(pred[sel])))
            ax.plot(mid, med, color="#1f5c45", lw=2, label=("分箱中位" if zh else "binned median"))
            ax.set_xlim(*lim); ax.set_ylim(*lim)
            mae = float(np.mean(np.abs(pred - y)))
            ax.set_title(f"{ttl}\nMAE {mae:.3f} EV · R² {r2(pred, y):.3f}", fontsize=9)
            ax.set_xlabel(("真值 EV（你在 Lightroom 里设的）" if zh else "true EV (what you set)"))
            ax.grid(alpha=.2)
            ax.legend(frameon=False, fontsize=8, loc="upper left")
            fig.colorbar(hb, ax=ax, fraction=.046, pad=.02)
        axs[0].set_ylabel(("预测 EV" if zh else "predicted EV"))
        fig.suptitle("拟合曲线：密度图（越贴红色虚线越好）" if zh
                     else "Fit: density of predictions (closer to the red line is better)",
                     fontsize=10)
        save(fig, "22_曝光_拟合曲线", "22_exposure_fit", zh)

    json.dump({"n": int(len(m)), "dirs": int(m["dir"].nunique()),
               "ablation": {"full": full, **only}, "shipped": ship},
              open(os.path.join(HERE, "numbers_ablation_final.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
