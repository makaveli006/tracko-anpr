# Pretrained number plate detector weights

Openly available plate-detector weights found by web research on 2026-11-06, downloaded as-is from the links below. Each model sits in its own subfolder named `<owner>__<repo>`.

**Update, 2026-11-06:** all of these were compared on this project's own footage, inside a no-network sandbox. The one chosen is `ayannotfound__Sentry/best.pt` ("sentry-26s"). The application does not load that file; it loads a copy re-saved as plain data in `models/plate/`. Results and method: [../tools/plate_detector_eval/RESULTS.md](../tools/plate_detector_eval/RESULTS.md). The files in this folder are kept only as the source for that comparison.

The notes below were written at download time, when none of these had been run or evaluated here. The base model of each file was confirmed from the metadata embedded in the file; accuracy figures on the source pages are the authors' own claims, and "Indian" rests on each repo's description and dataset names.

## YOLO26 — trained on Indian plates

| Link | Model | File in this folder | Size | Notes |
|---|---|---|---|---|
| https://github.com/DushyantRajpurohit/indian-anpr | YOLO26n | `DushyantRajpurohit__indian-anpr/detector.onnx` | 9.3 MB | ONNX only, fixed 416×416 input, needs NMS. Best documented. |
| https://github.com/purvrajsinhjadeja31105-dotcom/smart-helmet-detection | YOLO26m | `purvrajsinhjadeja31105-dotcom__smart-helmet-detection/plate_crop_best.pt` | 42.0 MB | Trained on motorcycle crops only, not full frames or cars. |
| https://github.com/nishantjaat9712/Ai-Parking-Slot-Detection | YOLO26n | `nishantjaat9712__Ai-Parking-Slot-Detection/best.pt` | 5.1 MB | Roboflow "Indian License Plate" export; source workspace not documented. |
| https://github.com/dinesh2068/Mainproject-phase-1 | YOLO26s | `dinesh2068__Mainproject-phase-1/indian_plate_yolo26s.pt` | 19.3 MB | Trained on only 654 images; no held-out accuracy. |

## YOLO26 — trained on mixed data that includes Indian plates

| Link | Model | File in this folder | Size | Notes |
|---|---|---|---|---|
| https://github.com/Tejascodz/drishti | YOLO26s | `Tejascodz__drishti/plate_yolo26s_in_960.onnx` | 36.6 MB | ONNX only, 960×960 input, from the v0.1.0 release. Indian share of the data looks small. Best engineered repo. |
| https://github.com/ayannotfound/Sentry | YOLO26s | `ayannotfound__Sentry/best.pt` | 19.4 MB | Meant to run on vehicle crops. 10 epochs; Indian images appear to be a minority. |
| https://github.com/tejaswi67/Vehicle-License-Plate-Detection | YOLO26n | `tejaswi67__Vehicle-License-Plate-Detection/best_license_plate_model.pt` | 5.1 MB | Foggy worldwide plates plus a Roboflow Indian set; proportions not stated. |

## YOLO26 — described as Indian, training data not documented

| Link | Model | File in this folder | Size | Notes |
|---|---|---|---|---|
| https://github.com/hem-pixel/number_plate_detection | YOLO26s | `hem-pixel__number_plate_detection/best.pt` | 19.4 MB | README names no training dataset. |
| https://github.com/Harp404/DRISHTI | YOLO26n | `Harp404__DRISHTI/plate.pt` | 5.2 MB | Roboflow data "incl. Indian plates". |
| https://github.com/dexitshallbe/NumberPlateDetection | YOLO26s | `dexitshallbe__NumberPlateDetection/my_model.pt` | 19.3 MB | Meant to run on vehicle crops. |

## Other models (`other-models/`)

Not YOLO26 Indian plate detectors; kept because they were already downloaded during the research.

| Link | Model | File in this folder | Size | Notes |
|---|---|---|---|---|
| https://huggingface.co/vivekvar/helmet-v5 | YOLO11m | `other-models/vivekvar__helmet-v5/plate_yolo_ft.pt` | 38.6 MB | Indian CCTV plates (Andhra Pradesh); labels were auto-generated. |
| https://huggingface.co/subash1652007/indian-plate-ocr | YOLOv8n | `other-models/subash1652007__indian-plate-ocr/yolo_best.pt` | 5.9 MB | Indian plates. Repo is marked non-commercial research use only. |
| https://huggingface.co/gursharn01/indian-license-plate-detector | YOLOv8n | `other-models/gursharn01__indian-license-plate-detector/no_plate_model.pt` | 5.9 MB | "Indian" appears only in the repo name; empty model card. |
| https://huggingface.co/rajcreo/traffic-violation-models | YOLO26s | `other-models/rajcreo__traffic-violation-models/helmet_detector.pt` | 19.5 MB | Four classes (bike, helmet, no-helmet, number-plate); data origin not stated. |

## Before using any of these

- **Untrusted files.** `.pt` files are Python pickles and can run code when loaded. These come from unvetted single-author repos, so load them only in an isolated environment. The two `.onnx` files do not carry this risk.
- **Licence.** Most source repos have no licence file. Weights derived from Ultralytics YOLO fall under AGPL-3.0 by Ultralytics's terms whatever the repo says, and a company use may need their Enterprise licence. The same applies to weights we train ourselves.
- **Fit for this project.** `ARCHITECTURE.md` calls for YOLO26s running on original-resolution vehicle crops. None of these is a confirmed match for that on Indian road footage; test on our own clips before choosing, and expect that fine-tuning may still be needed.
- **Not in git.** The weight files are git-ignored; only this README is tracked. Re-download from the links above if the files are missing.
