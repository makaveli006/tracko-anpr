# Build plan — Vehicle ANPR POC (tracko-anpr)

Approved by the user on 2026-11-06. Phases are done one at a time; each starts only on the user's go-ahead.

## Progress

Tick a phase when it is complete and merged into `development`.

- [x] Phase 1 — Guard rails and setup completion (done 2026-11-06)
- [x] Phase 2 — Vehicle detection and tracking (done 2026-11-06)
- [x] Phase 3 — OCR smoke test (done 2026-11-06; gate A: go with Awiros, a fallback reader is deferred to later)
- [ ] Phase 4 — Plate detector comparison (comparison done 2026-11-06, see `tools/plate_detector_eval/RESULTS.md`; gate B awaits the user's choice, then the chosen model is re-saved in a safe format)
- [ ] Phase 5 — OCR service
- [ ] Phase 6 — Validation, full pipeline, final video
- [ ] Phase 7 — Acceptance and freeze (go/no-go C)
- [ ] Phase 8 — Database
- [ ] Phase 9 — Worker
- [ ] Phase 10 — Services and API
- [ ] Phase 11 — Dashboard shell and Upload & Process
- [ ] Phase 12 — Overview page
- [ ] Phase 13 — Remaining pages and registry
- [ ] Phase 14 — Demo data and readiness

## Context

The project is fully specified but not built. `ARCHITECTURE.md`, `DESIGN/DASHBOARD_DESIGN.md` and `CLAUDE.md` describe an offline pipeline (uploaded MP4 → vehicle detection → tracking → plate detection → OCR → multi-frame validation → annotated video) and a seven-page NiceGUI dashboard for a leadership demo. What exists today: documentation, an empty folder skeleton, two working Python environments (main: PyTorch 2.14.1+cu126 + Ultralytics 8.4.203; `ocr/`: PaddlePaddle 3.3.1), FFmpeg, ten untested third-party plate-detector weights, and 82 two-minute test clips.

The user's 28-step list is the backbone. I re-read every Markdown file against it and had an independent reviewer do the same; both passes found work the list does not mention, and three ordering problems. This plan folds all of it into **14 sequential phases**, each ending in something that can be checked before the next begins.

## How every phase runs

1. I create the work branch from `development` myself, per `.claude/rules/github.md`.
2. I implement the phase and run installs and system commands myself (`uv add`, `docker compose`, model downloads). **Exception: the PaddleOCR source download is handed to the user as a command.** Anything needing `sudo` is handed over too.
3. I verify: `uv run ruff check`, `uv run pytest`, and a real run on test clips. Failures are reported as failures.
4. I update the docs the phase touched (`ARCHITECTURE.md` setup log, `CLAUDE.md` status, `README.md`).
5. I run the git sequence myself (`git add .` → commit → `git checkout development` → merge → delete branch; no push), per the user's decision of 2026-11-06. Before committing I check the branch is the work branch and stop if it is not.
6. **I report "Phase N of 14 complete — M phases left", list them, and stop.** The next phase starts only on the user's go-ahead.

## What the 28 steps left out

**Would break things if skipped**
- **`lap` is missing.** Ultralytics tracking needs `lap>=0.5.12`; it is not in `uv.lock`, and Ultralytics would install it behind uv's back so the next `uv sync` removes it. (Phase 1)
- **`.gitignore` has holes, and `git add .` is mandatory.** Not ignored today: `runs/` (Ultralytics output), a stray root-level `*.pt`, `datasets/`, `.env`, evaluation output. (Phase 1)
- **Unsafe weight files.** `pretrained-numberplate-weight/README.md` says `.pt` files must only be loaded in isolation. Decided: scan, sandbox, re-save the winner in a safe format. (Phase 4)
- **WSL sees only 15 GB of the 32 GB RAM** and no `.wslconfig` exists. Two model processes, PostgreSQL and 2K frames share it. (Measured in Phase 2; raising the limit is a user-side change.)

**Specified but not in the list**
- Settings module, `.env` for the database password, and somewhere to store the Settings page's values (none of the six tables fits). (Phases 1, 8)
- The OCR process protocol: the docs say the worker "sends plate crops" but not how. (Phase 5)
- Which frames get plate detection and OCR, and which crops are kept; the full videos total about 347,000 frames. (Phases 4, 6)
- Indian plate format rules and the meaning of each validation status (`ARCHITECTURE.md` §10, `DESIGN` §12). (Phase 6)
- Timing per stage, for "processing duration" and "average inference latency" (`ARCHITECTURE.md` §14 page 6). (Phases 2, 6, 8)
- What the eight endpoints cannot supply: readiness for the "System Ready" panel, the original video, crop images, all-videos totals, cross-video history with export, registry, settings, downloads, per-track observations. (Phase 10)
- Upload validation (MP4 only), and registering a file already on disk: `kozhikode.mp4` is 5.5 GB, the wrong size for a browser upload. (Phases 9, 10)
- A custom video player: speed, position kept when switching original/annotated, seek from table rows. (Phase 11)
- Blue overridden in NiceGUI/Quasar, one token stylesheet, the font served locally (no cloud). (Phase 11)
- Empty and error states, crash clean-up of half-written results, and what a re-processed video shows. (Phases 9, 11–13)
- A start-up runbook for demo day, and a backup of the database and `storage/` once the demo videos are processed. (Phase 14)

**Stale or contradictory statements to fix**
- `initial-images/` is deleted but still named in `CLAUDE.md` (line 101) and `.gitignore` (line 1).
- `CLAUDE.md` still says "no dependencies configured", "not yet installed" and "nothing installed".
- `DESIGN` §8 says "Original 1080p video quality"; the rule is now any resolution.
- `ARCHITECTURE.md` §1 says mobile-recorded, 1–3 minutes, ~6 Mbps; the footage is dashcam-style, 5–41 minutes, 3–33 Mbps.
- The reference image shows "Bike" and bright-green fills; the written rules ("Motorcycle", dark green `#166522`) win.
- Docker 29.9.3 is installed but missing from the setup log.

**Not required by the current spec, so not built unless asked:** job cancellation, video deletion, retry, video thumbnails. (They were in the earlier design spec and were dropped from the new one.)

## Ordering changes

- **OCR is smoke-tested before plate detectors are compared** (Phase 3 before Phase 4). It is the least-proven component, and "can the OCR read this crop" should be how the plate detector is chosen.
- **The registry page is built before the demo videos are processed, but filled after**, since its records come from plates recognised in those videos.
- **The pipeline is frozen before the full videos are processed** (Phase 7); any later threshold change means reprocessing everything.

## Decisions built into this plan (approved)

- **Pipeline runs as sequential passes**, matching the seven-stage timeline in `DESIGN` §9: detection and tracking over the whole video → plate detection on the best frames of each track → OCR → validation → render. This also lets the best frames be chosen after a track is complete.
- **Unique Tracks** = every track the tracker produced. **Total Vehicles** = tracks seen long enough and large enough to count ("eligible"). **Recognition coverage** = confirmed plates ÷ Total Vehicles.
- **Validation statuses:** Confirmed (consensus reached and format valid), Unconfirmed (readings exist but no consensus or invalid format), Not Detected (no plate found), Failed (processing error).
- **Settings are editable** and stored in a seventh table, `app_settings`; each job keeps a snapshot of the settings it ran with.
- **A re-processed video shows its latest completed job.**
- **Plate model:** if the winner at Phase 4 is not a YOLO26s at 640, the docs are updated to name what was chosen.
- **Live demo processes only a 2-minute clip**; the long videos are processed beforehand.

## Phases

### Phase 1 — Guard rails and setup completion
Steps 2, 3, 4.
- Fix every stale statement listed above; close the `.gitignore` holes.
- `uv add --dev ruff pytest`, `uv add "lap>=0.5.12"`; Ruff and pytest config in `pyproject.toml`; `YOLO_AUTOINSTALL=False`.
- `src/tracko_anpr/config.py`, `.env.example`.
- Dry-run that FastAPI 0.162.0, NiceGUI, SQLAlchemy, Alembic and psycopg resolve alongside PyTorch (no install yet).
- **Hand to user:** `git clone --depth 1 --branch v3.7.0 https://github.com/PaddlePaddle/PaddleOCR.git ocr/vendor/PaddleOCR`. Record the commit and model hashes in the tracked `ocr/README.md`.
- Models into `models/`: Awiros model, dictionary and licence (from the scratchpad if still there, expected SHA-256 `f9f1264e…c68e47`, else re-downloaded); official `yolo26m.pt`.
- Log Docker in the setup log; add "measured accuracy with a hand-labelled set" to FUTURE IMPLEMENTATION.
- **Done when:** ruff and pytest run; GPU check unchanged; `ppocr` imports from the vendored source; a test Ultralytics run leaves `git status` clean.

### Phase 2 — Vehicle detection and tracking
Step 5.
- Restore the three untested drafts from `…\scratchpad\drafts-detection-tracking\` (`video.py`, `tracking.py`, `annotate.py`) or rewrite them. They read resolution and frame rate with ffprobe, scale TrackTrack's lost-track time to the frame rate, settle each track's class by vote, and encode H.264 through FFmpeg under a temporary name.
- `tracko-anpr track <video>`: annotated MP4, per-frame boxes, per-track summary, stage timings.
- Unit tests for the pure logic.
- **Done when:** clips at 1080p/29.97, 1080p/60, 2K/30 and 2K/59.94 produce output with the same size, frame rate and frame count as the input; the output seeks in the browser; speed, GPU memory and RAM are recorded; the user has watched them.

### Phase 3 — OCR smoke test (go/no-go A)
First half of step 9.
- `anpr-ocr read <folder>` in `ocr/`: builds the network from the vendored source as Awiros's `test.py` does, loads the safetensors, prints text and confidence.
- About 30 plate crops from our own clips, including two-line plates, taken with the two `.onnx` candidates (safe to load) in a throwaway environment.
- **Done when:** the readings are tabulated beside the crops for the user to judge. **Gate A:** carry on with Awiros, or discuss the stock PP-OCRv5 fallback.

### Phase 4 — Plate detector comparison (go/no-go B)
Steps 6, 7, and 8 if triggered.
- `pipeline/cropping.py`: vehicle crops from the original frame, with a test that crop size equals box size at 2K.
- Evaluation set of vehicle crops across all eight videos.
- Scan every `.pt` (picklescan, fickling via `uvx`); run all candidates in a Docker container with `--network none`, weights read-only, on CPU.
- Compare: share of vehicles with a plate found, share of those the OCR reads into a valid format, agreement between models; a contact sheet per model.
- **Gate B (user decides):** pick a winner, or run **Phase 4b**: obtain IURS-NPDS, convert and split by source photo, fine-tune YOLO26s, evaluate on the same set, time-boxed.
- The winner is re-saved in a safe format inside the sandbox; the app never loads a third-party `.pt`. Its source, hash and licence are recorded.
- **Done when:** the comparison table is committed and the chosen file, loaded on the GPU in the main environment, reproduces its numbers.

### Phase 5 — OCR service
Second half of step 9.
- `anpr-ocr serve`: a long-running process the worker starts, one JSON line per request over stdin/stdout carrying crop file paths, with a "ready" line as the health check. No extra packages.
- `pipeline/ocr_client.py`: start, stop, batch, timeout, restart.
- **Done when:** a round trip from the main environment works; killing the OCR process produces a clear failure, not a hang; GPU memory with both frameworks loaded is recorded.

### Phase 6 — Validation, full pipeline, final video
Steps 10, 11.
- `pipeline/validation.py`: normalisation, standard and BH-series formats, look-alike correction only where it makes a reading valid, confidence-weighted consensus, the four statuses.
- `pipeline/runner.py`: the sequential passes, a progress callback per stage, per-stage timing, best vehicle and plate crop kept per track, second-pass renderer with amber plate boxes and text.
- `tracko-anpr process <video>`.
- **Done when:** unit tests pass, including the worked example in `ARCHITECTURE.md` §10, and one clip runs end to end.

### Phase 7 — Acceptance and freeze (go/no-go C)
Step 12.
- Run every combination we have: 1080p at 29.97, 30, 50, 60 and 2K at 30, 59.94; the same footage at 2K and 1080p side by side.
- Results table: coverage, speed, memory. Freeze thresholds and settings.
- **Gate C (user decides):** which full-length videos are feasible for the demo, given measured speed.

### Phase 8 — Database
Steps 13, 14, 15.
- `docker-compose.yml`: `postgres:18`, named volume at `/var/lib/postgresql`, localhost-only port, restart policy, credentials from `.env`.
- `uv add "fastapi==0.162.0" nicegui sqlalchemy alembic "psycopg[binary]"`; re-run the GPU check afterwards.
- SQLAlchemy models (six tables plus `app_settings`), Alembic and the first migration, the metric definitions as queries, and the `process` command writing its results to the database.
- **Done when:** migrate up, down, up on an empty database; row counts match the command-line output; data survives a container restart.

### Phase 9 — Worker
Step 16.
- Claim the oldest queued job, write stage and progress, record errors, heartbeat, reset stuck jobs on start-up and clear their half-written rows and files, own the OCR process.
- `tracko-anpr worker`, `tracko-anpr enqueue <video>`, and `tracko-anpr ingest <path>` for large files already on disk.
- **Done when:** a worker killed mid-job restarts and finishes without duplicates; a corrupt file ends as Failed with a message.

### Phase 10 — Services and API
Step 17.
- Service layer shared by the API and the dashboard; the eight endpoints; the additions listed above, written into `ARCHITECTURE.md`; upload validation; `tracko-anpr web` with NiceGUI mounted on FastAPI as one server process.
- **Done when:** route tests pass; a seek request on a video returns partial content; a non-MP4 upload is rejected with a clear message.

### Phase 11 — Dashboard shell and Upload & Process
Step 18 and the live-demo part of step 20.
- Design tokens from `DESIGN` §18, blue overridden, Inter served locally; header; sidebar with the real readiness panel; the video player component.
- Upload & Process page with real progress and the failure path.
- **Done when:** a screenshot matches the reference layout with no blue; stopping the worker or database turns the status panel to a warning; a 2-minute clip uploaded in the browser runs to completion.

### Phase 12 — Overview page
Step 19.
- Video selector and scope switch, five cards, player with original/annotated switch, seven-stage timeline, category donut, coverage bar, recent detections with row click → seek and details, "new vehicles per 10 seconds" chart, empty states.
- **Done when:** card values equal direct database queries; the chart sums to Total Vehicles; an empty database still renders.

### Phase 13 — Remaining pages and registry
Rest of step 20, and step 21's generator.
- Video Analysis, Detection History (search, filter, sort, export), Analytics, Settings, Demo Registry with the "Demonstration Data Only" banner; `tracko-anpr seed-registry`.
- **Done when:** the whole user journey is clicked through in the browser; a history row seeks the video; the export opens; matches and non-matches both appear.

### Phase 14 — Demo data and readiness
Steps 22, 23.
- Process the videos chosen at gate C; seed the registry; back up the database and `storage/` and test the restore.
- Runbook in `README.md`: database, migrations, worker, web app, health check, how the browser reaches WSL.
- Final sync of all three docs; final ruff and pytest pass; rehearsal.
- **Done when:** a cold start after `wsl --shutdown` reaches a green status panel following only the README, and the rehearsal works with the network unplugged.

## Left to the user (not phases)

- **Step 25, the `Co-Authored-By` line: decide before the next push.** It sits on the very first commit, and `development` is built on top of it, so removing it now means rewriting both branches and force-pushing both. I can hand over the exact commands, or it can be dropped.
- Step 24 end-of-day push; step 26 pull request to `main`; step 27 optional branch protection; step 28 the Ultralytics AGPL licence before production.
- If Phase 2 shows memory pressure: raise WSL's RAM limit with a `.wslconfig` file.

## Top risks

1. **Plate detection or OCR is not good enough on small, blurred dashcam plates.** Nothing has been run yet. Gates A and B, with time-boxed fine-tuning.
2. **Full-length videos take too long.** About 347,000 frames; speed is unmeasured until Phase 2. Gate C.
3. **A live upload fails in front of the audience.** Live-process only a 2-minute clip; everything else pre-processed and backed up.
4. **Memory:** WSL has 15 GB. Measured in Phase 2.
5. **Counts look wrong** from track switches and unrecognised vehicle types such as auto-rickshaws. Metric definitions above, plus a note for the walkthrough.

No demo date appears in any document, so the phases are not fitted to a calendar.

## Critical files

- Specs: `ARCHITECTURE.md`, `DESIGN/DASHBOARD_DESIGN.md`, `CLAUDE.md`, `.claude/rules/github.md`
- To change in Phase 1: `.gitignore`, `pyproject.toml`, `CLAUDE.md`, `ocr/README.md`
- To create: `src/tracko_anpr/{config,cli}.py`, `pipeline/{video,tracking,annotate,cropping,plates,ocr_client,validation,runner}.py`, `db/`, `worker/`, `api/`, `dashboard/`; `ocr/src/anpr_ocr/`; `docker-compose.yml`, `alembic.ini`, `migrations/`, `.env.example`
- To reuse: the three drafts in the session scratchpad; Awiros's `test.py` as the reference for building and loading the OCR model; Ultralytics's bundled `cfg/trackers/tracktrack.yaml`
