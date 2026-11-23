# Insect Auto Post · 昆虫微距自动后期

把一批**没修过的昆虫微距 RAW** 变成一批 **Lightroom 能直接读的 XMP**。
三个模块都只做「能规则化、且必须逐张做」的事：**裁切、曝光、锐化**（白平衡可选）。

> English: a batch post-processing pipeline for macro insect RAW files. One BiRefNet mask
> feeds both a 105-term ridge-regression cropper and a two-parameter exposure model;
> a small self-trained ResNet50 heatmap regressor supplies the head point. Output is
> Lightroom-compatible XMP sidecars. White balance is calibrated but off by default.

---

## 一条链路，一个掩膜

```
RAW ──extract_thumb()──► 全幅内嵌预览 (8256×5504)
      ──Resize 768──► BiRefNet ──► 全幅掩膜
                                    ├─ 开运算 → core 框（躯干）
                                    ├─ 外接框 → full 框（含附肢）
                                    └─ core 外扩 15% → 256px chip
                                          └─ ResNet50 热力图 → 头心 (hx,hy)
core / full / 头心 ──► 裁切 105 项 ──► CropLeft/Top/Right/Bottom
同一份掩膜亮度分位 ──► L_in / L_box ──► 曝光双参数 ──► Exposure2012
EXIF 光圈 ──► 分档 ──► Sharpness
                ↓
            XMP sidecar
```

**掩膜只算一次。** 裁切和曝光都要知道「虫在哪」，各跑一遍会得到两套互不相容的坐标。

---

## 三个模块

| 模块 | 形式 | 样本 | 留出精度 |
|---|---|---|---|
| 裁切 | 13 项特征 → 二次展开 105 项，岭回归预测 框心 x / 框心 y / log2(框宽) | 4184 张 / 11 批 | IoU 中位 **0.8650**（样本内 0.8756，80 张盲测 0.9017） |
| 曝光 | `EV = 3.0416 − 0.02108·L_in − 0.01362·L_box` | 4396 张 / 11 批 | MAE **0.286 档**（常数基线 0.42） |
| 锐化 | 按光圈分档，严格递增：≤2.8→20，<4→30，<5.6→40，<11→50，<14→60，≥14→65 | — | 抵消衍射的经验表（`assets/data/sharpen_table.csv`，可改） |
| 头部 | ResNet50 双尺度融合 + 64×64 热力图 + soft-argmax，256px chip | 见 `references/02` | 见下方「头部精度」 |
| 白平衡 | 常数 5333 K / +16 + 14 条批次例外（**默认不写**） | 1585 张 | MAE 163 K |

裁切的硬约束顺序不可调换：**① 绝不出界 > ② 腿到框边 ≥3% > ③ IoU 好看**。
多主体（交配对、两只并排）强制关掉头部项，仍出框。

### 头部精度

| 口径 | 值 |
|---|---|
| 误差中位（6 张有标注 RAW，core 框与标注同坐标空间） | **0.12·core 宽**（p75 0.17，最大 ≤0.20） |
| 跨 5 个批次随机抽 15 张实跑 | **15/15** 给出头点；人工放大核对 3 张均落在头上 |
| 训练期记录（口径未固定，谨慎引用） | ResNet50 + 软目标交叉熵 **90%**；对照：从零训 4 层 + MSE 5%、+软目标 22% |

样本量都不大，**别把 90% 当硬指标**——它只证明「换 ResNet50 骨干 + 软目标」这一步是对的。

置信度只做**极低门槛**（0.02）+ 几何校验（头点必须落在 core 外扩 20% 内）。
原因：这个网络的 softmax 峰值本来就在 0.034–0.064 之间，
早期用 0.05 当阈值等于卡在分布中位，会丢掉约 1/3 正确的点。

用户拖正过的头点会进 `head_fix.py` 的修正记忆：3 条起按 6 近邻补偿，
25 条起自动改成一个 7 参数线性残差模型（每次新增自动重拟合），不碰网络权重。
细节见 `SKILL.md` §2.6。

---

## 安装

```bash
git clone <this-repo>
cd insect-auto-post
python -m venv .venv && .venv/Scripts/activate      # Windows
pip install -r requirements.txt
```

- **BiRefNet 权重**：首次运行由 `transformers` 自动从 HuggingFace 拉
  （`ZhengPeng7/BiRefNet`，约 424 MB）。离线环境先设 `HF_HOME` 指到已有缓存。
- **头部权重** `assets/weights/head_kp_v2.pth`（**99 MB**）已随仓库提供。
  GitHub 单文件上限 100 MiB，刚好能进；建议用 **Git LFS**：
  ```bash
  git lfs install
  git lfs track "assets/weights/*.pth"
  ```

