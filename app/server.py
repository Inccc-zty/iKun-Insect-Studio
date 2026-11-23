"""本地 HTTP 服务：既是 UI 的后端，也是给 AI 用的接口。

绑 127.0.0.1，不对外。所有能力都是普通 JSON API：

    GET  /api/status            队列/速度/ETA/配置
    POST /api/add               {"paths": ["D:/照片/某目录", "C:/a.NEF"]}
    POST /api/start|pause|stop|clear
    POST /api/config            {"mode":"crop"|"exposure"|"both", ...}
    GET  /api/recent?n=40       最近处理结果（含叠加图名）
    GET  /api/preview/<name>    叠加图 jpg
    GET  /api/ping              心跳（决定是否生成预览）
    GET  /api/browse?path=      列目录（前端"选择文件夹"用）
    POST /api/train             {"root": "D:/训练集"}
    GET  /api/train/status
    POST /api/train/stop
    GET  /api/ai                AI 接口自描述（给模型看的清单）
"""
from __future__ import annotations

import json
import mimetypes
import os
import socket
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, "web")
DATA = os.path.join(ROOT, "data")


def _json(handler, obj, code=200):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _file(handler, path, ctype=None):
    if not os.path.isfile(path):
        handler.send_error(404)
        return
    data = open(path, "rb").read()
    handler.send_response(200)
    handler.send_header("Content-Type", ctype or mimetypes.guess_type(path)[0] or "application/octet-stream")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(data)


def make_handler(app):
    engine, cfg, trainer = app["engine"], app["cfg"], app["trainer"]

    class H(BaseHTTPRequestHandler):
        server_version = "InsectStudio/1.0"

        def log_message(self, fmt, *args):  # 静音，避免刷屏
            pass

        # ------------------------------------------------------------ GET
        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            p = urllib.parse.unquote(u.path)
            q = urllib.parse.parse_qs(u.query)

            if p in ("/", "/index.html"):
                return _file(self, os.path.join(WEB, "index.html"), "text/html; charset=utf-8")
            if p.startswith("/web/"):
                return _file(self, os.path.join(WEB, os.path.basename(p)))
            if p == "/api/status":
                return _json(self, engine.status())
            if p == "/api/ping":
                engine.ping()
                return _json(self, {"ok": True, "preview": engine.preview_allowed()})
            if p == "/api/recent":
                n = int(q.get("n", ["40"])[0])
                return _json(self, {"items": engine.recent(n)})
            if p.startswith("/api/preview/"):
                name = os.path.basename(p.split("/")[-1])
                return _file(self, os.path.join(DATA, "preview", name), "image/jpeg")
            if p == "/api/browse":
                return _json(self, _browse(q.get("path", [""])[0]))
            if p == "/api/train/status":
                return _json(self, trainer.status())
            if p == "/api/ai":
                return _json(self, _ai_manifest())
            return _json(self, {"error": "not found"}, 404)

        # ------------------------------------------------------------ POST
        def do_POST(self):
            u = urllib.parse.urlparse(self.path)
            p = u.path
            ln = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(ln) if ln else b"{}"
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except Exception:  # noqa: BLE001
                return _json(self, {"error": "bad json"}, 400)

            if p == "/api/add":
                paths = body.get("paths") or []
                n = engine.add_paths(paths)
                return _json(self, {"added": n, "total": engine.status()["total"]})
            if p == "/api/start":
                engine.start()
                return _json(self, {"ok": True, "status": engine.status()})
            if p == "/api/pause":
                engine.pause()
                return _json(self, {"ok": True})
            if p == "/api/stop":
                engine.stop()
                return _json(self, {"ok": True})
            if p == "/api/clear":
                return _json(self, {"ok": engine.clear()})
            if p == "/api/config":
                cfg.update(**{k: v for k, v in body.items() if k in cfg.as_dict()})
                return _json(self, {"ok": True, "cfg": cfg.as_dict()})
            if p == "/api/train":
                roots = body.get("roots") or body.get("root") or []
                ok, msg = trainer.start(roots, body.get("subdir", ""))
                return _json(self, {"ok": ok, "msg": msg})
            if p == "/api/train/stop":
                trainer.stop()
                return _json(self, {"ok": True})
            if p == "/api/shutdown":
                _json(self, {"ok": True})
                threading_shutdown(self.server)
                return
            return _json(self, {"error": "not found"}, 404)

    return H


