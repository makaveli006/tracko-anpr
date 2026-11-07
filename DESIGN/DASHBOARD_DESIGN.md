
# Vehicle ANPR POC — Premium Black Surveillance Dashboard

## 1. Project Objective

Build a modern, professional, dark-themed web application for an Indian Automatic Number Plate Recognition (ANPR) Proof of Concept (POC).

**Application:** Vehicle ANPR POC  
**Subtitle:** Detection • Tracking • Recognition  
**Audience:** C-suite leadership  
**Frontend:** NiceGUI (Python)  
**Backend:** FastAPI  
**Database:** PostgreSQL  

Use the attached dashboard screenshot as the **primary visual reference**.

The goal is to closely reproduce its layout, styling, visual hierarchy, colors, charts, video monitoring interface, navigation, and overall appearance.

The application must feel like a high-end, modern server-room surveillance dashboard.

This POC processes uploaded road traffic recordings, not live camera feeds.

---

## 2. Design Identity

### Primary Visual Style

Create a professional, premium, black surveillance dashboard.

The interface should resemble:

- A modern traffic monitoring control center
- A high-end server monitoring application
- A professional security operations dashboard
- An enterprise vehicle analytics platform

### Strict Color Restrictions

**Never use:**
- Blue
- Purple
- Violet
- Indigo
- Bluish gray
- Cyberpunk gradients
- Neon purple or blue glow
- White page backgrounds

The entire interface must use black, charcoal, graphite, white, gray, green, and amber.

### Color Palette

| Element | Color |
|---|---|
| Main background | `#080808` |
| Sidebar background | `#050505` |
| Top header | `#090909` |
| Primary card | `#141414` |
| Secondary card | `#191919` |
| Elevated surface | `#202020` |
| Card border | `#363636` |
| Divider | `#292929` |
| Primary text | `#F5F5F5` |
| Secondary text | `#B0B0B0` |
| Muted text | `#858585` |
| Primary green | `#36D428` |
| Dark green | `#166522` |
| Bright green | `#4ADE36` |
| Amber | `#FACC15` |
| Warning orange | `#F59E0B` |
| Error red | `#EF4444` |

Green is the primary accent.

Amber is reserved for warnings, number plate labels, and selected secondary indicators.

Use red only for errors and critical status.

### Surface Design

- Matte black and charcoal surfaces
- Thin gray borders
- Subtle shadows
- Rounded corners (8–12px)
- Very restrained gradients
- Strong readability
- Minimal visual clutter

Avoid excessive glow or flashy effects.

---

## 3. Layout Architecture

Reproduce the reference image's layout.

### Desktop Structure

```text
┌─────────────────────────────────────────────────────────────┐
│ TOP HEADER                                                  │
├────────────┬────────────────────────────────────────────────┤
│            │ OVERVIEW HEADER                                │
│ SIDEBAR    ├────────────────────────────────────────────────┤
│            │ FIVE SUMMARY METRIC CARDS                      │
│ Overview   ├─────────────────────┬────────────┬─────────────┤
│ Upload     │                     │            │ VEHICLE     │
│ Analysis   │ VIDEO ANALYSIS      │ PROCESSING │ CATEGORY    │
│ History    │                     │ STATUS     ├─────────────┤
│ Registry   │                     │            │ RECOGNITION │
│ Analytics  │                     │            │ COVERAGE    │
│ Settings   ├─────────────────────┴────────────┴─────────────┤
│            │ RECENT DETECTIONS       │ DETECTIONS OVER TIME  │
│            │                         │                       │
│ SYSTEM     │                         │                       │
│ READY      │                         │                       │
└────────────┴─────────────────────────┴───────────────────────┘
```

### Dimensions

- Header height: 62px
- Sidebar width: 210px
- Main content padding: 16px
- Card gaps: 14–16px
- Card border radius: 10–12px
- Desktop-first design
- Responsive on smaller screens

Use CSS Grid and Flexbox through NiceGUI.

Avoid absolute positioning for major containers.

---

## 4. Top Header

The header must look similar to the reference image.

### Background

Use a black/graphite surface.

Optionally add a very subtle server rack photographic texture in the header, matching the reference image.

The background must remain dark enough for the text to be readable.

Do not use a colorful gradient.

### Left Section

Display a small rounded app icon.

Icon:
White car outline inside a dark green square.

Application title:

**Vehicle ANPR POC**

Subtitle:

Detection • Tracking • Recognition

Title:
- White
- Bold
- Approximately 22px

Subtitle:
- Light gray
- Approximately 12px

### Right Section

Display:

