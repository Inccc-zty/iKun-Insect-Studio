# -*- coding: utf-8 -*-
"""Insect Studio 启动器。

    python run.py            # 正常启动
    python run.py --no-api   # 不启本地 API
    python run.py --port 8765

窗口关闭即退出；本地 API 随进程结束。
"""
from __future__ import annotations

import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if not getattr(sys, "frozen", False):
    sys.path.insert(0, HERE)

def _setup_hf_home():
    """模型缓存位置，按平台定。

    1. 环境变量 HF_HOME / INSECT_HF 优先（CI、排障用）
    2. 包里带了 hf/（打包时预下载）就用包内的，离线可用
    3. 否则放 data/hf，第一次运行联网下载一次
    """
    if os.environ.get("HF_HOME"):
        return os.environ["HF_HOME"]
    root = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.abspath(__file__)))
    for cand in (os.path.join(root, "_internal", "hf"), os.path.join(root, "hf")):
        if os.path.isdir(cand):
            os.environ["HF_HOME"] = cand
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            return cand
    d = os.path.join(root, "data", "hf")
    os.makedirs(d, exist_ok=True)
    os.environ["HF_HOME"] = d
    return d


HF_HOME = _setup_hf_home()


def _adapt_vram(cfg):
    """启动时看一眼显存：桌面占用高就临时降到 512，不写回配置文件。"""
    if cfg.get("device") != "cuda" or int(cfg.get("seg_size")) != 768:
        return
    try:
        import torch
        if not torch.cuda.is_available():
            return
        free, _total = torch.cuda.mem_get_info()
        gb = free / (1024 ** 3)
        if gb < 2.4:
            cfg._d["seg_size"] = 512
            print(f"[显存] 可用 {gb:.2f} GB，不足以跑 768，本次自动改用 512"
                  f"（界面里可手动改回）", flush=True)
    except Exception:  # noqa: BLE001
        pass



def _selftest() -> int:
    """无界面自检：只验证「模型能加载 + 前向能跑 + 系数能解框」。
    CI（macOS runner 没有 GPU）跑这个，代替人工点一遍。"""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import numpy as np
    from PIL import Image

    sys.path.insert(0, os.path.join(HERE, "skill", "scripts"))
    from app.config import Config
    from app import crop_rel                  # noqa: F401  只验证可导入
    import crop_v3
    import mask_head

    dev = "cpu"
    print(f"[selftest] python={sys.version.split()[0]} platform={sys.platform} HF_HOME={HF_HOME}")
    cfg = Config()
    cfg._d.update(device="cpu", seg_size=384)
    print("[selftest] config ok")

    img = Image.fromarray(
        (np.random.default_rng(0).random((480, 640, 3)) * 255).astype("uint8"))
    res = mask_head.analyze(img, dev=dev, size=384, want_head=True)
    print(f"[selftest] mask ok={res.get('ok')} size={res.get('size')} "
          f"reason={res.get('reason', '')}")
    if not res.get("ok"):
        # 纯噪声图上掩膜为空是正常的；把「能跑完前向」当作通过，用合成框继续验系数
        if res.get("reason") != "mask_empty":
            return 2
        print("[selftest] 噪声图掩膜为空，属预期；改用合成框验证系数")
        res = {"core": (0.40, 0.40, 0.60, 0.55), "full": (0.36, 0.37, 0.64, 0.60), "head": (0.50, 0.42)}

    J = crop_v3.load()
    cr = crop_v3.compute_crop(res["core"], res["full"], res.get("head"),
                              multi=False, J=J)
    print(f"[selftest] crop={tuple(round(v, 4) for v in cr['crop'])} w={cr['w']:.4f}")
    print("[selftest] OK")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-api", action="store_true")
    ap.add_argument("--selftest", action="store_true", help="无界面自检后退出")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--reset-all", action="store_true",
                    help="连 models/ 一起清空（默认重置会保留你训练/导入的模型）")
    ap.add_argument("--reset", action="store_true",
                    help="先把 data/ 清空到出厂状态再启动（测试用）")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()

    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QFont
    except ImportError:
        print("缺少 PySide6。安装：")
        print(r'  O:\ai修图\.venv_gpu\Scripts\python.exe -m pip install pyside6 '
              r'-i https://pypi.tuna.tsinghua.edu.cn/simple')
        return 2

    from app.paths import skill_dir
    if not os.path.isdir(os.path.join(skill_dir(), "scripts")):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "缺少算法包",
                             f"找不到算法目录：\n{skill_dir()}\n\n"
                             "分发时必须把整个 InsectStudio 文件夹一起拷贝，不能只拷 exe。")
        return 3

    from app.config import Config
    from app.engine import Engine
    from app.trainer import Trainer
    from app.reset import wipe

    if a.reset or a.reset_all:
        inv = wipe(keep_models=not a.reset_all)
        print(f"[reset] 清空 {len(inv['items'])} 项 / {inv['files']} 个文件 / "
              f"{inv['bytes'] / 1e6:.1f} MB，已恢复出厂状态", flush=True)

    cfg = Config()
    _adapt_vram(cfg)
    eng = Engine(cfg)
    tr = Trainer(cfg, eng)
    app_ctx = {"cfg": cfg, "engine": eng, "trainer": tr}

    port = None
    if not a.no_api:
        try:
            from app.server import Server
            srv = Server(app_ctx, port=a.port)
            port = srv.start_bg()
            print(f"[API] http://127.0.0.1:{port}/api/ai", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[API] 启动失败（不影响主程序）：{e}", flush=True)

    qapp = QApplication(sys.argv)
    qapp.setApplicationName("iKun Insect Studio")
    try:
        from PySide6.QtGui import QIcon
        from app.paths import asset_path
        ic = asset_path("app.ico")
        if os.path.exists(ic):
            qapp.setWindowIcon(QIcon(ic))
    except Exception:
        pass
    qapp.setFont(QFont("Microsoft YaHei UI", 9))

    from ui.main_window import MainWindow
    w = MainWindow(app_ctx)
    if port:
        w.status.showMessage(f"本地 API 已就绪：http://127.0.0.1:{port}/api/ai", 15000)
    w.show()
    return qapp.exec()


def _log_crash(exc: BaseException):
    """打包成 exe 后没有控制台，把崩溃写到 data/crash.log，方便排查。"""
    import traceback
    try:
        base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
            else os.path.dirname(os.path.abspath(__file__))
        d = os.path.join(base, "data")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "crash.log"), "a", encoding="utf-8") as f:
            f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
            f.write(traceback.format_exc())
    except Exception:
        pass


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as e:  # noqa: BLE001
        _log_crash(e)
        raise
