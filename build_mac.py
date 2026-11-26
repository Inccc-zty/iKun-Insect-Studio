# -*- coding: utf-8 -*-
"""在 macOS 上打包成 .app（onedir）。

    python build_mac.py                 # 完整打包 + 出 zip
    python build_mac.py --no-hf         # 不预下载模型（用户首次运行联网下载）
    python build_mac.py --no-zip        # 只出 .app

产物：`dist/iKunInsectStudio.app`，以及同名的 `iKunInsectStudio_macOS_arm64.zip`
（用 ditto 压，保留符号链接与签名扩展属性）。

与 Windows 的 build.py 是两套：Windows 裁 torch 的 CUDA 子库、改 exe 图标；
macOS 没有 CUDA，权重跟着 .app 走，压缩必须用 ditto（zip -r 会破坏 bundle）。
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP_NAME = "iKunInsectStudio"
STAGE = os.environ.get("INSECT_STAGE") or os.path.join(HERE, "build_mac_assets")
DIST = os.environ.get("INSECT_DIST") or os.path.join(HERE, "dist_mac")
BUILD = os.environ.get("INSECT_BUILD") or os.path.join(HERE, "build_mac")


def _skill_src() -> str:
    for c in (os.environ.get("INSECT_SKILL"),
              os.path.join(HERE, "skill"),
              os.path.abspath(os.path.join(HERE, "..", "skill", "insect-auto-post-v2"))):
        if c and os.path.isdir(os.path.join(c, "scripts")):
            return c
    raise SystemExit("找不到算法包（skill/scripts）")


def stage_skill(dst: str) -> None:
    src = _skill_src()
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(
        "__pycache__", "*.pyc", ".git", "build_*", "dist_*"))
    print(f"[stage] skill → {dst}")


def stage_hf(dst: str) -> bool:
    """把 BiRefNet 预下载进包内，用户首次运行就不用联网。"""
    os.makedirs(dst, exist_ok=True)
    os.environ["HF_HOME"] = dst
    os.environ.pop("HF_HUB_OFFLINE", None)
    try:
        from huggingface_hub import snapshot_download
        p = snapshot_download("ZhengPeng7/BiRefNet",
                              allow_patterns=["*.json", "*.py", "*.txt", "*.safetensors", "*.bin"])
        print(f"[stage] hf → {p}")
        return True
    except Exception as e:                      # noqa: BLE001
        print(f"[stage] 模型预下载失败（{type(e).__name__}: {e}），改成首次运行联网下载")
        return False


def build(stage: str, hf_dir: str) -> str:
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
            "--windowed", "--name", APP_NAME,
            "--osx-bundle-identifier", "com.ikun.insectstudio",
            "--distpath", DIST, "--workpath", BUILD, "--specpath", BUILD,
            "--add-data", f"{os.path.join(stage, 'skill')}:skill",
            # torchvision 的 C++ 扩展（nms 等）不会被默认 hook 收全，必须显式抓
            "--collect-all", "torchvision",
            "--collect-binaries", "torch",
            "--collect-submodules", "torch",
            "--collect-data", "torch",
            "--hidden-import", "torchvision.ops",
            "--hidden-import", "kornia",
            "--collect-all", "kornia",
            "--hidden-import", "timm",
            "--hidden-import", "einops",
            "--hidden-import", "transformers",
            "--hidden-import", "rawpy",
            "--collect-submodules", "rawpy",
            "--exclude-module", "matplotlib",
            "--exclude-module", "tkinter",
            "--exclude-module", "pandas"]
    if os.path.isdir(hf_dir) and os.listdir(hf_dir):
        args += ["--add-data", f"{hf_dir}:hf"]
    args.append(os.path.join(HERE, "run.py"))
    print("[build]", " ".join(args))
    r = subprocess.run(args)
    if r.returncode != 0:
        raise SystemExit(f"PyInstaller 失败，返回码 {r.returncode}")
    app = os.path.join(DIST, APP_NAME + ".app")
    if not os.path.isdir(app):
        raise SystemExit("没有生成 .app")
    return app


def zip_app(app: str) -> str:
    out = os.path.join(os.path.dirname(app), f"{APP_NAME}_macOS_arm64.zip")
    if os.path.exists(out):
        os.remove(out)
    subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", app, out], check=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-hf", action="store_true")
    ap.add_argument("--no-zip", action="store_true")
    a = ap.parse_args()

    if sys.platform != "darwin":
        raise SystemExit("这个脚本只能在 macOS 上跑")

    os.makedirs(STAGE, exist_ok=True)
    skill_dir = os.path.join(STAGE, "skill")
    stage_skill(skill_dir)
    hf_dir = os.path.join(STAGE, "hf")
    if not a.no_hf:
        stage_hf(hf_dir)

    app = build(STAGE, hf_dir)
    size = sum(os.path.getsize(os.path.join(dp, f))
               for dp, _dn, fn in os.walk(app) for f in fn)
    print(f"[done] {app}  {size / 1024 ** 3:.2f} GB")

    if not a.no_zip:
        z = zip_app(app)
        print(f"[done] {z}  {os.path.getsize(z) / 1024 ** 3:.2f} GB")


if __name__ == "__main__":
    main()
