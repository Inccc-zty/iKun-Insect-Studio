"""裁切模型的「成片相对」空间：只用裁好的 JPG 就能训练。

为什么可行
----------
成片本身就是裁切框里的画面。在成片上跑一次掩膜，能直接量到：

    虫体框宽 cw、高 ch（以成片为 1 归一化）
    虫体中心 (ccx, ccy)
    头点、整体框（含附肢）

于是「成片相对于虫体有多大、把虫体放在哪」就是可测量的事实：

    t0 = log2(1 / cw)      成片宽 = 虫体宽的多少倍
    t1 = log2(1 / ch)      成片高 = 虫体高的多少倍
    ox = ccx - 0.5         虫体中心偏离成片中心多少（成片宽为单位）
    oy = ccy - 0.5

这四件事由虫子的形状决定（离散度、体型比、附肢占比、头朝向），而这些描述量本身
与画面尺度无关，所以在成片上算出来的，与在全幅原片上算出来的**是同一个数**。

推理时倒过来用：全幅上量到虫体框，代进模型得到 (t0, t1, ox, oy)，就能解出裁切框

    W = cw · 2**t0 ,  H = ch · 2**t1
    cx = ccx + ox·W , cy = ccy + oy·H

所以它不需要原片、不需要 XMP——原片只是「另一种量法」，不是必需的前提。
"""
from __future__ import annotations

import math

import numpy as np

import crop_v3

SPACE = "crop_relative"
HEAD_KEYS = ("t0", "t1", "ox", "oy")


def _to_width_units(box, aspect):
    """把「按画幅归一化」的框换成「以画幅宽为单位」的框。

    y 除以 aspect（= 画幅宽/高）之后，横竖同一个单位，宽高比才是真实比例；
    否则同一只虫在一个 3:2 的成片和一个 1:1 的成片里会被算成不同的体型。
    """
    return (box[0], box[1] / aspect, box[2], box[3] / aspect)


def features(core, full, head=None, multi=False, aspect=1.0):
    """13 项尺度无关描述量（全部以画幅宽为单位）。"""
    core = _to_width_units(core, aspect)
    full = _to_width_units(full, aspect)
    head = (head[0], head[1] / aspect) if head is not None else None
    cl, ct, cr, cb = core
    fl, ft, fr, fb = full
    cw = max(cr - cl, 1e-4)
    ch = max(cb - ct, 1e-4)
    ccx, ccy = (cl + cr) / 2, (ct + cb) / 2
    fcx, fcy = (fl + fr) / 2, (ft + fb) / 2
    D = max((fr - fl) * (fb - ft) / (cw * ch), 1.0)
    hx = hy = 0.0
    if head is not None and not multi:
        hx = (head[0] - ccx) / cw
        hy = (head[1] - ccy) / ch
    base = [math.log2(D), math.log2(cw / ch),
            (fr - fl) / cw, (fb - ft) / cw,
            (fcx - ccx) / cw, (fcy - ccy) / cw,
            (fr - fl) / (fb - ft), 0.0, 0.0]
    return base + [hx, hy, hx * (fr - fl) / cw, hy * (fb - ft) / cw], (ccx, ccy, cw, ch)


def target(core, full, head=None, multi=False):
    """在「画面就是成片」的前提下，量出模型要学的四个数（画幅归一化）。"""
    _f, (ccx, ccy, cw, ch) = features(core, full, head, multi, aspect=1.0)
    return [math.log2(1.0 / cw), math.log2(1.0 / ch), ccx - 0.5, ccy - 0.5]


def design(f):
    return crop_v3.design(f)


def _ridge(X, y, mu, sd, lam=0.03):
    """标准化后的岭回归；截距不惩罚。与 refit_crop.ridge 同口径。"""
    Z = (X - mu) / sd
    Z[:, 0] = X[:, 0]
    n, k = Z.shape
    A = Z.T @ Z + lam * np.eye(k)
    A[0, 0] -= lam
    return np.linalg.solve(A, Z.T @ y)


def fit(rows, lam=0.03):
    """rows: [(core, full, head, multi, aspect)]，全部来自成片。"""
    X, Y = [], []
    for core, full, head, multi, aspect in rows:
        f, _ = features(core, full, head, multi, aspect=aspect)
        X.append(design(f))
        Y.append(target(core, full, head, multi))
    X = np.asarray(X, float)
    Y = np.asarray(Y, float)
    if len(X) < 50:
        raise RuntimeError(f"有效样本 {len(X)}/50 / Usable samples: {len(X)}/50")
    mu, sd = X.mean(0), X.std(0) + 1e-9
    mu[0], sd[0] = 0.0, 1.0
    coefs = {k: _ridge(X, Y[:, i], mu, sd, lam) for i, k in enumerate(HEAD_KEYS)}
    Z = (X - mu) / sd
    Z[:, 0] = X[:, 0]
    pred = np.column_stack([Z @ coefs[k] for k in HEAD_KEYS])
    err = np.abs(pred - Y)
    return {"version": "studio-refit", "space": SPACE, "lam": lam, "n": int(len(X)),
            "mu": mu.tolist(), "sd": sd.tolist(),
            "coef_t0": coefs["t0"].tolist(), "coef_t1": coefs["t1"].tolist(),
            "coef_ox": coefs["ox"].tolist(), "coef_oy": coefs["oy"].tolist(),
            "mae_in": {"t0": round(float(err[:, 0].mean()), 4),
                       "t1": round(float(err[:, 1].mean()), 4),
                       "ox": round(float(err[:, 2].mean()), 4),
                       "oy": round(float(err[:, 3].mean()), 4)},
            "note": "由成片相对空间拟合；推理时按 W=cw·2^t0 反解裁切框"}


