"""两张流程图（中英各一份），第二版：正交连线、不重叠、每步带细项。

   1) 它和 Lightroom 怎么接
   2) 完整工作流（生态摄影后期的五步）
"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "docs", "media")
os.makedirs(OUT, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

GREEN, DEEP, GREY, AMBER, BLUE = "#3f8f6b", "#1f5c45", "#8a8f93", "#c98a2a", "#4f86b8"
INK, SOFT, PAPER = "#1f2724", "#eaf3ee", "#f7f7f7"


def box(ax, x, y, w, h, title=None, body=None, fc=SOFT, ec=GREEN,
        fs_t=10.2, fs_b=8.6, tc=DEEP):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.008,rounding_size=0.012",
                                fc=fc, ec=ec, lw=1.5))
    if title and body:
        ax.text(x + w / 2, y + h * .68, title, ha="center", va="center",
                fontsize=fs_t, color=tc, fontweight="bold")
        ax.text(x + w / 2, y + h * .32, body, ha="center", va="center",
                fontsize=fs_b, color=INK, linespacing=1.55)
    elif title:
        ax.text(x + w / 2, y + h / 2, title, ha="center", va="center",
                fontsize=fs_t, color=tc, fontweight="bold", linespacing=1.55)


def harrow(ax, x1, x2, y, c=GREEN):
    ax.annotate("", xy=(x2, y), xytext=(x1, y),
                arrowprops=dict(arrowstyle="-|>", color=c, lw=1.7,
                                shrinkA=0, shrinkB=0, mutation_scale=13))


def varrow(ax, y1, y2, x, c=GREEN):
    ax.annotate("", xy=(x, y2), xytext=(x, y1),
                arrowprops=dict(arrowstyle="-|>", color=c, lw=1.7,
                                shrinkA=0, shrinkB=0, mutation_scale=13))


def canvas(w, h):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    return fig, ax


# ------------------------------------------------------------------ 1 与 LR 的关系
def fig_lr(zh: bool):
    t = (lambda a, b: a) if zh else (lambda a, b: b)
    fig, ax = canvas(12.0, 5.2)
    ax.text(.5, .96, t("它和 Lightroom 怎么接", "How it plugs into Lightroom"),
            ha="center", fontsize=15, fontweight="bold", color=DEEP)
    ax.text(.5, .905, t("两条路，一个出口：RAW 旁边多一个 .xmp，Lightroom 认它",
                        "Two routes, one exit: an .xmp beside the RAW, and Lightroom reads it"),
            ha="center", fontsize=9.4, color="#5c6b64")

    x_start, w_start = .012, .13
    cols = [.175, .335, .495]
    w = .145
    x_end, w_end = .845, .14
    yA, yB, hh = .60, .16, .17

    box(ax, x_start, .40, w_start, .18,
        t("一批新照片\n（RAW）", "a batch of RAW"), fs_t=10.4)

    ax.text(.175, .815, t("① 已经导进 Lightroom", "① already imported"),
            fontsize=9.6, color=GREY, fontweight="bold")
    ax.text(.175, .105, t("② 还没导进 Lightroom", "② not imported yet"),
            fontsize=9.6, color=GREY, fontweight="bold")

    A = [t("LR 里全选\n参数先别动", "select them in LR\nleave settings alone"),
         t("跑软件\n写 .xmp", "run the app\nwrites .xmp"),
         t("LR 右键\n读取元数据", "LR: right-click\nRead Metadata")]
    B = [t("直接拖进软件", "drop into the app"),
         t("批量出 .xmp\n原片不动", "batch writes .xmp\nRAW untouched"),
         t("RAW 拖进 LR 导入\n导入即读 .xmp", "import into LR\nXMP is read on import")]

    for i, x in enumerate(cols):
        ecA = [GREY, GREEN, AMBER][i]
        ecB = [GREEN, GREEN, AMBER][i]
        box(ax, x, yA, w, hh, A[i], fc=PAPER if i == 0 else SOFT, ec=ecA)
        box(ax, x, yB, w, hh, B[i], fc=SOFT, ec=ecB)

    # 起点 → 两行（正交折线）
    ax.plot([x_start + w_start, .152], [.49, .49], color=GREY, lw=1.7)
    ax.plot([.152, .152], [yA + hh / 2, yB + hh / 2], color=GREY, lw=1.7)
    harrow(ax, .152, cols[0], yA + hh / 2, GREY)
    harrow(ax, .152, cols[0], yB + hh / 2, GREY)

    for i in range(2):
        harrow(ax, cols[i] + w, cols[i + 1], yA + hh / 2, GREEN if i == 0 else AMBER)
        harrow(ax, cols[i] + w, cols[i + 1], yB + hh / 2, GREEN if i == 0 else AMBER)

    box(ax, x_end, .345, w_end, .30,
        t("Lightroom 里\n看到结果", "results inside\nLightroom"), fc="#e6f2ea", ec=DEEP,
        fs_t=10.2)

    # 两支 → 结果（折线，不斜穿）
    ax.plot([cols[2] + w, .825], [yA + hh / 2, yA + hh / 2], color=AMBER, lw=1.7)
    varrow(ax, yA + hh / 2, .60, .825, AMBER)
    ax.plot([cols[2] + w, .825], [yB + hh / 2, yB + hh / 2], color=AMBER, lw=1.7)
    varrow(ax, yB + hh / 2, .43, .825, AMBER)
    harrow(ax, .825, x_end, .60, AMBER)
    harrow(ax, .825, x_end, .43, AMBER)

    ax.text(.5, .025, t("差别只有一个动作：已经在 LR 里的那批，手点一次「读取元数据」。",
                        "The only difference: a batch already in LR needs one Read Metadata click."),
            ha="center", fontsize=9.2, color=DEEP)
    fig.tight_layout()
    fp = os.path.join(OUT, f"flow_lr.{'zh' if zh else 'en'}.png")
    fig.savefig(fp, dpi=170, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return fp


# ------------------------------------------------------------------ 2 工作流
STEPS = {
    "zh": [
        ("选片", "你", GREY,
         ["按批次先过一遍：糊的、抖的、重复的、遮挡的直接删",
          "留下有行为、有生境信息的；生态片的价值常在那一点环境里"]),
        ("挑出要精修的", "你", AMBER,
         ["只挑 5–10%：真正能出片的几张",
          "完整后期手工做（构图、光比、色彩），这几张不交给软件"]),
        ("跑批", "软件", GREEN,
         ["其余全部拖进软件，策略选「跳过已有 XMP」",
          "只做掩膜 → 裁切 → 曝光 → 锐化，写进 .xmp；白平衡不碰"]),
        ("微调", "你", BLUE,
         ["白平衡必须自己调（软件不猜色温）",
          "曝光、裁切个别不平的拖一下；头点拖错也会被记住"]),
        ("导出", "Lightroom", DEEP,
         ["LR 里「读取元数据」→ 套统一预设 → 导出",
          "软件只写 .xmp，原片一个字节都不动"]),
    ],
    "en": [
        ("Cull", "you", GREY,
         ["Go batch by batch: delete soft, shaken, duplicated, blocked frames",
          "Keep behaviour and habitat — in ecological work the environment is the story"]),
        ("Pick the keepers", "you", AMBER,
         ["Only 5–10%: the frames actually worth publishing",
          "Finish these by hand (composition, contrast, colour); keep them out of the batch"]),
        ("Batch run", "the app", GREEN,
         ["Drop the rest in, policy = 「skip photos with XMP」",
          "Mask → crop → exposure → sharpening into .xmp; white balance untouched"]),
        ("Fine-tune", "you", BLUE,
         ["White balance by hand — the app never guesses colour temperature",
          "Nudge the odd exposure or crop; a corrected head point is remembered"]),
        ("Export", "Lightroom", DEEP,
         ["Read Metadata in LR → apply your preset → export",
          "The app only writes .xmp; the RAW is never modified"]),
    ],
}


def fig_workflow(zh: bool):
    rows = STEPS["zh" if zh else "en"]
    fig, ax = canvas(9.0, 11.6)
    t = (lambda a, b: a) if zh else (lambda a, b: b)
    ax.text(.5, .975, t("完整工作流：从一堆废片到交付",
                        "The full workflow: from a card dump to delivery"),
            ha="center", fontsize=14.5, fontweight="bold", color=DEEP)
    ax.text(.5, .938, t("五步，前三步决定成片质量，后两步决定一致性",
                        "Five steps: the first three decide quality, the last two decide consistency"),
            ha="center", fontsize=9.2, color="#5c6b64")

    top, gap, bh = .885, .168, .128
    for i, (head, who, col, bullets) in enumerate(rows):
        y = top - i * gap - bh
        ax.add_patch(FancyBboxPatch((.055, y), .855, bh,
                                    boxstyle="round,pad=0.006,rounding_size=0.012",
                                    fc="white", ec=col, lw=1.6))
        ax.add_patch(plt.Circle((.105, y + bh / 2), .027, color=col, zorder=3))
        ax.text(.105, y + bh / 2, str(i + 1), ha="center", va="center",
                color="white", fontsize=11.5, fontweight="bold", zorder=4)
        ax.text(.150, y + bh - .034, head, fontsize=11.6, fontweight="bold", color=col)
        ax.text(.845, y + bh - .036, who, fontsize=8.8, color=col, ha="right",
                fontweight="bold")
        ax.text(.150, y + bh * .40, "· " + bullets[0], fontsize=9.0, color=INK)
        ax.text(.150, y + bh * .16, "· " + bullets[1], fontsize=9.0, color="#55655d")
        if i < len(rows) - 1:
            varrow(ax, y - .002, y - gap + bh + .006, .5, col)

    ax.text(.5, .022, t("② 和 ③ 不能换序：先手工修完，再让跑批跳过它们。",
                        "② and ③ cannot swap: finish the hand edits first, then let the batch skip them."),
            ha="center", fontsize=9.0, color="#5c6b64")
    fig.tight_layout()
    fp = os.path.join(OUT, f"flow_workflow.{'zh' if zh else 'en'}.png")
    fig.savefig(fp, dpi=170, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return fp


if __name__ == "__main__":
    for zh in (True, False):
        print(fig_lr(zh))
        print(fig_workflow(zh))
