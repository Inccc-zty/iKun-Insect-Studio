"""处理引擎：队列 + 单 worker + 结果缓存。

三条原则：
1. **掩膜只算一次**。裁切与曝光共用同一次 `mask_head.analyze()`。
2. **预览不额外算力**——叠加图用这次处理的掩膜画，不单独跑模型。
3. **逐步出图**：掩膜好了先画掩膜+框，头点好了加头点，裁切算完加裁切框。
   下一张还没出第一帧时，界面继续显示上一张的最后一帧，不闪黑、不跳回旧图。

白平衡（2026-11-16 用户决定）：不再写入 XMP。代码保留在 `wb_sharpen.py` 里备用，
Lightroom 会用相机 As Shot 的白平衡。
"""
from __future__ import annotations

import collections
import hashlib
import json
import os
import shutil
import sys
import threading
import time
import traceback

import cv2
import numpy as np
from PIL import Image

from .paths import app_root, skill_dir

ROOT = app_root()
SKILL = skill_dir()
sys.path.insert(0, os.path.join(SKILL, "scripts"))

import crop_v3          # noqa: E402
import exposure_model   # noqa: E402
import head_fix         # noqa: E402
import wb_sharpen       # noqa: E402
import mask_head        # noqa: E402
import xmp_write        # noqa: E402

from . import models, rawio, xmpio  # noqa: E402

PREVIEW_DIR = os.path.join(ROOT, "data", "preview")
# 每张照片的定稿叠加图按内容命名存一份，给「结果拼版」和右下角缩略图用
CACHE_DIR = os.path.join(PREVIEW_DIR, "cache")
MASK_DIR = os.path.join(PREVIEW_DIR, "masks")   # 768² PNG，约 15 KB/张
# 整条分析结果（掩膜 + 三个框 + 头点）的缓存：同一张图重跑时省掉 0.5 s 分割
ANALYSIS_DIR = os.path.join(ROOT, "data", "analysis_cache")
os.makedirs(ANALYSIS_DIR, exist_ok=True)
# 头部修正历史放在程序目录，跟着软件走，不受 skill 升级影响
os.environ.setdefault("INSECT_HEAD_FIX",
                      os.path.join(ROOT, "data", "head_fix.jsonl"))
# 用户在 <程序目录>/data/sharpen_table.csv 里改的分档优先；
# 首次运行自动把 skill 里的默认表复制过来，这样用户有个文件可改
_sh_user = os.path.join(ROOT, "data", "sharpen_table.csv")
if not os.path.exists(_sh_user):
    try:
        os.makedirs(os.path.dirname(_sh_user), exist_ok=True)
        shutil.copy2(os.path.join(SKILL, "assets", "data", "sharpen_table.csv"), _sh_user)
    except Exception:      # noqa: BLE001  拷不过去就退回 skill 默认，不阻断启动
        pass
if os.path.exists(_sh_user):
    os.environ.setdefault("INSECT_SHARPEN_TABLE", _sh_user)
