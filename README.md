# Sentinel

**A fact-checking engine for AI answers.** Give Sentinel a question, an
AI-generated answer, and a folder of trusted documents — it tells you, claim
by claim and with cited evidence, what is supported, what is contradicted,
and what is unverifiable, plus one overall trust score (0–100).

Everything runs locally and free: hand-built BM25 + local sentence-transformer
embeddings for retrieval, and a local natural-language-inference model for
verification. No paid APIs required; an optional free Gemini key upgrades
claim splitting and verification.

## Quick start

```powershell
pip install -e ".[api]"          # from the repo root
sentinel verify `
  --question "Tell me about the Aurora Solar Array." `
  --answer "The Aurora Solar Array is in the Atacama Desert in Chile. It has an installed capacity of 950 megawatts." `
  --sources samples/docs
```

You get a console report, a JSON trace in `logs/`, and a **self-contained
HTML report** (`logs/run_*.html`) you can open by double-click or send to
anyone. First run downloads two models (~800 MB total); after that it's
fully offline.

## The web app

```powershell
sentinel serve                   # API on http://127.0.0.1:8000
cd web; npm install; npm run dev # UI on http://localhost:3000
```

Open the UI, type a question, paste the AI answer, upload `.txt`/`.md`
documents (or point at a folder on disk), and watch it get fact-checked.
The History page lists every past run with scores; click into any run for
the full claim-by-claim breakdown.

## All commands

| Command | What it does |
|---|---|
| `sentinel verify --question ... --answer ... --sources DIR` | Fact-check (also: `--answer-file`, `--verifier auto\|gemini\|nli\|mock`, `--top-k N`, `--fail-below SCORE` for CI gates, `--no-html`, `--no-cache`, `--log-dir`) |
| `sentinel report logs\run_X.json` | Rebuild the HTML report from a saved log |
| `sentinel serve [--host --port]` | Start the local web API (backend for the UI) |
| `sentinel eval [--verifiers nli,mock]` | Measure verifier accuracy on the labeled eval set — prints per-tier accuracy and confusion matrices |
| `python -m sentinel --question ...` | v1-style invocation, still works |

## How the pipeline works

1. **Index** — docs are cleaned of markdown, split into sentence-aware
   overlapping chunks, embedded locally (`all-MiniLM-L6-v2`), and cached in
   SQLite so unchanged docs are never re-embedded.
2. **Claim splitting** — the answer becomes atomic factual claims (Gemini
   free tier if `GEMINI_API_KEY` is set, else rule-based).
3. **Evidence retrieval** — per claim, hybrid search over chunks: Okapi BM25
   (implemented from scratch) + cosine similarity, min-max normalized, 40/60
   weighted. Pronoun-heavy claims get the question's content words appended
   so retrieval knows the subject.
4. **Verification** — three tiers, best available wins: `gemini` (LLM
   judgment) → `nli` (local entailment model: entailment ⇒ SUPPORTED,
   contradiction ⇒ CONTRADICTED, neutral ⇒ UNSUPPORTED) → `mock` (keyword
   heuristics). A **relevance gate** blocks a known NLI failure mode:
   evidence can only contradict a claim if it's semantically about the same
   subject (cosine ≥ 0.4).
5. **Scoring** — supported = 1.0, unsupported = 0.3, contradicted = 0.0,
   averaged × 100.
6. **Tracing** — every run logs every step (chunks, retrieval scores per
   evidence hit, verdicts, confidences) to JSON + HTML.

## Web API

`sentinel serve` exposes:

- `GET /health` — liveness + active verifier tier
- `POST /verify` — multipart form: `question`, `answer`, `verifier`, `top_k`,
  plus uploaded `files` (max 20 × 2 MB, `.txt`/`.md`) and/or a local
  `sources_path`. Returns the full run log JSON.
- `GET /runs?limit=50` — run history, newest first
- `GET /runs/{run_id}` — one run's full log
- `GET /runs/{run_id}/report` — the stored HTML report

The server loads models once at startup and serializes pipeline runs (it's a
local single-user product by design; bind stays on 127.0.0.1).

## Testing & evaluation

```powershell
python -m unittest discover -s tests -v   # unit tests
sentinel eval --verifiers nli,mock        # accuracy on the labeled eval set
```

The eval set (`samples/eval_set.json`) contains 24 labeled claims — supported
(including hard paraphrases), contradicted (wrong numbers, negations, wrong
entities), and unsupported (plausible but absent) — all grounded in
`samples/docs`. It exists to prove with numbers that semantic (NLI)
verification beats keyword matching. Current results:

| Verifier | Accuracy | SUPPORTED recall | CONTRADICTED recall | UNSUPPORTED recall |
|---|---|---|---|---|
| `nli` (local, offline) | **83.3%** | 62.5% | 87.5% | 100% |
| `mock` (keywords) | 62.5% | 50.0% | 37.5% | 100% |

Neither tier ever hallucinates support for an absent fact (UNSUPPORTED
recall 100%); the NLI tier's remaining misses are hard paraphrases and
chunks that reference the subject only by pronoun — both documented in the
eval JSON output for future tuning.

## Project layout

```
sentinel/
  chunker.py     # loading, markdown cleanup, sentence-aware chunking
  embedder.py    # MiniLM embeddings + SQLite cache (+ offline fallback)
  retrieval.py   # BM25 from scratch + hybrid search
  claims.py      # claim splitting + pronoun-aware retrieval queries
  verifier.py    # verdict cascade (gemini → nli → mock) + relevance gate
  nli.py         # local entailment cross-encoder
  scoring.py     # trust score
  report.py      # self-contained HTML report
  api.py         # FastAPI backend for the web UI
  evalharness.py # accuracy measurement against the labeled eval set
  llm.py         # minimal Gemini REST client (no SDK)
  cli.py         # subcommands: verify / report / serve / eval
web/             # Next.js UI (verify form, results, history)
samples/         # demo docs + labeled eval set
tests/           # unit tests
```

## Configuration

- `GEMINI_API_KEY` — optional; enables the Gemini tier (free at
  https://aistudio.google.com/apikey)
- `GEMINI_MODEL` — default `gemini-2.0-flash`
- `SENTINEL_NLI_MODEL` — default `cross-encoder/nli-deberta-v3-base`;
  set `cross-encoder/nli-deberta-v3-xsmall` for a smaller/faster model
- `NEXT_PUBLIC_API_URL` (web UI) — default `http://127.0.0.1:8000`

Deferred to later versions: reranker model, real vector database, cloud
deployment, multi-user auth.
