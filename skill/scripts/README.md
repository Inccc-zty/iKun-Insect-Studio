# scripts 说明

八个模块 + 两个主程序 + 一个重拟合工具。所有模块的输入输出都是普通 Python 结构
（tuple / dict），不依赖本项目的目录，方便以后套界面。

| 文件 | 职责 | 依赖 |
|---|---|---|
| `nef_io.py` | 读 NEF 内嵌预览、读 EXIF 光圈/镜头、传感器尺寸 | rawpy, cv2, numpy |
| `mask_head.py` | BiRefNet 分割 + 开运算拆框 + 头部关键点 + 主体计数 | torch, transformers, cv2 |
| `crop_v3.py` | **裁切 105 项**，出四边界（含硬约束） | numpy |
| `exposure_model.py` | L\* 统计 + 双参数 EV | numpy, cv2 |
| `wb_sharpen.py` | 白平衡例外表（默认不启用）+ 按光圈锐化 | 标准库 |
| `xmp_write.py` | 生成 Lightroom XMP（只写必要字段） | 标准库 |
| `pipeline.py` | **一键**：串起来 + 写 params.csv / 检查图 | 以上全部 |
| `stages.py` | **分线**：mask / exposure / crop / write 四阶段 | 以上全部 |
| `refit_crop.py` | 在任意一张表上重拟合 105 项（换人/换范围） | numpy |

## 两条主程序的分工

* `pipeline.py` —— 适合"这批我全要"，一条命令到底。
* `stages.py` —— 适合"要反复调参数"：掩膜只跑一次，之后改 EV 系数或裁切公式都不用再碰 GPU。

## 最小调用（不跑 CLI）

```python
import nef_io, mask_head, crop_v3, exposure_model, wb_sharpen, xmp_write

nef  = r"/path/to/raws/Z04_7816.NEF"
prev = nef_io.preview_pil(nef)                 # PIL RGB，8256×5504
ow, oh = nef_io.sensor_size(nef)

res  = mask_head.analyze(prev, dev="cuda", size=768)
nsub = mask_head.count_subjects(res["mask"])
head = res["head"] if nsub <= 1 else None

me   = exposure_model.measure_pil(prev, res["mask"], res["full"])
ev   = exposure_model.predict(me["L_in"], me["L_box"])
cr   = crop_v3.compute_crop(res["core"], res["full"], head, multi=(nsub > 1))

# 白平衡默认不写；要写就解注释这两行
# wb = wb_sharpen.white_balance("2026.9.9 颐和园灯诱")
wb   = None
sh   = wb_sharpen.sharpness(nef_io.read_exif(nef)["fnumber"])

xml  = xmp_write.build("Z04_7816.NEF", cr["crop"], ev["ev"],
                      None if wb is None else wb["T"],
                      None if wb is None else wb["Tint"], sh)
xmp_write.assert_minimal(xml)                  # 不该出现的字段一个都不许有
```

## 自检

```bash
python crop_v3.py
# n=4184  IoU 中位 0.8756  均值 0.8487  ≥0.80 76.8%  画布受限 2.6%
```

对不上说明系数或特征顺序被改过了。

## 换系数

```bash
python refit_crop.py --csv ../assets/data/scope_crop_1022.csv
python pipeline.py --dir ... --coef ../assets/data/crop_coef_scope1022.json
```
