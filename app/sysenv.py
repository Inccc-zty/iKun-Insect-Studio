"""跨平台的小差异都收在这里：开文件夹、选设备、临时目录。

Windows 上是 `os.startfile`，macOS 上是 `open`；设备是 cuda → mps → cpu。
"""
from __future__ import annotations

import os
import subprocess
import sys


def is_mac() -> bool:
    return sys.platform == "darwin"


def is_win() -> bool:
    return os.name == "nt"


def open_path(path: str) -> None:
    """在系统文件管理器里打开一个文件或目录。"""
    path = os.path.abspath(path)
    if is_mac():
        subprocess.Popen(["open", path])
    elif is_win():
        os.startfile(path)                     # noqa: S606
    else:
        subprocess.Popen(["xdg-open", path])


def device_choices() -> list[str]:
    """按优先级列出可用的推理设备。macOS 上没有 CUDA，用 MPS（Apple 芯片）。"""
    out = []
    try:
        import torch
        if torch.cuda.is_available():
            out.append("cuda")
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            out.append("mps")
    except Exception:                          # noqa: BLE001
        pass
    out.append("cpu")
    return out


def pick_device(prefer: str = "") -> str:
    """尊重用户的显式选择；选不到就退到下一个可用设备。"""
    avail = device_choices()
    prefer = (prefer or "").strip().lower()
    if prefer and prefer != "auto":
        if prefer in avail:
            return prefer
        # 用户选了 cuda 但没有，就在 macOS 上退到 mps，其它退到 cpu
        return avail[0] if avail[0] != "cpu" else "cpu"
    return avail[0]
