# Knowledge notes

Background notes collected for the Vehicle ANPR POC. These are reference material, not project requirements; `ARCHITECTURE.md` and `DESIGN/DASHBOARD_DESIGN.md` remain the source of truth for what gets built.

---

## Online vs offline trackers in ANPR systems (deployment sense)

In Automatic Number Plate Recognition (ANPR) systems, online and offline trackers refer to how the system processes vehicle data, cross-references databases, and communicates between the camera (the "edge" device) and the central server. [[1]](https://www.aeroranger.com/blog-post/anpr-offline-storage-and-recovery/) [[2]](https://www.trafitek.com/anpr-system)

The primary difference lies in network dependency and processing location. [[1]](https://catchsystems.nl/technology.html) [[2]](https://www.trafitek.com/anpr-system)

### Online trackers (real-time / connected systems)

Online trackers are continuously connected to a central server or cloud network via cellular, Wi-Fi, or Ethernet connections. [[1]](https://edmondindustries.com/offline-vs-online-gps-tracking-for-travel/) [[2]](https://www.trafitek.com/anpr-system)

- **How they work:** The ANPR camera captures the license plate, processes it using Optical Character Recognition (OCR), and instantly transmits the data to a central database. [[1]](https://parkdirectukltd.co.uk/understanding-anpr-cameras-what-do-they-track-and-capture/) [[2]](https://www.trafitek.com/anpr-system)
- **Database queries:** It checks the data against "live" or active databases (such as national police databases, blacklists, or active parking permit systems) in real time. [[1]](https://www.verkada.com/au/blog/lpr-anpr-camera/) [[2]](https://www.gov.uk/government/publications/national-anpr-service-data-protection-impact-assessment/national-anpr-service-data-protection-impact-assessment-accessible) [[3]](https://www.trafitek.com/anpr-system)
- **Key benefit:** Instant alert generation. If a flagged vehicle (e.g., stolen or unregistered) passes the camera, law enforcement or security personnel receive a notification within milliseconds. [[1]](https://catchsystems.nl/technology.html) [[2]](https://www.youtube.com/watch?v=JB0pXUy2Yx0) [[3]](https://www.trafitek.com/anpr-system)
- **Limitation:** They rely entirely on a stable network connection. If the network drops or suffers from high latency, the live tracking capability stops or lags. [[1]](https://catchsystems.nl/technology.html)

### Offline trackers (edge / buffered systems)

Offline trackers are designed to operate independently of a continuous network connection, processing and storing information locally on the device itself. [[1]](https://edmondindustries.com/offline-vs-online-gps-tracking-for-travel/) [[2]](https://www.aeroranger.com/blog-post/anpr-offline-storage-and-recovery/) [[3]](https://catchsystems.nl/technology.html)

- **How they work:** The ANPR camera has built-in processing intelligence (Edge AI). It captures, reads, and logs the plates entirely on-board the device.
- **Database queries:** It cross-references plates using a localized, pre-downloaded database stored right on the camera or patrol vehicle's hard drive.
- **Data management:** All data logs, timestamps, and images are stored in an offline buffer. Once the device reconnects to a network—or when an operator manually downloads the data—it synchronizes with the central server.
- **Key benefit:** Reliability in remote areas. This is highly used in mobile patrol vehicles or remote solar-powered gantry cameras where cellular coverage is spotty or non-existent.
- **Limitation:** Centralized alerts are delayed until the device syncs up, meaning you cannot get "live" nation-wide system tracking updates while offline. [[1]](https://www.i-view.com.tw/improving-police-efficiency/?lang=en) [[2]](https://www.gov.uk/government/publications/national-anpr-service-data-protection-impact-assessment/national-anpr-service-data-protection-impact-assessment-accessible) [[3]](https://www.aeroranger.com/blog-post/anpr-offline-storage-and-recovery/) [[4]](https://catchsystems.nl/technology.html) [[5]](https://parkdirectukltd.co.uk/understanding-anpr-cameras-what-do-they-track-and-capture/) [[6]](https://www.trafitek.com/anpr-system)

### Direct comparison

| Feature | Online trackers | Offline trackers |
|---|---|---|
| Network dependency | Requires continuous active connection | Functions entirely without internet/network |
| Data synchronization | Instantaneous streaming to server | Saved locally and synced later (delayed) |
| Primary use case | City surveillance, tolling, active law enforcement | Mobile patrol cars, remote locations, parking lots |
| Alert capabilities | Immediate, live network-wide notifications | Localized alerts only (based on local list) |

### Note for this project: "online" means something different in `ARCHITECTURE.md`

*(Added by Claude; not part of the source text above.)*

The section above uses "online/offline" in the **deployment** sense: whether a camera is connected to a central server. `ARCHITECTURE.md` uses the same words in two other senses, and they should not be mixed up:

- **"TrackTrack — Online multi-object tracking algorithm"** is the **computer-vision** sense. An online tracker assigns track IDs frame by frame using only the current and past frames. An offline (batch) tracker looks at the whole video, including future frames, before deciding. It says nothing about network connections.
- **"Offline uploaded-video analysis"** is the **processing-mode** sense: the system works on recorded files after upload, not on a live camera feed.

So this POC runs an online tracker (computer-vision sense) inside an offline pipeline (processing-mode sense), and the deployment sense above does not apply to it: there are no edge cameras, no central server sync and no live database lookups.
