# -*- coding: utf-8 -*-
"""打包成 Windows 可执行程序（onedir）。

    python build.py            # 完整打包
    python build.py --clean    # 先清掉 build/ dist/

产物：`dist/InsectStudio/InsectStudio.exe`，双击即用。
算法模块与权重一起进 `dist/InsectStudio/skill/`，不依赖工作区。
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HF_SRC = os.environ.get("INSECT_HF") or r"D:/反渲染的研究/.cache/hf"
HF_MODEL = "models--ZhengPeng7--BiRefNet"     # 只带这一个，别把整个缓存塞进包
SKILL_SRC = os.environ.get("INSECT_SKILL") or r"O:/ai修图/skill/insect-auto-post-v2"
STAGE = os.environ.get("INSECT_STAGE") or os.path.join(HERE, "build_assets")
DIST = os.environ.get("INSECT_DIST") or os.path.join(HERE, "dist_final")
BUILD = os.environ.get("INSECT_BUILD") or os.path.join(HERE, "build")

APP_NAME = "iKunInsectStudio"

# 这些 CUDA 库对这条推理链（卷积/线性/插值）不是必需的，已在 GPU 上逐项实测：
#   删掉后 512 输入仍能完整跑完一张并写出 XMP。
# 不能删：cudnn_engines_precompiled（卷积引擎）、cufft、cusparse、cusolver、
#         cublas/cublasLt、nvrtc（torch 导入就要）、cupti（torch_cpu 直接导入）。
# 打包后裁掉可选文件（相对 _internal）。每一项都在 GPU 512 输入下实测跑完整张。
#
# 不能删（都是 torch_cuda.dll 的静态导入，删了 import torch 直接失败）：
#   cusolver64_11 / cufft64_10 / cusparse64_11 / cublas / cublasLt / cudnn64_9
# 不能删（运行期会真的用到）：
#   cudnn_engines_precompiled（卷积引擎）/ cudnn_heuristic（引擎选择）/ nvrtc
#   scipy（运行时报 extension modules cannot be imported）
TRIM = [
    # ---- 推理用不到的 CUDA 子库
    "torch/lib/cusolverMg64_11.dll",   # 174 MB 多卡求解器
    "torch/lib/curand64_10.dll",       #  63 MB 随机数
    "torch/lib/cudnn_adv64_9.dll",     # 230 MB RNN/attention 高级算子
    # ---- Qt 里这套界面用不到的模块
    "PySide6/opengl32sw.dll",          #  20 MB 软件 OpenGL 兜底
    "PySide6/Qt6Pdf.dll",              #  4.5 MB
    "PySide6/Qt6Qml.dll",              #  5.2 MB
    "PySide6/Qt6Quick.dll",            #  6.5 MB
    "PySide6/Qt6QmlModels.dll",
    "PySide6/Qt6Network.dll",
    # 注：PySide6/translations（6.9 MB）和 sklearn（13 MB）也是多余的，
    #     但它们是目录、上千个文件，一次性删除会被沙盒的批量删除保护拦下
    #     （SAFE_DELETE_BULK_CONFIRM_REQUIRED, >50 files），所以留着。
    #     想让它们也别进包，装包时 pip uninstall scikit-learn 再打包即可。
]


def make_icon(path):
    """画一个简洁的图标：深绿圆角底 + 白色虫体剪影。"""
    from PIL import Image, ImageDraw
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = []
    for S in sizes:
        im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        r = int(S * 0.22)
        d.rounded_rectangle([0, 0, S - 1, S - 1], radius=r, fill=(23, 27, 29, 255))
        # 身体：三个椭圆
        cx, cy = S / 2, S * 0.56
        w = S * 0.30
        d.ellipse([cx - w * 0.42, cy - S * 0.10, cx + w * 0.42, cy + S * 0.16],
                  fill=(94, 192, 143, 255))
        d.ellipse([cx - w * 0.30, cy - S * 0.26, cx + w * 0.30, cy - S * 0.02],
                  fill=(94, 192, 143, 255))
        d.ellipse([cx - S * 0.10, cy - S * 0.38, cx + S * 0.10, cy - S * 0.20],
                  fill=(223, 141, 142, 255))
        # 触角
        lw = max(1, S // 24)
        d.line([cx - S * 0.04, cy - S * 0.36, cx - S * 0.18, cy - S * 0.48],
               fill=(223, 141, 142, 255), width=lw)
        d.line([cx + S * 0.04, cy - S * 0.36, cx + S * 0.18, cy - S * 0.48],
               fill=(223, 141, 142, 255), width=lw)
        imgs.append(im)
    imgs[-1].save(path, format="ICO", sizes=[(s, s) for s in sizes])
    return path


def stage_skill():
    """把 skill 的 scripts + assets 复制到 build_assets/skill。"""
    dst = os.path.join(STAGE, "skill")
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    os.makedirs(dst, exist_ok=True)
    for sub in ("scripts", "assets"):
        src = os.path.join(SKILL_SRC, sub)
        if not os.path.isdir(src):
            raise SystemExit(f"找不到 {src}")
        shutil.copytree(src, os.path.join(dst, sub))
    # 去掉体积大又用不到的自检表（保留 v3 系数与权重）
    for junk in ("selftest_crop_4184.csv", "scope_crop_1022.csv", "scope_crop_2002.csv"):
        fp = os.path.join(dst, "assets", "data", junk)
        if os.path.exists(fp):
            os.remove(fp)
    total = sum(os.path.getsize(os.path.join(dp, f))
                for dp, _dn, fn in os.walk(dst) for f in fn)
    print(f"[stage] skill → {dst}  ({total/1e6:.0f} MB)")
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", action="store_true")
    ap.add_argument("--onefile", action="store_true", help="单文件（启动慢，不建议）")
    a = ap.parse_args()

    if a.clean:
        for d in (BUILD, DIST):
            if os.path.isdir(d):
                shutil.rmtree(d)
                print(f"[clean] 删除 {d}")

    os.makedirs(STAGE, exist_ok=True)
    src_ico = os.path.join(HERE, "assets", "app.ico")
    if os.path.exists(src_ico):
        shutil.copy2(src_ico, os.path.join(STAGE, "app.ico"))
        ico = os.path.join(STAGE, "app.ico")
        print(f"[icon] 用 assets/app.ico")
    else:
        ico = make_icon(os.path.join(STAGE, "app.ico"))
        print(f"[icon] 生成默认图标 {ico}")
    stage_skill()

    hf_arg = []
    hf_dst = os.path.join(STAGE, "hf")
    src_model = os.path.join(HF_SRC, "hub", HF_MODEL)
    dst_model = os.path.join(hf_dst, "hub", HF_MODEL)
    if os.path.isdir(src_model):
        if not os.path.isdir(dst_model):
            print(f"[stage] 自带模型 → {dst_model}")
            shutil.copytree(src_model, dst_model,
                            ignore=shutil.ignore_patterns("*.lock", "*.tmp", "*.incomplete"))
        hf_arg = ["--add-data", f"{hf_dst}{os.pathsep}hf"]
        mb = sum(os.path.getsize(os.path.join(dp, f))
                 for dp, _dn, fn in os.walk(dst_model) for f in fn) / 1024 ** 2
        print(f"[stage] 模型 {mb:.0f} MB 已入包")
    else:
        print("[stage] 没找到 BiRefNet 缓存，包内不带模型（用户首次运行需联网下载 848 MB）")

    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--name", APP_NAME,
        "--windowed",                       # 无控制台
        "--onedir" if not a.onefile else "--onefile",
        "--icon", ico,
        "--add-data", f"{os.path.join(STAGE, 'skill')}{os.pathsep}skill",
        "--collect-all", "kornia",
        "--hidden-import", "einops",
        "--hidden-import", "transformers",
        "--hidden-import", "transformers.models.auto",
        "--hidden-import", "transformers.dynamic_module_utils",
        "--hidden-import", "rawpy",
        "--hidden-import", "torchvision",
        "--hidden-import", "PIL._tkinter_finder",
        "--hidden-import", "PySide6.QtWidgets",
        "--hidden-import", "PySide6.QtGui",
        "--hidden-import", "PySide6.QtCore",
        "--collect-submodules", "rawpy",
        "--add-data", f"{os.path.join(HERE, 'assets')}{os.pathsep}assets",
        *hf_arg,
        "--exclude-module", "matplotlib",
        "--exclude-module", "tkinter",
        "--exclude-module", "tkinter",
        "--exclude-module", "pandas",
        "--exclude-module", "IPython",
        "--exclude-module", "notebook",
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.QtQuick",
        "--exclude-module", "PySide6.Qt3DCore",
        "--distpath", DIST,
        "--workpath", BUILD,
        "--specpath", BUILD,
        os.path.join(HERE, "run.py"),
    ]
    print("[build] 开始，torch 很大，通常 8–20 分钟\n")
    r = subprocess.run(args, cwd=HERE)
    if r.returncode != 0:
        raise SystemExit(f"打包失败，退出码 {r.returncode}")

    exe = os.path.join(DIST, APP_NAME, f"{APP_NAME}.exe")
    if not os.path.exists(exe):
        raise SystemExit(f"没找到 {exe}")

    # 运行期状态不能进发布包：否则用户「整包解压覆盖」时，他们的
    # config.json、训练好的模型（data/models/crop/*.json）会被一起盖掉。
    runtime = os.path.join(os.path.dirname(exe), "data")
    if os.path.isdir(runtime):
        shutil.rmtree(runtime, ignore_errors=True)
        print(f"[clean] 已移除运行期 data/：{runtime}")

    # 使用说明一起放进产物，换机器/发给别人都不用再找
    doc = os.path.join(HERE, "使用说明.md")
    if os.path.exists(doc):
        shutil.copy2(doc, os.path.join(os.path.dirname(exe), "使用说明.md"))
        print(f"[doc] 使用说明.md → {os.path.dirname(exe)}")

    # 裁掉可选 CUDA 库，能省约 0.47 GB
    internal = os.path.join(os.path.dirname(exe), "_internal")
    saved, gone = 0, []
    for rel in TRIM:
        fp = os.path.join(internal, rel.replace("/", os.sep))
        if not os.path.exists(fp):
            continue
        if os.path.isdir(fp):
            n = sum(os.path.getsize(os.path.join(dp, f))
                    for dp, _dn, fn in os.walk(fp) for f in fn)
            shutil.rmtree(fp, ignore_errors=True)
        else:
            n = os.path.getsize(fp)
            os.remove(fp)
        saved += n
        gone.append(rel)
    if gone:
        print(f"[trim] 删除 {len(gone)} 项无用文件，省 {saved/1e6:.0f} MB：{', '.join(gone)}")

    size = sum(os.path.getsize(os.path.join(dp, f))
               for dp, _dn, fn in os.walk(os.path.dirname(exe)) for f in fn)
    print(f"\n[done] {exe}")
    print(f"       整个文件夹 {size/1e9:.2f} GB —— 分发时要整个目录一起给")
    print(f"       双击 exe 即可运行；模型权重在 skill/assets/weights 里")


if __name__ == "__main__":
    main()
