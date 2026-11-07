# Plate detector comparison

Tools for comparing the third-party plate-detector weights in `pretrained-numberplate-weight/` on this project's own footage, without ever loading one of them in the main environment.

The results of the run on 2026-11-06 are in [RESULTS.md](RESULTS.md).

## Why a sandbox

Eight of the candidates are `.pt` files, and a `.pt` file can run code when it is loaded. They come from unvetted single-author repositories. So:

1. They are **scanned without being loaded** (`scan_weights.py`).
2. They are **loaded only inside a Docker container** that has no network, no GPU, a read-only filesystem, no Linux capabilities, the weights mounted read-only, and one writable folder for results.
3. The container writes only plain JSON (box coordinates). Scoring happens outside, on those files.
4. The chosen model is re-saved in a format that cannot carry code before the application uses it.

## Steps

Run everything from the repository root, in WSL.

```bash
# 1. Scan the .pt files. Reads the files' instructions only; nothing is executed.
python3 -I tools/plate_detector_eval/scan_weights.py pretrained-numberplate-weight
uvx picklescan -p pretrained-numberplate-weight          # independent second scanner

# 2. Track one piece of each test video (skip clips that already have a detections CSV).
uv run tracko-anpr track videos/clips/<video>/<piece>.mp4 --no-video

# 3. Cut the vehicle crops every candidate will be run on.
uv run python tools/plate_detector_eval/build_eval_set.py

# 4. Build the sandbox image (this step needs the network; the run does not get it).
docker build -t tracko-plate-sandbox tools/plate_detector_eval/sandbox

# 5. Run all candidates inside the sandbox.
mkdir -p storage/processed/phase4_eval
docker run --rm --network none --read-only --tmpfs /tmp:rw,size=2g \
  --cap-drop ALL --security-opt no-new-privileges --pids-limit 512 --memory 10g \
  -v "$PWD/pretrained-numberplate-weight:/weights:ro" \
  -v "$PWD/storage/vehicle_crops/phase4_eval:/crops:ro" \
  -v "$PWD/tools/plate_detector_eval/sandbox:/work:ro" \
  -v "$PWD/storage/processed/phase4_eval:/out:rw" \
  tracko-plate-sandbox python /work/run_candidates.py

# 6. Cut the plates each candidate found, read them, and score.
uv run python tools/plate_detector_eval/score.py crops
(cd ocr && uv run anpr-ocr read ../storage/plate_crops/phase4_eval --json ../storage/plate_crops/phase4_eval/readings.json)
uv run python tools/plate_detector_eval/score.py report
```

## After a candidate is chosen

```bash
# 7. Re-save the chosen file as plain data, inside the sandbox.
mkdir -p storage/processed/phase4_export models/plate
docker run --rm --network none --read-only --tmpfs /tmp:rw,size=2g \
  --cap-drop ALL --security-opt no-new-privileges --pids-limit 512 --memory 10g \
  -v "$PWD/pretrained-numberplate-weight:/weights:ro" \
  -v "$PWD/tools/plate_detector_eval/sandbox:/work:ro" \
  -v "$PWD/storage/processed/phase4_export:/out:rw" \
  tracko-plate-sandbox python /work/export_safe.py ayannotfound__Sentry/best.pt sentry-26s
cp storage/processed/phase4_export/sentry-26s.* models/plate/

# 8. Confirm the plain files, loaded on the GPU in the main environment, find the same plates.
uv run python tools/plate_detector_eval/verify_safe_model.py sentry-26s
```

The export checks itself: it rebuilds the network from the plain files and fails unless the output matches the original.

## How candidates are judged

There is no hand-labelled ground truth, so nothing here is an accuracy figure. Candidates are compared on what matters downstream:

- **Vehicles read:** vehicles on which the candidate found a plate that the plate reader then turned into a plate-shaped number with confidence of at least 0.85. This is the main figure.
- **Two frames agree:** vehicles whose two crops gave the identical number.
- **Consensus:** for each vehicle, the number that at least three candidates agreed on; how many of those each candidate matched, and how many it read differently.
- **Weak boxes:** boxes whose content the reader called unreadable or read with confidence under 0.5, which suggests the box was not a plate.

Contact sheets (`storage/processed/phase4_eval/sheet_<candidate>.jpg`) show the same vehicle crops for each of the leading candidates, with the box it drew and the number read, to be judged by eye.
