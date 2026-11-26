"""掩膜 + 本体/附肢拆分 + 头部定位。全项目唯一链路。

    prev = nef_io.preview_pil(nef)                 # 8256×5504 内嵌预览
    out  = analyze(prev)                           # 一次前向，三处复用
    out['core'], out['full']                       # 全画幅归一化框 (l,t,r,b)
    out['head']                                    # 全画幅归一化点 (x,y) 或 None

关键约定
    * 掩膜在 S×S 网格上推理，坐标天然是「占全画幅的比例」，不需要任何映射。
    * core = 开运算后的躯干框；full = 掩膜外接框（含腿/触角/翅）。
    * 头部关键点以 core 框外扩 15% 为输入，输出仍是全画幅归一化。
"""
from __future__ import annotations

import os

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision
from PIL import Image
from torchvision import transforms

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CKPT = os.path.join(ROOT, "assets", "weights", "head_kp_v2.pth")

_CACHE = {}


# ---------------------------------------------------------------- 分割
def _seg_model(dev):
    if "seg" not in _CACHE:
        from transformers import AutoModelForImageSegmentation
        m = AutoModelForImageSegmentation.from_pretrained(
            "ZhengPeng7/BiRefNet", trust_remote_code=True).float().eval().to(dev)
        _CACHE["seg"] = m
    return _CACHE["seg"]


def _tf(size):
    return transforms.Compose([transforms.Resize((size, size)), transforms.ToTensor(),
                               transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])


def segment(prev: Image.Image, size: int = 768, dev: str = "cuda") -> np.ndarray:
    """整幅缩到 size×size 跑一次，返回 size×size uint8 掩膜。"""
    m = _seg_model(dev)
    inp = _tf(size)(prev).unsqueeze(0).to(dev)
    with torch.no_grad():
        o = m(inp)
    lg = o["logits"] if isinstance(o, dict) else (o[-1] if isinstance(o, (list, tuple)) else o)
    if isinstance(lg, (list, tuple)):
        lg = lg[-1]
    prob = lg.sigmoid()[0, 0].float().cpu().numpy()
    return (prob * 255).astype(np.uint8)


def _bbox(m):
    ys, xs = np.where(m > 0)
    if xs.size == 0:
        return None
    H, W = m.shape
    return (xs.min() / W, ys.min() / H, (xs.max() + 1) / W, (ys.max() + 1) / H)


def split_body_core(mask: np.ndarray, r_scale: float = 0.035, keep_largest: bool = True):
    """开运算拆本体 / 附肢。

    为什么是开运算：语义是「局部厚度 ≥ 2r 的部分」，正是形态学开运算的定义。
    重建（geodesic）会把连在身体上的腿全部并进 core，那是反的。
    """
    m = (mask > 0).astype(np.uint8)
    if m.sum() < 50:
        return None
    full_bbox = _bbox(m)
    if full_bbox is None:
        return None
    area = float(m.sum())
    r = max(1, int(round(r_scale * np.sqrt(area))))
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    core = cv2.morphologyEx(m, cv2.MORPH_OPEN, ker)
    if core.sum() == 0:
        for rr in (max(1, r // 2), 1):
            k2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * rr + 1, 2 * rr + 1))
            core = cv2.morphologyEx(m, cv2.MORPH_OPEN, k2)
            if core.sum() > 0:
                r = rr
                break
    if core.sum() == 0:
        core = m.copy()
    if keep_largest and core.sum() > 0:
        n, lab, stats, _ = cv2.connectedComponentsWithStats(core, 8)
        if n > 2:
            big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            main = (lab == big).astype(np.uint8)
            dist = cv2.distanceTransform(1 - main, cv2.DIST_L2, 5)
            for i in range(1, n):
                if i == big:
                    continue
                piece = (lab == i)
                if piece.sum() and dist[piece].min() <= 2 * r + 1:
                    main |= piece.astype(np.uint8)
            core = main
    return {"core_mask": core, "limb_mask": cv2.bitwise_and(m, cv2.bitwise_not(core)),
            "core_bbox": _bbox(core), "full_bbox": full_bbox, "r": int(r),
            "area_full": area, "area_core": float(core.sum())}


