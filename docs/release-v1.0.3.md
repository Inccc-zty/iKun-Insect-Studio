**1.0.3：修好的成片 JPG 直接就能训练，不用原图、不用 XMP。**

### 这版改了什么

**裁切训练：三种数据都能用**

| 你手上有什么 | 入口 |
|---|---|
| RAW 或全幅 JPG + 同名 XMP | 「添加目录」 |
| **修好的成品 JPG（没有原图）** | 「**添加成品 JPG**」← 本版新增 |
| 成品 JPG + 对应未裁原图 | 「添加原图与成品 JPG」 |

**为什么成片就够**：成片本身就是裁切后的画面。在成片上跑一次掩膜，能直接量出虫体占画面多少、
虫心偏离画面中心多少；这些比例由虫子形状决定，与画幅大小无关，所以模型学到的
「形状 → 该放大多少倍、往哪偏」可以直接反解成裁切框：

    成片宽 W = 虫宽 × 2^t0      成片中心 = 虫心 − (ox·W, oy·H)

**验证**：用已知规律生成成片（宽 = 虫宽 ×（4 + 0.6×附肢比），宽高比 1.25，虫心偏 2%/3%），
只用成片训练，再拿 60 张没见过的原片反解——**IoU 中位 0.9997**。

**其它修正**

- 训练产物现在一定会进模型库；收不进去会直接报错，不再「显示完成但没有模型」
- 成片模型在软件里可以正常参与推理（按成片相对空间解框，仍守「不出界 → 腿留白 3%」）

### 下载

`iKunInsectStudio_v1.0.3.zip.001`、`.002` 与 `join-parts.bat` 放同一文件夹，双击 bat 合成 zip，
解压后运行 `iKunInsectStudio.exe`（整个文件夹一起留着）。

从旧版升级：只替换 `exe` 与 `_internal\`，**保留 `data\`**（训练的模型与头点记忆在里面）。

Windows 10/11 + NVIDIA 显卡（4 GB 显存起；2 GB 可用 384 档）。

**百度网盘**（提取码 8848）：https://pan.baidu.com/s/1dkWKy9bxWnTreHFD5cCBVA?pwd=8848

---

**1.0.3: finished JPEG exports are enough to train — no originals, no XMP.**

### What changed

**Crop training now takes three shapes of data**

| What you have | Entry |
|---|---|
| RAW or full-frame JPG + sidecar XMP | Add folder |
| **Finished exports, no originals** | **Add JPEG exports only** ← new |
| Exports plus uncropped originals | Add originals and JPEG exports |

**Why exports suffice**: an export *is* the frame after cropping. Mask it once and you can measure how
much of the frame the insect takes and how far its centre sits from the frame centre. Those ratios are
properties of the animal, not of the frame size, so "shape → how many times larger, offset by how much"
inverts straight into a crop box:

    W = body width × 2^t0      centre = body centre − (ox·W, oy·H)

**Verified**: generate exports with a known rule (width = body width × (4 + 0.6·limb ratio), aspect
1.25, offset 2%/3%), train on exports only, then invert on 60 unseen frames — **median IoU 0.9997**.

**Other fixes**

- A trained model is always adopted into the model library, and a failure now errors out instead of
  reporting "done" with no model installed
- Crop-relative models run in the app's inference path, still honouring "stay in frame → 3% limb margin"

### Download

Put `iKunInsectStudio_v1.0.3.zip.001`, `.002` and `join-parts.bat` in one folder, run the bat, unzip, and
launch `iKunInsectStudio.exe` (keep the whole folder together).

Upgrading: replace `exe` and `_internal\` only, **keep `data\`**.

Windows 10/11 with an NVIDIA GPU (4 GB VRAM; 2 GB works at 384).

**Baidu Netdisk** (code 8848): https://pan.baidu.com/s/1dkWKy9bxWnTreHFD5cCBVA?pwd=8848
