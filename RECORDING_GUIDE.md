# Recording guide — how to film so number plates can be read

The system can only read a plate it can see clearly. Most vehicles that end without a number in the dashboard are not software failures: they were filmed from the side, cut off by the frame edge, or too far away for the plate to be more than a smear. Ten minutes of care at the camera gives more than any change to the models. This guide is for anyone recording with a phone or a fixed camera.

## 1. What the system needs

- **Plate width of at least 130 pixels** in the frame when the vehicle is at its closest (for two-row plates, each row at least 70 pixels tall). Below 60 pixels almost nothing is read; above 150 pixels most plates are.
- **Seen head-on**: the camera in line with the traffic, looking at the front or the back of the vehicles, not at their sides.
- **Sharp**: no motion blur, in focus, plate not overexposed.
- **In view for at least half a second** (the system reads a vehicle in up to six different frames and confirms a number only when frames agree).

Rule of thumb for a phone recording in landscape at 1080p (a typical phone camera sees about 70° across): an Indian plate (about 50 cm wide) is **130 pixels wide at roughly 5 m** at 1× zoom, and at roughly **10 m at 2× zoom**. Farther than that, zoom in or move closer. Zooming is better than moving if it keeps you in line with the traffic.

## 2. Where to stand or mount

- **In line with the traffic.** Stand (or mount) where vehicles come towards you or go away from you — the middle of a lane's line of sight, not beside the road. The total angle between the camera's line of sight and the vehicles' direction should be **under 30°**, counting both sideways offset and height.
- **Height about half the distance** at which you want to read the plate: reading at 4 m → camera about 2 m high; at 7 m → about 3.5 m. For longer distances (7–20 m) the camera can be lower than half the distance. A phone held at chest height works for vehicles 4–8 m away.
- **Level.** Keep the phone horizontal; a tilt of more than 5° makes plates slanted and harder to read.
- **Above headlight height** if you can, so headlights do not blind the camera at dusk.
- **Not into the sun**, and not next to strong lights (street lamps, shop signs): they distort exposure and cause glare.
- **Still.** Rest the phone on a wall, a tripod or a railing. A hand-held phone moves; a moving camera makes the tracker's job harder.

## 3. How to record

- **Landscape, 1080p, 30 frames per second.** 4K adds nothing to recognition (a plate that is too small at 1080p is still too small at 4K) and takes about two and a half times longer to process. Portrait recordings are not used in this project.
- **MP4 (H.264)** is the format the system takes directly.
- **Lock focus and exposure** on the road area if your phone allows it (tap and hold on most phones). Autofocus hunting between a near car and the background blurs plates.
- **Prefer a fast shutter**: a "sports" or "action" video mode, or good daylight. Motion blur is the main reason a plate that is big enough is still unreadable.
- **Turn off heavy stabilisation effects** if the phone offers the choice; they can warp fast-moving vehicles.
- **Clips of 1–3 minutes** are ideal: long enough for many vehicles, short enough to process in a few minutes.
- Audio is not needed; the system ignores it.

## 4. Night and low light

- Plates are retro-reflective: they send light **straight back to where it came from**. A light placed at the camera makes plates glow; a street lamp to the side does nothing for the camera.
- Phones have no infrared illumination and open their shutter longer in the dark, so expect motion blur and much lower coverage at night. If night footage matters, use a camera with built-in IR, or a light mounted at the camera, and keep the camera's gain limited so the plate is not washed out.

## 5. Before you upload — the plate-width check

1. Play the clip and pause where a vehicle is at its closest.
2. Estimate the plate's width against the picture: at 1080p, 130 pixels is about **7% of the frame width** — roughly the width of a thumb held at arm's length against a laptop screen.
3. If the plate is a thin sliver, the recording will give unconfirmed numbers. Move closer or zoom in and record again; it is cheaper than processing.

After processing, the dashboard tells you how it went: open any detection and look at the **Width px** column in the observations table. If most widths are under 60, the camera was too far.

## 6. What we measured

The advice above comes from Axis Communications' published guidance and from our own runs, which agree. Share of plate readings that came back confident (≥0.85), by plate width in pixels, on the three demo videos:

| Video | Resolution | Median plate width | < 60 px | 60–100 px | 100–150 px | ≥ 150 px |
|---|---|---|---|---|---|---|
| zoomed-in | 1080p | 52 px | 12% (n=146) | 66% (n=44) | 47% (n=17) | 77% (n=31) |
| clear | 4K | 110 px | 0% (n=78) | 3% (n=115) | 9% (n=205) | 70% (n=255) |
| rope | 4K | 144 px | — (n=2) | — (n=2) | 62% (n=8) | 40% (n=10) |

Two things stand out. Pixel width is what counts, not the camera's resolution: at 4K the 60–150 px plates were still far away and blurred and read poorly, while at 1080p a 60–100 px plate close to the camera read two times out of three. And `zoomed-in`, filmed closest to the traffic, is the clip with the best coverage (27%) despite being the lowest resolution. Earlier, on dashcam footage, the pattern was the same: under 60 px about 12% read, 150 px and over about 68%.

Coverage in the dashboard is the share of counted vehicles that ended with a confirmed number. It is not accuracy — how to measure that is in `ARCHITECTURE.md`, "How to measure real accuracy".

## 7. Quick checklist

- [ ] Landscape, 1080p, 30 fps, MP4
- [ ] In line with the traffic, angle under 30°, phone level
- [ ] Camera about half as high as the reading distance; above headlights
- [ ] Plate at least 130 px wide (≈ 7% of the frame) when closest — pause and check
- [ ] Focus and exposure locked, fast shutter, phone held still
- [ ] Not into the sun; at night, light at the camera or expect low coverage
- [ ] 1–3 minute clips

---

Adapted for phone and static-camera recordings from Axis Communications' whitepaper *License plate capture — Key factors for successful license plate recognition* (December 2024) and the *AXIS License Plate Verifier* technical documentation (February 2026): the 130 / 70 pixel minimums, the 30° and 5° angle limits, the height-to-distance rule, the retro-reflection and shutter advice, and the recommendation to stay at 2 MP or below. The measurements are this project's own.
