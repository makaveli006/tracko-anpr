# Tracko ANPR: project notes for interviews

A personal proof of concept for reading Indian number plates from recorded video, built with AI assistance (Claude Code). This page covers what it does, what was hard, how it would run in production, and how to answer interview questions about it.

**Figures:** "measured" means this project produced the number. Anything marked "estimate" was not measured.

---

## 1. Project summary and results

**What it does:** you upload an MP4 of road traffic. The system finds each vehicle, follows it through the video, finds its number plate, reads it, and checks the reading across several frames. It then shows the results in a dashboard: an annotated video, a searchable history, charts, and a fictional registry to match numbers against.

**How one video flows through it:**

1. Upload the video; the web app adds a job to a queue.
2. A separate worker process picks the job up.
3. YOLO26m finds vehicles and TrackTrack follows them.
4. A YOLO26s model finds the plate on each vehicle's best frames.
5. A PaddlePaddle OCR model reads the plate.
6. Validation compares the readings across frames and confirms a number only if they agree.
7. Results go to PostgreSQL and files, and an annotated video is rendered.

**Built with:** Python 3.12, PyTorch, Ultralytics, PaddlePaddle, OpenCV, FFmpeg, FastAPI, NiceGUI, PostgreSQL 18 in Docker, SQLAlchemy and Alembic. It ran on one RTX 4070 Ti SUPER (16 GB) under WSL 2, with 286 automated tests.

**Measured results on the main video** (`zoomed-in`: 1080p, 1 minute 50 seconds, processed in about 3.5 minutes):

| Measure | Result |
|---|---|
| When the system was sure of a number, it was right | 15 of 16 (94%, ±25 points) |
| Plates a person could read that it confirmed correctly | 15 of 28 (54%, ±19 points) |
| Vehicle type correct | 27 of 32 (84%) |
| Vehicles shown against real vehicles | 59 shown, 32 real (before the parked-vehicle fix; a test suggests about 42 after it) |

Sixteen confirmed numbers is a small sample, so always quote "15 of 16", never "94% accurate". Results also depend heavily on footage: on a harder street video (`kdy`), a person could fully read only 10 plates out of 87 vehicles, and the system confirmed 3 of 125 entries, all 3 right.

**Resume lines you can use:**

- Built an offline number plate recognition system for Indian traffic video, with detection, tracking, OCR, multi-frame validation and a seven-page dashboard, developed with AI assistance.
- Measured accuracy against blind hand labels: 15 of 16 confirmed numbers correct on the main test video, with the sample size stated.
- Cut 4K processing time by about 30% (979 s to 667 s) and output size by 70% by removing repeated work from the render stage, with identical results.

---

## 2. Constraints

- **Recorded video only.** MP4 uploads, no live cameras. It's a proof of concept, not a live system.
- **One machine.** One 16 GB GPU, and WSL saw 15 GB of RAM. Everything ran on it: models, database and web app.
- **Driver limit.** The NVIDIA driver stayed at CUDA 12.8, which ruled out the default PyTorch build.
- **Libraries that can't share an environment.** PyTorch and PaddlePaddle demand different versions of the same NVIDIA library.
- **Phone footage.** No fixed camera, infrared light or control over angle, and the camera often moved.
- **Four vehicle classes.** The stock model knows car, motorcycle, bus and truck. Auto-rickshaws have no class of their own.
- **No custom training.** Pretrained models were used, chosen by testing, to stay inside the time available.
- **Fictional registry.** No real registration data, by design.
- **Deadline.** Late testing used one video at a time, and the sample sizes are small because of it.
- **Licences.** YOLO26 is AGPL-3.0, and the chosen plate model has no licence file. Fine for a personal project, not for selling.

---

## 3. Challenges faced

