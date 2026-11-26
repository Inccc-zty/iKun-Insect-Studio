"""运行期路径：开发时在工作区，打包后在 exe 旁边。

打包（PyInstaller onedir）后 `__file__` 指向 `_internal/app/…`，
但用户可写的目录应该是 exe 同级，所以统一从这里取。
"""
from __future__ import annotations

import os
import sys


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> str:
    """只读资源的根：打包后是 exe 同级（macOS 是 .app/Contents/MacOS），开发时是项目根。"""
    if is_frozen():
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def app_root() -> str:
    """可写目录：Windows 是 exe 同级（绿色版），macOS 放用户目录。

    macOS 的 .app 是只读语义的 bundle：往里写会破坏签名，升级时整包被替换，
    用户的模型和配置也会跟着丢。所以 data/ 放到 Application Support。
    """
    if is_frozen() and sys.platform == "darwin":
        d = os.path.expanduser("~/Library/Application Support/iKunInsectStudio")
        os.makedirs(d, exist_ok=True)
        return d
    return bundle_root()


def data_dir(*parts) -> str:
    d = os.path.join(app_root(), "data", *parts)
    os.makedirs(os.path.dirname(d) if parts else d, exist_ok=True)
    return d


def asset_path(name: str) -> str:
    """内置素材（logo / 图标）：打包后在 `_internal/assets/`，开发时在项目 assets/。"""
    cands = []
    if is_frozen():
        base = app_root()
        cands += [os.path.join(base, "assets", name),
                  os.path.join(getattr(sys, "_MEIPASS", ""), "assets", name),
                  os.path.join(base, "_internal", "assets", name)]
    cands.append(os.path.join(app_root(), "assets", name))
    for c in cands:
        if os.path.exists(c):
            return c
    return cands[-1]


def skill_dir() -> str:
    """算法包：打包后在 exe 同级 skill/，开发时用环境变量或工作区。"""
    if is_frozen():
        base = bundle_root()
        up = os.path.dirname(base)                      # macOS: Contents/MacOS → Contents
        for cand in (os.path.join(base, "skill"),
                     os.path.join(up, "Resources", "skill"),   # macOS .app
                     os.path.join(up, "Frameworks", "skill"),
                     os.path.join(getattr(sys, "_MEIPASS", base), "skill"),
                     os.path.join(base, "_internal", "skill")):
            if os.path.isdir(cand):
                return cand
        return os.path.join(base, "skill")
    return os.environ.get("INSECT_SKILL") or r"O:/ai修图/skill/insect-auto-post-v2"
