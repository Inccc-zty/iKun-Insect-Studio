# -*- coding: utf-8 -*-
"""一条命令：NEF 目录 → XMP（裁切 v3 / 曝光双参数 / 白平衡常数 / 按光圈锐化）。

    # 空跑：只算参数，不动照片
    python pipeline.py --dir "K:\\照片\\2026.9.9 颐和园灯诱" --out O:\\ai修图\\_xmp

    # 抽 5 张出叠加检查图
    python pipeline.py --dir ... --out ... --limit 5 --sheet

    # 确认后写回照片目录（旧 XMP 自动备份到 _xmp_backup/）
    python pipeline.py --dir ... --apply

**掩膜只算一次**：core / full / head 同时供裁切与曝光使用，不各跑一遍 BiRefNet。
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

FIELDS = ["file", "batch", "ev", "ev_raw", "L_in", "L_box", "occ", "saturated",
          "T", "tint", "wb_source", "sharp", "fnumber",
          "cw", "cx", "cy", "canvas_limited", "leg_pad_ok",
          "head", "nsub", "crop", "note"]


def list_raws(d, limit=0):
    fs = sorted(f for f in os.listdir(d) if f.lower().endswith(RAW_EXT))
    return fs[:limit] if limit else fs


def _small_bgr(prev, long_side=900):
    """把全幅预览先缩到长边 900 再转 BGR。

    曝光只取亮度分位，长边 900 足够（p95 由几万像素决定，缩略不改变它）。
    不缩的话每张要多占 136 MB×2，本机 16 GB 内存 + 桌面占用时会把跑批拖崩。
    """
    w, h = prev.size
    if max(w, h) > long_side:
        k = long_side / max(w, h)
        prev = prev.resize((max(int(w * k), 1), max(int(h * k), 1)))
    return cv2.cvtColor(np.asarray(prev), cv2.COLOR_RGB2BGR)


def draw_sheet(prev, mask, core, full, crop, head, path, W=1400):
    im = _small_bgr(prev, long_side=W)
    H2, W2 = im.shape[:2]

    # 掩膜：半透明红 + 细轮廓（与 Insect Studio 保持一致）
    m = cv2.resize(mask, (W2, H2), interpolation=cv2.INTER_NEAREST)
    sel = m >= 128
    if sel.any():
        ov = im.copy()
        ov[sel] = (235, 48, 48)
        im = cv2.addWeighted(ov, 0.30, im, 0.70, 0)
        cnts, _ = cv2.findContours(sel.astype(np.uint8), cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(im, cnts, -1, (245, 60, 60), 1, cv2.LINE_AA)

    def box(b, color, th=3, label=""):
        l, t, r, bo = [int(v * s) for v, s in zip(b, (W2, H2, W2, H2))]
        cv2.rectangle(im, (l, t), (r, bo), color, th)
        if label:
            cv2.putText(im, label, (l + 6, max(22, t + 22)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)

    box(full, (0, 165, 255), 2, "full")      # 橙：整体框
    box(core, (255, 150, 40), 2, "core")     # 蓝：身体框
    box(crop, (90, 220, 90), 4, "crop")      # 绿：裁切框
    im = np.ascontiguousarray(im)
    if head:
        hx, hy = int(head[0] * W2), int(head[1] * H2)
        cv2.circle(im, (hx, hy), 10, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.circle(im, (hx, hy), 3, (255, 255, 255), -1, cv2.LINE_AA)
    ok, buf = cv2.imencode(".jpg", im, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if ok:
        buf.tofile(path)


def run_one(p, stem, batch, args, dev):
    """单张：掩膜一次 → 四项参数 → XMP。返回 dict（失败时 note 非空）。"""
    rec = {"file": os.path.basename(p), "batch": batch}
    ex = nef_io.read_exif(p)
    prev = nef_io.preview_pil(p)
    ow, oh = nef_io.sensor_size(p)

    res = mask_head.analyze(prev, dev=dev, size=args.seg_size, want_head=not args.no_head)
    if not res.get("ok"):
        raise RuntimeError(res.get("reason", "mask_failed"))

    nsub = mask_head.count_subjects(res["mask"])
    head = res["head"] if nsub <= 1 else None
    core, full = res["core"], res["full"]

    # 曝光：同一份掩膜，只测两个亮度分位（先缩图再转 BGR，省内存）
    me = expo.measure_pil(prev, res["mask"], full)
    if me["L_in"] is None or me["L_box"] is None:
        raise RuntimeError("亮度测量失败（掩膜或背景为空）")
    ev = expo.predict(me["L_in"], me["L_box"])

    # 裁切：v3 105 项，多主体强制关头（规则 12）
    cr = crop_v3.compute_crop(core, full, head, multi=(nsub > 1),
                              J=crop_v3.load(args.coef) if args.coef else None)

    # 白平衡默认不写：用户 2026-11-16 定「这部分先不管」，XMP 沿用相机 As Shot。
    # 要恢复旧行为加 --wb。标定数据与 14 条例外仍在 assets/data/wb_table.csv。
    wb = wb_sharpen.white_balance(batch) if args.wb else None
    sh = wb_sharpen.sharpness(ex["fnumber"])

    xml = xmp_write.build(os.path.basename(p), cr["crop"], ev["ev"],
                          None if wb is None else wb["T"],
                          None if wb is None else wb["Tint"], sh)
    xmp_write.assert_minimal(xml)          # 不该出现的字段一个都不许有

    if args.apply:
        xp = os.path.join(args.dir, stem + ".xmp")
        if os.path.exists(xp):
            bak = os.path.join(args.dir, "_xmp_backup")
            os.makedirs(bak, exist_ok=True)
            shutil.copy2(xp, os.path.join(bak, stem + ".xmp"))
        open(xp, "w", encoding="utf-8").write(xml)
    else:
        open(os.path.join(args.out_dir, stem + ".xmp"), "w", encoding="utf-8").write(xml)

    if args.sheet:
        draw_sheet(prev, res["mask"], core, full, cr["crop"], head,
                   os.path.join(args.out_dir, stem + "_check.jpg"))

    lp = crop_v3.leg_pad_ok(cr["crop"], full, cr["pad_used"])
    rec.update(ev=ev["ev"], ev_raw=ev["ev_raw"], L_in=me["L_in"], L_box=me["L_box"],
               occ=me["occ"], saturated=int(ev["saturated"]),
               T="" if wb is None else wb["T"],
               tint="" if wb is None else wb["Tint"],
               wb_source="off" if wb is None else (wb["batch_matched"] or "default"),
               sharp="" if sh is None else sh,
               fnumber=ex["fnumber"] or "",
               cw=round(cr["w"], 4), cx=round(cr["cx"], 4), cy=round(cr["cy"], 4),
               canvas_limited=int(cr["canvas_limited"]), leg_pad_ok=int(lp),
               head=int(head is not None), nsub=nsub,
               crop=[round(v, 4) for v in cr["crop"]],
               note="；".join(x for x in (ev["warn"], wb["warn"] if wb else "",
                                          "掩膜降级到 %d（显存不足）" % res["mask_size"]
                                          if res.get("degraded") else "") if x))
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--apply", action="store_true",
                    help="写进照片目录（旧 XMP 自动备份到 _xmp_backup）")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--seg-size", type=int, default=768)
    ap.add_argument("--no-head", action="store_true")
    ap.add_argument("--sheet", action="store_true", help="输出叠加检查图")
    ap.add_argument("--batch", default="", help="白平衡例外表的批次名，默认取目录名")
    ap.add_argument("--wb", action="store_true",
                    help="把白平衡常数（+批次例外）写进 XMP。默认不写，沿用相机 As Shot")
    ap.add_argument("--coef", default="", help="换一套裁切系数（默认 assets/data/crop_coef_v3.json）")
    ap.add_argument("--csv", default="")
    args = ap.parse_args()

    dev = args.device
    if dev == "cuda":
        import torch
        dev = ("cuda" if torch.cuda.is_available()
               else "mps" if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available() else "cpu")

    args.out_dir = args.out or os.path.dirname(os.path.abspath(args.dir))
    os.makedirs(args.out_dir, exist_ok=True)
    batch = args.batch or os.path.basename(os.path.normpath(args.dir))
    wb = wb_sharpen.white_balance(batch) if args.wb else None

    files = list_raws(args.dir, args.limit)
    if wb is None:
        wb_line = "白平衡不写（沿用相机 As Shot）"
    else:
        wb_line = (f"{wb['T']}K / Tint {wb['Tint']:+.0f}"
                   f"{'（例外表：' + wb['batch_matched'] + '）' if wb['batch_matched'] else '（默认常数）'}")
    print(f"目录 {args.dir}\n{len(files)} 张  批次「{batch}」→ {wb_line}")
    print(f"输出 {'照片目录（apply）' if args.apply else args.out_dir}  设备 {dev}  "
          f"裁切 v3 / 曝光双参数 / 锐化按光圈\n")

    rows, fail, t0 = [], 0, time.time()
    last_err, consec = "", 0
    for i, f in enumerate(files, 1):
        p = os.path.join(args.dir, f)
        stem = os.path.splitext(f)[0]
        try:
            rec = run_one(p, stem, batch, args, dev)
            consec = 0
            print(f"  [{i:3d}/{len(files)}] {stem:<14s} f/{rec['fnumber'] or '?'}  "
                  f"EV{rec['ev']:+.2f}  L_in={rec['L_in']:.0f} L_box={rec['L_box']:.0f}  "
                  f"w={rec['cw']:.3f}  head={'Y' if rec['head'] else '-'}"
                  f"{'  锐化' + str(rec['sharp']) if rec['sharp'] != '' else ''}"
                  f"{'  ⚠饱和' if rec['saturated'] else ''}"
                  f"{'  ⚠画布受限' if rec['canvas_limited'] else ''}")
        except Exception as e:  # noqa: BLE001
            fail += 1
            rec = {"file": f, "batch": batch, "note": f"{type(e).__name__}: {e}"}
            print(f"  [{i:3d}/{len(files)}] {stem:<14s} 失败 {rec['note'][:80]}")
            msg = rec["note"]
            if any(k in msg.lower() for k in ("cuda", "memory", "mempo")):
                consec = consec + 1 if msg[:40] == last_err else 1
                last_err = msg[:40]
                if consec >= 3:
                    print("\n连续 3 张同一资源错误，继续跑只会全部失败。先停下来。")
                    print("  本机现状：GTX 1650 4 GB，Windows 桌面常态占 1.5–3.6 GB。")
                    print("  处理办法（按代价从低到高）：")
                    print("    1) 关掉浏览器/多余窗口，让显存可用 >2.5 GB，再跑 768；")
                    print("    2) python pipeline.py ... --seg-size 512   （掩膜略糊，IoU 约低 0.7 个点）；")
                    print("    3) python pipeline.py ... --device cpu     （慢 10 倍，但一定能跑）。")
                    print("  已成功的 {0} 张已写进 CSV。".format(len(rows) - fail))
                    rows.append(rec)
                    break
        rows.append(rec)

    cp = args.csv or os.path.join(args.out_dir, "params.csv")
    with open(cp, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    ok = [r for r in rows if r.get("ev") is not None]
    dt = time.time() - t0
    print(f"\n完成 {len(rows) - fail}/{len(rows)}   {dt:.0f}s（{dt / max(1, len(rows)):.2f}s/张）")
    if ok:
        evs = np.array([r["ev"] for r in ok])
        print(f"EV 中位 {np.median(evs):+.2f}  范围 {evs.min():+.2f}~{evs.max():+.2f}  "
              f"饱和 {sum(r['saturated'] for r in ok)} 张  "
              f"画布受限 {sum(r['canvas_limited'] for r in ok)} 张  "
              f"腿留白不达标 {sum(1 - r['leg_pad_ok'] for r in ok)} 张")
        undef = sum(1 for r in ok if r["wb_source"] == "default")
        if undef:
            print(f"白平衡走默认常数 {undef} 张（例外表未命中，见 params.csv 的 wb_source）")
    print(f"参数表 {cp}")
    if args.apply:
        print(f"XMP 已写入 {args.dir}，原文件备份在 _xmp_backup/")
    else:
        print("dry-run：未改动照片目录")


if __name__ == "__main__":
    main()