def compute_crop(core, full, head=None, multi=False, J=None, aspect=1.0, ratio=0.0):
    """把相对系数还原成裁切框，并沿用「不出界 → 腿留白 3% → 贴合」的约束顺序。"""
    c = J or {}
    f, _u = features(core, full, head, multi, aspect=aspect)
    ccx, ccy = (core[0] + core[2]) / 2, (core[1] + core[3]) / 2
    cw, ch = max(core[2] - core[0], 1e-4), max(core[3] - core[1], 1e-4)
    x = crop_v3.design(f)
    if len(x) != len(c["coef_t0"]):
        raise ValueError(f"特征数 {len(x)} 与系数 {len(c['coef_t0'])} 不匹配")
    mu = np.asarray(c["mu"], float)
    sd = np.asarray(c["sd"], float)
    z = (x - mu) / sd
    z[0] = x[0]
    t0, t1, ox, oy = (float(z @ np.asarray(c[f"coef_{k}"], float)) for k in HEAD_KEYS)
    t0, t1 = min(t0, 3.5), min(t1, 3.5)          # 最多放大 11 倍，防止外推出天际
    W = min(cw * (2 ** t0), 1.0)
    H = min(ch * (2 ** t1), 1.0)

    # 默认（ratio<=0）一律取**照片自身的比例**：成片训练时学的 t1 只用来定"多大"，
    # 不用来定"什么比例"，否则换一批成片，默认比例就跟着漂。
    pad = 0.03
    need_w = min(1.0, max(full[2] - full[0], 0.0) + 2 * pad)
    need_h = min(1.0, max(full[3] - full[1], 0.0) + 2 * pad)
    H = min(W, 1.0)          # 原片比例 = 归一化正方形（H_norm == W_norm）
    if ratio and ratio > 0:
        # 与 crop_v3 同一套规则：保持像素面积，比例精确；装不下就先长大，最后才放宽比例
        A0 = max(W, 0.05) ** 2 * aspect
        W = math.sqrt(A0 * ratio) / aspect
        H = W * aspect / ratio
        k = max(1.0, need_w / max(W, 1e-9), need_h / max(H, 1e-9))
        W *= k
        H *= k
        if W > 1.0 or H > 1.0:
            f = min(1.0 / W, 1.0 / H)
            W, H = W * f, H * f
    cx = ccx - ox * W      # ox = 虫心在成片中的偏移；反解时符号相反
    cy = ccy - oy * H
    box = [cx - W / 2, cy - H / 2, cx + W / 2, cy + H / 2]

    pad_used = 0.03
    limited = (box[0] < 0 or box[1] < 0 or box[2] > 1 or box[3] > 1)
    box = _enforce(box, full, pad_used)
    limited = limited or (box[0] <= 1e-6 or box[1] <= 1e-6
                          or box[2] >= 1 - 1e-6 or box[3] >= 1 - 1e-6)
    return {"crop": tuple(box), "pad_used": pad_used,
            "w": round(box[2] - box[0], 6),
            "cx": round((box[0] + box[2]) / 2, 6),
            "cy": round((box[1] + box[3]) / 2, 6),
            "canvas_limited": bool(limited),
            "rel": {"t0": round(t0, 3), "t1": round(t1, 3),
                    "ox": round(ox, 3), "oy": round(oy, 3)}}


def _enforce(box, full, pad):
    """① 装下全身框 + pad ② 框心夹进不切腿的可行域 ③ 再夹进画布。"""
    x0, y0, x1, y1 = box
    W, H = max(x1 - x0, 0.02), max(y1 - y0, 0.02)
    need_l, need_t = full[0] - pad, full[1] - pad
    need_r, need_b = full[2] + pad, full[3] + pad
    # 放大时**等比放大**，否则装下全身框这一步会把比例改掉
    need_w, need_h = need_r - need_l, need_b - need_t
    k = max(1.0, need_w / W, need_h / H, 0.05 / max(W, H))
    W, H = W * k, H * k
    if W > 1.0 or H > 1.0:
        f = min(1.0 / W, 1.0 / H)
        W, H = W * f, H * f
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    x0, x1 = cx - W / 2, cx + W / 2
    if x0 > need_l:
        x0, x1 = need_l, need_l + W
    if x1 < need_r:
        x0, x1 = need_r - W, need_r
    y0, y1 = cy - H / 2, cy + H / 2
    if y0 > need_t:
        y0, y1 = need_t, need_t + H
    if y1 < need_b:
        y0, y1 = need_b - H, need_b
    if x0 < 0 or y0 < 0 or x1 > 1 or y1 > 1:
        x0 = min(max(x0, 0.0), max(0.0, 1.0 - W))
        y0 = min(max(y0, 0.0), max(0.0, 1.0 - H))
        x1, y1 = x0 + W, y0 + H
    return [x0, y0, x1, y1]
