**1.0.3：修好的成品 JPG 直接就能训练，不用原图、不用 XMP；同时修掉上一版训练完「提示完成但模型没生效」的问题。**

## 这版修了什么（针对 1.0.2 的问题）

| 1.0.2 里的问题 | 现在的行为 |
|---|---|
| 只有修好的成片时，训练报「可用样本少于 50 张」 | 新增「添加成品 JPG」入口，成片直接可训 |
| 训练跑完显示「完成」，但模型库里没有新模型，推理用的还是旧系数 | 收录失败会直接报错，不再假成功 |
| 模型库只接受「全幅坐标」格式的系数，另一种空间写不进去 | 两种空间都能收录、都能在软件里切换 |
| 裁切框在成片相对空间算出来，却仍按全幅公式去解，框是错的 | 推理按系数里的空间分流，各走各的公式 |

## 这版新增

**「添加成品 JPG」：只有成片也能训练**

成片就是裁切后的那张画面，所以在成片上量两件事就够了——虫体占画面多少、虫心偏画面中心多少。
这些比例只由虫子形状决定，与画幅无关。模型学「形状 → 该放大多少倍、往哪偏」，推理时反解：

    成片宽 W = 虫宽 × 2^t0
    成片中心 = 虫心 − (ox·W, oy·H)

**验证**：用已知规律合成 240 张成片，只用成片训练，再拿 60 张没见过的原片反解，**IoU 中位 0.9997**；
真实 60 张成片训练后，模型对原片的推理框与虫体框位置关系正常。

现在训练页三个入口：

| 手上有什么 | 用哪个 |
|---|---|
| RAW 或全幅 JPG + 同名 XMP | 「添加目录」 |
| 修好的成品 JPG（无原图） | 「添加成品 JPG」 |
| 成品 JPG + 未裁原图 | 「添加原图与成品 JPG」 |

三者都至少 50 张。

## 升级

只替换 `exe` 与 `_internal\`，**保留 `data\`**（你训练的模型和头点记忆在里面）。

`iKunInsectStudio_v1.0.3.zip.001`、`.002` 与 `join-parts.bat` 放同一文件夹，双击 bat 合成 zip，解压即用。

Windows 10/11 + NVIDIA 显卡（4 GB 显存起；2 GB 可用 384 档）。

**百度网盘**（提取码 8848）：https://pan.baidu.com/s/1dkWKy9bxWnTreHFD5cCBVA?pwd=8848

---

**1.0.3: finished JPEG exports train on their own — no originals, no XMP. Also fixes "training reports done
but no model is installed" from the previous release.**

## Fixed since 1.0.2

| Problem in 1.0.2 | Behaviour now |
|---|---|
| With only finished exports, training failed with "fewer than 50 usable samples" | New **Add JPEG exports only** entry; exports train directly |
| Training said "done" while the model library gained nothing, so inference kept using the old coefficients | A failed adoption now raises instead of reporting success |
| The library accepted only full-frame coefficient files; the other space could not be stored | Both spaces are stored and switchable in the app |
| Boxes computed in the export-relative space were still solved with the full-frame formula, producing wrong crops | Inference dispatches on the space recorded in the coefficients |

## Added

**Add JPEG exports only**

An export *is* the frame after cropping, so two measurements suffice: how much of the frame the insect
takes, and how far its centre sits from the frame centre. Those ratios depend on the animal, not on the
frame size. The model learns "shape → how many times larger, offset by how much" and inverts at inference:

    W = body width × 2^t0        centre = body centre − (ox·W, oy·H)

**Verified**: 240 synthetic exports from a known rule, trained on exports only, then inverted on 60 unseen
frames — **median IoU 0.9997**. On 60 real exports the fitted model places boxes correctly on originals.

Three entries in the Train tab:

| What you have | Which one |
|---|---|
| RAW or full-frame JPG + sidecar XMP | Add folder |
| Finished exports, no originals | Add JPEG exports only |
| Exports plus uncropped originals | Add originals and JPEG exports |

All three need at least 50 photos.

## Upgrading

Replace `exe` and `_internal\` only, **keep `data\`** (your trained models and head corrections live there).

Put `iKunInsectStudio_v1.0.3.zip.001`, `.002` and `join-parts.bat` in one folder, run the bat, unzip, run.

Windows 10/11 with an NVIDIA GPU (4 GB VRAM; 2 GB works at 384).

**Baidu Netdisk** (code 8848): https://pan.baidu.com/s/1dkWKy9bxWnTreHFD5cCBVA?pwd=8848
