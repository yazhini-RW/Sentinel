"""Self-contained HTML report generated from a run log.

One file, inline CSS, no external assets — opens offline by double-click.
All content from the log is HTML-escaped (source docs are untrusted text).
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from .retrieval import tokenize

_VERDICT_COLORS = {
    "SUPPORTED": ("#16a34a", "✓"),
    "CONTRADICTED": ("#dc2626", "✗"),
    "UNSUPPORTED": ("#6b7280", "?"),
}


def _esc(value) -> str:
    return html.escape(str(value), quote=True)


def _num(value, default=0.0) -> float:
    """Coerce a log field to float — a crafted/corrupt log must never crash
    the generator or reach an unescaped interpolation site."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _score_color(score: float) -> str:
    if score >= 80:
        return "#16a34a"
    if score >= 50:
        return "#d97706"
    return "#dc2626"


def _highlight_best_sentence(claim: str, evidence_text: str) -> str:
    """Escape the evidence text and wrap the sentence that best matches the
    claim in <mark>. Escaping happens per-part, never around our own tags."""
    sentences = re.split(r"(?<=[.!?])\s+", evidence_text)
    claim_tokens = set(tokenize(claim))
    best_i, best_overlap = -1, 0.0
    for i, sent in enumerate(sentences):
        overlap = len(claim_tokens & set(tokenize(sent))) / max(len(claim_tokens), 1)
        if overlap > best_overlap:
            best_i, best_overlap = i, overlap
    parts = []
    for i, sent in enumerate(sentences):
        if i == best_i and best_overlap > 0:
            parts.append(f"<mark>{_esc(sent)}</mark>")
        else:
            parts.append(_esc(sent))
    return " ".join(parts)


def _gauge(score: float | None) -> str:
    if score is None:
        return '<div class="gauge gauge-na">n/a</div>'
    color = _score_color(score)
    deg = round(score * 3.6, 1)
    return (
        f'<div class="gauge" style="background:'
        f"conic-gradient({color} {deg}deg, var(--gauge-rest) {deg}deg 360deg)\">"
        f'<div class="gauge-inner"><span class="gauge-num" style="color:{color}">'
        f"{score:g}</span><span class=\"gauge-sub\">/ 100</span></div></div>"
    )


def _evidence_html(claim: str, ev: dict) -> str:
    scores = (
        f"hybrid {_num(ev.get('hybrid_score')):.2f} · "
        f"bm25 {_num(ev.get('bm25_score')):.2f} · "
        f"vector {_num(ev.get('vector_score')):.2f}"
    )
    return (
        "<details class='evidence'>"
        f"<summary><span class='doc'>{_esc(ev.get('doc', '?'))}</span>"
        f"<span class='scores'>{_esc(scores)}</span></summary>"
        f"<p>{_highlight_best_sentence(claim, str(ev.get('text', '')))}</p>"
        "</details>"
    )


def _claim_card(i: int, item: dict) -> str:
    verdict = str(item.get("verdict", "UNSUPPORTED"))
    color, mark = _VERDICT_COLORS.get(verdict, _VERDICT_COLORS["UNSUPPORTED"])
    confidence = item.get("confidence")
    conf_html = ""
    if isinstance(confidence, (int, float)):
        pct = max(0, min(100, round(confidence * 100)))
        conf_html = (
            f"<div class='confbar' title='confidence {pct}%'>"
            f"<div class='conffill' style='width:{pct}%;background:{color}'></div></div>"
            f"<span class='confpct'>{pct}%</span>"
        )
    evidence = "".join(_evidence_html(str(item.get("claim", "")), ev) for ev in item.get("evidence", []))
    return f"""
    <section class="card" style="border-left-color:{color}">
      <div class="card-head">
        <span class="badge" style="background:{color}">{mark} {_esc(verdict)}</span>
        <span class="method">{_esc(item.get('method', '?'))}</span>
        {conf_html}
      </div>
      <p class="claim"><strong>Claim {i}.</strong> {_esc(item.get('claim', ''))}</p>
      <p class="reason">{_esc(item.get('reason', ''))}</p>
      {evidence}
    </section>"""


def generate_html_report(log: dict) -> str:
    result = log.get("result", {}) or {}
    score = result.get("trust_score")
    if score is not None:
        score = max(0.0, min(100.0, _num(score)))
    counts = result.get("verdict_counts", {}) or {}
    if not isinstance(counts, dict):
        counts = {}
    counts = {k: int(_num(v)) for k, v in counts.items() if k in _VERDICT_COLORS}
    inputs = log.get("input", {}) or {}
    config = log.get("config", {}) or {}
    steps = log.get("steps", {}) or {}
    verification = steps.get("verification", []) or []
    index = steps.get("index", {}) or {}

    cards = "".join(_claim_card(i, item) for i, item in enumerate(verification, 1))
    if not cards:
        cards = "<p class='empty'>No verifiable factual claims were found in the answer.</p>"

    counts_html = " · ".join(
        f"<span style='color:{_VERDICT_COLORS[k][0]}'>{counts.get(k, 0)} {k.lower()}</span>"
        for k in ("SUPPORTED", "CONTRADICTED", "UNSUPPORTED")
    )
    docs_list = ", ".join(_esc(d) for d in index.get("documents", []))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sentinel report — trust score {_esc(score if score is not None else 'n/a')}</title>
