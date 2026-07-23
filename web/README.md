# Sentinel Web UI

Next.js frontend for Sentinel, a local fact-checking product that verifies an
AI-generated answer against source documents.

## Prerequisites

- Node.js 24+, npm 10+
- The Sentinel FastAPI backend running locally: `sentinel serve`
  (defaults to http://127.0.0.1:8000)

## Run

```bash
cd web
npm install
npm run dev
```

Open http://localhost:3000.

For a production build:

```bash
npm run build
npm run start
```

## Configuration

The API base URL is read from `NEXT_PUBLIC_API_URL` and defaults to
`http://127.0.0.1:8000`. To override it, copy `.env.local.example` to
`.env.local` and edit the value.

## Pages

- `/` — submit a question, an answer, and source documents (file uploads
  and/or a server folder path) for verification; results render inline.
- `/history` — table of past runs.
- `/runs/[id]` — full detail view for a single run.

The UI is fully offline: no external fonts, scripts, or images.