1. Environment badge: `POC – Indian Roads`
2. Notification bell
3. User profile icon

Environment badge:
- Rounded pill
- Dark charcoal background
- Thin gray border
- Small green status indicator
- White text

Maintain clean spacing.

The notification bell and the user profile icon are decorative in the POC: there is no login and no notification list.

---

## 5. Sidebar Navigation

### Appearance

Background:
`#050505`

Sidebar width:
210px

Add subtle separation from the main content.

Navigation text:
White / light gray

Navigation icons:
Neutral gray

### Active Navigation Item

Active background:
`#262626`

Left border:
4px bright green

Active icon:
Green

Text:
White

Rounded corners:
8px

### Navigation Items

1. Overview
2. Upload & Process
3. Video Analysis
4. Detection History
5. Demo Registry
6. Analytics
7. Settings

Use professional, minimal icons.

### System Status Panel

Fix a small status card near the bottom of the sidebar.

Title:

**System Ready**

Include a green status dot.

Details:

- GPU: NVIDIA (16 GB)
- Models: YOLO26m / YOLO26s
- OCR: Awiros-ANPR-OCR

Use small typography and subtle row spacing.

The status must reflect actual backend readiness.

If a service is unavailable, display a warning instead of a false green status.

---

## 6. Overview Header

Main heading:

**Overview**

Subtitle:

Vehicle Detection, Tracking and Number Plate Recognition from Uploaded Videos

Right-side metadata card:

`Processed: 5 Videos | Last Run: [Actual Timestamp]`

Appearance:
- Black/charcoal background
- Thin gray border
- Rounded corners
- Light text

The timestamp should come from the backend.

Video selector:

A dropdown chooses which processed video the player, processing status, charts and detections table show.

Scope switch:

The five summary cards can switch between the selected video and all processed videos.

---

## 7. Summary Metric Cards

Create five equal-width dark metric cards across the top.

### Card Styling

Background:
`#151515`

Border:
`1px solid #363636`

Radius:
10px

Each card contains:
- Icon on left
- Metric label
- Bold value
- Optional secondary detail

### Card 1 — Total Vehicles

Icon:
Green car

Label:
Total Vehicles

Example:
**1,248**

### Card 2 — Recognized Plates

Icon:
Green check

Label:
Recognized Plates

Example:
**1,087**

Secondary text:
87.1% in green

### Card 3 — Unique Tracks

Icon:
Green tracking target

Label:
Unique Tracks

Example:
**1,176**

### Card 4 — Videos Processed

Icon:
Green stacked layers

Label:
Videos Processed

Example:
**5**

### Card 5 — Average Processing Time

Icon:
Green clock

Label:
Avg. Processing Time

Example:
**3 min 42 sec / video**

All values must come from backend results.

Sample numbers are permitted only in clearly labeled demonstration mode.

---

## 8. Video Analysis Panel

This is the most important part of the dashboard.

It must be visually prominent and closely match the supplied screenshot.

### Panel Design

Background:
`#141414`

Border:
`#363636`

Radius:
12px

Panel title:
**Video Analysis**

### Video Mode Selector

Provide:

- Original Video
- Annotated Video

Use a segmented control.

Inactive:
Charcoal background with white text.

Active:
Dark green (`#166522`) background with white text.

Default:
Annotated Video, when available.

### Video Player

Use a 16:9 video player.

Requirements:

- Original video quality, at the video's own resolution and frame rate
- Play/pause
- Video seek bar
- Current playback timestamp
- Total duration
- Volume
- Fullscreen
- Playback speed

Use a near-black player frame.

### Detection Overlays

The annotated video should contain:

**Vehicle Bounding Boxes**
- Bright green thin borders
- Clearly visible against road footage
- Consistent stroke width

**Tracking Labels**
- Dark green (`#166522`) background
- White text
- Compact rounded rectangles

Examples:

`#T101 Car (0.98)`

`#T102 Motorcycle (0.96)`

`#T103 Bus (0.98)`

**Number Plate Annotations**
- Yellow/amber plate boundary
- Yellow plate text label
- Dark text where contrast requires it

Example:

`KL10AB1234 (0.97)`

### Important Behavior

The video is generated from uploaded and processed recordings.

Do not design this as a live camera stream.

Users must be able to switch between original and annotated footage.

Preserve playback position when switching versions.

---

## 9. Processing Status Panel

Position this card immediately to the right of the video player.

Title:

**Processing Status**

### Appearance

Dark charcoal card.

Create a vertical processing timeline.

Completed stages:
Green checkmarks.

Processing:
Amber progress indicator.

