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

if not getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 模型缓存（与 skill 一致）
os.environ.setdefault("HF_HOME", "D:/反渲染的研究/.cache/hf")
os.environ.setdefault("HF_HUB_OFFLINE", "1")


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-api", action="store_true")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--reset-all", action="store_true",
                    help="连 models/ 一起清空（默认重置会保留你训练/导入的模型）")
    ap.add_argument("--reset", action="store_true",
                    help="先把 data/ 清空到出厂状态再启动（测试用）")
    a = ap.parse_args()

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
