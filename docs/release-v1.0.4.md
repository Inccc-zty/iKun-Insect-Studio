**1.0.4：训练页三个按钮合并成一个下拉框。之前「添加目录 / 添加成品 JPG / 添加原图与成品 JPG」三个并排摆着，看不懂该点哪个。**

## 这版修了什么（针对 1.0.3 的问题）

| 1.0.3 里的问题 | 现在的行为 |
|---|---|
| 训练页横着一排三个按钮，名字说的是「文件类型」而不是「你要做什么」，不看说明书猜不出来 | 收成**一个「数据来源」下拉框 + 一个添加按钮**，按钮名字跟着选择变 |
| 「添加成品 JPG」「添加原图与成品 JPG」两个名字只差几个字，容易点错 | 三个选项分别是「带 XMP 的 RAW / 原图 JPG」「成品 JPG（只有成片）」「成品 JPG + 原图」，一眼能对上手上的文件 |
| 选错按钮会在错误入口里翻半天目录 | 先选来源，再点添加；加错的行可以直接 × 掉 |

## 现在的样子

训练页「训练目录」这一行的右侧：

    训练目录（可以放多个…）                    数据来源 [ 带 XMP 的 RAW / 原图 JPG ▾ ]

下面的按钮会跟着变：

| 数据来源 | 按钮 |
|---|---|
| 带 XMP 的 RAW / 原图 JPG | 添加带 XMP 的文件夹 |
| 成品 JPG（只有成片） | 添加成品 JPG 文件夹 |
| 成品 JPG + 原图 | 添加原图与成品目录 |

列表里每一行后面标着来源：`灵山 · 成片（12 张）`、`灵山 · XMP（437 张）`、`灵山 · 成片+原图（60 张）`。
选择会记住，下次打开还是上次那个。

三种来源的判定没变：

- **带 XMP**：文件夹里 RAW 或全幅 JPG，配同名 `.xmp`
- **只有成片**：修好的成品 JPG，从成片反解裁切框，不需要原图与 XMP
- **成片 + 原图**：两目录同名同结构，配准后落回原片坐标

## 升级

只替换 `exe` 与 `_internal\`，**保留 `data\`**（训练的模型与头点记忆在里面）。

`iKunInsectStudio_v1.0.4.zip.001`、`.002` 与 `join-parts.bat` 放同一文件夹，双击 bat 合成 zip，解压即用。

Windows 10/11 + NVIDIA 显卡（4 GB 显存起；2 GB 可用 384 档）。

**百度网盘**（提取码 **8848**）：

- Windows 整包：https://pan.baidu.com/s/1Y8DXyby6ZurjYscQKorsCw?pwd=8848
- macOS 整包：https://pan.baidu.com/s/1orsQ9RngYvnAi8pLO7Qb_w?pwd=8848

---

**1.0.4: the three training buttons became one drop-down. "Add folder / Add JPEG exports / Add originals
and exports" side by side gave no clue which one to press.**

## Fixed since 1.0.3

| Problem in 1.0.3 | Behaviour now |
|---|---|
| Three buttons in a row named after file types, not after what you are trying to do | **One "Data source" drop-down plus one add button**; the button renames itself |
| "Add JPEG exports" and "Add originals and exports" differ by a few characters, easy to misclick | Three options: "RAW / JPG with XMP", "Finished JPEGs only", "Finished JPEGs + originals" |
| Picking the wrong button meant browsing folders in the wrong flow | Choose the source, then add; a wrong row can be removed with × |

## What it looks like

Right side of the "Training folders" row:

    Training folders (several allowed…)        Data source [ RAW / JPG with XMP ▾ ]

The button follows the choice:

| Data source | Button |
|---|---|
| RAW / JPG with XMP | Add folder with XMP |
| Finished JPEGs only | Add finished-JPEG folder |
| Finished JPEGs + originals | Add originals and exports |

Each row is tagged with its source: `Lingshan · exports (12)`, `Lingshan · XMP (437)`, `Lingshan · exports + originals (60)`.
The choice is remembered between sessions.

## Upgrading

Replace `exe` and `_internal\` only, **keep `data\`**.

Put `iKunInsectStudio_v1.0.4.zip.001`, `.002` and `join-parts.bat` in one folder, run the bat, unzip, run.

Windows 10/11 with an NVIDIA GPU (4 GB VRAM; 2 GB works at 384).

**Baidu Netdisk** (code **8848**):

- Windows bundle: https://pan.baidu.com/s/1Y8DXyby6ZurjYscQKorsCw?pwd=8848
- macOS bundle: https://pan.baidu.com/s/1orsQ9RngYvnAi8pLO7Qb_w?pwd=8848
