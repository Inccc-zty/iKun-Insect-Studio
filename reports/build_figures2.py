"""第二批图：数据口径、裁切误差分解、头部置信度/误差、白平衡三条死路、锐化、链路、决策时间线。

全部从现有 CSV 重算；白平衡用归档报告里的数字（表已不存在，报告里逐条有出处）。
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORK = os.path.abspath(os.path.join(ROOT, "..", ".."))
ZH, EN = os.path.join(ROOT, "figures", "zh"), os.path.join(ROOT, "figures", "en")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

plt.rcParams["axes.unicode_minus"] = False


def lang_setup(zh: bool):
    # 英文图里也有中文批次名，两个都先给雅黑（含拉丁），避免豆腐块
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]


def save(fig, name, zh):
    d = ZH if zh else EN
    os.makedirs(d, exist_ok=True)
    fp = os.path.join(d, f"{name}.{'zh' if zh else 'en'}.png")
    fig.tight_layout()
    fig.savefig(fp, dpi=150, facecolor="white")
    plt.close(fig)
    return fp


def L(zh, a, b):
    return a if zh else b


# ------------------------------------------------------------------ 1 数据口径
def fig_dataset():
    d = pd.read_csv(os.path.join(WORK, "work_crop", "昆虫总表_v4_范围内.csv"),
                    encoding="utf-8-sig")
    vc = d["批次"].value_counts().sort_values()
    for zh in (True, False):
        lang_setup(zh)
        fig, ax = plt.subplots(figsize=(8.2, 6.6))
        ax.barh(range(len(vc)), vc.values, color="#3f8f6b", alpha=.9)
        ax.set_yticks(range(len(vc)))
        ax.set_yticklabels([s[:14] for s in vc.index], fontsize=6.6)
        for i, v in enumerate(vc.values):
            ax.text(v + 2, i, str(v), va="center", fontsize=7)
        ax.set_xlabel(L(zh, "照片数", "photos"))
        ax.set_title(L(zh, f"数据集口径 · {len(d)} 张 / {len(vc)} 批",
                       f"Dataset · {len(d)} photos / {len(vc)} batches"))
        ax.grid(axis="x", alpha=.25)
        save(fig, "F00-dataset", zh)


# ------------------------------------------------------------------ 2 裁切误差分解
def fig_crop_error():
    d = pd.read_csv(os.path.join(WORK, "work_crop", "数据集_全量化.csv"),
                    encoding="utf-8-sig")
    d = d.dropna(subset=["框宽误差", "框心误差", "IoU"])
    for zh in (True, False):
        lang_setup(zh)
        fig, ax = plt.subplots(1, 2, figsize=(9.2, 3.8))
        ax[0].scatter(d["框宽误差"], d["IoU"], s=4, alpha=.35, color="#4f86b8")
        ax[0].set_xlabel(L(zh, "框宽误差（占画幅）", "width error (frame)"))
        ax[0].set_ylabel("IoU")
        ax[0].set_title(L(zh, "尺寸误差 → IoU", "size error → IoU"))
        ax[0].grid(alpha=.25)
        ax[1].scatter(d["框心误差"], d["IoU"], s=4, alpha=.35, color="#c98a2a")
        ax[1].set_xlabel(L(zh, "框心误差（占画幅）", "centre error (frame)"))
        ax[1].set_ylabel("IoU")
        ax[1].set_title(L(zh, "位置误差 → IoU", "centre error → IoU"))
        ax[1].grid(alpha=.25)
        save(fig, "F04-crop-error", zh)

        # 留白与出界
        padok = float((d["腿留白达标"] == 1).mean()) if "腿留白达标" in d else float("nan")
        oob = float((d["是否出界"] == 1).mean()) if "是否出界" in d else float("nan")
        fig, ax = plt.subplots(figsize=(4.8, 3.6))
        vals = [padok * 100, oob * 100]
        names = [L(zh, "腿留白达标", "leg padding ok"), L(zh, "出界", "out of frame")]
        ax.bar(names, vals, color=["#3f8f6b", "#c0392b"])
        for i, v in enumerate(vals):
            ax.text(i, v + 1.2, f"{v:.1f}%", ha="center", fontsize=10)
        ax.set_ylim(0, 110)
        ax.set_ylabel("%")
        ax.set_title(L(zh, "硬约束达成率", "Hard-constraint rate"))
        ax.grid(axis="y", alpha=.25)
        save(fig, "F05-crop-constraints", zh)


# ------------------------------------------------------------------ 3 头部
def fig_head():
    d = pd.read_csv(os.path.join(WORK, "work_crop", "头部_kpv2_全量.csv"),
                    encoding="utf-8-sig")
    d = d.dropna(subset=["conf"])
    a = pd.read_csv(os.path.join(WORK, "work_crop", "头部标注_500.csv"),
                    encoding="utf-8-sig")
    a = a.dropna(subset=["ai_shift"])
    for zh in (True, False):
        lang_setup(zh)
        fig, ax = plt.subplots(figsize=(6.4, 3.9))
        ax.hist(d["conf"], bins=60, color="#4f86b8", alpha=.85)
        ax.axvline(0.02, color="#c0392b", lw=1.4,
                   label=L(zh, "门槛 0.02", "threshold 0.02"))
        ax.set_xlabel(L(zh, "热图峰值（softmax 后）", "heat-map peak"))
        ax.set_ylabel(L(zh, "张数", "photos"))
        ax.set_title(L(zh, f"头部置信度分布 · {len(d)} 张",
                       f"Head confidence · {len(d)} photos"))
        ax.legend(frameon=False)
        ax.grid(alpha=.25)
        save(fig, "F20-head-confidence", zh)

        fig, ax = plt.subplots(figsize=(6.4, 3.9))
        ax.hist(a["ai_shift"], bins=50, color="#c98a2a", alpha=.85)
        med = float(np.median(a["ai_shift"]))
        ax.axvline(med, color="#c0392b", lw=1.4,
                   label=L(zh, f"中位 {med:.3f}", f"median {med:.3f}"))
        ax.set_xlabel(L(zh, "误差（以身体宽为单位）", "error (body widths)"))
        ax.set_ylabel(L(zh, "张数", "photos"))
        ax.set_title(L(zh, f"头部点位误差 · {len(a)} 张复核",
                       f"Head-point error · {len(a)} reviewed"))
        ax.legend(frameon=False)
        ax.grid(alpha=.25)
        save(fig, "F21-head-error", zh)


# ------------------------------------------------------------------ 4 白平衡
def fig_wb():
    # 归档数字（白平衡_可行域报告.md）：MAE（K）
    rows = [
        ("全图", "whole image", 178.6),
        ("+ 高光", "+ specular", 181.0),
        ("+ 分区", "+ zones", 183.9),
        ("常数", "constant", 163.1),
        ("+ 用户其它调整", "+ other edits", 155.4),
    ]
    paths = [("全图", "whole", -0.288), ("掩膜内", "inside mask", -0.235),
             ("掩膜外", "outside", -0.311)]
    for zh in (True, False):
        lang_setup(zh)
        fig, ax = plt.subplots(figsize=(6.8, 3.9))
        names = [L(zh, r[0], r[1]) for r in rows]
        vals = [r[2] for r in rows]
        cols = ["#4f86b8", "#4f86b8", "#4f86b8", "#3f8f6b", "#8a8f93"]
        ax.bar(names, vals, color=cols)
        for i, v in enumerate(vals):
            ax.text(i, v + 3, f"{v:.1f}", ha="center", fontsize=9)
        ax.set_ylabel("MAE (K)")
        ax.set_title(L(zh, "白平衡：所有模型都不如常数",
                       "White balance: every model loses to a constant"))
        ax.set_ylim(0, max(vals) * 1.22)
        ax.grid(axis="y", alpha=.25)
        plt.setp(ax.get_xticklabels(), fontsize=8)
        save(fig, "F30-wb-models", zh)

        fig, ax = plt.subplots(figsize=(5.4, 3.6))
        names = [L(zh, p[0], p[1]) for p in paths]
        vals = [p[2] for p in paths]
        ax.bar(names, vals, color=["#4f86b8", "#c0392b", "#4f86b8"])
        for i, v in enumerate(vals):
            ax.text(i, v - 0.02 if v < 0 else v + 0.01, f"{v:+.3f}",
                    ha="center", va="top" if v < 0 else "bottom", fontsize=9)
        ax.axhline(0, color="#333", lw=.8)
        ax.set_ylabel("r (ΔT vs 特征)" if zh else "r (ΔT vs feature)")
        ax.set_title(L(zh, "掩膜内外与 ΔT 的相关性",
                       "Correlation with ΔT, inside/outside the mask"))
        ax.grid(axis="y", alpha=.25)
        plt.setp(ax.get_xticklabels(), fontsize=8)
        save(fig, "F31-wb-paths", zh)


# ------------------------------------------------------------------ 5 锐化
def fig_sharpen():
    x = [2.8, 4, 5.6, 11, 14, 22]
    y = [20, 30, 40, 50, 60, 65]
    for zh in (True, False):
        lang_setup(zh)
        fig, ax = plt.subplots(figsize=(5.4, 3.6))
        ax.step(x, y, where="post", color="#3f8f6b", lw=2)
        ax.scatter(x, y, color="#3f8f6b", s=28, zorder=3)
        ax.set_xlabel(L(zh, "光圈 f", "aperture f"))
        ax.set_ylabel("Sharpening")
        ax.set_title(L(zh, "锐化按光圈分档", "Sharpening by aperture"))
        ax.grid(alpha=.25)
        save(fig, "F40-sharpen", zh)


# ------------------------------------------------------------------ 6 链路
def fig_pipeline():
    steps = [
        ("NEF 8256×5504", "NEF 8256×5504"),
        ("内嵌预览", "embedded preview"),
        ("768²", "768²"),
        ("BiRefNet", "BiRefNet"),
        ("掩膜", "mask"),
        ("身体框 / 整体框", "body / whole box"),
        ("ResNet50 热图", "ResNet50 heatmap"),
        ("头点", "head point"),
        ("105 项裁切", "crop 105 terms"),
        ("EV 双参数", "EV two-term"),
        ("锐化查表", "sharpening"),
    ]
    for zh in (True, False):
        lang_setup(zh)
        fig, ax = plt.subplots(figsize=(11, 2.6))
        ax.set_xlim(0, len(steps) * 1.25)
        ax.set_ylim(0, 1)
        ax.axis("off")
        for i, (a, b) in enumerate(steps):
            x = i * 1.25 + 0.1
            box = FancyBboxPatch((x, 0.32), 1.0, 0.36, boxstyle="round,pad=0.06",
                                 fc="#eaf3ee", ec="#3f8f6b", lw=1.2)
            ax.add_patch(box)
            ax.text(x + 0.5, 0.5, L(zh, a, b), ha="center", va="center", fontsize=8)
            if i < len(steps) - 1:
                ax.annotate("", xy=(x + 1.2, 0.5), xytext=(x + 1.06, 0.5),
                            arrowprops=dict(arrowstyle="->", color="#3f8f6b", lw=1.2))
        fig.suptitle(L(zh, "一条照片，一次推理，三个模块", "One photo, one pass, three modules"),
                     fontsize=11)
        save(fig, "F01-pipeline", zh)


# ------------------------------------------------------------------ 7 决策时间线
def fig_timeline():
    rows = [
        ("① 只用「离散度/大小/位置」拟合", "1 · fit from dispersion/size/position", "v6"),
        ("② 发现撞号 + 越界（重做数据集）", "2 · id collision + out-of-scope (redo set)", "fixed"),
        ("③ 固定 2280 张，加入头点", "3 · freeze 2,280 photos, add head", "v7"),
        ("④ 头部自训 ResNet50（热图）", "4 · train ResNet50 heatmap", "v10"),
        ("⑤ 按批次 5 折 + 硬约束", "5 · 5-fold by batch + hard rules", "v10"),
        ("⑥ 100 张闭环 → 盲测 80 张", "6 · 100-photo loop → 80 blind", "0.90"),
    ]
    rows2 = [
        ("① 双参数提出（掩膜内 + 框内背景）", "1 · two-term idea", "idea"),
        ("② 全量重测 4396 张", "2 · measure 4,396", "data"),
        ("③ 与常数基线对比", "3 · vs constant", "0.29"),
        ("④ 100 张闭环验证", "4 · 100-photo loop", "ok"),
    ]
    rows3 = [
        ("① 无白参考的假设", "1 · no white reference", "?"),
        ("② 掩膜内/外 → 无效", "2 · inside/outside → no", "r<0"),
        ("③ 镜面高光 → 无效", "3 · specular → no", "r=.04"),
        ("④ 57 维学习 → 不如常数", "4 · 57 features → worse", "163K"),
    ]
    for zh in (True, False):
        lang_setup(zh)
        fig, axes = plt.subplots(1, 3, figsize=(12.4, 4.6))
        for ax, title, rows_ in zip(
                axes,
                [L(zh, "裁切与头部", "Crop & head"),
                 L(zh, "曝光", "Exposure"),
                 L(zh, "白平衡", "White balance")],
                [rows, rows2, rows3]):
            ax.axis("off")
            ax.set_title(title, fontsize=10)
            for i, (a, b, tag) in enumerate(rows_):
                y = 0.92 - i * 0.2
                ax.add_patch(FancyBboxPatch((0.02, y - 0.13), 0.96, 0.14,
                                            boxstyle="round,pad=0.02",
                                            fc="#f4f8f6", ec="#cfdcd5", lw=.8,
                                            transform=ax.transAxes))
                ax.text(0.05, y - 0.06, L(zh, a, b), fontsize=7.6,
                        transform=ax.transAxes, va="center")
                ax.text(0.97, y - 0.06, tag, fontsize=7, color="#3f8f6b",
                        transform=ax.transAxes, ha="right", va="center")
        fig.suptitle(L(zh, "三条线各自是怎么走过来的",
                       "How each thread actually got here"), fontsize=11)
        save(fig, "F90-timeline", zh)


if __name__ == "__main__":
    fig_dataset()
    fig_crop_error()
    fig_head()
    fig_wb()
    fig_sharpen()
    fig_pipeline()
    fig_timeline()
    print("done")