| Challenge | What happened | What fixed it |
|---|---|---|
| PyTorch and PaddlePaddle conflict | Each pinned a different cuDNN version, so one environment was impossible | Ran the reader as a separate process with its own environment, talking over JSON lines |
| OCR dropped characters | The reference method lost a character on almost every two-line plate | Switched to the model's attention decoder and widened the plate image: 16 of 16 test plates read, against 11 |
| Plates given to the wrong vehicle | Boxes overlap in traffic. A van's box showed the car ahead's plate, and later a half-hidden bus took a car's plate | Enclosed box wins; if two boxes only partly overlap, the nearer vehicle wins |
| Parked vehicles counted again and again | One scooter was counted 19 times, because the tracker lost it each time traffic passed | Merged tracks by camera-corrected position and colour. This was a partial fix: 167 fell to 125 on `kdy`, for 87 real vehicles |
| Phone cameras move | A simple "same spot" rule wrongly merged 23 to 33 vehicles | Measured the camera's movement and removed it before comparing positions |
| Confidence is not correctness | One Kerala plate was read as `DL...` at 0.86 confidence | Required agreement across frames, not a single confident reading |
| A damaged file "succeeded" | A truncated MP4 finished with 7 frames and no vehicles | The job now fails if under 90% of the expected frames can be read |
| Slow 4K processing | The render stage re-ran the plate detector on every frame and encoded at 4K | Reused existing plate boxes and encoded at 1080p: 979 s to 667 s, file 770 MB to 214 MB, same results |
| Untrusted model weights | Downloaded `.pt` files can run code when loaded | Scanned all 14 candidates, ran them in a Docker container with no network, and re-saved the chosen one in a safe format |
| Short plates looked wrong | Numbers like `KL39P77` looked like misreads | Checked them against the images: they were real, so the format rule was widened |
| Measuring honestly | The dashboard's "coverage" could be mistaken for accuracy | Kept the two apart, and measured accuracy with blind hand labels committed before any comparison |
| A broken environment | A tool run from Windows wiped the Linux environment partway through | Rebuilt it from the lock file in minutes, and recorded the rule |

---

## 4. Key design decisions

| Decision | Why | What it cost |
|---|---|---|
| Job queue in a PostgreSQL table, not Redis or Celery | One less service; `FOR UPDATE SKIP LOCKED` is enough at this size | Won't scale to high volumes |
| Worker separate from the web app | Long GPU work can't freeze the dashboard, and a crash stays contained | One more process to run |
| Two Python environments | The only way to run both model libraries on this driver | A process boundary and a protocol to maintain |
| Stages run one after another over the whole video | Knowing the whole track first picks better frames and allows validated labels | Slower than a single pass, and can't run live |
| Confirm a number only when frames agree | A wrong number is worse than no number | Many correct readings stay unconfirmed: 8 of 28 on the main video |
| Operator corrections stored beside the result | The system's answer stays intact, and corrections become labels | Two versions of a number to display |
| Files on disk, references in the database | Videos are too big for a database | Backups must cover both |
| Show coverage, never call it accuracy | Coverage says nothing about whether numbers are right | A less impressive-looking dashboard |
| One FastAPI and NiceGUI process | Simple for a proof of concept | Must be split up to scale |

---

## 5. Things we could do to improve

In priority order:

1. **Fix the vehicle count fully.** Stop losing parked vehicles in the tracker, using appearance matching (re-identification).
2. **Test readability on upload.** Today's check measures plate size only. It should also try reading sampled plates, so poor footage is caught in a minute.
3. **Measure properly.** Have people label a few hundred plates across all footage, to get a firm figure.
4. **Train on Indian plates.** Fine-tune the plate and OCR models on two-line, worn and hand-painted plates.
5. **Add Indian vehicle classes.** Auto-rickshaws caused 13 of 16 type errors on `kdy`.
6. **Use the readings more fully.** Combine readings across a parked vehicle's tracks, and review how strict the rules are: 8 correct readings were held back on the main video.
7. **Go faster.** Use GPU video decoding and batch inference. On 4K, CPU decoding is the main cost.
8. **Add integrations.** Send confirmed plates to other systems by webhook, with replay if the receiver is down.
9. **Make settings editable,** judged against the labelled set.
10. **Add direction-based counting,** to count entries and exits per lane.

---

## 6. How it would work in production

The biggest change is moving from uploaded files to live cameras. The system can't wait for a whole video, so decisions must be made as a vehicle leaves the frame.