Pending:
Gray indicators.

Failed:
Red indicator.

### Timeline Stages

1. Video Uploaded
2. Vehicle Detection (YOLO26m)
3. Vehicle Tracking (TrackTrack)
4. Plate Detection (YOLO26s)
5. Optical Character Recognition (OCR) — Awiros-ANPR-OCR
6. Multi-frame Validation
7. Result Generation

Use thin gray connecting lines.

For completed jobs, show a dark green status banner:

**Completed**

For active processing:

**Processing**

Display actual job progress from FastAPI.

Do not hardcode success states.

---

## 10. Vehicle Category Distribution

Create a dark card at the upper-right of the dashboard.

Title:

**Vehicle Category Distribution**

### Donut Chart

Use an interactive donut chart.

Color distribution:

- Car: Green `#27C443`
- Motorcycle: Yellow `#FACC15`
- Bus: Amber `#F59E0B`
- Truck: Red-orange `#EF5B47`

Do not use blue or purple.

### Chart Center

Display:

**1,248**

Vehicles

The center should use the same charcoal color as the card background.

### Legend

Place legend items to the right.

Each item shows:
- Category icon
- Category label
- Count
- Percentage

Example:

Car — 672 (53.8%)
Motorcycle — 336 (26.9%)
Bus — 124 (9.9%)
Truck — 116 (9.3%)

Use actual backend data.

---

## 11. Recognition Coverage

Position directly beneath the vehicle distribution card.

Title:

**Recognition Coverage**

### Progress Bar

Background:
Dark gray

Fill:
Bright green

Example:
87.1%

Supporting text:

`1,087 / 1,248 vehicles with recognized number plates`

Use a thin, modern progress bar.

Display accurate coverage calculations.

Recognition coverage is not equivalent to measured model accuracy.

---

## 12. Recent Detections Table

Create a large dark card below the main video analysis area.

Title:

**Recent Detections**

Top-right:
Green `View All` action.

### Table Columns

1. Time
2. Track ID
3. Vehicle
4. Registration Number
5. Confidence
6. Validation
7. Plate Image

### Table Appearance

Header:
`#242424`

Rows:
`#141414`

Hover:
`#202020`

Dividers:
`#303030`

Text:
White and light gray.

Registration number:
Semibold white.

### Validation Status

Confirmed:
Green check + green text.

Pending:
Amber warning + amber text.

Failed:
Red indicator.

Unconfirmed:
Gray or amber indicator.

### Plate Image

Display a small cropped license plate thumbnail.

Keep the thumbnail legible.

Clicking a detection should open details including:
- Vehicle crop
- Number plate crop
- Recognition text
- Confidence
- Track ID
- Detection timestamp
- Multi-frame observations
- Validation status
- Fictional registry match

Clicking the detection should also seek the video to its associated timestamp.

---

## 13. Detections Over Time Chart

Place the chart on the lower-right side.

Title:

**Detections Over Time**

### Design

Background:
`#141414`

Grid:
Very subtle gray horizontal lines.

X-axis:
Video Time (mm:ss)

Y-axis:
New vehicles per 10-second bucket (each vehicle is counted once, in the bucket where it is first seen, so the chart adds up to Total Vehicles)

### Chart Line

Primary color:
Bright green `#4ADE36`

Area fill:
Very subtle transparent green.

Line thickness:
2px.

Use minimal tooltips and small data-point indicators.

No blue charts.

No purple charts.

Do not exaggerate the brightness or introduce glowing effects.

---

## 14. Upload & Process Page

Use the same black theme throughout.

### Upload Area

Create a large central drag-and-drop card.

Background:
`#151515`

Border:
Dashed gray `#404040`

Icon:
White upload cloud.

Title:

**Upload Road Traffic Video**

Subtitle:

Upload an MP4 video to analyze vehicle movement and registration plates.

### Supported Inputs

- MP4 video
- H.264 preferred
- 1080p recommended
- 30 frames per second recommended

### File Information

After upload, display:
- Filename
- File size
- Resolution
- Duration
- Frame rate
- Upload status

### Processing Button

Primary action:

**Process Video**

Background:
Dark green (`#166522`)

Text:
White.

Provide job progress and errors.

On successful completion show:

- View Analysis
- Download Annotated Video
- View Detections

---

## 15. Additional Pages

### Video Analysis

Full-width video analysis page with:
- Original/annotated comparison
- Large player
- Track details
- Plate recognition details
- Timeline navigation
- Video download

### Detection History

Dark searchable table with:
- Registration number
- Video
- Track ID
- Vehicle type
- Time
- Confidence
- Validation state
- Plate image

