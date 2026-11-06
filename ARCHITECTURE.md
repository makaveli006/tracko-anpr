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

 Source          : Mobile-recorded Indian road traffic videos
 Camera          : Stationary roadside OR moving vehicle
 Resolution      : Any, read from each video
                   (1920 × 1080 suggested)
 Frame Rate      : Any, read from each video
                   (30 FPS suggested)
 Video Codec     : H.264
 Container       : MP4
 Bitrate         : ~6 Mbps (recommended starting point)
 Duration        : Initially 1–3 minutes per video

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
   GET  /api/jobs/{id}
   GET  /api/videos/{id}/results
   GET  /api/videos/{id}/detections
   GET  /api/videos/{id}/analytics
   GET  /api/videos/{id}/annotated

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

                         │
                         ▼

══════════════════════════════════════════════════════════════
 12. ANNOTATED VIDEO GENERATION
══════════════════════════════════════════════════════════════

 Tools           : OpenCV + FFmpeg
 Output          : H.264 MP4
 Resolution      : Same as the input video
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

   Detect auto-rickshaws and other Indian vehicle types.
   The POC keeps four classes (car, motorcycle, bus, truck)
   because the stock YOLO26m model knows only those, so
   other vehicle types may be missed or mislabelled.

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
