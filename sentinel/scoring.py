"""Combine per-claim verdicts into a 0-100 trust score.

SUPPORTED = 1.0 credit, UNSUPPORTED = 0.3 (unverifiable, not proven false),
CONTRADICTED = 0.0. The score is the weighted mean scaled to 0-100.
"""

from __future__ import annotations

from .verifier import Verdict

_CREDIT = {"SUPPORTED": 1.0, "UNSUPPORTED": 0.3, "CONTRADICTED": 0.0}


def trust_score(verdicts: list[Verdict]) -> float:
    if not verdicts:
        return 0.0
    total = sum(_CREDIT[v.verdict] for v in verdicts)
    return round(100 * total / len(verdicts), 1)


def verdict_counts(verdicts: list[Verdict]) -> dict[str, int]:
    counts = {"SUPPORTED": 0, "CONTRADICTED": 0, "UNSUPPORTED": 0}
    for v in verdicts:
        counts[v.verdict] += 1
    return counts
