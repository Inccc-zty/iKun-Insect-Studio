"""自动曝光：双参数模型。

    EV = 3.0416 − 0.02108 · L_in − 0.01362 · L_box

    L_in  = 掩膜内（腐蚀掉边缘混色像素后）亮度 L* 的 95 分位
    L_box = 全身外接矩形内、掩膜之外的亮度 L* 的 95 分位

为什么是这两个量
    * 你定 EV 看的是「最亮那批有结构的高光会不会溢出」，不是平均亮度。
      分位扫描（p80–p99.5）峰在 p95；p99 以上是甲壳/露珠的镜面反光，属噪声。
    * 主体只占画面约 3%，任何网格测光都被背景稀释；「知不知道虫在哪」本身
      就值 0.028 MAE。
    * 关系严格线性：二次、对数、交互、岭回归全部更差。

精度看哪里
    具体指标只写在 references/04-曝光.md，代码里不重复。
    一条要记住：留出 MAE 的量级是 0.28–0.29 档，常数基线 0.42 档。
    谁报的 MAE 落在 0.27 以下，先怀疑他漏了按批次留出。

边界
    * L_in ≥ 96 时内嵌 JPEG 高光已饱和，EV 不可靠 → 打 warning 标记。
    * 截距 b0 只在「NEF 内嵌预览」这套渲染坐标里成立，换渲染器要重标。
"""
from __future__ import annotations

import json
import os

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
COEF = os.path.join(ROOT, "assets", "data", "ev_coef.json")

_J = json.load(open(COEF, encoding="utf-8"))
_PATH = COEF
_BASE = dict(_J)          # 内置那一套，切回来用
# 换系数时缺的字段用内置兜底（clip / saturation_warn / 说明文字）
_FALLBACK = ("clip", "saturation_warn", "formula", "L_in", "L_box")


def use(path: str = None):
    """切到另一套曝光系数；path 为空 = 回到内置。

    只换 b0/b1/b2 与统计量，clip / saturation_warn 这些口径字段永远沿用内置，
    免得一个只写了三个数的文件把裁剪范围改成 0–1。
    """
    global _J, _PATH
    p = os.path.abspath(path) if path else COEF
    if p == _PATH:
        return _J
    d = json.load(open(p, encoding="utf-8"))
    for k in ("b0", "b1", "b2"):
        if k not in d:
            raise ValueError(f"{os.path.basename(p)} 缺少 {k}")
    for k in _FALLBACK:
        d.setdefault(k, _BASE.get(k))
    _J, _PATH = d, p
    return _J


def current():
    """给界面看：现在用的是哪一套。"""
    return {"path": _PATH,
            "builtin": os.path.abspath(_PATH) == os.path.abspath(COEF),
            "b0": _J.get("b0"), "b1": _J.get("b1"), "b2": _J.get("b2"),
            "n": _J.get("n"), "mae_holdout": _J.get("mae_holdout")}


def lstar(bgr: np.ndarray) -> np.ndarray:
    """BGR(uint8) → CIELAB L*（D65，Rec.709 亮度）。"""
    rgb = bgr[..., ::-1].astype(np.float32) / 255.0
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    y = 0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2]
    return np.where(y > 0.008856, 116.0 * np.cbrt(np.clip(y, 0, 1)) - 16.0, 903.3 * y)


def _erode(mask: np.ndarray, scale: float = 1.0) -> np.ndarray:
    """按距离变换腐蚀，半径随虫子大小自适应。"""
    m = mask.astype(np.uint8)
    if m.sum() == 0:
        return m.astype(bool)
    dist = cv2.distanceTransform(m, cv2.DIST_L2, 5)
    r = max(1.5 * scale, 0.03 * np.sqrt(m.sum()))
    inner = dist >= r
    if inner.sum() < 100 * scale * scale:
        inner = dist >= max(1.0 * scale, dist.max() * 0.5)
    return inner


def measure(bgr: np.ndarray, mask_small: np.ndarray, full_box, long_side: int = 900):
    """返回 L_in / L_box / 诊断量。

    bgr        预览（任意尺寸）
    mask_small S×S 掩膜（对应整幅归一化）
    full_box   (l,t,r,b) 归一化
    """
    H, W = bgr.shape[:2]
    k = long_side / max(W, H)
    sm = cv2.resize(bgr, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k < 1 else bgr
    h, w = sm.shape[:2]
    m = cv2.resize(mask_small, (w, h), interpolation=cv2.INTER_NEAREST) > 127

    L = lstar(sm)
    inner = _erode(m, scale=max(1.0, np.sqrt(w * h) / 900.0))
    l_in = float(np.percentile(L[inner], 95)) if inner.sum() > 50 else None

    l, t, r, b = full_box
    x0, x1 = int(max(0, l * w)), int(min(w, np.ceil(r * w)))
    y0, y1 = int(max(0, t * h)), int(min(h, np.ceil(b * h)))
    box = np.zeros((h, w), bool)
    box[y0:y1, x0:x1] = True
    bg = box & (~m)
    l_box = float(np.percentile(L[bg], 95)) if bg.sum() > 50 else None

    return {"L_in": None if l_in is None else round(l_in, 2),
            "L_box": None if l_box is None else round(l_box, 2),
            "L_all_p95": round(float(np.percentile(L, 95)), 2),
            "occ": round(float(m.mean()), 4),
            "bg_frac": round(float(bg.sum() / max(box.sum(), 1)), 3)}


def predict(L_in: float, L_box: float):
    b0, b1, b2 = _J["b0"], _J["b1"], _J["b2"]
    ev = b0 + b1 * L_in + b2 * L_box
    lo, hi = _J["clip"]
    clipped = min(max(ev, lo), hi)
    return {"ev": round(clipped, 2), "ev_raw": round(ev, 3),
            "clipped": bool(abs(clipped - ev) > 1e-9),
            "saturated": bool(L_in >= _J["saturation_warn"]),
            "warn": ("高光已饱和：内嵌 JPEG 的 p95 压在 100 上，此值不可靠，建议人工核"
                     if L_in >= _J["saturation_warn"] else "")}


def measure_pil(prev, mask_small, full_box, long_side: int = 900):
    """直接从 PIL 预览测量，内部先缩图再转 BGR。

    跑批时 PIL 全幅是 8256×5504（≈136 MB），再转一份 BGR 又 136 MB。
    本机 16 GB 内存、桌面常态占十几 G 时，两张图就能把内存吃到 OOM。
    这里先缩到长边 900（≈1.6 MB）再算，对 p95 没有可观测影响。
    """
    import cv2
    import numpy as np

    w, h = prev.size
    if max(w, h) > long_side:
        k = long_side / max(w, h)
        prev = prev.resize((max(int(w * k), 1), max(int(h * k), 1)))
    bgr = cv2.cvtColor(np.asarray(prev), cv2.COLOR_RGB2BGR)
    return measure(bgr, mask_small, full_box, long_side=long_side)