1. **Cameras.** Fixed IP cameras, in line with traffic, with infrared light for night. Placement matters more than any model.
2. **Edge box near the cameras.** A small GPU unit receives the RTSP stream and decodes it on the GPU. Running AI on-site means only events cross the network, not video.
3. **Detect and track live.** A model optimised with TensorRT runs on the stream, and the tracker keeps each vehicle's best frames in memory.
4. **Read when the vehicle leaves.** The plate model and OCR run on those best frames, and validation decides on the number.
5. **Send an event.** A small message goes to a queue: number, confidence, time, camera, direction and plate image. If the network is down, the edge box holds events and sends them later.
6. **Central services.** Consumers save events to the database, store images in object storage, and check them against watch lists.
7. **Dashboard and alerts.** Operators see live events and search history, and people review doubtful reads.
8. **Learning loop.** Corrections become training data, and a new model is compared on a fixed test set before rollout, starting with a few cameras.
9. **Monitoring.** Track camera health, frames per second, queue delay, and read rate per camera. A drop in read rate usually means a dirty lens or a moved camera.

| Part | Proof of concept | Production |
|---|---|---|
| Input | Uploaded MP4 | Live RTSP cameras |
| Processing | Stage by stage over a file | Continuous, per vehicle |
| Queue | PostgreSQL table | Kafka |
| Storage | Local disk | Object storage with retention rules |
| Scale | One machine | Many edge boxes, central services |
| Users | No login | Login, roles, audit log |
| Models | Pretrained, fixed | Trained on own data, versioned |

---

## 7. Tools for production

These are recommendations. None of them were used in this project.

| Job | Tool | Why |
|---|---|---|
| Video pipeline | NVIDIA DeepStream | Built for many live streams on one GPU |
| Faster models | TensorRT, with ONNX export | Much faster inference on NVIDIA GPUs |
| Serving models | NVIDIA Triton | Runs and versions several models |
| Edge hardware | NVIDIA Jetson, or a small GPU server | Processes video near the camera |
| Event queue | Apache Kafka | Durable, and replays events after failures |
| Database | PostgreSQL with TimescaleDB | Keeps what works, adds time-series speed |
| Images | S3 or MinIO | Cheap storage with automatic deletion |
| Deployment | Docker, Kubernetes (K3s at the edge) | Rolling updates across many sites |
| Monitoring | Prometheus and Grafana | Metrics and alerts |
| Logs and errors | Grafana Loki, Sentry | Finding faults quickly |
| Labelling | CVAT or Label Studio | Building training sets |
| Model tracking | MLflow | Records which model ran and how it scored |
| Delivery | GitHub Actions, Terraform | Repeatable testing and deployment |
| Login and secrets | Keycloak, HashiCorp Vault | Roles, single sign-on, safe secrets |
| Dashboard | React with FastAPI | Scales better than a one-process server |

---

## 8. Cost and scaling estimates

**All figures here are rough estimates for planning, not measurements. Check current prices before using them.**

The one measured starting point: detection and tracking ran at about 48 frames per second at 1080p on one RTX 4070 Ti SUPER, with the model unoptimised.

| | 10 cameras | 100 cameras |
|---|---|---|
| GPUs (assuming 4 to 8 cameras each, using TensorRT and skipping some frames) | 2 | 15 to 25 |
| Network, if video is sent centrally (about 4 Mbit/s per camera) | 40 Mbit/s | 400 Mbit/s |
| Storing all video for one day (about 43 GB per camera) | about 430 GB | about 4.3 TB |
| Cloud GPU cost per month (assuming $400 to $700 per GPU) | $800 to $1,400 | $6,000 to $17,500 |

**What drives the cost:**

- Keep only events and plate images, not full video. That cuts storage by far more than any other choice.
- Process at the edge to avoid sending video over the network.
- For always-on cameras, buying hardware usually beats renting cloud GPUs over a few years.

**How it scales:** each camera is independent, so capacity grows by adding edge boxes. The central side handles small event messages, which are much lighter than video. The first bottleneck is GPU capacity per site, not the database.

---

## 9. Security, privacy and legal

This is general awareness, not legal advice. A real deployment needs a lawyer's review.

- **Plates are personal data.** A number plate links to a person, and tracking plates shows where people go. India's Digital Personal Data Protection Act, 2023 would apply.
- **Purpose and consent.** State why the data is collected, collect only what that purpose needs, and put up notices at the site.
- **Retention.** Delete automatically, for example non-matching plates after 30 days. The right period depends on the purpose.
- **Access control.** Real logins, roles, and an audit log of who searched for what. This proof of concept has none, because it runs on one machine.
- **Encryption.** Encrypt data in transit and at rest.
- **Real registration data.** Only through authorised government channels. This project uses fictional records and says so on every screen.
- **Human review.** A number can be wrong, as 1 of 16 was here. A person must check before any action against someone.
- **Licences.** YOLO26 is AGPL-3.0, so a closed commercial product needs an Ultralytics licence or a different model. The chosen plate model has no licence file, so it must be replaced or retrained. The OCR model is Apache-2.0.
- **Model file safety.** Load third-party weights only after scanning, in a sandbox, and keep them in a safe format.