def threading_shutdown(server):
    import threading
    threading.Thread(target=server.shutdown, daemon=True).start()


def _browse(path: str):
    """列目录：给前端的"选择文件夹"用。返回父目录 + 子目录 + 该目录下图片数。"""
    import string
    if not path:
        drives = [f"{c}:\\" for c in string.ascii_uppercase if os.path.exists(f"{c}:\\")]
        return {"path": "", "parent": "", "dirs": drives, "images": 0}
    path = os.path.normpath(path)
    if not os.path.isdir(path):
        return {"path": path, "parent": os.path.dirname(path), "dirs": [], "images": 0, "error": "不存在"}
    dirs = []
    try:
        for name in sorted(os.listdir(path)):
            fp = os.path.join(path, name)
            if os.path.isdir(fp):
                dirs.append(fp)
    except PermissionError:
        pass
    from . import rawio
    n = len(rawio.scan_image_dir(path, recursive=False))
    return {"path": path, "parent": os.path.dirname(path), "dirs": dirs, "images": n}


def _ai_manifest():
    return {
        "name": "ikun-insect-studio",
        "desc": "昆虫微距自动后期（裁切 105 项 / 曝光双参数 / 锐化 → XMP；白平衡不写）",
        "base": "http://127.0.0.1:8765",
        "endpoints": [
            {"method": "GET", "path": "/api/status", "desc": "队列、速度（秒/张）、ETA、配置"},
            {"method": "POST", "path": "/api/add", "body": {"paths": ["目录或文件"]},
             "desc": "加入处理队列，递归展开目录"},
            {"method": "POST", "path": "/api/config",
             "body": {"mode": "both|crop|exposure", "seg_size": 768, "device": "cuda|cpu",
                      "coef": "", "sharpen_enable": True,
                      "xmp_policy": "protect|skip_all|force",
                      "train_dirs": ["D:/训练集A", "D:/训练集B"]},
             "desc": "改设置，立即生效"},
            {"method": "POST", "path": "/api/start", "desc": "开始/继续"},
            {"method": "POST", "path": "/api/pause", "desc": "暂停"},
            {"method": "GET", "path": "/api/recent?n=40", "desc": "最近结果（含 crop / ev / sharp）"},
            {"method": "POST", "path": "/api/train", "body": {"roots": ["训练集目录1", "训练集目录2"]},
             "desc": "从「原片 + 同名 XMP」重拟合裁切 / 曝光，可给多个目录"},
            {"method": "GET", "path": "/api/train/status", "desc": "训练进度与报告"},
        ],
        "notes": [
            "处理结果直接写成与图同名的 .xmp，LR 用「从文件读取元数据」应用。",
            "预览叠加图只在页面可见时生成；调 /api/ping 维持心跳。",
            "所有路径用绝对路径，支持中文。",
            "白平衡不写进 XMP，Lightroom 沿用相机 As Shot。",
            "xmp_policy=protect（默认）：软件写的可覆盖，手做的跳过；"
            "skip_all：已有同名 .xmp 一律跳过；force：全部重写（先备份）。",
            "归属记在照片目录的 _ikun_xmp_log.jsonl（含 SHA-1），手改过的会被认出来。",
        ],
    }


class Server:
    def __init__(self, app, host="127.0.0.1", port=8765):
        self.httpd = None
        self.host, self.port = host, port
        self.app = app

    def serve_forever(self):
        H = make_handler(self.app)
        for port in range(self.port, self.port + 20):
            try:
                self.httpd = ThreadingHTTPServer((self.host, port), H)
                self.port = port
                break
            except OSError:
                continue
        if self.httpd is None:
            raise RuntimeError("端口 8765–8784 都被占用")
        self.httpd.serve_forever()

    def start_bg(self):
        import threading
        t = threading.Thread(target=self.serve_forever, daemon=True)
        t.start()
        for _ in range(50):
            try:
                with socket.create_connection((self.host, self.port), 0.2):
                    return self.port
            except OSError:
                import time
                time.sleep(0.1)
        return self.port
