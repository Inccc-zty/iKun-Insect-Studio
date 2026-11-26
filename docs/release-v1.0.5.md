# iKun Insect Studio

**把昆虫微距里最枯燥的部分做掉：找虫、定框、给曝光。**

外拍一天回来，每个个体都要留一张记录，真正精修的只有几张。微距题材里虫子天生在画面中偏小，于是时间都花在剩下那几十上百张的重复裁切、重复调曝光上。这个软件把那部分收成一步：拖进文件夹，每张给一个裁切框和一次曝光，结果写成 Lightroom 能直接读的 `.xmp`，导入即生效。

- **裁切**：全画幅掩膜找出虫体，外接框 + 躯干框 + 头点 → 105 项模型给出裁切框，留出 IoU **0.865**
- **曝光**：掩膜内 p95 与框内掩膜外 p95，两个数进一条直线，留出 MAE **0.29 EV**
- **锐化**：按光圈查表（20 → 65）
- **学你的构图**：拿你自己修好的成品 JPG 即可重拟合裁切模型，不需要原图、不需要 XMP

> 裁切和曝光都可能出错，没有一个是 100% 准的。它的价值不是"准"，是把重复劳动从几小时压到几分钟。

---

## 这个版本更新了什么（1.0.5）

**训练数据来源只留两项，默认「成品 JPG」。** 这是本版唯一的目的：让「直接拿成片训练」成为默认路径。

| 1.0.4 里的问题 | 现在的行为 |
|---|---|
| 数据来源有三个选项，其中「成品 JPG + 原图」要求两套目录同名同结构，实际没人那样整理文件 | 撤掉该选项，只留两项 |
| 默认停在「带 XMP 的 RAW / 原图 JPG」，而实际大家手上只有成品 | 默认改成「成品 JPG」 |
| 新加的下拉框右边没有向下小三角，与软件里另两处下拉不一致 | 改用同一套绘制，三处外观一致 |

| 数据来源 | 说明 |
|---|---|
| **成品 JPG（默认）** | 选修好的成片文件夹。成片就是裁切后的画面，软件从它反解裁切框 |
| 带 XMP 的 RAW / 原图 JPG | 选原图文件夹，裁切框直接读同名 XMP |

两者都至少 50 张；训练产物进模型库，可在「模型（系数）」下拉切换。

## 下载与升级

`iKunInsectStudio_v1.0.5.zip.001`、`.002` 与 `join-parts.bat` 放同一文件夹，双击 bat 合成 zip，解压后运行 `iKunInsectStudio.exe`（整个文件夹要一起留着）。

从旧版升级：只替换 `exe` 与 `_internal\`，**保留 `data\`**（训练的模型与头点记忆在里面）。

Windows 10/11 + NVIDIA 显卡（4 GB 显存起；2 GB 可用 384 档）。

**百度网盘**（提取码 8848）：https://pan.baidu.com/s/1Y8DXyby6ZurjYscQKorsCw?pwd=8848

---
---

# iKun Insect Studio

**The two most repetitive jobs in insect macro, done in one pass: find the bug, place the crop, set the exposure.**

A day out shooting means one record frame per individual, and only a handful worth a full edit. In macro work the insect is always small in the frame, so the hours go into the ninety records — crop after crop, exposure after exposure. This tool folds that into one step: drop a folder in, and every frame gets a crop box and an exposure value, written as a `.xmp` your editor reads on import.

- **Crop** — a full-frame mask finds the insect, then a body box, a whole box and a head point feed a 105-term model. Hold-out IoU **0.865**
- **Exposure** — two p95 brightness numbers into one straight line; hold-out MAE **0.29 EV** (constant baseline 0.41)
- **Sharpening** — by aperture, 20 → 65
- **Learns your framing** — refit the crop model on your own finished JPEGs; no originals, no XMP

> Crop and exposure can both be wrong — nothing here is 100%. The value is not accuracy, it is turning hours of repetitive editing into minutes.

---

## What changed in 1.0.5

**Two data sources only, and the default is "Finished JPEGs".** That is the single point of this release: make training directly on exports the default path.

| Problem in 1.0.4 | Behaviour now |
|---|---|
| Three data sources, one of which ("exports + originals") demanded two mirrored folder trees nobody keeps | That option is gone; two remain |
| Default sat on "RAW / JPG with XMP", while most people only have finished exports | Default is now "Finished JPEGs" |
| The new drop-down had no small arrow, unlike the other two in the app | Same painter; all three look alike now |

| Data source | What it does |
|---|---|
| **Finished JPEGs (default)** | Pick the export folder; the app inverts the crop out of it |
| RAW / JPG with XMP | Pick the originals folder; the crop box comes from the sidecar |

Both need at least 50 photos; the result lands in the model library and is switchable in the model drop-down.

## Download and upgrade

Put `iKunInsectStudio_v1.0.5.zip.001`, `.002` and `join-parts.bat` in one folder, run the bat, unzip, run `iKunInsectStudio.exe` (keep the whole folder together).

Upgrading: replace `exe` and `_internal\` only, **keep `data\`** (your trained models live there).

Windows 10/11 with an NVIDIA GPU (4 GB VRAM; 2 GB works at 384).

**Baidu Netdisk** (code 8848): https://pan.baidu.com/s/1Y8DXyby6ZurjYscQKorsCw?pwd=8848
