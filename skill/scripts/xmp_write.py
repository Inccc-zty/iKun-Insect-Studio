"""写 Lightroom 认的 XMP sidecar —— 只写这条流水线真正决定的东西。

设计原则（2026-11-16 修订）
    只写四个模块的结果 + 让 LR 接受这个 sidecar 所必需的标识字段。
    **其余一概不写。** 不写不是"没实现"，是"不覆盖你在 LR 里已有的调整"：
    LR 的「从文件读取元数据」只应用 XMP 里出现的字段，缺失的保持原值。

    上一版曾把 Contrast2012 / Highlights2012 / Shadows2012 / Whites2012 /
    Blacks2012 / Texture / Clarity2012 / Dehaze / Vibrance / Saturation 全部写 0，
    并且写了一条直线 ToneCurvePV2012 —— 读一次 XMP 就会把这些全部清掉。
    那是本 skill 唯一会实际损坏成片的错误，已删除。

格式依据（对 LR 自己写出的 XMP 实证）
    * 不用 <?xpacket> 包裹，直接 <x:xmpmeta>
    * crs:Version="16.0"、crs:ProcessVersion="15.4"
    * 裁切是左上原点绝对坐标，已归一化：Left/Right ÷ 图宽，Top/Bottom ÷ 图高
    * 字段顺序：CropTop/Left/Bottom/Right → CropAngle → HasCrop
    * 必须带 crs:RawFileName、crs:HasSettings="True"
"""
from __future__ import annotations

HEAD = '''<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Adobe XMP Core 7.0-c000 1.000000, 0000/00-00:00:00        ">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
{tool}   crs:Version="16.0"
   crs:ProcessVersion="15.4"
{wb}{exposure}{profile}{sharp}{cropbox}   crs:CropAngle="0"
{cropflag}   crs:HasSettings="True"
   crs:AlreadyApplied="False"
   crs:RawFileName="{raw}">
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
'''


def build(raw_name: str, crop=None, ev: float = None, T: int = None,
          tint: float = None, sharpness=None, profile: str = "Camera Standard",
          creator: str = None):
    """生成一份 sidecar。

    raw_name   原文件名（含扩展名），写进 crs:RawFileName
    crop       (l,t,r,b) 归一化坐标；None 表示这一趟不写裁切
    ev         Exposure2012（档）；None 表示不写
    T / tint   色温 / 色调；两者都给才写
    sharpness  锐化数量；None 表示不写（f/14 以上）
    profile    CameraProfile；传 None 则不写（保留你在 LR 里选的那个）
    creator    写 xmp:CreatorTool（软件的来源标记，用来区分「软件写的」和「手做的」）。
               传 None 就不写 —— CLI 用法保持原样，一个字节都不多。
    """
    tool = ""
    if creator:
        import html
        tool = ('   xmlns:xmp="http://ns.adobe.com/xap/1.0/"\n'
                f'   xmp:CreatorTool="{html.escape(str(creator)[:120], quote=True)}"\n')
    wb = ""
    if T is not None and tint is not None:
        # Tint = 0 写成 "0"（不是 "+0"），与 LR 自己写出来的一致
        ts = ("%+g" % tint) if float(tint) else "0"
        wb = (f'   crs:WhiteBalance="Custom"\n'
              f'   crs:Temperature="{int(T)}"\n'
              f'   crs:Tint="{ts}"\n')

    exposure = "" if ev is None else f'   crs:Exposure2012="{"%+.2f" % ev}"\n'
    prof = "" if not profile else f'   crs:CameraProfile="{profile}"\n'
    sharp = "" if sharpness is None else f'   crs:Sharpness="{int(sharpness)}"\n'

    if crop is None:
        cropbox, cropflag = "", '   crs:HasCrop="False"\n'
    else:
        l, t, r, b = crop
        cropbox = (f'   crs:CropTop="{round(t, 6)}"\n'
                   f'   crs:CropLeft="{round(l, 6)}"\n'
                   f'   crs:CropBottom="{round(b, 6)}"\n'
                   f'   crs:CropRight="{round(r, 6)}"\n')
        cropflag = '   crs:HasCrop="True"\n'

    return HEAD.format(wb=wb, exposure=exposure, profile=prof, sharp=sharp,
                       cropbox=cropbox, cropflag=cropflag, raw=raw_name,
                       tool=tool)


# 出现在产物里就说明又写多了，用来做回归检查
FORBIDDEN = ("Contrast2012", "Highlights2012", "Shadows2012", "Whites2012",
             "Blacks2012", "Texture", "Clarity2012", "Dehaze", "Vibrance",
             "Saturation", "ToneCurve")


def assert_minimal(xml: str):
    """自检：不该出现的字段一个都不能出现。"""
    hit = [k for k in FORBIDDEN if k in xml]
    if hit:
        raise AssertionError(f"XMP 出现不该写的字段：{hit}")
    return True
