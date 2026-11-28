"""裁切公式 v3：105 项二次式，输出一个正方形裁切框（归一化全画幅坐标）。

    输入（全部 NEF 全画幅归一化 0–1）
        core = (l,t,r,b)  本体框（躯干，开运算后）
        full = (l,t,r,b)  全身框（含腿/触角/翅）
        head = (x,y) 或 None
        multi= True 时强制关闭头部项（规则 12）

    输出
        dict(crop=(l,t,r,b), w, cx, cy, canvas_limited, pad_used, head_used)

为什么是正方形
    原片 3:2，归一化坐标里 w==h 就等于物理上的 3:2 裁切。
    只解 `log2w` 一个尺寸量，比同时解 cw/ch 少一组自由度，误差也更稳。

特征（顺序不能改，与 crop_coef_v3.json 的 105 个系数一一对应）
    基础 9 项  log2D, core_w, core_h, full_w, full_h,
               core_cx-0.5, core_cy-0.5, dx_asy, dy_asy
    头部 4 项  hx, hy, hx·(core_cx-0.5), hy·(core_cy-0.5)
    D      = full 面积 / core 面积（离散度）
    dx_asy = (full_cx - core_cx) / core_w
    dy_asy = (full_cy - core_cy) / core_h
    hx,hy  = (头心 - core 中心) / core 宽高      —— 多主体时必须置 0

硬约束顺序（不可调换）
    ① 绝不出界  >  ② 腿到框边 ≥3%  >  ③ IoU 好看
"""
from __future__ import annotations

import json
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
COEF = os.path.join(ROOT, "assets", "data", "crop_coef_v3.json")

_CACHE = {}


def load(path: str = COEF) -> dict:
    if path not in _CACHE:
        _CACHE[path] = json.load(open(path, encoding="utf-8"))
    return _CACHE[path]


def features(core, full, head=None, multi: bool = False):
    """13 项基础特征。头点缺失或多主体时，头 4 项置 0（等价于「无头版」）。"""
    cl, ct, cr, cb = core
    fl, ft, fr, fb = full
    cw = max(cr - cl, 1e-4)
    ch = max(cb - ct, 1e-4)
    ccx, ccy = (cl + cr) / 2, (ct + cb) / 2
    fcx, fcy = (fl + fr) / 2, (ft + fb) / 2
    area_full = max((fr - fl) * (fb - ft), 1e-6)
    D = max(area_full / (cw * ch), 1.0)

    hx = hy = 0.0
    used = False
    if head is not None and not multi:
        hx = (head[0] - ccx) / cw
        hy = (head[1] - ccy) / ch
        used = True

    base = [math.log2(D), cw, ch, fr - fl, fb - ft,
            ccx - 0.5, ccy - 0.5,
            (fcx - ccx) / cw, (fcy - ccy) / ch]
    headf = [hx, hy, hx * (ccx - 0.5), hy * (ccy - 0.5)]
    return base + headf, (ccx, ccy, fcx, fcy, cw, ch, used)


def design(f):
    """[1] + f + 全部两两乘积（含平方）→ 105 维。"""
    v = [1.0] + list(f)
    k = len(f)
    for i in range(k):
        for j in range(i, k):
            v.append(f[i] * f[j])
    return np.asarray(v, float)