Provide sorting, filtering, and export.

### Demo Registry

Dark registry interface for fictional vehicle information.

Clearly display:

**Demonstration Data Only**

Never imply that actual government vehicle registration information is available.

### Analytics

Include:
- Vehicle category distribution
- Recognition coverage
- Detection activity
- Video processing duration
- Recognition confidence distribution
- Validated versus uncertain registrations

### Settings

Include:
- Model configuration
- Video processing settings
- Tracking configuration
- Recognition confidence thresholds
- Storage configuration

All pages must maintain the exact same black visual theme.

---

## 16. Backend Architecture

Maintain the existing POC technology stack.

### Frontend

NiceGUI

### Backend

FastAPI

### Video Processing

OpenCV + FFmpeg

### Detection Models

Vehicle:
YOLO26m

Number Plate:
Indian fine-tuned YOLO26s

### Vehicle Tracking

TrackTrack

### OCR

Awiros-ANPR-OCR

### Validation

Python-based multi-frame consensus.

### Database

PostgreSQL

### Storage

Local uploaded videos, annotated videos and plate images.

### Processing

Separate Python worker.

Do not block the NiceGUI interface during video inference.

### API Endpoints

- POST /api/videos
- GET /api/videos
- POST /api/videos/{id}/process
- GET /api/jobs/{id}
- GET /api/videos/{id}/results
- GET /api/videos/{id}/detections
- GET /api/videos/{id}/analytics
- GET /api/videos/{id}/annotated

---

## 17. Responsive Design

### Large Screens

- Sidebar visible
- Five metric cards on one row
- Three-column analysis layout
- Detections and timeline chart side by side

### Medium Screens

- Sidebar collapsible
- Metric cards wrap
- Video panel occupies more width
- Processing and statistics cards rearrange

### Mobile

- Drawer navigation
- Cards stack
- Video player resizes
- Tables scroll horizontally

The interface should prioritize desktop monitoring.

---

## 18. Implementation Requirements

Use NiceGUI components and custom CSS to closely match the reference.

Suggested components:
- ui.header
- ui.left_drawer
- ui.card
- ui.row
- ui.column
- ui.icon
- ui.button
- ui.video
- ui.upload
- ui.table
- ui.echart
- ui.linear_progress
- ui.dialog

Use a consistent design-token system.

Store all theme colors in a central stylesheet.

Do not scatter inconsistent colors across individual components.

### Design Tokens

```css
:root {
  --bg-main: #080808;
  --bg-sidebar: #050505;
  --bg-header: #090909;
  --bg-card: #141414;
  --bg-card-hover: #202020;
  --border-color: #363636;

  --text-primary: #f5f5f5;
  --text-secondary: #b0b0b0;
  --text-muted: #858585;

  --accent-green: #36d428;
  --accent-green-dark: #166522;
  --accent-amber: #facc15;
  --accent-red: #ef4444;
}
```

Never override these with blue, purple, or violet colors.

Disable framework default theme colors that would introduce blue.

---

## 19. Final Quality Requirements

The dashboard must:

1. Closely match the supplied image.
2. Use a true black/charcoal theme.
3. Have no bluish background tint.
4. Use green as its primary accent.
5. Use amber for plate highlights.
6. Maintain professional typography.
7. Have consistent card spacing.
8. Present the video player prominently.
9. Use realistic table and chart layouts.
10. Support real FastAPI data integration.
11. Keep the interface responsive during processing.
12. Work for uploaded recordings rather than live streams.
13. Be visually suitable for C-suite leadership.

### Critical Design Instruction

Do not turn this into a generic Artificial Intelligence dashboard.

Do not add chatbot elements, animated neural networks, futuristic
patterns, purple gradients, or other unrelated AI-themed visuals.

The desired appearance is:

**Modern Black Traffic Surveillance Control Room**

The interface should communicate:
- Operational clarity
- Reliability
- Precision
- Video intelligence
- Technical maturity

## Final Deliverable

Build a complete, modern, black-themed Vehicle ANPR POC dashboard
using NiceGUI.

Use the attached screenshot as the visual reference.

Preserve its layout, proportions and component positioning.

Convert all interface elements into functional components.

The application should allow users to:

1. Upload recorded Indian road videos.
2. Start AI processing.
3. Monitor actual job progress.
4. Watch the annotated video.
5. Inspect tracked vehicles.
6. Review recognized number plates.
7. Analyze detection statistics.
8. Present the results professionally to leadership.

**The final visual style must be black, graphite, green, amber and white — absolutely no blue, purple or violet.**
