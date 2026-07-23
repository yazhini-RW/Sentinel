"""Local NLI (natural language inference) verifier — free, offline, no API key.

Uses a cross-encoder fine-tuned for entailment/contradiction/neutral
(the same technique SelfCheckGPT and RAGAS-style faithfulness checkers use).
Each evidence chunk is the premise, the claim is the hypothesis:

    entailment    -> the evidence supports the claim      -> SUPPORTED
    contradiction -> the evidence opposes the claim       -> CONTRADICTED
    neutral       -> the evidence says nothing decisive   -> UNSUPPORTED
"""

from __future__ import annotations

import os
import re

import numpy as np

# base is noticeably better at paraphrase entailment than xsmall (tested);
# override with SENTINEL_NLI_MODEL=cross-encoder/nli-deberta-v3-xsmall for speed.
NLI_MODEL = os.environ.get("SENTINEL_NLI_MODEL", "cross-encoder/nli-deberta-v3-base")

# A verdict must beat this probability to count; otherwise neutral wins.
ENTAIL_THRESHOLD = 0.5
CONTRA_THRESHOLD = 0.5


class NliVerifier:
    def __init__(self, model_name: str = NLI_MODEL):
        from sentence_transformers import CrossEncoder

        self.model = CrossEncoder(model_name)
        # Label order differs between NLI checkpoints — read it from the config.
        id2label = self.model.model.config.id2label
        self.labels = {v.lower(): k for k, v in id2label.items()}

    def judge(self, claim: str, premises: list[str]) -> list[dict]:
        """Score claim against each premise. Returns per-premise probability dicts."""
        logits = self.model.predict(
            [(premise, claim) for premise in premises],
            apply_softmax=True,
            show_progress_bar=False,
        )
        probs = np.atleast_2d(np.asarray(logits))
        out = []
        for row in probs:
            out.append(
                {
                    "entailment": float(row[self.labels["entailment"]]),
                    "contradiction": float(row[self.labels["contradiction"]]),
                    "neutral": float(row[self.labels["neutral"]]),
                }
            )
        return out

    def _best_entailment(self, claim: str, premises: list[str]) -> tuple[float, int]:
        """Best entailment for the claim, checking each chunk AND its individual
        sentences. A long multi-topic chunk dilutes the NLI entailment signal for
        a specific claim (the model returns 'neutral'), so the one sentence that
        actually supports the claim is given a chance to score on its own.
        Contradiction is NOT computed here — sentence-level contradiction is noisy
        (a neighbouring off-topic sentence easily reads as 'contradiction'), so
        that stays at whole-chunk level in verify()."""
        candidates: list[str] = []
        owner: list[int] = []  # which chunk each candidate premise belongs to
        for i, premise in enumerate(premises):
            candidates.append(premise)
            owner.append(i)
            sentences = re.split(r"(?<=[.!?])\s+", premise)
            if len(sentences) > 1:
                for sent in sentences:
                    if len(sent.split()) >= 4:
                        candidates.append(sent)
                        owner.append(i)
        scores = self.judge(claim, candidates)
        best = max(range(len(scores)), key=lambda j: scores[j]["entailment"])
        return scores[best]["entailment"], owner[best]

    def verify(self, claim: str, premises: list[str]) -> tuple[str, str, float, int]:
        """Aggregate over evidence. Returns (verdict, reason, confidence, best_idx).

        Any single strongly-entailing chunk (or sentence within it) is enough to
        support; contradiction only wins if no evidence entails more strongly.
        """
        if not premises:
            return "UNSUPPORTED", "No evidence was retrieved for this claim.", 0.0, -1
        scores = self.judge(claim, premises)
        best_con_idx = max(range(len(scores)), key=lambda i: scores[i]["contradiction"])
        best_con = scores[best_con_idx]["contradiction"]
        best_ent, best_ent_idx = self._best_entailment(claim, premises)

        if best_ent >= ENTAIL_THRESHOLD and best_ent >= best_con:
            return (
                "SUPPORTED",
                f"Evidence entails the claim with {best_ent:.0%} NLI confidence",
                best_ent,
                best_ent_idx,
            )
        if best_con >= CONTRA_THRESHOLD:
            return (
                "CONTRADICTED",
                f"Evidence contradicts the claim with {best_con:.0%} NLI confidence",
                best_con,
                best_con_idx,
            )
        neutral = max(s["neutral"] for s in scores)
        return (
            "UNSUPPORTED",
            f"No evidence decisively confirms or denies the claim (best entailment {best_ent:.0%})",
            neutral,
            best_ent_idx,
        )


_verifier: NliVerifier | None = None


def get_nli_verifier() -> NliVerifier | None:
    """Lazy singleton; returns None if the model can't be loaded."""
    global _verifier
    if _verifier is None:
        try:
            _verifier = NliVerifier()
        except Exception as e:
            import sys

            print(f"[sentinel] NLI model unavailable ({type(e).__name__}: {e})", file=sys.stderr)
            return None
    return _verifier