# ---------------------------------------------------------------- 头部
# 2026-11-17 实测（15 张 / 5 批次，另 120 张有标注样本复核）：
#   热力图 softmax 峰值 conf 只在 0.034–0.064 之间，中位 0.056。
#   原阈值 0.05 正好卡在分布中部，等于把约 1/3「其实预测对了」的头点丢掉，
#   用户看到的现象就是「很多照片没有头部」。
# 现在：conf 只做极低门槛（0.02，滤掉完全发散的图），
#       再加一条几何校验——头点必须落在身体框外扩 20% 之内。
HEAD_CONF_MIN = 0.02
HEAD_BOX_SLACK = 0.20


def head_inside(core, pt, slack: float = HEAD_BOX_SLACK) -> bool:
    """头点是否落在身体框（外扩 slack 倍）内。兜底明显跑飞的点。"""
    if pt is None:
        return False
    cl, ct, cr, cb = [float(v) for v in core]
    w, h = cr - cl, cb - ct
    return (cl - slack * w <= pt[0] <= cr + slack * w and
            ct - slack * h <= pt[1] <= cb + slack * h)


class KPNet(nn.Module):
    """ResNet50 骨干 + 双尺度融合 + 64×64 热力图。"""

    def __init__(self, pretrained=False):
        super().__init__()
        w = "IMAGENET1K_V2" if pretrained else None
        bb = torchvision.models.resnet50(weights=w)
        self.stem = nn.Sequential(bb.conv1, bb.bn1, bb.relu, bb.maxpool, bb.layer1, bb.layer2)
        self.l3, self.l4 = bb.layer3, bb.layer4
        self.p4 = nn.Conv2d(2048, 256, 1)
        self.p3 = nn.Conv2d(1024, 256, 1)
        self.head = nn.Sequential(
            nn.Conv2d(256, 128, 3, padding=1), nn.BatchNorm2d(128), nn.LeakyReLU(0.1),
            nn.Conv2d(128, 64, 3, padding=1), nn.BatchNorm2d(64), nn.LeakyReLU(0.1),
            nn.Conv2d(64, 1, 1))

    def forward(self, x):
        x = self.stem(x)
        f3 = self.l3(x)
        f4 = self.l4(f3)
        p4 = F.interpolate(self.p4(f4), size=f3.shape[-2:], mode="bilinear", align_corners=False)
        p = self.p3(f3) + p4
        p = F.interpolate(p, size=(64, 64), mode="bilinear", align_corners=False)
        return self.head(p).squeeze(1)


MEAN = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
STD = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)


def _kp_model(dev):
    if "kp" not in _CACHE:
        net = KPNet(pretrained=False)
        ck = torch.load(CKPT, map_location="cpu", weights_only=False)
        net.load_state_dict(ck["state_dict"])
        net.eval().to(dev)
        _CACHE["kp"] = net
    return _CACHE["kp"]


@torch.no_grad()
def head_point(prev: Image.Image, core, dev: str = "cuda", pad: float = 0.15,
               conf_min: float = 0.05):
    """core 框外扩 pad 裁 256×256 → 热力图 soft-argmax → 全幅归一化点。"""
    net = _kp_model(dev)
    W, H = prev.size
    cl, ct, cr, cb = core
    w, h = cr - cl, cb - ct
    if w <= 1e-4 or h <= 1e-4:
        return None, 0.0
    l, t = max(0.0, cl - w * pad), max(0.0, ct - h * pad)
    r, b = min(1.0, cr + w * pad), min(1.0, cb + h * pad)
    box = (int(l * W), int(t * H), max(int(r * W), int(l * W) + 2), max(int(b * H), int(t * H) + 2))
    chip = prev.crop(box).resize((256, 256), Image.BILINEAR)
    x = torch.from_numpy(np.array(chip)).permute(2, 0, 1).float().div(255).unsqueeze(0).to(dev)
    x = (x - MEAN.to(dev)) / STD.to(dev)
    logits = net(x)
    p = F.softmax(logits.view(1, -1), dim=1).view(1, 64, 64)
    ys = (torch.arange(64, device=dev).float() + 0.5) / 64
    u = float((p.sum(1) * ys).sum())
    v = float((p.sum(2) * ys).sum())
    conf = float(p.max())
    return ((l + u * (r - l)), (t + v * (b - t))), conf


