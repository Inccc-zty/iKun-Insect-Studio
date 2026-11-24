"""主窗口：拖入队列 + 实时预览 + 结果缩略图墙 + 训练页。

视觉（2026-11-17 用户指定）
    * 默认浅色，右上角可切深色，选择会记住
    * 右上角可切中/英，选择会记住
    * 配色取那套「薄荷绿 + 珊瑚红」色系
    * 队列每行两行：上行文件名 + 光圈/快门/ISO，下行结果数字 + 状态
    * 右下角不再是表格，而是这一批结果的缩略图墙（像 Lightroom 的网格），
      点一下就等于点左边那一行；上方一行只显示「当前这张」的数字
    * 一键导出拼版 JPG（6 张一排，带框和头点）

标记配色与 engine._draw 一一对应。

按钮尺寸（2026-11-17）
    QSS 的 padding 和 setFixedHeight 一起用会把文字压掉一半（已经出现过两次）。
    所以这里所有小按钮统一走 _mini()：竖向 padding 归零 + 只给最小高度，
    文字宽度由字体度量算出来，不再写死。切语言后重新量一遍。
"""
from __future__ import annotations

import os
import time

from PySide6.QtCore import (Qt, QTimer, Signal, QRect, QRectF, QPointF, QSize, QThread,
                            QPropertyAnimation, QEasingCurve, QAbstractAnimation)
from PySide6.QtGui import (QPixmap, QFont, QColor, QImage, QIcon, QPainter,
                           QPen, QRegion)
from PySide6.QtWidgets import (
    QSizePolicy, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QListWidget, QListWidgetItem, QProgressBar, QSplitter,
    QTabWidget, QLineEdit, QFileDialog, QMessageBox, QGroupBox, QGridLayout, QScrollArea,
    QCheckBox, QTextEdit, QHeaderView, QFrame, QToolButton,
    QStyledItemDelegate, QStyle, QStyleOptionViewItem, QApplication,
    QAbstractItemView, QGraphicsOpacityEffect,
)

from app.paths import app_root, asset_path
from app.engine import crop_v3, CACHE_DIR, PREVIEW_DIR
from app import models, rawio, sheet
import head_fix          # engine 已把 skill/scripts 加进 sys.path

# 与 engine.PreviewKit.render 一一对应
C_MASK = "#f02e28"
C_FULL = "#ff9f3c"
C_CORE = "#3296ff"
C_CROP = "#50dc3e"
C_HEAD = "#f02828"

ROW_H = 40

# ---------------------------------------------------------------- 文案
TEXT = {
    "zh": {
        "subtitle": "昆虫自动化后期",
        "mode": "模式", "precision": "精度", "device": "设备",
        "modes": ["裁切 + 曝光", "只裁切", "只曝光"],
        "segs": ["掩膜 768", "掩膜 512"],
        "start": "开始处理", "pause": "暂停", "resume": "继续",
        "to_light": "浅色", "to_dark": "深色",
        "lang": "EN", "lang_tip": "切换英文",
        "tab_process": "处理", "tab_train": "训练", "tab_about": "说明",
        "queue": "队列", "count": "{n} 张",
        "add_dir": "加目录", "add_files": "加文件", "clear": "清空",
        "drop": "把文件夹或照片拖进来（整窗可拖）",
        "warming": "正在加载模型…（第一次约 30 秒，之后不用再等）",
        "warm_wait": "模型还在加载，好了会自动开始",
        "realtime": "实时预览", "minimize": "最小化自动暂停",
        "ev_prev": "曝光预览",
        "ev_prev_on": "曝光预览：开（整张按算出的 EV 显示）",
        "ev_prev_off": "曝光预览：关（显示原图）",
        "ev_prev_tip": "开：整张按算出的 EV 提亮/压暗；关：显示原图。"
                       "近似：±1 档以内和 Lightroom 基本一致，大正曝光会比 LR 更容易死白。",
        "xmp": "已有 XMP 的图片", "xmp_tip": "软件写的可以覆盖，你亲手改过的默认不动",
        "policies": ["保护你修的图", "全部跳过", "全部覆盖"],
        "policy_tip": "保护你修的图：软件写过的可以覆盖，你改过的跳过；"
                      "全部跳过：任何同名 XMP 都不动；"
                      "全部覆盖：都重写（覆盖前仍备份到 _xmp_backup/）",
        "legend": ["掩膜", "整体框", "身体框", "裁切框", "头部"],
        "ph": "把文件夹或照片拖进窗口\n\n点击队列里的照片可以预览原图",
        "ph_run": "处理后这里显示：红=掩膜　橙=整体框　蓝=身体框\n"
                  "绿粗框=裁切框　绿斜线=将被裁掉　红圈=头部",
        "done": "{d} / {t}", "fail": "（失败 {n}）", "skipn": "（跳过 {n}）",
        "speed": "{v:.2f} 秒/张", "speed_na": "— 秒/张",
        "eta_hm": "剩余 {m}:{s:02d}", "eta_s": "剩余 {s} 秒", "eta_na": "剩余 —",
        "st_ok": "完成", "st_fail": "失败", "st_skip": "跳过",
        "st_manual": "跳过·你修的", "st_exists": "跳过·已有",
        "st_edit": "微调", "st_fallback": "系数退回内置",
        "head_dbl_hint": "这张没标到头：拖一下头点，点「完成」即可",
        "no_write": "不写",
        "edit_hint": "微调：拖框边/角",
        "edit_tip": "拖框边/角改大小，拖框内移动；改身体或整体会自动重算裁切；完成后写回 XMP",
        "commit": "完成", "cancel": "取消",
        "edit_done": "已写入 XMP", "edit_discard": "已放弃上一张的微调",
        "learned": "　已记住这次头部修正，累计 {n} 条",
        "learned_toast": "✓ 已写入 XMP · 头部修正累计 {n} 条",
        "prev_cost": "（预览 +{v:.2f}s）",
        "follow": "跟随当前", "follow_tip": "自动选中正在处理的那张并滚到可见处；"
                                          "你手动点队列或缩略图会自动关掉它",
        "follow_off": "已停止跟随（你选了这张）",
        "now": "正在处理：{n}",
        "cur": "当前", "none_yet": "未处理", "no_sel": "未选择照片",
        "m_ev": "EV", "m_in": "L_in", "m_box": "L_box", "m_w": "框宽",
        "m_sh": "锐化", "m_origin": "来源",
        "o_new": "新建", "o_auto": "软件", "o_manual": "你修的",
        "slow_hint": "（会降低速度，最小化自动暂停）",
        "sheet": "结果拼版", "sheet_n": "{n} 张", "export": "导出拼版",
        "open_dir": "打开目录",
        "exporting": "正在拼版 {a}/{b}…", "export_done": "已导出 {n} 个文件：{p}",
        "export_none": "这一批还没有生成叠加图（打开实时预览再跑一遍即可）",
        "export_head": "导出训练样本",
        "export_none_head": "还没有累计任何头部修正（点开照片拖一下头点再点完成，就会记一条）",
        "export_head_ok": "已导出 {n} 条，其中 {u} 条带路径，可直接并入训练集",
        "sheet_title": "iKun Insect Studio · 裁切核对",
        "models_group": "模型（系数）",
        "model_crop": "裁切", "model_ev": "曝光",
        "model_import": "导入…", "model_open": "打开模型目录",
        "model_note": "切换从下一张生效；内置那套永远在，训练产物不会覆盖它。",
        "model_note_tip": "别人的系数也能用（几 KB 的 JSON，导入即可），"
                          "但裁切那 105 项学的是他自己的构图习惯，通常不如你自己的。",
        "model_switched": "已切换到 {n}（下一张生效）",
        "model_imported": "已导入 {n}",
        "model_import_bad": "导入失败：{e}",
        "train_group": "从「原片 + 同名 XMP」重拟合",
        "train_ph": "选多少个目录都行，会各自递归扫描",
        "train_dirs": "训练目录（可以放多个，也能直接把照片拖进来）",
        "train_added": "已加入 {n} 个目录，点「开始训练」即可",
        "train_pause": "暂停训练", "train_resume": "继续训练",
        "train_remove": "从训练集里去掉这个文件夹",
        "train_row": "{name}（{n} 张）",
        "train_tip_files": "只训练你挑的这 {n} 张",
        "train_tip_dir": "整个文件夹 {n} 张",
        "model_auto_switched": "已自动切到新训练的模型：{n}",
        "model_pick": "点这里选择要用的模型",
        "ver_now": "当前版本 {v}",
        "check_update": "检查更新",
        "open_release": "打开下载页",
        "upd_checking": "正在检查…",
        "upd_fail": "检查失败（网络不通，或还没发布过版本）",
        "upd_latest": "已是最新（{v}）",
        "upd_new": "有新版本 {v}，点「打开下载页」",
        "upd_title": "发现新版本",
        "train_clear_title": "清空训练列表",
        "train_clear_ask": "要从训练集里移除全部 {n} 个文件夹吗？\n照片不会被删除，只是不参加这次训练。",
        "train_added_dup": "这些目录已经在列表里了",
        "add_train": "添加目录", "del_train": "移除选中", "clear_train": "清空列表",
        "browse": "浏览", "train_go": "开始训练",
        "train_note": "只在你定下的那几类量上重拟合：裁切仍是 105 项（13 项特征），"
                      "曝光仍是 L_in / L_box 双参数。不换模型、不加新特征。\n"
                      "多个目录会按「目录名/第一层子目录」分批次做 5 折留出，"
                      "产物写到 data/train_*/，不会覆盖正在用的系数。",
        "train_done": "训练完成：{p}",
        "intro": "这一页做两件事：一是拿你自己的「原片 + XMP」重新拟合裁切/曝光；"
                 "二是管理头部位置的修正记忆。",
        "head_group": "头部修正学习（不动模型权重）",
        "head_off": "已累计 {n} 条 · 满 3 条开始生效",
        "head_knn": "已累计 {n} 条 · 6 近邻补偿（平均 {dx:+.3f} / {dy:+.3f} 体宽）",
        "head_linear": "已累计 {n} 条 · 7 参数线性残差（残差 {r:.3f} 体宽）",
        "head_refit": "重拟合", "head_csv": "导出 CSV", "head_clear": "清空记录",
        "head_note": "处理或微调时，把队列里的照片点开，拖红点到正确位置，点「完成」就记一条。\n"
                     "前 3 条起按几何最像的 6 条历史做平移补偿；累计到 25 条自动换成"
                     "一个 7 参数线性残差模型（每次新增都会自动重拟合，也可以手动点「重拟合」）。\n"
                     "这是给模型输出打的补丁，不是微调 ResNet——25 条修正喂不动 99 MB 的网络，"
                     "而这里每条只占约 200 字节，删掉即恢复原样。",
        "head_none": "还没有记录",
        "head_cleared": "已清空头部修正记录",
        "head_csv_done": "已导出 {n} 条到 {p}",
        "refit_none": "不足 {n} 条，先多标几张再重拟合",
        "refit_done": "已重拟合：{n} 条，残差 {r:.3f} 体宽",
        "reset_note": "测试用：清空设置、模型库、头部记忆、预览缓存和训练报告。"
                      "照片和 XMP 一律不动。",
        "reset_btn": "恢复初始状态…",
        "reset_ask": "要恢复到「第一次装好」的状态吗？\n\n"
                     "将删除 {n} 项（{mb:.1f} MB）：\n{names}\n\n"
                     "不会动：照片、照片旁边的 .xmp、_ikun_xmp_log.jsonl。\n\n"
                     "想模拟「别人第一次用」，建议先把照片复制到一个新文件夹再拖进来——"
                     "同一个目录里已有的 XMP 会被当成你修过的而跳过。",
        "reset_done": "已恢复初始状态（模型还在显存里，不用重新加载）",
        "reset_busy": "队列还在跑。先暂停，等当前这张处理完再重置。",
        "pick_dir": "选择照片目录", "pick_files": "选择照片",
        "pick_train": "添加到训练目录列表",
        "msg_running": "正在处理，先暂停再清空。",
        "msg_empty": "队列是空的，先拖入照片",
        "msg_need_dir": "先选一个存在的目录",
        "added": "加入 {n} 张",
        "ready": "就绪",
        "mini_note": "已最小化：预览渲染暂停（处理继续）",
        "click_prev": "预览：{n}",
        "api_ready": "本地 API 已就绪：{u}",
        "title": "iKun Insect Studio · 昆虫自动化后期",
    },
    "en": {
        "subtitle": "Automatic Insect Post-processing",
        "mode": "Mode", "precision": "Precision", "device": "Device",
        "modes": ["Crop + Exposure", "Crop only", "Exposure only"],
        "segs": ["Mask 768", "Mask 512"],
        "start": "Start", "pause": "Pause", "resume": "Resume",
        "to_light": "Light", "to_dark": "Dark",
        "lang": "中文", "lang_tip": "Switch to Chinese",
        "tab_process": "Process", "tab_train": "Train", "tab_about": "About",
        "queue": "Queue", "count": "{n} photos",
        "add_dir": "Folder", "add_files": "Files", "clear": "Clear",
        "drop": "Drop folders or photos anywhere in this window",
        "warming": "Loading models… (~30 s the first time, never again)",
        "warm_wait": "Models still loading — it will start by itself",
        "realtime": "Live preview", "minimize": "Paused when minimized",
        "ev_prev": "Exposure preview",
        "ev_prev_on": "Exposure preview: on",
        "ev_prev_off": "Exposure preview: off",
        "ev_prev_tip": "On: the whole frame brightened/darkened by the computed EV. "
                       "Off: the original. Approximate: fine within ±1 EV, big positive "
                       "values clip harder than Lightroom.",
        "xmp": "Photos with XMP", "xmp_tip": "Overwrite ours, keep yours by default",
        "policies": ["Keep mine", "Skip all", "Overwrite"],
        "policy_tip": "Keep mine: overwrite what this app wrote, skip what you edited; "
                      "Skip all: never touch an existing XMP; "
                      "Overwrite: rewrite everything (still backed up to _xmp_backup/)",
        "legend": ["Mask", "Full", "Body", "Crop", "Head"],
        "ph": "Drop folders or photos here\n\nClick a photo in the queue to preview it",
        "ph_run": "After processing: red=mask  orange=full  blue=body\n"
                  "green thick=crop  green hatch=to be cropped  red ring=head",
        "done": "{d} / {t}", "fail": " ({n} failed)", "skipn": " ({n} skipped)",
        "speed": "{v:.2f} s/photo", "speed_na": "— s/photo",
        "eta_hm": "ETA {m}:{s:02d}", "eta_s": "ETA {s}s", "eta_na": "ETA —",
        "st_ok": "Done", "st_fail": "Failed", "st_skip": "Skipped",
        "st_manual": "skip·manual", "st_exists": "skip·exists",
        "st_edit": "fine-tuned", "st_fallback": "fallback to built-in",
        "head_dbl_hint": "No head point on this one: drag it, then press Done",
        "no_write": "not set",
        "edit_hint": "Drag edges/corners",
        "edit_tip": "Drag edges/corners to resize, inside to move; body/full changes refit the crop; Apply writes XMP",
        "commit": "Apply", "cancel": "Cancel",
        "edit_done": "Saved to XMP", "edit_discard": "Previous adjustment discarded",
        "learned": "  head fix remembered, {n} total",
        "learned_toast": "✓ Saved to XMP · {n} head fixes learned",
        "prev_cost": " (+{v:.2f}s preview)",
        "follow": "Follow", "follow_tip": "Auto-select the photo being processed and scroll it into view; "
                                         "clicking a photo turns it off",
        "follow_off": "Follow turned off (you picked this one)",
        "now": "Processing: {n}",
        "cur": "Current", "none_yet": "not processed", "no_sel": "no photo selected",
        "m_ev": "EV", "m_in": "L_in", "m_box": "L_box", "m_w": "Crop w",
        "m_sh": "Sharpen", "m_origin": "Origin",
        "o_new": "new", "o_auto": "app", "o_manual": "manual",
        "slow_hint": "(slower, paused when minimised)",
        "sheet": "Contact sheet", "sheet_n": "{n} photos", "export": "Export sheet",
        "open_dir": "Open folder",
        "exporting": "Building sheet {a}/{b}…", "export_done": "Wrote {n} file(s): {p}",
        "export_none": "Nothing to lay out yet (turn live preview on and run again)",
        "export_head": "Export training samples",
        "export_none_head": "No head corrections recorded yet (open a photo, drag the head point, commit)",
        "export_head_ok": "Exported {n} rows, {u} of them carry a path and can join the training set",
        "sheet_title": "iKun Insect Studio · crop check",
        "models_group": "Models (coefficients)",
        "model_crop": "Crop", "model_ev": "Exposure",
        "model_import": "Import…", "model_open": "Open model folder",
        "model_note": "Applies from the next photo; the built-in set always stays.",
        "model_note_tip": "Someone else's coefficients work too (a few KB of JSON), but the 105 "
                          "terms encode their own framing habits — usually worse for you.",
        "model_switched": "Switched to {n} (next photo)",
        "model_imported": "Imported {n}",
        "model_import_bad": "Import failed: {e}",
        "train_group": "Refit from RAW + sidecar XMP",
        "train_ph": "Pick one or more folders; each is scanned recursively",
        "train_dirs": "Training folders (multiple allowed — you can drop photos here)",
        "train_added": "Added {n} folder(s); press Start training",
        "train_pause": "Pause", "train_resume": "Resume",
        "train_remove": "Remove this folder from the training set",
        "train_row": "{name} ({n} photos)",
        "train_tip_files": "Train only the {n} photos you picked",
        "train_tip_dir": "The whole folder, {n} photos",
        "model_auto_switched": "Switched to the newly trained model: {n}",
        "model_pick": "Click to pick a model",
        "ver_now": "Version {v}",
        "check_update": "Check for updates",
        "open_release": "Open download page",
        "upd_checking": "Checking…",
        "upd_fail": "Check failed (offline, or nothing published yet)",
        "upd_latest": "Up to date ({v})",
        "upd_new": "Version {v} is available — open the download page",
        "upd_title": "Update available",
        "train_clear_title": "Clear the training list",
        "train_clear_ask": "Remove all {n} folders from the training set?\nNo photos are deleted — they just drop out of this run.",
        "train_added_dup": "Those folders are already in the list",
        "add_train": "Add folder", "del_train": "Remove selected", "clear_train": "Clear list",
        "browse": "Browse", "train_go": "Start training",
        "train_note": "Refits only the terms you defined: crop stays 105 terms "
                      "(13 features), exposure stays L_in / L_box. "
                      "No new model, no new features.\n"
                      "Multiple folders are grouped by folder/top-subfolder into 5-fold hold-out. "
                      "Output goes to data/train_*/ and never overwrites the active coefficients.",
        "train_done": "Training finished: {p}",
        "intro": "Two things live here: refit crop/exposure from your own RAW+XMP pairs, "
                 "and manage the head-point corrections.",
        "head_group": "Head correction memory (no model weights touched)",
        "head_off": "{n} recorded · kicks in at 3",
        "head_knn": "{n} recorded · 6-neighbour bias (mean {dx:+.3f} / {dy:+.3f} core width)",
        "head_linear": "{n} recorded · 7-parameter linear residual ({r:.3f} core width)",
        "head_refit": "Refit", "head_csv": "Export CSV", "head_clear": "Clear",
        "head_note": "Open a processed photo, drag the red point onto the head, hit Apply — one record.\n"
                     "From 3 records it shifts by the 6 most similar histories; at 25 it switches to a "
                     "7-parameter linear residual model (refit automatically on every new record, "
                     "or press Refit).\n"
                     "This patches the model output, it does not fine-tune ResNet: 25 corrections cannot "
                     "move a 99 MB network, while each record here costs ~200 bytes and can be deleted.",
        "head_none": "no records yet",
        "head_cleared": "Head corrections cleared",
        "head_csv_done": "Exported {n} rows to {p}",
        "refit_none": "Need at least {n} records first",
        "refit_done": "Refit on {n} records, residual {r:.3f} core width",
        "reset_note": "For testing: clears settings, models, head memory, preview cache and "
                      "training reports. Photos and XMP are never touched.",
        "reset_btn": "Factory reset…",
        "reset_ask": "Restore the app to its just-installed state?\n\n"
                     "This deletes {n} item(s) ({mb:.1f} MB):\n{names}\n\n"
                     "Never touched: photos, their .xmp sidecars, _ikun_xmp_log.jsonl.\n\n"
                     "To simulate a first-time user, copy the photos into a new folder first — "
                     "existing XMPs in the same folder are treated as manual and skipped.",
        "reset_done": "Factory state restored (models stay in VRAM, no reload needed)",
        "reset_busy": "The queue is still running. Pause and let the current photo finish.",
        "pick_dir": "Choose a photo folder", "pick_files": "Choose photos",
        "pick_train": "Add to training folders",
        "msg_running": "Still processing. Pause first, then clear.",
        "msg_empty": "Queue is empty — drop some photos first",
        "msg_need_dir": "Pick a folder that exists first",
        "added": "Added {n} photos",
        "ready": "Ready",
        "mini_note": "Minimized: preview rendering paused (processing continues)",
        "click_prev": "Preview: {n}",
        "api_ready": "Local API ready: {u}",
        "title": "iKun Insect Studio · Automatic Insect Post-processing",
    },
}


