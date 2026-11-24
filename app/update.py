"""检查 GitHub 上的新版本（只查，不自动替换正在运行的文件）。"""
from __future__ import annotations

import json
import re
import urllib.request

from .version import REPO, VERSION


def _num(s: str):
    return tuple(int(x) for x in re.findall(r"\d+", s)[:3]) or (0,)


def is_newer(latest: str, current: str = VERSION) -> bool:
    return _num(latest) > _num(current)


def _get_json(url, timeout):
    req = urllib.request.Request(url, headers={
        "User-Agent": "iKunInsectStudio/" + VERSION,
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _from_release(timeout):
    d = _get_json(f"https://api.github.com/repos/{REPO}/releases/latest", timeout)
    latest = (d.get("tag_name") or "").lstrip("vV")
    return {"latest": latest, "notes": d.get("body") or "",
            "page": d.get("html_url") or "",
            "published": (d.get("published_at") or "")[:10],
            "assets": [{"name": a.get("name", ""), "size": a.get("size", 0),
                        "url": a.get("browser_download_url", "")}
                       for a in d.get("assets", [])]}


def _from_version_json(timeout):
    # raw.githubusercontent.com 在部分网络下不通，改走 api.github.com 的 contents 接口
    import base64
    meta = _get_json(f"https://api.github.com/repos/{REPO}/contents/version.json", timeout)
    d = json.loads(base64.b64decode(meta.get("content", "")).decode("utf-8"))
    return {"latest": str(d.get("version", "")).lstrip("vV"),
            "notes": d.get("notes") or "", "page": d.get("url") or "",
            "published": str(d.get("date", ""))[:10],
            "assets": [{"name": "下载", "size": 0, "url": d.get("url", "")}]}


def check(timeout: float = 6.0):
    """返回 {ok, latest, notes, page, assets, error}。
    依次尝试：GitHub Release → 仓库根 version.json。"""
    for fn in (_from_release, _from_version_json):
        try:
            d = fn(timeout)
        except Exception:      # noqa: BLE001
            continue
        if not d.get("latest"):
            continue
        d.update({"ok": True, "current": VERSION, "newer": is_newer(d["latest"])})
        return d
    return {"ok": False, "current": VERSION, "error": "没有找到可用的版本信息"}


def download(url: str, dst: str, on_progress=None):
    """把安装包下到指定位置，返回路径。"""
    req = urllib.request.Request(url, headers={"User-Agent": "iKunInsectStudio/" + VERSION})
    with urllib.request.urlopen(req, timeout=30) as r, open(dst, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            buf = r.read(1 << 20)
            if not buf:
                break
            f.write(buf)
            done += len(buf)
            if on_progress:
                on_progress(done, total)
    return dst
