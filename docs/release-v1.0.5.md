**1.0.5：训练数据来源只留两项，默认就是「成品 JPG」——成片直接训练，绝大多数人只需要这一条路。**

## 这版改了什么（针对 1.0.4 的问题）

| 1.0.4 里的问题 | 现在的行为 |
|---|---|
| 数据来源有三个选项，其中一个（成品 JPG + 原图）要求两套目录同名同结构，实际没人会那样整理文件 | **撤掉这个选项**，只留两项 |
| 默认停在「带 XMP 的 RAW / 原图 JPG」，而实际大家手上只有修好的成片 | **默认改成「成品 JPG」**，打开就是能直接用的那条路 |
| 新加的下拉框右边没有向下的小三角，和软件里另外两处下拉长得不一样 | 改成同一套绘制，三处外观一致 |

## 现在只有两条路

| 数据来源 | 说明 |
|---|---|
| **成品 JPG（默认）** | 选修好的成片文件夹。成片就是裁切后的画面，软件从它反解裁切框，不需要原图、不需要 XMP |
| 带 XMP 的 RAW / 原图 JPG | 选原图文件夹，裁切框直接读同名 XMP；保留着 Lightroom 工程时用 |

两者都至少 50 张。训练产物进模型库，可在「模型（系数）」下拉里切换。

## 为什么默认成品 JPG

因为这是绝大多数人的实际状态：原片躺在硬盘里、XMP 未必留着，但**修好的成片一定在**。
成片本身已经包含「你怎么裁的」这个答案——虫体占画面多大、偏在哪，量出来就是你的构图习惯。
把它反解成裁切框，比要求你翻出同名 XMP 现实得多。

## 升级

只替换 `exe` 与 `_internal\`，**保留 `data\`**（训练的模型与头点记忆在里面）。

`iKunInsectStudio_v1.0.5.zip.001`、`.002` 与 `join-parts.bat` 放同一文件夹，双击 bat 合成 zip，解压即用。

Windows 10/11 + NVIDIA 显卡（4 GB 显存起；2 GB 可用 384 档）。

**百度网盘**（提取码 8848）：https://pan.baidu.com/s/1dkWKy9bxWnTreHFD5cCBVA?pwd=8848

---

**1.0.5: two data sources only, and the default is "Finished JPEGs" — exports train directly, which is all
most people ever need.**

## Fixed since 1.0.4

| Problem in 1.0.4 | Behaviour now |
|---|---|
| Three data sources, one of which ("exports + originals") demanded two mirrored folder trees nobody actually keeps | That option is **gone**; two remain |
| Default sat on "RAW / JPG with XMP", while most people only have finished exports | Default is now **Finished JPEGs** |
| The new drop-down had no small arrow, unlike the other two drop-downs in the app | Same painter, same look in all three places |

## The two paths

| Data source | What it does |
|---|---|
| **Finished JPEGs (default)** | Pick the export folder. An export is the frame after cropping; the app inverts it into a crop box. No originals, no XMP |
| RAW / JPG with XMP | Pick the originals folder; the crop box comes straight from the sidecar |

Both need at least 50 photos. The result lands in the model library and is switchable in the model drop-down.

## Why exports are the default

Because that is the real state of most libraries: the RAWs sit on a drive, the XMPs may be gone, but the
**edited exports are always there**. An export already carries the answer to "how did you crop this" —
how much of the frame the insect takes and where it sits. Inverting that into a box is far more realistic
than asking you to dig up matching sidecars.

## Upgrading

Replace `exe` and `_internal\` only, **keep `data\`**.

Put `iKunInsectStudio_v1.0.5.zip.001`, `.002` and `join-parts.bat` in one folder, run the bat, unzip, run.

Windows 10/11 with an NVIDIA GPU (4 GB VRAM; 2 GB works at 384).

**Baidu Netdisk** (code 8848): https://pan.baidu.com/s/1dkWKy9bxWnTreHFD5cCBVA?pwd=8848
