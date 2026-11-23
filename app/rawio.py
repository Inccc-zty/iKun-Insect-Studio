"""多厂家 RAW / 位图统一读取。

只解决三件事：
    1. 拿一张能看的全幅预览（PIL RGB）
    2. 拿光圈（锐化要用）
    3. 判断这是不是 RAW

RAW 优先走内嵌 JPEG 预览（快、且对 Z8 的 HE 压缩是唯一可行路径）；
缩略图太小的机型退到 rawpy.postprocess(half_size=True)；
postprocess 也失败的（Nikon HE）才报错。
"""
from __future__ import annotations

import io
import os
import struct

from PIL import Image

RAW_EXT = (".nef", ".nrw", ".dng", ".cr2", ".cr3", ".arw", ".srf", ".sr2",
           ".raf", ".orf", ".rw2", ".pef", ".srw", ".raw", ".rwl", ".3fr",
           ".erf", ".mef", ".mos", ".mrw", ".x3f", ".iiq")
IMG_EXT = (".jpg", ".jpeg", ".tif", ".tiff", ".png", ".bmp") + RAW_EXT

# 内嵌预览短边小于这个值就不用它（说明只是 160×120 那种缩略图）
MIN_PREVIEW = 1000

TAG_EXIF_IFD, TAG_FNUMBER, TAG_APERTURE = 0x8769, 0x829D, 0x9202
TAG_FOCAL, TAG_ISO, TAG_EXPOSURE, TAG_LENS, TAG_MODEL = 0x920A, 0x8827, 0x829A, 0xA434, 0x0110
TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8, 13: 4}


def is_raw(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in RAW_EXT


def is_image(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in IMG_EXT


# ---------------------------------------------------------------- 预览
def preview_pil(path: str) -> Image.Image:
    """统一入口：返回 RGB 预览（尺寸不保证，但纵横比与原始一致）。"""
    if not is_raw(path):
        im = Image.open(path)
        im = im.convert("RGB")
        return im

    import rawpy
    with rawpy.imread(path) as r:
        try:
            th = r.extract_thumb()
            if th.format == rawpy.ThumbFormat.JPEG:
                im = Image.open(io.BytesIO(bytes(th.data))).convert("RGB")
                if min(im.size) >= MIN_PREVIEW:
                    return im
        except Exception:  # noqa: BLE001
            pass
        # 退路：解 Bayer（半尺寸）。Nikon HE 会在这里抛 LibRawFileUnsupportedError
        rgb = r.postprocess(half_size=True, use_camera_wb=True, output_bps=8)
        return Image.fromarray(rgb)


def preview_thumb(path: str, long_side: int = 900) -> Image.Image:
    im = preview_pil(path)
    w, h = im.size
    if max(w, h) > long_side:
        k = long_side / max(w, h)
        im = im.resize((max(int(w * k), 1), max(int(h * k), 1)), Image.LANCZOS)
    return im


# ---------------------------------------------------------------- EXIF
def _ifd(buf, off):
    out = {}
    if off + 2 > len(buf):
        return out
    n = struct.unpack_from("<H", buf, off)[0]
    for i in range(n):
        p = off + 2 + 12 * i
        if p + 12 > len(buf):
            break
        tag, typ, cnt = struct.unpack_from("<HHI", buf, p)
        size = TYPE_SIZE.get(typ, 1) * cnt
        if size <= 4:
            raw = buf[p + 8:p + 8 + size]
        else:
            o = struct.unpack_from("<I", buf, p + 8)[0]
            raw = buf[o:o + size] if o < len(buf) else b""
        out[tag] = (typ, cnt, raw)
    return out


def _num(e):
    if e is None:
        return None
    typ, cnt, raw = e
    try:
        if typ in (5, 10):
            a, b = struct.unpack("<II" if typ == 5 else "<ii", raw[:8])
            return a / b if b else None
        if typ == 3:
            return float(struct.unpack("<H", raw[:2])[0])
        if typ == 4:
            return float(struct.unpack("<I", raw[:4])[0])
        if typ == 2:
            return raw.split(b"\x00")[0].decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return None
    return None


def format_shutter(t):
    """1/250 这种写法比 0.004 好读。"""
    try:
        t = float(t)
    except (TypeError, ValueError):
        return "—"
    if t <= 0:
        return "—"
    if t >= 1:
        return f"{t:g}s"
    return f"1/{round(1 / t)}"


def meta_text(ex: dict) -> str:
    """队列右侧的一行信息：f/8 · 1/250 · ISO 400。"""
    f = ex.get("fnumber")
    iso = ex.get("iso")
    fs = f"f/{float(f):g}" if f else "f/—"
    ss = format_shutter(ex.get("exposure_s"))
    is_ = f"ISO {int(iso)}" if iso else "ISO —"
    return f"{fs} · {ss} · {is_}"


def read_exif(path: str, head_bytes: int = 65536) -> dict:
    """返回 {fnumber, focal_mm, iso, exposure_s, lens, model}。

    RAW 直接解 TIFF 头（<1 ms）；位图用 PIL 的 getexif。
    """
    if not is_raw(path):
        out = {"fnumber": None, "focal_mm": None, "iso": None,
               "exposure_s": None, "lens": None, "model": None}
        try:
            im = Image.open(path)
            ex = im.getexif()
            fn = ex.get(0x829D)
            if fn is None:
                av = ex.get(0x9202)
                fn = 2 ** (av / 2) if av else None
            out.update(fnumber=round(float(fn), 2) if fn else None,
                       focal_mm=ex.get(0x920A), iso=ex.get(0x8827),
                       exposure_s=ex.get(0x829A), model=ex.get(0x0110))
        except Exception:  # noqa: BLE001
            pass
        return out

    try:
        with open(path, "rb") as f:
            buf = f.read(head_bytes)
        if buf[:2] not in (b"II", b"MM"):
            raise ValueError("not tiff")
        ifd0_off = struct.unpack_from("<I", buf, 4)[0]
        ifd0 = _ifd(buf, ifd0_off)
        exif = {}
        ent = ifd0.get(TAG_EXIF_IFD)
        if ent is not None and len(ent[2]) >= 4:
            off = struct.unpack_from("<I", ent[2], 0)[0]
            if 0 < off < len(buf):
                exif = _ifd(buf, off)
        n = _num(exif.get(TAG_FNUMBER))
        av = _num(exif.get(TAG_APERTURE))
        if n is None and av is not None:
            n = 2 ** (av / 2)
        return {"fnumber": round(n, 2) if n else None,
                "focal_mm": _num(exif.get(TAG_FOCAL)),
                "iso": _num(exif.get(TAG_ISO)),
                "exposure_s": _num(exif.get(TAG_EXPOSURE)),
                "lens": _num(exif.get(TAG_LENS)),
                "model": _num(ifd0.get(TAG_MODEL))}
    except Exception:  # noqa: BLE001
        return {"fnumber": None, "focal_mm": None, "iso": None,
                "exposure_s": None, "lens": None, "model": None}


def scan_image_dir(root: str, recursive: bool = True):
    """列出目录下所有可处理的图像（只看扩展名，不打开文件）。"""
    out = []
    if os.path.isfile(root):
        return [root] if is_image(root) else []
    if recursive:
        for dp, _dn, fn in os.walk(root):
            for f in fn:
                p = os.path.join(dp, f)
                if is_image(p):
                    out.append(p)
    else:
        for f in os.listdir(root):
            p = os.path.join(root, f)
            if os.path.isfile(p) and is_image(p):
                out.append(p)
    return sorted(out)
