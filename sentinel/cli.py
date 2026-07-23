"""Sentinel CLI.

Subcommands:
    sentinel verify --question ... --answer ... --sources DIR   (fact-check)
    sentinel report LOG.json                                    (rebuild HTML report)
    sentinel serve [--host --port]                              (web API + UI backend)
    sentinel eval [--verifiers nli,mock]                        (accuracy harness)

`python -m sentinel --question ...` (the v1 form) still works — it is
rewritten to the `verify` subcommand for backward compatibility.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .chunker import chunk_documents, load_documents
from .claims import contextualize_query, split_claims
from .embedder import CachedEmbedder, get_embedder
from .llm import gemini_available
from .report import report_from_json_file, write_report
from .retrieval import HybridIndex
from .scoring import trust_score, verdict_counts
from .verifier import verify_claim

_VERDICT_MARK = {"SUPPORTED": "[+]", "CONTRADICTED": "[X]", "UNSUPPORTED": "[?]"}


def _describe_mode(verifier: str) -> str:
    if verifier == "auto":
        return "Gemini (free tier)" if gemini_available() else "local NLI model (offline)"
    return {"gemini": "Gemini (free tier)", "nli": "local NLI model (offline)", "mock": "rule-based mock"}[verifier]


def run_pipeline(
    question: str,
    answer: str,
    sources: str,
    top_k: int = 3,
    log_dir: str = "logs",
    verifier: str = "auto",
    cache: bool = True,
    quiet: bool = False,
    html_report: bool = True,
) -> dict:
    """Run the full pipeline. Returns the run log dict (also saved to log_dir)."""

    def say(msg: str = "") -> None:
        if not quiet:
            print(msg)

    t0 = time.perf_counter()
    log: dict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input": {"question": question, "answer": answer, "sources_folder": str(Path(sources).resolve())},
        "config": {"top_k": top_k, "verifier": verifier, "gemini_enabled": gemini_available(), "cache": cache},
        "steps": {},
    }

    say("Sentinel — fact-checking pipeline")
    say(f"Verifier: {_describe_mode(verifier)}\n")

    # 1-2. Load, chunk, embed, index
    docs = load_documents(sources)
    chunks = chunk_documents(docs)
    say(f"Indexed {len(docs)} documents -> {len(chunks)} chunks.")
    cache_path = Path(log_dir) / "embedding_cache.db" if cache else None
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
    embedder = get_embedder(cache_path)
    index = HybridIndex(chunks, embedder)
    log["steps"]["index"] = {
        "documents": list(docs),
        "num_chunks": len(chunks),
        "embedder": embedder.name,
        "chunks": [{"chunk_id": c.chunk_id, "doc": c.doc_name, "text": c.text} for c in chunks],
    }

    # 3. Claim splitting
    claims, split_method = split_claims(question, answer)
    log["steps"]["claim_splitting"] = {"method": split_method, "claims": claims}
    if not claims:
        say("\nNo verifiable factual claims found in the answer — nothing to check.")
        log["result"] = {"trust_score": None, "verdict_counts": verdict_counts([]), "note": "no claims extracted"}
        _finalize(log, log_dir, html_report, say)
        return log
    say(f"Split answer into {len(claims)} claims ({split_method}).\n")

    # 4-5. Retrieval + verification per claim
    results = []
    for i, claim in enumerate(claims, 1):
        query = contextualize_query(claim, question)
        evidence = index.search(query, top_k=top_k)
        verdict = verify_claim(claim, evidence, mode=verifier)
        results.append(verdict)

        mark = _VERDICT_MARK[verdict.verdict]
        conf = f" (confidence {verdict.confidence:.0%})" if verdict.confidence is not None else ""
        say(f"Claim {i}: {claim}")
        say(f"  {mark} {verdict.verdict} [{verdict.method}]{conf} — {verdict.reason}")
        for h in verdict.evidence:
            snippet = h.chunk.text if len(h.chunk.text) <= 110 else h.chunk.text[:107] + "..."
            say(f"      evidence [{h.chunk.doc_name}] (hybrid {h.hybrid_score:.2f}): {snippet}")
        say()

    log["steps"]["verification"] = [
        {
            "claim": v.claim,
            "retrieval_query": contextualize_query(v.claim, question),
            "verdict": v.verdict,
            "reason": v.reason,
            "method": v.method,
            "confidence": v.confidence,
            "evidence": [
                {
                    "chunk_id": h.chunk.chunk_id,
                    "doc": h.chunk.doc_name,
                    "text": h.chunk.text,
                    "bm25_score": h.bm25_score,
                    "vector_score": h.vector_score,
                    "hybrid_score": h.hybrid_score,
                }
                for h in v.evidence
            ],
        }
        for v in results
    ]

    # 6. Score
    score = trust_score(results)
    counts = verdict_counts(results)
    log["result"] = {
        "trust_score": score,
        "verdict_counts": counts,
        "elapsed_seconds": round(time.perf_counter() - t0, 2),
    }
    if isinstance(embedder, CachedEmbedder):
        log["result"]["embedding_cache"] = {"hits": embedder.hits, "misses": embedder.misses}

    say("-" * 60)
    say(
        f"TRUST SCORE: {score}/100   "
        f"(supported {counts['SUPPORTED']}, contradicted {counts['CONTRADICTED']}, "
        f"unsupported {counts['UNSUPPORTED']})"
    )
    _finalize(log, log_dir, html_report, say)
    return log


def _finalize(log: dict, log_dir: str, html_report: bool, say) -> None:
    """Assign a run id, save the JSON log, and (optionally) the HTML report."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    log["run_id"] = run_id
    out_file = log_path / f"{run_id}.json"
    out_file.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    say(f"Run log saved to {out_file}")
    if html_report:
        report_file = write_report(log, out_file)
        say(f"HTML report saved to {report_file}")


