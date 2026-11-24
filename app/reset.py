"""把软件恢复到「第一次装好」的状态（测试用）。

只清 `<程序目录>/data` 里的东西：

    config.json        设置（模式/精度/主题/语言/模型选择…）
    sharpen_table.csv  改过的锐化分档
    head_fix.jsonl     头部修正记忆 + head_bias.json 线性模型
    models/            导入或训练出来的系数
    preview/           叠加图与定稿图缓存
    train_*/           训练报告与中间表
    crash.log

**绝不碰**：照片、照片旁边的 `.xmp`、`_ikun_xmp_log.jsonl`。
那些是你的作品和归属记录，不属于「软件状态」。

想模拟「别人第一次用」，光重置软件还不够——同一个目录里的 XMP 和账本还在，
软件会按「手做」跳过它们。把照片复制到一个新文件夹再拖进来才是干净的一次。
"""
from __future__ import annotations

import os
import shutil

from .paths import app_root, skill_dir


def data_dir() -> str:
    return os.path.join(app_root(), "data")


def inventory():
    """清点 data 目录：删之前给用户看清单用。"""
    d = data_dir()
    items = []
    if os.path.isdir(d):
        for name in sorted(os.listdir(d)):
            p = os.path.join(d, name)
            try:
                if os.path.isdir(p):
                    files = size = 0
                    for dp, _dn, fn in os.walk(p):
                        for f in fn:
                            files += 1
                            try:
                                size += os.path.getsize(os.path.join(dp, f))
                            except OSError:
                                pass
                else:
                    files, size = 1, os.path.getsize(p)
            except OSError:
                continue
            items.append({"name": name, "files": files, "bytes": size})
    return {"dir": d, "items": items,
            "files": sum(i["files"] for i in items),
            "bytes": sum(i["bytes"] for i in items)}


KEEP_ON_RESET = {"models"}     # 用户训练/导入的系数：重置也不许删


def wipe(keep_models: bool = True):
    """删掉 data 下的内容，并把只读的默认文件放回去。返回清点结果。

    keep_models=True（默认）会**保留 models/**——那是用户自己训练或导入的资产，
    升级、重置、清理都不应该动它。只有 wipe(keep_models=False) 才真的清空。
    """
    inv = inventory()
    d = data_dir()
    if os.path.isdir(d):
        for name in os.listdir(d):
            if keep_models and name in KEEP_ON_RESET:
                continue
            p = os.path.join(d, name)
            try:
                if os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    os.remove(p)
            except OSError:
                pass          # 有文件被占用就跳过，不阻断
    restore()
    return inv


def restore():
    """把随包带的默认文件放回 data/（目前只有锐化分档表）。"""
    src = os.path.join(skill_dir(), "assets", "data", "sharpen_table.csv")
    dst = os.path.join(data_dir(), "sharpen_table.csv")
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.exists(dst) and os.path.exists(src):
            shutil.copy2(src, dst)
        os.makedirs(os.path.join(data_dir(), "preview", "cache"), exist_ok=True)
    except OSError:
        pass
