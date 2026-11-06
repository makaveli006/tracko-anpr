# Plate detector comparison — results (2026-11-06)

## Summary

The five leading candidates are equivalent on this footage: each led to a confident reading on 87 to 92 of 476 vehicles. What limits the result is not which detector is used but how large the plate is in the picture.

**Recommended: `sentry-26s`** (`ayannotfound__Sentry/best.pt`). It is a YOLO26s at input size 640 built for vehicle crops, which is exactly what `ARCHITECTURE.md` specifies. It is level with the best on vehicles read, agreed with the other candidates most often, and disagreed with them least.

Nothing here is an accuracy figure. There is no hand-labelled ground truth; candidates are compared with each other and by what the plate reader could make of the boxes they drew.

## What was compared

- **Candidates:** the ten YOLO26 files in `pretrained-numberplate-weight/`, plus the four in `other-models/`.
- **Evaluation set:** 917 vehicle crops of 476 vehicles, from one 2-minute piece of each of the eight test videos. Up to 60 vehicles per clip, the ones that came closest to the camera, each at the two frames where it was largest.
- **Reader:** every plate box was cut from the vehicle crop and read with the Awiros model (attention decoder), 4,506 plate crops in all.

## Safety

- **Static scan, nothing loaded:** `scan_weights.py` and the independent `picklescan` tool both found no dangerous imports in any of the 12 `.pt` files. Each file imports exactly what the official Ultralytics `yolo26m.pt` imports; the only extras are two ordinary layer types (`C2f`, `DFL`) in the three older-YOLO models.
- **Loading:** every candidate was loaded only inside a Docker container with no network, no GPU, a read-only filesystem, no Linux capabilities and read-only weights. All 14 loaded and ran.

## Results

Plate boxes are counted at detector confidence 0.25 or more. "Vehicles read" means the reader produced a plate-shaped number with confidence 0.85 or more.

| Candidate | Model | Crops with a plate box | Vehicles with a box | **Vehicles read** | Two frames agree | Matches consensus (of 94) | Differs from consensus | Weak boxes | CPU ms per crop |
|---|---|---|---|---|---|---|---|---|---|
| `tejas-26s-onnx` | YOLO26s, 960, ONNX | 475 (52%) | 314 | **92** | 26 | 82 | 7 | 57% | 111 |
| `sentry-26s` | YOLO26s, 640 | 483 (53%) | 311 | **90** | 27 | 86 | 1 | 58% | 36 |
| `dushyant-26n-onnx` | YOLO26n, 416, ONNX | 422 (46%) | 282 | **89** | 22 | 84 | 2 | 51% | 13 |
| `harp-26n` | YOLO26n, 640 | 380 (41%) | 256 | **88** | 21 | 78 | 7 | 50% | 14 |
| `purvraj-26m` | YOLO26m, 640 | 483 (53%) | 309 | **87** | 19 | 78 | 6 | 57% | 100 |
| `dexit-26s` | YOLO26s, 640 | 331 (36%) | 216 | 84 | 25 | 78 | 4 | 44% | 36 |
| `nishant-26n` | YOLO26n, 640 | 317 (35%) | 215 | 81 | 22 | 76 | 4 | 44% | 14 |
| `vivekvar-11m` | YOLO11m, 640 | 322 (35%) | 218 | 79 | 19 | 73 | 5 | 44% | 98 |
| `tejaswi-26n` | YOLO26n, 640 | 310 (34%) | 214 | 78 | 18 | 74 | 4 | 48% | 14 |
| `hempixel-26s` | YOLO26s, 640 | 312 (34%) | 208 | 75 | 20 | 70 | 4 | 48% | 36 |
| `subash-v8n` | YOLOv8n, 640 | 282 (31%) | 200 | 74 | 16 | 70 | 1 | 46% | 15 |
| `dinesh-26s` | YOLO26s, 640 | 191 (21%) | 134 | 68 | 18 | 63 | 3 | 29% | 36 |
| `gursharn-v8n` | YOLOv8n, 640 | 171 (19%) | 129 | 18 | 5 | 15 | 2 | 74% | 15 |
| `rajcreo-26s-4class` | YOLO26s, 4 classes | 58 (6%) | 50 | 13 | 1 | 13 | 0 | 45% | 38 |

