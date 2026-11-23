# 07 · XMP 与 Lightroom

## 1. 为什么用 XMP，而不是直接改目录

Lightroom 的调整存在两个地方：

- **目录数据库**（`.lrcat`）：LR 自己的 SQLite，正在运行时被锁；
- **XMP sidecar**：照片旁边的同名 `.xmp`，纯文本。

走 XMP 的好处：

1. **不需要 LR 正在运行**，更不需要重启 LR；
2. 可读、可 diff、可备份、可回滚；
3. LR 有官方入口把它读进来：「从文件读取元数据」。

**这条很重要**：你明确说过不许重启 Lightroom（会清空照片选区）。
整条流水线就是按"LR 可以一直开着"设计的。

## 2. 写哪些字段（以及为什么只写这些）

```xml
crs:WhiteBalance="Custom"      <!-- 仅 --wb 时写；默认不写这三行 -->
crs:Temperature="5333"         <!-- 同上 -->
crs:Tint="+16"                 <!-- 同上 -->
crs:Exposure2012="+0.88"
crs:Sharpness="65"          <!-- f<14 时才写 -->
crs:CameraProfile="Camera Standard"
crs:CropTop / CropLeft / CropBottom / CropRight
crs:CropAngle="0"
crs:HasCrop="True"
crs:HasSettings="True"
crs:AlreadyApplied="False"
crs:RawFileName="Z04_7816.NEF"
```

**就这些。** 其余一概不写。

> **白平衡默认不写**（2026-11-16 起）：XMP 里不出现 `WhiteBalance / Temperature / Tint`，
> Lightroom 沿用相机 As Shot。要写回加 `--wb`。字段模板本身没变，`xmp_write.build()`
> 在 `T=None 或 tint=None` 时自动省略这三行。

### 为什么不写高光/阴影/清晰度/曲线

LR 的「从文件读取元数据」**只应用 XMP 里出现的字段**，缺失的保持原值。

所以：不写 = 不碰。写 0 = 把你的调整清零。

**v1 在这里犯过一个必须记住的错**：它的模板里硬写了

```
Contrast2012 / Highlights2012 / Shadows2012 / Whites2012 / Blacks2012
Texture / Clarity2012 / Dehaze / Vibrance / Saturation = 0
```

外加一条直线 `ToneCurvePV2012 = [(0,0),(255,255)]`。
读一次 XMP，你在 LR 里调过的这些东西全部归零。
而它的 SKILL.md 当时写的是"不做高光/阴影/清晰度"——文档说不对，代码全做了。

本 skill 的防线：`xmp_write.assert_minimal()` 在每次生成后检查，
一旦出现上面这些字段（或 `ToneCurve`）直接抛错，`pipeline.py` 会中断并报出文件名。

## 3. 格式上的几个硬要求

来自对 LR 自己写出的 XMP 的实证：

| 要求 | 原因 |
|---|---|
| 不用 `<?xpacket>` 包裹，直接 `<x:xmpmeta>` | LR 接受，且更简单 |
| `crs:Version="16.0"`、`crs:ProcessVersion="15.4"` | 版本太低 LR 会按旧流程解释 |
| 裁切是**左上原点的绝对坐标**，已归一化 | Left/Right ÷ 图宽，Top/Bottom ÷ 图高 |
| 必须带 `crs:RawFileName` | 否则 LR 可能不认这个 sidecar |
| `crs:HasSettings="True"`、`crs:HasCrop="True"` | 缺了不生效 |
| 不写 `CropConstrainAspectRatio` | LR 自己也不写 |

`CameraProfile` 默认写 `Camera Standard`——这是你给动物/生态/昆虫定的配置。
如果某批想保留你在 LR 里选的那个，传 `profile=None` 即可不写。

## 4. 在 LR 里怎么生效

1. 打开 LR → 进入照片所在文件夹；
2. 全选 → 右键 → **「从文件读取元数据」**；
3. 完成。裁切、曝光、色温、锐化会同时套上。

**不要做的事：**

- 不要用「导入」去覆盖目录（会重建条目，可能丢收藏/关键词）；
- 不要在 LR 里对这些照片点「保存元数据到文件」——那会把 LR 里的旧值写回去；
- 如果某张已经在 LR 里精修过，先备份再读元数据，否则会被覆盖。

## 5. 备份与回滚

`pipeline.py --apply` 在写之前，会把已有的 `.xmp` 复制到：

```
照片目录/_xmp_backup/<同名>.xmp
```

回滚：

```bash
cp 照片目录/_xmp_backup/*.xmp 照片目录/
```

或者在 LR 里对这批照片「还原」——但 XMP 已经被覆盖，LR 的还原只对当前会话有效。
**所以写之前一定先备份。**

## 6. 裁切的分母

XMP 的裁切坐标是相对**传感器有效像素**，掩膜是在**内嵌预览**上算的。

实测 Z8 两者都是 **8256×5504**（`sensor_size()` 返回 `raw.sizes.crop_width/height`），
完全一致，没有需要补偿的偏移。

但如果相机改用非满幅裁切模式（DX 1.5×），必须用 `crop_width/height`，不能用预览尺寸。
`nef_io.sensor_size()` 已经处理了这一点。

## 7. 写完自查

```python
import glob, re
for f in sorted(glob.glob('照片目录/*.xmp'))[:3]:
    t = open(f, encoding='utf-8').read()
    print(f.split('\\')[-1],
          re.search(r'crs:Exposure2012="([^"]*)"', t).group(1),
          re.search(r'crs:Temperature="([^"]*)"', t).group(1),
          re.search(r'crs:Sharpness="([^"]*)"', t).group(1) if 'Sharpness' in t else '默认')
```

三条都对，再让 LR 读。另外确认**没有** `Highlights2012` 等字段。