def _ensure_font():
    """确保中文字体可用：优先系统雅黑，其次手动加载 msyh.ttc。"""
    from PySide6.QtGui import QFontDatabase
    fams = set(QFontDatabase.families())
    for name in ("Microsoft YaHei UI", "Microsoft YaHei", "SimHei", "SimSun"):
        if name in fams:
            QApplication.setFont(QFont(name, 9))
            return name
    for fp in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf",
               "C:/Windows/Fonts/simsun.ttc"):
        if os.path.exists(fp):
            fid = QFontDatabase.addApplicationFont(fp)
            fam = QFontDatabase.applicationFontFamilies(fid)
            if fam:
                QApplication.setFont(QFont(fam[0], 9))
                return fam[0]
    return ""


def pil_to_pixmap(im):
    """PIL RGB → QPixmap（复制数据，避免 PIL 释放后悬空）。"""
    if im.mode != "RGB":
        im = im.convert("RGB")
    w, h = im.size
    data = im.tobytes("raw", "RGB")
    qi = QImage(data, w, h, 3 * w, QImage.Format_RGB888).copy()
    return QPixmap.fromImage(qi)


def _mini(btn, pad=11):
    """小按钮的唯一做法：竖向 padding 归零 + 只给最小高度，文字永不被裁。"""
    btn.setStyleSheet(f"padding:0 {pad}px;")
    btn.setMinimumHeight(28)
    return btn


def _fit_width(btn, extra=30, minimum=52):
    """按字体度量算宽度——切中文/英文后都够，不再出现「中文只露出一半」。"""
    fm = btn.fontMetrics()
    btn.setFixedWidth(max(fm.horizontalAdvance(btn.text()) + extra, minimum))
    return btn


def _fit_combo(cb, extra=46, minimum=96):
    """下拉框按最长的一项定宽；里面还有箭头，所以多留一点。"""
    fm = cb.fontMetrics()
    w = max([fm.horizontalAdvance(cb.itemText(i)) for i in range(cb.count())] or [0])
    cb.setFixedWidth(max(w + extra, minimum))
    return cb


class QueueDelegate(QStyledItemDelegate):
    """队列行（两行）：

        上行  文件名 ……………………………… f/16 · 1/60 · ISO 800
        下行  EV +0.35 · L 182/96 · 框 0.344 · 锐 65 ……… 完成
    """

    def __init__(self, win):
        super().__init__(win.list)
        self.win = win
        self._theme("light")

    def _theme(self, name):
        dark = name == "dark"
        self.dark = dark
        self.name_color = "#c6d1cb" if dark else "#26322d"
        self.meta_color = "#7f8c86" if dark else "#5f6b66"
        self.res_color = "#5ec08f" if dark else "#2f7d5c"
        self.sel_name = "#eaf4ee" if dark else "#0f231b"
        self.sel_meta = "#cfe3d8" if dark else "#22503c"
        self.sel_bg = "#26453a" if dark else "#cfe6da"
        self.ok_color = "#4f9d78" if dark else "#2f7d5c"
        self.err_color = "#d9737a" if dark else "#b3454f"
        self.skip_color = "#8a948f" if dark else "#6f7c77"
        self.run_color = "#5ec08f" if dark else "#23795a"
        self.mute_color = "#5a6663" if dark else "#98a49f"

    def sizeHint(self, option, index):
        s = super().sizeHint(option, index)
        s.setHeight(ROW_H)
        return s

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        selected = bool(opt.state & QStyle.State_Selected)
        # 选中底色自己画：不依赖系统蓝色高亮，也避免浅色主题白字压浅底
        opt.state &= ~QStyle.State_Selected
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)
        row = index.row()
        failed_row = False
        if row < len(self.win._tasks):
            r0 = self.win._tasks[row].result or {}
            failed_row = bool(r0.get("error"))
        if failed_row and not selected:
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#fdeced" if not self.dark else "#3a2124"))
            painter.drawRoundedRect(opt.rect.adjusted(1, 1, -1, -1), 5, 5)
            painter.restore()
        if selected:
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(self.sel_bg))
            painter.drawRoundedRect(opt.rect.adjusted(1, 1, -1, -1), 5, 5)
            # 左侧 4px 条：失败=红，正常=绿
            painter.setBrush(QColor("#c0392b" if failed_row else "#2f8f6b"))
            painter.drawRoundedRect(opt.rect.left() + 4, opt.rect.top() + 6,
                                    4, max(opt.rect.height() - 12, 4), 2, 2)
            painter.restore()
        elif failed_row:
            painter.save()
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#c0392b"))
            painter.drawRoundedRect(opt.rect.left() + 4, opt.rect.top() + 6,
                                    4, max(opt.rect.height() - 12, 4), 2, 2)
            painter.restore()

        tasks = self.win._tasks
        if row >= len(tasks):
            return
        t = tasks[row]
        r = opt.rect.adjusted(12, 3, -10, -3)
        top = r.top()
        painter.save()

        f1 = painter.font()
        f1.setPixelSize(13)
        f2 = QFont(f1)
        f2.setPixelSize(11)

        # ---- 上行：文件名 + 相机参数
        painter.setFont(f1)
        fm1 = painter.fontMetrics()
        meta = t.meta or ""
        mw = fm1.horizontalAdvance(meta)
        name_w = max(r.width() - mw - 14, 50)
        name = fm1.elidedText(os.path.basename(t.path), Qt.ElideMiddle, name_w)

        if selected:
            ncol, mcol = self.sel_name, self.sel_meta
        elif t.state == "failed":
            ncol, mcol = self.err_color, self.err_color
        elif t.state == "skipped":
            ncol, mcol = self.skip_color, self.skip_color
        else:
            ncol, mcol = self.name_color, self.meta_color
        if t.state == "running":
            ncol = self.run_color

        line1 = QRect(r.left(), top, r.width(), 17)
        painter.setPen(QColor(ncol))
        painter.drawText(line1, Qt.AlignLeft | Qt.AlignVCenter, name)
        if meta:
            painter.setPen(QColor(mcol))
            painter.drawText(line1, Qt.AlignRight | Qt.AlignVCenter, meta)

        # ---- 下行：结果数字 + 状态
        painter.setFont(f2)
        fm2 = painter.fontMetrics()
        res, state, scol = self._line2(t, selected)
        sw = fm2.horizontalAdvance(state)
        res_w = max(r.width() - sw - 12, 40)
        line2 = QRect(r.left(), top + 17, r.width(), 16)
        if res:
            painter.setPen(QColor(self.sel_meta if selected else self.res_color
                                  if t.state == "done" else self.mute_color))
            painter.drawText(line2, Qt.AlignLeft | Qt.AlignVCenter,
                             fm2.elidedText(res, Qt.ElideRight, res_w))
        if state:
            painter.setPen(QColor(scol))
            painter.drawText(line2, Qt.AlignRight | Qt.AlignVCenter, state)
        painter.restore()

    def _line2(self, t, selected):
        r = t.result or {}
        if r.get("error"):
            sh = r.get("sharp")
            left = f"{self.win._t('m_sh')} {sh}" if sh is not None else ""
            return left, self.win._t("st_fail"), self.err_color
        if r.get("skipped"):
            reason = r.get("skip_reason")
            key = {"manual": "st_manual", "exists": "st_exists"}.get(reason, "st_skip")
            return "", self.win._t(key), self.skip_color
        if t.state == "running":
            return "", "…", self.run_color
        if not r:
            return "", "", self.mute_color
        bits = []
        ev = r.get("ev")
        if isinstance(ev, (int, float)):
            bits.append(f"{self.win._t('m_ev')} {ev:+.2f}")
        li, lb = r.get("L_in"), r.get("L_box")
        if isinstance(li, (int, float)) and isinstance(lb, (int, float)):
            bits.append(f"L {li:.0f}/{lb:.0f}")
        w = r.get("w")
        if isinstance(w, (int, float)):
            bits.append(f"{self.win._t('m_w')} {w:.3f}")
        sh = r.get("sharp")
        if sh is not None:
            bits.append(f"{self.win._t('m_sh')} {sh}")
        st = self.win._t("st_edit") if r.get("manual_crop") else self.win._t("st_ok")
        return " · ".join(bits), st, self.ok_color if not r.get("manual_crop") \
            else ("#c98a2a" if not selected else "#f0c987")


class ArrowCombo(QComboBox):
    """原生箭头在各主题下几乎看不见，自己画一个在框内右侧。"""

    def paintEvent(self, e):
        super().paintEvent(e)
        from PySide6.QtGui import QPainter, QPolygonF, QColor
        from PySide6.QtCore import QPointF
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        cx, cy = w - 15, h / 2.0
        col = QColor("#2f7d5d" if self.isEnabled() else "#a8b3ad")
        if getattr(self, "_dark", False):
            col = QColor("#7cc4a4" if self.isEnabled() else "#7d8a84")
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawPolygon(QPolygonF([QPointF(cx - 5, cy - 2.6), QPointF(cx + 5, cy - 2.6),
                                 QPointF(cx, cy + 3.8)]))
        p.end()

    def set_theme(self, dark):
        self._dark = bool(dark)
        self.update()


class _UpdWorker(QThread):
    """后台查一次 GitHub，不卡界面。"""
    done = Signal(dict)

    def run(self):
        try:
            from app import update
            self.done.emit(update.check())
        except Exception as e:      # noqa: BLE001
            self.done.emit({"ok": False, "error": str(e)})


class DropList(QListWidget):
    """支持从资源管理器拖入文件/文件夹的队列。"""

    def __init__(self, on_paths):
        super().__init__()
        self.on_paths = on_paths
        self.setAcceptDrops(True)
        self.setSelectionMode(QListWidget.ExtendedSelection)
        self.setSpacing(1)
        self.setFrameShape(QFrame.NoFrame)
        self.setObjectName("queue")
        self.setMouseTracking(True)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.viewport().setStyleSheet("border:1px dashed #4fa87f;")

    def dragLeaveEvent(self, e):
        self.viewport().setStyleSheet("")

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        self.dragLeaveEvent(e)
        if paths:
            self.on_paths(paths)


