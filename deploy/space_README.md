---
title: Sentinel Engine
emoji: 🛡️
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Sentinel — fact-checking engine (API)

This Space runs the Sentinel backend: it verifies AI-generated answers
against uploaded source documents using hybrid retrieval (BM25 + local
embeddings) and a local NLI verification model.

This is the **API only** — it has no visual page of its own. The web
interface is a separate Next.js app (see the main repo's `web/` folder),
deployed on Vercel and pointed at this Space's URL.

- `GET /health` — liveness check
- `POST /verify` — fact-check an answer (multipart: question, answer,
  verifier, top_k, uploaded files)
- `GET /runs`, `GET /runs/{id}` — run history

Full source: https://github.com/yazhini-RW/Sentinel

Note: this Space only accepts uploaded documents, not server folder paths
(`SENTINEL_ALLOW_SOURCES_PATH=0`), since it's open to the public — a folder
path only makes sense on a private, locally-run instance.
