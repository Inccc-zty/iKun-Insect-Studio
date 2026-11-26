# iKun Insect Studio

**把昆虫微距里最枯燥的部分做掉：找虫、定框、给曝光。**

外拍一天回来，每个个体都要留一张记录，真正精修的只有几张。微距题材里虫子天生在画面中偏小，于是时间都花在剩下那几十上百张的重复裁切、重复调曝光上。这个软件把那部分收成一步：拖进文件夹，每张给一个裁切框和一次曝光，结果写成 Lightroom 能直接读的 `.xmp`，导入即生效。

- **裁切**：全画幅掩膜找出虫体，外接框 + 躯干框 + 头点 → 105 项模型给出裁切框，留出 IoU **0.865**
- **曝光**：掩膜内 p95 与框内掩膜外 p95，两个数进一条直线，留出 MAE **0.29 EV**
- **锐化**：按光圈查表（20 → 65）
- **学你的构图**：拿你自己修好的成品 JPG 即可重拟合裁切模型，不需要原图、不需要 XMP

> 裁切和曝光都可能出错，没有一个是 100% 准的。它的价值不是"准"，是把重复劳动从几小时压到几分钟。

---

## 这个版本更新了什么（1.0.6）

| 平台 | 文件 | 大小 | 说明 |
|---|---|---:|---|
| Windows | `iKunInsectStudio_v1.0.6.zip.001` / `.002` / `.003` + `join-parts.bat` | 3.38 GB | 合并后解压 |
| **macOS** | `iKunInsectStudio_macOS_arm64.zip` | **0.78 GB** | Apple 芯片（M1 及以后），解压得到 `.app` |

**Mac 版怎么装**：解压 → 把 `iKunInsectStudio.app` 拖进「应用程序」→ 首次打开若提示"无法验证开发者"，
右键点图标选「打开」，或执行一次：

```
xattr -dr com.apple.quarantine /Applications/iKunInsectStudio.app
```

包没有苹果签名，这一步只清掉 Gatekeeper 的隔离标记。**Intel Mac 跑不了**——PyTorch 已不再发布
Intel macOS 的二进制。Mac 版在 CI 里跑过自检（加载 BiRefNet、前向、解框全过），但这台机器没有
Apple 芯片，实际速度要你那边测：M1/M2 走 MPS，8 GB 内存建议精度选 512。

**更重要的一个修复：包里现在自带模型了**

之前的分发包**不含** BiRefNet 权重，靠 `HF_HOME` 指向开发者本机的缓存目录。别人装上以后这个目录不存在，
第一次推理就去联网下载；下不到（没网、被墙、盘符不存在）就每张都是红的。这就是"只有我这台能跑"的原因。

现在：

- BiRefNet（848 MB）在打包时塞进 `_internal/hf`，**开箱即用，不联网**
- 启动时按「包内 `hf/` → 旧缓存路径 → `data/hf`」依次找，找不到才联网下载
- 包体从 2.6 GB 涨到约 3.4 GB（压缩后），换来的是别人装上就能跑

**为了跨平台改了什么**

| 问题 | 处理 |
|---|---|
| 设备只认 `cuda` / `cpu` | 改成 `cuda → mps → cpu` 自动选；Apple 芯片走 MPS |
| `torch.cuda.empty_cache()` 在无 CUDA 机器上会抛错 | 加可用性判断，只在真有 CUDA 时调用 |
| 模型缓存写死 `D:/反渲染的研究/.cache/hf` | 改成：包内 `hf/`（打包时预下载）→ 否则 `data/hf`；Mac 上不会出现名为 `D:` 的目录 |
| 「打开所在文件夹」用 `os.startfile`（Windows 专有） | 抽到 `app/sysenv.py`，macOS 走 `open` |
| 打包脚本只有 Windows 一套 | 新增 `build_mac.py`，`.app` 用 ditto 压（`zip -r` 会破坏 bundle 结构） |
| 分发包不带模型，别人跑不了 | BiRefNet 打进 `_internal/hf`，离线可用 |

**macOS 上的性能**：Apple 芯片用 MPS，第一次推理会慢一些（编译内核），之后接近同档显卡；
8 GB 内存的机器建议精度选 512。

**另外：裁切比例可以选了**

参数区多了一个下拉（和「分割精度」同一排）：`原图比例`（默认，老行为）/ `1:1` / `4:5` / `3:2` / `16:9` / `自定义`。
选中的比例会同时作用于两条裁切路径；`原图比例` 时行为与 1.0.5 完全一致。实测（8256×5504 原片）：

