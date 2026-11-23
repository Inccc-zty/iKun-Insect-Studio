"""NEF 读取：内嵌全幅预览 + 容器内 EXIF（不解 RAW）。

为什么不用 rawpy.postprocess()
    Z8 的 HE / HE* 压缩 RAW 走 intoPIX TicoRAW，LibRaw 0.22.x 直接抛
    LibRawFileUnsupportedError。但每张 NEF 内嵌一张全幅 JPEG 预览，
    extract_thumb() 只读这段数据（3–4 ms），全幅 8256×5504。
"""
from __future__ import annotations

import io
import struct

import cv2
import numpy as np
import rawpy
from PIL import Image

FLAG = {1: cv2.IMREAD_COLOR, 2: cv2.IMREAD_REDUCED_COLOR_2,
        4: cv2.IMREAD_REDUCED_COLOR_4, 8: cv2.IMREAD_REDUCED_COLOR_8}


def preview_jpeg(path: str) -> bytes:
    with rawpy.imread(path) as r:
        th = r.extract_thumb()
    if th.format != rawpy.ThumbFormat.JPEG:
        raise RuntimeError(f"{path}: 内嵌预览不是 JPEG")
    return bytes(th.data)


def read_bgr(path: str, div: int = 1) -> np.ndarray:
    buf = np.frombuffer(preview_jpeg(path), dtype=np.uint8)
    im = cv2.imdecode(buf, FLAG[div])
    if im is None:
        raise RuntimeError(f"{path}: 预览解码失败")
    return im


def preview_pil(path: str) -> Image.Image:
    """全幅 PIL 图（RGB），给 BiRefNet / 关键点用。"""
    return Image.open(io.BytesIO(preview_jpeg(path))).convert("RGB")


def sensor_size(path: str):
    """传感器有效像素（裁切 XMP 的分母用它，不是预览尺寸）。"""
    with rawpy.imread(path) as r:
        return int(r.sizes.crop_width), int(r.sizes.crop_height)


# ---------------------------------------------------------------- EXIF
TAG_EXIF_IFD, TAG_FNUMBER, TAG_APERTURE = 0x8769, 0x829D, 0x9202
TAG_FOCAL, TAG_ISO, TAG_EXPOSURE, TAG_LENS, TAG_MODEL = 0x920A, 0x8827, 0x829A, 0xA434, 0x0110
TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8}


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
        raw = buf[p + 8:p + 8 + size] if size <= 4 else buf[struct.unpack_from("<I", buf, p + 8)[0]:][:size]
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
    except Exception:
        return None
    return None


def read_exif(path: str, head_bytes: int = 262144) -> dict:
    with open(path, "rb") as f:
        buf = f.read(head_bytes)
    if buf[:2] not in (b"II", b"MM"):
        raise ValueError(f"{path}: 不是 TIFF/NEF")
    ifd0_off = struct.unpack_from("<I", buf, 4)[0]
    ifd0 = _ifd(buf, ifd0_off)
    exif = {}
    ent = ifd0.get(TAG_EXIF_IFD)
    if ent is not None and len(ent[2]) >= 4:
        # 直接从 entry 的值域取偏移。旧版用 list(ifd0).index() 反推物理位置，
        # 一旦 IFD 里有重复 tag 或解析中途 break，索引就错位（读到别的 IFD）。
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
