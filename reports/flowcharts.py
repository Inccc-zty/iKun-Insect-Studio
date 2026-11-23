"""两张流程图（中英各一份）：
   1) 它和 Lightroom 怎么接：已导入 / 未导入 两条路
   2) 完整工作流：选片 → 精修 → 跑批 → 微调 → 导出
输出到 docs/media/，由 docs/manual.md 引用。
"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "docs", "media")
os.makedirs(OUT, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

GREEN = "#3f8f6b"
DEEP = "#1f5c45"
GREY = "#8a8f93"
AMBER = "#c98a2a"
BLUE = "#4f86b8"
INK = "#1f2724"
SOFT = "#eaf3ee"


def box(ax, x, y, w, h, text, fc=SOFT, ec=GREEN, fs=10, bold=False, tc=INK):
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012,rounding_size=0.02",
                       fc=fc, ec=ec, lw=1.4)
    ax.add_patch(p)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
            color=tc, fontweight="bold" if bold else "normal", linespacing=1.5)


def arrow(ax, p1, p2, color=GREEN, style="-|>", lw=1.6, rad=0.0, ls="-"):
    a = FancyArrowPatch(p1, p2, arrowstyle=style, mutation_scale=13,
                        color=color, lw=lw, linestyle=ls,
                        connectionstyle=f"arc3,rad={rad}")
    ax.add_patch(a)


def canvas(w=11, h=6.2):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return fig, ax


# --------------------------------------------------------------- 1 与 LR 的关系
def fig_lr(zh: bool):
    fig, ax = canvas(11.6, 5.4)
    t = (lambda a, b: a) if zh else (lambda a, b: b)

    ax.text(.5, .955, t("它和 Lightroom 怎么接", "How it plugs into Lightroom"),
            ha="center", fontsize=15, fontweight="bold", color=DEEP)
    ax.text(.5, .905, t("两条路，出口一样：照片旁边多一个 .xmp，LR 认它",
                        "Two routes, one exit: an .xmp beside each RAW, and Lightroom reads it"),
            ha="center", fontsize=9.5, color="#5c6b64")

    # 列坐标
    x0, w0 = .015, .135          # 起点
    xs = [.19, .395, .60]        # 三列
    ws = .165
    xr, wr = .815, .17           # 结果

    ya, ha = .60, .18            # 上支
    yb, hb = .17, .18            # 下支

    # 起点
    box(ax, x0, .40, w0, .18,
        t("一批新照片\n（RAW）", "a batch of RAW"), fc="#f4f8f6", fs=9.4, bold=True)

    # 分支标签
    ax.text(.19, .835, t("① 已经导进 Lightroom", "① already in Lightroom"),
            fontsize=9.8, color=GREY, fontweight="bold")
    ax.text(.19, .105, t("② 还没导进 Lightroom", "② not imported yet"),
            fontsize=9.8, color=GREY, fontweight="bold")

    A = [t("LR 里全选这批\n参数先别动", "select the batch in LR\nleave settings alone"),
         t("跑 iKun Insect Studio\nRAW 旁边写 .xmp", "run the app\nwrites .xmp beside RAW"),
         t("LR：右键 →\n「从文件读取元数据」", "LR: right-click →\nRead Metadata from File")]
    B = [t("直接拖进\niKun Insect Studio", "drop straight into\nthe app"),
         t("批量出 .xmp\n（原片不动）", "batch writes .xmp\nRAW untouched"),
         t("把 RAW 拖进 LR 导入\n（导入即读 .xmp）", "import the RAWs into LR\nXMP read on import")]

    for i, x in enumerate(xs):
        box(ax, x, ya, ws, ha, A[i], fc="#f7f7f7" if i == 0 else SOFT,
            ec=GREY if i == 0 else (AMBER if i == 2 else GREEN), fs=8.8,
            bold=(i == 2))
        box(ax, x, yb, ws, hb, B[i], fc=SOFT,
            ec=AMBER if i == 2 else GREEN, fs=8.8, bold=(i == 2))

    # 起点 → 两支
    arrow(ax, (x0 + w0, .54), (xs[0], ya + ha / 2), GREY)
    arrow(ax, (x0 + w0, .44), (xs[0], yb + hb / 2), GREY)
    # 横向
    for i in range(2):
        arrow(ax, (xs[i] + ws, ya + ha / 2), (xs[i + 1], ya + ha / 2),
              GREEN if i == 1 else GREY)
        arrow(ax, (xs[i] + ws, yb + hb / 2), (xs[i + 1], yb + hb / 2),
              GREEN if i == 1 else GREY)
    # 汇合
    box(ax, xr, .345, wr, .30, t("Lightroom 里\n看到最终结果", "final result\ninside Lightroom"),
        fc="#e6f2ea", ec=DEEP, fs=9.6, bold=True)
    arrow(ax, (xs[2] + ws, ya + ha / 2), (xr, .56), AMBER)
    arrow(ax, (xs[2] + ws, yb + hb / 2), (xr, .43), AMBER)

    ax.text(.5, .035, t("差别只有一个动作：已经在 LR 里的那批，要手点一次「读取元数据」。",
                        "The only difference: a batch already in LR needs one click on Read Metadata."),
            ha="center", fontsize=9.2, color=DEEP)
    fig.tight_layout()
    fp = os.path.join(OUT, f"flow_lr.{'zh' if zh else 'en'}.png")
    fig.savefig(fp, dpi=170, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return fp


# --------------------------------------------------------------- 2 工作流
def fig_workflow(zh: bool):
    fig, ax = canvas(8.4, 11.2)
    t = (lambda a, b: a) if zh else (lambda a, b: b)

    ax.text(.5, .972, t("完整工作流：从一堆废片到交付",
                        "The full workflow: from a card dump to delivery"),
            ha="center", fontsize=14.5, fontweight="bold", color=DEEP)

    steps = [
        (t("选片", "Cull"),
         t("手动过一遍，太丑的、糊的、重复的直接删",
           "Go through by hand; delete the ugly, the soft, the duplicates"),
         t("这一步只能你做，软件不猜", "only you can do this — the tool will not guess"),
         GREY),
        (t("挑出要精修的", "Pick the keepers"),
         t("特别满意的几张，先自己手动修到满意",
           "The few you really care about: edit them by hand first"),
         t("后面跑批时要「跳过自己修过的」，靠的就是这批",
          "this is what 「skip what I edited」 protects later"),
         AMBER),
        (t("跑批", "Batch run"),
         t("剩下的全部拖进软件，策略选「跳过已有 XMP」",
           "drop the rest into the app, policy = 「skip photos with XMP」"),
         t("掩膜 + 裁切 + 曝光 + 锐化一次出完，写成 .xmp",
           "mask + crop + exposure + sharpening in one pass, written as .xmp"),
         GREEN),
        (t("微调", "Fine-tune"),
         t("白平衡手动调；个别曝光、裁切不平的，在软件里拖一下",
           "white balance by hand; nudge the odd exposure or crop in the app"),
         t("拖过的这张会记住，下次遇到相近的自动补偿",
           "a nudged head point is remembered and reused for similar frames"),
         BLUE),
        (t("导出", "Export"),
         t("LR 里「读取元数据」→ 统一套预设 → 导出",
           "Read Metadata in LR → apply your preset → export"),
         t("软件只写到 .xmp，不碰你的原片", "the app only writes .xmp; RAWs are never touched"),
         DEEP),
    ]

    top = .925
    gap = .175
    for i, (head, what, note, col) in enumerate(steps):
        y = top - i * gap - .12
        box(ax, .06, y, .88, .125, "", fc="white", ec=col, fs=9)
        # 序号圆
        ax.add_patch(plt.Circle((.115, y + .062), .026, color=col, zorder=3))
        ax.text(.115, y + .062, str(i + 1), ha="center", va="center",
                color="white", fontsize=11, fontweight="bold", zorder=4)
        ax.text(.165, y + .085, head, fontsize=11.5, fontweight="bold", color=col)
        ax.text(.165, y + .050, what, fontsize=9.4, color=INK)
        ax.text(.165, y + .020, note, fontsize=8.4, color="#6b7a73", style="italic")
        if i < len(steps) - 1:
            arrow(ax, (.5, y - .004), (.5, y - gap + .128), col, lw=1.8)

    ax.text(.5, .022, t("第 2 步和第 3 步的顺序不能反：先手动修完，再让软件避开它们。",
                        "Steps 2 and 3 cannot swap: edit by hand first, then let the batch skip them."),
            ha="center", fontsize=8.8, color="#5c6b64")
    fig.tight_layout()
    fp = os.path.join(OUT, f"flow_workflow.{'zh' if zh else 'en'}.png")
    fig.savefig(fp, dpi=170, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return fp


if __name__ == "__main__":
    for zh in (True, False):
        print(fig_lr(zh))
        print(fig_workflow(zh))
