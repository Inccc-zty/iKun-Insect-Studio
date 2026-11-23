"""头部位置的「记忆式修偏」——不改 ResNet，只学一个残差。

一句话
------
模型给出头点之后，再看一眼「几何量相近的历史修正」：如果以前在差不多的构图下，
你总把点往左上方拖 0.08 个体宽，这一次就先替你拖过去。**不动神经网络，不动权重。**

两条路，按累计条数自动切换
--------------------------
* n < 25    6 近邻（kNN）：找几何向量最像的 6 条历史，按 1/(d+0.08) 加权，
            再乘一个「最近邻有多近」的可信度 —— 就是「平移补过去」。
* n ≥ 25    重拟合一个 7 参数线性残差模型（1 个偏置 + 6 个特征），
            岭回归、标准化、带 n/(n+10) 收缩。这就是「先累计、再重训」，
            只不过重训的是这 7 个数，不是 99 MB 的 ResNet。
            每次新增修正后第一次调用会自动重拟合（毫秒级），也可手动触发。

为什么不去微调 CNN
----------------
* ResNet50 头点模型 99 MB，为了几个点去微调，权重增量要另存、要跟模型版本绑定；
* 二十几条修正喂不进一个 2500 万参数的网络，只会把它拽坏；
* 而残差模型每条记录 ~200 字节，可读、可删、可审计、可导出。

特征（归一化，消除尺度）
------------------------
    core_cx, core_cy            身体框中心
    log2(core_w), log2(core_h)  身体框大小（对数，大小虫同尺度）
    log2(D)                     D = full 面积 / core 面积（离散度）
    log2(core_w / core_h)       身体长宽比

补偿量
------
    offset = (true − pred) / core_w        两条轴都用 core 宽做尺度
    kNN：6 近邻加权，最近邻距离 0 → 全量，到 MAX_DIST → 0
    线性：w·[1, f]，再乘 n/(n+10)
    两条路都截断到 ±0.40 core 宽

存储
----
    $INSECT_HEAD_FIX  >  <skill>/assets/data/head_fix.jsonl     一行一条修正
    同目录 head_bias.json                                        线性模型（7×2 个数）
    软件里用环境变量指到 <程序目录>/data/，换 skill 版本也不丢。
"""
from __future__ import annotations

import json
import math
import os
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_STORE = os.path.join(ROOT, "assets", "data", "head_fix.jsonl")

MIN_K = 3           # 少于这么多条就不敢用 kNN
MAX_DIST = 0.60     # 最近邻距离超过这个值就不补偿（特征空间欧氏距离）
K = 6               # 参与加权的邻居数
MAX_OFFSET = 0.40   # 偏移上限，单位 = core 宽
FIT_MIN = 25        # 累计到这个条数改用线性残差模型
LAM = 0.5           # 岭回归强度（标准化之后）
SHRINK_N = 10       # 收缩系数 n/(n+SHRINK_N)

_LOCK = threading.RLock()
_CACHE = {"key": None, "model": None}


def store_path() -> str:
    return os.environ.get("INSECT_HEAD_FIX") or DEFAULT_STORE


def model_path() -> str:
    return os.path.join(os.path.dirname(store_path()), "head_bias.json")


def _feat(core, full):
    cl, ct, cr, cb = [float(v) for v in core]
    fl, ft, fr, fb = [float(v) for v in full]
    cw = max(cr - cl, 1e-6)
    ch = max(cb - ct, 1e-6)
    fw = max(fr - fl, 1e-6)
    fh = max(fb - ft, 1e-6)
    D = max(fw * fh / (cw * ch), 1.0)
    return [
        (cl + cr) / 2.0,
        (ct + cb) / 2.0,
        math.log2(cw),
        math.log2(ch),
        math.log2(D),
        math.log2(cw / ch),
    ]


def _dist(a, b) -> float:
    # 中心用 1 倍、大小用 0.7 倍、形状用 0.5 倍，避免大小差异压过位置差异
    w = (1.0, 1.0, 0.7, 0.7, 0.5, 0.5)
    return math.sqrt(sum(((x - y) * wi) ** 2 for x, y, wi in zip(a, b, w)))


def load():
    p = store_path()
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    return out


def count() -> int:
    return len(load())


def add(core, full, pred, true, batch="", path="") -> int:
    """记一条「模型给 pred，用户改成 true」。返回累计条数。

    path 是这张照片的完整路径——没有它，导出的样本没法拿去重训（模型要读图）。
    """
    if pred is None or true is None:
        raise ValueError("pred / true 都不能为空")
    p = store_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    rec = {
        "t": round(time.time(), 1),
        "batch": str(batch)[:80],
        "core": [round(float(v), 6) for v in core],
        "full": [round(float(v), 6) for v in full],
        "pred": [round(float(pred[0]), 6), round(float(pred[1]), 6)],
        "true": [round(float(true[0]), 6), round(float(true[1]), 6)],
        "f": [round(v, 6) for v in _feat(core, full)],
        "path": str(path or ""),
    }
    with _LOCK:
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return count()


