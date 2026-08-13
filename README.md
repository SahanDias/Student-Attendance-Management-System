# Student-Attendance-Management-System

Reads scanned paper attendance sheets and turns them into digital attendance
records. An uploaded sheet image goes through an image-processing pipeline,
the grid is detected, each student's signature cell is cut out and checked for
a mark, and the present/absent result is stored in MongoDB and shown in a web
UI.

## Stack

- **Backend** — Python, FastAPI, OpenCV, MongoDB (Motor / PyMongo)
- **Frontend** — Next.js 16, React 19, TypeScript, Tailwind CSS, shadcn/ui

## Project layout

```
backend/
  app/
    api/          FastAPI routers (sheets, students, attendance, signatures)
    core/         MongoDB client, file storage manager
    models/       Pydantic schemas
    services/     pipeline, grid detection, cell extraction,
                  presence detection, signature matching, evaluation
      steps/      grayscale, resize, deskew, denoise, binarize
  cli/            command-line runners (sams.py, infovis.py, migrate_status.py)
  storage/        uploaded sheets and per-step debug images
frontend/
  app/            Next.js routes (upload, sessions, students, signatures, settings)
  components/     UI components and page components
  services/       API client and per-domain service calls
  types/          shared API types
```

## How it works

1. **Upload** — a sheet image plus an `info.xml` listing the students.
2. **Pipeline** — grayscale → resize → deskew → denoise → binarize. Every step
   saves a numbered PNG so the result can be audited.
3. **Grid detection** — locates the table rows and columns on the sheet.
4. **Cell extraction** — crops the signature cell for each student row.
5. **Presence detection** — decides whether each cell contains a signature.
6. **Signature matching** — compares the cell against the student's known
   signature; low-confidence cases are flagged for manual review.
7. **Evaluation / storage** — results are written to MongoDB and returned to
   the UI, with live progress over a WebSocket.

## Setup

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env`:

```
MONGODB_URI=mongodb://localhost:27017
DB_NAME=sams
STORAGE_ROOT=storage
API_PREFIX=/api
```

Run a single sheet through the pipeline from the command line:

```bash
python cli/sams.py path/to/sheet.jpg path/to/info.xml
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Opens on http://localhost:3000. It expects the API at
`http://localhost:8000/api`; override with `NEXT_PUBLIC_API_URL`. The UI runs
on mock data by default — set `NEXT_PUBLIC_USE_MOCK=false` to talk to the real
backend.

## API endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/sheets/upload` | upload a sheet image and info file |
| POST | `/api/sheets/{session_id}/process` | run the pipeline |
| GET | `/api/sheets` | list sessions |
| GET | `/api/sheets/{session_id}/steps` | per-step pipeline images |
| GET | `/api/sheets/{session_id}/results` | attendance results |
| GET | `/api/sheets/{session_id}/evaluation` | accuracy evaluation |
| WS | `/api/sheets/ws/{session_id}` | live processing progress |
| GET | `/api/students` | list students |
| GET | `/api/attendance/trend` | attendance over time |
| GET | `/api/attendance/summary` | attendance summary |
| GET | `/api/signatures` | signature records |
| POST | `/api/signatures/{student_index}/verify` | verify a signature |
| POST | `/api/signatures/{student_index}/review` | submit a manual review |

## Scripts

| Command | What it does |
| --- | --- |
| `python cli/sams.py <image> <info.xml>` | process one sheet end to end |
| `python cli/infovis.py` | visualise parsed info data |
| `python cli/migrate_status.py` | migrate attendance status values |
| `npm run dev` | start the frontend in development |
| `npm run build` | production build |
| `npm run lint` | lint the frontend |
| `npm run format` | format with Prettier |
| `pytest` | run backend tests |
