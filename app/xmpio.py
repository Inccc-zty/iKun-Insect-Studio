"""XMP 的写与读 + 来源账本（哪张是软件做的、哪张是手做的）。

写：直接复用 skill 的 xmp_write（只写四个模块，带黑名单自检）。
读：训练时要拿真值——裁切四边界、Exposure2012、Temperature/Tint。

来源账本（2026-11-17 用户要求）
------------------------------
每写完一张，就在**照片所在目录**追加一行 `_ikun_xmp_log.jsonl`：

    {"t": 1763..., "img": "Z04_6393.NEF", "xmp": "Z04_6393.xmp",
     "origin": "auto", "sha": "…", "ev": 0.35, "sharp": 65, "crop": [...]}

判定一张 XMP 现在归谁：
    有记录 + 文件哈希没变      → auto   （软件写的，没被动过，可以覆盖）
    有记录 + 哈希变了          → manual （写过之后被改过，按手做保护）
    没有记录                   → manual （来路不明，宁可不碰）

这样「你在 LR 里改过那张」和「软件刚写的那张」就分得开，
不会被下一次跑批悄悄盖掉。账本是追加写的（一行一张，O(1)），
不重写整个文件，也不会因为中途崩溃而丢历史。
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time

# skill 的 scripts 目录
from .paths import skill_dir


SKILL = skill_dir()
sys.path.insert(0, os.path.join(SKILL, "scripts"))

import xmp_write  # noqa: E402

SIDE_EXT = ".xmp"
LOG_NAME = "_ikun_xmp_log.jsonl"
CREATOR = "iKun Insect Studio 4.0"

# 目录 → {文件名: 最后一条记录}；按 (mtime, size) 失效
_LOG_CACHE = {}

POLICIES = ("protect", "skip_all", "force")


def sidecar_path(image_path: str) -> str:
    """与图同名的 .xmp（不看图是否存在）。"""
    return os.path.splitext(image_path)[0] + SIDE_EXT


_NUM = r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?'


def _get(text: str, key: str):
    import re
    m = re.search(rf'crs:{key}\s*=\s*"([^"]*)"', text)
    return m.group(1) if m else None


def read_truth(image_path: str):
    """读同名 XMP 的真值。没有 sidecar 返回 None。"""
    p = sidecar_path(image_path)
    if not os.path.exists(p):
        return None
    try:
        t = open(p, encoding="utf-8", errors="replace").read()
    except OSError:
        return None

    d = {}
    for k in ("CropLeft", "CropTop", "CropRight", "CropBottom",
              "Exposure2012", "Temperature", "Tint", "CropAngle"):
        v = _get(t, k)
        if v is not None:
            try:
                d[k] = float(v)
            except ValueError:
                pass
    d["HasCrop"] = (_get(t, "HasCrop") or "").lower() == "true"
    d["WhiteBalance"] = _get(t, "WhiteBalance")
    if not d["HasCrop"]:
        for k in ("CropLeft", "CropTop", "CropRight", "CropBottom"):
            d.pop(k, None)
    return d


# ---------------------------------------------------------------- 来源账本
def log_path(image_path: str) -> str:
    return os.path.join(os.path.dirname(image_path), LOG_NAME)


def sha1_file(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _log_index(lp: str):
    """读一个目录的账本，返回 {小写文件名: 最后一条}。带 mtime 缓存。"""
    try:
        st = os.stat(lp)
        key = (st.st_mtime_ns, st.st_size)
    except OSError:
        return {}
    hit = _LOG_CACHE.get(lp)
    if hit and hit[0] == key:
        return hit[1]
    idx = {}
    try:
        with open(lp, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    r = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                k = str(r.get("img") or "").lower()
                if k:
                    idx[k] = r
    except OSError:
        return {}
    _LOG_CACHE[lp] = (key, idx)
    return idx


def origin_of(image_path: str) -> str:
    """'none' | 'auto' | 'manual'。

    auto   上一次是我们写的，而且之后没人动过
    manual 上一次是手写的（你自己拖的框），或者写完之后被改过，或者压根没记录
    """
    xp = sidecar_path(image_path)
    if not os.path.exists(xp):
        return "none"
    rec = _log_index(log_path(image_path)).get(os.path.basename(image_path).lower())
    if rec is None:
        return "manual"          # 没有账本记录：来路不明，按手做
    try:
        same = sha1_file(xp) == rec.get("sha")
    except OSError:
        return "manual"
    if not same:
        return "manual"          # 写过之后被改过
    return "auto" if rec.get("origin") == "auto" else "manual"


def decide(image_path: str, policy: str = "protect"):
    """跑批前决定这张要不要写。返回 dict(skip, origin, reason)。"""
    policy = policy if policy in POLICIES else "protect"
    xp = sidecar_path(image_path)
    if not os.path.exists(xp):
        return {"skip": False, "origin": "none", "reason": "new"}
    o = origin_of(image_path)
    if policy == "force":
        return {"skip": False, "origin": o, "reason": "force"}
    if policy == "skip_all":
        return {"skip": True, "origin": o, "reason": "exists"}
    if o == "auto":
        return {"skip": False, "origin": o, "reason": "auto"}
    return {"skip": True, "origin": o, "reason": "manual"}


def _append_log(image_path: str, origin: str, extra=None):
    lp = log_path(image_path)
    rec = {
        "t": round(time.time(), 1),
        "img": os.path.basename(image_path),
        "xmp": os.path.basename(sidecar_path(image_path)),
        "origin": origin,
        "app": CREATOR,
    }
    if extra:
        rec.update({k: v for k, v in extra.items() if v is not None})
    try:
        with open(lp, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        _LOG_CACHE.pop(lp, None)          # 下次重新读
    except OSError:
        pass                              # 只读盘也不影响写 XMP


# ---------------------------------------------------------------- 写
def write_sidecar(image_path: str, crop=None, ev=None, T=None, tint=None,
                  sharpness=None, profile="Camera Standard", backup=True,
                  origin="auto", policy="protect"):
    """写 sidecar；已存在则先复制到 _xmp_backup/。

    返回 dict:
        path    写到的文件
        written 是否真的写了
        backed  是否备份过
        origin  写之前这张的归属（none/auto/manual）
        reason  new | auto | manual | force | exists
    """
    dst = sidecar_path(image_path)
    before = "none"
    if os.path.exists(dst):
        before = origin_of(image_path)
        if policy == "skip_all":
            return {"path": dst, "written": False, "backed": False,
                    "origin": before, "reason": "exists"}
        if policy != "force" and before != "auto":
            return {"path": dst, "written": False, "backed": False,
                    "origin": before, "reason": "manual"}

    name = os.path.basename(image_path)
    xml = xmp_write.build(name, crop, ev, T, tint, sharpness, profile=profile,
                          creator=CREATOR)
    xmp_write.assert_minimal(xml)

    backed = False
    if backup and os.path.exists(dst):
        bak = os.path.join(os.path.dirname(image_path), "_xmp_backup")
        os.makedirs(bak, exist_ok=True)
        import shutil
        shutil.copy2(dst, os.path.join(bak, os.path.basename(dst)))
        backed = True
    tmp = dst + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(xml)
    os.replace(tmp, dst)                 # 原子替换，断电不会留半个文件
    try:
        sha = sha1_file(dst)
    except OSError:
        sha = ""
    _append_log(image_path, origin, {
        "sha": sha,
        "ev": None if ev is None else round(float(ev), 3),
        "sharp": sharpness,
        "crop": None if crop is None else [round(float(v), 5) for v in crop],
    })
    return {"path": dst, "written": True, "backed": backed,
            "origin": before,
            "reason": "new" if before == "none"
                      else ("force" if policy == "force" else "auto")}


FORBIDDEN = xmp_write.FORBIDDEN
