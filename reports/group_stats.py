"""4184 拟合样本按目录拆分：微观（全部混在一起）vs 宏观（每目录先算中位再平均）。

为什么必须两个都给：4184 里「2025.7 青海」一个目录占 2326 张（56%），
只报总体中位等于用一批的难度代表全部。
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

TRUTH = os.path.join(WORK, "work_crop", "拟合样本_裁切真值.csv")
SHIPPED = os.path.join(WORK, "skill", "insect-auto-post-v2", "assets", "data", "crop_coef_v3.json")


def iou(a, b):
    iw = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    ih = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = iw * ih
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def main():
    df = pd.read_csv(TRUTH, encoding="utf-8-sig").dropna(
        subset=["crop_l", "crop_t", "crop_r", "crop_b", "core_l", "full_l"])
    J = json.load(open(SHIPPED, encoding="utf-8"))
    rows = []
    for r in df.itertuples(index=False):
        core = (r.core_l, r.core_t, r.core_r, r.core_b)
        full = (r.full_l, r.full_t, r.full_r, r.full_b)
        hx, hy = r.hx, r.hy
        head = None if (pd.isna(hx) or pd.isna(hy)) else (float(hx), float(hy))
        multi = bool(int(r.multi)) if not pd.isna(getattr(r, "multi", np.nan)) else False
        p = crop_v3.compute_crop(core, full, head, multi, J=J)
        rows.append((r.group, iou(p["crop"], (r.crop_l, r.crop_t, r.crop_r, r.crop_b))))
    d = pd.DataFrame(rows, columns=["group", "iou"])

    per = d.groupby("group").iou.agg(["count", "median", "mean"])
    per = per.sort_values("median")
    micro = float(d.iou.median())
    macro = float(per["median"].mean())
    res = {
        "n": int(len(d)), "groups": int(len(per)),
        "micro_median": micro, "micro_mean": float(d.iou.mean()),
        "ge_0.8": float((d.iou >= 0.8).mean()),
        "macro_median_of_medians": macro,
        "per_group": {k: {"n": int(v["count"]), "median": float(v["median"])}
                      for k, v in per.iterrows()},
    }
    # 去掉青海再看
    d2 = d[~d.group.str.contains("青海", na=False)]
    res["without_qinghai"] = {
        "n": int(len(d2)), "micro_median": float(d2.iou.median()),
        "macro_median_of_medians": float(d2.groupby("group").iou.median().mean()),
    }
    print(json.dumps(res, ensure_ascii=False, indent=1))
    json.dump(res, open(os.path.join(HERE, "numbers_4184_groups.json"), "w",
                        encoding="utf-8"), ensure_ascii=False, indent=2)
    per.to_csv(os.path.join(HERE, "per_group_4184.csv"), encoding="utf-8-sig")


if __name__ == "__main__":
    main()
