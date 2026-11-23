"""用 HTML + CSS 画流程图，再用 Chrome 无头模式截成 2x PNG。

输出：docs/media/flow_lr.{zh,en}.png、flow_workflow.{zh,en}.png
"""
from __future__ import annotations

import os
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "docs", "media")
os.makedirs(OUT, exist_ok=True)

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{
  width:1180px;padding:52px 56px;background:#fff;
  font-family:"Microsoft YaHei","PingFang SC","Segoe UI",sans-serif;
  color:#1f2724;-webkit-font-smoothing:antialiased;
}
h1{font-size:30px;letter-spacing:.5px;color:#173f30;font-weight:700}
.sub{margin-top:10px;font-size:15px;color:#6b7a72;line-height:1.6}
.rule{height:3px;width:56px;background:#2f7d5d;border-radius:2px;margin:18px 0 34px}
.card{
  background:#fff;border:1px solid #dfe8e3;border-radius:12px;
  padding:16px 18px;box-shadow:0 1px 2px rgba(23,63,48,.04);
  font-size:14px;line-height:1.55;
}
.card b{display:block;font-size:15px;color:#1f4d3b;margin-bottom:4px;font-weight:600}
.card span{color:#5b6b63}
.card.grey{border-color:#e3e7e5;background:#fafbfa}
.card.grey b{color:#4a5751}
.card.amber{border-color:#e8cf9f;background:#fffaf0}
.card.amber b{color:#8a5c14}
.card.green{border-color:#a9d3bf;background:#f3faf6}
.card.green b{color:#1f5c45}
.card.deep{border-color:#1f5c45;background:#eef6f1}
.card.deep b{color:#173f30}
.arr{flex:0 0 34px;height:2px;background:#cfdcd5;position:relative;margin:0 2px}
.arr::after{content:"";position:absolute;right:-1px;top:-4px;width:7px;height:7px;
  border-top:2px solid #cfdcd5;border-right:2px solid #cfdcd5;transform:rotate(45deg)}
.arr.green{background:#9dc4b1}
.arr.green::after{border-color:#9dc4b1}
.arr.amber{background:#dcc394}
.arr.amber::after{border-color:#dcc394}
"""


def lr_page(zh: bool) -> str:
    t = (lambda a, b: a) if zh else (lambda a, b: b)
    A = [t("LR 里全选这批<br><span>参数先别动</span>", "select them in LR<br><span>leave settings alone</span>"),
         t("跑 iKun Insect Studio<br><span>RAW 旁边写 .xmp</span>", "run iKun Insect Studio<br><span>writes .xmp beside the RAW</span>"),
         t("LR「读取元数据」<br><span>右键 → 从文件读取</span>", "LR: Read Metadata<br><span>right-click → from file</span>")]
    B = [t("直接拖进软件<br><span>不用先导入 LR</span>", "drop straight into the app<br><span>no import needed first</span>"),
         t("批量出 .xmp<br><span>原片一个字节不动</span>", "batch writes .xmp<br><span>RAW untouched</span>"),
         t("RAW 拖进 LR 导入<br><span>导入时自动读 .xmp</span>", "import the RAWs into LR<br><span>XMP is read on import</span>")]
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{CSS}
.grid{{display:grid;grid-template-columns:150px 1fr 186px;grid-template-rows:auto auto;
        gap:52px 14px;align-items:center}}
.start{{grid-column:1;grid-row:1 / span 2}}
.result{{grid-column:3;grid-row:1 / span 2;align-self:stretch;
         display:flex;flex-direction:column;justify-content:center}}
.lane{{display:flex;align-items:center;gap:10px}}
.lane .card{{flex:1}}
.tag{{font-size:13px;color:#7d8c85;margin-bottom:10px;letter-spacing:.3px}}
.taglane{{grid-column:2;display:flex;flex-direction:column}}
</style></head><body>
<h1>{t("它和 Lightroom 怎么接", "How it plugs into Lightroom")}</h1>
<div class="sub">{t("两条路，一个出口：每张 RAW 旁边多一个同名 .xmp，Lightroom 认它。软件从不改原片。",
                    "Two routes, one exit: a sidecar .xmp beside every RAW. The app never modifies the RAW.")}</div>
<div class="rule"></div>
<div class="grid">
  <div class="card green start"><b>{t("一批新照片", "a batch of RAW")}</b><span>{t("已经修过几张也算", "some already edited is fine")}</span></div>

  <div class="taglane">
    <div class="tag">{t("① 已经导进 Lightroom", "① already imported into Lightroom")}</div>
    <div class="lane">
      <div class="card grey">{A[0]}</div><div class="arr"></div>
      <div class="card green">{A[1]}</div><div class="arr green"></div>
      <div class="card amber">{A[2]}</div><div class="arr amber"></div>
    </div>
  </div>

  <div class="card deep result"><b>{t("Lightroom 里", "inside")}<br>{t("看到结果", "Lightroom")}</b><span>{t("框、曝光、锐化都在", "crop, exposure, sharpening")}</span></div>

  <div class="taglane">
    <div class="tag">{t("② 还没导进 Lightroom", "② not imported yet")}</div>
    <div class="lane">
      <div class="card green">{B[0]}</div><div class="arr green"></div>
      <div class="card green">{B[1]}</div><div class="arr green"></div>
      <div class="card amber">{B[2]}</div><div class="arr amber"></div>
    </div>
  </div>
</div>
<div class="sub" style="margin-top:36px;font-size:14px">
  {t("差别只有一个动作：已经在 LR 里的那批，要手点一次「读取元数据」；没导入的，导入时就自动读了。",
     "One action differs: a batch already in LR needs a manual Read Metadata; a fresh import reads the XMP by itself.")}
</div>
</body></html>"""


STEPS = {
    "zh": [
        ("选片", "", "grey",
         ["按批次过一遍：糊的、抖的、重复的、遮挡的，直接删",
          "留下有行为、有生境的那几张——生态片的价值常在那一点环境"]),
        ("挑出要精修的", "", "amber",
         ["只挑 5–10%，真正值得发表的几张",
          "完整后期手工做：构图、光比、色彩；这几张不交给软件"]),
        ("跑批", "软件", "green",
         ["其余全部拖进软件，策略选「跳过已有 XMP」",
          "只做掩膜 → 裁切 → 曝光 → 锐化，写成 .xmp；白平衡不碰"]),
        ("统一微调", "图像后期软件", "deep",
         ["白平衡、整体曝光、色彩、局部调整，在这里成批做",
          "软件里的头部微调是可选项，不属于这条主线"]),
        ("导出", "图像后期软件", "deep",
         ["套统一预设 → 导出（尺寸、输出锐化、水印）",
          "软件只写 .xmp，原片一个字节都不动"]),
    ],
    "en": [
        ("Cull", "", "grey",
         ["Go batch by batch: delete soft, shaken, duplicated, blocked frames",
          "Keep the ones with behaviour and habitat — that context is the story"]),
        ("Pick the keepers", "", "amber",
         ["Only 5–10%: the frames actually worth publishing",
          "Finish them by hand — composition, contrast, colour; keep them out of the batch"]),
        ("Batch run", "the app", "green",
         ["Drop the rest in, policy = skip photos with XMP",
          "Mask → crop → exposure → sharpening into .xmp; white balance untouched"]),
        ("Global fine-tuning", "post-processing app", "deep",
         ["White balance, overall exposure, colour, local adjustments — in bulk",
          "The in-app head nudge is optional and not on this mainline"]),
        ("Export", "post-processing app", "deep",
         ["Apply your preset → export (size, output sharpening, watermark)",
          "The app only writes .xmp; the RAW is never modified"]),
    ],
}


def wf_page(zh: bool) -> str:
    t = (lambda a, b: a) if zh else (lambda a, b: b)
    rows = STEPS["zh" if zh else "en"]
    body = []
    for i, (head, who, cls, bullets) in enumerate(rows):
        lis = "".join(f"<li>{b}</li>" for b in bullets)
        body.append(f"""
    <div class="step">
      <div class="num {cls}">{i+1}</div>
      <div class="body card {cls}">
        <div class="head"><b>{head}</b>{f"<em>{who}</em>" if who else ""}</div>
        <ul>{lis}</ul>
      </div>
    </div>""")
        if i < len(rows) - 1:
            body.append(f'<div class="link {rows[i+1][2]}"></div>')
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{CSS}
.step{{display:flex;gap:20px;align-items:stretch}}
.num{{width:46px;height:46px;border-radius:50%;color:#fff;display:flex;
      align-items:center;justify-content:center;font-size:19px;font-weight:700;flex:0 0 46px;
      margin-top:14px}}
.num.grey{{background:#8a8f93}} .num.amber{{background:#b8791f}}
.num.green{{background:#2f7d5d}} .num.deep{{background:#173f30}}
.body{{flex:1;padding:18px 22px}}
.head{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px}}
.head b{{font-size:17px}} .head em{{font-style:normal;font-size:13px;opacity:.75}}
.body ul{{margin-left:18px}} .body li{{font-size:14px;color:#40504a;line-height:1.75}}
.link{{width:2px;height:26px;background:#cfdcd5;margin-left:22px}}
.link.green{{background:#a9d3bf}} .link.amber{{background:#e8cf9f}}
.link.deep{{background:#9dc4b1}}
</style></head><body>
<h1>{t("完整工作流", "The full workflow")}</h1>
<div class="sub">{t("五步。前三步决定成片质量，后两步决定一致性；真正意义上的「微调」在图像后期软件里。",
                    "Five steps. The first three decide quality, the last two decide consistency — and the real fine-tuning happens in your post-processing software.")}</div>
<div class="rule"></div>
{"".join(body)}
<div class="sub" style="margin-top:26px;font-size:14px">
  {t("② 和 ③ 不能换序：先把要精修的做完，再让跑批跳过它们。", "② and ③ cannot swap: finish the hand edits first, then let the batch skip them.")}
</div>
</body></html>"""


def render(html: str, name: str, height: int = 900):
    fp = os.path.join(tempfile.gettempdir(), name + ".html")
    open(fp, "w", encoding="utf-8").write(html)
    png = os.path.join(OUT, name + ".png")
    cmd = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
           "--force-device-scale-factor=2", f"--window-size=1180,{height}",
           f"--screenshot={png}", "file:///" + fp.replace("\\", "/")]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    return png


if __name__ == "__main__":
    for zh in (True, False):
        tag = "zh" if zh else "en"
        print(render(lr_page(zh), f"flow_lr.{tag}", 560))
        print(render(wf_page(zh), f"flow_workflow.{tag}", 985))
