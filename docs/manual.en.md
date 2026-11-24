# iKun Insect Studio · Manual

> For people already shooting insects and editing in Lightroom, Camera Raw or an equivalent.
> 中文版：[manual.md](manual.md)

---

## 0 What it is

**A tool that does the boring, repetitive part for you: find the insect, place the crop, set the exposure.**

### Who it is for

Every field trip, every individual needs one record frame. Out of a hundred shots a day, a handful
are portfolio-grade and the rest are **records**. The records still need cropping — in macro work
the insect is always small in the frame: hand-holding shakes, the magnification is rarely enough,
and the insect will not let you get closer. Uncroped, the photo is "a bug somewhere in the middle".

So what actually eats your evening is not the five good frames — it is the other ninety-five:
the same crop, the same exposure nudge, over and over.

**The app does exactly those two things:**

- **Crop** — usually usable as-is, sometimes off
- **Exposure** — an estimate, often off

Either can be wrong; nothing here is 100%. The value is not accuracy, it is **turning a hundred
repetitive edits into a few minutes** — you glance at the misses and fix them, which is far faster
than cropping from scratch.

The result is a sidecar `.xmp` that post-processing software reads directly.

> The app was built against **Lightroom** and **Adobe Camera Raw (ACR)** as references.
> `.xmp` is Adobe's open sidecar standard: Lightroom, Camera Raw, Bridge and Photoshop all read it.
> Whenever this manual says "post-processing software", it means that family.

![batch](media/panel80.jpg)

Three columns per row: original / boxes and head point / result.

---

## 1 The standard workflow

![workflow](media/flow_workflow.en.png)

| Step | Where | What | Output |
|---|---|---|---|
| ① Cull | any culling tool | go through by batch; delete soft, shaken, duplicated, blocked | a clean candidate set |
| ② Pick the keepers | Lightroom | only 5–10%, finished by hand | a few publishable frames |
| ③ Batch run · **the app** | iKun Insect Studio | drop the rest in, policy = protect what I edited | one `.xmp` per photo |
| ④ Global fine-tuning | post-processing app | white balance, overall exposure, colour, local adjustments — in bulk | one consistent look |
| ⑤ Export | post-processing app | preset → export (size, output sharpening, watermark) | deliverables |

**② and ③ cannot swap**: finish the hand edits first, then let the batch skip them.

> **What to cull with**: Lightroom works, but a dedicated culler is faster — Nikon NX Studio, for
> instance, is much quicker for browsing and rating. Other makers have their own; use whatever
> feels right.

### About step ④

**The real fine-tuning happens in post-processing software** (Lightroom / Camera Raw) — white balance, overall exposure, tone curve, local
masks. That is where a batch becomes one look, and it is a judgement call, not a measurement.
The app only puts the crop and the exposure on the sliders.

> White balance is deliberately not written: whether a scene should be cooler or warmer is an
> expressive choice, not something you measure off the frame.

---

## 2 After installing

1. Unzip to a **fixed folder** (not the Desktop, and do not rename it later), e.g. `D:/iKunInsectStudio`
2. Double-click `iKunInsectStudio.exe`
3. First launch loads the models in 10–20 s; **the window appears first and the models load in the
   background**, so you can queue photos immediately
4. To reset: close the app, double-click `重置到初始状态.bat` in the same folder

> An NVIDIA GPU (4 GB+) is recommended. CPU works too, at 5–10 s per photo.

---

## 3 How to run your first batch

1. Drop **a folder**, or **a batch of photos**, onto the window
2. Mode: `Crop + Exposure`
3. 「Photos with XMP」 → **protect what I edited**
4. Press **Start**
5. **Import the batch into your post-processing software** — the `.xmp` is read on import and the crop and exposure land on the sliders

> Only if these photos are **already in the software** do you need one extra click: select all → right-click →
> **Read Metadata from File**.

---

## 4 What it changes, and what it does not

| | |
|---|---|
| **Changes** | crop box (position + size), exposure EV, sharpening amount |
| **Leaves alone** | white balance, colour, contrast, local adjustments |
| **Never touches** | the RAW. Only a sidecar `.xmp` |

Where the three numbers come from:

- **Crop**: BiRefNet mask → body box + whole box + head point, 13 numbers expanded to 105 terms
- **Exposure**: p95 luma inside the mask + p95 luma of the box background, regressed to your EV
- **Sharpening**: aperture only; the smaller the aperture, the more sharpening

---

## 5 How it plugs into your post-processing software

![with LR](media/flow_lr.en.png)

