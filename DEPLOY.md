# Deploying Sentinel

Sentinel has two halves. The website is easy to host anywhere; the engine holds
~800 MB of AI models in memory, which most free hosts can't fit.

| Piece | What it is | Where it goes |
|---|---|---|
| **Website** (`web/`) | Next.js | **Vercel** (free, no card) |
| **Engine** (`sentinel/`) | Python + FastAPI + ~800 MB of AI models | see the options below |

## Choosing where the engine runs

As of 2026, no free host offers *always-on + no credit card + enough RAM for
the models* all at once — the free tiers big enough for PyTorch (Google Cloud
Run, Oracle, Fly) all require a card, and the no-card ones (Render free =
512 MB) are too small. So there are two practical routes:

- **Route A — Cloudflare Tunnel (free, no card).** The engine runs on your own
  machine (`sentinel serve`) and a free tunnel gives it a public URL. Full AI
  accuracy. Trade-off: your machine must be on. **This is the setup in Part 1.**
- **Route B — Google Cloud Run (free tier, needs a card for verification).**
  The engine runs in the cloud 24/7 with no machine of yours involved. The
  `Dockerfile` in this repo is already built and tested for it. See Part 3.

Either way, deploy the engine first — the website needs its public URL.

---

## Part 1 — Expose the engine with a free Cloudflare Tunnel (no card)

1. Install cloudflared (Windows): `winget install Cloudflare.cloudflared`
   (macOS: `brew install cloudflared`; Linux: see Cloudflare's docs).
2. Start the engine **locked down for public exposure** — no arbitrary folder
   reads, and trusting the tunnel host:
   ```powershell
   $env:SENTINEL_ALLOW_SOURCES_PATH = "0"        # uploads only, no server paths
   $env:SENTINEL_TRUSTED_HOSTS = "*.trycloudflare.com"
   $env:SENTINEL_CORS_ORIGINS = "https://YOUR-SITE.vercel.app"   # set after Part 2
   sentinel serve --port 8010
   ```
3. In a second terminal, open the tunnel:
   ```
   cloudflared tunnel --url http://127.0.0.1:8010
   ```
   It prints a public URL like `https://something-random.trycloudflare.com`.
   That's your **API URL** — copy it for Part 2. Test it:
   `curl https://something-random.trycloudflare.com/health`
4. After Part 2 gives you the Vercel URL, restart the engine (step 2) with
   `SENTINEL_CORS_ORIGINS` set to that exact Vercel address, so only your site
   may call the engine from a browser.

Notes: the free quick-tunnel URL changes each time you restart cloudflared, and
the engine only answers while your machine is on and both processes are running.

---

## Part 2 — Deploy the website to Vercel

1. Create a free account at https://vercel.com and connect your GitHub.
2. Click **Add New → Project**, select your `Sentinel` repo.
3. **Important (monorepo setting)**: set **Root Directory** to `web`. This tells
   Vercel the Next.js app lives in the `web/` subfolder, not the repo root —
   after which the framework preset should auto-detect as **Next.js** (if it
   guessed FastAPI, change it manually to Next.js).
4. Add an environment variable:
   - **Name**: `NEXT_PUBLIC_API_URL`
   - **Value**: the engine's public URL — the Cloudflare Tunnel URL from
     Part 1 (or the Cloud Run URL from Part 3).
5. Click **Deploy**. Vercel builds and gives you a live URL like
   `https://sentinel-yourname.vercel.app`.
6. Go back and finish Part 1 step 4: restart the engine with
   `SENTINEL_CORS_ORIGINS` set to this exact Vercel URL.

Open the Vercel URL — you now have a fully public Sentinel: paste a question
and an AI's answer, upload documents, and get a fact-check.

---

## Part 3 — (Optional) Run the engine 24/7 on Google Cloud Run

This removes the "your machine must be on" limitation, at the cost of Google
requiring a card for identity verification (you stay within the free tier).

1. Install the gcloud CLI: https://cloud.google.com/sdk/docs/install
2. `gcloud auth login` and `gcloud config set project YOUR_PROJECT_ID`
3. From the repo root, deploy straight from source (Cloud Run builds the
   `Dockerfile` for you):
   ```
   gcloud run deploy sentinel-engine \
     --source . --region us-central1 --allow-unauthenticated \
     --memory 2Gi --cpu 2 --timeout 300 --max-instances 1 \
     --set-env-vars SENTINEL_ALLOW_SOURCES_PATH=0,SENTINEL_CORS_ORIGINS=https://YOUR-SITE.vercel.app
   ```
4. It prints a `https://sentinel-engine-....run.app` URL — use that as
   `NEXT_PUBLIC_API_URL` in Vercel (Part 2). `--max-instances 1` caps cost.

The Dockerfile already reads `$PORT` dynamically, so it works on Cloud Run as-is.

---

## Updating after a deploy

- **Website changes**: push to GitHub's `main` — Vercel redeploys automatically.
- **Engine (tunnel route)**: just restart `sentinel serve` with your new code.
- **Engine (Cloud Run route)**: re-run the `gcloud run deploy` command.

## Reverting to local-only

Nothing about deployment changes local use — `sentinel serve` +
`npm run dev` still work exactly as before on your own machine.