Column meanings:

- **Two frames agree:** vehicles whose two crops gave the identical number.
- **Consensus:** for 94 vehicles, at least three candidates agreed on a number. "Matches" is how many of those the candidate also read; "differs" is how many it read as something else.
- **Weak boxes:** share of the candidate's boxes whose content the reader called unreadable or read with confidence under 0.5.
- **CPU ms per crop:** measured inside the sandbox, on the CPU. It shows relative cost only; the application runs on the GPU.

## What the numbers say

- **The leaders overlap almost completely.** 72 vehicles were read by all of the top five; 104 by at least one of them; 108 by at least one of all 14. No candidate reads more than 4 vehicles that the other leaders miss.
- **Combining two detectors gains little.** `sentry-26s` with either `dushyant-26n-onnx` or `tejas-26s-onnx` reaches 96 vehicles, against 90 to 92 alone.
- **Finding the plate is not the bottleneck; reading it is.** At least one candidate drew a box on 443 of the 476 vehicles, but only 108 of those were ever read.
- **Plate width decides.** For `sentry-26s`:

| Plate box width | Boxes | Read |
|---|---|---|
| under 40 px | 68 | 0% |
| 40 to 59 px | 84 | 6% |
| 60 to 99 px | 176 | 30% |
| 100 to 149 px | 95 | 44% |
| 150 px and over | 60 | 45% |

- **Resolution matters.** The same footage gave 12 of 60 vehicles read at 2K (`kozhikode_part03`) and 6 of 60 at 1080p (`kozikode-4k_part03`).
- **Footage matters most.** Vehicles read by `sentry-26s`, per clip: `kochi_part02` 33 of 60, `mavoor_part02` 15, `kozhikode_part03` 12, `ooty_part03` 11 of 56, `kochi-city_part05` 7, `kozikode-4k_part03` 6, `trafiic_part01` 3, `truck_part02` 3.

## What the contact sheets show

- Many of the "nearest" vehicles show no plate at all: they are seen from the side, cut off by the frame edge, or passing too fast.
- Where a plate is visible and of reasonable size, it is found and read correctly (for example `KL11BW2228`, `KL48U6445`, `TN22DJ7205`).
- Boxes are sometimes drawn on things that are not plates (a wheel, a logo, a sign). The reader gives those low confidence (0.2 to 0.5), so the confidence threshold removes them.
- In `ooty` and `truck` the camera car's own dashboard and bonnet are tracked as a "vehicle". Later phases need to exclude it.

## Why `sentry-26s`

- It matches the architecture: YOLO26s, input 640, meant to run on vehicle crops.
- Vehicles read: 90, against 92 for the leader. With no ground truth, that gap is noise.
- Best agreement with the other candidates: 86 of 94 consensus numbers matched, and only 1 read differently.
- A third of the leader's cost (36 against 111 ms per crop on the CPU).

Its weaknesses, from `pretrained-numberplate-weight/README.md`: it was trained for only 10 epochs on mixed data in which Indian plates look like a minority, and its repository has no licence file. Like every Ultralytics-derived model it falls under AGPL-3.0.

`dushyant-26n-onnx` is the alternative: already in a format that cannot carry code, the fastest, and trained only on Indian plates, with 89 vehicles read. It is a YOLO26n with a fixed 416 input, not the YOLO26s the architecture names.

## Is fine-tuning (Phase 4b) needed?

Not on this evidence. A better detector cannot raise the result much: the leaders already put a box on nearly every vehicle that anyone could read, and what stops the rest is plate size and visibility. Fine-tuning would be worth revisiting only if a hand-labelled check later shows plates being missed.

## Files

- `storage/processed/phase4_eval/comparison.csv` — the table above.
- `storage/processed/phase4_eval/sheet_<candidate>.jpg` — contact sheets for the six leading candidates: the same 24 vehicle crops, with the box each drew and what was read.
- `storage/processed/phase4_eval/detections_<candidate>.json` — raw boxes from the sandbox.

These are git-ignored; regenerate them with the steps in [README.md](README.md).