| 选择 | 归一化框 | 实际像素比例 |
|---|---|---|
| 原图比例 | 0.5049 × 0.5049 | 1.500 |
| 1:1 | 0.5049 × 0.7573 | 1.000 |
| 4:5 | 0.5049 × 0.9467 | 0.800 |
| 16:9 | 0.5049 × 0.4260 | 1.778 |

## 下载与升级

**Windows**：`…zip.001`、`.002` 与 `join-parts.bat` 放同一文件夹，双击 bat 合成 zip，解压后运行
`iKunInsectStudio.exe`（整个文件夹一起留着）。升级只替换 `exe` 与 `_internal\`，**保留 `data\`**。

**macOS**：解压后把 `.app` 拖进「应用程序」。升级直接覆盖整个 `.app`，`data/` 在
`~/Library/Application Support/iKunInsectStudio`，不会被覆盖。

**精度按可用显存选**：4 GB 卡选 **512**，6 GB 以上选 768。选高于可用显存的档不会报错，
但会走系统分页，从 0.8 秒掉到 3 秒以上。

**百度网盘**（提取码 8848）：https://pan.baidu.com/s/1Y8DXyby6ZurjYscQKorsCw?pwd=8848

---
---

# iKun Insect Studio

**The two most repetitive jobs in insect macro, done in one pass: find the bug, place the crop, set the exposure.**

A day out shooting means one record frame per individual, and only a handful worth a full edit. In macro work the insect is always small in the frame, so the hours go into the ninety records — crop after crop, exposure after exposure. This tool folds that into one step: drop a folder in, and every frame gets a crop box and an exposure value, written as a `.xmp` your editor reads on import.

- **Crop** — a full-frame mask finds the insect, then a body box, a whole box and a head point feed a 105-term model. Hold-out IoU **0.865**
- **Exposure** — two p95 brightness numbers into one straight line; hold-out MAE **0.29 EV**
- **Sharpening** — by aperture, 20 → 65
- **Learns your framing** — refit the crop model on your own finished JPEGs; no originals, no XMP

> Crop and exposure can both be wrong — nothing here is 100%. The value is not accuracy, it is turning hours of repetitive editing into minutes.

---

## What changed in 1.0.6

| Platform | File | Size | Notes |
|---|---|---:|---|
| Windows | `iKunInsectStudio_v1.0.6.zip.001` / `.002` / `.003` + `join-parts.bat` | 3.38 GB | merge, then unzip |
| **macOS** | `iKunInsectStudio_macOS_arm64.zip` | **0.78 GB** | Apple Silicon (M1+), unzip to get the `.app` |

**Installing on macOS**: unzip, drag `iKunInsectStudio.app` into Applications. If macOS complains about an
unverified developer, right-click the icon and choose Open, or run once:

```
xattr -dr com.apple.quarantine /Applications/iKunInsectStudio.app
```

The bundle is unsigned; that only clears Gatekeeper's quarantine flag. **Intel Macs are not supported** —
PyTorch no longer publishes Intel macOS binaries. The app passed its selftest inside CI (BiRefNet loaded, one
forward pass, coefficients resolved), but this runner has no Apple silicon, so real speed is yours to measure:
M1/M2 use MPS, and an 8 GB machine should pick tier 512.

**What had to change for cross-platform**

| Problem | Fix |
|---|---|
| Device was `cuda` / `cpu` only | now `cuda → mps → cpu`; Apple Silicon uses MPS |
| `torch.cuda.empty_cache()` throws where there is no CUDA | guarded by an availability check |
| Model cache hard-coded to a Windows path | now: bundled `hf/` → else `data/hf`; no stray `D:` folder on macOS |
| "Reveal in folder" used `os.startfile` | moved to `app/sysenv.py`; macOS uses `open` |
| Only a Windows build script existed | added `build_mac.py`; the `.app` is zipped with `ditto` (`zip -r` breaks bundles) |

**Performance on macOS**: MPS is slower on the very first inference (kernel compilation), then comparable.
On an 8 GB machine pick tier 512.

**The Windows build was rebuilt too**, purely so both sides run identical code — no functional change over 1.0.5.

## Download and upgrade

**Windows**: put `…zip.001`, `.002` and `join-parts.bat` in one folder, run the bat, unzip, run
`iKunInsectStudio.exe`. Upgrading: replace `exe` and `_internal\` only, **keep `data\`**.

**macOS**: unzip, drag the `.app` into Applications. Upgrading replaces the bundle; `data/` lives in
`~/Library/Application Support/iKunInsectStudio` and survives.

**Pick the mask tier by free VRAM**: 512 on 4 GB cards, 768 on 6 GB and up. A tier above free VRAM does not
error — it pages through system memory and drops from 0.8 s to over 3 s.

**Baidu Netdisk** (code 8848): https://pan.baidu.com/s/1Y8DXyby6ZurjYscQKorsCw?pwd=8848
