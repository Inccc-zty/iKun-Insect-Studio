# -*- coding: utf-8 -*-
"""掩膜一次，裁切与曝光各跑一条线。

    阶段 1  mask      NEF → 掩膜、core/full/head、L_in/L_box      （贵，跑一次）
    阶段 2a exposure  几何表 → EV + 白平衡 + 锐化                   （纯算术，毫秒级）
    阶段 2b crop      几何表 → 裁切框（v3 105 项）                  （纯算术，毫秒级）
    阶段 3  write     两条线的 CSV → XMP                            （合并写）

为什么能拆
    两条线唯一的交集是「掩膜给出的几何量」。掩膜一算完，它们就互不相干了：
    曝光只用 L_in / L_box；裁切只用 core / full / head / nsub。
    所以换 EV 系数不用重跑 GPU，换裁切公式也不用。

用法
    python stages.py mask     --dir "K:\\照片\\某目录" --cache ./_stage
    python stages.py exposure --cache ./_stage
    python stages.py crop     --cache ./_stage
    python stages.py write    --cache ./_stage --out ./_xmp
    python stages.py all      --dir ... --cache ./_stage --out ./_xmp
"""
from __future__ import annotations

import argparse
import csv
import os
import shutil
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import crop_v3
import exposure_model as expo
import mask_head
import nef_io
import wb_sharpen
import xmp_write

RAW_EXT = (".nef", ".nrw", ".dng", ".cr2", ".cr3", ".arw", ".raf", ".orf", ".rw2")

GEO_FIELDS = ["file", "batch", "sensor_w", "sensor_h", "mask_size",
              "core_l", "core_t", "core_r", "core_b",
              "full_l", "full_t", "full_r", "full_b",
              "head_x", "head_y", "head_ok", "nsub", "occupancy",
              "L_in", "L_box", "fnumber", "note"]


def list_raws(d, limit=0):
    fs = sorted(f for f in os.listdir(d) if f.lower().endswith(RAW_EXT))
    return fs[:limit] if limit else fs


