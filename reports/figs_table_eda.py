"""曝光线的两件事：
   1) 21b：把 13 类算法 + 双参数合成一张表（对比的是"你标定的 EV"）
   2) EDA：对 曝光盒内外_范围内.csv 做清洗 + 探索，出 4 张图 + 一份 md
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORK = os.path.abspath(os.path.join(ROOT, "..", ".."))
OUTS = [os.path.join(ROOT, "figures"), os.path.join(WORK, "图集_待选")]

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# (中文名, 英文名, 具体输入中文, 具体输入英文, MAE, R², 是否最终)
ALGS = [
    ("双参数（最终）", "two-term (final)",
     "① 掩膜内所有像素亮度的 p95\n② 掩膜外接框内、掩膜外像素的 p95",
     "① p95 of luma inside the mask\n② p95 of luma inside the box but outside the mask",
     0.281, 0.596, True),
    ("三参数", "three-term",
     "双参数两项 + ③ 整幅平均亮度",
     "the two above + ③ mean luma of the whole frame",
     0.278, 0.612, False),
    ("双参数变体 A", "variant A",
     "① 掩膜内 p95 + ② 整幅 p90", "mask p95 + global p90", 0.280, 0.608, False),
    ("双参数变体 B", "variant B",
     "① 掩膜内 p95 + ② 框外 p95", "mask p95 + outside-box p95", 0.288, 0.600, False),
    ("网格混合", "grid blend",
     "0.6×掩膜内 p95 + 0.4×网格 p90", "0.6·mask p95 + 0.4·grid p90", 0.288, 0.604, False),
    ("单参数", "single",
     "只用 ① 掩膜内 p95", "mask p95 only", 0.315, 0.494, False),
    ("高光保护（全图）", "highlight-safe (global)",
     "整幅 p99", "global p99", 0.343, 0.415, False),
    ("高光保护（最亮网格）", "highlight-safe (bright grid)",
     "最亮 25% 网格的均值", "mean of the brightest 25% grid cells", 0.360, 0.416, False),
    ("尼康矩阵式", "Nikon matrix",
     "0.5×中央 + 0.3×p90 + 0.2×亮度占比", "0.5·centre + 0.3·p90 + 0.2·brightness share",
     0.363, 0.375, False),
    ("高光保护（网格）", "highlight-safe (grid)",
     "网格 p90", "grid p90", 0.364, 0.389, False),
    ("中央重点", "centre-weighted",
     "高斯加权网格均值", "Gaussian-weighted grid mean", 0.381, 0.312, False),
    ("平均测光", "average",
     "网格均值（按 18% 灰归零）", "grid mean, anchored to 18% grey", 0.389, 0.286, False),
    ("中间调锚定", "mid-tone anchor",
     "网格中位", "grid median", 0.412, 0.226, False),
]


def save(fig, zh_name, en_name, zh):
    for od in OUTS:
        d = os.path.join(od, "zh" if zh else "en")
        os.makedirs(d, exist_ok=True)
        fig.savefig(os.path.join(d, (zh_name if zh else en_name) + ".png"),
                    dpi=170, facecolor="white", bbox_inches="tight")
    plt.close(fig)


def table_fig():
    for zh in (True, False):
        rows = sorted(ALGS, key=lambda x: x[4])
        fig, ax = plt.subplots(figsize=(11.4, 5.8))
        ax.axis("off")
        head = (["算法", "具体输入（怎么算出来的）", "MAE (EV)", "R²"] if zh
                else ["algorithm", "inputs (how it is computed)", "MAE (EV)", "R²"])
        cell = []
        for zh_name, en_name, zin, ein, mae, r2, *rest in rows:
            cell.append([zh_name if zh else en_name, zin if zh else ein,
                         f"{mae:.3f}", f"{r2:.3f}"])
        t = ax.table(cellText=cell, colLabels=head, loc="center", cellLoc="left",
                     colWidths=[0.22, 0.50, 0.13, 0.10])
        t.auto_set_font_size(False)
        t.set_fontsize(8.4)
        t.scale(1, 1.55)
        for (r, c), cl in t.get_celld().items():
            cl.set_edgecolor("#d7e1db")
            if r == 0:
                cl.set_facecolor("#eaf3ee")
                cl.set_text_props(weight="bold")
                continue
            src = rows[r - 1]
            if src[6]:
                cl.set_facecolor("#d8f0e4")
                cl.set_text_props(weight="bold")
            elif r % 2 == 0:
                cl.set_facecolor("#f7faf8")
        ax.set_title(("各种曝光算法 vs 你标定的 EV（越靠上越好）" if zh else
                      "Exposure algorithms against your labelled EV (top = best)")
                     + "\n" +
                     ("MAE = 平均绝对误差，单位 EV；R² = 能解释你调整量的比例"
                      if zh else "MAE in EV; R² = share of your adjustment explained"),
                     fontsize=10, pad=14)
        save(fig, "21b_曝光_算法表", "21b_exposure_table", zh)


def eda():
    df = pd.read_csv(os.path.join(WORK, "work_crop", "曝光盒内外_范围内.csv"),
                     encoding="utf-8-sig")
    n0 = len(df)
    need = ["EV", "in_p95", "bg_p95", "all_p95"]
    for c in need:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    na = df[need].isna().sum().to_dict()
    df = df.dropna(subset=need)
    n1 = len(df)
    # 清洗：EV 在 [-3,3]，p95 在 [1,254]
    bad = ((df.EV.abs() > 3) | (df.in_p95 < 1) | (df.in_p95 > 254) |
           (df.bg_p95 < 1) | (df.bg_p95 > 254))
    df_clean = df[~bad]
    n2 = len(df_clean)
    df_clean = df_clean.copy()
    df_clean["pred"] = (2.775 - 0.01783 * df_clean.in_p95 - 0.01355 * df_clean.bg_p95)
    df_clean["res"] = df_clean.pred - df_clean.EV
    mae = float(df_clean.res.abs().mean())
    r2 = 1 - float(((df_clean.res) ** 2).sum()) / float(((df_clean.EV - df_clean.EV.mean()) ** 2).sum())

    summary = [
        "# 曝光数据 EDA",
        "",
        f"- 原始行数：**{n0}**",
        f"- 关键列缺失（EV / in_p95 / bg_p95 / all_p95）：{na} → 剩 **{n1}**",
        f"- 越界（|EV|>3 或 p95∉[1,254]）：**{n0 - n2 - (n0 - n1)}** → 保留 **{n2}**",
        f"- EV 分布：中位 {df_clean.EV.median():.2f}，均值 {df_clean.EV.mean():.2f}，"
        f"范围 [{df_clean.EV.min():.2f}, {df_clean.EV.max():.2f}]",
        f"- L_in（掩膜内 p95）：中位 {df_clean.in_p95.median():.0f}，范围 "
        f"[{df_clean.in_p95.min():.0f}, {df_clean.in_p95.max():.0f}]",
        f"- L_box（盒内背景 p95）：中位 {df_clean.bg_p95.median():.0f}",
        f"- 相关系数：EV~L_in {df_clean.EV.corr(df_clean.in_p95):.3f}，"
        f"EV~L_box {df_clean.EV.corr(df_clean.bg_p95):.3f}，"
        f"L_in~L_box {df_clean.in_p95.corr(df_clean.bg_p95):.3f}",
        f"- 双参数拟合残差：MAE **{mae:.3f} EV**，R² **{r2:.3f}**",
        "",
        "## 读法",
        "EV 是你标定的目标；L_in / L_box 是两张 8-bit 内嵌预览里的亮度分位。"
        "两者相关性很高（同一张图的两个区域），所以系数会互相分担——"
        "这不是共线性故障，去掉任一参数 MAE 都会升到 0.315 以上。",
    ]
    open(os.path.join(HERE, "eda_exposure.md"), "w", encoding="utf-8").write("\n".join(summary))

    for zh in (True, False):
        # 1) EV 分布
        fig, ax = plt.subplots(figsize=(6.4, 3.8))
        ax.hist(df_clean.EV, bins=60, color="#3f8f6b", alpha=.85)
        ax.axvline(0, color="#333", lw=.8)
        ax.set_xlabel("EV（你标定的调整量）" if zh else "EV (your label)")
        ax.set_ylabel("张数" if zh else "photos")
        ax.set_title(f"EV 分布 · n={len(df_clean)}" if zh else f"EV distribution · n={len(df_clean)}")
        ax.grid(alpha=.25)
        save(fig, "23_曝光_EV分布", "23_exposure_ev_hist", zh)

        # 2) 残差 vs L_in（找非线性/饱和）
        fig, ax = plt.subplots(figsize=(6.6, 4.0))
        ax.scatter(df_clean.in_p95, df_clean.res, s=5, alpha=.28, color="#4f86b8")
        bins = np.linspace(df_clean.in_p95.min(), df_clean.in_p95.max(), 14)
        mid, med = [], []
        for i in range(len(bins) - 1):
            sel = (df_clean.in_p95 >= bins[i]) & (df_clean.in_p95 < bins[i + 1])
            if sel.sum() >= 10:
                mid.append((bins[i] + bins[i + 1]) / 2)
                med.append(float(df_clean.res[sel].median()))
        ax.plot(mid, med, color="#c0392b", lw=2, label=("分箱中位" if zh else "binned median"))
        ax.axhline(0, color="#333", lw=.8)
        ax.set_xlabel("L_in（掩膜内 p95）" if zh else "L_in (mask p95)")
        ax.set_ylabel("残差 EV（预测 − 真值）" if zh else "residual (pred − true)")
        ax.set_title("残差随亮度变化（应接近 0 且平）" if zh else "Residual vs brightness")
        ax.legend(frameon=False, fontsize=8)
        ax.grid(alpha=.25)
        save(fig, "24_曝光_残差与亮度", "24_exposure_residual_vs_lum", zh)

        # 3) 逐批 MAE
        gg = df_clean.groupby("批次").res
        g = pd.DataFrame({"count": gg.size(), "mae": gg.apply(lambda s: float(s.abs().mean()))})
        g = g[g["count"] >= 15].sort_values("mae")
        fig, ax = plt.subplots(figsize=(7.6, 4.6))
        ax.barh([str(i)[:18] for i in g.index], g["mae"], color="#3f8f6b", alpha=.9)
        ax.axvline(mae, color="#c0392b", ls="--", lw=1.2,
                   label=(f"总体 {mae:.3f}" if zh else f"overall {mae:.3f}"))
        for i, v in enumerate(g["mae"]):
            ax.text(v + .004, i, f"{v:.2f}", va="center", fontsize=7)
        ax.set_xlabel("MAE (EV)")
        ax.set_title("逐批次误差（样本≥15 的批次）" if zh else "MAE by batch (n ≥ 15)")
        ax.legend(frameon=False, fontsize=8)
        ax.grid(axis="x", alpha=.25)
        save(fig, "25_曝光_逐批误差", "25_exposure_by_batch", zh)

    print("EDA done:", n0, n1, n2, round(mae, 3), round(r2, 3))


if __name__ == "__main__":
    table_fig()
    eda()
