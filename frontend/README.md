# Attendance Insight

Build an admin dashboard for a Student Attendance Management System (university 

coursework project). The system reads photographed attendance signing sheets, runs 

OpenCV image processing to detect which students signed, and stores results in MongoDB. 

This dashboard is the operator's interface to that backend.

=== DESIGN DIRECTION ===

Clean academic-institutional feel, not a startup SaaS look. Light theme with an optional 

dark toggle. Restrained palette: deep indigo primary, slate greys, emerald for "present", 

rose for "absent", amber for "needs review". Generous whitespace, subtle borders instead 

of heavy shadows. Inter or similar for UI text, a monospace face for student index 

numbers and technical values. Data density matters more than decoration — this is a tool 

someone uses for an hour at a time.

=== LAYOUT ===

Persistent left sidebar (collapsible) with: Dashboard, Upload Sheet, Sessions, Students, 

Signature Review, Settings. Top bar with page title, breadcrumb, dark-mode toggle, and a 

connection-status dot for the backend API.

=== PAGE 1: DASHBOARD (/) ===

- Four stat cards: Total Sheets Processed, Total Students, Overall Attendance Rate, 

  Flagged Signatures

- Line chart: attendance rate over time, one point per session date

- Horizontal bar chart: attendance percentage per student, sorted lowest first, top 10 

  shown, "view all" link

- Recent Sessions table: date, subject code, students detected, present/absent counts, 

  status badge, view action

=== PAGE 2: UPLOAD SHEET (/upload) ===

The most important page — it must visualise the image processing pipeline.

- Two drag-and-drop zones side by side: one for the sheet image (jpg/png), one for 

  info.xml. Show file name, size, and an image thumbnail preview once dropped.

- Optional settings row: subject code input, session date picker, "header rows" number 

  input (default 1), "signature column" select (default: last column)

- "Start Processing" button, disabled until both files are present

- On submit, switch to a live processing view driven by a WebSocket:

    * A vertical stepper listing the pipeline stages: Resize, Grayscale, Denoise, 

      Deskew, Binarize, Grid Detection, Cell Extraction, Presence Detection

    * Each step shows pending / running (spinner) / done (check) / failed (x)

    * As each step completes, its output image appears as a thumbnail in a gallery to 

      the right; clicking one opens a lightbox with the full image, the step name, and 

      a short description of the technique used

    * A before/after slider comparing the original photo with the final binarized image

- On completion, show the results table: row number, student index, name, present/absent 

  badge, ink ratio as a small progress bar, and the cropped signature image thumbnail. 

  Include an "Export as CSV" button.

=== PAGE 3: SESSIONS (/sessions and /sessions/[id]) ===

List view: searchable, filterable by subject and date range, sortable table of all 

processed sheets with status badges.

Detail view: the same processing-step gallery (read-only), the attendance results table, 

and the original uploaded sheet image. A "reprocess" button that re-runs with different 

header-row / signature-column settings.

=== PAGE 4: STUDENTS (/students and /students/[index]) ===

List: searchable table of students — index, name, batch, sessions attended, attendance 

percentage with a coloured progress bar.

Detail: the student's photo-less profile header, a donut chart of present vs absent, a 

bar chart of attendance per session date, a calendar-style heatmap of session dates, and 

a gallery of every signature crop collected for that student across sessions.

=== PAGE 5: SIGNATURE REVIEW (/signatures) ===

A verification queue. Card grid where each card shows two signature crops side by side 

(reference vs current), the student index, a similarity score with a coloured ring, and 

Confirm / Flag buttons. Filter by "flagged only".

=== PAGE 6: SETTINGS (/settings) ===

Backend API base URL input with a "test connection" button, detection threshold sliders 

(ink ratio threshold, minimum component area), and a default header-rows value.

=== BACKEND API (FastAPI, base http://127.0.0.1:8000/api) ===

POST /sheets/upload            multipart: image + info_xml -> { session_id }

POST /sheets/{id}/process      body { header_rows, signature_col } -> starts processing

GET  /sheets/{id}/steps        -> [{ name, order, path }]

GET  /sheets/{id}/results      -> [{ student_index, present, ink_ratio, cell_image, confidence }]

WS   /sheets/ws/{id}           -> { step, order, total, path, status }

GET  /attendance/{index}

GET  /attendance/{index}/summary  -> { present, absent, percentage, series: [{date, present}] }

GET  /students

GET  /students/{index}

Images are served as static files: http://127.0.0.1:8000/static/<path from the API>

Build with typed API client functions in one place (src/lib/api.ts) and TanStack Query 

for data fetching. Use mock data matching these exact shapes so every screen is fully 

populated in preview, but keep the mock layer swappable with a single flag.

=== STATES — do not skip these ===

Every list and chart needs an explicit empty state with an illustration and a call to 

action, a skeleton loading state, and an error state with a retry button. The upload 

page needs a failure state that shows the backend error message and keeps the partial 

step gallery visible so the operator can see which stage broke.

Make it fully responsive; the processing gallery should stack below the stepper on 

mobile. Use accessible colour contrast and never convey present/absent by colour alone — 

always pair with a text label or icon.

This project was built with [Lovable](https://lovable.dev).

**Live app**: https://sheet-scan-scribe.lovable.app

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/ec0e5141-d1de-4368-9d7a-c7abb2778437).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```
