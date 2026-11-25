"""训练：从「原片 + 同名 XMP」的一批目录里重拟合三套参数。

流程（与 skill 的标定口径一致）：
    ① 扫描：找出有 sidecar 的图
    ② 提取：跑一次掩膜 → core/full/head；同时读 XMP 真值（裁切/EV/白平衡）
    ③ 拟合：
         裁切 105 项（岭回归 λ=0.03，按批次 5 折留出）
         曝光双参数（最小二乘，按批次留出 MAE）
         白平衡（批次中位 + 全局中位）
    ④ 落盘：trainset.csv + 三份参数 + report.md

只输出到 data/train_*，**不覆盖** skill 里的在用系数；要不要替换由人决定。
"""
from __future__ import annotations

import csv
import json
import math
import os
import statistics
import threading
import time

import numpy as np

from . import crop_pair, crop_rel, models, rawio, xmpio

import sys as _sys
from .paths import app_root, skill_dir


_SKILL = skill_dir()
_sys.path.insert(0, os.path.join(_SKILL, "scripts"))
import exposure_model
import mask_head        # noqa: E402

ROOT = app_root()
OUT_ROOT = os.path.join(ROOT, "data")

FIELDS = ["group", "jpg", "nef", "crop_l", "crop_t", "crop_r", "crop_b",
          "core_l", "core_t", "core_r", "core_b",
          "full_l", "full_t", "full_r", "full_b",
          "hx", "hy", "multi", "EV", "T", "Tint", "fnumber", "L_in", "L_box", "label_path"]


