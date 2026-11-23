"""把一次跑批的结果拼成「一张图」—— 6 张一排的核对版式。

用户要的：横向 6 张、带框和头点、最后压成不太大的 JPG，一次导完。
这里只做排版：图是在处理时画好的叠加图（data/preview/cache/*.jpg），
不重跑模型、不重新解码 RAW，所以导出 500 张也只要几秒。

排版
    白底，6 列；每格 = 图（等比塞进 4:3 框）+ 一行说明（文件名 · EV · 锐化）
    顶上一行标题（时间 / 张数 / 模式）
    超过 CHUNK 张自动分文件：拼版_01.jpg、拼版_02.jpg …（单张太高一是不好传，
    二是 JPEG 长边有上限）
"""
from __future__ import annotations

import math
import os
import time

from PIL import Image, ImageDraw, ImageFont

COLS = 6
CELL_W = 360
PAD = 20
GUT = 10
CAP_H = 26
CHUNK = 120
QUALITY = 80

_BG = (255, 255, 255)
_LINE = (222, 232, 227)
_TEXT = (38, 50, 45)
_DIM = (110, 124, 118)
_ACC = (47, 125, 92)

_FONT_CACHE = {}


def _font(size, bold=False):
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    cands = (["C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyhbd.ttf",
              "C:/Windows/Fonts/segoeuib.ttf"] if bold else
             ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyh.ttf",
              "C:/Windows/Fonts/segoeui.ttf"])
    f = None
    for p in cands:
        if os.path.exists(p):
            try:
                f = ImageFont.truetype(p, size)
                break
            except OSError:
                continue
    if f is None:
        f = ImageFont.load_default()
    _FONT_CACHE[key] = f
    return f


def _elide(draw, text, font, max_w):
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text + "…"


def _caption(it):
    bits = [os.path.basename(it.get("path") or "")]
    ev = it.get("ev")
    if isinstance(ev, (int, float)):
        bits.append(f"EV {ev:+.2f}")
    sh = it.get("sharp")
    if sh is not None:
        bits.append(f"锐 {sh}")
    return bits


def build_sheet(items, out_path, cols=COLS, cell_w=CELL_W, quality=QUALITY,
                title="", on_progress=None, lang="zh"):
    """把 items 排成图，写到 out_path（不带分卷）或 out_01/02…（分卷）。

    没有图的（失败、或没生成定稿图）也占一格，画成灰底 + 失败标记，
    保证「这一批处理了多少张，版上就有多少格」，不会悄悄少人。

    返回实际写出的文件列表。
    """
    if not items:
        raise RuntimeError("没有可拼版的图")

    img_w = cell_w
    img_h = int(round(cell_w * 0.72))
    cell_h = img_h + CAP_H
    f_cap = _font(13)
    f_name = _font(14)
    f_title = _font(19, bold=True)

    groups = [items[i:i + CHUNK] for i in range(0, len(items), CHUNK)] \
        if len(items) > CHUNK else [items]
    base, ext = os.path.splitext(out_path)
    out_paths = []

    done = 0
    total = len(items)
    for gi, group in enumerate(groups):
        rows = int(math.ceil(len(group) / cols))
        w = PAD * 2 + cols * cell_w + (cols - 1) * GUT
        head = 54
        h = head + PAD + rows * cell_h + (rows - 1) * GUT + PAD
        sheet = Image.new("RGB", (w, h), _BG)
        d = ImageDraw.Draw(sheet)

        # 标题
        t = title or time.strftime("iKun Insect Studio · %Y-%m-%d %H:%M")
        if len(groups) > 1:
            t += f"    （{gi + 1}/{len(groups)}）"
        d.text((PAD, 16), t, font=f_title, fill=_TEXT)
        sub = f"{total} 张 · 每行 {cols} 张"
        d.text((w - PAD - d.textlength(sub, font=f_cap), 23), sub, font=f_cap, fill=_ACC)
        d.line([(PAD, head - 6), (w - PAD, head - 6)], fill=_LINE, width=1)

        for k, it in enumerate(group):
            r, c = divmod(k, cols)
            x = PAD + c * (cell_w + GUT)
            y = head + PAD + r * (cell_h + GUT)
            im = None
            fp = it.get("_file") or ""
            if fp and os.path.exists(fp):
                try:
                    im = Image.open(fp).convert("RGB")
                except Exception:      # noqa: BLE001
                    im = None
            if im is not None:
                # 等比塞进 (cell_w, img_h)，不足补白
                s = min(cell_w / im.width, img_h / im.height)
                nw, nh = max(int(im.width * s), 1), max(int(im.height * s), 1)
                im = im.resize((nw, nh), Image.BOX)
                ox = x + (cell_w - nw) // 2
                oy = y + (img_h - nh) // 2
                sheet.paste(im, (ox, oy))
                d.rectangle([x, y, x + cell_w - 1, y + img_h - 1], outline=_LINE, width=1)
            else:
                bad = bool(it.get("error"))
                d.rectangle([x, y, x + cell_w - 1, y + img_h - 1],
                            fill=(250, 240, 240) if bad else (244, 246, 245),
                            outline=(226, 150, 150) if bad else _LINE, width=1)
                msg = ("失败" if lang == "zh" else "FAILED") if bad else \
                      ("无预览" if lang == "zh" else "NO IMAGE")
                col = (176, 60, 66) if bad else (150, 160, 155)
                tw = d.textlength(msg, font=f_title)
                d.text((x + (cell_w - tw) / 2, y + img_h / 2 - 14), msg,
                       font=f_title, fill=col)

            # 说明行：文件名靠左，EV/锐化靠右
            cy = y + img_h + 5
            bits = _caption(it)
            if it.get("error"):
                sh = it.get("sharp")
                right = (("失败" if lang == "zh" else "failed") +
                         (f" · 锐 {sh}" if lang == "zh" and sh is not None
                          else f" · sharp {sh}" if sh is not None else ""))
            else:
                right = "   ".join(bits[1:])
            rw = d.textlength(right, font=f_cap)
            name = _elide(d, bits[0], f_name, cell_w - rw - 12)
            d.text((x + 2, cy), name, font=f_name, fill=_TEXT)
            if right:
                d.text((x + cell_w - rw - 2, cy + 1), right, font=f_cap, fill=_DIM)

            done += 1
            if on_progress and done % 10 == 0:
                on_progress(done, total)

        if len(groups) == 1:
            fp = out_path
        else:
            fp = f"{base}_{gi + 1:02d}{ext or '.jpg'}"
        sheet.save(fp, "JPEG", quality=quality, optimize=True, progressive=True)
        out_paths.append(fp)

    if on_progress:
        on_progress(total, total)
    return out_paths