os.makedirs(PREVIEW_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(MASK_DIR, exist_ok=True)

# 斜线底纹只跟画布尺寸有关，缓存起来，每张图不用重画
_HATCH = {}


def _hatch(h, w):
    key = (h, w)
    a = _HATCH.get(key)
    if a is None:
        a = np.zeros((h, w, 3), np.uint8)
        G = (104, 212, 128)                      # BGR：翠绿（红多一丢丢、蓝少一点）
        for o in range(-h, w + h, 32):           # 从左下到右上
            cv2.line(a, (o, h - 1), (o + h, 0), G, 1, cv2.LINE_AA)
        _HATCH[key] = a
        if len(_HATCH) > 4:
            _HATCH.pop(next(iter(_HATCH)))
    return a


class PreviewKit:
    """一张图的预览底图：缩放 + 掩膜红色叠加只做一次，后续每帧只画框。"""

    def __init__(self, prev, mask, max_side: int = 1000, ev=None):
        w, h = prev.size
        if max(w, h) > max_side:
            k = max_side / max(w, h)
            # 大幅缩图用 BOX（面积平均）：比 LANCZOS 快 2–3 倍，预览看不出差别
            prev = prev.resize((max(int(w * k), 1), max(int(h * k), 1)),
                               Image.BOX)
        self.bgr = cv2.cvtColor(np.asarray(prev), cv2.COLOR_RGB2BGR)
        self.H, self.W = self.bgr.shape[:2]
        self._lut = {}
        if ev is not None and abs(float(ev)) >= 0.05:
            # 先曝光再叠掩膜，红色标记就不会被一起提亮
            self.bgr = cv2.LUT(self.bgr, self._ev_lut(float(ev)))

        m = cv2.resize(np.asarray(mask), (self.W, self.H),
                       interpolation=cv2.INTER_NEAREST)
        sel = m >= 128
        if sel.any():
            ov = self.bgr.copy()
            ov[sel] = (40, 46, 240)                  # BGR：正红
            self.bgr = cv2.addWeighted(ov, 0.35, self.bgr, 0.65, 0)
            cnts, _ = cv2.findContours(sel.astype(np.uint8), cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(self.bgr, cnts, -1, (30, 30, 250), 1, cv2.LINE_AA)

    # ---- 曝光预览：线性空间乘 2^EV，再回 sRGB（用 256 项 LUT，几毫秒）
    @staticmethod
    def _ev_lut(ev: float):
        x = np.arange(256, dtype=np.float32) / 255.0
        lin = np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)
        lin = np.clip(lin * float(2.0 ** ev), 0.0, 1.0)
        srgb = np.where(lin <= 0.0031308, lin * 12.92,
                        1.055 * np.power(lin, 1.0 / 2.4) - 0.055)
        return np.clip(srgb * 255.0 + 0.5, 0, 255).astype(np.uint8)

    def _exposed(self, ev: float):
        key = round(float(ev), 2)
        lut = self._lut.get(key)
        if lut is None:
            lut = self._ev_lut(key)
            self._lut[key] = lut
        return cv2.LUT(self.bgr, lut)

    def _compose(self, ev=None, split=False):
        """这一帧的底图：给了 ev 就整幅按曝光调整，否则原图。

        以前是左原图/右调整后的分屏，用户明确要求「要么全开要么全关」，所以整幅切。
        """
        if ev is None or abs(float(ev)) < 0.05:
            return self.bgr.copy()
        return self._exposed(ev)

    def _tag(self, img, text, x, y, color):
        fs, th = 0.5, 1
        (tw, tht), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, fs, th)
        y = max(y + tht + 4, tht + 6)
        x = min(max(x, 4), self.W - tw - 8)
        cv2.rectangle(img, (x - 4, y - tht - 4), (x + tw + 4, y + base),
                      (18, 18, 22), -1)
        cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, fs,
                    color, th, cv2.LINE_AA)

    def _box(self, img, b, color, th=2, label="", where="tl"):
        if not b:
            return
        l, t, r, bo = [int(v * s) for v, s in
                       zip(b, (self.W, self.H, self.W, self.H))]
        cv2.rectangle(img, (l, t), (r, bo), (245, 245, 245), th + 2, cv2.LINE_AA)
        cv2.rectangle(img, (l, t), (r, bo), color, th, cv2.LINE_AA)
        if label:
            if where == "br":
                self._tag(img, label, r - 52, bo - 10, color)
            else:
                self._tag(img, label, l + 8, t + 8, color)

    def render(self, core, full, head, crop=None, ev=None, split=True):
        img = self._compose(ev, split)
        if crop:
            l, t, r, bo = [int(v * s) for v, s in
                           zip(crop, (self.W, self.H, self.W, self.H))]
            l, t = max(l, 0), max(t, 0)
            r, bo = min(r, self.W), min(bo, self.H)
            outside = np.ones((self.H, self.W), bool)
            outside[t:bo, l:r] = False
            if outside.any():
                ov = img.copy()
                ov[outside] = (104, 212, 128)
                img = cv2.addWeighted(ov, 0.16, img, 0.84, 0)
                blend = cv2.addWeighted(img, 1.0, _hatch(self.H, self.W), 0.38, 0)
                img[outside] = blend[outside]

        # 由外到内：裁切（绿、粗）→ 整体（橙）→ 身体（蓝）
        self._box(img, full, (60, 160, 255), 2, "full", "br")
        self._box(img, core, (255, 150, 50), 2, "core")
        self._box(img, crop, (62, 220, 80), 5, "crop")

        if head:
            hx, hy = int(head[0] * self.W), int(head[1] * self.H)
            # 2026-11-17 用户要求：红圈比原来小 30%（白 10/红 8/点 3 → 7/5/2）
            cv2.circle(img, (hx, hy), 7, (250, 250, 250), 3, cv2.LINE_AA)
            cv2.circle(img, (hx, hy), 5, (40, 40, 235), 2, cv2.LINE_AA)
            cv2.circle(img, (hx, hy), 2, (40, 40, 235), -1, cv2.LINE_AA)
        return img


class Task:
    __slots__ = ("path", "state", "err", "t0", "t1", "result",
                 "meta", "meta_done", "xmp_exists")

    def __init__(self, path):
        self.path = path
        self.state = "queued"      # queued | running | done | failed | skipped
        self.err = ""
        self.t0 = self.t1 = 0.0
        self.result = None
        self.meta = ""             # "f/8 · 1/250 · ISO 400"
        self.meta_done = False
        self.xmp_exists = False