class Preview(QWidget):
    """预览 / 手动微调画布。

    普通模式只显示一张已经画好叠加的 jpg。
    微调模式（set_edit）显示原始图 + 可拖动的框：身体、整体、裁切、头点。
    """

    edited = Signal(str)
    committed = Signal()
    cancelled = Signal()
    dbl = Signal()            # 双击：没标头就进微调
    dropped = Signal(list)    # 往画布上拖照片/文件夹

    def __init__(self, text=""):
        super().__init__()
        self._pm = None
        self._text = text
        self._bg = QColor("#eef3f0")
        self._fg = QColor("#4f5b56")
        self._bd = QColor("#dfe7e2")
        self._rect = QRect()
        self.boxes = None
        self._hover = None
        self._drag = None
        self._active = None
        self._dirty = False
        self.setMinimumSize(420, 280)
        self.setObjectName("preview")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    # ------------------------------------------------------------ 数据
    def set_text(self, t):
        self._text = t
        self.update()

    def set_theme(self, dark):
        self._bg = QColor("#0b0f0d" if dark else "#eef3f0")
        self._fg = QColor("#8b9793" if dark else "#4f5b56")
        self._bd = QColor("#242b28" if dark else "#dfe7e2")
        self.update()

    def set_pixmap(self, pm):
        self._pm = pm
        self.boxes = None
        self._rect = QRect()
        self.update()

    def set_image(self, path):
        pm = QPixmap(path)
        if not pm.isNull():
            self.set_pixmap(pm)

    def clear_image(self):
        self._pm = None
        self.boxes = None
        self._rect = QRect()
        self.update()

    def set_edit(self, pm, core, full, crop, head):
        self._pm = pm
        self.boxes = {"core": tuple(core), "full": tuple(full),
                      "crop": tuple(crop),
                      "head": tuple(head) if head else None}
        self._dirty = False
        self._hover = None
        self._drag = None
        self.update()

    def clear_edit(self):
        self.boxes = None
        self._hover = None
        self._drag = None
        self._active = None
        self.update()

    def box(self, k):
        return self.boxes.get(k) if self.boxes else None

    def set_crop(self, crop):
        if self.boxes:
            self.boxes["crop"] = tuple(crop)
            self.update()

    def is_editing(self):
        return self.boxes is not None

    # ------------------------------------------------------------ 绘制
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), self._bg)
        p.setPen(QPen(self._bd, 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        if self._pm is None:
            p.setPen(self._fg)
            p.drawText(self.rect(), Qt.AlignCenter, self._text)
            self._rect = QRect()
            return
        scaled = self._pm.scaled(self.size(), Qt.KeepAspectRatio,
                                 Qt.SmoothTransformation)
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        p.drawPixmap(x, y, scaled)
        self._rect = QRect(x, y, scaled.width(), scaled.height())
        if self.boxes:
            self._paint_boxes(p)

    def _map(self, b):
        r = self._rect
        return QRectF(r.x() + b[0] * r.width(), r.y() + b[1] * r.height(),
                      (b[2] - b[0]) * r.width(), (b[3] - b[1]) * r.height())

    def _paint_boxes(self, p):
        b = self.boxes
        r = self._rect
        if b.get("crop"):
            cr = self._map(b["crop"]).toRect()
            clip = QRegion(r).subtracted(QRegion(cr))
            p.save()
            p.setClipRegion(clip)
            p.fillRect(r, QColor(128, 212, 104, 28))
            p.setPen(QPen(QColor(128, 212, 104, 120), 1))
            for o in range(-r.height(), r.width() + r.height(), 18):
                p.drawLine(r.x() + o, r.bottom(), r.x() + o + r.height(), r.top())
            p.restore()

        def frame(box, color, w):
            q = self._map(box)
            p.setPen(QPen(QColor(245, 245, 245, 230), w + 2))
            p.drawRect(q)
            p.setPen(QPen(QColor(color), w))
            p.drawRect(q)

        if b.get("full"):
            frame(b["full"], "#ff9f3c", 2)
        if b.get("core"):
            frame(b["core"], "#3296ff", 2)
        if b.get("crop"):
            frame(b["crop"], "#50dc3e", 4)
        if b.get("head"):
            hx = r.x() + b["head"][0] * r.width()
            hy = r.y() + b["head"][1] * r.height()
            p.setPen(QPen(QColor(250, 250, 250), 3))
            p.setBrush(QColor(250, 250, 250))
            p.drawEllipse(QPointF(hx, hy), 7, 7)
            p.setPen(QPen(QColor("#f02e28"), 2))
            p.setBrush(QColor("#f02e28"))
            p.drawEllipse(QPointF(hx, hy), 5, 5)
            p.drawEllipse(QPointF(hx, hy), 2, 2)

        # 手柄：hover 或刚才拖的那个框
        kind = (self._hover[0] if self._hover else None) or self._active
        if kind and kind != "head" and b.get(kind):
            q = self._map(b[kind])
            p.setPen(QPen(QColor("#123024"), 1))
            p.setBrush(QColor("#ffffff"))
            for pt in (q.topLeft(),
                       QPointF(q.center().x(), q.top()), q.topRight(),
                       QPointF(q.right(), q.center().y()), q.bottomRight(),
                       QPointF(q.center().x(), q.bottom()), q.bottomLeft(),
                       QPointF(q.left(), q.center().y())):
                p.drawRect(QRectF(pt.x() - 3.5, pt.y() - 3.5, 7, 7))

    # ------------------------------------------------------------ 交互
    def _norm(self, pos):
        r = self._rect
        return ((pos.x() - r.x()) / max(r.width(), 1),
                (pos.y() - r.y()) / max(r.height(), 1))

    def _hit(self, pos):
        if not self.boxes or self._rect.isNull():
            return None
        tol = 8
        for kind in ("core", "full", "crop"):
            bb = self.boxes.get(kind)
            if not bb:
                continue
            q = self._map(bb)
            l, t, r, bo = q.left(), q.top(), q.right(), q.bottom()
            x, y = pos.x(), pos.y()
            if abs(x - l) <= tol and abs(y - t) <= tol:
                return kind, "lt"
            if abs(x - r) <= tol and abs(y - t) <= tol:
                return kind, "rt"
            if abs(x - l) <= tol and abs(y - bo) <= tol:
                return kind, "lb"
            if abs(x - r) <= tol and abs(y - bo) <= tol:
                return kind, "rb"
            if abs(x - l) <= tol and t <= y <= bo:
                return kind, "l"
            if abs(x - r) <= tol and t <= y <= bo:
                return kind, "r"
            if abs(y - t) <= tol and l <= x <= r:
                return kind, "t"
            if abs(y - bo) <= tol and l <= x <= r:
                return kind, "b"
        h = self.boxes.get("head")
        if h:
            hx = self._rect.x() + h[0] * self._rect.width()
            hy = self._rect.y() + h[1] * self._rect.height()
            if abs(pos.x() - hx) <= 13 and abs(pos.y() - hy) <= 13:
                return "head", "move"
        for kind in ("core", "full", "crop"):
            bb = self.boxes.get(kind)
            if bb and self._map(bb).contains(QPointF(pos)):
                return kind, "move"
        return None

    def _cursor(self, part):
        return {
            "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
            "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
            "lt": Qt.SizeFDiagCursor, "rb": Qt.SizeFDiagCursor,
            "rt": Qt.SizeBDiagCursor, "lb": Qt.SizeBDiagCursor,
            "move": Qt.SizeAllCursor,
        }.get(part, Qt.ArrowCursor)

    def mouseDoubleClickEvent(self, e):
        """双击画布：如果这张还没标头，直接进微调去标。"""
        if not self.boxes and e.button() == Qt.LeftButton:
            self.dbl.emit()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.dropped.emit(paths)
        e.acceptProposedAction()

    def mousePressEvent(self, e):
        if not self.boxes or e.button() != Qt.LeftButton:
            return
        hit = self._hit(e.position().toPoint())
        if not hit:
            return
        kind, part = hit
        self._active = kind
        self.setFocus()
        self._drag = {"kind": kind, "part": part,
                      "start": self._norm(e.position().toPoint()),
                      "orig": tuple(self.boxes[kind]) if kind != "head"
                              else tuple(self.boxes["head"])}
        self.setCursor(self._cursor(part))
        self.update()

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if not self._drag:
            hit = self._hit(pos)
            self._hover = hit
            self.setCursor(self._cursor(hit[1] if hit else None))
            self.update()
            return
        d = self._drag
        nx, ny = self._norm(pos)
        dx = nx - d["start"][0]
        dy = ny - d["start"][1]
        kind = d["kind"]
        if kind == "head":
            hx = min(max(d["orig"][0] + dx, 0.0), 1.0)
            hy = min(max(d["orig"][1] + dy, 0.0), 1.0)
            self.boxes["head"] = (hx, hy)
        else:
            l, t, r, b = d["orig"]
            part = d["part"]
            if part == "move":
                w, h = r - l, b - t
                l = min(max(l + dx, 0.0), 1.0 - w)
                t = min(max(t + dy, 0.0), 1.0 - h)
                r, b = l + w, t + h
            else:
                if "l" in part:
                    l = min(max(l + dx, 0.0), r - 0.03)
                if "r" in part:
                    r = min(max(r + dx, l + 0.03), 1.0)
                if "t" in part:
                    t = min(max(t + dy, 0.0), b - 0.03)
                if "b" in part:
                    b = min(max(b + dy, t + 0.03), 1.0)
            self.boxes[kind] = (l, t, r, b)
        self._dirty = True
        self.edited.emit(kind)
        self.update()

    def mouseReleaseEvent(self, e):
        if self._drag:
            self._drag = None
            self.setCursor(Qt.ArrowCursor)
            self.update()

    def keyPressEvent(self, e):
        if not self.boxes:
            return
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.committed.emit()
        elif e.key() == Qt.Key_Escape:
            self.cancelled.emit()


class SheetWorker(QThread):
    """后台拼版：几百张也不卡界面；缺定稿图的在这里现画。"""

    done = Signal(object)      # 文件列表
    fail = Signal(str)

    def __init__(self, items, out_path, title, lang="zh", resolver=None, parent=None):
        super().__init__(parent)
        self.items = items
        self.out_path = out_path
        self.title = title
        self.lang = lang
        self.resolver = resolver

    def run(self):
        try:
            payload = []
            for r in self.items:
                fp = r.get("_file") or ""
                if not fp and self.resolver is not None:
                    try:
                        fp = self.resolver(r) or ""
                    except Exception:      # noqa: BLE001
                        fp = ""
                payload.append(dict(r, _file=fp))
            paths = sheet.build_sheet(payload, self.out_path, title=self.title,
                                      lang=self.lang)
            self.done.emit(paths)
        except Exception as e:      # noqa: BLE001
            self.fail.emit(f"{type(e).__name__}: {e}")


class MainWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        _ensure_font()
        self.app_ctx = app
        self.engine = app["engine"]
        self.cfg = app["cfg"]
        self.trainer = app["trainer"]
        self._lang = self.cfg.get("lang") or "zh"
        if self._lang not in TEXT:
            self._lang = "zh"
        self._tasks = []
        self._total_seen = 0
        self._last_preview = None
        self._preview_pin = None
        self._last_row_shown = -1
        self._edit_task = None
        self._edit_dirty = False
        self._thumbs = {}
        self._theme = self.cfg.get("theme") or "light"
        self._sheet_sig = None
        self._sheet_worker = None
        self._train_dirs = self._norm_train_dirs(self.cfg.get("train_dirs") or [])

        self.setWindowTitle(self._t("title"))
        self.resize(1460, 920)
        self.setAcceptDrops(True)
        try:
            ic = asset_path("app.ico")
            if os.path.exists(ic):
                self.setWindowIcon(QIcon(ic))
        except Exception:  # noqa: BLE001
            pass

        self._build()
        self._apply_theme(self._theme)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(500)
        self.engine.ping()
        # 先把窗口画出来；模型在后台读（冷盘要 30–40 秒，正好用拖照片的时间）
        if self.cfg.get("preload", True):
            QTimer.singleShot(700, self.engine.warmup_async)

    # ---------------------------------------------------------------- 文案
    def _t(self, key, **kw):
        s = TEXT[self._lang].get(key, TEXT["zh"].get(key, key))
        if isinstance(s, list):
            return s
        try:
            return s.format(**kw) if kw else s
        except (KeyError, IndexError, ValueError):
            return s

    # ---------------------------------------------------------------- UI
    def _build(self):
        root = QWidget()
        root.setObjectName("root")
        v = QVBoxLayout(root)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(10)
        v.addWidget(self._topbar())

        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_process(), self._t("tab_process"))
        self.tabs.addTab(self._tab_train(), self._t("tab_train"))
        self.tabs.addTab(self._tab_about(), self._t("tab_about"))
        v.addWidget(self.tabs, 1)
        self.setCentralWidget(root)
        self.status = self.statusBar()
        self.status.showMessage(self._t("ready"))

    def _topbar(self):
        bar = QFrame()
        bar.setObjectName("topbar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(14, 8, 14, 8)
        h.setSpacing(10)

        logo = QLabel()
        pm = QPixmap(asset_path("logo.png"))
        if not pm.isNull():
            logo.setPixmap(pm.scaled(38, 38, Qt.KeepAspectRatio,
                                     Qt.SmoothTransformation))
        logo.setFixedSize(40, 40)
        h.addWidget(logo)

        tv = QVBoxLayout()
        tv.setSpacing(0)
        tv.setContentsMargins(0, 0, 0, 0)
        self.logo_title = QLabel("iKun <span style='color:#3f8f6b'>Insect Studio</span>")
        self.logo_title.setTextFormat(Qt.RichText)
        self.logo_title.setObjectName("logo")
        from PySide6.QtGui import QFontDatabase
        fam = "Arial"
        for fp in ("C:/Windows/Fonts/segoeuib.ttf",      # Segoe UI Bold
                   "C:/Windows/Fonts/bahnschrift.ttf",
                   "C:/Windows/Fonts/arialbd.ttf"):
            if os.path.exists(fp):
                fid = QFontDatabase.addApplicationFont(fp)
                names = QFontDatabase.applicationFontFamilies(fid)
                if names:
                    fam = names[0]
                    break
        lf = QFont(fam, 16)
        lf.setWeight(QFont.Bold)
        lf.setLetterSpacing(QFont.AbsoluteSpacing, 0.4)
        self.logo_title.setFont(lf)
        self.logo_sub = QLabel(self._t("subtitle"))
        self.logo_sub.setObjectName("subtitle")
        tv.addWidget(self.logo_title)
        tv.addWidget(self.logo_sub)
        h.addLayout(tv)
        h.addSpacing(20)

        def group(label, widget):
            box = QHBoxLayout()
            box.setSpacing(6)
            lb = QLabel(label)
            lb.setObjectName("fieldLabel")
            box.addWidget(lb)
            box.addWidget(widget)
            box._label = lb
            return box

        self.cb_mode = QComboBox()
        self.cb_mode.addItems(self._t("modes"))
        self.cb_mode.setCurrentIndex(["both", "crop", "exposure"].index(
            self.cfg.get("mode") if self.cfg.get("mode") in ("both", "crop", "exposure") else "both"))
        self.cb_mode.currentIndexChanged.connect(self._cfg_changed)
        g1 = group(self._t("mode"), self.cb_mode)
        h.addLayout(g1)

        self.cb_seg = QComboBox()
        self.cb_seg.addItems(self._t("segs"))
        self.cb_seg.setCurrentIndex(0 if int(self.cfg.get("seg_size")) == 768 else 1)
        self.cb_seg.currentIndexChanged.connect(self._cfg_changed)
        g2 = group(self._t("precision"), self.cb_seg)
        h.addLayout(g2)

        self.cb_dev = QComboBox()
        self.cb_dev.addItems(["CUDA", "CPU"])
        self.cb_dev.setCurrentIndex(0 if self.cfg.get("device") == "cuda" else 1)
        self.cb_dev.currentIndexChanged.connect(self._cfg_changed)
        g3 = group(self._t("device"), self.cb_dev)
        h.addLayout(g3)

        self.cb_mode.setMinimumWidth(132)
        self.cb_seg.setMinimumWidth(100)
        self.cb_dev.setMinimumWidth(88)
        self._top_groups = [(g1, "mode"), (g2, "precision"), (g3, "device")]

        h.addStretch(1)
        self.b_lang = _mini(QPushButton(self._t("lang")), 12)
        self.b_lang.setObjectName("ghost")
        self.b_lang.setToolTip(self._t("lang_tip"))
        self.b_lang.clicked.connect(self._toggle_lang)
        _fit_width(self.b_lang)
        h.addWidget(self.b_lang)

        self.b_theme = _mini(QPushButton(""), 12)
        self.b_theme.setObjectName("ghost")
        self.b_theme.clicked.connect(self._toggle_theme)
        h.addWidget(self.b_theme)

        self.b_pause = QPushButton(self._t("pause"))
        self.b_pause.setObjectName("ghost")
        self.b_pause.setMinimumHeight(28)
        self.b_pause.clicked.connect(self._pause)
        self.b_start = QPushButton(self._t("start"))
        self.b_start.setObjectName("primary")
        self.b_start.setMinimumWidth(110)
        self.b_start.setMinimumHeight(28)
        self.b_start.clicked.connect(self._start)
        h.addWidget(self.b_pause)
        h.addWidget(self.b_start)
        return bar

    def _tab_process(self):
        wrap = QWidget()
        wv = QVBoxLayout(wrap)
        wv.setContentsMargins(0, 0, 0, 0)
        wv.setSpacing(8)

        w = QWidget()
        v = QHBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        # ---------- 左：队列
        left = QFrame()
        left.setObjectName("card")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(12, 10, 12, 10)
        lv.setSpacing(8)

        hd = QHBoxLayout()
        hd.setSpacing(8)
        self.l_queue = QLabel(self._t("queue"))
        self.l_queue.setObjectName("cardTitle")
        self.l_count = QLabel(self._t("count", n=0))
        self.l_count.setObjectName("counter")
        hd.addWidget(self.l_queue)
        hd.addWidget(self.l_count)
        hd.addStretch(1)
        self.b_add_dir = _mini(QPushButton(self._t("add_dir")))
        self.b_add_dir.setObjectName("ghost")
        self.b_add_dir.clicked.connect(self._pick_dir)
        self.b_add_files = _mini(QPushButton(self._t("add_files")))
        self.b_add_files.setObjectName("ghost")
        self.b_add_files.clicked.connect(self._pick_files)
        self.b_clear = _mini(QPushButton(self._t("clear")))
        self.b_clear.setObjectName("ghost")
        self.b_clear.clicked.connect(self._clear)
        for b in (self.b_add_dir, self.b_add_files, self.b_clear):
            hd.addWidget(b)
        lv.addLayout(hd)

        self.l_hint = QLabel(self._t("drop"))
        self.l_hint.setObjectName("hint")
        lv.addWidget(self.l_hint)

        self.list = DropList(self._on_paths)
        self.list.setItemDelegate(QueueDelegate(self))
        self.list.itemClicked.connect(self._on_item_clicked)
        # 上下方向键只改 currentRow，不发 itemClicked —— 这里补上
        self.list.currentRowChanged.connect(self._on_row_changed)
        lv.addWidget(self.list, 1)
        self.split_main = QSplitter(Qt.Horizontal)
        self.split_main.setChildrenCollapsible(False)
        self.split_main.addWidget(left)

        # ---------- 右：预览 + 当前数字 + 缩略图墙
        right = QFrame()
        right.setObjectName("card")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(12, 10, 12, 10)
        rv.setSpacing(7)

        # 预览区（开关 + 图例 + 预览 + 数字）与拼版区之间可拖动
        top_box = QWidget()
        tlay = QVBoxLayout(top_box)
        tlay.setContentsMargins(0, 0, 0, 0)
        tlay.setSpacing(7)
        sheet_box = QWidget()
        slay = QVBoxLayout(sheet_box)
        slay.setContentsMargins(0, 0, 0, 0)
        slay.setSpacing(4)

        ph = QHBoxLayout()
        ph.setSpacing(12)
        self.chk_prev = QCheckBox(self._t("realtime"))
        self.chk_prev.setChecked(bool(self.cfg.get("preview_enabled")))
        self.chk_prev.stateChanged.connect(self._preview_toggle)

        self.chk_ev = QCheckBox(self._t("ev_prev"))
        self.chk_ev.setChecked(bool(self.cfg.get("preview_exposure", True)))
        self.chk_ev.setToolTip(self._t("ev_prev_tip"))
        self.chk_ev.stateChanged.connect(self._evprev_toggle)

        # 两个开关并排，说明合成一行放它们下面
        # 「跟随当前」不再露出来：列表默认跟着跑批滚动，你点某张就停在它上面。
        # 仍然建一个隐藏的复选框，让内部开关逻辑保持不变。
        self.chk_follow = QCheckBox(self._t("follow"))
        self.chk_follow.setChecked(True)
        self.chk_follow.setVisible(False)

        _row = QHBoxLayout()
        _row.setContentsMargins(0, 0, 0, 0)
        _row.setSpacing(14)
        _row.addWidget(self.chk_prev)
        _row.addWidget(self.chk_ev)
        _col = QVBoxLayout()
        _col.setContentsMargins(0, 0, 0, 0)
        _col.setSpacing(0)
        _col.addLayout(_row)
        self.l_slow = QLabel(self._t("slow_hint"))
        self.l_slow.setObjectName("hint")
        _col.addWidget(self.l_slow)
        ph.addLayout(_col)
        ph.addStretch(1)                 # 后面这一组整体靠右
        ph.addSpacing(24)

        self.l_xmp = QLabel(self._t("xmp"))
        self.l_xmp.setObjectName("fieldLabel")
        ph.addWidget(self.l_xmp)
        self.cb_policy = QComboBox()
        self.cb_policy.addItems(self._t("policies"))
        self.cb_policy.setCurrentIndex(
            {"protect": 0, "skip_all": 1, "force": 2}.get(self.engine.policy(), 0))
        self.cb_policy.setToolTip(self._t("policy_tip"))
        _fit_combo(self.cb_policy)
        _fit_combo(self.cb_mode)
        self.cb_policy.currentIndexChanged.connect(self._policy_changed)
        ph.addWidget(self.cb_policy)
        ph.addSpacing(14)

        tlay.addLayout(ph)

        # 图例单独一行靠右；微调条在左侧，只在编辑时出现
        self.edit_bar = QWidget()
        eb = QHBoxLayout(self.edit_bar)
        eb.setContentsMargins(0, 0, 0, 0)
        eb.setSpacing(8)
        self.l_edit = QLabel(self._t("edit_hint"))
        self.l_edit.setObjectName("hint")
        self.l_edit.setToolTip(self._t("edit_tip"))
        self.b_commit = _mini(QPushButton(self._t("commit")), 12)
        self.b_commit.setObjectName("primary")
        self.b_commit.clicked.connect(self._commit_edit)
        self.b_cancel = _mini(QPushButton(self._t("cancel")), 12)
        self.b_cancel.setObjectName("ghost")
        self.b_cancel.clicked.connect(self._cancel_edit)
        eb.addWidget(self.l_edit)
        eb.addWidget(self.b_commit)
        eb.addWidget(self.b_cancel)
        self.edit_bar.hide()

        lh = QHBoxLayout()
        lh.addWidget(self.edit_bar)
        lh.addStretch(1)
        self.legend_holder = QWidget()
        self.legend_layout = QHBoxLayout(self.legend_holder)
        self.legend_layout.setContentsMargins(0, 0, 0, 0)
        self.legend_layout.setSpacing(16)
        lh.addWidget(self.legend_holder)
        tlay.addLayout(lh)

        self.preview = Preview(self._t("ph"))
        self.preview.edited.connect(self._on_edit_changed)
        self.preview.committed.connect(self._commit_edit)
        self.preview.cancelled.connect(self._cancel_edit)
        self.preview.dbl.connect(self._preview_dbl)
        self.preview.dropped.connect(self._on_paths)
        tlay.addWidget(self.preview, 1)

        # 当前这张的一行数字
        strip = QHBoxLayout()
        strip.setSpacing(14)
        self.l_cur = QLabel(self._t("no_sel"))
        self.l_cur.setObjectName("curName")
        self.l_metrics = QLabel("")
        self.l_metrics.setObjectName("hint")
        self.l_state = QLabel("")
        self.l_state.setObjectName("hint")
        self.l_state.setMinimumWidth(76)
        strip.addWidget(self.l_cur)
        strip.addWidget(self.l_metrics, 1)
        strip.addWidget(self.l_state)
        tlay.addLayout(strip)

        # 结果缩略图墙
        gh = QHBoxLayout()
        gh.setSpacing(10)
        self.l_sheet = QLabel(self._t("sheet"))
        self.l_sheet.setObjectName("cardTitle")
        self.l_sheetn = QLabel(self._t("sheet_n", n=0))
        self.l_sheetn.setObjectName("counter")
        gh.addWidget(self.l_sheet)
        gh.addWidget(self.l_sheetn)
        gh.addStretch(1)
        self.b_export = _mini(QPushButton(self._t("export")))
        self.b_export.setObjectName("ghost")
        self.b_export.clicked.connect(self._export_sheet)
        self.b_open = _mini(QPushButton(self._t("open_dir")))
        self.b_open.setObjectName("ghost")
        self.b_open.clicked.connect(self._open_output_dir)
        gh.addWidget(self.b_export)
        gh.addWidget(self.b_open)
        slay.addLayout(gh)

        self.grid = QListWidget()
        self.grid.setViewMode(QListWidget.IconMode)
        self.grid.setIconSize(QSize(128, 88))
        self.grid.setGridSize(QSize(136, 96))
        self.grid.setResizeMode(QListWidget.Adjust)
        self.grid.setMovement(QListWidget.Static)
        self.grid.setSpacing(2)
        self.grid.setUniformItemSizes(True)
        self.grid.setFrameShape(QFrame.NoFrame)
        self.grid.setObjectName("grid")
        self.grid.setSelectionMode(QAbstractItemView.SingleSelection)
        self.grid.itemClicked.connect(self._on_grid_clicked)
        slay.addWidget(self.grid)
        self.split_right = QSplitter(Qt.Vertical)
        self.split_right.setChildrenCollapsible(False)
        self.split_right.addWidget(top_box)
        self.split_right.addWidget(sheet_box)
        self.split_right.setStretchFactor(0, 1)
        self.split_right.setStretchFactor(1, 0)
        rv.addWidget(self.split_right, 1)
        self.split_main.addWidget(right)
        self.split_main.setStretchFactor(0, 5)
        self.split_main.setStretchFactor(1, 8)
        v.addWidget(self.split_main, 1)
        self._restore_split()
        # 拖一下就记一次，别等关窗（关窗时被强杀就丢了）
        self.split_main.splitterMoved.connect(lambda *_: self._save_split())
        self.split_right.splitterMoved.connect(self._on_sheet_dragged)

        wv.addWidget(w, 1)
        wv.addWidget(self._footer())
        return wrap

    def _footer(self):
        card = QFrame()
        card.setObjectName("card")
        h = QHBoxLayout(card)
        h.setContentsMargins(16, 9, 16, 9)
        h.setSpacing(16)
        self.pbar = QProgressBar()
        self.pbar.setMaximum(100)
        self.pbar.setTextVisible(False)
        self.pbar.setFixedHeight(10)
        h.addWidget(self.pbar, 1)
        self.l_done = QLabel("0 / 0")
        self.l_speed = QLabel(self._t("speed_na"))
        self.l_eta = QLabel(self._t("eta_na"))
        for x in (self.l_done, self.l_speed, self.l_eta):
            x.setObjectName("stat")
            x.setMinimumWidth(96)
            h.addWidget(x)
        return card

    def _tab_train(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(10)

        self.l_intro = QLabel(self._t("intro"))
        self.l_intro.setObjectName("hint")
        self.l_intro.setWordWrap(True)
        v.addWidget(self.l_intro)

        # ---- 模型（系数）切换
        self.box_models = QGroupBox(self._t("models_group"))
        mg = QGridLayout(self.box_models)
        mg.setHorizontalSpacing(10)
        mg.setVerticalSpacing(8)
        self.l_crop_model = QLabel(self._t("model_crop"))
        self.l_crop_model.setObjectName("fieldLabel")
        self.cb_crop_model = ArrowCombo()
        self.cb_crop_model.setMinimumWidth(360)
        self.cb_crop_model.setMaximumWidth(560)
        self.cb_crop_model.currentIndexChanged.connect(
            lambda: self._model_changed("crop", self.cb_crop_model))
        self.b_crop_import = _mini(QPushButton(self._t("model_import")))
        self.b_crop_import.setObjectName("ghost")
        self.b_crop_import.clicked.connect(lambda: self._import_model("crop"))
        self.l_ev_model = QLabel(self._t("model_ev"))
        self.l_ev_model.setObjectName("fieldLabel")
        self.cb_ev_model = ArrowCombo()
        self.cb_ev_model.setMinimumWidth(360)
        self.cb_ev_model.setMaximumWidth(560)
        self.cb_ev_model.currentIndexChanged.connect(
            lambda: self._model_changed("ev", self.cb_ev_model))
        self.b_ev_import = _mini(QPushButton(self._t("model_import")))
        self.b_ev_import.setObjectName("ghost")
        self.b_ev_import.clicked.connect(lambda: self._import_model("ev"))
        self.b_open_models = _mini(QPushButton(self._t("model_open")))
        self.b_open_models.setObjectName("ghost")
        self.b_open_models.clicked.connect(self._open_models_dir)
        for cb in (self.cb_crop_model, self.cb_ev_model):
            cb.setToolTip(self._t("model_pick"))
        mg.addWidget(self.l_crop_model, 0, 0)
        mg.addWidget(self.cb_crop_model, 0, 1)
        mg.addWidget(self.b_crop_import, 0, 2)
        mg.addWidget(self.l_ev_model, 1, 0)
        mg.addWidget(self.cb_ev_model, 1, 1)
        mg.addWidget(self.b_ev_import, 1, 2)
        mg.addWidget(self.b_open_models, 0, 3, 2, 1)
        mg.setColumnStretch(1, 1)
        self.l_model_note = QLabel(self._t("model_note"))
        self.l_model_note.setObjectName("hint")
        self.l_model_note.setWordWrap(True)
        self.l_model_note.setToolTip(self._t("model_note_tip"))
        mg.addWidget(self.l_model_note, 2, 0, 1, 4)
        v.addWidget(self.box_models)

        # ---- 训练目录（多个）
        self.box_train = QGroupBox(self._t("train_group"))
        g = QVBoxLayout(self.box_train)
        g.setSpacing(8)
        self.l_train_dirs = QLabel(self._t("train_dirs"))
        self.l_train_dirs.setObjectName("fieldLabel")
        g.addWidget(self.l_train_dirs)

        self.train_list = DropList(self._add_train_paths)   # 直接把照片/文件夹拖进来
        self.train_list.setObjectName("listbox")
        self.train_list.setFrameShape(QFrame.NoFrame)
        self.train_list.setFixedHeight(78)
        g.addWidget(self.train_list)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.b_add_train = _mini(QPushButton(self._t("add_train")))
        self.b_add_train.setObjectName("ghost")
        self.b_add_train.clicked.connect(self._pick_train_dir)
        self.b_del_train = _mini(QPushButton(self._t("del_train")))
        self.b_del_train.setObjectName("ghost")
        self.b_del_train.clicked.connect(self._del_train_dir)
        self.b_clear_train = _mini(QPushButton(self._t("clear_train")))
        self.b_clear_train.setObjectName("ghost")
        self.b_clear_train.clicked.connect(self._clear_train_dirs)
        self.t_go = QPushButton(self._t("train_go"))
        self.t_go.setObjectName("primary")
        self.t_go.setMinimumHeight(28)
        self.t_go.clicked.connect(self._train)
        self.b_pause_train = _mini(QPushButton(self._t("train_pause")))
        self.b_pause_train.setObjectName("ghost")
        self.b_pause_train.clicked.connect(self._toggle_pause_train)
        self.b_pause_train.setEnabled(False)
        self.b_del_train.hide()
        for b in (self.b_add_train, self.b_clear_train):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(self.b_pause_train)
        row.addWidget(self.t_go)
        g.addLayout(row)
        v.addWidget(self.box_train)

        self.t_pbar = QProgressBar()
        self.t_pbar.setFixedHeight(8)
        self.t_pbar.setTextVisible(False)
        v.addWidget(self.t_pbar)

        self.t_log = QTextEdit()
        self.t_log.setReadOnly(True)
        self.t_log.setObjectName("log")
        self.t_log.setMinimumHeight(140)
        v.addWidget(self.t_log, 1)

        self.l_train_note = QLabel(self._t("train_note"))
        self.l_train_note.setObjectName("hint")
        self.l_train_note.setWordWrap(True)
        v.addWidget(self.l_train_note)

        # ---- 头部修正记忆
        self.box_head = QGroupBox(self._t("head_group"))
        hg = QVBoxLayout(self.box_head)
        hg.setSpacing(8)
        hr = QHBoxLayout()
        hr.setSpacing(8)
        self.l_head = QLabel("")
        self.l_head.setObjectName("fieldLabel")
        hr.addWidget(self.l_head, 1)
        self.b_refit = _mini(QPushButton(self._t("head_refit")))
        self.b_refit.setObjectName("ghost")
        self.b_refit.clicked.connect(self._refit_head)
        self.b_head_csv = _mini(QPushButton(self._t("head_csv")))
        self.b_head_csv.setObjectName("ghost")
        self.b_head_csv.clicked.connect(self._export_head)
        self.b_head_clear = _mini(QPushButton(self._t("head_clear")))
        self.b_head_clear.setObjectName("ghost")
        self.b_head_clear.clicked.connect(self._clear_head)
        for b in (self.b_refit, self.b_head_csv, self.b_head_clear):
            hr.addWidget(b)
        hg.addLayout(hr)
        self.l_head_note = QLabel(self._t("head_note"))
        self.l_head_note.setObjectName("hint")
        self.l_head_note.setWordWrap(True)
        hg.addWidget(self.l_head_note)
        v.addWidget(self.box_head)

        # ---- 测试 / 维护：一键回到「第一次装好」
        row = QHBoxLayout()
        row.setSpacing(10)
        self.l_maint = QLabel(self._t("reset_note"))
        self.l_maint.setObjectName("hint")
        self.l_maint.setWordWrap(True)
        self.b_reset = _mini(QPushButton(self._t("reset_btn")), 12)
        self.b_reset.setObjectName("ghost")
        self.b_reset.clicked.connect(self._factory_reset)
        row.addWidget(self.l_maint, 1)
        row.addWidget(self.b_reset)
        v.addLayout(row)

        self._refresh_train_list()
        self._refresh_head()
        self._refresh_models()

        # 内容比窗口高时出现滚动条，绝不把控件压到最小高度（以前那版会把说明挤成一条）
        self.train_page = page
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # 滚动区视口默认是白底，会把白色分组框吃掉；给页面本身铺主题底色（走 QSS，不走内联样式，
        # 否则会盖掉 #primary 这些子控件规则）
        page.setObjectName("trainpage")
        page.setAttribute(Qt.WA_StyledBackground, True)   # 纯 QWidget 默认不画 QSS 背景
        scroll.setWidget(page)
        w = QWidget()
        wl = QVBoxLayout(w)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(scroll)
        QTimer.singleShot(0, self._fit_train_page)
        return w

    def _fit_train_page(self):
        """把滚动页的最小高度钉在内容真实需要的高度。

        为什么需要：QLabel 自动换行时 minimumSizeHint 只按一行算，布局会把它压扁，
        文字就被裁掉（这一版之前训练页就是这么坏的）。量一遍 sizeHint 再写回最小高度，
        窗口变矮时走滚动条，而不是挤控件。
        """
        p = getattr(self, "train_page", None)
        if p is None or p.layout() is None:
            return
        p.setMinimumHeight(0)
        p.layout().activate()
        p.setMinimumHeight(p.layout().sizeHint().height())

    def _tab_about(self):
        from app.version import VERSION
        w = QWidget()
        v = QVBoxLayout(w)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.l_ver = QLabel(self._t("ver_now", v=VERSION))
        self.l_ver.setObjectName("fieldLabel")
        self.b_update = _mini(QPushButton(self._t("check_update")))
        self.b_update.setObjectName("ghost")
        self.b_update.clicked.connect(lambda: self._check_update(False))
        self.b_open_rel = _mini(QPushButton(self._t("open_release")))
        self.b_open_rel.setObjectName("ghost")
        self.b_open_rel.hide()
        self.l_upd = QLabel("")
        self.l_upd.setObjectName("hint")
        row.addWidget(self.l_ver)
        row.addWidget(self.b_update)
        row.addWidget(self.b_open_rel)
        row.addWidget(self.l_upd, 1)
        v.addLayout(row)
        self.about = QTextEdit()
        self.about.setReadOnly(True)
        self.about.setObjectName("log")
        self._refresh_models()
        try:
            self.l_speed.setText(self._t("speed_na"))
            self.l_eta.setText(self._t("eta_na"))
        except Exception:      # noqa: BLE001
            pass
        self.about.setHtml(self._about_html())
        v.addWidget(self.about)
        return w

    def _check_update(self, silent=True):
        if getattr(self, "_upd_worker", None) is not None and self._upd_worker.isRunning():
            return
        if not silent:
            self.l_upd.setText(self._t("upd_checking"))
        self._upd_worker = _UpdWorker(self)
        self._upd_worker.done.connect(lambda d: self._on_update(d, silent))
        self._upd_worker.start()

    def _on_update(self, d, silent):
        import time as _t
        self.cfg.update(update_checked_at=_t.time())
        if not d.get("ok"):
            self.l_upd.setText(self._t("upd_fail"))
            if not silent:
                self.status.showMessage(self._t("upd_fail"), 6000)
            return
        self.cfg.update(update_latest=d.get("latest", ""))
        if not d.get("newer"):
            self.l_upd.setText(self._t("upd_latest", v=d.get("latest", "")))
            if not silent:
                self.status.showMessage(self._t("upd_latest", v=d.get("latest", "")), 6000)
            return
        self.l_upd.setText(self._t("upd_new", v=d.get("latest")))
        self.b_open_rel.show()
        url = d.get("page") or ""
        try:
            self.b_open_rel.clicked.disconnect()
        except Exception:      # noqa: BLE001
            pass
        self.b_open_rel.clicked.connect(lambda: __import__("webbrowser").open(url))
        if silent:
            self._toast(self._t("upd_new", v=d.get("latest")), 15000)
        else:
            QMessageBox.information(self, self._t("upd_title"),
                                    self._t("upd_new", v=d.get("latest")) + "\n\n" + url)

    def _about_html(self):
        en = self._lang == "en"
        dark = self._theme == "dark"
        ct = "#bcc8c2" if dark else "#3a4742"
        ch = "#e9efeb" if dark else "#1f2724"
        ca = "#8fb8a6" if dark else "#3f8f6b"
        cl = "#272d2e" if dark else "#e0e8e4"
        rows = [
            ("Crop" if en else "裁切",
             "105-term quadratic (13 features, pairwise products); "
             "hold-out median IoU 0.8650; 80-photo blind test 0.9017"
             if en else
             "105 项二次式（13 项特征 × 两两乘积）；"
             "留出 IoU 中位 0.8650，80 张盲测 0.9017"),
            ("Exposure" if en else "曝光",
             "EV = 3.0416 − 0.02108·L_in − 0.01362·L_box; "
             "hold-out MAE 0.28–0.29 EV"
             if en else
             "EV = 3.0416 − 0.02108·L_in − 0.01362·L_box；"
             "留出 MAE 0.28–0.29 档"),
            ("Sharpen" if en else "锐化",
             "By aperture, strictly increasing: ≤2.8 → 20, &lt;4 → 30, &lt;5.6 → 40, "
             "&lt;11 → 50, &lt;14 → 60, ≥14 → 65. Smaller aperture, more sharpening. "
             "Editable: data/sharpen_table.csv"
             if en else
             "按光圈分档，越小补得越多：≤2.8 → 20，&lt;4 → 30，&lt;5.6 → 40，"
             "&lt;11 → 50，&lt;14 → 60，≥14 → 65。分档可直接改 data/sharpen_table.csv"),
            ("Head" if en else "头部",
             "ResNet50 heatmap + soft-argmax; a 6-feature correction memory on top "
             "(6-neighbour, then a 7-parameter linear residual from 25 records)."
             if en else
             "ResNet50 热图 + soft-argmax；上面再叠一层 6 特征修正记忆"
             "（3 条起 6 近邻，25 条起改 7 参数线性残差）。"),
        ]
        tr = "".join(
            f'<tr><td style="color:{ca}"><b>{k}</b></td>'
            f'<td style="color:{ct}">{v}</td></tr>' for k, v in rows)

        # ---- 整条 AI 链路（2026-11-20 用户要求写进说明）
        if en:
            steps = [
                ("1 · Segment", "Shrink the whole frame to 768², run BiRefNet once",
                 "One black-and-white mask: insect = white. This is the only place a big "
                 "network looks at the whole photo."),
                ("2 · Body", "Erode the mask a little (opening), keep the largest blob",
                 "Legs and antennae are one pixel wide — erosion snaps them, what is left is "
                 "the torso. Its bounding box is the body box."),
                ("3 · Whole", "Bounding box of the untouched mask",
                 "Legs, antennae and wings set the outer limit. Body area ÷ whole area = how "
                 "far the limbs are spread — one of the 13 features."),
                ("4 · Head", "Body box +15% → 256² chip → ResNet50 → 64×64 heat map",
                 "The heat map says <i>where</i> the head is, not just whether there is one; "
                 "soft-argmax takes the weighted centre, so the point lands between cells."),
                ("5 · Gate", "Peak score + geometric check (inside body box +20%)",
                 "Two subjects (mating pair, side by side) force the head off — the box spans "
                 "both, so a head direction has no meaning."),
                ("6 · Crop", "13 numbers → 105 terms → centre x, centre y, log2 width",
                 "Then three hard rules, in order: never leave the canvas &gt; keep 3% leg "
                 "padding &gt; look good (IoU)."),
                ("7 · Light", "p95 brightness inside the mask + p95 outside it in the box",
                 "Two numbers into one straight line gives EV. Sharpening is a table lookup "
                 "by aperture."),
            ]
            pl = "".join(
                f'<tr><td style="color:{ca}; white-space:nowrap"><b>{a}</b></td>'
                f'<td style="color:{ct}">{b}</td>'
                f'<td style="color:{ct}; font-size:12px">{c}</td></tr>' for a, b, c in steps)
            pipe = (f'<h4 style="color:{ch}">The whole chain, in plain words</h4>'
                    f'<p style="color:{ct}">One photo = <b>one</b> segmentation + <b>one</b> '
                    f'head look. Everything else is arithmetic on those numbers, which is why '
                    f'the three modules cannot disagree with each other.</p>'
                    f'<table cellpadding="5">{pl}</table>'
                    f'<p style="color:{ct}; font-size:12px">Limits: below ~8% of the frame '
                    f'width the mask gets soft and the crop drifts; a pure back view still gets '
                    f'a plausible front-ish point — drag it if it looks wrong.</p>')
        else:
            steps = [
                ("1 · 分割", "整幅缩到 768²，跑一次 BiRefNet",
                 "得到一张黑白掩膜：虫=白。整条链路只有这一步是「大网络看整张照片」。"),
                ("2 · 身体", "掩膜做开运算（先腐蚀再膨胀），留最大的一块",
                 "腿和触角只有一两个像素宽，一腐蚀就断；剩下的就是躯干。外接矩形 = 身体框。"),
                ("3 · 整体", "原始掩膜的外接矩形",
                 "腿、触角、翅伸到哪，框就到哪。整体面积 ÷ 身体面积 = 腿张开的程度，"
                 "是 13 个特征里的一个。"),
                ("4 · 头部", "身体框外扩 15% 裁 256² → ResNet50 → 64×64 热力图",
                 "热力图回答的是「头在哪」，不是「有没有头」；soft-argmax 取加权重心，"
                 "点能落在格子之间（亚像素）。"),
                ("5 · 把关", "峰值分数 + 几何校验（落在身体框外扩 20% 内）",
                 "两只以上（交配对、并排）强制关掉头部项——框横跨两只，头心方向没意义。"),
                ("6 · 裁切", "13 个数展开成 105 项 → 框心 x、框心 y、log2 框宽",
                 "再按顺序卡三条硬规矩：绝不出界 &gt; 腿留白 ≥3% &gt; IoU 好看。"),
                ("7 · 影调", "掩膜内 p95 亮度 + 框内掩膜外的 p95 亮度",
                 "两个数进一条直线就是 EV；锐化按光圈查表。"),
            ]
            pl = "".join(
                f'<tr><td style="color:{ca}; white-space:nowrap"><b>{a}</b></td>'
                f'<td style="color:{ct}">{b}</td>'
                f'<td style="color:{ct}; font-size:12px">{c}</td></tr>' for a, b, c in steps)
            pipe = (f'<h4 style="color:{ch}">整条链路，说人话</h4>'
                    f'<p style="color:{ct}">一张照片 = <b>一次</b>分割 + <b>一次</b>找头。'
                    f'后面全是拿这几个数做算术，所以三个模块不可能互相打架。</p>'
                    f'<table cellpadding="5">{pl}</table>'
                    f'<p style="color:{ct}; font-size:12px">边界：虫宽不到画面 8% 时掩膜会糊、'
                    f'裁切会飘；纯背面也会得到一个「大致靠前」的点——看着不对就拖一下。</p>')

        if en:
            title = "iKun Insect Studio · Automatic Insect Post-processing"
            p1 = "One pipeline, one mask, three modules:"
            p3 = ("How to use: process the photos first, then import them into Lightroom "
                  "together with their .xmp files. Only a batch you already imported needs "
                  "selecting → right-click → <i>Read Metadata from File</i>. No restart.")
            p4 = ("<b style='color:%s'>AI API</b>: a local API listens on 127.0.0.1:8765. "
                  "Open <code>http://127.0.0.1:8765/api/ai</code> for a self-describing "
                  "manifest." % ch)
            p5 = ("<b style='color:%s'>XMP ownership</b>: every write appends one line to "
                  "<code>_ikun_xmp_log.jsonl</code> in the photo folder, together with a SHA-1 "
                  "of the file it wrote. Next run: same hash = untouched, overwrite; "
                  "different hash (you edited it in Lightroom) = treat as manual, skip. "
                  "No record at all = also manual. Policy is switchable in the top bar."
                  % ch)
            p6 = ("<b style='color:%s'>Contact sheet</b>: one click lays every result of this "
                  "run into a 6-per-row JPG (quality 80, split every 120 photos). "
                  "The bottom-right grid is the same list, clickable." % ch)
            p7 = ("<b style='color:%s'>Preview cost</b>: overlays reuse the mask from the "
                  "processing pass, so no extra model run. Switching live preview off — or "
                  "minimizing the window — stops drawing altogether and the run gets a little "
                  "faster; how much depends on the machine and the photos." % ch)
        else:
            title = "iKun Insect Studio · 昆虫自动化后期"
            p1 = "一条链路，一个掩膜，三个模块："
            p3 = ("怎么用：先把照片处理好，再连同 .xmp 一起导入 Lightroom。"
                  "只有已经导入过、后来又处理的那批，才需要在网格里选中 → 右键"
                  "「从文件读取元数据」；不用重启 LR。")
            p4 = ("<b style='color:%s'>AI 接口</b>：启动时在 127.0.0.1:8765 起本地 API。"
                  "访问 <code>http://127.0.0.1:8765/api/ai</code> 拿自描述清单。" % ch)
            p5 = ("<b style='color:%s'>XMP 归属</b>：每写一张，就在照片所在目录的 "
                  "<code>_ikun_xmp_log.jsonl</code> 里追加一行，连同写出去那份文件的 SHA-1。"
                  "下次跑批：哈希没变=没人动过，可覆盖；哈希变了（你在 LR 里改过）=按你修过的跳过；"
                  "账本里根本没记录=也按你修过的算。三种策略在顶栏可切。" % ch)
            p6 = ("<b style='color:%s'>结果拼版</b>：一键把这一批的所有结果排成 6 张一排的 JPG"
                  "（质量 80，超过 120 张自动分卷）。右下角那面缩略图墙就是同一批，可以点。"
                  % ch)
            p7 = ("<b style='color:%s'>预览开销</b>：叠加图复用处理时那一份掩膜，不额外跑模型。"
                  "关掉「实时预览」或把窗口最小化，就不再画叠加图，速度会快一点——"
                  "快多少取决于电脑和照片大小，每台机器都不一样。"
                  "<b>曝光预览</b>是个开关：开了整张按算出的 EV 调整（线性乘 2^EV，走 LUT，"
                  "只多几毫秒），关掉就是原图。这是近似——±1 档以内和 LR 基本一致，"
                  "大正值会比 LR 更容易死白。" % ch)
        cm = "#8b9793" if dark else "#7b8782"
        if en:
            copy = ("© 2026 Zheng Tianyu — Laboratory of Systematics and Evolutionary "
                    "Entomology, China Agricultural University")
        else:
            copy = "© 2026 中国农业大学 系统与进化昆虫学实验室 · 郑天宇"
        tagline = ("For the shots you can't be bothered to deal with."
                   if en else "帮你快速处理那些懒得处理的烂片。")
        return (f'<div style="color:{ct}; line-height:1.7">'
                f'<h3 style="color:{ch}">{title}</h3>'
                f'<p style="color:{ch}; font-size:15px; margin-top:-6px">'
                f'<b>{tagline}</b></p>'
                f'<p>{p3}</p>'
                f'<p>{p1}</p><table cellpadding="5">{tr}</table>'
                f'{pipe}'
                f'<hr style="border-color:{cl}">'
                f'<p>{p4}</p><p>{p5}</p><p>{p6}</p><p>{p7}</p>'
                f'<p style="color:{cm}; font-size:12px; margin-top:18px">{copy}</p>'
                f'</div>')

    # ---------------------------------------------------------------- 主题 / 语言
    def _apply_theme(self, name):
        name = name if name in THEMES else "light"
        self._theme = name
        self.setStyleSheet(THEMES[name] + COMBO_QSS[name])
        self.cfg.update(theme=name)
        if getattr(self, "logo_title", None) is not None:
            acc = "#4fa87f" if name == "dark" else "#3f8f6b"
            self.logo_title.setText(
                f"iKun <span style='color:{acc}'>Insect Studio</span>")
        if getattr(self, "b_theme", None) is not None:
            self.b_theme.setText(self._t("to_light" if name == "dark" else "to_dark"))
            _fit_width(self.b_theme)
        if getattr(self, "list", None) is not None:
            d = self.list.itemDelegate()
            if isinstance(d, QueueDelegate):
                d._theme(name)
                self.list.viewport().update()
        if getattr(self, "preview", None) is not None:
            self.preview.set_theme(name == "dark")
        for cb in (getattr(self, "cb_crop_model", None), getattr(self, "cb_ev_model", None)):
            if isinstance(cb, ArrowCombo):
                cb.set_theme(name == "dark")
        if hasattr(self, "about"):
            self.about.setHtml(self._about_html())
        self._update_legend()

    def _toggle_theme(self):
        """切主题：先把当前画面抓成一张图盖在上面，再让它 0.2 秒淡出。"""
        target = "light" if self._theme == "dark" else "dark"
        try:
            shot = self.grab()
        except Exception:      # noqa: BLE001
            self._apply_theme(target)
            return
        self._apply_theme(target)
        ov = QLabel(self)
        ov.setPixmap(shot)
        ov.setGeometry(self.rect())
        ov.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        ov.setScaledContents(True)
        ov.raise_()
        ov.show()
        eff = QGraphicsOpacityEffect(ov)
        ov.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(200)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.InOutQuad)
        anim.finished.connect(ov.deleteLater)
        anim.start(QAbstractAnimation.DeleteWhenStopped)
        self._fade_anim = anim          # 保持引用，不然会被回收

    def _apply_lang(self, name):
        name = name if name in TEXT else "zh"
        if name == self._lang:
            return
        self._lang = name
        self.cfg.update(lang=name)
        self._retranslate()

    def _toggle_lang(self):
        self._apply_lang("en" if self._lang == "zh" else "zh")

    def _retranslate(self):
        self.setWindowTitle(self._t("title"))
        self.logo_sub.setText(self._t("subtitle"))
        for lay, key in self._top_groups:
            lay._label.setText(self._t(key))

        for cb, key, n in ((self.cb_mode, "modes", 3), (self.cb_seg, "segs", 2),
                           (self.cb_policy, "policies", 3)):
            idx = cb.currentIndex()
            cb.blockSignals(True)
            cb.clear()
            cb.addItems(self._t(key))
            cb.setCurrentIndex(min(idx, n - 1))
            cb.blockSignals(False)

        self.b_lang.setText(self._t("lang"))
        self.b_lang.setToolTip(self._t("lang_tip"))
        _fit_width(self.b_lang)                 # 中文/英文都重新量宽度
        self.b_theme.setText(self._t("to_light" if self._theme == "dark" else "to_dark"))
        _fit_width(self.b_theme)
        _fit_combo(self.cb_policy)
        _fit_combo(self.cb_mode)
        self.b_start.setText(self._t("start"))
        self.b_pause.setText(self._t("resume") if self.engine.paused else self._t("pause"))

        self.tabs.setTabText(0, self._t("tab_process"))
        self.tabs.setTabText(1, self._t("tab_train"))
        self.tabs.setTabText(2, self._t("tab_about"))

        self.l_queue.setText(self._t("queue"))
        self.b_add_dir.setText(self._t("add_dir"))
        self.b_add_files.setText(self._t("add_files"))
        self.b_clear.setText(self._t("clear"))
        self.l_hint.setText(self._t("drop"))
        self.chk_prev.setText(self._t("realtime"))
        self.l_slow.setText(self._t("slow_hint"))
        self.l_slow.setText(self._t("slow_hint"))
        self.chk_ev.setText(self._t("ev_prev"))
        self.chk_ev.setToolTip(self._t("ev_prev_tip"))
        self.l_xmp.setText(self._t("xmp"))
        self.cb_policy.setToolTip(self._t("policy_tip"))
        self.l_edit.setText(self._t("edit_hint"))
        self.l_edit.setToolTip(self._t("edit_tip"))
        self.b_commit.setText(self._t("commit"))
        self.b_cancel.setText(self._t("cancel"))
        self.l_sheet.setText(self._t("sheet"))
        self.l_sheetn.setText(self._t("sheet_n", n=self.grid.count()))
        self.b_export.setText(self._t("export"))
        self.b_open.setText(self._t("open_dir"))
        if self.preview._pm is None:
            self.preview.set_text(self._t("ph"))
        if self._tasks:
            self._update_strip()

        self.l_intro.setText(self._t("intro"))
        self.box_models.setTitle(self._t("models_group"))
        self.l_crop_model.setText(self._t("model_crop"))
        self.l_ev_model.setText(self._t("model_ev"))
        self.b_crop_import.setText(self._t("model_import"))
        self.b_ev_import.setText(self._t("model_import"))
        self.b_open_models.setText(self._t("model_open"))
        self.l_model_note.setText(self._t("model_note"))
        self.l_model_note.setToolTip(self._t("model_note_tip"))
        self.box_train.setTitle(self._t("train_group"))
        self.l_train_dirs.setText(self._t("train_dirs"))
        self.b_add_train.setText(self._t("add_train"))
        self.b_del_train.setText(self._t("del_train"))
        self.b_clear_train.setText(self._t("clear_train"))
        self.t_go.setText(self._t("train_go"))
        self.l_train_note.setText(self._t("train_note"))
        self.box_head.setTitle(self._t("head_group"))
        self.b_refit.setText(self._t("head_refit"))
        self.b_head_csv.setText(self._t("head_csv"))
        self.b_head_clear.setText(self._t("head_clear"))
        self.l_head_note.setText(self._t("head_note"))
        self.l_maint.setText(self._t("reset_note"))
        self.b_reset.setText(self._t("reset_btn"))
        self._refresh_models()
        try:
            self.l_speed.setText(self._t("speed_na"))
            self.l_eta.setText(self._t("eta_na"))
        except Exception:      # noqa: BLE001
            pass
        self.about.setHtml(self._about_html())
        try:
            from app.version import VERSION
            self.l_ver.setText(self._t("ver_now", v=VERSION))
            if not self.l_upd.text():
                pass
        except Exception:      # noqa: BLE001
            pass
        if not self._tasks:
            self.l_cur.setText(self._t("no_sel"))
        self.l_hint.setText(self._t("drop"))
        self._refresh_train_list()
        self._update_legend()
        self._refresh_list()
        self._refresh_head()
        # 切语言会让不少控件的 sizeHint 变；强制重排一次，别等下一次重绘
        self.tabs.tabBar().update()
        self.tabs.tabBar().adjustSize()
        if self.centralWidget() is not None and self.centralWidget().layout():
            self.centralWidget().layout().activate()
        self.status.showMessage(self._t("ready"))

    def _update_legend(self):
        if not hasattr(self, "legend_layout"):
            return
        while self.legend_layout.count():
            it = self.legend_layout.takeAt(0)
            w = it.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        text_color = "#93a09b" if self._theme == "dark" else "#4f5b56"
        labels = self._t("legend")
        for (color, dot), text in zip(((C_MASK, "&#9679;"), (C_FULL, "&#9679;"),
                                       (C_CORE, "&#9679;"), (C_CROP, "&#9679;"),
                                       (C_HEAD, "&#9678;")), labels):
            lab = QLabel(
                f'<span style="color:{color};font-size:13px;">{dot}</span>'
                f'<span style="color:{text_color};font-size:11px;"> {text}</span>')
            lab.setTextFormat(Qt.RichText)
            lab.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
            self.legend_layout.addWidget(lab)

    # ---------------------------------------------------------------- 列表
    def _on_paths(self, paths):
        n = self.engine.add_paths(paths)
        self._refresh_list()
        self.status.showMessage(self._t("added", n=n), 4000)

    def _refresh_list(self):
        with self.engine.lock:
            tasks = list(self.engine.tasks)
        self._tasks = tasks[:2000]
        self._total_seen = len(tasks)
        if len(self._tasks) != self.list.count():
            sb = self.list.verticalScrollBar()
            pos = sb.value()
            self.list.clear()
            for t in self._tasks:
                it = QListWidgetItem(os.path.basename(t.path))
                it.setToolTip(t.path)
                self.list.addItem(it)
            sb.setValue(pos)
        self.l_count.setText(self._t("count", n=len(tasks)))

    def _select_row(self, row, by_user=True):
        """所有「选中某一张」的入口统一走这里。"""
        if row < 0 or row >= len(self._tasks):
            return
        self.list.setCurrentRow(row)
        item = self.list.item(row)
        if item is not None:
            self.list.scrollToItem(item, QAbstractItemView.EnsureVisible)
        self._show_task(self._tasks[row])
        self._sync_grid(row)

    def _on_item_clicked(self, item):
        self._select_row(self.list.row(item))

    def _on_row_changed(self, row):
        """键盘方向键或程序改 currentRow 时同步右侧（跟随时被 blockSignals 屏蔽）。"""
        if row < 0 or row >= len(self._tasks) or row == self._last_row_shown:
            return
        self._show_task(self._tasks[row])
        self._sync_grid(row)

    def _on_grid_clicked(self, item):
        row = item.data(Qt.UserRole)
        if row is not None:
            self._select_row(int(row))

    def _sync_grid(self, row):
        if row < 0 or row >= len(self._tasks):
            return
        path = self._tasks[row].path
        for i in range(self.grid.count()):
            it = self.grid.item(i)
            if it.data(Qt.UserRole + 1) == path:
                sb = self.grid.verticalScrollBar()
                pos = sb.value()
                self.grid.blockSignals(True)
                self.grid.setCurrentItem(it)
                sb.setValue(pos)          # 选中但不抢滚动条：右侧不乱跳
                self.grid.blockSignals(False)
                break

    def _show_task(self, t):
        self._toast_until = 0          # 换照片了，上一张的提交提示该走了
        row = self.list.currentRow()
        if 0 <= row < len(self._tasks):
            self._last_row_shown = row
        self._update_strip(t)
        # 处理完、且带裁切结果的，进入手动微调
        if t.result and t.result.get("crop") and t.result.get("core") \
                and not t.result.get("error"):
            self._begin_edit(t)
            return
        self._end_edit()
        self._preview_pin = t.path
        self._last_preview = None
        r = t.result or {}
        fp = os.path.join(CACHE_DIR, r.get("preview") or "") if r.get("preview") else ""
        if fp and os.path.exists(fp):
            self.preview.set_image(fp)      # 失败的那张：带红框 / 无几何的原图
            self.status.showMessage(self._t("click_prev", n=os.path.basename(t.path)), 3000)
            return
        pm = self._thumb(t.path)
        if pm is not None:
            self.preview.set_pixmap(pm)
            self.status.showMessage(self._t("click_prev", n=os.path.basename(t.path)), 3000)

    def _update_strip(self, t=None):
        if t is None:
            row = self.list.currentRow() if hasattr(self, "list") else -1
            t = self._tasks[row] if 0 <= row < len(self._tasks) else None
        if t is None:
            self.l_cur.setText(self._t("no_sel"))
            self.l_metrics.setText("")
            self._set_state("")
            return
        self.l_cur.setText(f"{self._t('cur')}：{os.path.basename(t.path)}")
        r = t.result or {}
        bit = []
        if r.get("skipped"):
            self.l_metrics.setText(t.meta or "")
            self._set_state(self._t("st_manual") if r.get("skip_reason") == "manual"
                            else self._t("st_skip"))
            return
        if r.get("error"):
            self.l_metrics.setText("")
            self._set_state(self._t("st_fail"), "#b3454f")
            return
        if not r:
            self.l_metrics.setText("　".join([x for x in (t.meta or "",
                                                          self._t("none_yet")) if x]))
            self._set_state("")
            return
        ev = r.get("ev")
        bit.append(f"{self._t('m_ev')} {ev:+.2f}" if isinstance(ev, (int, float))
                   else f"{self._t('m_ev')} —")
        for k, lab in (("L_in", "m_in"), ("L_box", "m_box")):
            v = r.get(k)
            bit.append(f"{self._t(lab)} {v:.0f}" if isinstance(v, (int, float))
                       else f"{self._t(lab)} —")
        w = r.get("w")
        bit.append(f"{self._t('m_w')} {w:.3f}" if isinstance(w, (int, float))
                   else f"{self._t('m_w')} —")
        sh = r.get("sharp")
        bit.append(f"{self._t('m_sh')} {sh}" if sh is not None else
                   f"{self._t('m_sh')} {self._t('no_write')}")
        o = r.get("origin")
        if o in ("auto", "manual", "none"):
            bit.append(f"{self._t('m_origin')} {self._t('o_' + o)}")
        self.l_metrics.setText("　".join(bit))
        warn = r.get("coef_warn") or r.get("ev_warn")
        if warn:
            self._set_state(self._t("st_fallback"), "#c98a2a")
            self.l_state.setToolTip(str(warn))
        else:
            self.l_state.setToolTip("")
            self._set_state(self._t("st_edit") if r.get("manual_crop")
                            else self._t("st_ok"),
                            "#c98a2a" if r.get("manual_crop") else None)

    def _set_state(self, text, color=None):
        """状态位。toast 还没过期就让它待着（换选中行会立刻清掉）。"""
        if time.time() < getattr(self, "_toast_until", 0):
            return
        self._toast_until = 0
        self.l_state.setStyleSheet(f"color:{color};font-weight:600;" if color else "")
        self.l_state.setText(text)

    def _toast(self, text, ms=9000, color="#2f7d5c"):
        """在「当前」那一行临时显示一句反馈，比状态栏显眼。"""
        self._toast_until = time.time() + ms / 1000.0
        self._toast_text = text
        self.l_state.setStyleSheet(f"color:{color};font-weight:600;")
        self.l_state.setText(text)

    # ---------------------------------------------------------------- 手动微调
    def _preview_dbl(self):
        """双击：没标头就进微调，并把焦点放在头点上。"""
        if self.preview.is_editing():
            return
        row = self.list.currentRow()
        if not (0 <= row < len(self._tasks)):
            return
        t = self._tasks[row]
        if (t.result or {}).get("head_xy"):
            return
        self._begin_edit(t)
        try:
            self.preview._active = "head"
            self.preview.update()
        except Exception:      # noqa: BLE001
            pass
        self.status.showMessage(self._t("head_dbl_hint"), 5000)

    def _begin_edit(self, t):
        if self._edit_task is t:
            return
        self._end_edit()
        r = t.result or {}
        # 带掩膜的底图（没有掩膜就退回原图），点开就能确认它认对了没有
        pm = None
        try:
            ev_show = r.get("ev") if self.cfg.get("preview_exposure", True) else None
            pm = pil_to_pixmap(self.engine.edit_base(t.path, r, ev=ev_show))
        except Exception:      # noqa: BLE001
            pm = self._thumb(t.path)
        if pm is None:
            self.status.showMessage(self._t("click_prev", n=os.path.basename(t.path)), 4000)
            return
        head = tuple(r["head_xy"]) if r.get("head_xy") else None
        self.preview.set_edit(pm, tuple(r["core"]), tuple(r["full"]),
                              tuple(r["crop"]), head)
        self._edit_task = t
        self._edit_dirty = False
        self._preview_pin = t.path
        self._last_preview = None
        self.edit_bar.show()
        self.status.showMessage(self._t("edit_hint"), 6000)

    def _on_edit_changed(self, kind):
        self._edit_dirty = True
        if kind == "crop" or self._edit_task is None:
            return
        r = self._edit_task.result
        core = self.preview.box("core")
        full = self.preview.box("full")
        head = self.preview.box("head")
        if not core or not full:
            return
        try:
            J = crop_v3.load(self.cfg.get("coef")) if self.cfg.get("coef") else None
            cr = crop_v3.compute_crop(tuple(core), tuple(full), head,
                                      multi=(r.get("nsub", 1) > 1), J=J)
            self.preview.set_crop(cr["crop"])
        except Exception:  # noqa: BLE001
            pass

    def _commit_edit(self):
        t = self._edit_task
        if not t:
            return
        crop = self.preview.box("crop")
        if not crop:
            return
        head = self.preview.box("head")
        core = self.preview.box("core")
        full = self.preview.box("full")
        try:
            self.engine.commit_crop(t.path, crop, head=head, core=core, full=full)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "", str(e))
            return
        self._update_strip(t)          # 先刷新数字，再盖提示，否则提示会被刷掉
        lr = (t.result or {}).get("learned") if t.result else None
        if lr and lr.get("n"):
            self._toast(self._t("learned_toast", n=lr["n"]), 12000)
            self._refresh_head()
        else:
            self._toast(self._t("edit_done"), 6000)
        self._end_edit(keep_pin=True)

    def _cancel_edit(self):
        self._end_edit(keep_pin=True)

    def _end_edit(self, silent=False, keep_pin=False):
        was_dirty = bool(getattr(self, "_edit_dirty", False))
        task = getattr(self, "_edit_task", None)
        if task is None and not self.preview.is_editing():
            return
        self._edit_task = None
        self._edit_dirty = False
        self.preview.clear_edit()
        if hasattr(self, "edit_bar"):
            self.edit_bar.hide()
        if keep_pin and task is not None:
            # 留在这一张上：显示它最新的定稿图，别跳回正在跑的那张
            r = task.result or {}
            fp = os.path.join(CACHE_DIR, r["preview"]) if r.get("preview") else ""
            if fp and os.path.exists(fp):
                self.preview.set_image(fp)
                self._last_preview = "pinned"
            self._preview_pin = task.path
        else:
            self._preview_pin = None
            self._last_preview = None
        if was_dirty and not silent and not keep_pin:
            self.status.showMessage(self._t("edit_discard"), 4000)

    def _thumb(self, path):
        pm = self._thumbs.get(path)
        if pm is not None:
            return pm
        try:
            im = rawio.preview_thumb(path, 1200)
            pm = pil_to_pixmap(im)
        except Exception:  # noqa: BLE001
            return None
        if len(self._thumbs) > 6:
            self._thumbs.pop(next(iter(self._thumbs)))
        self._thumbs[path] = pm
        return pm

    # ---------------------------------------------------------------- 动作
    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, self._t("pick_dir"))
        if d:
            self._on_paths([d])

    def _pick_files(self):
        fs, _ = QFileDialog.getOpenFileNames(
            self, self._t("pick_files"), "",
            "Images (*.nef *.nrw *.dng *.cr2 *.cr3 *.arw *.raf *.orf *.rw2 *.pef "
            "*.jpg *.jpeg *.tif *.tiff *.png *.bmp)")
        if fs:
            self._on_paths(fs)

    def _clear(self):
        if self.engine.running:
            QMessageBox.information(self, "", self._t("msg_running"))
            return
        self.engine.clear()
        self._end_edit(silent=True)
        self._tasks = []
        self._thumbs.clear()
        self._preview_pin = None
        self._last_preview = None
        self._sheet_sig = None
        self._refresh_list()
        self.grid.clear()
        self.l_sheetn.setText(self._t("sheet_n", n=0))
        self.preview.clear_image()
        self.preview.set_text(self._t("ph"))
        self._update_strip()

    @staticmethod
    def _short(name, n):
        return name if len(name) <= n else name[: n - 1] + "…"

    def _preview_toggle(self):
        self.cfg.update(preview_enabled=self.chk_prev.isChecked())

    def _evprev_toggle(self):
        """开关一变，当前这张立刻重画——不然看着就像没生效。"""
        on = self.chk_ev.isChecked()
        self.cfg.update(preview_exposure=on)
        self._last_preview = None      # 处理中的下一帧也按新设置
        t = self._edit_task
        if t is None or not self.preview.is_editing():
            # 不在微调里：把当前正在看的那张按新开关重画一遍
            path = self._preview_pin
            if not path:
                it = self.list.currentItem()
                if it is not None:
                    path = it.data(Qt.UserRole + 1)       # 列表里路径存在 UserRole+1
                    if not path:
                        row = it.data(Qt.UserRole)
                        if isinstance(row, int) and 0 <= row < len(self.engine.tasks):
                            path = self.engine.tasks[row].path
            if path:
                ev = None
                try:
                    task = next((x for x in self.engine.tasks if x.path == path), None)
                    if task is not None and task.result and on:
                        ev = task.result.get("ev")
                except Exception:      # noqa: BLE001
                    ev = None
                fp = self.engine.refresh_ev(path, ev)
                if fp:
                    self.preview.set_image(fp)
                    self._last_preview = "pinned"
            return
        # 保留已经拖过的框，只换底图
        keep = {k: self.preview.box(k) for k in ("crop", "core", "full", "head")}
        dirty = self._edit_dirty
        r = t.result or {}
        try:
            ev = r.get("ev") if on else None
            pm = pil_to_pixmap(self.engine.edit_base(t.path, r, ev=ev))
        except Exception:      # noqa: BLE001
            return
        if pm is None or keep["crop"] is None:
            return
        self.preview.set_edit(pm, keep["core"], keep["full"], keep["crop"], keep["head"])
        self._edit_dirty = dirty
        self.status.showMessage(self._t("ev_prev_on" if on else "ev_prev_off"), 4000)

    def _policy_changed(self):
        pol = ("protect", "skip_all", "force")[self.cb_policy.currentIndex()]
        self.cfg.update(xmp_policy=pol)

    def _set_follow(self, on):
        self.chk_follow.blockSignals(True)
        self.chk_follow.setChecked(bool(on))
        self.chk_follow.blockSignals(False)
        self.cfg.update(follow=bool(on))
        if on:
            self._preview_pin = None      # 恢复跟随：不再定格在手动点的那张
            self._last_preview = None

    def _cfg_changed(self):
        mode = ["both", "crop", "exposure"][self.cb_mode.currentIndex()]
        seg = 768 if self.cb_seg.currentIndex() == 0 else 512
        dev = "cuda" if self.cb_dev.currentIndex() == 0 else "cpu"
        self.cfg.update(mode=mode, seg_size=seg, device=dev)

    def _start(self):
        if not self.engine.tasks:
            self.status.showMessage(self._t("msg_empty"), 4000)
            return
        self._end_edit(silent=True)
        if self.chk_follow.isChecked():
            self._preview_pin = None
        self.engine.ping()
        warm = self.engine.status().get("warm", {})
        self.engine.start()
        self.status.showMessage(
            self._t("warm_wait") if warm.get("state") == "loading" else self._t("start"),
            6000 if warm.get("state") == "loading" else 3000)

    def _pause(self):
        if self.engine.paused:
            self.engine.start()
        else:
            self.engine.pause()

    # ---------------------------------------------------------------- 训练
    def _norm_train_dirs(self, raw):
        """老配置里是字符串，新配置是 {dir, files}；统一成后者。"""
        out = []
        for r in raw or []:
            if isinstance(r, dict):
                d = r.get("dir") or ""
                out.append({"dir": d, "files": list(r.get("files") or []),
                            "n": r.get("n")})
            elif isinstance(r, str) and r:
                out.append({"dir": r, "files": [], "n": None})
        return out

    def _count_dir(self, d):
        try:
            from app import rawio
            return len(rawio.scan_image_dir(d, self.cfg.get("recursive")))
        except Exception:      # noqa: BLE001
            return 0

    def _refresh_train_list(self):
        self.train_list.clear()
        for e in self._train_dirs:
            if e.get("files"):
                n = len(e["files"])
            else:
                if e.get("n") is None:
                    e["n"] = self._count_dir(e["dir"])
                n = e["n"]
            name = os.path.basename(e["dir"].rstrip("\\/")) or e["dir"]
            it = QListWidgetItem()
            it.setToolTip(f"{e['dir']}\n" + (self._t("train_tip_files", n=n) if e.get("files")
                                              else self._t("train_tip_dir", n=n)))
            it.setSizeHint(QSize(120, 26))
            self.train_list.addItem(it)
            holder = QWidget()
            hb = QHBoxLayout(holder)
            hb.setContentsMargins(4, 0, 2, 0)
            hb.setSpacing(4)
            lab = QLabel(self._t("train_row", name=name, n=n))
            hb.addWidget(lab, 1)
            btn = QToolButton()
            btn.setText("×")
            btn.setObjectName("ghost")
            btn.setFixedSize(20, 20)
            btn.setToolTip(self._t("train_remove"))
            btn.clicked.connect(lambda _=False, d=e["dir"]: self._remove_train_dir(d))
            hb.addWidget(btn)
            self.train_list.setItemWidget(it, holder)
        self.cfg.update(train_dirs=[{"dir": e["dir"], "files": e.get("files") or []}
                                    for e in self._train_dirs])

    def _pick_train_dir(self):
        d = QFileDialog.getExistingDirectory(self, self._t("pick_train"))
        if d:
            d = os.path.normpath(d)
            if d not in {e["dir"] for e in self._train_dirs}:
                self._train_dirs.append({"dir": d, "files": [], "n": None})
                self._refresh_train_list()

    def _add_train_paths(self, paths):
        """文件夹 → 整个文件夹；照片 → 只训练被拖进来的这几张。"""
        from app import rawio
        buckets, touched = {}, 0
        for p in paths:
            p = os.path.normpath(p)
            if os.path.isdir(p):
                buckets.setdefault(p, None)      # None = 整个文件夹
            elif os.path.isfile(p) and rawio.is_image(p):
                buckets.setdefault(os.path.dirname(p), set())
                if buckets[os.path.dirname(p)] is not None:
                    buckets[os.path.dirname(p)].add(p)
        by_dir = {e["dir"]: e for e in self._train_dirs}
        for d, fs in buckets.items():
            e = by_dir.get(d)
            if e is None:
                e = {"dir": d, "files": [], "n": None}
                self._train_dirs.append(e)
                by_dir[d] = e
            if fs is None:                        # 整个文件夹覆盖前面的挑图
                e["files"] = []
                e["n"] = None
            else:
                merged = set(e.get("files") or []) | fs
                e["files"] = sorted(merged)
            touched += 1
        if touched:
            self._refresh_train_list()
            self.status.showMessage(self._t("train_added", n=touched), 5000)
        else:
            self.status.showMessage(self._t("train_added_dup"), 4000)

    def _remove_train_dir(self, d):
        key = os.path.normcase(os.path.normpath(d))
        self._train_dirs = [e for e in self._train_dirs
                            if os.path.normcase(os.path.normpath(e["dir"])) != key]
        self._refresh_train_list()

    def _toggle_pause_train(self):
        paused = self.trainer.toggle_pause()
        self.b_pause_train.setText(self._t("train_resume" if paused else "train_pause"))

    def _del_train_dir(self):
        row = self.train_list.currentRow()
        if 0 <= row < len(self._train_dirs):
            self._train_dirs.pop(row)
            self._refresh_train_list()

    def _clear_train_dirs(self):
        if not self._train_dirs:
            return
        if QMessageBox.question(
                self, self._t("train_clear_title"), self._t("train_clear_ask", n=len(self._train_dirs)),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self._train_dirs = []
        self._refresh_train_list()

    def _train(self):
        if not self._train_dirs:
            QMessageBox.warning(self, "", self._t("msg_need_dir"))
            return
        self._train_switched = False
        ok, msg = self.trainer.start([dict(e) for e in self._train_dirs])
        if not ok:
            QMessageBox.information(self, "", msg)

    # ---------------------------------------------------------------- 恢复初始状态
    def _factory_reset(self):
        """测试用：把 data/ 清空，回到第一次装好的样子。"""
        if self.engine.running:
            QMessageBox.information(self, "", self._t("reset_busy"))
            return
        from app import reset as _reset
        inv = _reset.inventory()
        names = "、".join(i["name"] for i in inv["items"]) or ("(empty)" if self._lang == "en" else "（空）")
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(self._t("reset_btn").rstrip("…"))
        box.setText(self._t("reset_ask", n=len(inv["items"]),
                            mb=inv["bytes"] / 1e6, names=names))
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        if box.exec() != QMessageBox.Yes:
            return
        self.engine.stop()
        self._end_edit(silent=True)
        _reset.wipe()
        self._reload_defaults()
        self.status.showMessage(self._t("reset_done"), 12000)

    def _reload_defaults(self):
        """把界面和内存里的配置都拉回 DEFAULTS（配合 _factory_reset）。"""
        from app.config import CFG_VER, DEFAULTS
        import copy
        self.cfg._d = copy.deepcopy(DEFAULTS)
        self.cfg._d["wb_enable"] = False
        self.cfg._d["_v"] = CFG_VER
        self.cfg.save()

        # 队列 / 预览 / 缩略图墙
        self.engine.clear()
        self._tasks = []
        self._thumbs.clear()
        self._preview_pin = None
        self._last_preview = None
        self._sheet_sig = None
        self._last_row_shown = -1
        self._refresh_list()
        self.grid.clear()
        self.l_sheetn.setText(self._t("sheet_n", n=0))
        self.preview.clear_image()
        self.preview.set_text(self._t("ph"))
        self._update_strip()
        self.pbar.setValue(0)
        self.l_done.setText("0 / 0")
        self.l_speed.setText(self._t("speed_na"))
        self.l_eta.setText(self._t("eta_na"))

        # 控件回默认
        for cb, idx in ((self.cb_mode, 0), (self.cb_seg, 0),
                        (self.cb_dev, 0), (self.cb_policy, 0)):
            cb.blockSignals(True)
            cb.setCurrentIndex(idx)
            cb.blockSignals(False)
        for chk, val in ((self.chk_prev, True), (self.chk_follow, True)):
            chk.blockSignals(True)
            chk.setChecked(val)
            chk.blockSignals(False)

        self._lang = "zh"
        self._theme = "light"
        self._train_dirs = []
        self._refresh_train_list()
        self._refresh_models()
        self._refresh_head()
        self._apply_theme("light")
        self._retranslate()
        try:
            import time as _t
            if _t.time() - float(self.cfg.get("update_checked_at") or 0) > 86400:
                QTimer.singleShot(4000, lambda: self._check_update(True))
        except Exception:      # noqa: BLE001
            pass

    # ---------------------------------------------------------------- 模型（系数）
    def _refresh_models(self):
        for kind, cb, key in (("crop", self.cb_crop_model, "coef"),
                              ("ev", self.cb_ev_model, "ev_coef")):
            cur = self.cfg.get(key) or ""
            cb.blockSignals(True)
            cb.clear()
            for m in models.list_models(kind, en=self._lang == "en"):
                cb.addItem(m["label"], m["path"])
            idx = cb.findData(cur)
            if idx < 0 and cur:
                # 存的模型文件被删了：自动回落到内置，别留一个空指向
                cb.setCurrentIndex(0)
                self.cfg.update(**{key: cb.currentData() or ""})
            else:
                cb.setCurrentIndex(idx if idx >= 0 else 0)
            cb.blockSignals(False)

    def _model_changed(self, kind, cb):
        key = "coef" if kind == "crop" else "ev_coef"
        item = models.list_models(kind, en=self._lang == "en")
        i = cb.currentIndex()
        if 0 <= i < len(item) and item[i].get("broken"):
            QMessageBox.warning(self, "", item[i]["label"])
            idx = cb.findData(self.cfg.get(key) or "")
            cb.blockSignals(True)
            cb.setCurrentIndex(idx if idx >= 0 else 0)
            cb.blockSignals(False)
            return
        path = cb.currentData() or ""
        if path == (self.cfg.get(key) or ""):
            return
        self.cfg.update(**{key: path})
        self.status.showMessage(self._t("model_switched", n=cb.currentText()), 8000)

    def _import_model(self, kind):
        fs, _ = QFileDialog.getOpenFileNames(
            self, self._t("model_import"), "", "JSON (*.json)")
        last = ""
        for f in fs:
            try:
                last = models.import_file(kind, f)
            except Exception as e:      # noqa: BLE001
                QMessageBox.warning(self, "", self._t("model_import_bad", e=e))
        if last:
            self._refresh_models()
            cb = self.cb_crop_model if kind == "crop" else self.cb_ev_model
            idx = cb.findData(last)
            if idx >= 0:
                cb.setCurrentIndex(idx)
            self.status.showMessage(self._t("model_imported", n=os.path.basename(last)), 8000)

    def _open_models_dir(self):
        d = os.path.dirname(models.store_dir("crop"))
        os.startfile(d)                      # noqa: S606

    # ---------------------------------------------------------------- 头部修正
    def _refresh_head(self):
        st = head_fix.stats()
        n = st["n"]
        if n < 3:
            txt = self._t("head_off", n=n)
        elif st["mode"] == "linear":
            txt = self._t("head_linear", n=n, r=st.get("rmse") or 0.0)
        elif st["mode"] == "knn":
            txt = self._t("head_knn", n=n, dx=st.get("mean_dx", 0.0),
                          dy=st.get("mean_dy", 0.0))
        else:
            txt = self._t("head_none")
        self.l_head.setText(txt)

    def _refit_head(self):
        st = head_fix.stats()
        if st["n"] < head_fix.FIT_MIN:
            self.status.showMessage(self._t("refit_none", n=head_fix.FIT_MIN), 6000)
            return
        m = head_fix.fit()
        if m:
            self.status.showMessage(self._t("refit_done", n=m["n"], r=m["rmse"]), 9000)
        self._refresh_head()

    def _export_head(self):
        st = head_fix.stats()
        if not st.get("n"):
            self.status.showMessage(self._t("export_none_head"), 8000)
            return
        fp, _ = QFileDialog.getSaveFileName(self, self._t("export_head"),
                                            "head_fix.csv", "CSV (*.csv)")
        if not fp:
            return
        try:
            total, usable = head_fix.export_csv(fp)
        except Exception as e:      # noqa: BLE001
            QMessageBox.warning(self, "", str(e))
            return
        msg = self._t("export_head_ok", n=total, u=usable)
        self.status.showMessage(msg, 12000)

    def _clear_head(self):
        if QMessageBox.question(self, "", self._t("head_clear") + "?") != QMessageBox.Yes:
            return
        head_fix.clear()
        self._refresh_head()
        self.status.showMessage(self._t("head_cleared"), 6000)

    # ---------------------------------------------------------------- 拼版
    def _export_sheet(self):
        items = self.engine.export_items()
        if not items:
            self.status.showMessage(self._t("export_none"), 8000)
            return
        first = os.path.dirname(items[0]["path"])
        name = f"拼版_{time.strftime('%Y%m%d_%H%M')}.jpg" if self._lang == "zh" \
            else f"sheet_{time.strftime('%Y%m%d_%H%M')}.jpg"
        fp, _ = QFileDialog.getSaveFileName(self, self._t("export"),
                                            os.path.join(first, name), "JPEG (*.jpg)")
        if not fp:
            return
        payload = []
        for r in items:
            f = os.path.join(CACHE_DIR, r.get("preview") or "")
            payload.append(dict(r, _file=f if os.path.exists(f) else ""))
        title = f"{self._t('sheet_title')} · {time.strftime('%Y-%m-%d %H:%M')}"
        self.b_export.setEnabled(False)
        self.status.showMessage(self._t("exporting", a=0, b=len(payload)))
        w = SheetWorker(payload, fp, title, lang=self._lang,
                        resolver=self.engine.export_file, parent=self)
        w.done.connect(self._sheet_done)
        w.fail.connect(self._sheet_fail)
        self._sheet_worker = w
        w.start()

    def _sheet_done(self, paths):
        self.b_export.setEnabled(True)
        self._last_export = paths[0] if paths else ""
        self.status.showMessage(self._t("export_done", n=len(paths), p=paths[0]
                                        if paths else ""), 20000)

    def _sheet_fail(self, msg):
        self.b_export.setEnabled(True)
        self.status.showMessage(msg, 12000)

    def _open_output_dir(self):
        d = getattr(self, "_last_export", "")
        if d and os.path.exists(d):
            os.startfile(os.path.dirname(d))     # noqa: S606
            return
        items = self.engine.sheet_items()
        if items:
            os.startfile(os.path.dirname(items[0]["path"]))   # noqa: S606
        else:
            os.startfile(app_root())                            # noqa: S606

    # ---------------------------------------------------------------- 刷新
    def _refresh_grid(self):
        # 拼版为空时压成一条；有内容再展开。只做一次状态切换，
        # 用户亲手拖过之后一律不再自动改。
        try:
            now_empty = self.grid.count() == 0
            if (not getattr(self, "_sheet_user_dragged", False)
                    and now_empty != getattr(self, "_sheet_empty", None)):
                tot = sum(self.split_right.sizes()) or 700
                self.split_right.setSizes([max(200, tot - 56), 56] if now_empty
                                          else [max(260, tot - 230), 230])
            self._sheet_empty = now_empty
        except Exception:      # noqa: BLE001
            pass
        items = self.engine.sheet_items()
        sig = tuple((r.get("path"), r.get("preview")) for r in items)
        if sig == self._sheet_sig:
            return
        sel = self.list.currentRow()
        self._sheet_sig = sig
        rowmap = {t.path: i for i, t in enumerate(self._tasks)}
        self.grid.blockSignals(True)
        self.grid.clear()
        for r in items:
            fp = os.path.join(CACHE_DIR, r.get("preview") or "")
            if not os.path.exists(fp):
                continue
            it = QListWidgetItem(QIcon(fp), "")
            it.setToolTip(os.path.basename(r.get("path") or ""))
            it.setData(Qt.UserRole, rowmap.get(r.get("path")))
            it.setData(Qt.UserRole + 1, r.get("path"))
            self.grid.addItem(it)
        self.grid.blockSignals(False)
        self.l_sheetn.setText(self._t("sheet_n", n=self.grid.count()))
        if 0 <= sel < len(self._tasks):
            self._sync_grid(sel)

    def _row_of(self, path):
        for i, t in enumerate(self._tasks):
            if t.path == path:
                return i
        return None

    def _tick(self):
        if self.isVisible() and not self.isMinimized():
            self.engine.ping()
        st = self.engine.status()
        total, done, failed, skipped = (st["total"], st["done"],
                                        st["failed"], st["skipped"])
        finished = done + failed + skipped
        self.pbar.setMaximum(max(total, 1))
        self.pbar.setValue(finished)
        txt = self._t("done", d=finished, t=total)
        if failed:
            txt += self._t("fail", n=failed)
        if skipped:
            txt += self._t("skipn", n=skipped)
        self.l_done.setText(txt)
        if st["speed"]:
            spd = self._t("speed", v=st["speed"])
            pc = st.get("preview_cost") or 0
            if pc:
                spd += self._t("prev_cost", v=pc)
            self.l_speed.setText(spd)
        else:
            self.l_speed.setText(self._t("speed_na"))
        if st["eta"]:
            m, s = divmod(int(st["eta"]), 60)
            self.l_eta.setText(self._t("eta_hm", m=m, s=s) if m
                               else self._t("eta_s", s=s))
        else:
            self.l_eta.setText(self._t("eta_na"))

        self.b_pause.setText(self._t("resume") if st["paused"] else self._t("pause"))
        if st["total"] != self._total_seen:
            self._refresh_list()

        # ---- 跟随正在处理的这张：选中 + 滚到可见；左栏上方同时显示文件名
        cur = st.get("current")
        if cur:
            name = os.path.basename(cur)
            self.l_hint.setText(self._t("now", n=self._short(name, 26)))
        elif st.get("warm", {}).get("state") == "loading":
            self.l_hint.setText(self._t("warming"))
        else:
            self.l_hint.setText(self._t("drop"))
        if (cur and st.get("running") and self.chk_follow.isChecked()
                and not self.preview.is_editing()):
            row = self._row_of(cur)
            if row is not None and self.list.currentRow() != row:
                self.list.blockSignals(True)
                self.list.setCurrentRow(row)
                self.list.blockSignals(False)
                item = self.list.item(row)
                if item is not None:
                    self.list.scrollToItem(item, QAbstractItemView.EnsureVisible)
                self._sync_grid(row)
                # 跟随时不进入微调，只显示这一张的叠加图
        self.list.viewport().update()

        # ---- 缩略图墙
        self._refresh_grid()

        # ---- 大图：只在「跟随」或「定格的就是这一张」时换图，绝不回头翻旧结果
        if not self.preview.is_editing():
            follow = self.chk_follow.isChecked()
            live = self.engine.live_preview()
            name = live.get("name")
            if name and (follow or (self._preview_pin and live.get("path") == self._preview_pin)):
                if name != self._last_preview:
                    # engine 给的是绝对路径（定稿图在 cache/ 子目录）
                    fp = name if os.path.isabs(name) else os.path.join(PREVIEW_DIR, name)
                    if os.path.exists(fp):
                        self.preview.set_image(fp)
                        self._last_preview = name

        # 当前这张的数字（跟着选中行走，不跟正在处理的走）
        row = self.list.currentRow()
        if 0 <= row < len(self._tasks):
            self._update_strip(self._tasks[row])
        elif cur:
            r = self._row_of(cur)
            if r is not None:
                self._update_strip(self._tasks[r])

        ts = self.trainer.status()
        if ts["state"] in ("scan", "extract", "fit"):
            self._train_done_seen = False
        if ts["state"] != "idle":
            self.t_pbar.setValue(int(ts["progress"]))
            log = "\n".join(ts["log"])
            if log != self.t_log.toPlainText():
                self.t_log.setPlainText(log)
                self.t_log.verticalScrollBar().setValue(
                    self.t_log.verticalScrollBar().maximum())
            if ts["state"] == "done" and not getattr(self, "_train_switched", False):
                rep = ts.get("report") or {}
                got = []
                for kind, key in (("crop", "coef"), ("ev", "ev_coef")):
                    path = (rep.get(kind) or {}).get("adopted")
                    if path:
                        self.cfg.update(**{key: path})
                        got.append(os.path.basename(path))
                if got:
                    self._train_switched = True
                    self._refresh_models()
                    self._toast(self._t("model_auto_switched", n="、".join(got)), 12000)
            if ts["state"] == "done":
                self.status.showMessage(self._t("train_done", p=ts["out_dir"]), 15000)
                if not getattr(self, "_train_done_seen", False):
                    self._train_done_seen = True
                    self._refresh_models()

    # ---------------------------------------------------------------- 拖入（整窗）
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self._on_paths(paths)
        e.acceptProposedAction()

    # ---------------------------------------------------------------- 窗口事件
    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == e.Type.WindowStateChange:
            if self.isMinimized():
                self.status.showMessage(self._t("mini_note"), 3000)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if getattr(self, "train_page", None) is not None:
            self._fit_train_page()

    def _restore_split(self):
        """恢复上次拖出来的两处分栏宽度。"""
        try:
            sm = self.cfg.get("split_main")
            self.split_main.setSizes(sm if isinstance(sm, list) and len(sm) == 2
                                     else [520, 900])
            sr = self.cfg.get("split_right")
            self.split_right.setSizes(sr if isinstance(sr, list) and len(sr) == 2
                                      else [640, 220])
        except Exception:      # noqa: BLE001
            pass

    def _on_sheet_dragged(self, *args):
        """用户亲手拖过拼版分隔条：从此不再自动收起/展开，免得"一拖就弹回去"。"""
        self._sheet_user_dragged = True
        self._save_split()

    def _save_split(self):
        try:
            self.cfg.update(split_main=list(self.split_main.sizes()),
                            split_right=list(self.split_right.sizes()))
        except Exception:      # noqa: BLE001
            pass

    def closeEvent(self, e):
        self._save_split()
        self.engine.stop()
        super().closeEvent(e)



def _combo_qss(b64):
    return f"""
QComboBox {{ padding-right: 26px; }}
QComboBox::drop-down {{ width: 0px; border: none; }}
QComboBox::down-arrow {{ image: none; width: 0px; height: 0px; }}
QToolButton#dropdown {{ border: none; background: transparent; color: #2f7d5d;
    font-size: 11px; font-weight: 700; padding: 0 2px; }}
QToolButton#dropdown:hover {{ background: rgba(63,143,107,0.12); border-radius: 4px; }}
"""


COMBO_QSS = {"light": _combo_qss("iVBORw0KGgoAAAANSUhEUgAAABQAAAAMCAYAAABiDJ37AAAAQ0lEQVR4nGNgGHGAEV3Avj/7P6mGHCycCjeHCZ8kqYZhNZAUQ7GpYyJFMTHyTORowmcZEz4DsWkmNYwZcAFyYn9wAgB7uBgUmiRU4gAAAABJRU5ErkJggg=="), "dark": _combo_qss("iVBORw0KGgoAAAANSUhEUgAAABQAAAAMCAYAAABiDJ37AAAAQ0lEQVR4nGNgGHGAEV2g4sSC/6Qa0mGRADeHCZ8kqYZhNZAUQ7GpYyJFMTHyTORowmcZEz4DsWkmNYwZcAFyYn9wAgDPkhI1y7sPcQAAAABJRU5ErkJggg==")}

THEMES = {}

THEMES["dark"] = """
* { outline: none; }
QWidget#root, QMainWindow { background:#0f1412; }
QWidget#trainpage { background:#0f1412; }

QFrame#topbar { background:#161b19; border:1px solid #242b28; border-radius:10px; }
QLabel#logo { color:#e9efeb; }
QLabel#subtitle { color:#7f8c86; font-size:10px; letter-spacing:0.4px; }
QLabel#fieldLabel { color:#8b9793; font-size:12px; }
QLabel#cardTitle { color:#dde5e0; font-size:14px; font-weight:600; }
QLabel#counter { color:#8b9793; font-size:12px; }
QLabel#hint { color:#8b9793; font-size:12px; }
QLabel#stat { color:#a3afaa; font-size:12px; }
QLabel#curName { color:#dde5e0; font-size:12px; font-weight:600; }

QFrame#card { background:#161b19; border:1px solid #242b28; border-radius:10px; }
QLabel#preview { background:#0b0f0d; border:1px solid #242b28; border-radius:8px;
    color:#8b9793; font-size:13px; }

QTabWidget::pane { border:none; background:transparent; }
QTabBar::tab { background:transparent; color:#93a09b; padding:8px 18px;
    margin-right:4px; border-radius:7px; font-size:13px; }
QTabBar::tab:hover { color:#c7d2cc; background:#171d1a; }
QTabBar::tab:selected { color:#eaf4ee; background:#1d2422; }

QPushButton { background:#1d2422; border:1px solid #2b3231; padding:7px 16px;
    border-radius:7px; color:#cdd8d2; font-size:13px; }
QPushButton:hover { background:#242b28; border-color:#3d4542; }
QPushButton:pressed { background:#191f1d; }
QPushButton#primary { background:#4fa87f; border:1px solid #5ec08f; color:#0d1a14;
    font-weight:600; }
QPushButton#primary:hover { background:#5ec08f; }
QPushButton#ghost { background:transparent; border:1px solid #2b3231; color:#a3afaa; }
QPushButton#ghost:hover { background:#1d2422; color:#d3ddd7; }
QPushButton:disabled { color:#5c6663; border-color:#242b28; }

QComboBox { background:#191f1d; border:1px solid #2b3231; padding:6px 8px;
    border-radius:7px; color:#cdd8d2; min-width:86px; }
QComboBox:hover { border-color:#3d4542; }
QComboBox::drop-down { border:none; width:18px; }
QComboBox QAbstractItemView { background:#191f1d; border:1px solid #2b3231;
    selection-background-color:#26453a; selection-color:#eaf4ee; color:#cdd8d2; padding:4px; }

QLineEdit { background:#191f1d; border:1px solid #2b3231; padding:7px 10px;
    border-radius:7px; color:#cdd8d2; }

QProgressBar { background:#1a1f1d; border:none; border-radius:4px; color:#c8d4ce; }
QProgressBar::chunk { background:#4fa87f; border-radius:4px; }

QGroupBox { border:1px solid #242b28; border-radius:10px; margin-top:14px;
    padding:12px 10px 10px 10px; color:#b3bfb9; }
QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 6px;
    color:#8fb8a6; font-size:12px; }

QListWidget#queue { background:transparent; border:none; }
QListWidget#queue::item { border-radius:6px; }
QListWidget#queue::item:hover { background:#1b2220; }
QListWidget#queue::item:selected { background:#26453a; color:#eaf4ee; }

QListWidget#grid { background:transparent; border:none; }
QListWidget#grid::item { border:2px solid transparent; border-radius:7px; }
QListWidget#grid::item:hover { border-color:#3d5a4c; }
QListWidget#grid::item:selected { border:2px solid #4fa87f; background:transparent; }
QListWidget#listbox { background:#0f1412; border:1px solid #242b28; border-radius:8px; }
QListWidget#listbox::item { padding:4px 8px; border-radius:5px; color:#c6d1cb; }
QListWidget#listbox::item:selected { background:#26453a; color:#eaf4ee; }

QScrollArea { background:transparent; border:none; }
QScrollArea > QWidget > QWidget { background:transparent; }

QTextEdit#log { background:#0d1211; border:1px solid #242b28; border-radius:8px;
    color:#b3bfb9; padding:8px; }

QCheckBox { color:#a3afaa; font-size:13px; spacing:7px; }
QCheckBox::indicator { width:15px; height:15px; border-radius:4px;
    border:1px solid #3a423e; background:#191f1d; }
QCheckBox::indicator:checked { background:#4fa87f; border-color:#5ec08f; }

QScrollBar:vertical { background:transparent; width:10px; margin:2px; }
QScrollBar::handle:vertical { background:#2b3231; border-radius:5px; min-height:30px; }
QScrollBar::handle:vertical:hover { background:#3d4542; }
QScrollBar::add-line, QScrollBar::sub-line { height:0; }
QScrollBar:horizontal { background:transparent; height:10px; }
QScrollBar::handle:horizontal { background:#2b3231; border-radius:5px; }

QStatusBar { background:#0f1412; color:#8b9793; font-size:12px; }
QStatusBar::item { border:none; }
"""

THEMES["light"] = """
* { outline: none; }
QWidget#root, QMainWindow { background:#f2f6f3; }
QWidget#trainpage { background:#f2f6f3; }

QFrame#topbar { background:#ffffff; border:1px solid #e0e8e4; border-radius:10px; }
QLabel#logo { color:#1b241f; }
QLabel#subtitle { color:#5f6b66; font-size:10px; letter-spacing:0.4px; }
QLabel#fieldLabel { color:#4f5b56; font-size:12px; }
QLabel#cardTitle { color:#1b241f; font-size:14px; font-weight:600; }
QLabel#counter { color:#5f6b66; font-size:12px; }
QLabel#hint { color:#4f5b56; font-size:12px; }
QLabel#stat { color:#42504a; font-size:12px; }
QLabel#curName { color:#1b241f; font-size:12px; font-weight:600; }

QFrame#card { background:#ffffff; border:1px solid #e0e8e4; border-radius:10px; }
QLabel#preview { background:#eef3f0; border:1px solid #dfe7e2; border-radius:8px;
    color:#4f5b56; font-size:13px; }

QTabWidget::pane { border:none; background:transparent; }
QTabBar::tab { background:transparent; color:#5f6b66; padding:8px 18px;
    margin-right:4px; border-radius:7px; font-size:13px; }
QTabBar::tab:hover { color:#1b241f; background:#eaefec; }
QTabBar::tab:selected { color:#123024; background:#dcebe3; }

QPushButton { background:#ffffff; border:1px solid #d7e1db; padding:7px 16px;
    border-radius:7px; color:#26322d; font-size:13px; }
QPushButton:hover { background:#f2f7f4; border-color:#bccfc5; }
QPushButton:pressed { background:#e8f0eb; }
QPushButton#primary { background:#3f8f6b; border:1px solid #3f8f6b; color:#ffffff;
    font-weight:600; }
QPushButton#primary:hover { background:#4ea87e; border-color:#4ea87e; }
QPushButton#ghost { background:transparent; border:1px solid #d7e1db; color:#42504a; }
QPushButton#ghost:hover { background:#f2f7f4; color:#16201b; }
QPushButton:disabled { color:#a9b5b0; border-color:#e6eeea; }

QComboBox { background:#ffffff; border:1px solid #d7e1db; padding:6px 8px;
    border-radius:7px; color:#26322d; min-width:86px; }
QComboBox:hover { border-color:#bccfc5; }
QComboBox::drop-down { border:none; width:18px; }
QComboBox QAbstractItemView { background:#ffffff; border:1px solid #d7e1db;
    selection-background-color:#dcebe3; selection-color:#10251c; color:#26322d; padding:4px; }

QLineEdit { background:#ffffff; border:1px solid #d7e1db; padding:7px 10px;
    border-radius:7px; color:#26322d; }

QProgressBar { background:#e4eee8; border:none; border-radius:4px; color:#26322d; }
QProgressBar::chunk { background:#4fa87f; border-radius:4px; }

QGroupBox { border:1px solid #e0e8e4; border-radius:10px; margin-top:14px;
    padding:12px 10px 10px 10px; color:#33413a; }
QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 6px;
    color:#2f7d5c; font-size:12px; }

QListWidget#queue { background:transparent; border:none; }
QListWidget#queue::item { border-radius:6px; }
QListWidget#queue::item:hover { background:#f2f7f4; }
QListWidget#queue::item:selected { background:#dcebe3; color:#10251c; }

QListWidget#grid { background:transparent; border:none; }
QListWidget#grid::item { border:2px solid transparent; border-radius:7px; }
QListWidget#grid::item:hover { border-color:#bcd8c9; }
QListWidget#grid::item:selected { border:2px solid #3f8f6b; background:transparent; }
QListWidget#listbox { background:#fbfdfc; border:1px solid #e0e8e4; border-radius:8px; }
QListWidget#listbox::item { padding:4px 8px; border-radius:5px; color:#26322d; }
QListWidget#listbox::item:selected { background:#dcebe3; color:#10251c; }

QScrollArea { background:transparent; border:none; }
QScrollArea > QWidget > QWidget { background:transparent; }

QTextEdit#log { background:#fbfdfc; border:1px solid #dfe7e2; border-radius:8px;
    color:#26322d; padding:8px; }

QCheckBox { color:#42504a; font-size:13px; spacing:7px; }
QCheckBox::indicator { width:15px; height:15px; border-radius:4px;
    border:1px solid #bfd0c7; background:#ffffff; }
QCheckBox::indicator:checked { background:#4fa87f; border-color:#3f8f6b; }

QScrollBar:vertical { background:transparent; width:10px; margin:2px; }
QScrollBar::handle:vertical { background:#cfdcd5; border-radius:5px; min-height:30px; }
QScrollBar::handle:vertical:hover { background:#b6c7be; }
QScrollBar::add-line, QScrollBar::sub-line { height:0; }
QScrollBar:horizontal { background:transparent; height:10px; }
QScrollBar::handle:horizontal { background:#cfdcd5; border-radius:5px; }

QStatusBar { background:#f2f6f3; color:#4f5b56; font-size:12px; }
QStatusBar::item { border:none; }
"""
