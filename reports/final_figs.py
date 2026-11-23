"""最终数据集（范围内 2275 张 / 14 目录）的三张总览图，中英各一份。

只画「一眼能读懂」的东西：每目录多少张、每目录中位 IoU、整体分布。
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

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

OUTS = [os.path.join(ROOT, "figures"), os.path.join(WORK, "图集_待选")]
J = json.load(open(os.path.join(WORK, "skill", "insect-auto-post-v2", "assets", "data",
                                "crop_coef_v3.json"), encoding="utf-8"))


def iou(a, b):
    iw = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    ih = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = iw * ih
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def short(name: str) -> str:
    """去掉日期前缀和"北京"，只留人能认的部分。"""
    if name == "1微距拍的昆虫":
        return "青海"
    import re as _re
    s = _re.sub(r"^\d{4}\.\d{1,2}\.\d{1,2}(-\d{1,2}(\.\d{1,2})?)?\s*", "", name)
    s = _re.sub(r"^\d{4}\.\d{1,2}\s*", "", s)
    s = s.replace("北京", "").replace("(还没备份)", "").replace("（还没备份）", "")
    return s.strip() or name


def main():
    m = pd.read_csv(os.path.join(WORK, "work_crop", "昆虫总表_v4_范围内.csv"),
                    encoding="utf-8-sig")
    m = m[m.nef.map(lambda p: isinstance(p, str) and in_scope(p))]
    # 与报告口径一致：只要昆虫 + 可标定
    m = m[(m.get("insect_ok") == 1) & (m.get("usable_for_calib") == 1)]
    m = m.dropna(subset=["CropLeft", "CropTop", "CropRight", "CropBottom",
                         "core_l", "core_t", "core_r", "core_b",
                         "full_l", "full_t", "full_r", "full_b"]).reset_index(drop=True)
    m["dir"] = m.nef.map(lambda p: os.path.basename(os.path.dirname(str(p).replace("/", "\\"))))

    rows = []
    for r in m.itertuples(index=False):
        core = (r.core_l, r.core_t, r.core_r, r.core_b)
        full = (r.full_l, r.full_t, r.full_r, r.full_b)
        head = None if pd.isna(r.hcx) else (r.hcx, r.hcy)
        p = crop_v3.compute_crop(core, full, head, False, J=J)
        rows.append((r.dir, iou(p["crop"], (r.CropLeft, r.CropTop, r.CropRight, r.CropBottom))))
    d = pd.DataFrame(rows, columns=["dir", "iou"])
    stat = d.groupby("dir").iou.agg(["count", "median"]).sort_values("median")
    # 同名目录（两个"虎峪"）要区分开，否则标签会重叠成一格
    labels = []
    seen = {}
    for k in stat.index:
        base = short(k)
        if base in seen:
            seen[base] += 1
            base = f"{base}({k.split()[0]})"
        else:
            seen[base] = 0
        labels.append(base)
    micro = float(d.iou.median())
    macro = float(stat["median"].mean())

    for lang in ("zh", "en"):
        zh = lang == "zh"
        # 1) 每目录张数
        fig, ax = plt.subplots(figsize=(7.2, 5.0))
        s = stat.sort_values("count")
        colors = ["#c0392b" if k == "1微距拍的昆虫" else "#3f8f6b" for k in s.index]
        ax.barh([short(k) for k in s.index], s["count"], color=colors, alpha=.9)
        ax.set_ylim(-0.6, len(s) - 0.4)
        for i, v in enumerate(s["count"]):
            ax.text(v + 8, i, str(int(v)), va="center", fontsize=8)
        ax.set_xlabel("photos" if not zh else "照片数")
        ax.set_title(f"Final set: {len(d)} photos / {len(stat)} folders"
                     if not zh else f"最终数据集：{len(d)} 张 / {len(stat)} 个目录")
        ax.grid(axis="x", alpha=.25)
        for od in OUTS:
            p = os.path.join(od, lang, ("01_数据集总览" if zh else "01_dataset") + ".png")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            fig.tight_layout(); fig.savefig(p, dpi=160, facecolor="white")
        plt.close(fig)

        # 2) 每目录中位 IoU
        fig, ax = plt.subplots(figsize=(7.2, 5.0))
        colors = ["#c0392b" if k == "1微距拍的昆虫" else "#3f8f6b" for k in stat.index]
        ax.barh(labels, stat["median"], color=colors, alpha=.9)
        ax.set_ylim(-0.6, len(stat) - 0.35)
        ax.axvline(micro, color="#333", lw=1, ls="--")
        ax.text(micro + .004, -0.6, ("micro %.3f" % micro) if not zh else ("总体 %.3f" % micro),
                fontsize=8, color="#333")
        for i, (v, n) in enumerate(zip(stat["median"], stat["count"])):
            ax.text(v + .006, i, f"{v:.3f}  n={int(n)}", va="center", fontsize=7.5)
        ax.set_xlim(min(stat["median"]) - .05, 1.0)
        ax.set_xlabel("IoU median" if not zh else "IoU 中位")
        ax.set_title(("Crop by folder · macro %.3f" % macro) if not zh
                     else ("裁切成绩（按目录）· 宏观平均 %.3f" % macro))
        ax.grid(axis="x", alpha=.25)
        for od in OUTS:
            p = os.path.join(od, lang, ("03_裁切成绩_逐目录" if zh else "03_crop_by_folder") + ".png")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            fig.tight_layout(); fig.savefig(p, dpi=160, facecolor="white")
        plt.close(fig)

        # 3) 分布
        fig, ax = plt.subplots(figsize=(6.6, 4.0))
        ax.hist(d.iou, bins=60, range=(0, 1), color="#3f8f6b", alpha=.85)
        ax.axvline(micro, color="#c0392b", lw=1.5,
                   label=(f"median {micro:.3f}" if not zh else f"中位 {micro:.3f}"))
        ax.set_xlabel("IoU")
        ax.set_ylabel("photos" if not zh else "张数")
        ax.set_title("Crop IoU distribution" if not zh else "裁切 IoU 分布")
        ax.legend(frameon=False)
        ax.grid(alpha=.25)
        for od in OUTS:
            p = os.path.join(od, lang, ("04_裁切分布" if zh else "04_iou_hist") + ".png")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            fig.tight_layout(); fig.savefig(p, dpi=160, facecolor="white")
        plt.close(fig)

    res = {"n": int(len(d)), "dirs": int(len(stat)), "micro": micro, "macro": macro,
           "per_dir": {k: {"n": int(v["count"]), "median": float(v["median"])}
                       for k, v in stat.iterrows()}}
    json.dump(res, open(os.path.join(HERE, "numbers_final.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps({k: res[k] for k in ("n", "dirs", "micro", "macro")}, indent=1))


if __name__ == "__main__":
    main()
