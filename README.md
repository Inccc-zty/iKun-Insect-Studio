# iKun Insect Studio

**Automated post-processing for insect macro RAW.** One pass per photo: crop + exposure +
sharpening, written as a Lightroom `.xmp`. White balance is deliberately left alone.

> 中文版见 [README.zh-CN.md](README.zh-CN.md) · 中文完整说明在 [docs/](docs/)（写作中）

---

## What it does

- **Crop** — finds the insect with a full-frame mask, measures a body box and a whole box,
  predicts a square crop with a 105-term model (4,184 photos, hold-out IoU **0.865**).
- **Exposure** — two p95 brightness numbers (inside the mask / background inside the box)
  into one straight line; hold-out MAE **0.29 EV** (constant baseline: 0.41).
- **Sharpening** — by aperture, strictly increasing (20 → 65).

## What it deliberately does not do

- **No white balance.** Only a constant reproduces what the operator actually does
  (−1.000 regression slope on As Shot). The reasoning is a whole chapter: `docs/06-white-balance.md`.
- **No reframing.** It never rotates, never changes aspect ratio, never touches composition.
- **No matting.** The mask is a ruler, not a cut-out — the red overlay only exists so you can
  confirm it found the animal.

## Quick start (Windows)

1. Download the latest release, extract all parts.
2. Double-click `iKunInsectStudio.exe` (keep the whole folder together).
3. Drop a folder of RAWs, pick a mode, press **Start**.
4. The `.xmp` appears next to each photo → in Lightroom: *Read Metadata from File*.

The model preloads in the background for ~30 s on first launch; you can queue photos meanwhile.

## How it works, in one paragraph

Each photo is segmented **once** at 768² with BiRefNet. The mask gives two boxes (body via
morphological opening, whole via bounding box). A self-trained ResNet50 turns a 256² crop of the
body box into a 64×64 heat map, and soft-argmax turns it into a head point. Those numbers — 13 of
them — become 105 terms that predict the crop centre and width; two brightness percentiles become
the exposure; the aperture looks up the sharpening. Nothing else is estimated.

## Numbers

| Module | Data | Metric |
|---|---|---|
| Crop | 4,184 photos / 11 batches | hold-out IoU median **0.8650**, blind test 80 photos **0.9017** |
| Exposure | 4,396 photos / 11 batches | hold-out MAE **0.29 EV** (constant 0.41) |
| Head | 6 annotated RAWs + 500 reviewed | median error **0.12 · core width** |
| White balance | 5,065 JPG / 2,280 RAW | constant T=5333/+16, MAE **163 K** — best achievable |

## Repository layout

```
app/        engine (mask, crop, exposure, sharpening, XMP)
ui/         desktop UI (PySide6)
skill/      algorithm package: scripts + method notes + reference docs
docs/       bilingual manual + analysis reports
figures/    zh/ and en/ versions of every figure
```

Model weights (`head_kp_v2.pth`, 95 MB) and the Windows build live in **Releases**, not in git.

## Build from source

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
python run.py                 # dev run
python build.py               # PyInstaller one-folder build
```

## License

MIT — see [LICENSE](LICENSE).

© 2026 Zheng Tianyu · Laboratory of Systematics and Evolutionary Entomology,
China Agricultural University.
