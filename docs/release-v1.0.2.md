**1.0.2：训练可以喂三种数据——RAW+XMP、全幅 JPG+XMP、以及只有成品 JPG 的裁切导出。**

### 这版改了什么

**训练数据（本次的主要改动）**

- 新增「**添加原图与成品 JPG**」入口：先选未裁切原图目录，再选对应的成品 JPG 目录，
  没有 XMP 也能训练
- 软件用特征点配准反推裁切框：验证这一对确实是同一张照片、且是轴对齐裁切；
  **配不上就跳过**，不会把不相干的图硬凑成样本；同名原图有两份时同样拒收
- 复原精度实测：三种不同裁切位置，归一化误差 **0.000**
- 原图损坏只跳过那一张，不中断整批
- 训练结果区分标注来源：XMP 来的与图配准来的，各自记在 `trainset.csv` 的 `label_path` 列

**稳定性**

- 提取缓存按分割精度分键：换 384/512/768 不再复用旧结果
- 样本不足时的报错写明「有效裁切样本 N/50」，不再笼统说少于 50 张
- 裁切拟合失败会明确报错，不再静默标「完成」

### 训练数据怎么选

| 你手上有什么 | 怎么做 |
|---|---|
| RAW + 同名 XMP | 训练页 →「添加目录」 |
| 全幅 JPG + 同名 XMP | 训练页 →「添加目录」 |
| 只有裁好的成品 JPG（有原图） | 训练页 →「添加原图与成品 JPG」，两个目录同名同结构 |
| 只有裁好的成品 JPG（无原图） | 无法训练：被裁掉的画面已不在文件里 |

### 下载

下载 `iKunInsectStudio_v1.0.2.zip.001`、`.002` 和 `join-parts.bat`，放同一文件夹，
双击 `join-parts.bat` 合成 zip，解压后运行 `iKunInsectStudio.exe`（整个文件夹要一起留着）。

从旧版升级：只替换 `exe` 与 `_internal\`，**保留 `data\`**（训练的模型和头点记忆在里面）。

需要 Windows 10/11 + NVIDIA 显卡（4 GB 显存起；2 GB 可用 384 档）。

**百度网盘**（提取码 8848）：https://pan.baidu.com/s/1l1-JLttPB9EuO1Mz6AbbIw?pwd=8848

---

**1.0.2: training now takes three kinds of input — RAW+XMP, full-frame JPG+XMP, and plain cropped
JPEG exports.**

### What changed

**Training data (the point of this release)**

- New **Add originals and JPEG exports** entry: pick the uncropped originals folder, then the matching
  export folder — no XMP required
- The app recovers the crop box by feature registration, verifying that the pair really is the same
  photo and that the crop is axis-aligned; **unverified pairs are skipped**, and a stem with two
  candidate originals is rejected
- Measured recovery error across three different crop positions: **0.000** normalised
- A corrupt original skips that frame only, never the batch
- Where each label came from is recorded per row (`label_path` in `trainset.csv`)

**Robustness**

- The extraction cache is keyed by mask size, so switching 384/512/768 no longer reuses stale rows
- The "not enough samples" error now reports the usable count (N/50)
- A failed crop fit is reported as an error instead of a silent "done"

### Choosing your input

| What you have | What to do |
|---|---|
| RAW + sidecar XMP | Train tab → Add folder |
| Full-frame JPG + sidecar XMP | Train tab → Add folder |
| Cropped exports, originals available | Train tab → Add originals and JPEG exports |
| Cropped exports only | Cannot train — the discarded part of the frame is gone |

### Download

Get `iKunInsectStudio_v1.0.2.zip.001`, `.002` and `join-parts.bat` into one folder, run
`join-parts.bat`, unzip, and launch `iKunInsectStudio.exe` (keep the whole folder together).

Upgrading: replace `exe` and `_internal\` only, **keep `data\`**.

Windows 10/11 with an NVIDIA GPU (4 GB VRAM; 2 GB works at 384).

**Baidu Netdisk** (code 8848): https://pan.baidu.com/s/1l1-JLttPB9EuO1Mz6AbbIw?pwd=8848