# ---------------------------------------------------------------- 一次跑完
def _is_cuda_mem(e: BaseException) -> bool:
    """判断是不是「显存不够」这一类错误。

    除了标准 OOM，实测这台机器（GTX 1650 4 GB + 桌面占 1.5–3.6 GB）还会报两种：
      CUDA error: CUBLAS_STATUS_NOT_INITIALIZED   —— 上下文还没建起来就分配失败
      LibRawMemPoolOverflowError                  —— 连带系统内存也不够
    两种都按「资源不足」处理：降一档重试，仍失败就把话说清楚，别让每张都静默失败。
    """
    s = f"{type(e).__name__}: {e}".lower()
    return any(k in s for k in ("outofmemory", "out of memory", "cublas_status",
                                "cuda error", "mempoolexceeded", "mempooleoverflow"))


def analyze(prev: Image.Image, dev: str = "cuda", size: int = 768, want_head: bool = True,
            progress=None):
    """掩膜 + 拆框 + 头点。显存不够时自动降到一半重跑一次。

    为什么要降级而不是直接失败：GTX 1650 只有 4 GB，Windows 桌面常态吃 1.5–3.6 GB，
    同一份代码同一张图，桌面占用高时 768 会 OOM。降级到 384 后坐标仍是
    「占全画幅的比例」，几何定义不变，只是小虫那一档掩膜会糊一点。
    降级会在返回值里标 degraded=True，params.csv 的 note 也会带上。
    """
    used = size
    try:
        m = segment(prev, used, dev)
    except (RuntimeError, MemoryError) as e:
        if not _is_cuda_mem(e):
            raise
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001
            pass
        used = max(384, size // 2)
        m = segment(prev, used, dev)

    sp = split_body_core((m >= 128).astype(np.uint8), r_scale=0.035)
    if sp is None:
        return {"ok": False, "reason": "mask_empty", "mask": m, "size": used}

    # 进度回调：掩膜一出来就先给 UI 画第一帧（核心/全身框），
    # 头点算完再画第二帧。回调失败绝不能影响主流程。
    if progress is not None:
        try:
            progress("mask", m, sp["core_bbox"], sp["full_bbox"], None)
        except Exception:  # noqa: BLE001
            pass

    head, conf = (None, 0.0)
    if want_head:
        try:
            head, conf = head_point(prev, sp["core_bbox"], dev)
        except (RuntimeError, MemoryError) as e:
            if not _is_cuda_mem(e):
                raise
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:  # noqa: BLE001
                pass
            head, conf = None, 0.0
        if head is not None and (conf < HEAD_CONF_MIN
                                 or not head_inside(sp["core_bbox"], head)):
            head = None
        if progress is not None:
            try:
                progress("head", m, sp["core_bbox"], sp["full_bbox"], head)
            except Exception:  # noqa: BLE001
                pass
    return {"ok": True, "mask": m, "mask_size": used, "degraded": used != size,
            "core": sp["core_bbox"], "full": sp["full_bbox"],
            "core_mask": sp["core_mask"], "limb_mask": sp["limb_mask"],
            "head": head, "head_conf": conf, "r": sp["r"],
            "area_full": sp["area_full"] / float(used * used)}


def count_subjects(mask, ratio: float = 0.08) -> int:
    """最大连通域之外，还有几个面积超过主块 ratio 的主体。

    ratio=0.08 是经验值：同一只虫被触角/腿断开时，碎块通常远小于 8%；
    真出现第二只虫（交配对、两只并排）时，第二块一般 >8%。判错的代价可控：
    多判 → 关掉头部项（略保守）；漏判 → 头部项作用在两只虫的中点（框心会偏）。
    """
    m = (mask >= 128).astype(np.uint8)
    n, _lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    if n < 3:
        return 1
    areas = np.sort(stats[1:, cv2.CC_STAT_AREA])[::-1]
    if areas[0] <= 0:
        return 0
    return int(1 + np.sum(areas[1:] > ratio * areas[0]))