def _positive_int(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return n


def _add_verify_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--question", required=True, help="The question that was asked")
    answer_group = p.add_mutually_exclusive_group(required=True)
    answer_group.add_argument("--answer", help="The AI-generated answer to verify")
    answer_group.add_argument("--answer-file", help="Path to a text file containing the answer")
    p.add_argument("--sources", required=True, help="Folder of .txt/.md source documents")
    p.add_argument("--top-k", type=_positive_int, default=3, help="Evidence chunks per claim (default 3)")
    p.add_argument("--log-dir", default="logs", help="Directory for JSON run logs (default ./logs)")
    p.add_argument(
        "--verifier",
        choices=["auto", "gemini", "nli", "mock"],
        default="auto",
        help="Verification tier: auto = Gemini if key set, else local NLI, else mock",
    )
    p.add_argument("--no-cache", action="store_true", help="Disable the SQLite embedding cache")
    p.add_argument("--no-html", action="store_true", help="Skip writing the HTML report")
    p.add_argument(
        "--fail-below",
        type=float,
        default=None,
        metavar="SCORE",
        help="Exit with code 2 if the trust score is below SCORE (for CI gates)",
    )


def _cmd_verify(args: argparse.Namespace) -> int:
    answer = args.answer
    if args.answer_file:
        try:
            answer = Path(args.answer_file).read_text(encoding="utf-8", errors="replace").strip()
        except OSError as e:
            print(f"Error reading --answer-file: {e}", file=sys.stderr)
            return 1

    try:
        log = run_pipeline(
            args.question, answer, args.sources, args.top_k, args.log_dir,
            verifier=args.verifier, cache=not args.no_cache, html_report=not args.no_html,
        )
    except (FileNotFoundError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    score = log["result"]["trust_score"]
    if args.fail_below is not None and (score is None or score < args.fail_below):
        print(f"FAIL: trust score {score} is below threshold {args.fail_below}", file=sys.stderr)
        return 2
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    try:
        out = report_from_json_file(args.log_json)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Error: could not build report from {args.log_json}: {e}", file=sys.stderr)
        return 1
    print(f"HTML report saved to {out}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        print(
            "Error: the web server needs FastAPI + uvicorn.\n"
            "Install them with:  pip install fastapi uvicorn python-multipart",
            file=sys.stderr,
        )
        return 1
    uvicorn.run("sentinel.api:app", host=args.host, port=args.port, log_level="info")
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    from .evalharness import run_eval

    return run_eval(
        eval_set=args.eval_set,
        sources=args.sources,
        verifiers=[v.strip() for v in args.verifiers.split(",") if v.strip()],
        top_k=args.top_k,
        log_dir=args.log_dir,
    )


def main(argv: list[str] | None = None) -> int:
    # Windows consoles often default to cp1252; force utf-8 so verdicts render.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    argv = list(sys.argv[1:] if argv is None else argv)
    # Backward compatibility: `python -m sentinel --question ...` == `verify`.
    if argv and argv[0].startswith("-") and argv[0] not in ("-h", "--help"):
        argv.insert(0, "verify")

    parser = argparse.ArgumentParser(prog="sentinel", description="Verify AI answers against source documents.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_verify = sub.add_parser("verify", help="Fact-check an answer against source documents")
    _add_verify_args(p_verify)
    p_verify.set_defaults(func=_cmd_verify)

    p_report = sub.add_parser("report", help="Rebuild the HTML report from a JSON run log")
    p_report.add_argument("log_json", help="Path to a run_*.json log file")
    p_report.set_defaults(func=_cmd_report)

    p_serve = sub.add_parser("serve", help="Start the local web API (backend for the Next.js UI)")
    p_serve.add_argument("--host", default="127.0.0.1", help="Bind host (default 127.0.0.1)")
    p_serve.add_argument("--port", type=int, default=8000, help="Port (default 8000)")
    p_serve.set_defaults(func=_cmd_serve)

    p_eval = sub.add_parser("eval", help="Measure verifier accuracy on a labeled eval set")
    p_eval.add_argument("--eval-set", default="samples/eval_set.json", help="Labeled eval set JSON")
    p_eval.add_argument("--sources", default="samples/docs", help="Source docs folder for the eval set")
    p_eval.add_argument("--verifiers", default="nli,mock", help="Comma-separated tiers to compare")
    p_eval.add_argument("--top-k", type=_positive_int, default=3)
    p_eval.add_argument("--log-dir", default="logs")
    p_eval.set_defaults(func=_cmd_eval)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
