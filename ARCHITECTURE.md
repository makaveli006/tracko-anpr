```text
PROJECT: Indian Vehicle Detection, Tracking & Number Plate Recognition
PURPOSE: C-Suite Leadership Demonstration
TYPE: Recorded Video Processing POC
LANGUAGE: Python
HARDWARE: NVIDIA GeForce RTX 4070 Ti SUPER GPU with 16 GB VRAM
CPU: AMD Ryzen 9 7900X (12 cores / 24 threads)
RAM: 32 GB (2 × 16 GB)
HOST OS: Windows Server 2022 Standard (64-bit)
RUNTIME: WSL 2 — Ubuntu 24.04 (the entire application runs inside WSL)
DATABASE: PostgreSQL 18 (stable) in Docker inside WSL


══════════════════════════════════════════════════════════════
 1. VIDEO INPUT
══════════════════════════════════════════════════════════════

 Source          : Recorded Indian road traffic videos. The
                   test footage is dashcam-style driving
                   video.
 Camera          : Stationary roadside OR moving vehicle
 Resolution      : Any, read from each video
                   (1920 × 1080 suggested)
 Frame Rate      : Any, read from each video
                   (30 FPS suggested)
 Video Codec     : H.264
 Container       : MP4
 Bitrate         : Any (~6 Mbps or more suggested). The test
                   footage runs from 3 to 33 Mbps.
 Duration        : Any. Development uses 2-minute pieces; the
                   full test videos run 5 to 41 minutes.

 No live camera or RTSP streaming required.

 Accepted input  : MP4 only. The pipeline does not take
                   other formats.

                   Any resolution and frame rate are accepted
                   and are read from the video itself.
                   1080p at 30 FPS is the suggestion. A
                   60 FPS video takes about twice as long to
                   process, and higher resolution is slower
                   too but gives sharper plate crops.

                   Source clips in another container (for
                   example WebM) are converted to H.264 MP4
                   with FFmpeg beforehand, keeping their own
                   resolution and frame rate:

                     ffmpeg -i input.webm -c:v libx264 \
                       -preset medium -crf 20 \
                       -pix_fmt yuv420p -c:a aac -b:a 128k \
                       -movflags +faststart output.mp4

 Test clips      : Pipeline development uses 2-minute pieces
                   of each video. Every video has its own
                   folder, named after it:

                     videos/clips/<video>/<video>_partNN.mp4

                   The pieces are cut without re-encoding,
                   so they keep the source quality. The full
                   videos are kept for the final demo.

                     ffmpeg -i <video>.mp4 -map 0:v:0 \
                       -map 0:a:0? -c copy -f segment \
                       -segment_time 120 -reset_timestamps 1 \
                       -segment_start_number 1 \
                       -segment_format_options \
                       movflags=+faststart \
                       clips/<video>/<video>_part%02d.mp4


                         │
                         ▼

══════════════════════════════════════════════════════════════
 2. NICEGUI — WEB APPLICATION
══════════════════════════════════════════════════════════════

 Functions:
   • Upload one or multiple MP4 videos
   • Preview uploaded video and metadata
   • Start video processing
   • Display processing progress
   • View processed video and detection results
   • Compare original vs annotated video
   • Browse detection history and analytics

                         │
                         ▼

══════════════════════════════════════════════════════════════
 3. FASTAPI — BACKEND
══════════════════════════════════════════════════════════════

 Version         : FastAPI 0.162.0

 Responsibilities:
   • Accept and validate video uploads
   • Save uploaded video files
   • Create and manage processing jobs
   • Start background processing via a separate worker
   • Report job progress and errors
   • Retrieve results from PostgreSQL
   • Serve processed videos and cropped images
   • Provide REST API endpoints

 Endpoints:
   POST /api/videos
   GET  /api/videos
   POST /api/videos/{id}/process
   POST /api/videos/{id}/plate-check
   GET  /api/jobs/{id}
   GET  /api/videos/{id}/results
   GET  /api/videos/{id}/detections
   GET  /api/videos/{id}/analytics
   GET  /api/videos/{id}/annotated

 HOW THE API IS BUILT (api/, services/, Phase 10)

 One process: `tracko-anpr web` runs FastAPI with the NiceGUI
 dashboard mounted on it (ui.run_with). Routes are thin;
 every one calls a function in tracko_anpr/services/, and
 the dashboard pages call the same functions, so the two
 could be split into separate services later without logic
 moving. Services return dataclasses, which FastAPI
 serialises as they are. Each request is one database
 transaction (api/app.py, get_session).

 The eight endpoints above, and what the dashboard needs
 beyond them:

   GET  /api/system/status      the sidebar's "System Ready"
                                panel: database (reachable and
                                migrated), worker (reported in
                                the last 15 s, idle or on a
                                job), GPU (nvidia-smi), model
                                files, reader installed,
                                FFmpeg. ready is true only
                                when all but the GPU line are
                                ok; never a false green.
   GET  /api/summary?video_id=  the five Overview cards, for
                                one video or all
   POST /api/videos/ingest      register a file already on
                                disk, without copying (too
                                large to upload)
   GET  /api/videos/{id}/original      the uploaded video
   GET  /api/videos/{id}/download/{k}  annotated | results |
                                       detections | plates,
                                       as attachments
   GET  /api/analytics          Analytics across all videos
   GET  /api/detections         Detection History: every
                                video, filtered by video,
                                status, type, travel direction
                                (approach = towards | away |
                                none), number search; sorted;
                                paged
   GET  /api/detections/export.csv     the same rows as CSV
   GET  /api/detections/{track_pk}     one detection in full,
                                with every plate observation
                                (the multi-frame evidence), its
                                event lifecycle (new / read /
                                confirmed / corrected / lost)
                                and its fictional registry match
   GET  /api/images/{path}      vehicle and plate crops, only
                                from storage/vehicle_crops and
                                storage/plate_crops
   GET  /api/registry[/{number}]  the FICTIONAL registry, with
                                its disclaimer in every answer;
                                a record one character away is
                                a "possible" match, never a match
   GET  /api/registry/lists     the named lists and their counts
   POST /api/registry/lists     add a number to a list (a
                                fictional record if none exists)
   PUT  /api/registry/{id}      description and list of a record
   DELETE /api/registry/{id}/list   take a record out of its list
   POST /api/registry/import    CSV import; the template is at
                                GET /api/registry/import-template.csv
   GET/PUT /api/settings        the Settings page's values
   GET  /api/jobs               the queue

 Rules the routes enforce:
   • Uploads: .mp4 only, and the file must be readable by
     ffprobe after it is written; otherwise it is deleted and
     the answer is 400 with a sentence saying why. A second
     upload of the same name becomes name-2. Uploads over 8 GB
     are refused (use ingest).
   • Videos stream with HTTP range support (206 Partial
     Content), which is what lets the player seek.
   • Files are served only from under storage/ (or a
     registered video's own file); a path that resolves
     elsewhere is 404.
   • Processing is never run in the web process: POST
     /api/videos/{id}/process inserts a queued job and
     returns 202; a pending job is reused, not duplicated.
   • The worker writes an idle heartbeat (app_settings key
     worker_heartbeat) on every poll, so the status panel can
     see a worker that has nothing to do.

 Verified 2026-11-07: 21 route tests on SQLite; and against
 PostgreSQL with a worker running, /api/system/status said
 ready with all six checks green, a Range request on a 106 MB
 annotated video answered 206 with the right Content-Range,
 and a .mov upload was refused with its message.

 MANUAL NUMBER PLATE CORRECTION (services/corrections.py,
 added 2026-11-07)

 An operator can correct a recognised number and/or the
 vehicle type from the details dialog (any detections table:
 Overview, Video Analysis, Detection History). The system's
 own result is never changed: the correction is stored
 beside it in plate_corrections, with the system's number,
 status and type at the time, an optional name (remembered in
 the browser) and note. The newest correction per track is
 the current one; earlier ones stay as history and "Undo"
 removes the newest.

 Rules (the service enforces them, the API answers 400 with
 the reason): the number is normalised and must pass the
 pipeline's own Indian-format check (is_valid_plate); the type
 must be one of the four classes; a correction that equals the
 system's result is refused.

 Where it shows: the corrected value in the table cell with an
 amber pencil and a dashed underline, the system's value in
 the tooltip; both values in the dialog; an "Operator
 Corrections" card on Analytics (detections corrected,
 numbers, confirmed numbers changed and their share, types).
 Nothing else moves: Total Vehicles, Recognized Plates,
 coverage, the registry Match / No Match and every chart keep
 counting the pipeline's result, by the user's decision, so
 the demo figures stay the system's and human and machine
 answers can be compared.

 API: PUT /api/detections/{track_pk}/correction
 {number?, vehicle_type?, corrected_by?, note?};
 DELETE ... /correction (undo); GET /api/corrections?video_id=
 (summary and current corrections). GET /api/detections/
 {track_pk} carries correction and corrections. The Detection
 History export gains corrected_number, corrected_type,
 corrected_by and corrected_at: a labels/<video>_truth.csv for
 "HOW TO MEASURE REAL ACCURACY" can start from it, with the
 corrected columns as true_number and true_type.

 FEATURES INSPIRED FROM AXIS COMMUNICATIONS

 On 2026-11-07 two Axis Communications documents were read
 against this project: the AXIS License Plate Verifier
 technical documentation (February 2026; an on-camera LPR
 application with lists, events and integrations) and the
 whitepaper "License plate capture — key factors for
 successful license plate recognition" (December 2024; the
 physics of getting readable plates). Everything that
 presupposes a live camera (barriers, I/O, PTZ, IR and
 shutter settings) is out of scope by the spec. What carries
 over, in the order worth doing:

 1. RECORDING GUIDE — done 2026-11-07.
    RECORDING_GUIDE.md at the project root, for anyone
    filming with a phone or a fixed camera: plate at least
    130 px wide when closest (two-row plates 70 px per row),
    camera in line with the traffic within 30°, level within
    5°, height about half the reading distance, above
    headlights, not into the sun; landscape 1080p at 30 fps
    (4K adds nothing and costs two and a half times the
    processing),
    focus and exposure locked, fast shutter, phone still,
    1 to 3 minute clips; night only with light at the camera
    (plates are retro-reflective); a plate-width self-check
    before uploading (130 px is about 7% of a 1080p frame);
    and our own measured read rates by plate width on the
    three demo videos, which agree with Axis's numbers
    (1080p: 60 to 100 px read 66% of the time; 4K: under
    150 px rarely; zoomed-in, filmed closest, has the best
    coverage at the lowest resolution). The Upload page shows
    the guide's first three sections under "Recording tips
    for better results", rendered from the same file. Zero
    pipeline change; it is the largest lever on coverage.

 2. PLATE-SIZE CHECK ON UPLOAD — done 2026-11-07.
    Before the full run, which takes minutes, the worker
    samples 24 frames spread evenly over the video (the first
    and last 5% left out), finds the vehicles in them with
    YOLO26m (detection only, no tracking: VehicleTracker.
    detect) and the plates on those vehicles with sentry-26s,
    exactly as stage 4 would, and reports the plate widths
    (pipeline/plate_check.py): the median, the 90th
    percentile as "the largest plates seen", the shares under
    60 px and at or over 130 px, and a verdict with one
    sentence for the user. The verdict follows the largest
    plates, not the median, because a plate is only big when
    its vehicle is close and that is where the pipeline reads
    it; the thresholds are the recording guide's (130 px →
    good, 60 to 130 → borderline, under 60 → low; no plates
    found on the vehicles seen, or no vehicles, are their own
    verdicts). It measures size only: blur, angle and light
    are not checked, and nothing it finds is stored as a
    result. Mirrors Axis's pixel counter.
    Where it runs: never in the web process. videos.plate_
    check (migration e5a1c9d2b7f3) holds the state (pending |
    running | done | failed, times, worker, error) and the
    result; every upload and ingest requests a check; the
    worker serves a pending check before the next queued job
    (half a minute against minutes, and someone is waiting on
    the Upload page), keeps the two detectors loaded between
    checks, and on start queues again any check a dead worker
    left running. A check is not a processing_jobs row, so
    the job recovery that deletes result folders never
    touches it. POST /api/videos/{id}/plate-check asks for
    one (202; the state travels in VideoSummary.plate_check);
    tracko-anpr check <video> [--frames 24] runs it from the
    command line. The Upload page's File Information card
    shows a spinner while it runs, then the sentence in green
    / amber / red with "Check again"; the videos list has a
    "Plate size" column; videos registered before the check
    existed read "Not checked · Check now".
    Measured on zoomed-in: 60 vehicles and 41 plates in 24
    frames in 28 s on the command line (42 s from the click
    on the Upload page, the worker's model load included),
    median 44 px, largest 107 px, verdict "borderline: some
    will be read", which matches its 27% coverage.

 3. DIRECTION PER TRACK AND NEW / UPDATE / LOST EVENTS —
    done 2026-11-07.
    Direction. pipeline/direction.py reads each track's
    travel direction from the boxes the tracker already
    produced, with no model: the median box height of the
    first fifth of the track against the last fifth (ratio
    at least 1.25 → "towards" the camera, at most 1/1.25 →
    "away"), and the median box centre's shift as a share of
    the frame width (at least 10% → "right" or "left"). Both
    parts may be set ("Towards camera, left"); neither →
    "Undetermined" (a vehicle that hardly moved, or a track
    too short to compare). Medians, because the first and
    last boxes of a track are the noisiest. Ratios and
    fractions only, so nothing depends on resolution or
    frame rate. The two thresholds (DirectionRules) are NOT
    part of the Phase 7 frozen set: changing them changes
    labels, never a count or a plate; they are recorded in
    results.json's settings. The user chose the wording
    "Towards / Away from camera" over Axis's Entry / Exit
    because the demo cameras are roadside phones, not gate
    cameras. Stored on vehicle_tracks as approach and
    sideways (migration d41ec7a0b3f2; the column is called
    sideways because "lateral" is a reserved word in
    PostgreSQL). Shown: a Direction column in every
    detections table, a Direction filter on Detection
    History (URL parameter dir, API parameter approach =
    towards | away | none), a "direction" column in the CSV
    export, and Detections Over Time on the Overview as
    stacked bars (towards, away, undetermined per 10-second
    bucket; metrics.detections_over_time_by_direction, which
    adds up bucket for bucket to detections_over_time).
    Limits: direction is relative to the picture, so a
    vehicle crossing the frame is only "left" or "right"; a
    stopped vehicle is "Undetermined"; the two demo videos
    were processed again to carry it (results otherwise
    identical), and the upload 214173 keeps NULLs, shown as
    "Undetermined". Measured on the demo set: zoomed-in has
    22 of 59 counted vehicles undetermined, clear 86 of 185.
    Those 86 are not a threshold problem: their median
    height ratio is 0.99 with no sideways shift, their
    median track lasts 1.4 s, 72 are motorcycles and 67 are
    unconfirmed, i.e. mostly short fragments of tracks and
    two-wheelers waiting at the roadside; lowering the
    ratio to 1.15 would relabel only 12 of them. Expect the
    undetermined share to fall with longer tracks, not with
    looser thresholds.
    Events. The details dialog has an "Events" list, the
    Verifier's New / Update / Lost lifecycle reconstructed
    at read time by services/results.py:lifecycle from rows
    that already exist (nothing is logged while a video is
    processed): "new" at the first frame; "read" at the first
    reading above the validator's 0.6 confidence floor and
    again at every later reading with a different text (the
    "updates"); "confirmed" at the observation where the
    agreeing readings of the final number (as written or
    after look-alike correction) reach the validator's
    minimum of 2 with one of them at 0.85 or more, for
    confirmed tracks only; "lost" at the last frame with the
    direction; and "corrected" for each operator correction,
    the one kind with a wall-clock time rather than a video
    time. Clicking an event with a video time opens Video
    Analysis at that moment. The events are in the API's
    DetectionDetail (field "events").

 4. NEAR-MATCH FLAGGING IN THE REGISTRY — done 2026-11-07.
    Axis matches with one character of tolerance by default
    and documents that it lets look-alikes through. Here a
    registry record one edit away from a confirmed number
    (Levenshtein distance 1: one substitution, insertion or
    deletion; validation.edit_distance) is a "Possible
    match": amber, with the record and the differing
    character named in words ("3 read where the record has
    8", validation.describe_difference), and never counted
    or shown as a Match. Only confirmed numbers are looked
    up (the user's decision); the recognised number itself
    is never changed. services/registry.py returns a
    RegistryMatch (record, exact, distance, difference,
    others: how many more records are also one away); when
    several records are one away a substitution is preferred
    over a dropped or extra character, then the lowest
    number. Lookups normalise case and spaces. Shown in every
    detections table (amber "Possible match" with a tooltip),
    the details dialog ("Possible match · number · record"
    plus the difference), the Demo Registry page (counts
    "n match · m possible · k no match", the table, and the
    search answer in an amber banner) and the API
    (GET /api/registry/{number} answers match, possible,
    distance, difference and record, with response models;
    registry_match in the detection endpoints carries the
    record under "record"). The CSV export has
    demo_registry_possible (the near record's number) beside
    demo_registry_match (owner, exact matches only). The
    seeder adds near-miss records one look-alike character
    from a share of the confirmed numbers that have no record
    (seed-registry --near 0.25; deterministic; the note names
    the source number so a re-run adds nothing), so the state
    is visible in the demo: on 2026-11-07 it added 3 (and 4
    exact records, because the confirmed set changed when
    rope was dropped); the registry holds 29 records, and the
    Demo Registry page shows 21 match · 3 possible · 22 no
    match. No pipeline change, no reprocessing.

 5. HISTORY AND REGISTRY CONVENIENCES — done 2026-11-07.
    "Copy link" on Detection History and on a Demo Registry
    search puts the address of the exact view (every filter,
    sort and page is a URL parameter) on the clipboard.
    Registry records can belong to a named list ("Staff",
    "Visitors", "Watch") and carry an operator's description:
    demo_registry.list_name and .description (migration
    f7b3d9c4e1a2); `note` remains the provenance ("Added from
    the dashboard by … on …; fictional", "Imported from
    list.csv by …"), which the seeder also reads for its
    near-miss records. From the Demo Registry page a
    recognised number is added to a list (the search answer's
    "Add to a list", the recognised-numbers table's "Add to
    list"), which creates a fictional placeholder record for
    it when none exists (owner "(added from the dashboard)",
    valid a year); records are edited (list, description) or
    removed from their list, never deleted from the page; a
    CSV is imported with the columns of
    GET /api/registry/import-template.csv (only the number is
    required; an existing number is updated for the fields
    given; an invalid number or date skips the row with the
    line and the reason; an unknown vehicle type becomes
    Car). The page filters by list (URL parameter list) and
    shows List and Description columns; a Match in any
    detections table reads "Match · Staff" and the details
    dialog shows the list and the description. API:
    GET /api/registry/lists, GET /api/registry/import-
    template.csv, POST /api/registry/import (multipart),
    POST /api/registry/lists, PUT /api/registry/{id},
    DELETE /api/registry/{id}/list, GET /api/registry?list=.
    The dialog is components/registry_dialog.py (anchored to
    the page content, the operator's name from the browser as
    the corrections do). Everything added is fictional and
    says so. No pipeline change, no reprocessing.

 6. Outbound integration (future). An HTTP POST webhook per
    confirmed plate with the same JSON shape as the API's
    detection (plate, confidence, direction, time, video,
    crop URLs), a "Test with a virtual plate" button, and a
    buffer that stores events while the receiver is down and
    replays them, as Axis's push events do. Turns the POC
    into a component.

 7. Configuration after the freeze (future). The knobs Axis
    exposes that we keep fixed: confidence threshold (lower
    for low light), minimum number of characters, area of
    interest, retention period and capture type. Any of them
    changes results, so they wait until the demo and are
    judged with the accuracy procedure.

 FASTER VIDEO PROCESSING (item 4 of the future work)

 "Optimize the video processing pipeline to reduce
 processing time, especially for 4K videos. Explore batch
 inference, parallel processing, and faster video encoding."
 Taken in steps, cheapest first; each step is measured on
 the three demo videos and must leave every result
 identical. The settings frozen in Phase 7 are untouched.

 Where the time went before any change (clear.mp4, 4K at
 60 FPS, 2 min 25 s, 8,688 frames; the Phase 14 run,
 979 s in all):
   detection and tracking      536 s   55%
   plate detection and OCR      64 s    7%
   render pass                 379 s   39%
     second decode of the 4K     32 s
     plate detector run again   217 s   (to find the box
                                         to outline, in
                                         every frame)
     encoding 3840x2160         126 s
 The render pass was doing work that was already done
 (the plate boxes exist from stage 4) and encoding a size
 the browser never shows (the dashboard plays the video in
 a 1,000 px wide player).

 STEP 1 — RENDER PASS (done 2026-11-07)
   • The outlines come from the stage-4 plate sightings:
     annotate.plate_boxes_by_frame keeps each plate's
     position relative to its vehicle box, interpolates it
     between the examined frames and holds it outside
     them. The plate detector no longer runs in stage 7.
     Known limit: while a vehicle is partly hidden its box
     shrinks and the outline drifts by a few pixels (seen
     on rope: a truck passing behind a tree). A frame the
     tracker skipped gets no box, as before.
   • Inputs taller than 1080p are scaled down to 1080p for
     the annotated copy (PipelineOptions.annotated_max_
     height, default 1080; cv2.INTER_AREA before drawing;
     boxes scaled with the frame; width kept even). The
     original video, the crops and every result stay at
     full resolution. results.json records the copy's size
     under "annotated_video".
   • Measured by reprocessing the demo set through the
     worker (the earlier figures are the Phase 14 runs):

     Video      Format    Before   After   Render pass    Annotated file
     ─────────────────────────────────────────────────────────────────────
     clear      4K 60     979 s    667 s   379 s → 157 s  770 MB → 214 MB
     rope       4K 30     194 s    145 s    82 s →  33 s  288 MB →  90 MB
     zoomed-in  1080p 30  213 s    208 s    67 s →  43 s  111 MB → 107 MB

     clear now runs at 4.6 times its length (was 6.8),
     rope at 2.5, zoomed-in at 1.9. Detection and tracking
     varies by about 20% between runs of the same video,
     so the whole-run figures carry that noise; the render
     pass figures do not. On clear the render pass is now
     42 s decoding, 24 s scaling and drawing, 91 s
     encoding 1920x1080.
   • Results: every vehicle record, summary and plate
     count identical to the earlier runs (rope's
     timestamps moved by 1 ms because its file had been
     re-muxed without audio in between, which changed the
     reported frame rate in the fourth decimal).
   • Tests: plate_boxes_by_frame (interpolation, holding,
     the small-vehicle rule, tracks never seen),
     output_size, and rendering a tiny video at a smaller
     height with its boxes (tests/test_pipeline_logic.py).

 WHERE THE TIME GOES NOW (clear.mp4, 667 s)
   detection and tracking      472 s   71%   (4K decoding
                                              is CPU-bound)
   plate detection and OCR      38 s    6%
   render pass                 157 s   24%

 STEP 2 — DECODE ONCE, AND DECODE ON THE GPU (future)
   The 4K file is decoded twice (tracking pass and render
   pass), both by FFmpeg/OpenCV on the CPU at 5 to 10
   frames/s for 4K against 30 to 50 at 1080p, which is
   why detection and tracking is 71% of the run while the
   GPU waits. Two options, in order:
   • Hardware decoding (FFmpeg -hwaccel cuda / NVDEC)
     for both passes. The card has an NVDEC engine; the
     apt FFmpeg 6.1.1 in WSL needs checking for nvdec
     support (WSL passes the GPU through for CUDA; video
     engines are a separate question). Potentially the
     largest remaining lever for 4K.
   • Keep a 1080p copy of each frame from the first pass
     (on disk, ~6 MB per frame uncompressed, or as a fast
     intra-only video) and render from that, removing the
     second decode (42 s on clear).
   Rendering inside the tracking pass is not an option:
   labels show the settled class and the validated number,
   which are known only after the whole track is seen.

 STEP 3 — BATCH INFERENCE AND FASTER ENCODING (future)
   • Decode on a thread and feed YOLO26m batches of frames
     (Ultralytics tracking takes one frame at a time;
     batching needs the tracker to be driven per frame
     from batched detections). Worth doing only once
     decoding stops being the bottleneck.
   • Encode the annotated copy with NVENC (h264_nvenc)
     instead of libx264: the 91 s of 1080p encoding on
     clear would fall to roughly 15 s. Needs an FFmpeg
     build with nvenc in WSL; quality and file size to be
     checked against the current CRF 20 / preset fast.
   • Parallel processing across videos is one worker per
     GPU-sized slice of memory (a run peaks at 3.4 GB of
     16 GB); the queue already allows several workers, but
     one 4K run saturates the CPU decoder, so it is not
     expected to help on this machine and is not planned
     for the POC.

 HOW THE WORKER IS BUILT (worker/service.py, Phase 9)

 The processing_jobs table is the queue; nothing else passes
 between the web app and the worker. The web app (or the
 command line) inserts a row with status queued. A separate
 process, `tracko-anpr worker`, does the rest:

   claim      the oldest queued job, with SELECT ... FOR
              UPDATE SKIP LOCKED, so two workers could never
              take the same one; status → processing,
              worker_id, attempts + 1, started_at
   run        run_pipeline on the video's file, under the
              video's name, with the worker's own plate
              reader (started once, kept for every job, and
              restarted by the client if it dies)
   progress   stage, stage_done, stage_total and heartbeat_at
              written on the job at every stage change and
              at least every 2 seconds; a stale heartbeat is
              how a dead worker can be told from a slow job
   finish     store_result writes the figures and the rows
              in one transaction → completed; any exception
              → failed with "<type>: <message>" and the
              half-written folders removed; the worker then
              carries on with the next job
   recover    on start-up, every job still at processing was
              abandoned by a worker that died. First time:
              back to queued, folders removed. Second time:
              failed, with the reason, so a video that
              crashes the worker cannot loop for ever.
   stop       Ctrl+C or SIGTERM finishes the current job and
              exits; a second Ctrl+C interrupts it and puts
              the job back in the queue (not counted as a
              crash)

 The reader child process is started with PR_SET_PDEATHSIG,
 so a worker killed outright (kill -9, out of memory) takes
 the reader and its GPU memory down with it.

 Commands:
   uv run tracko-anpr worker [--once] [--poll-seconds N]
   uv run tracko-anpr ingest <path> [--name N]   register a
              file already on disk (no copy): for videos too
              large to upload through the browser
   uv run tracko-anpr enqueue <id | name | path>  queue it
   uv run tracko-anpr jobs                        the queue

 Verified 2026-11-07 against PostgreSQL:
   • A worker killed with kill -9 at 33% of plate detection
     on trafiic_part01: the next worker put the job back in
     the queue, removed the half-written folders and ran it
     to completion (223 s). One job, attempts 2, and the
     rows equal the file results: 182 tracks, 128 plates,
     91 events. No duplicates.
   • A reader whose parent was killed with kill -9 was gone
     8 seconds later and GPU use fell from 997 to 457 MiB.
   • A text file named .mp4 is refused at ingest ("moov
     atom not found").
   • A truncated MP4 (400 KB of a 2-minute clip) at first
     "completed" with 7 frames and no vehicles, because
     FFmpeg stops quietly where a file breaks. The pipeline
     now fails a run that reads under 90% of the frames the
     header declares: "Only 7 of 3680 frames could be read
     from truncated.mp4; the file is probably truncated or
     damaged."

                         │
                         ▼

══════════════════════════════════════════════════════════════
 4. OPENCV + FFMPEG — VIDEO PROCESSING
══════════════════════════════════════════════════════════════

 OpenCV:
   • Read video frames
   • Resize images for detection
   • Crop vehicles and number plates
   • Draw detection boxes and tracking labels

 FFmpeg:
   • Decode H.264 video
   • Inspect video properties
   • Encode annotated output video as H.264 MP4

 Important:
   • Preserve the original full-resolution frames
   • Do not use resized inference frames for plate crops

                         │
                         ▼

══════════════════════════════════════════════════════════════
 5. YOLO26m — AI MODEL 1: VEHICLE DETECTION
══════════════════════════════════════════════════════════════

 Framework       : Ultralytics / PyTorch
 Model           : YOLO26 Medium
 Weights         : yolo26m.pt
 Input Size      : 1536 (initial target)
 Precision       : FP16 where supported

 Detect:
   • Cars
   • Motorcycles
   • Buses
   • Trucks

 Output:
   • Vehicle bounding boxes
   • Vehicle class
   • Detection confidence

                         │
                         ▼

══════════════════════════════════════════════════════════════
 6. TRACKTRACK — VEHICLE TRACKING
══════════════════════════════════════════════════════════════

 Type            : Online multi-object tracking algorithm
 Implementation  : Ultralytics (compatible version)
 Configuration   : tracktrack.yaml

 Responsibilities:
   • Assign unique tracking IDs
   • Track vehicles between frames
   • Maintain vehicle identity during movement
   • Handle temporary occlusion where possible
   • Reduce duplicate vehicle counting

 Example:
   Car → Track #101
   Motorcycle → Track #102
   Bus → Track #103

 Note:
   Track IDs are local to each processing job.
   They are not permanent vehicle identities.

                         │
                         ▼

══════════════════════════════════════════════════════════════
 7. ORIGINAL-RESOLUTION VEHICLE CROPPING
══════════════════════════════════════════════════════════════

 Tool            : OpenCV
 Source          : Original full-resolution frame

 Process:
   • Obtain vehicle bounding box from YOLO26m
   • Map coordinates to original frame
   • Crop the vehicle from original-resolution video
   • Preserve maximum available image details
   • Pass vehicle crop to plate detector

                         │
                         ▼

══════════════════════════════════════════════════════════════
 8. YOLO26s — AI MODEL 2: NUMBER PLATE DETECTION
══════════════════════════════════════════════════════════════

 Framework       : Ultralytics / PyTorch
 Model           : YOLO26 Small
 Weights         : Indian fine-tuned checkpoint
 Input Size      : 640 initially
 Training        : Annotated Indian number plate dataset

 Responsibilities:
   • Locate Indian registration plates
   • Detect plates inside vehicle crops
   • Support front and rear plates
   • Handle different plate sizes and orientations

 Output:
   • Number plate bounding box
   • Plate detection confidence
   • Cropped plate image

 Important:
   Indian fine-tuned model weights must be obtained
   or trained; standard pretrained weights alone
   are not sufficient.

 Approach:
   1. Test the downloaded YOLO26 plate weights in
      pretrained-numberplate-weight/ on our own clips.
   2. Fine-tune YOLO26s on the IURS-NPDS dataset
      (19,309 images) only if they miss plates.

 Chosen (2026-11-06):
   sentry-26s, from the repository ayannotfound/Sentry.
   A YOLO26s at input size 640, made for vehicle crops.

   14 candidates were compared on 917 vehicle crops from all
   eight test videos. The five leaders were equivalent; this
   one matches the specification above and agreed with the
   others most. Fine-tuning was not needed: what limits the
   result is how large the plate is in the picture, not the
   detector. Full results:
   tools/plate_detector_eval/RESULTS.md

 Safe loading:
   The original is a .pt file, which can run code when
   loaded. It was scanned, loaded only inside a Docker
   container with no network, and re-saved there as plain
   data (safetensors numbers, a text layout, a details file).
   The application loads only that copy, from models/plate/,
   and refuses a .pt file.

 Measured: 4.8 ms per vehicle crop on the GPU at FP16.

                         │
                         ▼

══════════════════════════════════════════════════════════════
 9. AWIROS-ANPR-OCR — AI MODEL 3: TEXT RECOGNITION
══════════════════════════════════════════════════════════════

 Model           : Awiros-ANPR-OCR
 Architecture    : PP-OCRv5 based
 Framework       : PaddlePaddle
 Source          : Hugging Face — Awiros/anpr-ocr
 Runtime         : Own Python environment and process,
                   separate from the PyTorch models
 Decoder         : The model's attention (NRTR) decoder, with
                   the plate image widened by 1.5. Awiros's
                   reference script uses the CTC decoder,
                   which misses characters on two-line plates
                   (see "OCR Smoke Test" below).
 Service         : The reader runs as a long-lived program
                   (anpr-ocr serve) that the main program
                   starts and talks to in lines of JSON over
                   standard input and output, sending plate
                   crops as file paths. No network port is
                   opened.

                   Measured 2026-11-06: about 20 s to start,
                   then 8 to 10 ms per plate. If the reader
                   dies mid-request the caller gets a clear
                   error (after about 13 s, the time WSL
                   takes to release a GPU process), and the
                   next request starts a fresh reader.

 GPU memory with all three models loaded (YOLO26m at 1536 on
 a 2K frame, the plate detector, and the reader): about
 3.8 GB of the card's 16 GB.

 Responsibilities:
   • Read registration plate characters
   • Extract alphanumeric registration numbers
   • Support Indian-style number plates
   • Process single-line and double-line plates

 Example Output:
   KL10AB1234

 CTC Confidence:
   CTC stands for Connectionist Temporal Classification.

   It is the method the OCR model uses to turn a plate image
   into text. The model slices the image into narrow vertical
   strips, predicts a character (or "blank") for each strip,
   then merges repeats and drops the blanks to get the final
   string, such as KL10AB1234.

   The CTC confidence is the score the model gives that
   reading, between 0 and 1. In PaddleOCR it is the average
   of the probabilities of the characters it kept, so 0.97
   means the model was on average 97% sure of each character.
   It measures how sure the model is, not whether the reading
   is actually correct.

                         │
                         ▼

══════════════════════════════════════════════════════════════
 10. MULTI-FRAME VALIDATION — PYTHON LOGIC
══════════════════════════════════════════════════════════════

 Type            : Custom validation algorithm
 Separate AI     : Not required

 Process:
   • Collect OCR results for each tracked vehicle
   • Normalize recognized plate text
   • Compare readings across multiple frames
   • Use confidence-weighted consensus
   • Validate plausible Indian plate formats
   • Select most reliable plate number
   • Mark uncertain results as unconfirmed

 Example:
   Frame 1 → KL10AB1234
   Frame 2 → KL10AB1234
   Frame 3 → KL10A81234
   Frame 4 → KL10AB1234

   Final Result → KL10AB1234

 HOW IT IS BUILT (pipeline/validation.py, rules.py, runner.py)

 Which tracks count as vehicles ("Total Vehicles"):
   • Followed for at least 0.5 seconds, and at some point at
     least 6% of the frame height tall (65 px at 1080p).
     Sizes are fractions and times are seconds, so the rule
     means the same at any resolution and frame rate.
   • Not the camera car itself. Two shapes are recognised:
     its bonnet (a track 10 seconds or longer, a quarter of
     the frame wide, resting on the bottom edge 80% of the
     time) and, when the camera is inside the cab, its own
     door pillar and window boxed as a "car" (a track 3
     seconds or longer, at least two fifths of the frame
     wide, with another vehicle's whole box inside it in at
     least 10% of its frames, because the traffic is seen
     through it). Both are dropped from the counts and not
     drawn. Measured on 2026-11-06: every cabin track was at
     least 43% of the frame wide and no real vehicle more
     than 33%.
   • Not a repeat: a later track with the same confirmed
     number as an earlier one, not in view at the same time,
     is the same vehicle under a new track number. It keeps
     its number but is not counted again.
   • Not a repeat, parked vehicles (pipeline/repeats.py,
     2026-11-07): two tracks with no confirmed number are one
     parked vehicle when both barely moved (under 5% of the
     frame width), they never overlap in time, their boxes
     overlap by at least 50% once the camera's movement is
     removed, and their colours match at 0.6 or more. The
     track with a confirmed number stays counted, otherwise
     the earliest. See PARKED VEHICLES AND PLATE OWNERSHIP.
   "Unique Tracks" is every track the tracker produced.

 Which frames are read:
   • Up to 6 frames per vehicle, the ones where its box is
     largest and not cut off by the frame edge, at least
     0.15 seconds apart.

 Whose plate it is:
   • Vehicle boxes overlap in traffic, so a vehicle's cut-out
     can show a neighbour's plate. Among the boxes containing
     the plate's centre, one lying at least 80% inside another
     wins (a van's box takes in the car ahead of it). When
     two boxes only partly overlap, the nearer vehicle wins,
     the one whose box reaches lower in the picture. Box size
     alone was the rule until 2026-11-07, when a partly hidden
     bus with the smaller box received a car's plate.

 Plate formats accepted:
   • Standard: 2-letter state code, 1 to 2 digit district,
     0 to 3 series letters (never I or O), 1 to 4 digits.
     Short forms are real and must stay valid: KL39P77,
     KL361375 and TN062264 were all read correctly from
     plates in our clips.
   • BH series: 2 digits, "BH", 4 digits, 1 to 2 letters.
   • Look-alike characters (0/O, 1/I, 8/B, 5/S, 2/Z ...) are
     corrected only where that makes a reading valid, at
     most 2 per reading, and never when two corrections are
     equally possible.

 Deciding:
   • Readings under 0.60 confidence, and the reader's
     "unreadable" answers, do not vote.
   • Each remaining reading votes for its text with a weight
     equal to its confidence. A valid number beats text that
     is not one.
   • Confirmed needs all of: a valid format, at least 2
     frames giving the same number, at least 60% of the
     votes, and one reading at 0.85 confidence or more.
   • Two vehicles in view at the same time cannot both hold
     the same confirmed number: the one with more agreeing
     frames keeps it, the other becomes unconfirmed.

 Statuses:
   Confirmed     the rules above are met
   Unconfirmed   a plate was found, but the readings do not
                 meet them (the reason is recorded)
   Not Detected  no plate was found on the vehicle
   Failed        processing error

 Recognition coverage = confirmed ÷ Total Vehicles. It is
 coverage, not accuracy.

                         │
                         ▼

══════════════════════════════════════════════════════════════
 11. POSTGRESQL — DATABASE
══════════════════════════════════════════════════════════════

 Version         : PostgreSQL 18 (stable)
 Deployment      : Docker container inside WSL (Ubuntu 24.04)
 Access Layer    : SQLAlchemy, with Alembic migrations
 Driver          : psycopg 3

 Tables:
   videos
   processing_jobs
   vehicle_tracks
   plate_observations
   recognition_events
   demo_registry

 Store:
   • Video metadata
   • Processing job status
   • Vehicle tracking IDs
   • Vehicle categories
   • Bounding boxes and timestamps
   • Recognized registration numbers
   • Confidence and validation status
   • Fictional demonstration registry matches
   • References to image/video files

 Local File Storage:
   storage/uploads/
   storage/processed/
   storage/vehicle_crops/
   storage/plate_crops/

 HOW IT IS BUILT (db/models.py, db/store.py, db/metrics.py,
 migrations/)

 Seven tables: the six above plus app_settings, which holds
 the Settings page's values (each job also keeps its own
 snapshot of the settings it ran with, so changing a setting
 does not rewrite history). PostgreSQL stores facts and
 references only; the columns ending in _path point at files
 under storage/, relative to the project root.

   videos ──< processing_jobs ──< vehicle_tracks ──< plate_observations
                                       │
                                       ├──1 recognition_events
                                       └──< plate_corrections
   demo_registry   fictional; matched to recognition_events
                   by registration number, nothing else
   app_settings    key → value (JSONB)

   videos              one file: name (its folder under
                       storage/), path, size, width, height,
                       exact frame rate, frame count, length,
                       and plate_check (the plate-size check's
                       state and result, JSON)
   processing_jobs     one run of the pipeline over one
                       video; also the worker's queue:
                       status (queued, processing, completed,
                       failed), stage and progress, started /
                       finished / heartbeat times, worker id,
                       error, settings snapshot, timings,
                       memory, processing_seconds, and the
                       paths of the files it wrote
   vehicle_tracks      one per track: T<n> id (local to the
                       job), type, best confidence, first and
                       last frame and second, countable,
                       camera_car, same_vehicle_as,
                       counts_as_vehicle, vehicle crop path,
                       and the travel direction as approach
                       (towards / away / NULL) and sideways
                       (left / right / NULL)
   plate_observations  one per plate examined: frame, box,
                       detector confidence, reading, reader
                       confidence, unreadable, second decoder
                       text, which cut-out found it, crop path
   recognition_events  one per countable track: status
                       (confirmed, unconfirmed, not_detected),
                       registration number, confidence,
                       support, readings, share, reason, plate
                       crop path
   demo_registry       FICTIONAL: number, owner, vehicle,
                       type, colour, registering office,
                       valid until, note (provenance), and an
                       operator's description and list_name
   plate_corrections   an operator's correction of a track's
                       number and/or type, with the system's
                       values at the time, who, when, note;
                       newest row per track is current

 A video processed again gets a new job on the same videos
 row; every figure on the dashboard is measured over each
 video's latest completed job. Track ids mean nothing
 outside their job.

 The figures, defined once as queries in db/metrics.py:
   Total Vehicles        tracks with counts_as_vehicle
   Unique Tracks         every track of the job
   Recognized Plates     counted vehicles whose event is
                         confirmed
   Recognition coverage  Recognized ÷ Total. Not accuracy.
   Videos Processed      videos with a completed job
   Avg. Processing Time  mean processing_seconds of those
                         latest jobs
   Category breakdown    counted vehicles by type
   Detections Over Time  counted vehicles per 10-second
                         bucket of first_seen_s; adds up to
                         Total Vehicles
   Detections table      counted vehicles joined to their
                         event, newest first

 How results get in: `tracko-anpr process` registers the
 video and creates a job with status processing before the
 run (so a crash leaves a failed job with its error, not
 nothing), then store_result writes the job's figures and
 the rows. The worker (Phase 9) uses the same functions.
 `--no-db` writes files only.

 Verified 2026-11-07 on a 20-second run: the row counts
 equal the command's own summary (56 tracks, 31 vehicles,
 9 confirmed, 126 plates examined = 126 observation rows,
 32 events = 31 counted vehicles + 1 repeat track).

                         │
                         ▼

══════════════════════════════════════════════════════════════
 12. ANNOTATED VIDEO GENERATION
══════════════════════════════════════════════════════════════

 Tools           : OpenCV + FFmpeg
 Output          : H.264 MP4
 Resolution      : Up to 1080p (inputs above 1080p are scaled
                   down for playback; the original is untouched)
 Playback FPS    : Same as the input video

 Annotations:
   • Vehicle bounding boxes
   • Vehicle class labels
   • Persistent tracking IDs
   • Number plate bounding boxes
   • Recognized registration numbers
   • Recognition confidence
   • Validation status

 Output Example:
   storage/processed/video_001_annotated.mp4

 HOW IT IS BUILT (pipeline/annotate.py)
   • Rendered as a second pass, after validation, so a label
     shows only what the whole track supports.
   • Vehicle: bright green outline, dark green label with
     white text, e.g. "#T101 Car (0.98)".
   • Plate: amber outline at the plate, with the number just
     below it. The outline comes from the plates found in
     stage 4 (plate_boxes_by_frame): the plate's position
     relative to the vehicle box is interpolated between the
     examined frames and held before the first and after the
     last, so the plate detector does not run again in this
     pass (it used to, in every frame, and that was a quarter
     of a 4K run). While a vehicle is partly hidden its box
     shrinks and the outline can drift by a few pixels. Where
     a vehicle is too small to outline (under the 6%-of-frame
     rule) the number is written inside the bottom of its box.
   • Confirmed: black on amber, "KL10AB1234 (0.97)".
     Unconfirmed: amber on dark, "KL10AB1234 unconfirmed".
   • Same frame rate and frame count as the input; audio
     copied from the original. Inputs taller than 1080p are
     scaled down to 1080p (PipelineOptions.annotated_max_
     height; boxes scaled with the frame) because the browser
     plays them at a fraction of their size anyway and a 4K
     encode took as long as the tracking; detection, crops
     and results always use the original frames. results.json
     records the copy's size under "annotated_video".

 Files written for one video (tracko-anpr process):
   storage/processed/<name>/annotated.mp4
   storage/processed/<name>/results.json    per vehicle
   storage/processed/<name>/detections.csv  per box per frame
   storage/processed/<name>/plates.csv      per plate read
   storage/vehicle_crops/<name>/T<id>.jpg
   storage/plate_crops/<name>/T<id>_f<frame>.png

                         │
                         ▼

══════════════════════════════════════════════════════════════
 13. FASTAPI — RESULT DELIVERY
══════════════════════════════════════════════════════════════

 Responsibilities:
   • Expose completed processing results
   • Serve annotated video
   • Return recognized plate data
   • Return detection history
   • Calculate or retrieve analytics
   • Provide cropped vehicle/plate images

                         │
                         ▼

══════════════════════════════════════════════════════════════
 14. NICEGUI — FINAL LEADERSHIP DASHBOARD
══════════════════════════════════════════════════════════════

 PAGE 1: Overview
   • Total vehicles detected
   • Unique vehicle tracks
   • Confirmed registration numbers
   • Vehicle category breakdown
   • Processing status

 PAGE 2: Upload & Process
   • Upload videos
   • Video metadata
   • Plate-size check (are the plates big enough to read?)
   • Start processing
   • Processing progress and errors

 PAGE 3: Video Analysis
   • Original video playback
   • Annotated video playback
   • Tracking IDs and recognized plates
   • Fullscreen and playback controls

 PAGE 4: Detection History
   • Timestamp
   • Tracking ID
   • Vehicle category
   • Travel direction (towards / away from the camera,
     left / right), also a filter
   • Plate image
   • Recognized text
   • Recognition confidence
   • Validation status
   • Jump to video timestamp

 PAGE 5: Demo Registry
   • Fictional vehicle registrations
   • Demonstration vehicle information
   • Match / No Match status
   • Fictional records are generated from a share of the
     plates recognized in the demo videos, so the demo
     shows both matches and non-matches

 PAGE 6: Analytics
   • Vehicle category distribution
   • Detections over time
   • Recognition coverage
   • Processing duration
   • Average inference latency

 PAGE 7: Settings
   • Detection confidence thresholds
   • Model configuration
   • Tracking configuration
   • Processing resolution
   • Video output settings

 HOW THE DASHBOARD IS BUILT (dashboard/, Phase 11 onwards)

 One frame for every page (dashboard/layout.py): the theme,
 the 62 px header (app icon, title, subtitle, environment
 badge, decorative bell and profile), the 210 px sidebar with
 the seven navigation items and the status panel, and the
 content column. Pages call the service layer only, through
 dashboard/runtime.py, in a worker thread with a session of
 their own.

 The brand: the Tracko logo (DESIGN/logo/, added 2026-11-07)
 is blue on white in the original, which the design forbids,
 so tools/make_logo_assets.py derives theme-coloured copies
 with a transparent background (car body light, brackets
 and signal arcs green) into dashboard/static/logo/. The
 full logo with the wordmark sits in the header next to
 "Vehicle ANPR POC"; the mark alone is the favicon, the
 header on narrow screens, and a faint watermark behind
 every empty state. The originals are never served.

 Colours: every colour is a token in dashboard/static/
 theme.css (DESIGN section 18); Quasar's palette is replaced
 per page with ui.colors so no blue reaches the screen; the
 Inter font is served from the package, nothing from the
 internet. Filled green is dark green #166522 with white text.

 The status panel is live: services.readiness every 5 s;
 green "System Ready" only with the database, a worker, the
 models, the reader and FFmpeg all present, otherwise amber
 "Attention needed" naming what is missing.

 Upload & Process (dashboard/pages/upload.py): the dropped
 file is saved under storage/uploads/.incoming, checked with
 ffprobe and named exactly as an API upload would be, then
 shown (file name, size, resolution, duration, frame rate,
 when added). "Process Video" queues a job for the worker;
 the seven-stage timeline and the progress bar are redrawn
 every second from the job row until it ends as Completed
 (with View Analysis, Download Annotated Video and View
 Detections) or Failed (with the reason in red). A list of
 every registered video lets one be picked and processed
 again. Nothing on the page is simulated.

 The video player component (dashboard/components/player.py)
 is built here for the Overview and Video Analysis pages:
 the browser's own controls (play, seek bar, time, volume,
 speed, fullscreen) under an Original / Annotated segmented
 control that keeps the playback position and state when
 switching; seek() lets a table row jump the video.

 Verified 2026-11-07 in headless Chromium on the Windows host
 (the pages fill in over a websocket, so a plain screenshot
 flag is not enough):
   • The frame matches the reference layout: header, 210 px
     sidebar with the active item's green bar, dark cards,
     green and amber accents, no blue anywhere.
   • zoomed-in.mp4 (265 MB, 1080p, 1 min 50 s) uploaded
     through the page's file input, was shown with its
     details, was queued with "Process Video", showed live
     progress ("Processing 29%", "69 / 3,288 frames") and
     ended Completed after 209 s on the worker: 59 vehicles,
     16 confirmed plates, with per-stage times on the
     timeline and the three follow-up buttons.
   • With the worker stopped, the panel turned amber
     "Attention needed: worker last reported 29 s ago" within
     one refresh; with it running, green "System Ready".
   • A bug found by the run: a timer created inside a click
     handler whose button had just been redrawn raised "The
     parent element this slot belongs to has been deleted",
     so the page never polled. Timers are now created once at
     page build and only switched on and off.

 THE OVERVIEW (dashboard/pages/overview.py, Phase 12)

 Data: one call, services/overview.py, so the page is thin
 and the figures can be tested against the queries directly.
   • Video selector: every video with a completed job, the
     newest selected by default (?video=<id> picks one). It
     drives the player, the timeline, the donut, the coverage
     bar, the table and the chart.
   • Scope switch "This video / All videos" for the five
     cards only; the header card shows Processed: N Videos
     and the last run's time across all videos.
   • Cards: Total Vehicles, Recognized Plates with coverage
     in green, Unique Tracks, Videos Processed, Avg.
     Processing Time (mean of each video's latest run). A
     line under them says coverage is not accuracy, or, in
     the all-videos scope, what the cards and charts count.
   • Video Analysis: the player component, annotated copy
     by default, original on the switch, position kept.
   • Processing Status: the seven-stage timeline of the
     video's latest completed job with per-stage seconds.
   • Vehicle Category Distribution: ECharts donut in the
     design's four colours (Car green, Motorcycle yellow,
     Bus amber, Truck red-orange), the total in the centre,
     legend with icon, count and share.
   • Recognition Coverage: thin green bar, percentage, and
     "confirmed / counted vehicles with recognized number
     plates", with the not-accuracy note.
   • Recent Detections: the eight newest counted vehicles
     (time, track, type with icon, number, confidence,
     validation badge, plate thumbnail). A row click seeks
     the video to half a second before the vehicle appears
     and opens the details dialog: vehicle and plate crops,
     the number, validation, confidence, agreement, reason,
     every plate observation (frame, time, reading, reader
     and detector confidence, plate width) and the fictional
     registry match or "No match", with the disclaimer.
     "View All" goes to Detection History for that video.
   • Detections Over Time: ECharts stacked bars per
     10-second bucket of video time, split by travel
     direction (towards the camera in bright green, away in
     dark green, undetermined in grey, with a legend); the
     buckets add up to Total Vehicles.
   • Empty states: with nothing processed, the cards read 0,
     the player, charts and table say so, and the selector
     and scope switch are disabled; nothing is invented.

 Verified 2026-11-07: cards equal metrics.summary for the
 video and for all videos (tests); the chart's buckets sum
 to Total Vehicles (tests); an empty database renders the
 page (test and by hand); in headless Chromium on zoomed-in-2
 the cards read 59 / 16 (27.1%) / 85 / 1 / 3 min 29 sec, the
 all-videos scope 240 / 44 (18.3%) / 412 / 5 / 2 min 35 sec,
 a row click moved the video to 1:46 and opened the dialog,
 and switching Original / Annotated kept the position (42 s)
 both ways, with no browser console errors.

 THE REMAINING PAGES (Phase 13)

 Video Analysis (/analysis?video=&t=): the player at full
 width with the Original / Annotated switch; download
 buttons for the annotated video, results JSON, detections
 CSV and plates CSV; Plate Recognition figures for the
 video; the processing timeline; and Tracked Vehicles,
 every counted vehicle in order of appearance (time, track,
 type, number, confidence, validation, registry, plate
 thumbnail). A row seeks the video to the vehicle's first
 appearance and opens the details dialog. ?t= seeks on
 arrival, which is how a History row lands here.

 Detection History (/history): every counted vehicle across
 all processed videos, with filters (video, validation
 state, vehicle type, number search), sortable columns,
 pages of 25, and Export CSV, which downloads exactly the
 rows the filters select through /api/detections/export.csv.
 A row opens the details dialog with an "Open in Video
 Analysis" button that lands on the player at that moment.

 Demo Registry (/registry): "Demonstration Data Only" in an
 amber banner at the top, with the disclaimer sentence; a
 number lookup (exact match → green banner with the
 fictional record, otherwise "no exact match"); Recognised
 Numbers vs Registry, every number the pipeline confirmed
 with Match / No Match and the fictional record; and the
 registry records themselves. `tracko-anpr seed-registry`
 generates the records (services/registry_seed.py):
 fictional owner, vehicle, colour, registering office (by
 state code) and validity for about half of the confirmed
 numbers (--share), plus a few numbers that appear in no
 video (--extra), deterministically (--seed), so a re-run
 adds nothing; --reset starts over.

 Analytics (/analytics?video=): for one video or all:
 category donut, validated vs uncertain bars (confirmed,
 unconfirmed, no plate found), recognition coverage,
 detection activity (over video time for one video; counted
 vehicles per video across all), confidence distribution of
 confirmed numbers in bands, and processing duration per
 video with a table of length, processing time, speed
 against real time, frames, ms per frame and ms per plate.
 The average inference latency is weighted by frames and
 plates, not a mean of per-video means.

 Settings (/settings): the frozen pipeline settings in the
 design's groups (model configuration, processing
 resolution, tracking, detection and recognition
 thresholds, video output, storage) with their real values
 and a note that they are frozen; nothing is editable in the
 POC, and a value stored through the API would be shown
 beside the value the pipeline runs with.

 DEMO DATA AND READINESS (Phase 14, 2026-11-07)

 The test runs were cleared (tracko-anpr reset-data --yes)
 and the demo videos processed through the worker, with the
 frozen settings. The user removed the three portrait
 recordings on the same day (portrait-narzo before its run
 finished, portrait and portrait-new after theirs), so the
 demo set is three videos; their results were removed from
 the database and storage/ and the registry re-seeded.

 Video         Format     Length  Processing  Tracks  Vehicles  Confirmed  Coverage
 ────────────────────────────────────────────────────────────────────────────────────
 zoomed-in     1080p 30    1:50    3 min 33 s    85       59        16      27.1%
 rope          4K 30       0:57    3 min 14 s    12        7         2      28.6%
 clear         4K 60       2:25   15 min 44 s   269      185        30      16.2%
 All three                 5:12   22 min 31 s   366      251        48      19.1%
 (rope was dropped from the demo set later that day; the
 set is clear and zoomed-in: 354 tracks, 244 vehicles, 46
 confirmed, 18.9% coverage.)

 By type: Car 75, Motorcycle 143, Bus 2, Truck 31. Plate
 status: 48 confirmed, 175 unconfirmed, 28 with no plate
 found. Inference latency over all frames: 50 ms per frame
 for detection and tracking (4K decoding is the cost: 35 ms
 at 1080p, 53 to 60 ms at 4K), 29 ms per plate read.
 Processing ran at 0.15x to 0.52x real time; clear.mp4 took
 6.5 times its length, half of it writing the 4K annotated
 copy (locating plates again in every frame and encoding
 3840x2160). For the record, the two portrait videos ran
 at 0.22x real time (8 and 17 minutes) with 20.6% and 24.3%
 coverage before they were dropped. Coverage is not
 accuracy.

 FIRST ACCURACY MEASUREMENT (2026-11-07, zoomed-in only)

 The first run of "HOW TO MEASURE REAL ACCURACY", on all 59
 counted tracks of zoomed-in. A first figure, not a firm one:
 the sample is small and the margins are wide.

 Tracks labelled                 59
 Real distinct vehicles          32
 Repeat tracks of those          27    (no false tracks)
 Confirmed among the 32          16
   correct                       15
   wrong                          1
 Reading accuracy                15 of 16 = 94% ±25 points
 Plates a person can read        28
 Reading recall                  15 of 28 = 54% ±19 points
 Unconfirmed or no plate         16: 8 right number, 3 wrong
                                 number, 4 no number, 1 not
                                 checkable
 Vehicle type errors             5 of 32

 The one wrong confirmation: T26, system KL65H4621, true
 KL65M4621 (one character, M read as H, two-line plate with a
 shadow across it, 60 to 85 px). Crop:
 storage/plate_crops/zoomed-in/T26_f*.png. Two readers
 independently read M.

 What it shows:
   • Total Vehicles overcounts this video: 59 against 32 real
     vehicles. One parked scooter (KL842291) holds 19 tracks
     and another 5, because repeats are merged only by a
     confirmed number and neither number confirmed, and the
     tracker loses a parked vehicle each time traffic passes
     in front. The repeat rule needs a position test for
     parked vehicles; that is pipeline work for after the
     demo.
   • The confirmation rules are cautious, as designed: of the
     11 unconfirmed vehicles with a checkable reading, 8 had
     the right number and 3 the wrong one. Loosening them
     would gain true numbers and let some errors through.
   • Types: the two jeeps, the Thar and the red taxi came out
     as Truck, and the auto-rickshaw as Truck (it has no class
     of its own).
   • Two track faults seen: T30 starts on a red taxi and jumps
     to the jeep of T32, and the plate crop under bus track
     T109 belongs to motorcycle T111 passing behind it.

 How it was labelled: Claude read every track from crops only
 (tools/label_contact_sheets.py, with full frames for T30 and
 T109), without seeing the system's answers; those labels
 were committed before any comparison (8d3fc27). The user
 then read 21 plates blind on a page showing crops only: the
 11 Claude marked doubtful and 10 random sure ones. All 10
 spot checks agreed exactly. Of the 11 doubtful, 5 agreed and
 6 differed; the user's reading was taken, except T3 and T4,
 whose answers were not complete numbers and stay partly
 legible. So 21 tracks had a human eye and the rest of the
 sheet is Claude's alone: weaker than a fully human-labelled
 sheet, and the figures must be quoted with that said.

 Not measured: vehicles with no track at all, which needs
 someone to watch the video. Not covered: clear, whose rows
 would give 30 more confirmed numbers. Pipeline: the answers
 come from job 18, run on the code committed as 73a8564.
 Files: labels/zoomed-in_system.csv and _truth.csv; recount
 with tools/measure_accuracy.py. No accuracy figure is shown
 on the dashboard; at n = 16 it waits for the full sample.

 SECOND ACCURACY MEASUREMENT (2026-11-07, kdy, the main video)

 All 167 tracks labelled the same way, on the answers from
 the reprocessing described under PARKED VEHICLES AND PLATE
 OWNERSHIP (job 22, run on the code merged as 61936ef).
 Plain-language version: ACCURACY.md.

 Tracks labelled                 167
 Real distinct vehicles          87
 Shown as Total Vehicles         125
 Repeat tracks                   80   (42 merged by the
                                      system, 1 of those a
                                      real vehicle lost)
 Confirmed among the 87          3, all correct (too few for
                                 a percentage; ±58 points)
 Plates a person can fully read  10 (13 more in part, 64 not)
 Reading recall                  3 of 10 = 30% ±32 points
 Those 10 plates                 3 confirmed right, 1 right
                                 but unconfirmed, 5 wrong but
                                 unconfirmed, 1 no reading
 Vehicle type errors             16 of 87, 13 of them
                                 three-wheelers with no class

 The 5 wrong readings each differ by one character (KL18BL1647
 for KL10BL1647, KL84E7031 for KL84E7081), and none was
 confirmed: the rules kept them out. Of the 83 vehicles left
 unconfirmed, 1 had the right number, 5 a wrong one, 67 no
 number, and 10 cannot be checked.

 How it was labelled: Claude read all 167 from crops only,
 committed before any comparison (ef7f8b9). The user then read
 29 plates blind, under rules fixed beforehand: the 19
 doubtful, the 4 Claude was sure of, and 6 large ones marked
 unreadable. The user could fully read 9 of the 29. Of Claude's
 4 sure plates, 3 matched exactly and T254 could be read only
 in part. Of the 19 doubtful, 4 matched, T66 settled a letter
 Claude could not read, T76 differed by one digit (the user's
 reading was used), and the rest could not be confirmed and
 left the scoring: T312, T326 and T368 were readable to Claude
 alone, and on T368 the two readers disagreed. T30's answer
 looks complete, but that plate is cut off by the frame edge, so it
 stays partly legible. None of the 6 unreadable plates was read
 in full. KL84F8061 rests on Claude's reading of T269, whose
 crops are sharp, and T254 was relabelled as its repeat so the
 labels name the track the system counts. Vehicles were matched
 by appearance, so 87 is an estimate. Vehicles with no track
 at all were not measured.

 PARKED VEHICLES AND PLATE OWNERSHIP (2026-11-07)

 Two faults the labels exposed, fixed together. This reopens
 the Phase 7 freeze for these two rules only, at the user's
 request; every other setting stays frozen.

 Parked vehicles. Repeats were merged only by a confirmed
 number, so a parked vehicle with an unreadable plate was
 counted each time traffic passed in front of it. Phone
 footage also moves, so pixel position alone is not enough:
 a plain same-place rule wrongly merged 23 to 33 vehicles on
 kdy at the overlap that removed most repeats. So
 track_video now measures the camera's movement
 (tracking.CameraPath, cv2.phaseCorrelate on every 6th frame
 at 480 px wide), which feeds only this rule, and
 pipeline/repeats.py compares tracks by corrected position
 and colour (ParkedRules: max_move 0.05, min_overlap 0.5,
 min_look 0.6, recorded in results.json's settings).
 mark_parked_repeats runs after mark_repeat_tracks and uses
 the same same_vehicle_as column, so the database, API and
 pages are unchanged. Tracks in view together, or with two
 different confirmed numbers, are never merged.

 Plate ownership. See "Whose plate it is". Offline on the
 stored sightings, 4 of 238 moved on zoomed-in and 37 of 643
 on kdy, none shown to move away from the right vehicle. One
 blank reading went from a car to a scooter in front of it
 (T289, frame 1365): the known cost of the nearer-vehicle
 rule, and it has no text.

 Measured on kdy, reprocessed twice with identical results:

                            Before   After
 Tracks                       301     301   (tracking unchanged)
 Total Vehicles               167     125   (87 real, labelled)
 Repeat tracks                  0      42
 Confirmed numbers              4       3
 Run time                   279 s   324 s

   • 42 tracks merged: 40 right, 2 wrong. T358, a three-wheeler,
     was merged into a parked van and is the one real vehicle
     lost from the count. T376 went to the wrong parent but
     was a repeat anyway.
   • The confirmed number removed was the wrong one: the bus T1
     no longer holds the white car's KL11BG7003. The car T4
     now has those readings and stays unconfirmed, because its
     9 readings disagree (7003, 7008, 7009). That is the
     caution working.
   • All 3 confirmed numbers are right by the labels.
   • Run time: the new steps measure about 3 s (camera 1.7 s,
     validation 0.9 s). The rest of the rise is in the tracking
     stage, which swung from 160 to 269 s across these runs;
     the 410 s run was slowed by my own status polling. Nothing
     suggests the new code causes it, but it was not isolated.

 Limits:
   • A partial fix. kdy's overcount fell from 92% to 44%, and
     38 extra entries remain. Looser thresholds merge real
     vehicles, which then vanish from the count (at 111
     entries, 12 are wrong), so they stay strict.
   • The thresholds were chosen on the labels they are scored
     on, so other footage may do a little worse.
   • Only kdy was reprocessed. clear and zoomed-in keep their
     stored rows on the old rules; offline, zoomed-in would go
     from 59 to 42 for 32 real, with no wrong merge.
   • Readings are not pooled across a parked vehicle's tracks,
     which might confirm more numbers but changes validation.

 Why kdy confirms so few (measured 2026-11-07): for 127 of
 167 entries a plate was found but could not be read. 61% of
 its plates are under 60 px wide, where nothing read
 confidently, and even at 150 px or more only 35% of readings
 were confident, against 70 to 77% on clear and zoomed-in.
 Large plates look melted by eye. A simple sharpness measure
 did not confirm that (249 against 270 and 93), so its cause
 is unproven; heavy phone processing is a guess. Of 87 vehicles
 only 10 plates were fully readable by eye and 13 partly (see
 SECOND ACCURACY MEASUREMENT). The plate-size check cannot see
 this, because it measures size only.

 Registry: tracko-anpr seed-registry --reset made 18
 fictional records for 48 confirmed numbers plus 4 for
 numbers seen in no video (22 in all), so the Demo Registry
 page shows both matches and non-matches.

 Backup: scripts/backup.sh. Proved on the five-video set by
 wiping everything with reset-data and restoring with
 scripts/restore.sh: every row count and figure identical,
 every folder and file back. The current backup of the
 three-video set is backups/20261107-035046 (storage.tar
 1.2 GB).

 Cold start: after `wsl --shutdown`, following only the
 README's "Demo day" steps, the container was up on its own
 5 seconds after WSL started, the migration was a no-op, and
 15 seconds later /api/system/status said ready on all six
 checks with the demo data in place.

 Cold start, second rehearsal (2026-11-07, after the day's
 changes: cheaper render pass, travel direction, plate-size
 check, registry near-match and lists, the rebuilt .venv,
 three more migrations). Following only the runbook from
 `wsl --shutdown`: the container was listed 6 s after the
 first WSL command and healthy 2 s later, alembic upgrade
 head was a no-op at f7b3d9c4e1a2, the worker logged ready
 within seconds, /api/system/status said ready as soon as
 the web app answered, db-status showed 2 videos, 244
 vehicles, 46 confirmed. All seven pages rendered in
 headless Chromium with no console errors (System Ready,
 Direction columns, Events, the 1080p annotated player, the
 registry's 22 match · 3 possible · 21 no match with the
 Staff list). A live upload of a 20-second zoomed-in cut:
 registered in 1 s, plate-size verdict after 50 s (cold
 worker, "largest plates about 138 px"), processed to
 Completed 68 s after the click, 11 vehicles; the test video
 was then removed. scripts/restore.sh of the latest backup
 (20261107-090212) with the services stopped took 15 s and
 left every figure and the 30 registry records as they were;
 the services were ready again 7 s after being started.
 Nothing tripped; the runbook gained the measured times and
 a row for the plate-size check.

 Offline: with every request to any host other than the app
 blocked, all seven pages rendered with the Inter font, the
 icons and the charts; no request left the machine.

 Readiness checks also fixed one thing: the status panel
 flickered amber while the worker was busy, because a job's
 heartbeat comes with progress reports and the reader's
 start-up and a plate batch report nothing for 20 seconds or
 more; a busy worker is now allowed 60 s between reports.

 Verified 2026-11-07 in headless Chromium, the whole journey
 clicked through the sidebar: 59 tracked vehicles on Video
 Analysis; History 240 counted vehicles → 44 confirmed → 42
 with "KL", sorted by confidence ascending (0.85, 0.88, ...);
 a History row opened Video Analysis at 71.31 s; Export CSV
 downloaded detections.csv with the 44 filtered rows; the
 registry showed 8 matches and 20 no-matches after seeding
 (28 confirmed numbers, 8 + 4 records), a known number looked
 up as a Match and an unknown one as no match; Analytics and
 Settings rendered; no browser console errors.


══════════════════════════════════════════════════════════════
 FINAL DEPLOYMENT CONFIGURATION
══════════════════════════════════════════════════════════════

 Language         : Python
 Frontend         : NiceGUI
 Backend          : FastAPI 0.162.0
 Web Process      : One process — NiceGUI mounted on the
                    FastAPI app
 Processing       : Separate Python worker
 Job Queue        : processing_jobs table in PostgreSQL,
                    polled by the worker
 Video Processing : OpenCV + FFmpeg
 Object Detection : Ultralytics YOLO26m + YOLO26s
 Tracking         : TrackTrack
 OCR              : Awiros-ANPR-OCR
 Validation       : Multi-frame consensus
 Database         : PostgreSQL 18 (stable), Docker inside WSL
 Database Access  : SQLAlchemy + Alembic migrations, psycopg 3
 Storage          : Local filesystem
 GPU              : NVIDIA GeForce RTX 4070 Ti SUPER (16 GB VRAM)
 CPU              : AMD Ryzen 9 7900X (12 cores / 24 threads)
 RAM              : 32 GB (2 × 16 GB)
 GPU Driver       : NVIDIA 572.16 (supports up to CUDA 12.8),
                    kept as is — no driver upgrade
 PyTorch          : 2.14.1, CUDA 12.6 build
 OCR Runtime      : Separate Python environment and process
                    (PaddlePaddle 3.3.1, CUDA 12.6 build),
                    because PyTorch and PaddlePaddle require
                    different cuDNN versions
 Host OS          : Windows Server 2022 Standard (64-bit)
 Runtime          : WSL 2 — Ubuntu 24.04 (entire application)
 Inference        : FP16 where supported
 Input            : Recorded H.264 MP4
 Output           : Annotated MP4 + detection results
 Dependencies     : Latest stable at install time, locked in
                    uv.lock (FastAPI and PostgreSQL are pinned
                    exactly)
 Code Quality     : Ruff (linting and formatting),
                    pytest (tests)

 PROCESSING MODE:
   Offline uploaded-video analysis.
   Processing does not need to run at real-time speed.

 NOT REQUIRED FOR INITIAL POC:
   ✗ Stationary CCTV camera
   ✗ Live RTSP stream
   ✗ WebRTC
   ✗ Live camera connection
   ✗ Redis / Celery
   ✗ Cloud infrastructure
   ✗ Microservices deployment

 FUTURE IMPLEMENTATION:
   Run NiceGUI and FastAPI as two separate services instead
   of one process. What two services would buy:
   • The API and the dashboard could be restarted, deployed
     or scaled independently.
   • A different frontend could replace NiceGUI later
     without touching the backend.

   Indian vehicle classification. Train the vehicle detection
   model to recognize auto-rickshaws, scooters, vans and other
   Indian vehicle categories. This will improve vehicle
   classification and traffic analytics. The POC keeps four
   classes (car, motorcycle, bus, truck) because the stock
   YOLO26m model knows only those, so an auto-rickshaw is
   today labelled car or motorcycle, a scooter is a
   motorcycle, and a van a car or truck. How it would be
   done: collect and label frames from the user's own
   footage (a few hundred boxes per new class, from several
   videos and times of day), fine-tune YOLO26m on them with
   the stock classes kept, measure against a held-out set
   (same method as "HOW TO MEASURE REAL ACCURACY"), then add
   the classes to VEHICLE_CLASSES, the donut colours, the
   icons and the registry seeder. It changes a frozen
   setting, so every demo video would be processed again,
   and the YOLO26 AGPL question (below) applies to the
   trained weights too.

   Measure real accuracy. For now the dashboard shows
   recognition coverage and confidence only, labelled as not
   being accuracy. The step-by-step procedure is the section
   "HOW TO MEASURE REAL ACCURACY" near the end of this file;
   it needs a hand-labelled set, which does not exist yet.

   A fallback plate reader. The Awiros model passed its test
   on this project's plates, so it is the only reader for
   now. Later: add the stock PP-OCRv5 model as a second
   reader to switch to if Awiros ever proves unsuitable.

 OPEN ITEM — LICENCE:
   Ultralytics YOLO26, and any weights trained from it, are
   AGPL-3.0. Company use may need an Ultralytics Enterprise
   licence. The POC proceeds with YOLO26; this must be
   settled before any production or customer use.


══════════════════════════════════════════════════════════════
 SYSTEM SETUP — INSTALLATION COMMANDS
══════════════════════════════════════════════════════════════

 Run inside WSL (Ubuntu 24.04). Each entry records what was
 actually run on this machine and when.

 FFMPEG
   Installed : 2026-11-06, version 6.1.1-3ubuntu5 (apt)
   Location  : /usr/bin/ffmpeg and /usr/bin/ffprobe

   Install:
     sudo apt-get update
     sudo apt-get install -y ffmpeg

   Verify:
     ffmpeg -version
     ffprobe -version

 PYTORCH + ULTRALYTICS (main environment)
   Installed : 2026-11-06
   Versions  : torch 2.14.1+cu126, torchvision 0.29.1+cu126,
               ultralytics 8.4.203

   pyproject.toml points torch and torchvision at PyTorch's
   CUDA 12.6 download index, so the plain command below
   fetches the build that matches the GPU driver.

   Install (in WSL, not Windows PowerShell):
     cd /mnt/c/Users/ontashai/Desktop/tracko-anpr
     export UV_LINK_MODE=copy
     uv add "torch==2.14.1" torchvision ultralytics

   UV_LINK_MODE=copy tells uv to copy package files into the
   virtual environment instead of linking them from its
   cache, which cannot work across the WSL and Windows
   drives.

   Then check that it worked and the GPU is visible:
     uv run python -c "import torch, torchvision, ultralytics; print(torch.__version__, torchvision.__version__, ultralytics.__version__); print('CUDA available:', torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"

   Expected output:
     2.14.1+cu126 0.29.1+cu126 8.4.203
     CUDA available: True
     NVIDIA GeForce RTX 4070 Ti SUPER

 PADDLEPADDLE (OCR environment, separate from the main one)
   Installed : 2026-11-06
   Versions  : paddlepaddle-gpu 3.3.1 (CUDA 12.6 build),
               with nvidia-cudnn-cu12 9.5.1.17
   Location  : ocr/.venv

   ocr/pyproject.toml points paddlepaddle-gpu at Paddle's own
   CUDA 12.6 download index, because PyPI only has the old
   2.6.2.

   Install (in WSL, inside the ocr folder):
     cd /mnt/c/Users/ontashai/Desktop/tracko-anpr/ocr
     export UV_LINK_MODE=copy
     uv add "paddlepaddle-gpu==3.3.1" safetensors numpy opencv-python pillow pyyaml shapely scikit-image pyclipper rapidfuzz tqdm requests packaging

   Then check that PaddlePaddle works on the GPU:
     uv run python -c "import paddle; print(paddle.__version__); print('CUDA build:', paddle.device.is_compiled_with_cuda()); paddle.utils.run_check()"

   Expected output: 3.3.1, CUDA build: True, and a final line
   saying PaddlePaddle is installed successfully.

   What to expect:
   • A warning about VIRTUAL_ENV: when the terminal has the
     main (tracko-anpr) environment active, uv says it is
     ignoring it. That is harmless; uv creates a separate
     ocr/.venv, which is the point. Run deactivate first to
     avoid the warning.
   • A "libcuda.so ... cannot open shared object file"
     message was printed on this machine, but the GPU check
     still passed. If the OCR model later fails to use the
     GPU, try:
       export LD_LIBRARY_PATH=/usr/lib/wsl/lib:$LD_LIBRARY_PATH

 PADDLEOCR SOURCE CODE (ocr/vendor/, git-ignored)
   Downloaded : 2026-11-06
   Version    : tag v3.7.0, commit
                b03f46425e8ff4442b268ce449e3eef758146cd4
   Size       : about 243 MB

   The Awiros OCR model is not a pip package: its network is
   built from PaddleOCR's own source code (the ppocr folder),
   so that code must be present on disk.

   Download (in WSL):
     cd /mnt/c/Users/ontashai/Desktop/tracko-anpr
     git clone --depth 1 --branch v3.7.0 https://github.com/PaddlePaddle/PaddleOCR.git ocr/vendor/PaddleOCR

   Checked on this machine: the code imports in the OCR
   environment with the packages already installed, and the
   network it builds matches the Awiros weights exactly
   (545 of 545 tensors, 37.3 million values, no mismatches).

 DEVELOPMENT TOOLS AND TRACKING DEPENDENCY (main environment)
   Installed : 2026-11-06
   Versions  : ruff 0.17.4, pytest 9.2.0, lap 0.5.14

   Install (in WSL, from the project root):
     export UV_LINK_MODE=copy
     uv add "lap>=0.5.12"
     uv add --dev ruff pytest

   lap is required by Ultralytics tracking. Ultralytics would
   otherwise install it by itself, outside uv.lock, and the
   next uv sync would remove it. The application sets
   YOLO_AUTOINSTALL=False so that cannot happen silently.

   Use:
     uv run ruff check
     uv run ruff format
     uv run pytest

 MODEL FILES (models/, git-ignored)
   Placed    : 2026-11-06

   Vehicle detector, official Ultralytics release asset:
     curl -L -o models/yolo26m.pt https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26m.pt
     SHA-256 401cea9ab23ad19246ff7744859816bc599f350e93c9dd30367b6f0a0745d0b7

   OCR model, Hugging Face Awiros/anpr-ocr
   (revision eadbc5ae4faa8284c8a547a60142fd555c3059ca):
     mkdir -p models/awiros
     for f in model.safetensors en_dict.txt LICENSE README.md requirements.txt test.py; do curl -L -o models/awiros/$f https://huggingface.co/Awiros/anpr-ocr/resolve/main/$f; done
     SHA-256 of model.safetensors:
     f9f1264e0c115a239ca6d6700a74ceffab17168b75dafc6c169c232012c68e47

 PLATE DETECTOR MODEL (models/plate/, git-ignored)
   Placed    : 2026-11-06
   Source    : pretrained-numberplate-weight/
               ayannotfound__Sentry/best.pt
               (https://github.com/ayannotfound/Sentry)
   SHA-256 of that source file:
     13f5aef6dfbeb294593726fb0d714d85bea642cb43e622eb3dcccc846e98ea0d
   SHA-256 of models/plate/sentry-26s.safetensors:
     7002e81e07ee53a5fd709d7b88b0af44f27b46dd3ee59919ec011385913b4d7b

   Made by re-saving the source file as plain data inside the
   no-network sandbox (run from the repository root, in WSL):

     docker build -t tracko-plate-sandbox tools/plate_detector_eval/sandbox
     mkdir -p storage/processed/phase4_export models/plate
     docker run --rm --network none --read-only --tmpfs /tmp:rw,size=2g --cap-drop ALL --security-opt no-new-privileges --pids-limit 512 --memory 10g -v "$PWD/pretrained-numberplate-weight:/weights:ro" -v "$PWD/tools/plate_detector_eval/sandbox:/work:ro" -v "$PWD/storage/processed/phase4_export:/out:rw" tracko-plate-sandbox python /work/export_safe.py ayannotfound__Sentry/best.pt sentry-26s
     cp storage/processed/phase4_export/sentry-26s.* models/plate/

   Checked: inside the sandbox, the network rebuilt from the
   plain files gave output identical to the original. In the
   main environment on the GPU it found the same plates as the
   original did in the sandbox on 916 of 917 crops; the one
   difference sat on the confidence threshold.

   Check it again:
     uv run python tools/plate_detector_eval/verify_safe_model.py sentry-26s

   Also added to the main environment for this: safetensors
     uv add safetensors

 DOCKER (already on the machine, not installed by this project)
   Checked   : 2026-11-06
   Versions  : Docker 29.9.3, Docker Compose v5.7.0
   Notes     : Native engine inside Ubuntu, not Docker Desktop.
               The WSL user is in the docker group, so no
               sudo is needed.

 BACKEND PACKAGES (main environment)
   Installed : 2026-11-07 (Phase 8)
   Versions  : FastAPI 0.162.0 (pinned exactly), NiceGUI 4.0.0,
               SQLAlchemy 2.1.8, Alembic 1.20.1, psycopg 3.3.8
               (with psycopg-binary). PyTorch 2.14.1+cu126
               unchanged; the GPU check still passes.

   Install (in WSL):
     cd /mnt/c/Users/ontashai/Desktop/tracko-anpr
     export UV_LINK_MODE=copy
     uv add "fastapi==0.162.0" nicegui sqlalchemy alembic "psycopg[binary]"

 POSTGRESQL 18 (Docker container inside WSL)
   Started   : 2026-11-07 (Phase 8)
   Image     : postgres:18 (PostgreSQL 18.6 at the time)
   Container : tracko-anpr-postgres, port 127.0.0.1:5432
   Data      : named Docker volume tracko-anpr_postgres_data,
               mounted at /var/lib/postgresql inside the
               container (the postgres:18 image's path)
   Config    : docker-compose.yml at the project root; the
               credentials come from .env (git-ignored; copy
               .env.example and set POSTGRES_PASSWORD).

   Start (in WSL):
     cd /mnt/c/Users/ontashai/Desktop/tracko-anpr
     cp .env.example .env        # then set a real POSTGRES_PASSWORD
     docker compose up -d
     docker compose ps           # wait for "healthy"

   Create or update the tables:
     uv run alembic upgrade head

   Check it:
     uv run tracko-anpr db-status

   Verified 2026-11-07: migrate up, down and up again on the
   empty database; `alembic check` finds no difference
   between the models and the database; the rows survive
   `docker compose down` followed by `up` (the volume keeps
   them); with the container stopped, `tracko-anpr process`
   stops with a clear message before doing any work.


══════════════════════════════════════════════════════════════
 FINAL EXECUTION FLOW
══════════════════════════════════════════════════════════════

 RECORD VIDEO
      ↓
 NICEGUI UPLOAD
      ↓
 FASTAPI
      ↓
 PROCESSING WORKER
      ↓
 OPENCV / FFMPEG
      ↓
 YOLO26m
      ↓
 TRACKTRACK
      ↓
 ORIGINAL VEHICLE CROP
      ↓
 YOLO26s
      ↓
 AWIROS-ANPR-OCR
      ↓
 MULTI-FRAME VALIDATION
      ↓
 POSTGRESQL + FILE STORAGE
      ↓
 ANNOTATED MP4 GENERATION
      ↓
 FASTAPI RESULTS
      ↓
 NICEGUI DASHBOARD
      ↓
 C-SUITE LEADERSHIP DEMONSTRATION


 TOTAL:
   3 AI Models
   1 Tracking Algorithm
   1 Backend (FastAPI 0.162.0)
   1 Frontend (NiceGUI)
   1 Database (PostgreSQL 18 in Docker)
   1 Video Processing Worker
   1 NVIDIA GeForce RTX 4070 Ti SUPER GPU (16 GB VRAM)
══════════════════════════════════════════════════════════════


══════════════════════════════════════════════════════════════
 MODELS AND ALGORITHMS IN THE SYSTEM
══════════════════════════════════════════════════════════════

 This Indian Automatic Number Plate Recognition (ANPR) system
 uses 3 main Artificial Intelligence (AI) models, plus
 1 tracking algorithm.

 #  Component      Model / Algorithm Purpose
 ────────────────────────────────────────────────────────────
 1  Vehicle        YOLO26m           Detect cars, motorcycles,
    detection                        buses, and trucks

 2  Vehicle        TrackTrack        Assign and maintain
    tracking                         vehicle tracking
                                     identifiers

 3  Number plate   YOLO26s (Indian   Locate number plates
    detection      fine-tuned)

 4  Text           Awiros-ANPR-OCR   Read vehicle registration
    recognition    (PP-OCRv5)        numbers
══════════════════════════════════════════════════════════════


══════════════════════════════════════════════════════════════
 MEASURED PERFORMANCE — DETECTION AND TRACKING (2026-11-06)
══════════════════════════════════════════════════════════════

 YOLO26m with TrackTrack, input size 1536, FP16, on full
 2-minute test clips. "Whole run" here is tracking plus
 rendering the annotated video only; the full pipeline with
 plates is measured in the next section.

 Clip format         Tracking      Whole run    Whole run
                     (frames/s)    (frames/s)   vs real time
 ────────────────────────────────────────────────────────────
 1080p, 29.97 FPS    48            25           0.83x
 1080p, 60 FPS       50            28           0.47x
 2K, 30 FPS          31            16           0.52x
 2K, 59.94 FPS       35            18           0.28x

 Memory at peak: about 350 MiB of GPU memory (PyTorch) and
 2 GB of RAM.

 Every annotated video matched its input exactly in
 resolution, frame rate and frame count.

 Run it:
   uv run tracko-anpr track videos/clips/<video>/<piece>.mp4
══════════════════════════════════════════════════════════════


══════════════════════════════════════════════════════════════
 MEASURED — FULL PIPELINE, END TO END (2026-11-06)
══════════════════════════════════════════════════════════════

 The whole pipeline on two complete 2-minute clips: vehicle
 detection and tracking, plate detection, reading, validation
 and the annotated video with plates.

                          kochi_part02     mavoor_part02
                          2K, 59.94 FPS    1080p, 60 FPS
 ────────────────────────────────────────────────────────────
 Frames                   7,250            7,200
 Tracks                   266              245
 Count as vehicles        173              183
   too brief or too far   84               59
   camera car             0                0
   same vehicle again     9                3
 Car / Motorcycle         85 / 69          70 / 46
 Bus / Truck              5 / 14           14 / 53
 Plates examined          687              431
 Confirmed                44               13
 Unconfirmed              102              95
 Not detected             27               75
 Recognition coverage     25.4%            7.1%

 Time (seconds), two runs of each clip:
 Detection and tracking   222 to 315       167 to 248
 Plate detection          20 to 22         13 to 14
 Reading (with start-up)  23 to 24         19 to 23
 Validation               under 0.1        under 0.1
 Annotated video          193 to 225       143 to 147
 Total                    484 to 586       372 to 429
 Compared with real time  0.21x to 0.25x   0.28x to 0.32x

 • Both annotated videos matched their inputs exactly in
   resolution, frame rate and frame count.
 • GPU memory: 350 MiB peak for PyTorch in the main process;
   the reader is a separate process (about 3.8 GB in all,
   measured in Phase 5).
 • The second run of each clip was slower in detection and
   tracking although that code had not changed. The cause was
   not found; Phase 7 measures speed again over more clips.
 • Over half of the video-writing time is spent finding each
   plate again in every frame so that it can be outlined
   (156 of 225 seconds at 2K). This is the first place to
   look if the full-length videos take too long.
 • Coverage is far higher at 2K than at 1080p, as the plate
   detector comparison predicted: plates under 60 px wide are
   almost never read. Coverage is not accuracy.

 CHECKED BY EYE
 • Four confirmed numbers looked like misreadings because
   they are short (KL39P77, KL361375, TN062264, KL452960).
   All four are correct: the plates really say that.
 • Two numbers were confirmed on two vehicles at once. In
   both cases a vehicle's box overlapped a smaller vehicle
   and picked up its plate (a van and the car ahead of it; a
   car and a motorcycle in front of it). Fixed by giving a
   plate to the smallest vehicle box containing its centre
   (refined on 2026-11-07, see "Whose plate it is");
   after the fix the car ahead holds its number with 10
   agreeing frames and no number is confirmed twice at once.
 • Known limit of that rule: when a distant vehicle's box
   lies inside a near vehicle's box right at the plate, the
   reading can go to the distant one. Seen once (three
   readings of a motorcycle's plate went to a car behind
   it); it caused no wrong confirmation.
 • Not yet done: checking every confirmed number against its
   plate image. That needs the hand-labelled set listed under
   FUTURE IMPLEMENTATION.

 Run it:
   uv run tracko-anpr process videos/clips/<video>/<piece>.mp4
══════════════════════════════════════════════════════════════


══════════════════════════════════════════════════════════════
 ACCEPTANCE RUN AND FROZEN SETTINGS (Phase 7, 2026-11-06)
══════════════════════════════════════════════════════════════

 One 2-minute clip from each of the eight source videos was
 run through the whole pipeline with the settings below, which
 are now frozen: changing any of them later means processing
 every demo video again. Memory was sampled from outside the
 program every two seconds, so it includes the reader process.

 Clip                Format         Tracks  Vehicles  Confirmed  Unconf.  Not det.  Coverage
 ──────────────────────────────────────────────────────────────────────────────────────────
 kochi-city_part05   1080p 29.97     303     196         5        138       53       2.6%
 kochi_part02        2K    59.94     266     173        44        102       27      25.4%
 kozhikode_part03    2K    30        187     123        10         91       22       8.1%
 kozikode-4k_part03  1080p 30        167     116         5         81       30       4.3%
 mavoor_part02       1080p 60        245     183        13         95       75       7.1%
 ooty_part03         1080p 50        115      63         2         42       19       3.2%
 trafiic_part01      1080p 29.97     182      91         3         43       45       3.3%
 truck_part02        1080p 60        430     216         0        108      108       0.0%

 "Vehicles" is tracks that count (Total Vehicles); coverage is
 confirmed ÷ vehicles and is not accuracy. ooty and truck are
 after the cabin rule below (7 and 8 cabin tracks removed).

 Time in seconds, and speed:

 Clip                Track  Plates  Read  Video  Total  Track fps  Overall fps  vs real time
 ──────────────────────────────────────────────────────────────────────────────────────────
 kochi-city_part05    114     13     31     67    225      45         16.0        0.53x
 kochi_part02         252     23     22    201    499      34         14.5        0.24x
 kozhikode_part03     154     18     23    106    301      30         12.4        0.41x
 kozikode-4k_part03   107     11     25     63    206      44         17.6        0.59x
 mavoor_part02        186     14     24    129    353      46         20.4        0.34x
 ooty_part03          157     10     22    104    294      47         20.2        0.40x
 trafiic_part01        99      9     21     66    195      48         18.9        0.63x
 truck_part02         169     14     23    102    308      50         23.4        0.39x

 "Read" includes about 20 seconds of reader start-up. Of the
 "Video" time, 15 to 127 seconds went on locating plates to
 outline them (more plates in view, more time).

 MEMORY
 • Main process: PyTorch's GPU peak was 1,646 MiB on every
   clip (the plate detector on a batch of 32 cut-outs is the
   high point, not the vehicle detector), and 2.2 to 2.5 GB
   of RAM.
 • Whole machine while a run was going: GPU use rose by
   3.4 GB over idle on every clip (main process plus the
   reader), and RAM by 2.9 to 4.0 GB. WSL has 15 GB, so a
   run leaves room for PostgreSQL and the web app.

 WHAT THE FULL-LENGTH VIDEOS WOULD TAKE
 At each clip's measured overall speed, applied to the whole
 video it was cut from:

 Video          Format         Length    Estimated processing
 ────────────────────────────────────────────────────────────
 trafiic        1080p 29.97     4.6 min      7 min
 truck          1080p 60        5.2 min     14 min
 mavoor         1080p 60       10.5 min     31 min
 ooty           1080p 50       14.1 min     35 min
 kochi-city     1080p 29.97    25.6 min     48 min
 kochi          2K    59.94    13.3 min     55 min
 kozikode-4k    1080p 30       40.6 min     69 min
 kozhikode      2K    30       40.6 min     98 min
 All eight together                         about 6 hours

 Estimates, not measurements: a full video is one job, and
 the clips show run-to-run variation of about 20% in the
 tracking stage with unchanged code. kozhikode and
 kozikode-4k are the same footage; the 2K copy found twice
 the confirmed plates (10 against 5) at 1.4 times the cost.

 FROZEN SETTINGS (results.json "settings" records them per run)
 Vehicle detector    yolo26m.pt, input 1536, FP16, confidence 0.1,
                     four classes
 Tracker             TrackTrack, lost tracks kept 1.0 s (frames
                     scaled to the video's frame rate)
 Plate detector      sentry-26s.safetensors, input 640,
                     confidence 0.25
 Frames per vehicle  6, at least 0.15 s apart, where the box
                     is largest and not cut off
 Vehicle cut-out     4% margin around the box
 Counts as vehicle   followed 0.5 s or more, at some point 6%
                     of the frame height or taller
 Camera car          bonnet: 10 s or more, 25% of the frame
                     wide, on the bottom edge 80% of the time;
                     cabin: 3 s or more, 40% wide, another
                     vehicle wholly inside it in 10% of frames
 Reading threshold   readings under 0.6 confidence do not vote
 Confirmed           valid format, 2 or more agreeing frames,
                     60% of the confidence-weighted votes, one
                     reading 0.85 or higher; no number held by
                     two vehicles in view at once
 Plate formats       standard (state code, 1 to 2 district
                     digits, 0 to 3 series letters without I
                     or O, 1 to 4 digits) and BH series

 CHECKED BY EYE
 • Camera car, bonnet shape: trafiic_part01 flagged one
   track, the camera car's white bonnet in the bottom-right
   corner. Correct.
 • Camera car, cabin shape (new in Phase 7): in ooty and
   truck the camera is inside the cab, and the detector
   boxed the door pillar, window and mirror as a "car" for
   up to 39 seconds at a time, seven and eight tracks in all.
   None rested on the bottom edge, so the bonnet rule missed
   them. The cabin rule removed exactly those tracks and no
   real vehicle, checked track by track and in the videos.
 • truck_part02 confirmed nothing because its plates are too
   small to read from a high cab: the median plate found was
   38 px wide and 78% were under 60 px, where the reader
   almost never succeeds. The 25 confident readings disagree
   with each other. That is the known limit of small plates,
   not a fault in the pipeline.
 • Low coverage on dashcam footage is expected: most tracked
   vehicles are seen from the side, cut off by the frame
   edge, or too far away to show a readable plate.

 GATE C — which full videos go in the demo is the user's
 decision, made with the table above.

 FOOTAGE CHANGED ON 2026-11-07. The dashcam videos and their
 2-minute pieces above were removed by the user and replaced
 with static-camera phone recordings (the user and a
 relative filming the roadside): clear.mp4 (4K, 60 FPS,
 2.4 min), rope.mp4 (4K, 57 s), zoomed-in.mp4 (1080p,
 1.8 min) and, at first, three recordings held upright
 (portrait.mp4, portrait-new.mp4, portrait-narzo.mp4), which
 the user removed later the same day: no portrait footage
 in the demo. Later still on 2026-11-07 the user deleted
 rope.mp4 as well, so the demo set is clear and zoomed-in;
 rope's rows and result files were removed, and its figures
 below stay as measurements only. The settings stay frozen.
 First 10-second runs on them (Phase 10 smoke check):
   • The upright recordings carry a "rotate -90" tag. OpenCV
     applies it, so probe_video now reports the upright size
     (2160x3840) and the annotated video comes out upright.
     HEVC decodes without any change.
   • 4K is slow to decode: detection and tracking managed
     about 10 frames/s on clear.mp4 (60 FPS) and 5 to 6 on
     the upright ones, against 30 to 50 on the 1080p and 2K
     dashcam clips, because decoding 50 Mbit/s 4K frames is
     CPU work. A full 4K video is likely to take 5 to 10
     times its own length; Phase 14 measures the real
     figures when the demo videos are processed.
   • Static cameras have no camera car, and plates are seen
     head-on, so coverage should be higher than on dashcam
     footage; 10 seconds is too little to say.
══════════════════════════════════════════════════════════════


══════════════════════════════════════════════════════════════
 HOW TO MEASURE REAL ACCURACY (procedure; run on zoomed-in and kdy,
 see FIRST and SECOND ACCURACY MEASUREMENT)
══════════════════════════════════════════════════════════════

 WHY COVERAGE IS NOT ACCURACY

 Coverage answers "of the vehicles we counted, how many ended
 with a confirmed number?" (48 of 251 = 19.1% on the demo
 set). It says nothing about whether those 48 numbers are
 right, whether the 203 others had readable plates we missed,
 or whether 251 is the true number of vehicles. Accuracy
 needs a reference the system did not produce: a person
 writing down the truth for a sample of vehicles. That
 reference is the "hand-labelled set" (ground truth).

 Three questions, three different measurements:

   1. Reading accuracy    When the system confirms a number,
                          how often is it the right number?
   2. Reading recall      Of the vehicles whose plate a person
                          can read in the video, how many did
                          the system confirm correctly?
   3. Counting accuracy   Is "Total Vehicles" right? Vehicles
                          missed, counted twice (track breaks),
                          or not vehicles at all.

 Each needs its own labels. Do 1 first: it is the cheapest
 and the one leadership will ask about ("is that number
 real?").

 WHAT YOU NEED

   • A processed video (its storage/processed/<name>/ folder
     and database rows exist).
   • The History page's Export CSV, or
     storage/processed/<name>/results.json, which lists every
     counted vehicle with its track id, time, status and the
     number the system settled on.
   • The crops under storage/vehicle_crops/<name>/T<id>.jpg
     and storage/plate_crops/<name>/T<id>_f<frame>.png, which
     is what a person looks at to read the truth.
   • The annotated video, to check a vehicle in context when
     the crops are not enough.
   • A spreadsheet or CSV editor. Nothing else.

 HOW BIG A SAMPLE

 Accuracy from n checked items has a margin of error of about
 ±1/√n at the usual 95% confidence: 30 items → ±18 points,
 100 → ±10, 400 → ±5. For a first answer, label every
 confirmed vehicle of the demo set (48 today) plus 100
 unconfirmed or not-detected ones; report the margins with
 the numbers. Never quote accuracy from fewer than 30 items
 without the margin beside it.

 STEP 1 — EXPORT THE SYSTEM'S ANSWERS

   From the dashboard: Detection History → choose the video
   (or all) → Export CSV. Or, on the command line:
     curl -s "http://localhost:8080/api/detections/export.csv?video_id=<id>" > labels/<name>_system.csv
   Columns: video, track, vehicle_type, first_seen_s,
   last_seen_s, registration_number, status, confidence,
   agreeing_frames, readings, reason, demo_registry_match.

 STEP 2 — MAKE THE LABEL SHEET

   Create labels/<name>_truth.csv with these columns, one
   row per vehicle track from step 1 (copy track, vehicle_type,
   first_seen_s, registration_number and status across as the
   system's answer; add the empty label columns):

     track            T<id>, from the export
     system_number    what the system said (may be empty)
     system_status    confirmed / unconfirmed / not_detected
     true_number      what a person reads from the plate crop
                      and the video; empty if no plate is
                      legible to a human either
     plate_legible    yes / partly / no (partly = a human can
                      read some characters but not all)
     true_type        Car / Motorcycle / Bus / Truck / Other,
                      if it differs from the system's type
     is_vehicle       yes / no (no = the track is not a
                      vehicle: a sign, a shadow, a person)
     duplicate_of     T<id> of an earlier track if this is the
                      same vehicle counted again; else empty
     labelled_by      who read it, and whether two readers
                      agreed
     label_doubt      yes when the labeller was unsure
     note             anything odd (cut off, night, two-line
                      plate, glare)

   Keep the labels/ folder in git: it is small text, and the
   point is that the measurement can be repeated after any
   change to the pipeline.

 STEP 3 — LABEL, WITH RULES WRITTEN DOWN FIRST

   • Read the plate crop(s) first, then the vehicle crop,
     then the video at first_seen_s if still unsure. Write
     the number exactly as printed, without spaces, upper
     case (KL07AB1234). If one character is unreadable, write
     it as ? and set plate_legible = partly.
   • Do not look at system_number before writing true_number
     (cover the column, or label from the crops folder by
     file name). Reading the system's answer first makes a
     person agree with it; that is the main way such
     measurements go wrong.
   • Two people labelling the same 30 vehicles independently,
     then comparing, tells you how reliable the labels
     themselves are. Disagreements are usually two-line
     plates and 0/O, 8/B, 1/I.
   • Label every row of the sample, including the ones the
     system got nothing for: those are where recall is
     decided.

 STEP 4 — COUNT

   Over rows with is_vehicle = yes and duplicate_of empty:

   Reading accuracy (precision of confirmed numbers)
     correct    = confirmed and system_number == true_number
     wrong      = confirmed and system_number != true_number
     accuracy   = correct / (correct + wrong)
     Report also the character error rate of the wrong ones
     (how many characters differ): one wrong character is a
     very different failure from a made-up number.

   Reading recall (over plates a human can read)
     readable   = rows with plate_legible = yes
     found      = readable rows that are confirmed and correct
     recall     = found / readable
     Also list readable rows that ended unconfirmed with the
     right number: those are the system being cautious, not
     wrong, and say whether the thresholds are too strict.

   Unconfirmed, what are they?
     Of the unconfirmed rows, how many had the right number as
     system_number (the guess was right but unsupported), how
     many wrong, how many had no legible plate at all. This
     tells whether loosening the rules would gain true
     numbers or let errors through.

   Counting accuracy (needs the extra labels)
     false tracks   = is_vehicle = no
     duplicates     = duplicate_of not empty
     misses         = vehicles a person sees in the video that
                      have no track at all. Finding these means
                      watching the video and counting, at least
                      for one or two minutes; note the time
                      window used.
     counted vehicles vs true vehicles in that window, with
     the three error kinds listed separately.

   Type accuracy
     rows where true_type is filled and differs from the
     system's type, as a share of all labelled vehicles.

   A spreadsheet does all of this with COUNTIFS; a short
   script (tools/measure_accuracy.py, with
   tools/label_contact_sheets.py for blind crops) produces
   the same table so
   it can be re-run after any change.

 STEP 5 — WRITE IT UP HONESTLY

   Report, for each video and overall:
     • n labelled, n confirmed, accuracy of confirmed numbers
       with its ± margin
     • recall over human-readable plates with its margin
     • the list of wrong confirmations, each with crop, system
       number, true number (these are the ones to study)
     • counting errors by kind, if measured
     • who labelled, when, with which rules, and the git
       commit of the pipeline that produced the answers
   Put the table in this file next to the acceptance run, and
   only then consider showing an accuracy figure on the
   Analytics page, labelled with its sample size and date.
   Until a label sheet exists the dashboard must keep saying
   "coverage, not accuracy".

 WHAT TO EXPECT, FROM WHAT IS KNOWN SO FAR

   • The OCR smoke test (below) read all 16 clearly legible
     plates correctly out of 16, so accuracy of confirmed
     numbers on legible plates should be high; the acceptance
     run found the confirmation rules reject most single-frame
     and low-confidence readings, which is what keeps wrong
     numbers out.
   • Recall will be the weak figure: most vehicles are seen
     from the side, cut off, or with plates under 60 px wide.
     That is a camera placement question more than a model
     question, and the measurement will show it.
   • The known failure shapes to look for in the wrong list:
     a neighbour's plate credited to a vehicle whose box
     encloses it (Phase 6), two-line plates, 0/O and 8/B,
     and the state code misread (a Kerala plate once read as
     DL at 0.86 confidence).

 WHEN THE PIPELINE CHANGES

   The settings are frozen for the demo. After the demo, any
   change (thresholds, a new plate detector, a reader
   fallback) is judged by re-running the same label sheet:
   process the same videos, export, join on track and time
   (track ids change between runs, so match on first_seen_s
   within a second and vehicle type), recount. A change is
   worth keeping only if accuracy does not fall and recall
   rises, or the other way round, by more than the margins.
══════════════════════════════════════════════════════════════


══════════════════════════════════════════════════════════════
 OCR SMOKE TEST — AWIROS-ANPR-OCR (2026-11-06)
══════════════════════════════════════════════════════════════

 Question: can the Awiros model read number plates from this
 project's own footage?

 HOW IT WAS TESTED

 448 plate crops were cut from four test clips, using the
 vehicle boxes from the tracking pass and the two ONNX plate
 detectors (ONNX files cannot run code, so they are safe to
 load). 40 crops were picked to cover large and small,
 one-line and two-line plates, and read by eye.

 FINDING 1 — THE REFERENCE SCRIPT USES THE WEAKER DECODER

 The model has two decoders. Awiros's own test.py reads the
 CTC decoder. On Awiros's own nine sample plates that gives
 5 right and 4 with one character missing, including all
 three two-line plates. Their published results file shows
 the same misses.

 The other decoder (the attention, or NRTR, head) writes the
 text one character at a time. It reads two-line plates
 correctly. This project uses it.

 FINDING 2 — DRAWING THE PLATE WIDER HELPS

 Widening the plate image by 1.5 before reading fixes
 characters lost at the right edge.

 RESULTS, PLATES CLEARLY LEGIBLE BY EYE

                               Awiros's 9     Our 16
                               samples        plates
 ────────────────────────────────────────────────────────────
 Reference script (CTC)        5 right        11 right
 CTC, plate widened            7 right        13 right
 Attention, plate widened      8 right        16 right
 (what this project uses)

 Of our 16, 13 are one-line and 3 are two-line; the chosen
 method read all of both. These are small samples: enough to
 choose a method, not enough to state an accuracy figure.

 WHAT ELSE THE TEST SHOWED

 • Unreadable plates: the model answers with a fixed word
   meaning "cannot read", which the reader turns into an
   empty, unreadable result.
 • Things that are not plates: the model still writes a
   plausible plate number (for example KA02CM4231), but with
   confidence about 0.2 to 0.3. Good readings sit near 0.92.
   A confidence threshold is required; confidence alone is
   not proof of a correct reading.
 • Plate size decides everything. Share of crops giving a
   confident, plate-shaped reading:

     Plate width          Crops   Confident readings
     under 60 px            93    12%
     60 to 99 px           153    33%
     100 to 149 px          93    47%
     150 px and over       109    68%

 • State code slips: one Kerala plate was read as DL... at
   confidence 0.86. Multi-frame validation has to handle
   this.
 • Speed: about 10 ms per plate on the GPU, after about 15 s
   to load the model.

 Run it (inside the ocr folder):
   uv run anpr-ocr read <folder of plate images>

 The 40 crops with their readings are in
 storage/processed/phase3_ocr_smoke_sheet_1.jpg and _2.jpg.
══════════════════════════════════════════════════════════════


══════════════════════════════════════════════════════════════
 CUDA AND GPU LIBRARY COMPATIBILITY (CHECKED 2026-11-06)
══════════════════════════════════════════════════════════════

 WHY THE OCR RUNS IN A SEPARATE ENVIRONMENT

 The conflict is over one NVIDIA library, cuDNN
 (package name nvidia-cudnn-cu12):

 Package                    Version         cuDNN it requires
 ────────────────────────────────────────────────────────────
 PyTorch (torch)            2.14.1+cu126    exactly 9.10.2.21

 PaddlePaddle               3.3.1 (CUDA     exactly 9.5.1.17
 (paddlepaddle-gpu)         12.6 build)

 Only one version of cuDNN can be installed in an
 environment, and each package demands a different exact
 one, so uv refuses to install both together.


 PYTORCH BUILDS PER CUDA VERSION

 The latest PyTorch is 2.15.0, and its newest CUDA build is
 for CUDA 13.4.

 Newest PyTorch available for each CUDA version
 (Linux, Python 3.12), from PyTorch's download site:

 CUDA version   Newest PyTorch build
 ────────────────────────────────────────────────────────────
 13.4           2.15.0
 13.2           2.15.0 (the default from PyPI)
 13.0           2.14.1
 12.9           2.13.0
 12.8           2.11.0
 12.6           2.14.1

 The installed driver (572.16) supports up to CUDA 12.8. So
 without a driver upgrade the newest PyTorch that can run is
 2.14.1, using its CUDA 12.6 build. PyTorch 2.15.0 exists
 only for CUDA 13.2 and 13.4, which need a newer driver.
══════════════════════════════════════════════════════════════


══════════════════════════════════════════════════════════════
 COMPETITORS — TOP ALTERNATIVES TO YOLO IN 2026
══════════════════════════════════════════════════════════════

 These are actual alternative detection architectures,
 not renamed YOLO models.

 For reference only: they are not part of the selected
 pipeline, which uses YOLO26m and YOLO26s.


 1. RF-DETR                                    (Top contender)

   Roboflow's Real-Time Detection Transformer offers
   excellent accuracy and fast inference. It is designed for
   fine-tuning on custom datasets, making it a strong
   candidate for Indian vehicles and plates.

   Best for : Accuracy-focused vehicle and plate detection.
   Official : https://github.com/roboflow/rf-detr


 2. RT-DETR

   Baidu's Real-Time Detection Transformer uses an efficient
   transformer architecture for fast object detection.
   RT-DETRv2 is a mature option with publicly available
   pretrained models and code.

   Best for : Real-time vehicle detection and custom
              fine-tuning.
   Official : https://github.com/lyuwenyu/RT-DETR


 3. D-FINE

   A high-performance real-time transformer detector that
   focuses on accurate object localization. Particularly
   interesting when precise bounding boxes matter.

   Best for : Accurate vehicle localization and experimenting
              with small plate detection.
   Official : https://github.com/Peterande/D-FINE


 4. RTMDet

   A fast single-stage detector developed by OpenMMLab. It is
   a convolutional alternative rather than a detection
   transformer, and it supports real-time deployment.

   Best for : Low-latency vehicle detection and edge
              deployment experiments.
   Official : https://github.com/open-mmlab/mmdetection
              (configs/rtmdet)


 LIBRARY AVAILABILITY

 Model     Full name             Python library   Available in
                                                  Ultralytics?
 ────────────────────────────────────────────────────────────
 YOLO26    You Only Look Once    ultralytics      Yes

 RT-DETR   Real-Time Detection   ultralytics      Yes
           Transformer

 RF-DETR   Roboflow Detection    rfdetr           Not natively
           Transformer
══════════════════════════════════════════════════════════════


══════════════════════════════════════════════════════════════
 ALTERNATIVES — ALL SIX TRACKING ALGORITHMS IN ULTRALYTICS
══════════════════════════════════════════════════════════════

 For reference only: TrackTrack is the tracker selected for
 this POC. The others are available as alternatives.

 Tracker         Available?   Main strength
 ────────────────────────────────────────────────────────────
 TrackTrack      Yes          Crowded scenes, occlusion,
                              fewer duplicate track IDs

 BoT-SORT        Yes          Stable tracking with appearance
                              matching and camera-motion
                              compensation

 ByteTrack       Yes          High-speed tracking with low
                              computational overhead

 Deep OC-SORT    Yes          Complex motion, occlusion and
                              appearance matching

 OC-SORT         Yes          Irregular motion without
                              requiring appearance
                              recognition

 FastTracker     Yes          Lightweight tracking with
                              occlusion handling

 Original SORT   No           Basic Kalman-filter tracking;
                              requires external
                              implementation
══════════════════════════════════════════════════════════════
```
