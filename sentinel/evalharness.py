"""Accuracy eval harness: score verifier tiers against a labeled eval set.

Loads a JSON eval set of claims with gold verdicts, builds the retrieval
index over the source documents exactly once, then runs every requested
verifier tier over every case. Prints per-tier accuracy, per-label recall
and a confusion matrix, plus a cross-tier comparison line, and saves a
machine-readable JSON summary to the log directory.

Used by `python -m sentinel eval` (see cli.py).
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .chunker import chunk_documents, load_documents
from .embedder import get_embedder
from .retrieval import HybridIndex
from .verifier import VERDICTS, verify_claim

_VALID_TIERS = ("auto", "gemini", "nli", "mock")
_COL = 14  # column width fitting the longest verdict name ("CONTRADICTED")


def _fail(message: str) -> int:
    print(f"Error: {message}", file=sys.stderr)
    return 1


def _load_cases(eval_set: str) -> list[dict]:
    """Load and validate the eval set. Raises ValueError with a clear message."""
    path = Path(eval_set)
    if not path.is_file():
        raise ValueError(f"eval set not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"eval set {path} is not valid JSON: {e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
        raise ValueError(f'eval set {path} must be a JSON object with a "cases" list')
    cases = data["cases"]
    if not cases:
        raise ValueError(f"eval set {path} contains no cases")
    for i, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"case {i} must be an object, got {type(case).__name__}")
        claim = case.get("claim")
        if not isinstance(claim, str) or not claim.strip():
            raise ValueError(f'case {i} is missing a non-empty "claim" string')
        if case.get("label") not in VERDICTS:
            raise ValueError(
                f"case {i} has invalid label {case.get('label')!r} "
                f"(expected one of: {', '.join(VERDICTS)})"
            )
    return cases


def _score_tier(tier: str, cases: list[dict], evidence: list, case_rows: list[dict]) -> dict:
    """Run one verifier tier over every case; returns the tier's stats dict."""
    t0 = time.perf_counter()
    confusion = {gold: {pred: 0 for pred in VERDICTS} for gold in VERDICTS}
    for case, hits, row in zip(cases, evidence, case_rows):
        predicted = verify_claim(case["claim"], hits, mode=tier).verdict
        row["predicted"][tier] = predicted
        confusion[case["label"]][predicted] += 1

    correct = sum(confusion[v][v] for v in VERDICTS)
    recall = {}
    for gold in VERDICTS:
        total = sum(confusion[gold].values())
        recall[gold] = round(confusion[gold][gold] / total, 4) if total else None
    return {
        "accuracy": round(correct / len(cases), 4),
        "correct": correct,
        "total": len(cases),
        "per_label_recall": recall,
        "confusion_matrix": confusion,
        "elapsed_seconds": round(time.perf_counter() - t0, 2),
    }


def _print_tier_report(tier: str, stats: dict, cases: list[dict], case_rows: list[dict]) -> None:
    confusion = stats["confusion_matrix"]
    print()
    print("=" * 60)
    print(
        f"Tier '{tier}': accuracy {stats['correct']}/{stats['total']} "
        f"= {stats['accuracy']:.1%}   ({stats['elapsed_seconds']}s)"
    )
    print("\n  Per-label recall:")
    for gold in VERDICTS:
        total = sum(confusion[gold].values())
        recall = stats["per_label_recall"][gold]
        shown = "n/a" if recall is None else f"{recall:.1%}"
        print(f"    {gold:<{_COL}} {confusion[gold][gold]}/{total}  ({shown})")

    print("\n  Confusion matrix (rows = gold, columns = predicted):")
    print("    " + " " * _COL + "".join(f"{pred:>{_COL}}" for pred in VERDICTS))
    for gold in VERDICTS:
        cells = "".join(f"{confusion[gold][pred]:>{_COL}}" for pred in VERDICTS)
        print(f"    {gold:<{_COL}}{cells}")

    misses = [
        (case["claim"], case["label"], row["predicted"][tier])
        for case, row in zip(cases, case_rows)
        if row["predicted"][tier] != case["label"]
    ]
    if misses:
        print(f"\n  Misclassified ({len(misses)}):")
        for claim, gold, predicted in misses:
            text = claim if len(claim) <= 72 else claim[:69] + "..."
            print(f"    gold {gold:<13} pred {predicted:<13} {text}")


def run_eval(
    eval_set: str,
    sources: str,
    verifiers: list[str],
    top_k: int = 3,
    log_dir: str = "logs",
) -> int:
    """Run every verifier tier over the labeled eval set. Returns 0 ok, 1 error."""
    try:
        cases = _load_cases(eval_set)
    except ValueError as e:
        return _fail(str(e))

    if not verifiers:
        return _fail("no verifier tiers given (try --verifiers nli,mock)")
    unknown = [v for v in verifiers if v not in _VALID_TIERS]
    if unknown:
        return _fail(
            f"unknown verifier tier(s): {', '.join(unknown)} "
            f"(choose from: {', '.join(_VALID_TIERS)})"
        )
    verifiers = list(dict.fromkeys(verifiers))  # dedupe, keep order

    # Load, chunk, embed and index the sources exactly once for all tiers.
    try:
        docs = load_documents(sources)
    except FileNotFoundError as e:
        return _fail(str(e))
    chunks = chunk_documents(docs)
    embedder = get_embedder(None)
    index = HybridIndex(chunks, embedder)

    print("Sentinel eval harness")
    print(f"Eval set: {eval_set} ({len(cases)} cases)")
    print(f"Sources:  {len(docs)} documents -> {len(chunks)} chunks  [{embedder.name}]")
    print(f"Tiers:    {', '.join(verifiers)}   (top_k={top_k})")

    # Retrieval does not depend on the tier: search once per case, reuse.
    evidence = [index.search(case["claim"], top_k=top_k) for case in cases]

    case_rows = [{"claim": c["claim"], "gold": c["label"], "predicted": {}} for c in cases]
    tier_stats: dict[str, dict] = {}
    for tier in verifiers:
        try:
            tier_stats[tier] = _score_tier(tier, cases, evidence, case_rows)
        except RuntimeError as e:  # includes GeminiError; e.g. nli model missing
            return _fail(f"verifier tier '{tier}' failed: {e}")
        _print_tier_report(tier, tier_stats[tier], cases, case_rows)

    print()
    print("Comparison: " + " vs ".join(f"{t}: {s['accuracy']:.1%}" for t, s in tier_stats.items()))

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    out_file = log_path / f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "eval_set": str(Path(eval_set).resolve()),
        "sources": str(Path(sources).resolve()),
        "config": {
            "top_k": top_k,
            "verifiers": verifiers,
            "num_cases": len(cases),
            "embedder": embedder.name,
        },
        "tiers": tier_stats,
        "cases": case_rows,
    }
    out_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Eval summary saved to {out_file}")
    return 0