class Engine:
    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.RLock()
        self.tasks = []
        self.running = False
        self.paused = False
        self.thread = None
        self.last_ping = 0.0
        self.started_at = 0.0
        self.durations = []          # 最近 30 张的耗时
        self.results = []            # 最近完成的，给前端列表用
        self.model_dev = None
        self._models_ready = False
        self._warm_lock = threading.Lock()
        self.warm = {"state": "idle", "dt": 0.0, "err": ""}   # idle/loading/ready/failed
        self.ui_visible = True       # 兼容旧接口；是否生成预览以心跳为准
        self.meta_version = 0        # 队列信息（光圈/快门/ISO）扫描进度
        self._meta_thread = None
        self.live = {"path": None, "name": None, "stage": None, "t": 0.0}
        self.preview_seconds = 0.0   # 画叠加图累计耗时
        self.preview_images = 0      # 画过预览的图片数
        self._kits = collections.OrderedDict()   # 最近 3 张的预览底图

    # ---------------------------------------------------------------- 队列
    def add_paths(self, paths):
        """传入文件或目录；目录按 recursive 展开。返回新加的张数。"""
        new = []
        for p in paths:
            p = os.path.normpath(p)
            if os.path.isdir(p):
                new += rawio.scan_image_dir(p, self.cfg.get("recursive"))
            elif os.path.isfile(p) and rawio.is_image(p):
                new.append(p)
        # 同一 stem 的 NEF 与 JPG 会共用一个 .xmp，必须只留一个（RAW 优先）
        picked = {}
        for p in new:
            key = (os.path.dirname(p), os.path.splitext(os.path.basename(p))[0].lower())
            cur = picked.get(key)
            if cur is None or (not rawio.is_raw(cur) and rawio.is_raw(p)):
                picked[key] = p
        with self.lock:
            have = {t.path for t in self.tasks}
            added = 0
            for p in picked.values():
                if p in have:
                    continue
                self.tasks.append(Task(p))
                added += 1
        if added:
            self._start_meta_scan()
        return added

    def _start_meta_scan(self):
        """后台读 EXIF（光圈/快门/ISO），不阻塞界面、不影响处理速度。"""
        t = self._meta_thread
        if t is not None and t.is_alive():
            return
        self._meta_thread = threading.Thread(target=self._meta_loop, daemon=True)
        self._meta_thread.start()

    def _meta_loop(self):
        while True:
            with self.lock:
                task = next((t for t in self.tasks if not t.meta_done), None)
            if task is None:
                return
            try:
                ex = rawio.read_exif(task.path)
                task.meta = rawio.meta_text(ex)
            except Exception:  # noqa: BLE001
                task.meta = ""
            task.xmp_exists = os.path.exists(xmpio.sidecar_path(task.path))
            task.meta_done = True
            self.meta_version += 1

    def clear(self):
        with self.lock:
            if self.running:
                return False
            self.tasks.clear()
            self.results.clear()
            self.durations.clear()
            self._kits.clear()
            # 清空队列就换了一批，上一批的定稿图没用了
            try:
                for f in os.listdir(CACHE_DIR):
                    os.remove(os.path.join(CACHE_DIR, f))
            except OSError:
                pass
            self.live = {"path": None, "name": None, "stage": None, "t": 0.0}
            return True

    def remove_failed(self):
        with self.lock:
            n = len(self.tasks)
            self.tasks = [t for t in self.tasks
                          if t.state not in ("failed", "skipped")]
            return n - self.tasks

    # ---------------------------------------------------------------- 运行
    def policy(self) -> str:
        p = self.cfg.get("xmp_policy") or ""
        if p in xmpio.POLICIES:
            return p
        return "skip_all" if self.cfg.get("skip_if_xmp") else "protect"

    def start(self):
        with self.lock:
            if self.running:
                self.paused = False
                return
            self.running = True
            self.paused = False
            self.started_at = time.time()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def pause(self):
        self.paused = True

    def stop(self):
        self.paused = True
        self.running = False

    # ---------------------------------------------------------------- 模型预热
    def crop_ratio(self) -> float:
        """目标像素宽高比（宽/高）；0 = 跟随原片比例。"""
        v = str(self.cfg.get("crop_ratio") or "source").strip()
        table = {"1:1": 1.0, "4:5": 4 / 5, "3:2": 3 / 2, "16:9": 16 / 9}
        if v in table:
            return table[v]
        if v == "custom":
            txt = str(self.cfg.get("crop_ratio_custom") or "").replace("：", ":")
            try:
                a, b = txt.split(":")
                r = float(a) / float(b)
                return r if 0.2 <= r <= 5 else 0.0
            except Exception:               # noqa: BLE001
                return 0.0
        return 0.0

    def pick_device(self):
        """cuda → mps（Apple 芯片）→ cpu，用户显式选过也只在可用时采用。"""
        from . import sysenv
        return sysenv.pick_device(self.cfg.get("device") or "auto")

    def warmup(self, dev=None, block=True):
        """加载掩膜 + 头部模型。第一次要 30–40 秒（冷盘），之后同进程内是 0。

        启动后由界面在后台调一次，等用户把照片拖进来的时间就把模型读上来了；
        真正开始处理时如果还没好，这里会等它（同一把锁，不会重复加载、不会双份显存）。
        """
        dev = dev or self.pick_device()
        self.model_dev = dev
        t0 = time.time()
        if not block and self._warm_lock.locked():
            return False
        with self._warm_lock:
            if self.warm["state"] == "ready":
                return True
            self.warm.update(state="loading", err="")
            try:
                # 两个模型并行读：串行约 6 s，并行约 4 s（都是纯 IO + 一次 CUDA 上传）
                import concurrent.futures as _cf
                with _cf.ThreadPoolExecutor(max_workers=2) as _ex:
                    _f1 = _ex.submit(mask_head._seg_model, dev)
                    _f2 = _ex.submit(mask_head._kp_model, dev)
                    _f1.result()
                    _f2.result()
                self.warm.update(state="ready", dt=round(time.time() - t0, 2))
            except Exception as e:      # noqa: BLE001
                self.warm.update(state="failed", err=f"{type(e).__name__}: {e}")
                raise
        return True

    def warmup_async(self):
        if self.warm["state"] in ("loading", "ready"):
            return
        threading.Thread(target=self._warm_loop, daemon=True).start()

    def _warm_loop(self):
        try:
            self.warmup(block=False)
        except Exception:      # noqa: BLE001  预热失败要给真正处理时再报一次
            pass

    def _ensure_models(self):
        """开始处理前确保模型在显存里（后台预热过就直接返回）。"""
        if self._models_ready:
            return
        self.model_dev = self.pick_device()
        self.warmup(self.model_dev)
        self._models_ready = True

    def _loop(self):
        while self.running:
            if self.paused:
                time.sleep(0.1)
                continue
            task = None
            with self.lock:
                for t in self.tasks:
                    if t.state == "queued":
                        task = t
                        break
            if task is None:
                time.sleep(0.15)
                if all(t.state in ("done", "failed", "skipped")
                       for t in self.tasks) and self.tasks:
                    with self.lock:
                        self.running = False
                continue

            # 已有 XMP 的处理策略（见 app/xmpio.py）：
            #   protect  软件写的可覆盖，手做的跳过（默认）
            #   skip_all 任何同名 XMP 都不动
            #   force    都覆盖（覆盖前仍会备份到 _xmp_backup/）
            # 放在抢任务之后、加载模型之前，跳过一张的代价只有一次 exists()+读账本。
            dec = xmpio.decide(task.path, self.policy())
            if dec["skip"]:
                task.state = "skipped"
                task.result = {"path": task.path, "skipped": True,
                               "skip_reason": dec["reason"],
                               "origin": dec["origin"],
                               "batch": os.path.basename(os.path.dirname(task.path))}
                with self.lock:
                    self.results.append(task.result)
                    self.results = self.results[-300:]
                continue

            task.state = "running"
            task.t0 = time.time()
            _pv0 = self.preview_seconds
            try:
                self._ensure_models()
                task.result = self._process(task.path)
                task.state = "done"
            except Exception as e:  # noqa: BLE001
                task.state = "failed"
                task.err = f"{type(e).__name__}: {e}"
                task.result = {"path": task.path, "error": task.err}
                # 失败了也该知道自己该给多少锐化——只读 EXIF，不碰模型
                try:
                    ex = rawio.read_exif(task.path)
                    f = ex.get("fnumber")
                    task.result.update(fnumber=f, meta=rawio.meta_text(ex),
                                       sharp=wb_sharpen.sharpness(f) if f is not None else None)
                except Exception:      # noqa: BLE001
                    pass
                # 失败的也要有图可看：整幅预览 + 红框 + FAILED 角标，缩略图和拼版都用它
                try:
                    prev = rawio.preview_pil(task.path)
                    kit = PreviewKit(prev, np.zeros((64, 64), np.uint8),
                                     int(self.cfg.get("max_preview_side") or 1000))
                    img = kit.bgr.copy()
                    cv2.rectangle(img, (3, 3), (kit.W - 4, kit.H - 4), (70, 70, 235), 6)
                    kit._tag(img, "FAILED", 14, 16, (70, 70, 235))
                    fp = self._save_preview(img, key=f"fail|{task.path}", transient=False)
                    if fp:
                        task.result.update(preview=os.path.basename(fp),
                                           failed_frame=True)
                except Exception:      # noqa: BLE001
                    pass
                if os.environ.get("INSECT_DEBUG"):
                    traceback.print_exc()
            task.t1 = time.time()
            dt = task.t1 - task.t0
            try:
                _perf_log(task.path, dt, self.preview_seconds - _pv0)
            except Exception:      # noqa: BLE001
                pass
            with self.lock:
                self.durations.append(dt)
                self.durations = self.durations[-30:]
                self.results.append(task.result)
                self.results = self.results[-300:]

    # ---------------------------------------------------------------- 单张
    def _process(self, path):
        cfg = self.cfg
        mode = cfg.get("mode")
        seg = int(cfg.get("seg_size"))
        do_crop = mode in ("both", "crop")
        do_expo = mode in ("both", "exposure")

        ex = rawio.read_exif(path)
        prev = rawio.preview_pil(path)

        # ---- 逐步出图：掩膜 → 头点 → 裁切
        kit_holder = [None]

        def on_stage(stage, mask, core, full, head):
            if not self.preview_allowed():
                return
            try:
                _, kit_holder[0] = self._publish(
                    path, prev, mask, core, full, head, None, stage,
                    kit_holder[0])
            except Exception:  # noqa: BLE001
                pass

        ck = ""
        res = None
        if self.cfg.get("mask_cache", True):
            ck = self._analysis_key(path, seg)
            res = self._load_analysis(ck)
            if res is not None:
                # 缓存命中也要把两帧照样推给界面，视觉上没差别
                on_stage("mask", res["mask"], res["core"], res["full"], None)
                on_stage("head", res["mask"], res["core"], res["full"], res.get("head"))
        if res is None:
            res = mask_head.analyze(prev, dev=self.model_dev, size=seg,
                                    want_head=True, progress=on_stage)
            if self.cfg.get("mask_cache", True) and res.get("ok"):
                self._save_analysis(ck or self._analysis_key(path, seg), res)
        if not res.get("ok"):
            raise RuntimeError(res.get("reason", "mask_failed"))

        nsub = mask_head.count_subjects(res["mask"])
        head = res["head"] if nsub <= 1 else None
        core, full = res["core"], res["full"]
        batch_name = os.path.basename(os.path.dirname(path))

        # 模型原值先留一份（学习时要用「预测 → 修正」这一对）
        head_pred = list(head) if head else None
        fix_info = {"n": 0, "applied": False}
        if head is not None and self.cfg.get("head_fix", True):
            head, fix_info = head_fix.apply(core, full, head)
        head_shown = list(head) if head else None   # 屏幕上真正画出来的那个点

        mask_name = self._save_mask(res["mask"], path)
        out = {"path": path, "batch": batch_name, "mask": mask_name,
               "cached": bool(res.get("cached")),
               "fnumber": ex.get("fnumber"), "nsub": nsub,
               "meta": rawio.meta_text(ex),
               "head": head is not None,
               "head_xy": [round(head[0], 6), round(head[1], 6)] if head else None,
               "head_shown": [round(v, 6) for v in head_shown] if head_shown else None,
               "head_pred": [round(v, 6) for v in head_pred] if head_pred else None,
               "head_fix": fix_info,
               "mask_size": res["mask_size"],
               "degraded": bool(res.get("degraded")),
               "core": list(core), "full": list(full),
               "time": round(time.time(), 3)}

        ev = sh = None
        cr = None

        if do_expo:
            ev_path, ev_warn = models.resolve("ev", cfg.get("ev_coef") or "")
            try:
                exposure_model.use(ev_path or None)
            except Exception as e:      # noqa: BLE001
                ev_warn = f"{type(e).__name__}: {e}；已退回内置"
                exposure_model.use(None)
            if ev_warn:
                out["ev_warn"] = ev_warn
            me = exposure_model.measure_pil(prev, res["mask"], full)
            if me["L_in"] is not None and me["L_box"] is not None:
                ev = exposure_model.predict(me["L_in"], me["L_box"])
                # 用户补偿：叠加在模型输出上，不改模型本身；越界夹到 ±5 EV
                bias = float(cfg.get("ev_bias") or 0.0)
                ev_final = max(-5.0, min(5.0, float(ev["ev"]) + bias))
                out.update(ev=ev_final, ev_raw=ev["ev_raw"], ev_bias=bias,
                           L_in=me["L_in"], L_box=me["L_box"],
                           occ=me["occ"], saturated=bool(ev["saturated"]))
                ev["ev"] = ev_final      # 写 XMP 用的是这个字典，别只改 out
            else:
                out["note"] = "亮度测量失败，只写裁切"

        # 锐化：按光圈分档（严格递增 20/30/40/50/60/65，见 data/sharpen_table.csv）。
        # 只有读不到光圈时 sharp=None，才不写该字段。
        if cfg.get("sharpen_enable"):
            f = ex.get("fnumber")
            sh = wb_sharpen.sharpness(f)
            out["sharp"] = sh
            if f is None:
                out["sharp_note"] = "无光圈信息"
            elif sh is None:
                out["sharp_note"] = f"f/{float(f):g} 不在分档表覆盖范围内"
            else:
                out["sharp_note"] = f"f/{float(f):g} → {sh}"

        if do_crop:
            c_path, c_warn = models.resolve("crop", cfg.get("coef") or "")
            try:
                J = crop_v3.load(c_path) if c_path else None
            except Exception as e:      # noqa: BLE001
                c_warn = f"{type(e).__name__}: {e}；已退回内置"
                J = None
            if c_warn:
                out["coef_warn"] = c_warn
            if (J or {}).get("space") == "crop_relative":
                from . import crop_rel
                _w, _h = prev.size
                cr = crop_rel.compute_crop(core, full, head, multi=(nsub > 1), J=J,
                                           aspect=_w / max(_h, 1), ratio=self.crop_ratio())
                out["crop_space"] = "crop_relative"
            else:
                _w, _h = prev.size
                cr = crop_v3.compute_crop(core, full, head, multi=(nsub > 1), J=J,
                                          ratio=self.crop_ratio(),
                                          aspect=_w / max(_h, 1))
            out.update(crop=[round(v, 5) for v in cr["crop"]], w=round(cr["w"], 4),
                       cx=round(cr["cx"], 4), cy=round(cr["cy"], 4),
                       canvas_limited=bool(cr["canvas_limited"]),
                       leg_pad_ok=bool(crop_v3.leg_pad_ok(cr["crop"], full, cr["pad_used"])))

        # 写 sidecar：mode 决定写哪几块，缺的部分写 None。
        # 白平衡固定不写（T/tint 传 None）——沿用相机 As Shot。
        wr = xmpio.write_sidecar(
            path,
            crop=cr["crop"] if cr is not None else None,
            ev=ev["ev"] if ev is not None else None,
            T=None, tint=None,
            sharpness=sh if cfg.get("sharpen_enable") else None,
            profile=cfg.get("profile"),
            backup=bool(cfg.get("backup")),
            origin="auto", policy=self.policy(),
        )
        out["xmp"] = wr["path"]
        out["backed"] = wr["backed"]
        out["written"] = wr["written"]
        out["origin"] = wr["origin"]          # 写之前：none / auto / manual

        # 最后一帧：加上裁切框与"将被裁掉"的绿色斜线；同时落一份定稿图给拼版用
        if self.preview_allowed():
            ev_show = ev["ev"] if (ev and cfg.get("preview_exposure", True)) else None
            pv, _ = self._publish(path, prev, res["mask"], core, full, head,
                                  cr["crop"] if cr else None, "done",
                                  kit_holder[0],
                                  key=self._cache_key(path, core, full, head, cr),
                                  ev=ev_show)
            if pv:
                out["preview"] = os.path.basename(pv)
        if kit_holder[0] is not None:
            self.preview_images += 1
            self._remember_kit(path, kit_holder[0], (core, full, head))
        return out

    @staticmethod
    def _cache_key(path, core, full, head, cr):
        crop = cr["crop"] if cr else None
        return f"{path}|{core}|{full}|{head}|{crop}"

    def _remember_kit(self, path, kit, geom):
        """留最近 3 张的预览底图，手动改框后可以立刻重画缩略图。"""
        try:
            self._kits[path] = (kit, geom)
            while len(self._kits) > 3:
                self._kits.popitem(last=False)
        except Exception:      # noqa: BLE001
            pass

    # ---------------------------------------------------------------- 预览
    def ping(self):
        self.last_ping = time.time()

    def preview_allowed(self):
        """只看心跳：界面每 0.5 s ping 一次，最小化后自然停止（6 s 超时）。"""
        if not self.cfg.get("preview_enabled"):
            return False
        return (time.time() - self.last_ping) < 6.0

    def _weights_sig(self):
        """权重一变，缓存全部作废。"""
        try:
            fp = os.path.join(ROOT, "skill", "assets", "weights", "head_kp_v2.pth")
            st = os.stat(fp)
            return f"{int(st.st_mtime)}-{st.st_size}"
        except OSError:
            return "0"

    def _analysis_key(self, path, seg, want_head=True):
        try:
            st = os.stat(path)
        except OSError:
            return ""
        raw = f"{os.path.normcase(path)}|{st.st_mtime_ns}|{st.st_size}|{seg}|{int(want_head)}|{self._weights_sig()}"
        return hashlib.sha1(raw.encode("utf-8", "ignore")).hexdigest()[:20]

    def _load_analysis(self, key):
        if not key:
            return None
        jf = os.path.join(ANALYSIS_DIR, key + ".json")
        pf = os.path.join(ANALYSIS_DIR, key + ".png")
        if not (os.path.exists(jf) and os.path.exists(pf)):
            return None
        try:
            with open(jf, encoding="utf-8") as f:
                meta = json.load(f)
            mask = cv2.imdecode(np.fromfile(pf, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            if mask is None:
                return None
            side = int(meta.get("mask_size") or meta.get("size") or 0)
            if not side:
                return None
            if mask.shape[0] != side:
                mask = cv2.resize(mask, (side, side), interpolation=cv2.INTER_LINEAR)
            meta["mask"] = mask
            meta["cached"] = True
            return meta
        except Exception:      # noqa: BLE001
            return None

    def _save_analysis(self, key, res):
        if not key or not res.get("ok"):
            return
        try:
            mask = res["mask"]
            meta = {k: res[k] for k in ("ok", "size", "core", "full", "head",
                                        "conf", "degraded") if k in res}
            meta["mask_size"] = int(mask.shape[0])
            meta["core"] = [float(v) for v in meta.get("core", [])]
            meta["full"] = [float(v) for v in meta.get("full", [])]
            if meta.get("head") is not None:
                meta["head"] = [float(v) for v in meta["head"]]
            with open(os.path.join(ANALYSIS_DIR, key + ".json"), "w", encoding="utf-8") as fh:
                json.dump(meta, fh, ensure_ascii=False)
            ok, buf = cv2.imencode(".png", mask)
            if ok:
                buf.tofile(os.path.join(ANALYSIS_DIR, key + ".png"))
            _prune_dir(ANALYSIS_DIR, keep=4000)
        except Exception:      # noqa: BLE001
            pass

    def _load_mask(self, name):
        if not name:
            return None
        fp = os.path.join(MASK_DIR, name)
        if not os.path.exists(fp):
            return None
        try:
            return cv2.imdecode(np.fromfile(fp, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        except Exception:      # noqa: BLE001
            return None

    def edit_base(self, path, r, ev=None):
        """微调画布用：原图缩到 1000px + 掩膜红叠加（有掩膜才叠）。返回 PIL 图。

        这样点开一张处理完的照片，看到的是带掩膜的图，而不是没标记的原片。
        """
        prev = rawio.preview_thumb(path, 1100)
        mask = self._load_mask(r.get("mask"))
        if mask is None:
            # 没有掩膜也要能按 EV 显示：给一张空掩膜（PreviewKit 会跳过叠加）
            mask = np.zeros((64, 64), np.uint8)
        kit = PreviewKit(prev, mask, int(self.cfg.get("max_preview_side") or 1000), ev=ev)
        return Image.fromarray(cv2.cvtColor(kit.bgr, cv2.COLOR_BGR2RGB))

    def _save_mask(self, mask, key):
        """把 768² 掩膜存成 PNG：缩略图墙补图、点开预览都靠它。约 15 KB/张。"""
        try:
            name = hashlib.sha1(f"mask|{key}".encode("utf-8", "ignore")).hexdigest()[:16] + ".png"
            ok, buf = cv2.imencode(".png", mask)
            if not ok:
                return None
            buf.tofile(os.path.join(MASK_DIR, name))
            return name
        except Exception:      # noqa: BLE001
            return None

    def _publish(self, path, prev, mask, core, full, head, crop, stage, kit=None,
                 key=None, ev=None):
        if not self.preview_allowed():
            return None, kit
        t0 = time.time()
        if kit is None:
            kit = PreviewKit(prev, mask, int(self.cfg.get("max_preview_side") or 1000))
        # 大图：给了 ev 就左原图右调整后；定稿图（缩略图墙/拼版）保持原图
        live_img = kit.render(core, full, head, crop, ev=ev)
        fp = self._save_preview(live_img)
        cache_path = None
        if key:
            cache_path = self._save_preview(kit.render(core, full, head, crop),
                                            key, transient=False)
        self.preview_seconds += time.time() - t0
        if fp:
            with self.lock:
                # name 存绝对路径：定稿图在 cache/ 子目录，界面不能只按文件名拼
                self.live = {"path": path, "name": fp, "stage": stage,
                             "t": time.time()}
        return (cache_path or fp), kit

    def _save_preview(self, bgr, key=None, transient=True):
        """写一张叠加图。key 给定时另存一份固定名字的定稿图（拼版/缩略图用）。

        transient=False 时只写定稿图，不落临时帧（大图那帧另有一份，别互相覆盖）。
        """
        stamp = f"{int(time.time()*1000)}_{abs(hash(time.time())) % 10**8}"
        name = f"{stamp}.jpg"
        fp = os.path.join(PREVIEW_DIR, name)
        ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        if not ok:
            return None
        if transient:
            buf.tofile(fp)
        out = fp
        if key:
            # 定稿图按内容命名：同一张、同样的框重跑会落到同一个文件，不会越积越多
            try:
                cname = hashlib.sha1(str(key).encode("utf-8", "ignore")).hexdigest()[:16] + ".jpg"
                out = os.path.join(CACHE_DIR, cname)
                buf.tofile(out)
            except Exception:      # noqa: BLE001
                out = fp
        if transient:
            files = [x for x in sorted(os.listdir(PREVIEW_DIR)) if x.endswith(".jpg")]
            for f in files[:-40]:
                try:
                    os.remove(os.path.join(PREVIEW_DIR, f))
                except OSError:
                    pass
        return out

    def refresh_ev(self, path, ev):
        """就地重画某张的实时预览（切「曝光预览」开关时用）。

        底图还在内存就直接画；不在就按原图 + 掩膜重建。返回新图路径，失败返回 ""。
        """
        with self.lock:
            task = next((t for t in self.tasks if t.path == path), None)
            r = dict(task.result) if task and task.result else None
        if not r or not r.get("crop"):
            return ""
        kit = self._kits.get(path)
        if kit is None:
            try:
                prev = rawio.preview_thumb(path, 1100)
                mask = self._load_mask(r.get("mask"))
                if mask is None:
                    mask = np.zeros((64, 64), np.uint8)
                kit = (PreviewKit(prev, mask,
                                  int(self.cfg.get("max_preview_side") or 1000)), None)
            except Exception:      # noqa: BLE001
                return ""
        try:
            img = kit[0].render(r["core"], r["full"], r.get("head_xy"),
                                r["crop"], ev=ev)
            fp = self._save_preview(img, transient=True)
            return fp or ""
        except Exception:          # noqa: BLE001
            return ""

    def live_preview(self):
        with self.lock:
            return dict(self.live) if self.live else {}

    def commit_crop(self, path, crop, head=None, core=None, full=None):
        """手动微调后写回 XMP（只改裁切，EV/锐化沿用这条结果）。

        head 不为空、且与屏幕上那个点差得开时，顺手记一条头部修正样本，
        下次遇到几何量相近的照片会自动补偿（见 skill/scripts/head_fix.py）。

        这一笔的 origin 记成 manual：是你亲手定的框，之后跑批默认不覆盖。
        """
        with self.lock:
            task = next((t for t in self.tasks if t.path == path), None)
            r = dict(task.result) if task and task.result else None
        if not r:
            raise RuntimeError("这条还没有处理结果，不能写裁切")
        crop = [float(max(0.0, min(1.0, v))) for v in crop]
        if crop[2] - crop[0] < 0.02 or crop[3] - crop[1] < 0.02:
            raise RuntimeError("裁切框太小")
        core = [float(v) for v in (core or r.get("core"))]
        full = [float(v) for v in (full or r.get("full"))]
        wr = xmpio.write_sidecar(
            path, crop=crop, ev=r.get("ev"), T=None, tint=None,
            sharpness=r.get("sharp") if self.cfg.get("sharpen_enable") else None,
            profile=self.cfg.get("profile"), backup=bool(self.cfg.get("backup")),
            origin="manual", policy="force")
        learned = None
        pred = r.get("head_shown") or r.get("head_pred")
        if head is not None and pred:
            hx, hy = float(head[0]), float(head[1])
            px, py = pred
            cw = max(core[2] - core[0], 1e-6)
            if ((hx - px) ** 2 + (hy - py) ** 2) ** 0.5 / cw > 0.02:   # 2% 体宽才记
                try:
                    n = head_fix.add(core, full, (px, py), (hx, hy),
                                     batch=r.get("batch", ""), path=path)
                    learned = {"n": n, "dx": round((hx - px) / cw, 4),
                               "dy": round((hy - py) / cw, 4),
                               "mode": head_fix.stats().get("mode")}
                except Exception:      # noqa: BLE001  学习失败不能影响写 XMP
                    learned = None

        # 重画这张的缩略图：底图不在内存（被挤掉了）就按原图 + 掩膜重建一次，
        # 否则界面会继续显示旧的那张，头点看着像"跳回错误位置"。
        pv = None
        kit = self._kits.get(path)
        if kit is None:
            try:
                prev = rawio.preview_thumb(path, 1100)
                mask = self._load_mask(r.get("mask"))
                if mask is None:
                    mask = np.zeros((64, 64), np.uint8)
                kit = (PreviewKit(prev, mask,
                                  int(self.cfg.get("max_preview_side") or 1000)), None)
            except Exception:      # noqa: BLE001
                kit = None
        if kit is not None:
            try:
                img = kit[0].render(core, full, head, crop)
                pv = self._save_preview(
                    img, key=self._cache_key(path, core, full, head, {"crop": crop}))
            except Exception:      # noqa: BLE001
                pv = None

        if task and task.result is not None:
            task.result.update(
                crop=[round(v, 5) for v in crop],
                w=round(crop[2] - crop[0], 4),
                cx=round((crop[0] + crop[2]) / 2, 4),
                cy=round((crop[1] + crop[3]) / 2, 4),
                core=[round(v, 5) for v in core], full=[round(v, 5) for v in full],
                manual_crop=True,
                preview=os.path.basename(pv) if pv else (r.get("preview") or None),
                origin="manual", written=wr["written"],
                manual_head=[round(float(head[0]), 6), round(float(head[1]), 6)]
                            if head is not None else None,
                head_xy=[round(float(head[0]), 6), round(float(head[1]), 6)]
                        if head is not None else task.result.get("head_xy"),
                learned=learned)
        return wr

    # ---------------------------------------------------------------- 状态
    def status(self):
        with self.lock:
            total = len(self.tasks)
            done = sum(1 for t in self.tasks if t.state == "done")
            failed = sum(1 for t in self.tasks if t.state == "failed")
            skipped = sum(1 for t in self.tasks if t.state == "skipped")
            running = sum(1 for t in self.tasks if t.state == "running")
            queued = sum(1 for t in self.tasks if t.state == "queued")
            durs = list(self.durations)
            cur = next((t for t in self.tasks if t.state == "running"), None)
            elapsed = time.time() - self.started_at if self.started_at else 0
            avg = (sum(durs) / len(durs)) if durs else 0.0
            remain = avg * queued if avg else 0.0
            return {
                "running": self.running and not self.paused,
                "paused": self.paused,
                "total": total, "done": done, "failed": failed,
                "skipped": skipped,
                "running_n": running, "queued": queued,
                "speed": round(avg, 2),                      # 秒/张
                "per_min": round(60.0 / avg, 1) if avg else 0,
                "elapsed": round(elapsed, 1),
                "eta": round(remain, 1),
                "current": cur.path if cur else None,
                "preview_allowed": self.preview_allowed(),
                "preview_cost": round(self.preview_seconds / self.preview_images, 3)
                                if self.preview_images else 0.0,
                "warm": dict(self.warm),
                "cfg": self.cfg.as_dict(),
            }

    def recent(self, n=40):
        with self.lock:
            rs = [r for r in self.results if r]
        return rs[-n:][::-1]

    def sheet_items(self):
        """缩略图墙：只给已经有定稿图的（失败/跳过没有图）。"""
        with self.lock:
            rs = [dict(t.result) for t in self.tasks
                  if t.result and t.result.get("preview")]
        return [r for r in rs if not r.get("skipped")]

    def export_items(self):
        """拼版：done + failed 全要，按队列顺序。失败的在版面上标红。"""
        with self.lock:
            rs = [dict(t.result) for t in self.tasks if t.result]
        return [r for r in rs if not r.get("skipped")]

    def export_file(self, r):
        """拼版用的一张图：有定稿图直接给；没有就现画一张（掩膜 PNG 还在就能带掩膜）。

        返回路径或 ""。只在导出时对缺图的那些调用，正常情况一次都不会触发。
        """
        name = r.get("preview")
        if name:
            fp = os.path.join(CACHE_DIR, name)
            if os.path.exists(fp):
                return fp
        if r.get("error") or not r.get("core") or not r.get("crop"):
            return ""
        try:
            prev = rawio.preview_pil(r["path"])
            mask = None
            mn = r.get("mask")
            if mn:
                mp = os.path.join(MASK_DIR, mn)
                if os.path.exists(mp):
                    buf = np.fromfile(mp, dtype=np.uint8)
                    mask = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
            if mask is None:
                mask = np.zeros((128, 128), np.uint8)
            kit = PreviewKit(prev, mask, int(self.cfg.get("max_preview_side") or 1000))
            head = r.get("head_shown") or r.get("head_xy")
            img = kit.render(r["core"], r["full"], head, r.get("crop"))
            return self._save_preview(
                img, key=self._cache_key(r["path"], r["core"], r["full"], head,
                                         {"crop": r.get("crop")}), transient=False)
        except Exception:      # noqa: BLE001
            return ""

    def all_results(self):
        with self.lock:
            return [dict(t.result) for t in self.tasks if t.result]


def _prune_dir(d: str, keep: int = 4000, every: int = 100) -> None:
    """目录里按修改时间只留最新 keep 个文件；每 every 次调用才真的扫一遍。"""
    global _prune_tick
    _prune_tick += 1
    if _prune_tick % every:
        return
    try:
        files = [os.path.join(d, f) for f in os.listdir(d)]
        if len(files) <= keep:
            return
        files.sort(key=lambda p: os.path.getmtime(p))
        for f in files[:len(files) - keep]:
            try:
                os.remove(f)
            except OSError:
                pass
    except OSError:
        pass


_prune_tick = 0


def _perf_log(path, total, preview):
    """每张一行：总耗时、预览耗时、其余（读 RAW + 分割 + 头点 + 写 xmp）。
    写在 <程序目录>/data/perf.log，用来定位"为什么这张 7 秒"。"""
    import os as _os
    from .paths import data_dir
    line = "%s\t总 %.2fs\t预览 %.2fs\t其余 %.2fs\t%s\n" % (
        time.strftime("%Y-%m-%d %H:%M:%S"), total, preview,
        max(total - preview, 0.0), _os.path.basename(path))
    try:
        with open(_os.path.join(data_dir(), "perf.log"), "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:      # noqa: BLE001
        pass