---

## 10. Interview questions and simple answers

### About the project

**1. Tell me about this project.**
It reads Indian number plates from traffic video. You upload a video, and it finds each vehicle, follows it, reads the plate across several frames, and shows the result in a dashboard.
*Example: on a 1 minute 50 second roadside video, it took about 3.5 minutes and confirmed 16 numbers, 15 of them correct.*

**2. Why did you build it?**
To learn a full computer vision system from end to end, not just one model. It covers video, models, a database, background jobs, a dashboard and honest measurement.
*Example: most of the work wasn't the AI model. It was plates going to the wrong vehicle and parked cars being counted twice.*

**3. How much did you build yourself? Did you use AI?**
I built it with Claude Code. I set the goals, chose the architecture and tools, decided trade-offs, reviewed results and checked plates by hand. The AI wrote much of the code under that direction. I can explain how each part works and why it was built that way.
*Example: I chose the database, decided to keep models off the web server, and read plates by hand to check the accuracy results.*

**4. What are you most proud of?**
Measuring it honestly. It would have been easy to show a big number, but I separated coverage from accuracy and tested against blind labels.
*Example: the dashboard said 27% coverage, which is not accuracy. A blind check showed 15 of 16 confirmed numbers were right.*

**5. What was the hardest problem?**
Counting vehicles correctly. Reading a plate is one model, but knowing two sightings are the same vehicle is much harder.
*Example: a parked scooter was counted 19 times, because traffic kept hiding it and the tracker treated it as new each time.*

**6. What would you do differently?**
Start measuring earlier, and control the footage. Good recordings would have saved more time than any code change.
*Example: on one poor video, a person could fully read only 10 plates out of 87 vehicles. No model can read what isn't there.*

### Computer vision

**7. What is the difference between detection and tracking?**
Detection finds objects in one frame. Tracking links them across frames, so the same car keeps one id.
*Example: detection says "there is a car here". Tracking says "this is still car number 14".*

**8. Why use several frames instead of one?**
A single frame can be blurred or misread. If several frames agree, the number is far more likely to be right.
*Example: one Kerala plate was read as `DL...` at 0.86 confidence. One frame would have accepted it, while requiring agreement rejects it.*

**9. Why two models for vehicles and plates?**
Plates are tiny in a full frame. Finding the vehicle first, then searching only inside it, gives the plate model a closer view.
*Example: the plate model works on a cut-out of the car at full resolution, not on the shrunken whole frame.*

**10. What decides whether a plate can be read?**
Mostly its width in pixels, and how sharp it is.
*Example: on earlier footage, about 12% of plates under 60 pixels gave a confident reading, against about 68% at 150 pixels and over.*

**11. Doesn't 4K give better results?**
Not automatically. What counts is the plate's size and sharpness, not the video's resolution, and 4K costs much more time.
*Example: the best read rate came from the 1080p video, because it was filmed closest to the traffic.*

**12. How did you choose the plate model?**
I tested 14 candidates on real crops, not published scores. The top five performed about the same, so I chose one made for vehicle cut-outs.
*Example: each of the top five led to a confident reading on 87 to 92 of 476 vehicles.*

**13. Why does a confidence score not mean the answer is right?**
It's the model's own opinion of itself, and models can be confidently wrong.
*Example: the reader even gave plausible plate numbers for things that weren't plates, at about 0.2 to 0.3.*

**14. How do you stop a plate being given to the wrong vehicle?**
Vehicle boxes overlap, so I check which vehicle owns it. An enclosed box wins; otherwise the nearer vehicle, the one lower in the picture, wins.
*Example: a half-hidden bus had a smaller box than the car in front, and it wrongly took the car's plate until I changed the rule.*

**15. Why do Indian plates make this harder?**
Formats vary: two-line plates, different colours, hand-painted numbers, and short old-style numbers. Traffic is also dense, with many two-wheelers.
*Example: `KL39P77` looks like a misread but is a real plate, so the format rules had to allow it.*