Two cases, one action differs:

| Your situation | What to do |
|---|---|
| **New import** | just import — **the `.xmp` is read on import**, nothing else to click |
| The batch is **already in** the software | after the run: select all → right-click → **Read Metadata from File** |

**The RAW is never modified**, so either order is safe.

---

## 6 Two optional extras (not part of the mainline)

Neither is required; skipping both still gives you a complete batch.

### 6.1 Nudging the head point inside the app

When: one frame got the head wrong and the crop followed it.

How: open the photo → drag the head point → **Done**. The correction is remembered and applied to
geometrically similar frames (nearest-neighbour from 3 records, a 7-parameter linear residual from 25).

- It only moves the **crop box**; nothing is written into Lightroom
- **Every nudge makes the model fit your judgement better** — the corrections accumulate as
  training samples and can be exported at any time (see 6.2)
- Not a per-batch step: fix it when you see it

### 6.2 Training your own crop model

When: your subjects look very different from the built-in set (all super-macro, all groups).

How: Train tab → add folders → Start. It uses **your own edited photos with XMP sidecars**,
reads how you actually cropped, and fits a new set of coefficients. The result sits alongside the
built-in model and you can switch back at any time.

- Needs **at least a few dozen** edited photos; more is better
- The output is a coefficient file only, no images, easy to copy elsewhere
- Again: nothing changes inside Lightroom

> Both are in the app, but **neither is a step in the workflow**. In normal use you finish ③ and go
> straight to Lightroom.

---

## 7 The interface

(to be filled with the Process / Train / About screenshots)

---

## 8 FAQ

**Q: Nothing changed in my software.**
A: Check whether the run happened **before** import. A run before import is picked up automatically;
a run after import needs one click on Read Metadata from File.

**Q: Will it overwrite my edits?**
A: With 「protect what I edited」 it only fills the ones you have not touched. 「Overwrite」 changes all.

**Q: Why is white balance always untouched?**
A: The app does not guess colour temperature. Your setting is a fixed habit, not a function of the
illuminant, so guessing would be wrong.

**Q: How long does a batch take?**
A: 1–3 s per photo on a GPU; faster with live preview off.

---

## 9 Known limits

1. **No rotated crops.** About 8% of your finished crops are rotated; the app only produces
   axis-aligned boxes, so those will not match. May be added later.
2. **No white balance.** Not for lack of trying: nothing we tried predicts your setting well —
   inside/outside the mask, specular highlights, multi-feature models — a constant beats them all.
3. **Exposure is an estimate.** Large moves (±1.5 EV and beyond) drift; use it as a starting point.
4. **Small insects drift.** When the insect is under 8% of the frame width the mask blurs and the
   box can be off — check those frames.

---

## 10 Why it is 4.4 GB

Unzip it and you get a 4.4 GB folder with **not a single photo** in it. The breakdown:

| Part | Size | What it is |
|---|---|---|
| PyTorch + CUDA runtime | **~3.9 GB** | the libraries that let the models run on the GPU |
| Model weights | ~420 MB | segmentation model + head keypoint model |
| Qt, OpenCV, image decoding | ~200 MB | the window, RAW reading, preview rendering |
| Scripts and config | a few MB | the actual logic |

### What those 3.9 GB are

| File | Size | Job | Removable? |
|---|---|---|---|
| `torch_cuda.dll` | 1.33 GB | GPU kernels | no, core |
| `cudnn_engines_precompiled` | 563 MB | convolution kernels | no — removing it costs 10× speed or breaks outright |
| `cublasLt` | 519 MB | matrix multiply | no |
| `cusolver / cufft / cusparse` | 817 MB | solvers, FFT, sparse | **no** — `torch_cuda.dll` imports them statically; remove them and `import torch` fails (tested) |
| `torch_cpu.dll` | 241 MB | CPU fallback kernels | no |

### Why CUDA at all

Without it everything runs on CPU: **0.3 s → 5–10 s per photo**, i.e. an extra hour on a 500-frame batch.
Not a good trade, so the CUDA build is the default.

### Could it be smaller

Yes, by changing the inference engine:

| Option | Size | Cost |
|---|---|---|
| Current (PyTorch + CUDA) | 4.4 GB | — |
| ONNX Runtime (CUDA) | ~1.8 GB | export both models, verify accuracy frame by frame |
| ONNX Runtime (CPU) | ~0.8 GB | tiny, but 5 s per photo and up |

Not done yet: **these coefficients were calibrated on PyTorch**, so switching engines means re-validating
accuracy, not just swapping a library.