# ---------------------------------------------------------------- 线性残差模型
def _xy(recs):
    """返回 (F[n,6], DX[n], DY[n])，两个偏移都以各自 core 宽为单位。"""
    F, DX, DY = [], [], []
    for r in recs:
        pc = [float(v) for v in r["core"]]
        rcw = max(pc[2] - pc[0], 1e-6)
        F.append([float(v) for v in (r.get("f") or _feat(r["core"], r["full"]))])
        DX.append((float(r["true"][0]) - float(r["pred"][0])) / rcw)
        DY.append((float(r["true"][1]) - float(r["pred"][1])) / rcw)
    return F, DX, DY


def _ridge(F, y, lam=LAM):
    """标准化 + 闭式岭回归（7 个参数，n 再大也是毫秒级）。"""
    n, m = len(F), len(F[0])
    mu = [sum(row[j] for row in F) / n for j in range(m)]
    sd = [max(math.sqrt(sum((row[j] - mu[j]) ** 2 for row in F) / n), 1e-6)
          for j in range(m)]
    # 设计矩阵：第 0 列是偏置，不标准化
    A = [[1.0] + [(row[j] - mu[j]) / sd[j] for j in range(m)] for row in F]
    d = m + 1
    XtX = [[sum(A[i][a] * A[i][b] for i in range(n)) for b in range(d)] for a in range(d)]
    Xty = [sum(A[i][a] * y[i] for i in range(n)) for a in range(d)]
    for a in range(1, d):          # 偏置不惩罚
        XtX[a][a] += lam
    # 高斯消元（d≤7，直接做）
    M = [row[:] + [Xty[a]] for a, row in enumerate(XtX)]
    for c in range(d):
        piv = max(range(c, d), key=lambda r: abs(M[r][c]))
        if abs(M[piv][c]) < 1e-12:
            return None, mu, sd
        M[c], M[piv] = M[piv], M[c]
        pv = M[c][c]
        for r in range(d):
            if r == c:
                continue
            f = M[r][c] / pv
            if f:
                for k in range(c, d + 1):
                    M[r][k] -= f * M[c][k]
    w = [M[a][d] / M[a][a] for a in range(d)]
    return w, mu, sd


def fit(recs=None, save=True):
    """用累计的修正重拟合 7×2 个系数。返回模型 dict（样本不足返回 None）。"""
    recs = load() if recs is None else recs
    if len(recs) < FIT_MIN:
        return None
    F, DX, DY = _xy(recs)
    wx, mu, sd = _ridge(F, DX)
    wy, _, _ = _ridge(F, DY)
    if wx is None or wy is None:
        return None
    pred = []
    for row, a, b in zip(F, DX, DY):
        z = [1.0] + [(row[j] - mu[j]) / sd[j] for j in range(len(mu))]
        pred.append((sum(w * v for w, v in zip(wx, z)) - a,
                     sum(w * v for w, v in zip(wy, z)) - b))
    rmse = math.sqrt(sum(p[0] ** 2 + p[1] ** 2 for p in pred) / (2 * len(pred)))
    model = {
        "n": len(recs),
        "t": round(time.time(), 1),
        "mu": [round(v, 6) for v in mu], "sd": [round(v, 6) for v in sd],
        "wx": [round(v, 6) for v in wx], "wy": [round(v, 6) for v in wy],
        "rmse": round(rmse, 4),
        "shrink": round(len(recs) / (len(recs) + SHRINK_N), 4),
        "feat": ["bias", "core_cx", "core_cy", "log2_cw", "log2_ch", "log2_D", "log2_ar"],
    }
    if save:
        try:
            os.makedirs(os.path.dirname(model_path()), exist_ok=True)
            with open(model_path(), "w", encoding="utf-8") as f:
                json.dump(model, f, ensure_ascii=False, indent=1)
        except OSError:
            pass
    with _LOCK:
        try:
            _CACHE["key"] = (len(recs), os.path.getmtime(store_path()))
        except OSError:
            _CACHE["key"] = (len(recs), 0.0)
        _CACHE["model"] = model
    return model


def _current_model(n_store):
    """拿到跟当前记录一致的模型；新记录会自动触发一次重拟合。"""
    if n_store < FIT_MIN:
        return None
    try:
        key = (n_store, os.path.getmtime(store_path()))
    except OSError:
        key = (n_store, 0.0)
    with _LOCK:
        if _CACHE["key"] == key and _CACHE["model"]:
            return _CACHE["model"]
    m = fit()
    if m:
        with _LOCK:
            _CACHE["key"] = key
    return m


