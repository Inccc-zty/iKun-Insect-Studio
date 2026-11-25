**1.0.1：小显存也能稳定跑，训练页按你的方式挑图，加数据不用重跑老图。**

### 这版改了什么

**更快、更省显存**
- 掩膜精度新增 **384 档**：2 GB 显存的机器也能稳定跑，实测 0.39 秒/张（768 是 0.77 秒）
- 显存不够时依旧自动降级，结果标 `degraded`，不会静默给错框
- 每张的耗时写进 `data/perf.log`，卡在哪一段一眼能看出来

**训练页**
- 每个文件夹显示「（N 张）」——加入多少就显示多少，可以只训练你拖进来的那几张
- 修复「明明几百张却提示少于 50 张无法拟合」：连拍去重把 533 对压成了 29 对
- 提取结果会缓存，下次加新照片时旧图直接复用，不重跑
- 支持**暂停 / 继续**训练
- 训练完成自动切到新模型；模型文件被删会自动回落到内置
- 「重置到初始状态」**保留你训练/导入的模型**

**界面**
- 曝光预览跟随实时预览：关掉实时预览时自动关闭，再打开时恢复上次状态
- 深色模式两条白缝修复（左右分栏、预览与拼版之间）
- 图标改为透明底，只留虫体
- 说明页新增「检查更新」，与 `version.json` 联动
- 中英切换：版本行、未选择照片、训练列表等不再残留中文

### 下载

1. 下载 `iKunInsectStudio_v1.0.1.zip.001`、`.002` 和 `join-parts.bat`，放同一个文件夹
2. 双击 `join-parts.bat`，得到 `iKunInsectStudio_v1.0.1.zip`
3. 解压 → 双击 `iKunInsectStudio.exe`（**整个文件夹要一起留着**）
4. 从 1.0.0 升级：只替换 `exe` 和 `_internal\`，**保留 `data\`**（那里有你训练的模型和头点记忆）

需要 Windows 10/11 + NVIDIA 显卡（4 GB 显存起，2 GB 可跑 384 档）。

**百度网盘备用**（提取码 8848）：https://pan.baidu.com/s/1jU0VFZo8SVXKQgvZ83TGPg?pwd=8848

---

**1.0.1: stable on small GPUs, training that works the way you pick photos, and no re-running old frames.**

### What changed

**Faster, leaner on VRAM**
- New **384 px** mask tier: a 2 GB card now runs steadily, 0.39 s per photo measured (768 is 0.77 s)
- Out of VRAM still degrades gracefully and flags `degraded` — never a silently wrong box
- Per-photo timing is written to `data/perf.log`

**Training tab**
- Each folder shows **(N photos)** — exactly what you added, and you can train only the frames you picked
- Fixed "hundreds of pairs but it says fewer than 50": burst de-duplication had collapsed 533 pairs into 29
- Extraction results are cached; adding new photos no longer re-runs the old ones
- **Pause / resume** while training
- Switching to the freshly trained model is automatic; a deleted model file falls back to the built-in one
- "Reset to initial state" **keeps the models you trained**

**Interface**
- Exposure preview follows the live-preview switch, restoring its previous state
- Two white seams in dark mode fixed (splitter handles)
- Logo is now a transparent cut-out of the insect itself
- About tab gained **Check for updates**, wired to `version.json`
- Language switch no longer leaves Chinese in the version line, empty-selection label or training rows

### Download

1. Get `iKunInsectStudio_v1.0.1.zip.001`, `.002` and `join-parts.bat` into one folder
2. Run `join-parts.bat` → `iKunInsectStudio_v1.0.1.zip`
3. Unzip, keep the whole folder together, double-click `iKunInsectStudio.exe`
4. Upgrading from 1.0.0: replace `exe` and `_internal\` only, **keep `data\`** (your trained models and head corrections live there)

Windows 10/11 with an NVIDIA GPU (4 GB VRAM; 2 GB works at 384).

**Baidu Netdisk mirror** (code 8848): https://pan.baidu.com/s/1jU0VFZo8SVXKQgvZ83TGPg?pwd=8848
