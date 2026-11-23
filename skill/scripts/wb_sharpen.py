"""白平衡（常数 + 批次例外）与按光圈的锐化补偿。

白平衡为什么不是模型
    ΔT = 用户设定 − 相机 As Shot。对 MakerNote 的 as_shot_K 回归，斜率 −1.063（n=1585）；
    对内部推算的 T_as 回归，斜率 −1.000（n=1960）。两个数都对，是同一个行为的两种算法。
    意思是：无论相机判断多少，用户都把它完全抵消，回到同一个固定白点。
    所以「估光源」的算法在原理上预测不了它——方向不对应。

    能落地的只有常数 + 按批次的例外表，见 assets/data/wb_table.csv。
    例外表的值全部来自 wb_calib（1960 行标定表）的批次中位，逐条可核。

锐化为什么按光圈
    小光圈衍射让 MTF 下滑，光圈越小（f 值越大）越需要补锐化。
    分档见 sharpen_table.csv，严格递增：
        ≤2.8 → 20   <4 → 30   <5.6 → 40   <11 → 50   <14 → 60   ≥14 → 65
    2026-11-17 用户修正：旧表把 f/14 以上设为「不写」，方向是反的（光圈越大补得越少），
    现已改成最高档 65，且每档严格递增。

    这张表用户可以直接改：改 assets/data/sharpen_table.csv 即刻生效（进程内缓存，
    重启软件生效）；软件里另有 <程序目录>/data/sharpen_table.csv 的覆盖版本，
    用环境变量 INSECT_SHARPEN_TABLE 指过去。
"""
from __future__ import annotations

import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WB_CSV = os.path.join(ROOT, "assets", "data", "wb_table.csv")
SH_CSV = (os.environ.get("INSECT_SHARPEN_TABLE")
          or os.path.join(ROOT, "assets", "data", "sharpen_table.csv"))

_WB = None
_SH = None


def _load_wb():
    global _WB
    if _WB is None:
        rows = list(csv.DictReader(open(WB_CSV, encoding="utf-8-sig")))
        _WB = {r["batch"]: r for r in rows}
        if "__default__" not in _WB:
            raise RuntimeError(f"{WB_CSV} 缺少 __default__ 行，无法兜底")
    return _WB


def _norm(s: str) -> str:
    return (s or "").replace("\\", "/").strip().lower()


def white_balance(batch: str = ""):
    """按批次名匹配例外表；匹配不到用全局常数 5333 / +16。

    匹配规则：表里的键是目录名的一段，批次字符串**包含**它就算命中；取最长命中，
    避免「雾灵山」同时命中承德（5481/10）与东极仙谷（5212/8）。
    """
    T = _load_wb()
    d = T["__default__"]
    best, best_len = None, -1
    b = _norm(batch)
    for k, v in T.items():
        if k == "__default__":
            continue
        nk = _norm(k)
        if nk and nk in b and len(k) > best_len:
            best, best_len = v, len(k)
    row = best or d
    return {"T": int(float(row["T"])), "Tint": float(row["Tint"]),
            "batch_matched": best["batch"] if best else "",
            "default": best is None,
            "warn": "" if best else f"批次「{batch}」未命中例外表，用默认 5333/+16；"
                                    f"若这场光明显不同，在 wb_table.csv 加一行"}


def batches():
    """列出例外表里所有键（诊断用）。"""
    return [k for k in _load_wb() if k != "__default__"]


def _load_sh():
    global _SH
    if _SH is None:
        _SH = list(csv.DictReader(open(SH_CSV, encoding="utf-8-sig")))
    return _SH


def reload_tables():
    """清掉缓存，下次调用重新读 CSV（改完表不想重启进程时用）。"""
    global _WB, _SH
    _WB = _SH = None


def sharpness(fnumber):
    """按光圈给 Sharpness；读不到光圈返回 None（不写该字段）。

    分档（严格小于，区间左闭右开；见 sharpen_table.csv）：
        f ≤ 2.8   → 20   超大光圈
        f < 4.0   → 30
        f < 5.6   → 40
        f < 11    → 50   衍射开始可见
        f < 14    → 60   衍射明显
        f ≥ 14    → 65   小光圈，补得最狠
    """
    if fnumber is None:
        return None
    try:
        f = float(fnumber)
    except (TypeError, ValueError):
        return None
    for r in _load_sh():
        lo, hi = float(r["f_min"]), float(r["f_max"])
        if lo <= f < hi:
            return int(float(r["amount"])) if r["amount"].strip() else None
    return None
