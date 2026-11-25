"""Recover an axis-aligned crop from a full frame and its JPEG export."""
import os

import cv2
import numpy as np
from PIL import Image, ImageOps


BOUNDS = ("CropLeft", "CropTop", "CropRight", "CropBottom")


def is_jpeg(path):
    return os.path.splitext(path)[1].lower() in (".jpg", ".jpeg")


def match_export(export, export_root, original_root, rawio):
    relative = os.path.relpath(export, export_root)
    if relative == os.pardir or relative.startswith(os.pardir + os.sep):
        return None, None
    folder = os.path.join(original_root, os.path.dirname(relative))
    if not os.path.isdir(folder):
        return None, None
    stem = os.path.normcase(os.path.splitext(os.path.basename(relative))[0])
    matches = []
    for candidate in rawio.scan_image_dir(folder, False):
        if os.path.normcase(os.path.splitext(os.path.basename(candidate))[0]) != stem:
            continue
        if os.path.samefile(candidate, export):
            continue
        try:
            bounds = recover_crop(rawio.preview_pil(candidate), export)
        except Exception:      # 坏 RAW / 读不了的文件，跳过这一个候选
            continue
        if bounds is not None:
            matches.append((candidate, dict(zip(BOUNDS, bounds), HasCrop=True)))
    return matches[0] if len(matches) == 1 else (None, None)


def _features(image, detector):
    image = image.copy()
    image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
    pixels = np.asarray(image.convert("L"))
    points, descriptors = detector.detectAndCompute(pixels, None)
    return points, descriptors, image.size


def recover_crop(original, export_path):
    """Return normalized bounds, or None when correspondence is ambiguous."""
    with Image.open(export_path) as image:
        exported = ImageOps.exif_transpose(image)
    detector = cv2.SIFT_create(nfeatures=3500)
    source, sd, (sw, sh) = _features(original, detector)
    target, td, (tw, th) = _features(exported, detector)
    if sd is None or td is None or min(len(sd), len(td)) < 20:
        return None
    matcher = cv2.BFMatcher()
    forward = {a.queryIdx: a.trainIdx for a, b in matcher.knnMatch(td, sd, k=2)
               if a.distance < 0.72 * b.distance}
    reverse = {a.queryIdx: a.trainIdx for a, b in matcher.knnMatch(sd, td, k=2)
               if a.distance < 0.72 * b.distance}
    pairs = [(t, s) for t, s in forward.items() if reverse.get(s) == t]
    if len(pairs) < 20:
        return None
    dst = np.float32([target[t].pt for t, _ in pairs])
    src = np.float32([source[s].pt for _, s in pairs])
    affine, inliers = cv2.estimateAffine2D(dst, src, ransacReprojThreshold=2.5)
    if affine is None or inliers is None:
        return None
    keep = inliers.ravel().astype(bool)
    if keep.sum() < 20 or keep.mean() < 0.75:
        return None
    if np.any(np.ptp(dst[keep], axis=0) < np.array([tw, th]) * 0.30):
        return None
    x, y = affine[0, 0], affine[1, 1]
    if min(x, y) <= 0 or abs(x / y - 1) > 0.025:
        return None
    if max(abs(affine[0, 1]), abs(affine[1, 0])) > 0.005 * min(x, y):
        return None
    left, top = affine[:, 2]
    bounds = np.array([left / sw, top / sh, (left + x * tw) / sw, (top + y * th) / sh])
    if bounds.min() < -0.004 or bounds.max() > 1.004:
        return None
    return tuple(np.clip(bounds, 0, 1).tolist())