def stats():
    """给界面看的：累计条数、当前模式、残差。"""
    recs = load()
    n = len(recs)
    out = {"n": n, "mode": "off", "rmse": None, "fit_min": FIT_MIN,
           "knn_k": K, "store": store_path()}
    if n == 0:
        return out
    if n < MIN_K:
        out["mode"] = "wait"
        return out
    if n >= FIT_MIN:
        m = _current_model(n)
        if m:
            out["mode"] = "linear"
            out["rmse"] = m["rmse"]
            out["coef"] = m
            return out
    out["mode"] = "knn"
    F, DX, DY = _xy(recs)
    out["mean_dx"] = round(sum(DX) / len(DX), 4)
    out["mean_dy"] = round(sum(DY) / len(DY), 4)
    return out


def apply(core, full, head):
    """按历史修正量微调 head。返回 (head, info)。

    info = {"n": 用了多少条, "mode": "knn"|"linear", "dx","dy": 施加的偏移(单位 core 宽)}
    没有可用历史时原样返回，info["n"]=0。
    """
    if head is None:
        return head, {"n": 0, "mode": "off", "applied": False}
    recs = load()
    n = len(recs)
    if n < MIN_K:
        return head, {"n": n, "mode": "off", "applied": False}

    f0 = _feat(core, full)
    cw = max(float(core[2]) - float(core[0]), 1e-6)
    dx = dy = 0.0
    info = {"n": n, "applied": True}

    model = _current_model(n)
    if model:
        mu, sd = model["mu"], model["sd"]
        z = [1.0] + [(f0[j] - mu[j]) / sd[j] for j in range(len(mu))]
        dx = sum(w * v for w, v in zip(model["wx"], z)) * model["shrink"]
        dy = sum(w * v for w, v in zip(model["wy"], z)) * model["shrink"]
        info.update(mode="linear", rmse=model["rmse"], shrink=model["shrink"])
    else:
        scored = []
        for r in recs:
            rf = r.get("f") or _feat(r["core"], r["full"])
            d = _dist(f0, rf)
            pc = [float(v) for v in r["core"]]
            rcw = max(pc[2] - pc[0], 1e-6)
            scored.append((d,
                           (float(r["true"][0]) - float(r["pred"][0])) / rcw,
                           (float(r["true"][1]) - float(r["pred"][1])) / rcw))
        scored.sort(key=lambda x: x[0])
        near = scored[:K]
        dmin = near[0][0]
        info["d"] = round(dmin, 3)
        if dmin > MAX_DIST:
            return head, {"n": 0, "d": round(dmin, 3), "mode": "knn", "applied": False}
        ws = [1.0 / (d + 0.08) for d, _, _ in near]
        wsum = sum(ws)
        dx = sum(w * o[1] for w, o in zip(ws, near)) / wsum
        dy = sum(w * o[2] for w, o in zip(ws, near)) / wsum
        conf = max(0.0, 1.0 - dmin / MAX_DIST) ** 0.5   # 越远越保守
        dx *= conf
        dy *= conf
        info.update(mode="knn", conf=round(conf, 3))

    dx = max(-MAX_OFFSET, min(MAX_OFFSET, dx))
    dy = max(-MAX_OFFSET, min(MAX_OFFSET, dy))
    nh = (float(head[0]) + dx * cw, float(head[1]) + dy * cw)
    nh = (min(max(nh[0], 0.0), 1.0), min(max(nh[1], 0.0), 1.0))
    info.update(dx=round(dx, 4), dy=round(dy, 4))
    return nh, info


def export_csv(path: str):
    """把累计的修正导成**能直接重训**的 CSV（列名对齐 头部标注_500.csv）。

    必须有 path 才能重训——老记录没有 path 的会写成空，并在返回里计数。
    返回 (总条数, 可用条数)。
    """
    recs = load()
    if not recs:
        return 0, 0
    cols = ["nef", "batch", "hx", "hy", "ai_hx", "ai_hy", "ai_shift", "multi",
            "core_l", "core_t", "core_r", "core_b",
            "full_l", "full_t", "full_r", "full_b"]
    import csv
    usable = 0
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in recs:
            c, fu = r["core"], r["full"]
            cw = max(c[2] - c[0], 1e-6)
            d = ((r["true"][0] - r["pred"][0]) ** 2 +
                 (r["true"][1] - r["pred"][1]) ** 2) ** 0.5 / cw
            pth = r.get("path", "")
            if pth:
                usable += 1
            w.writerow([pth, r.get("batch", ""),
                        round(r["true"][0], 6), round(r["true"][1], 6),
                        round(r["pred"][0], 6), round(r["pred"][1], 6),
                        round(d, 4), 0,
                        *[round(float(v), 6) for v in c],
                        *[round(float(v), 6) for v in fu]])
    return len(recs), usable


def clear():
    """清空历史（连同线性模型一起）。"""
    for p in (store_path(), model_path()):
        if os.path.exists(p):
            os.remove(p)
    with _LOCK:
        _CACHE.update(key=None, model=None)