def _f(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- 阶段 1
def stage_mask(args):
    cache = os.path.abspath(args.cache)
    mdir = os.path.join(cache, "mask")
    os.makedirs(mdir, exist_ok=True)
    batch = args.batch or os.path.basename(os.path.normpath(args.dir))

    dev = args.device
    if dev == "cuda":
        import torch
        dev = ("cuda" if torch.cuda.is_available()
               else "mps" if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available() else "cpu")

    files = list_raws(args.dir, args.limit)
    print(f"[mask] {args.dir}\n       {len(files)} 张  设备 {dev}  掩膜 {args.seg_size}px  → {cache}")
    rows, fail, t0 = [], 0, time.time()

    for i, f in enumerate(files, 1):
        p = os.path.join(args.dir, f)
        stem = os.path.splitext(f)[0]
        rec = {k: "" for k in GEO_FIELDS}
        rec.update(file=f, batch=batch)
        try:
            ex = nef_io.read_exif(p)
            prev = nef_io.preview_pil(p)
            ow, oh = nef_io.sensor_size(p)
            res = mask_head.analyze(prev, dev=dev, size=args.seg_size,
                                    want_head=not args.no_head)
            if not res.get("ok"):
                raise RuntimeError(res.get("reason", "mask_failed"))

            nsub = mask_head.count_subjects(res["mask"])
            head = res["head"] if nsub <= 1 else None
            core, full = res["core"], res["full"]

            me = expo.measure_pil(prev, res["mask"], full)
            if me["L_in"] is None or me["L_box"] is None:
                raise RuntimeError("亮度测量失败（掩膜或背景为空）")

            np.savez_compressed(
                os.path.join(mdir, stem + ".npz"),
                mask=(np.asarray(res["mask"]) >= 128).astype(np.uint8),
                mask_size=np.array(res["mask_size"]),
                core=np.array(core, float), full=np.array(full, float),
                head=np.array(head if head else [np.nan, np.nan], float))

            rec.update(
                sensor_w=ow, sensor_h=oh, mask_size=res["mask_size"],
                core_l=core[0], core_t=core[1], core_r=core[2], core_b=core[3],
                full_l=full[0], full_t=full[1], full_r=full[2], full_b=full[3],
                head_x="" if head is None else round(head[0], 5),
                head_y="" if head is None else round(head[1], 5),
                head_ok=int(head is not None), nsub=nsub,
                occupancy=round(me["occ"], 5),
                L_in=round(me["L_in"], 2), L_box=round(me["L_box"], 2),
                fnumber=ex["fnumber"] or "")
            print(f"  [{i:3d}/{len(files)}] {stem:<14s} L_in={me['L_in']:.0f} "
                  f"L_box={me['L_box']:.0f}  occ={me['occ']*100:.1f}%  "
                  f"head={'Y' if head else '-'}  nsub={nsub}")
        except Exception as e:  # noqa: BLE001
            fail += 1
            rec["note"] = f"{type(e).__name__}: {e}"
            print(f"  [{i:3d}/{len(files)}] {stem:<14s} 失败 {rec['note'][:80]}")
        rows.append(rec)

    gp = os.path.join(cache, "geometry.csv")
    with open(gp, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=GEO_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    dt = time.time() - t0
    print(f"[mask] 完成 {len(rows)-fail}/{len(rows)}  {dt:.0f}s（{dt/max(1,len(rows)):.2f}s/张）")
    print(f"       几何表 {gp}")
    print("       两条支线都从这里读，互不影响。")
    return gp


def read_geo(cache):
    gp = os.path.join(cache, "geometry.csv")
    if not os.path.exists(gp):
        raise SystemExit(f"找不到 {gp}，先跑 `stages.py mask`")
    all_rows = list(csv.DictReader(open(gp, encoding="utf-8-sig")))
    rows = [r for r in all_rows if not (r.get("note") or "").strip()]
    print(f"[geo] 读 {gp}：共 {len(all_rows)} 行，可用于计算 {len(rows)} 行")
    if not rows:
        raise SystemExit("几何表里没有成功记录")
    return gp, rows


# ---------------------------------------------------------------- 阶段 2a
def stage_exposure(args):
    cache = os.path.abspath(args.cache)
    gp, rows = read_geo(cache)

    out = []
    for r in rows:
        ev = expo.predict(float(r["L_in"]), float(r["L_box"]))
        wb = wb_sharpen.white_balance(r["batch"]) if args.wb else None
        sh = wb_sharpen.sharpness(_f(r["fnumber"]))
        out.append(dict(
            file=r["file"], batch=r["batch"],
            EV=round(ev["ev"], 4), EV_raw=round(ev["ev_raw"], 4),
            L_in=r["L_in"], L_box=r["L_box"], occupancy=r["occupancy"],
            saturated=int(ev["saturated"]),
            Temperature="" if wb is None else wb["T"],
            Tint="" if wb is None else wb["Tint"],
            wb_source="off" if wb is None else (wb["batch_matched"] or "default"),
            Sharpness="" if sh is None else sh,
            fnumber=r["fnumber"], note=ev["warn"]))

    p = os.path.join(cache, "exposure.csv")
    with open(p, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    evs = np.array([o["EV"] for o in out])
    print(f"[exposure] EV 中位 {np.median(evs):+.2f}  范围 {evs.min():+.2f}~{evs.max():+.2f}  "
          f"饱和警告 {sum(o['saturated'] for o in out)} 张")
    print(f"           → {p}")
    print("           想改某张 EV：直接改 exposure.csv 的 EV 列，再跑 write。")
    return p


# ---------------------------------------------------------------- 阶段 2b
def stage_crop(args):
    cache = os.path.abspath(args.cache)
    gp, rows = read_geo(cache)

    out = []
    for r in rows:
        core = (float(r["core_l"]), float(r["core_t"]), float(r["core_r"]), float(r["core_b"]))
        full = (float(r["full_l"]), float(r["full_t"]), float(r["full_r"]), float(r["full_b"]))
        head = None
        if r["head_ok"] == "1" and r["head_x"] not in ("", "nan"):
            head = (float(r["head_x"]), float(r["head_y"]))
        multi = int(_f(r["nsub"], 1) or 1) > 1
        cr = crop_v3.compute_crop(core, full, head, multi=multi,
                                  J=crop_v3.load(args.coef) if args.coef else None)
        lp = crop_v3.leg_pad_ok(cr["crop"], full, cr["pad_used"])
        out.append(dict(
            file=r["file"], batch=r["batch"],
            crop_l=round(cr["crop"][0], 5), crop_t=round(cr["crop"][1], 5),
            crop_r=round(cr["crop"][2], 5), crop_b=round(cr["crop"][3], 5),
            w=round(cr["w"], 4), cx=round(cr["cx"], 4), cy=round(cr["cy"], 4),
            canvas_limited=int(cr["canvas_limited"]), leg_pad_ok=int(lp),
            head_used=int(cr["head_used"]), multi=int(multi)))

    p = os.path.join(cache, "crop.csv")
    with open(p, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    ww = np.array([o["w"] for o in out])
    print(f"[crop] w 中位 {np.median(ww):.3f}  画布受限 {sum(o['canvas_limited'] for o in out)} 张  "
          f"用头 {sum(o['head_used'] for o in out)} 张  多主体 {sum(o['multi'] for o in out)} 张  "
          f"腿留白不达标 {sum(1 - o['leg_pad_ok'] for o in out)} 张")
    print(f"       → {p}")
    print("       想换公式：改 crop.csv 四个 crop_ 列，再跑 write。")
    return p


# ---------------------------------------------------------------- 阶段 3
def stage_write(args):
    cache = os.path.abspath(args.cache)
    ep = os.path.join(cache, "exposure.csv")
    cp = os.path.join(cache, "crop.csv")
    if not os.path.exists(ep) and not os.path.exists(cp):
        raise SystemExit("exposure.csv 和 crop.csv 都不存在，先跑那两条线")
    if args.apply and not args.dir:
        raise SystemExit("--apply 必须同时给 --dir（照片目录），否则会写到当前工作目录")

    ex = {r["file"]: r for r in csv.DictReader(open(ep, encoding="utf-8-sig"))} if os.path.exists(ep) else {}
    cr = {r["file"]: r for r in csv.DictReader(open(cp, encoding="utf-8-sig"))} if os.path.exists(cp) else {}
    files = sorted(set(ex) | set(cr))

    def _num(v):
        """exposure.csv 里空字符串 = 这一趟不写该字段。"""
        try:
            return None if v in (None, "", "nan", "None") else float(v)
        except (TypeError, ValueError):
            return None

    out = args.out or cache
    os.makedirs(out, exist_ok=True)
    n_e = n_c = 0
    for f in files:
        e, c = ex.get(f), cr.get(f)
        xml = xmp_write.build(
            f,
            None if c is None else (float(c["crop_l"]), float(c["crop_t"]),
                                    float(c["crop_r"]), float(c["crop_b"])),
            None if e is None else float(e["EV"]),
            None if e is None else _num(e.get("Temperature")),
            None if e is None else _num(e.get("Tint")),
            None if e is None else _num(e.get("Sharpness")))
        xmp_write.assert_minimal(xml)
        n_e += e is not None
        n_c += c is not None
        dst = (os.path.join(args.dir, os.path.splitext(f)[0] + ".xmp") if args.apply
               else os.path.join(out, os.path.splitext(f)[0] + ".xmp"))
        if args.apply and os.path.exists(dst):
            bak = os.path.join(args.dir, "_xmp_backup")
            os.makedirs(bak, exist_ok=True)
            shutil.copy2(dst, os.path.join(bak, os.path.basename(dst)))
        open(dst, "w", encoding="utf-8").write(xml)

    where = args.dir if args.apply else out
    print(f"[write] {len(files)} 个 XMP → {where}")
    print(f"        带曝光 {n_e} 张，带裁切 {n_c} 张"
          f"{'（原文件已备份到 _xmp_backup）' if args.apply else ''}")


# ---------------------------------------------------------------- 一键
def stage_all(args):
    args.cache = args.cache or os.path.join(args.out or "_stage", "_stage")
    stage_mask(args)
    stage_exposure(args)
    stage_crop(args)
    stage_write(args)


def main():
    ap = argparse.ArgumentParser(description="掩膜一次，裁切与曝光分两条线")
    ap.add_argument("stage", choices=["mask", "exposure", "crop", "write", "all"])
    ap.add_argument("--dir", default="", help="照片目录（mask / write --apply 用）")
    ap.add_argument("--cache", default="./_stage")
    ap.add_argument("--out", default="", help="XMP 输出目录（write 用）")
    ap.add_argument("--apply", action="store_true", help="直接写进照片目录（自动备份）")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--seg-size", type=int, default=768)
    ap.add_argument("--no-head", action="store_true")
    ap.add_argument("--batch", default="")
    ap.add_argument("--coef", default="", help="换一套裁切系数")
    ap.add_argument("--wb", action="store_true",
                    help="exposure 阶段把白平衡写进表；默认不写（沿用相机 As Shot）")
    a = ap.parse_args()

    if a.stage in ("mask", "all") and not a.dir:
        raise SystemExit("mask 阶段必须给 --dir")
    {"mask": stage_mask, "exposure": stage_exposure, "crop": stage_crop,
     "write": stage_write, "all": stage_all}[a.stage](a)


if __name__ == "__main__":
    main()
