"""系数模型（裁切 105 项 / 曝光 3 参数）的登记表。

三种来源，一律可以随时切回去：

    builtin   skill/assets/data 里那两份，只读，永远在
    train     训练页产出，自动落到 data/models/<kind>/训练_YYYYmmdd_HHMM.json
    import    别人给你的 JSON，从这里导入（几 KB，拷过来就能用）

为什么可以切：它们只是系数文件，不含权重、不含代码。
裁切那 105 项学的是「这个人的构图习惯」，换人用别人的系数通常更差——
所以列表里把样本量和留出指标一起显示，切换前你自己能看见。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time

from .paths import app_root, skill_dir

KIND_DIR = {"crop": "crop", "ev": "ev"}
LABEL = {"crop": "裁切", "ev": "曝光"}


def builtin_path(kind: str) -> str:
    base = os.path.join(skill_dir(), "assets", "data")
    return os.path.join(base, "crop_coef_v3.json" if kind == "crop" else "ev_coef.json")


def store_dir(kind: str) -> str:
    d = os.path.join(app_root(), "data", "models", KIND_DIR[kind])
    os.makedirs(d, exist_ok=True)
    return d


def _peek(path: str, kind: str):
    d = json.load(open(path, encoding="utf-8"))
    if kind == "crop":
        for k in ("coef_cx", "coef_cy", "coef_log2w"):
            if k not in d:
                raise ValueError(f"缺少 {k}")
        n = len(d["coef_cx"])
        if not (len(d["coef_cy"]) == len(d["coef_log2w"]) == n):
            raise ValueError("三组系数长度不一致")
        return {"n": d.get("n") or n, "metric": d.get("iou_holdout"),
                "fitted": d.get("fitted") or d.get("version") or ""}
    for k in ("b0", "b1", "b2"):
        if k not in d:
            raise ValueError(f"缺少 {k}")
    return {"n": d.get("n"), "metric": d.get("mae_holdout"),
            "fitted": d.get("version") or d.get("fitted") or ""}


def _label(name: str, info: dict, kind: str, builtin=False, en=False) -> str:
    bits = [name]
    if info.get("n"):
        bits.append(f"{int(info['n'])} photos" if en else f"{int(info['n'])} 张")
    m = info.get("metric")
    if isinstance(m, (int, float)):
        bits.append(("hold-out " if en else "留出 ")
                    + f"{'IoU' if kind == 'crop' else 'MAE'} {m:.3f}")
    return " · ".join(bits)


def list_models(kind: str, en: bool = False):
    """返回 [{path, name, label, builtin, n, metric}]，第一项永远是内置。"""
    out = []
    bp = builtin_path(kind)
    try:
        info = _peek(bp, kind)
        out.append({"path": "", "name": "Built-in" if en else "内置", "builtin": True,
                    "label": _label("Built-in" if en else "内置", info, kind, True, en),
                    **info})
    except Exception:          # noqa: BLE001  算法包损坏也要能进界面
        out.append({"path": "", "name": "Built-in" if en else "内置", "builtin": True,
                    "label": ("Built-in (failed to read)" if en else "内置（读取失败）"),
                    "n": None, "metric": None})
    d = store_dir(kind)
    for f in sorted(os.listdir(d)):
        if not f.lower().endswith(".json"):
            continue
        p = os.path.join(d, f)
        try:
            info = _peek(p, kind)
        except Exception as e:      # noqa: BLE001
            out.append({"path": p, "name": os.path.splitext(f)[0], "builtin": False,
                        "label": f"{os.path.splitext(f)[0]}（不可用：{e}）",
                        "n": None, "metric": None, "broken": True})
            continue
        name = os.path.splitext(f)[0]
        out.append({"path": p, "name": name, "builtin": False,
                    "label": _label(name, info, kind), **info})
    return out


def resolve(kind: str, path: str):
    """配置里的路径 → 实际要用的文件。空/不存在/坏文件一律退回内置，并说明原因。"""
    if not path:
        return "", ""
    if not os.path.exists(path):
        return "", f"找不到 {os.path.basename(path)}，已退回内置"
    try:
        _peek(path, kind)
    except Exception as e:      # noqa: BLE001
        return "", f"{os.path.basename(path)} 不可用（{e}），已退回内置"
    return path, ""


def import_file(kind: str, src: str) -> str:
    """把别人的 JSON 收进 data/models/<kind>/。重复导入自动改名。"""
    info = _peek(src, kind)     # 先验，坏文件不进库
    stem = re.sub(r'[\\/:*?"<>|]+', "_", os.path.splitext(os.path.basename(src))[0])[:60]
    d = store_dir(kind)
    dst = os.path.join(d, f"{stem}.json")
    i = 2
    while os.path.exists(dst):
        dst = os.path.join(d, f"{stem}_{i}.json")
        i += 1
    shutil.copy2(src, dst)
    return dst


def adopt_trained(kind: str, src: str) -> str:
    """训练产物进库（训练页结束时调）。名字带时间戳，不覆盖旧的。"""
    info = _peek(src, kind)
    stamp = time.strftime("%Y%m%d_%H%M")
    d = store_dir(kind)
    dst = os.path.join(d, f"训练_{stamp}.json")
    i = 2
    while os.path.exists(dst):
        dst = os.path.join(d, f"训练_{stamp}_{i}.json")
        i += 1
    shutil.copy2(src, dst)
    return dst


def active(kind: str, cfg) -> str:
    """界面显示用：当前生效的那一条（找不到就返回内置）。"""
    key = "coef" if kind == "crop" else "ev_coef"
    p, _ = resolve(kind, cfg.get(key) or "")
    if not p:
        return ""
    return p