class Trainer:
    def __init__(self, cfg, engine):
        self.cfg = cfg
        self.engine = engine          # 复用已加载的模型
        self.lock = threading.RLock()
        self.state = "idle"           # idle | scan | extract | fit | done | failed
        self.msg = ""
        self.progress = 0.0
        self.log = []
        self.out_dir = ""
        self.report = {}
        self.roots = []
        self.rows = []
        self.train_csv = ""
        self._stop = False
        self.thread = None

    # ---------------------------------------------------------------- API
    def start(self, roots, subdir: str = ""):
        """roots：目录 / 目录列表 / [{dir, files}]。
        files 非空表示「只用这几个文件」，为空表示整个目录。"""
        if isinstance(roots, (str, dict)):
            roots = [roots]
        entries = []
        for r in roots:
            if isinstance(r, dict):
                d = os.path.normpath(r.get("dir") or "")
                if not os.path.isdir(d):
                    continue
                fs = [os.path.normpath(f) for f in (r.get("files") or [])
                      if f and os.path.isfile(f)]
                if r.get("files") and not fs:
                    continue
                original = r.get("original_dir")
                if original and not os.path.isdir(original):
                    return False, "原图目录不存在 / Original folder is missing"
                entries.append({"dir": d, "files": fs, "original_dir": original,
                                "mode": r.get("mode") or ("pair" if original else "xmp")})
            else:
                d = os.path.normpath(r) if r else ""
                if d and os.path.isdir(d):
                    entries.append({"dir": d, "files": [], "original_dir": None, "mode": "xmp"})
        if not entries:
            return False, "先选至少一个存在的目录"
        with self.lock:
            if self.state in ("scan", "extract", "fit"):
                return False, "已有训练在跑"
            self.state = "scan"
            self.msg = "扫描中"
            self.progress = 0.0
            self.log = []
            self.report = {}
            self._stop = False
            self._pause = False
            self._relative_done = False
            self.roots = [e["dir"] for e in entries]
        self.thread = threading.Thread(target=self._run, args=(entries, subdir), daemon=True)
        self.thread.start()
        return True, f"已开始（{len(entries)} 个文件夹）"

    def stop(self):
        self._stop = True

    def toggle_pause(self):
        self._pause = not getattr(self, "_pause", False)
        self._say("已暂停（点「继续训练」接着跑）" if self._pause else "继续")
        return self._pause

    def status(self):
        with self.lock:
            return {"state": self.state, "msg": self.msg,
                    "progress": round(self.progress, 1),
                    "log": self.log[-60:], "out_dir": self.out_dir,
                    "report": self.report}

    def _say(self, s):
        with self.lock:
            self.log.append(f"{time.strftime('%H:%M:%S')}  {s}")

    # ---------------------------------------------------------------- 主流程
    def _run(self, roots, subdir):
        try:
            self._extract(roots, subdir)
            if getattr(self, "_relative_done", False):
                return                      # 成片相对空间：提取与拟合已在内部完成
            if self._stop:
                raise RuntimeError("已停止")
            self._fit()
            if "error" in self.report.get("crop", {}):
                raise RuntimeError(self.report["crop"]["error"])
            with self.lock:
                self.state = "done"
                self.msg = "完成"
                self.progress = 100.0
        except Exception as e:  # noqa: BLE001
            with self.lock:
                self.state = "failed"
                self.msg = f"{type(e).__name__}: {e}"
            self._say(f"失败：{e}")

    # ---------------------------------------------------------------- ① 扫描 + ② 提取
    def _extract(self, entries, subdir):
        if any(e.get("mode") == "crop_only" for e in entries):
            return self._extract_relative([e for e in entries if e.get("mode") == "crop_only"], subdir)
        pairs, seen = [], set()
        for ent in entries:
            if self._stop:
                raise RuntimeError("已停止")
            root, selected = ent["dir"], ent["files"]
            files = selected or rawio.scan_image_dir(root, self.cfg.get("recursive"))
            original = ent.get("original_dir")
            for path in files:
                while self._pause and not self._stop:
                    time.sleep(0.2)
                if self._stop:
                    raise RuntimeError("已停止")
                if not original and rawio.is_image(path):
                    target = xmpio.read_truth(path)
                    source = path
                    label = xmpio.sidecar_path(path)
                elif original and crop_pair.is_jpeg(path):
                    try:
                        source, target = crop_pair.match_export(path, root, original, rawio)
                    except Exception:      # noqa: BLE001  单张读不了就跳过，不中断整批
                        source, target = None, None
                    label = path
                    if target is None:
                        self._say(f"未能验证裁切配对 / Crop match rejected: {path}")
                else:
                    continue
                if not target or not target.get("HasCrop"):
                    continue
                coords = [target.get(k) for k in crop_pair.BOUNDS]
                if any(v is None or not math.isfinite(v) for v in coords):
                    continue
                left, top, right, bottom = coords
                if right - left <= 0.01 or bottom - top <= 0.01:
                    continue
                key = _cache_key(source)
                if key in seen:
                    continue
                seen.add(key)
                group = _group_of(source, original or root)
                pairs.append((source, target, group, label))
        self._say(f"已加载 {len(pairs)} 张照片（有裁切真值）")
        if len(pairs) < 50:
            raise RuntimeError("可用样本少于 50 张，无法拟合")

        stamp = time.strftime("%Y%m%d_%H%M")
        self.out_dir = os.path.join(OUT_ROOT, f"train_{stamp}")
        os.makedirs(self.out_dir, exist_ok=True)

        with self.lock:
            self.state = "extract"
            self.msg = "提取几何与真值"
        self.engine._ensure_models()

        rows = []
        cache = _load_cache()
        reused = 0
        t0 = time.time()
        for i, (p, t, group, label) in enumerate(pairs, 1):
            if self._stop:
                raise RuntimeError("已停止")
            while getattr(self, "_pause", False) and not self._stop:
                time.sleep(0.2)
            key = _cache_key(p)
            hit = cache.get(key)
            seg_size = int(self.cfg.get("seg_size"))
            if hit and hit.get("seg_size") == seg_size and hit.get("mtime") == _mtime(p):
                rows.append(_with_label(hit["row"], t, group, label))
                reused += 1
                with self.lock:
                    self.progress = 100.0 * i / len(pairs)
                    self.msg = f"复用 {reused} 张（已提取过）"
                continue
            try:
                prev = rawio.preview_pil(p)
                res = mask_head.analyze(
                    prev, dev=self.engine.model_dev, size=seg_size,
                    want_head=True)
                if not res.get("ok"):
                    continue
                nsub = mask_head.count_subjects(res["mask"])
                head = res["head"] if nsub <= 1 else None
                core, full = res["core"], res["full"]
                me = exposure_model.measure_pil(prev, res["mask"], full)
                row = {
                    "jpg": p, "nef": p,
                    "core_l": round(core[0], 6), "core_t": round(core[1], 6),
                    "core_r": round(core[2], 6), "core_b": round(core[3], 6),
                    "full_l": round(full[0], 6), "full_t": round(full[1], 6),
                    "full_r": round(full[2], 6), "full_b": round(full[3], 6),
                    "hx": "" if head is None else round(head[0], 6),
                    "hy": "" if head is None else round(head[1], 6),
                    "multi": int(nsub > 1),
                    "fnumber": "",
                    "L_in": "" if me.get("L_in") is None else round(me["L_in"], 2),
                    "L_box": "" if me.get("L_box") is None else round(me["L_box"], 2),
                }
                rows.append(_with_label(row, t, group, label))
                cache[key] = {"mtime": _mtime(p), "seg_size": seg_size, "row": row}
                if i % 20 == 0:
                    _save_cache(cache)
            except Exception as e:  # noqa: BLE001
                self._say(f"跳过 {os.path.basename(p)}: {type(e).__name__}")
            with self.lock:
                self.progress = 100.0 * i / max(len(pairs), 1)
                self.msg = f"提取 {i}/{len(pairs)}"
            if i % 20 == 0:
                el = time.time() - t0
                self._say(f"{i}/{len(pairs)}  平均 {el/i:.2f}s/张  预计还需 {(len(pairs)-i)*el/i/60:.1f} 分钟")

        csvp = os.path.join(self.out_dir, "trainset.csv")
        with open(csvp, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        _save_cache(cache)
        if reused:
            self._say(f"其中 {reused} 张直接用了上次的提取结果，没重复跑")
        self._say(f"写出 {csvp}（{len(rows)} 行）")
        self.train_csv = csvp
        self.rows = rows

    def _extract_relative(self, entries, subdir):
        """只用成品 JPG：在成片自己身上量「虫体占画面多少、偏在哪」，
        拟合成「虫体 → 成片」的相对关系，推理时反解裁切框。不需要原图、不需要 XMP。"""
        files, groups = [], {}
        for ent in entries:
            root, selected = ent["dir"], ent["files"]
            fs = selected or rawio.scan_image_dir(root, self.cfg.get("recursive"))
            fs = [p for p in fs if crop_pair.is_jpeg(p)]
            self._say(f"{os.path.basename(root)}：{len(fs)} 张成品 JPG")
            for p in fs:
                files.append(p); groups[p] = _cache_key(os.path.dirname(p))
        if len(files) < 50:
            raise RuntimeError(f"成品 JPG 只有 {len(files)} 张，至少 50 张才能拟合 / "
                               f"Need 50+ JPEG exports, got {len(files)}")

        stamp = time.strftime("%Y%m%d_%H%M")
        self.out_dir = os.path.join(OUT_ROOT, f"train_{stamp}")
        os.makedirs(self.out_dir, exist_ok=True)
        with self.lock:
            self.state = "extract"; self.msg = "提取（成片相对空间）"
        self.engine._ensure_models()

        rows_rel, bad = [], 0
        t0 = time.time()
        for i, p in enumerate(files, 1):
            if self._stop:
                raise RuntimeError("已停止")
            while self._pause and not self._stop:
                time.sleep(0.2)
            try:
                prev = rawio.preview_pil(p)
                res = mask_head.analyze(prev, dev=self.engine.model_dev,
                                        size=int(self.cfg.get("seg_size")), want_head=True)
                if not res.get("ok"):
                    bad += 1; continue
                nsub = mask_head.count_subjects(res["mask"])
                head = res["head"] if nsub <= 1 else None
                aspect = prev.size[0] / max(prev.size[1], 1)
                rows_rel.append((res["core"], res["full"], head, nsub > 1, aspect, p,
                                 groups[p]))
            except Exception as e:      # noqa: BLE001
                bad += 1
                self._say(f"跳过 {os.path.basename(p)}: {type(e).__name__}")
            with self.lock:
                self.progress = 100.0 * i / len(files)
                self.msg = f"提取 {i}/{len(files)}（跳过 {bad}）"
            if i % 20 == 0:
                el = time.time() - t0
                self._say(f"{i}/{len(files)}  平均 {el/i:.2f}s/张")

        self._say(f"可用于训练的成片 {len(rows_rel)} 张（跳过 {bad}）")
        if len(rows_rel) < 50:
            raise RuntimeError(f"有效成片 {len(rows_rel)}/50，无法拟合")

        with self.lock:
            self.state = "fit"; self.msg = "拟合（成片相对空间）"
        J = crop_rel.fit([r[:5] for r in rows_rel])
        J["fitted"] = time.strftime("%Y-%m-%d %H:%M")
        J["groups"] = sorted({r[6] for r in rows_rel})
        cpath = os.path.join(self.out_dir, "crop_coef.json")
        json.dump(J, open(cpath, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        rep = {"crop": {"space": "crop_relative", "n": J["n"], "mae_in": J["mae_in"]}}
        rep["crop"]["adopted"] = models.adopt_trained("crop", cpath)   # 收不进去就等于没训练，直接报错
        self._say(f"已收进模型库：{rep['crop']['adopted']}")
        with open(os.path.join(self.out_dir, "trainset.csv"), "w", newline="",
                  encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["image", "group", "core_l", "core_t", "core_r", "core_b",
                        "full_l", "full_t", "full_r", "full_b", "multi", "aspect"])
            for core, full, head, multi, aspect, p, g in rows_rel:
                w.writerow([p, g, *[round(v, 6) for v in core], *[round(v, 6) for v in full],
                            int(multi), round(aspect, 4)])
        md = [f"# 训练报告 {time.strftime('%Y-%m-%d %H:%M')}", "",
              "空间：成片相对（不需要原图与 XMP）", "```",
              json.dumps(rep, ensure_ascii=False, indent=1), "```"]
        open(os.path.join(self.out_dir, "report.md"), "w", encoding="utf-8").write("\n".join(md))
        with self.lock:
            self.report = rep
            self.state = "done"
            self.msg = "完成"
            self.progress = 100.0
        self._relative_done = True
        self._say("完成")

    # ---------------------------------------------------------------- ③ 拟合
    def _fit(self):
        with self.lock:
            self.state = "fit"
            self.msg = "拟合"
            self.progress = 0.0
        rows = self.rows
        rep = {}

        # --- 裁切
        try:
            import refit_crop as R
            X, Y, G, GT = [], [], [], []
            for r in rows:
                try:
                    f = R.feats(r)
                except Exception:  # noqa: BLE001
                    continue
                l, t, rr, b = (float(r["crop_l"]), float(r["crop_t"]),
                               float(r["crop_r"]), float(r["crop_b"]))
                if rr - l <= 0.01 or b - t <= 0.01:
                    continue
                X.append(R.design(f))
                Y.append([(l + rr) / 2, (t + b) / 2, math.log2(rr - l)])
                G.append(r["group"])
                GT.append((l, t, rr, b))
            if len(X) < 50:
                raise RuntimeError(f"有效裁切样本 {len(X)}/50 / Usable crop samples: {len(X)}/50")
            X = np.array(X); Y = np.array(Y); G = np.array(G)
            mu, sd = X.mean(0), X.std(0) + 1e-9
            mu[0], sd[0] = 0.0, 1.0
            lam = 0.03
            coefs = {n: R.ridge(X, Y[:, j], mu, sd, lam)
                     for j, n in enumerate(("cx", "cy", "log2w"))}
            ious = [R.iou(_box(R.decode(x, coefs)), gt) for x, gt in zip(X, GT)]
            # 按批次 5 折
            rng = np.random.RandomState(0)
            bl = sorted(set(G)); rng.shuffle(bl)
            folds = [set(bl[i::5]) for i in range(5)]
            out_ious = []
            for k in range(5):
                te = np.array([g in folds[k] for g in G]); tr = ~te
                if tr.sum() < 50 or te.sum() < 10:
                    continue
                mk, sk = X[tr].mean(0), X[tr].std(0) + 1e-9
                mk[0], sk[0] = 0.0, 1.0
                ck = {n: R.ridge(X[tr], Y[tr, j], mk, sk, lam)
                      for j, n in enumerate(("cx", "cy", "log2w"))}
                for i in np.where(te)[0]:
                    out_ious.append(R.iou(_box(R.decode(X[i], ck)), GT[i]))
            rep["crop"] = {"n": len(X), "groups": len(set(G)),
                           "iou_in": round(float(np.median(ious)), 4),
                           "iou_holdout": round(float(np.median(out_ious)), 4) if out_ious else None}
            J = {"version": "studio-refit", "fitted": time.strftime("%Y-%m-%d %H:%M"),
                 "n": int(len(X)), "groups": sorted(set(G)), "lam": lam, "pad_min": 0.03,
                 "features": ["bias"] + [f"f{i+1}" for i in range(13)] + ["prod"],
                 "coef_cx": coefs["cx"].tolist(), "coef_cy": coefs["cy"].tolist(),
                 "coef_log2w": coefs["log2w"].tolist(),
                 "iou_in": rep["crop"]["iou_in"],
                 "iou_holdout": rep["crop"]["iou_holdout"],
                 "note": "由 insect-studio 训练产出；bias 已折进系数"}
            cpath = os.path.join(self.out_dir, "crop_coef.json")
            json.dump(J, open(cpath, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            try:
                dst = models.adopt_trained("crop", cpath)
                rep["crop"]["adopted"] = dst
                self._say(f"已收进模型库：{dst}")
            except Exception as e:      # noqa: BLE001
                self._say(f"收进模型库失败（不影响报告）：{e}")
            self._say(f"裁切：n={len(X)} 样本内 {rep['crop']['iou_in']} "
                      f"留出 {rep['crop']['iou_holdout']}")
        except Exception as e:  # noqa: BLE001
            rep["crop"] = {"error": str(e)}
            self._say(f"裁切拟合失败：{e}")

        # --- 曝光（要求有 EV 真值；L_in/L_box 需要重测，这里用掩膜外接框近似不够，
        #     所以只有已存进 CSV 的 EV 用不上 —— 训练时无法反推 L_in/L_box，
        #     必须现场测。为不重复跑模型，曝光系数只在"已有 L_in/L_box 的旧表"上拟合。
        try:
            A, ev, gp = [], [], []
            for r in rows:
                try:
                    li, lb, e = float(r["L_in"]), float(r["L_box"]), float(r["EV"])
                except (TypeError, ValueError):
                    continue
                A.append([li, lb, 1.0]); ev.append(e); gp.append(r["group"])
            A = np.array(A); ev = np.array(ev); gp = np.array(gp)
            if len(A) >= 100:
                c = np.linalg.lstsq(A, ev, rcond=None)[0]
                pred = A @ c
                mae_in = float(np.mean(np.abs(ev - pred)))
                rng = np.random.RandomState(0)
                bl = sorted(set(gp)); rng.shuffle(bl)
                folds = [set(bl[i::5]) for i in range(5)]
                mae_out, r2_out = [], []
                for k in range(5):
                    te = np.array([g in folds[k] for g in gp]); tr = ~te
                    if tr.sum() < 50 or te.sum() < 10:
                        continue
                    ck = np.linalg.lstsq(A[tr], ev[tr], rcond=None)[0]
                    pk = A[te] @ ck
                    mae_out.append(float(np.mean(np.abs(ev[te] - pk))))
                    ss = float(((ev[te] - pk) ** 2).sum())
                    r2_out.append(1 - ss / max(float(((ev[te] - ev[te].mean()) ** 2).sum()), 1e-9))
                rep["exposure"] = {
                    "n": int(len(A)), "batches": len(set(gp)),
                    "b0": round(float(c[2]), 6), "b1": round(float(c[0]), 6),
                    "b2": round(float(c[1]), 6),
                    "mae_in": round(mae_in, 4),
                    "mae_holdout": round(float(np.median(mae_out)), 4) if mae_out else None,
                    "r2_holdout": round(float(np.median(r2_out)), 4) if r2_out else None,
                    "mae_const": round(float(np.mean(np.abs(ev - np.median(ev)))), 4)}
                import exposure_model as _em
                full = dict(_em._BASE)          # 以内置为底，只换三个系数与统计量
                full.update(version="studio-refit",
                            fitted=time.strftime("%Y-%m-%d %H:%M"),
                            b0=round(float(c[2]), 8), b1=round(float(c[0]), 8),
                            b2=round(float(c[1]), 8), n=int(len(A)),
                            batches=len(set(gp)),
                            mae_in=rep["exposure"]["mae_in"],
                            mae_holdout=rep["exposure"]["mae_holdout"],
                            r2_holdout=rep["exposure"]["r2_holdout"],
                            note="由 insect-studio 训练产出；口径与内置一致（同一测量函数）")
                epath = os.path.join(self.out_dir, "ev_coef.json")
                json.dump(full, open(epath, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=1)
                try:
                    rep["exposure"]["adopted"] = models.adopt_trained("ev", epath)
                    self._say(f"已收进模型库：{rep['exposure']['adopted']}")
                except Exception as e:      # noqa: BLE001
                    self._say(f"收进模型库失败（不影响报告）：{e}")
                self._say(f"曝光：n={len(A)} 留出 MAE {rep['exposure']['mae_holdout']} 档")
            else:
                rep["exposure"] = {"note": f"有效样本只有 {len(A)}，少于 100，未拟合"}
        except Exception as e:  # noqa: BLE001
            rep["exposure"] = {"error": str(e)}
            self._say(f"曝光拟合失败：{e}")

        # --- 白平衡
        wb = []
        for r in rows:
            try:
                wb.append((r["group"], float(r["T"]), float(r["Tint"])))
            except (TypeError, ValueError):
                continue
        if wb:
            Ts = [x[1] for x in wb]
            by = {}
            for g, T, ti in wb:
                by.setdefault(g, []).append((T, ti))
            table = []
            for g, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
                table.append({"batch": g, "T": round(statistics.median([a for a, _ in v])),
                              "Tint": round(statistics.median([b for _, b in v]), 1),
                              "n": len(v)})
            with open(os.path.join(self.out_dir, "wb_table.csv"), "w", newline="",
                      encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=["batch", "T", "Tint", "n"])
                w.writeheader()
                w.writerows(table)
            rep["wb"] = {"n": len(wb),
                         "T_median": round(statistics.median(Ts)),
                         "mae_const": round(float(np.mean(np.abs(np.array(Ts) - 5333))), 1),
                         "batches": len(by)}
            self._say(f"白平衡：n={len(wb)} T 中位 {rep['wb']['T_median']} "
                      f"常数 MAE {rep['wb']['mae_const']} K")

        rep["out_dir"] = self.out_dir
        with self.lock:
            self.report = rep
            self.progress = 100.0
        md = [f"# 训练报告 {time.strftime('%Y-%m-%d %H:%M')}", ""]
        for k, v in rep.items():
            md.append(f"## {k}")
            md.append("```")
            md.append(json.dumps(v, ensure_ascii=False, indent=1))
            md.append("```")
        open(os.path.join(self.out_dir, "report.md"), "w", encoding="utf-8").write("\n".join(md))
        self._say("完成")


CACHE_FILE = os.path.join(OUT_ROOT, "train_cache.json")


def _with_label(row, target, group, label):
    return dict(row, group=group, label_path=label,
                crop_l=target["CropLeft"], crop_t=target["CropTop"],
                crop_r=target["CropRight"], crop_b=target["CropBottom"],
                EV=target.get("Exposure2012", ""), T=target.get("Temperature", ""),
                Tint=target.get("Tint", ""))


def _mtime(p):
    try:
        return os.path.getmtime(p)
    except OSError:
        return 0.0


def _cache_key(p):
    return os.path.normcase(os.path.abspath(p))


def _load_cache():
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:      # noqa: BLE001
        return {}


def _save_cache(cache):
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        tmp = CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        os.replace(tmp, CACHE_FILE)
    except Exception:      # noqa: BLE001
        pass


def _box(t):
    cx, cy, w = t
    return (cx - w / 2, cy - w / 2, cx + w / 2, cy + w / 2)


def _top_batch(p):
    parts = [x for x in p.replace("/", "\\").split("\\") if x]
    # 期望形如 K:\照片\<批次>\...
    for i, seg in enumerate(parts):
        if seg == "照片" and i + 1 < len(parts):
            return parts[i + 1]
    return os.path.dirname(p)


def _group_of(path: str, root: str) -> str:
    """批次名 = 相对 root 的第一层目录；直接在 root 下就用 root 名。

    这样「多个训练目录」也能按批次分折，不会把不同场次混成一折。
    """
    try:
        rel = os.path.relpath(path, root)
    except ValueError:
        return _top_batch(path)
    if rel.startswith(".."):
        return _top_batch(path)
    head = rel.replace("/", "\\").split("\\")[0]
    if head in (".", "") or head == os.path.basename(rel):
        return _cache_key(root)
    return _cache_key(os.path.join(root, head))


_BURST = __import__("re").compile(r"(\d+)(?!.*\d)")


def _dedupe_burst(pairs, gap: int = 5):
    """同目录、编号差 ≤gap 视为同一只虫的连拍，只留第一张。"""
    out, last = [], {}
    for p, t in pairs:
        d = os.path.dirname(p)
        stem = os.path.splitext(os.path.basename(p))[0]
        m = _BURST.search(stem)
        num = int(m.group(1)) if m else None
        key = (d, stem[:len(stem) - len(m.group(1))] if m else stem)
        prev = last.get(key)
        if num is not None and prev is not None and 0 < num - prev <= gap:
            last[key] = num
            continue
        if num is not None:
            last[key] = num
        out.append((p, t))
    return out