## 快速开始

```bash
# 0) 空跑：只看参数，不动照片
python scripts/pipeline.py --dir /path/to/raws --out ./_xmp

# 1) 抽 5 张出叠加检查图（掩膜 / core / full / 裁切框 / 头点）
python scripts/pipeline.py --dir /path/to/raws --out ./_xmp --limit 5 --sheet

# 2) 确认后写回照片目录（旧 XMP 自动备份到 _xmp_backup/）
python scripts/pipeline.py --dir /path/to/raws --apply

# 可选：把白平衡也写进 XMP（默认不写，沿用相机 As Shot）
python scripts/pipeline.py --dir /path/to/raws --apply --wb
```

输出 `params.csv`：每张的 EV / L_in / L_box / 光圈 / 锐化 / 框宽 / 是否饱和 /
是否画布受限 / 腿留白是否达标。

分两条线跑（改参数不用重跑分割）：

```bash
python scripts/stages.py mask     --dir /path/to/raws --cache ./_stage
python scripts/stages.py exposure --cache ./_stage     # → exposure.csv
python scripts/stages.py crop     --cache ./_stage     # → crop.csv
python scripts/stages.py write    --cache ./_stage --out ./_xmp
```

### 自查（纯 CPU，秒级）

```bash
python scripts/crop_v3.py
# 应为：中位 0.8756 / 均值 0.8487 / ≥0.8 76.8% / 画布受限 2.6%
```

对不上就说明系数或特征顺序被改过。

---

## 目录

| 路径 | 内容 |
|---|---|
| `SKILL.md` | 给 Agent 用的技能说明（结构、铁律、边界） |
| `说明书.md` | 从零到出 XMP 的操作手册 |
| `references/01`–`10` | 口径与数据、掩膜与头部、裁切、曝光、白平衡、锐化、XMP、验证、移植、弯路 |
| `assets/data/*.json` | 裁切 / 曝光系数 |
| `assets/data/*.csv` | 自检表、白平衡例外表、锐化分档 |
| `assets/weights/head_kp_v2.pth` | 头部关键点权重 |
| `scripts/` | 流水线、分线、重拟合、自检 |

---

## 边界（先说清楚，免得白试）

1. **只对微距、单只主体、虫体完整**的片子成立。混进风景/花絮会 `mask_empty`，这是正常的。
2. **小虫是唯一系统性弱点**：虫宽 < 全幅 8% 时，768 输入下虫子只有 20–60 px，掩膜会糊。
3. **8-bit 高光饱和**：`L_in ≥ 96` 的照片（约 11.5%）EV 不可信，需人工核。
4. **白平衡不做自动估计**：常数 + 例外表就是上限，换一场没见过的光要人工加一行。
5. **EV 截距绑定渲染器**：b0 与 L\* 刻度绑定在「RAW 内嵌预览」上，换渲染器要重标。
6. **裁切系数是某个人的构图习惯**：换人要用他自己的成品重拟合，不能直接套。

## 数据与合规

- 仓库**不含任何原始照片**。`assets/data/selftest_crop_4184.csv` 只有归一化几何真值
  （裁切四边、core/full 框、头点），文件名已去掉路径，仅用于回归自检。
- `crop_coef_v3.json` 的训练集（4184 张）来自个人作品集，**未包含在仓库内**；
  想换一套系数请用 `scripts/refit_crop.py` 在自有数据上重拟合（见 `references/09`）。

## 上传到 GitHub（第一次）

```bash
cd insect-auto-post
git init
git lfs install
git lfs track "assets/weights/*.pth"
git add .gitattributes
git add .
git commit -m "insect auto post: crop v3 + exposure + sharpen -> XMP"
git branch -M main
git remote add origin git@github.com:<你的账号>/insect-auto-post.git
git push -u origin main
```

要点：

- `.pth` 是 94.4 MiB，低于 GitHub 单文件 100 MiB 硬上限，**不加 LFS 也能推**；
  但加了 LFS 更稳（以后换权重不会撑爆仓库）。不加 LFS 时把上面 `git lfs` 三行删掉即可。
- 仓库里没有原始照片，`assets/data/*.csv` 只有归一化几何真值与批次名。
- `.gitignore` 已排除 `_xmp/`、`_stage/`、`__pycache__`、`*.xmp` 等运行产物。

## 许可

MIT，见 `LICENSE`。模型权重的使用请遵守各自上游许可（BiRefNet: MIT；ResNet50 预训练权重: BSD-3）。