<style>
:root {{
  --bg: #f8fafc; --fg: #0f172a; --muted: #64748b; --card: #ffffff;
  --border: #e2e8f0; --gauge-rest: #e2e8f0; --mark-bg: #fef08a; --mark-fg: #111;
}}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#0b1220; --fg:#e2e8f0; --muted:#94a3b8; --card:#111a2e;
           --border:#1e293b; --gauge-rest:#1e293b; --mark-bg:#854d0e; --mark-fg:#fef9c3; }}
}}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg);
       font:15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }}
.wrap {{ max-width: 880px; margin: 0 auto; padding: 32px 20px 64px; }}
h1 {{ font-size: 22px; margin: 0 0 4px; }}
.sub {{ color: var(--muted); font-size: 13px; margin-bottom: 24px; }}
.top {{ display:flex; gap:28px; align-items:center; flex-wrap:wrap;
        background:var(--card); border:1px solid var(--border); border-radius:14px; padding:20px; }}
.gauge {{ width:120px; height:120px; border-radius:50%; display:flex;
          align-items:center; justify-content:center; flex:none; }}
.gauge-inner {{ width:92px; height:92px; border-radius:50%; background:var(--card);
                display:flex; flex-direction:column; align-items:center; justify-content:center; }}
.gauge-num {{ font-size:28px; font-weight:700; }}
.gauge-sub {{ font-size:11px; color:var(--muted); }}
.gauge-na {{ background:var(--gauge-rest); color:var(--muted); font-weight:600; }}
.qa {{ min-width: 260px; flex:1; }}
.qa p {{ margin: 6px 0; overflow-wrap:anywhere; }}
.qa .label {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
.counts {{ margin-top:10px; font-size:14px; }}
.card {{ background:var(--card); border:1px solid var(--border); border-left-width:4px;
         border-radius:12px; padding:16px 18px; margin-top:16px; }}
.card-head {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; }}
.badge {{ color:#fff; font-size:12px; font-weight:700; padding:3px 10px; border-radius:999px; }}
.method {{ color:var(--muted); font-size:12px; border:1px solid var(--border);
           padding:2px 8px; border-radius:999px; }}
.confbar {{ width:110px; height:8px; background:var(--gauge-rest); border-radius:4px; overflow:hidden; }}
.conffill {{ height:100%; }}
.confpct {{ font-size:12px; color:var(--muted); }}
.claim {{ margin:12px 0 4px; font-size:15px; overflow-wrap:anywhere; }}
.reason {{ margin:0 0 8px; color:var(--muted); font-size:13.5px; }}
.evidence {{ border-top:1px dashed var(--border); padding:8px 0 0; margin-top:8px; }}
.evidence summary {{ cursor:pointer; display:flex; gap:12px; align-items:baseline; }}
.evidence .doc {{ font-weight:600; font-size:13px; }}
.evidence .scores {{ color:var(--muted); font-size:12px; }}
.evidence p {{ margin:8px 0 4px; font-size:13.5px; overflow-wrap:anywhere; }}
mark {{ background:var(--mark-bg); color:var(--mark-fg); padding:0 2px; border-radius:3px; }}
.empty {{ color:var(--muted); font-style:italic; }}
.foot {{ margin-top:28px; color:var(--muted); font-size:12.5px; border-top:1px solid var(--border);
         padding-top:14px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Sentinel fact-check report</h1>
  <div class="sub">{_esc(log.get('timestamp', ''))} · verifier: {_esc(config.get('verifier', 'auto'))}
    · sources: {docs_list or '—'}</div>
  <div class="top">
    {_gauge(score)}
    <div class="qa">
      <p class="label">Question</p>
      <p>{_esc(inputs.get('question', ''))}</p>
      <p class="label">Answer under review</p>
      <p>{_esc(inputs.get('answer', ''))}</p>
      <div class="counts">{counts_html}</div>
    </div>
  </div>
  {cards}
  <div class="foot">
    Embedder: {_esc(index.get('embedder', '?'))} · chunks: {_esc(index.get('num_chunks', '?'))}
    · elapsed: {_esc(result.get('elapsed_seconds', '?'))}s
    · generated by Sentinel v1 — every verdict is traceable in the matching JSON log.
  </div>
</div>
</body>
</html>"""


def write_report(log: dict, json_log_path: str | Path) -> Path:
    """Write the HTML report next to its JSON log (same name, .html)."""
    out = Path(json_log_path).with_suffix(".html")
    out.write_text(generate_html_report(log), encoding="utf-8")
    return out


def report_from_json_file(json_path: str | Path) -> Path:
    log = json.loads(Path(json_path).read_text(encoding="utf-8"))
    return write_report(log, json_path)
