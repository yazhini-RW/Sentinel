# Deploying Sentinel

Sentinel has two halves that deploy to two different free platforms:

| Piece | What it is | Where it goes | Why |
|---|---|---|---|
| **Engine** (`sentinel/`) | Python + FastAPI + ~800 MB of AI models | **Hugging Face Spaces** (Docker) | Needs to stay running and hold large models in memory — standard website hosts (including Vercel) don't support this. |
| **Website** (`web/`) | Next.js | **Vercel** | Lightweight, exactly what Vercel is built for. |

Both are free. Do the engine first — the website needs its URL.

---

## Part 1 — Deploy the engine to Hugging Face Spaces

1. Create a free account at https://huggingface.co (if you don't have one).
2. Go to https://huggingface.co/new-space
   - **Space name**: `sentinel-engine` (or anything you like)
   - **License**: your choice (MIT is fine)
   - **Select the Space SDK**: **Docker** → then choose the **Blank** Docker template
   - **Space hardware**: **CPU basic — Free**
   - **Visibility**: Public (so your website can reach it)
   - Click **Create Space**
3. Hugging Face shows you a git URL for the new Space, e.g.
   `https://huggingface.co/spaces/YOUR_USERNAME/sentinel-engine`
   Clone your **GitHub** Sentinel repo locally if you haven't, then push it to
   this Space's git remote:
   ```
   git remote add space https://huggingface.co/spaces/YOUR_USERNAME/sentinel-engine
   git push space main
   ```
   (You'll be asked to sign in — use a Hugging Face **access token** as the
   password: create one at https://huggingface.co/settings/tokens with
   "write" access.)
4. **Replace the Space's README** with the one made for it (the Space reads
   its config from README.md frontmatter, which is different from the
   GitHub README):
   ```
   cp deploy/space_README.md README.md
   git add README.md
   git commit -m "Use Space README for Hugging Face"
   git push space main
   ```
   (Do this only on this remote/checkout — don't push it to GitHub too,
   unless you don't mind swapping the repo's README.)
5. Open your Space's page on huggingface.co — it will **build for a few
   minutes** (installing PyTorch etc.), then show "Running". Test it:
   ```
   curl https://YOUR_USERNAME-sentinel-engine.hf.space/health
   ```
   You should see `{"status":"ok",...}`. That URL is your **API URL** — copy
   it, you need it in Part 2.

### Notes on the free tier
- The free CPU tier **sleeps after inactivity** and takes 30–60 seconds to
  wake on the next request — this is normal, not a bug.
- The Dockerfile sets `SENTINEL_ALLOW_SOURCES_PATH=0` for this public
  deployment, meaning visitors can only **upload files**, not type a server
  folder path (that option only makes sense on a private, locally-run
  instance — see `sentinel/api.py` for the full reasoning).

---

## Part 2 — Deploy the website to Vercel

1. Create a free account at https://vercel.com and connect your GitHub.
2. Click **Add New → Project**, select your `Sentinel` repo.
3. **Important (monorepo setting)**: set **Root Directory** to `web`
   (Vercel's project settings → General → Root Directory). This tells Vercel
   the Next.js app lives in the `web/` subfolder, not the repo root.
4. Add an environment variable:
   - **Name**: `NEXT_PUBLIC_API_URL`
   - **Value**: the Hugging Face Space URL from Part 1, e.g.
     `https://YOUR_USERNAME-sentinel-engine.hf.space`
5. Click **Deploy**. Vercel builds and gives you a live URL like
   `https://sentinel-yourname.vercel.app`.

Open that URL — you now have a fully public Sentinel: paste a question,
paste an AI's answer, upload documents, and get a fact-check, all served
from free infrastructure.

---

## Updating after a deploy

- **Website changes**: push to GitHub's `main` — Vercel redeploys automatically.
- **Engine changes**: push to the `space` remote (`git push space main`) —
  the Space rebuilds automatically.

## Reverting to local-only

Nothing about deployment changes local use — `sentinel serve` +
`npm run dev` still work exactly as before on your own machine.
