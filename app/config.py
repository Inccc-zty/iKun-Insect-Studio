"""配置：一个 JSON 文件，改完立即生效（下次取任务时读）。"""
from __future__ import annotations

import json
import os

from .paths import app_root

ROOT = app_root()
CFG = os.path.join(ROOT, "data", "config.json")

DEFAULTS = {
    "mode": "both",           # both | crop | exposure
    "seg_size": 768,          # 512 省显存
    "device": "cuda",         # cuda | cpu
    "coef": "",               # 裁切系数：空 = 内置 105 项；否则填 data/models/crop/*.json
    "ev_coef": "",            # 曝光系数：空 = 内置；否则填 data/models/ev/*.json
    "wb_enable": False,       # 白平衡不再写（保留字段，默认关）
    "sharpen_enable": True,   # 是否写锐化
    "skip_if_xmp": False,     # 旧字段，保留兼容
    "xmp_policy": "protect",  # protect | skip_all | force（见 app/xmpio.py）
    "train_dirs": [],
    "train_src": "crop_only",  # 训练数据来源：xmp | crop_only（默认成品 JPG）
    "profile": "Camera Standard",
    "recursive": True,
    "preload": True,          # 启动后在后台把模型读进显存（省掉第一次点开始的 30–40 秒）
    "preview_enabled": True,  # UI 里的预览开关
    "preview_exposure": True, # 大图分屏显示「原图 | 按算出的 EV 调整后」
    "mask_cache": False,      # 同一张图重跑时复用上次的掩膜/框/头点（不改结果）
    "follow": True,           # 队列自动跟随正在处理的那张
    "head_fix": True,         # 用历史手动修正去微调头点（skill/scripts/head_fix.py）
    "backup": True,           # 覆盖旧 XMP 前备份
    "max_preview_side": 1000, # 叠加图长边（够面板显示，越小越快）
    "theme": "light",         # light | dark
    "lang": "zh",             # zh | en
    "_v": 0,                  # 配置版本，用于一次性迁移
}

# 当前配置版本：1 = 初版（深色默认） 2 = 浅色默认 + 中英切换
CFG_VER = 2


class Config:
    def __init__(self, path: str = CFG):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._d = dict(DEFAULTS)
        self._loaded = {}
        self.load()
        # 白平衡已停用：无论旧配置写的是什么，都强制关掉
        self._d["wb_enable"] = False
        # 旧配置里只有 skip_if_xmp，没有三档策略：勾过就继承成「全部跳过」
        if "xmp_policy" not in self._loaded and self._loaded.get("skip_if_xmp"):
            self._d["xmp_policy"] = "skip_all"
        if int(self._d.get("_v") or 0) < CFG_VER:
            # 一次性迁移：老配置里可能存着 dark，这里强制回到浅色默认，
            # 之后再记住用户自己的选择。
            self._d["theme"] = "light"
            self._d["lang"] = "zh"
            self._d["_v"] = CFG_VER
            self.save()

    def load(self):
        if os.path.exists(self.path):
            try:
                d = json.load(open(self.path, encoding="utf-8"))
                self._loaded = d
                self._d.update({k: v for k, v in d.items() if k in DEFAULTS})
            except Exception:  # noqa: BLE001
                pass
        return self._d

    def save(self):
        json.dump(self._d, open(self.path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)

    def get(self, k, default=None):
        return self._d.get(k, DEFAULTS.get(k, default))

    def update(self, **kw):
        for k, v in kw.items():
            if k in DEFAULTS:
                self._d[k] = v
        self.save()
        return self._d

    def as_dict(self):
        return dict(self._d)