def compute_crop(core, full, head=None, multi: bool = False, J: dict = None,
                 ratio: float = 0.0, aspect: float = 0.0):
    """ratio：目标像素宽高比（宽/高）。0 表示「跟随原片比例」，即老行为。
    aspect：画幅自身宽高比（像素），用于把归一化的 dy 换算成目标比例下的高度。"""
    c = J or load()
    f, (ccx, ccy, fcx, fcy, cw, ch, head_used) = features(core, full, head, multi)
    x = design(f)
    if len(x) != len(c["coef_cx"]):
        raise ValueError(f"特征数 {len(x)} 与系数 {len(c['coef_cx'])} 不匹配")

    cx = float(x @ np.asarray(c["coef_cx"]))
    cy = float(x @ np.asarray(c["coef_cy"]))
    w = 2.0 ** float(x @ np.asarray(c["coef_log2w"]))
    pad = float(c.get("pad_min", 0.03))

    # ② 腿留白：框必须装下「全身框 + 每边 pad」
    need_l, need_t = full[0] - pad, full[1] - pad
    need_r, need_b = full[2] + pad, full[3] + pad
    need_w = need_r - need_l
    need_h = need_b - need_t

    # 高度：默认（ratio=0 或画幅未知）与宽相等，即「归一化方形 = 原片比例」
    src_aspect = aspect if aspect and aspect > 0 else 1.0
    r = ratio if ratio and ratio > 0 else 0.0

    # 固定比例时，宽高互相牵制：必须同时满足「装下全身框」的两个方向，
    # 否则选 16:9 遇到瘦高个会把腿切掉（旧实现只给宽加了 need）。
    if r <= 0:
        w = h = max(w, need_w, need_h, 0.05)
    else:
        k = r / src_aspect                      # w = h * k
        h = max(need_h, need_w / k, w / k, 0.05)   # 同时满足两条腿留白与模型预测的宽
        w = h * k

    limited = False
    ratio_cut = False
    ratio_relaxed = False
    if w > 1.0 or h > 1.0:           # ① 画布装不下 → 按比例缩到画布内，标记
        f = min(1.0 / w, 1.0 / h)
        w, h = w * f, h * f
        limited = True
        ratio_cut = (h + 1e-9 < need_h) or (w + 1e-9 < need_w)
    if ratio_cut:
        # 比例和「不切腿」冲突时，不切腿优先：放弃精确比例，放到能装下为止
        w = min(1.0, max(w, need_w))
        h = min(1.0, max(h, need_h))
        ratio_relaxed = True
        ratio_cut = (h + 1e-9 < need_h) or (w + 1e-9 < need_w)

    # 框心先夹进「不能切腿」的可行域
    x0, x1 = cx - w / 2, cx + w / 2
    if x0 > need_l:
        x0, x1 = need_l, need_l + w
    if x1 < need_r:
        x0, x1 = need_r - w, need_r
    y0, y1 = cy - h / 2, cy + h / 2
    if y0 > need_t:
        y0, y1 = need_t, need_t + h
    if y1 < need_b:
        y0, y1 = need_b - h, need_b

    # 再夹进画布
    if x0 < 0 or y0 < 0 or x1 > 1 or y1 > 1:
        limited = True
        x0 = min(max(x0, 0.0), max(0.0, 1.0 - w))
        y0 = min(max(y0, 0.0), max(0.0, 1.0 - h))
        x1, y1 = x0 + w, y0 + h

    return {"crop": (x0, y0, x1, y1), "w": w, "h": h, "ratio_cut": ratio_cut, "ratio_relaxed": ratio_relaxed,
            "cx": (x0 + x1) / 2, "cy": (y0 + y1) / 2,
            "canvas_limited": bool(limited), "pad_used": pad,
            "head_used": bool(head_used), "multi": bool(multi) or head is None}


def leg_pad_ok(crop, full, pad: float = 0.03) -> bool:
    """四条腿是否都在框内、且离框边 ≥ pad。"""
    return (crop[0] <= full[0] - pad + 1e-9 and crop[1] <= full[1] - pad + 1e-9
            and crop[2] >= full[2] + pad - 1e-9 and crop[3] >= full[3] + pad - 1e-9)


def iou(a, b) -> float:
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


if __name__ == "__main__":
    import csv

    src = os.path.join(ROOT, "assets", "data", "selftest_crop_4184.csv")
    if not os.path.exists(src):
        print("自检需要 assets/data/selftest_crop_4184.csv（见 references/03-裁切.md §6）")
        raise SystemExit(0)
    rows = list(csv.DictReader(open(src, encoding="utf-8-sig")))
    ious, lim = [], 0
    for r in rows:
        g = lambda k: float(r[k])  # noqa: E731
        core = (g("core_l"), g("core_t"), g("core_r"), g("core_b"))
        full = (g("full_l"), g("full_t"), g("full_r"), g("full_b"))
        multi = (r.get("multi") == "1")
        head = None if multi else (g("hx"), g("hy"))
        o = compute_crop(core, full, head, multi=multi)
        lim += o["canvas_limited"]
        ious.append(iou(o["crop"], (g("crop_l"), g("crop_t"), g("crop_r"), g("crop_b"))))
    a = np.array(ious)
    print(f"训练集自检 n={len(a)}  IoU 中位 {np.median(a):.4f}  均值 {a.mean():.4f}  "
          f"q25 {np.percentile(a, 25):.4f}  ≥0.80 {(a >= 0.8).mean()*100:.1f}%  "
          f"画布受限 {lim} ({lim/len(a)*100:.1f}%)")
    print("（这是系数回代，高于 5 折留出的 0.8650 属正常）")