### System design

**16. Why is the worker separate from the web app?**
Video processing is slow and heavy. Keeping it separate means the dashboard stays responsive, and a crash in one job doesn't take the site down.
*Example: while the worker spends minutes on a video, the user can still browse results.*

**17. Why PostgreSQL as the queue instead of Redis or Celery?**
There was one worker and few jobs, so another service wasn't worth running. A table with `FOR UPDATE SKIP LOCKED` is safe and simple. At high volume I would move to a real queue.
*Example: a job is just a row with a status, so one query shows the whole queue.*

**18. What happens if the worker crashes mid-job?**
On restart it finds jobs left in progress, removes the half-written files, and tries once more. If that fails too, the job is marked failed with a reason.
*Example: a job left half-done by a power cut goes back in the queue instead of staying stuck.*

**19. How did you handle two AI libraries that conflict?**
I ran each in its own environment, as separate processes that talk through JSON messages.
*Example: PyTorch and PaddlePaddle needed different versions of cuDNN, so the plate reader runs as a small service.*

**20. How did you make it faster?**
I measured where time went, then removed wasted work rather than guessing.
*Example: the render stage was re-detecting plates it already knew and encoding at 4K. Fixing that took one video from 979 to 667 seconds with identical results.*

**21. How did you test it?**
286 automated tests that need no GPU, using fake pipelines and tiny generated videos, plus before-and-after comparisons of real results and browser checks of the dashboard.
*Example: after each change I compared every vehicle record with the previous run to prove nothing else moved.*

**22. How did you handle bad input?**
Files are checked on upload, and a run fails clearly rather than producing an empty result.
*Example: a truncated MP4 once "completed" with 7 frames. Now a job fails if under 90% of the frames can be read.*

### Accuracy and measurement

**23. How accurate is it?**
When it was sure, it was right 15 times out of 16 on the main video. That's a small sample, so I give the count, not a percentage. It confirmed 15 of the 28 plates a person could read.
*Example: if I said "94% accurate", the true figure could still be anywhere from about 70% to 100%.*

**24. What is the difference between accuracy and coverage?**
Accuracy asks whether the numbers it gave were right. Coverage asks how many vehicles got a number at all.
*Example: a system could confirm one plate correctly and have 100% accuracy, but almost no coverage.*

**25. What is the difference between precision and recall here?**
Precision: of the numbers it confirmed, how many were right. Recall: of the plates that could be read, how many it got.
*Example: on the main video, precision was 15 of 16 and recall was 15 of 28. I chose high precision, because a wrong number is worse than a missing one.*

**26. How did you avoid fooling yourself when measuring?**
Labels were written without seeing the system's answers and saved first. A person then read the hard plates and a random sample without seeing either answer.
*Example: all 10 random spot checks matched exactly, which showed the labels could be trusted.*

**27. Your count was wrong. How do you explain that?**
It's a known weakness that I found myself by measuring. Parked vehicles get counted again when traffic hides them. I reduced it but didn't remove it, and I don't present it as a true traffic count.
*Example: 59 shown for 32 real on the main video. A later fix cut another video from 167 to 125, for 87 real.*

### Production

**28. How would you run this on live cameras?**
Process each stream on a small GPU box near the camera, and send only small events to central services.
*Example: instead of sending video, a site sends "KL07AB1234, Gate 2, 09:15" with a plate image.*

**29. How would you scale to 100 cameras?**
Each camera is independent, so add edge boxes. Optimise the model first, because that decides how many cameras one GPU can handle.
*Example: my rough estimate is 4 to 8 cameras per GPU with TensorRT, so about 15 to 25 GPUs. I would measure this before buying.*

**30. What would worry you most about privacy?**
Plate data shows where people go, so it needs a clear purpose, short retention, access controls and an audit log. A person should also check a number before anyone acts on it.
*Example: delete non-matching plates after a set period, and log every search.*

**31. How would you improve accuracy over time?**
Use operator corrections as training data, and compare each new model on a fixed test set before rollout.
*Example: this project already stores corrections beside the system's answer, ready to export as labels.*

**32. How would you know if it stopped working in production?**
Watch the read rate per camera, not just whether the service is up. The software can run fine while results get worse.
*Example: a sudden drop on one camera usually means a dirty lens or a moved camera, and that should raise an alert.*
