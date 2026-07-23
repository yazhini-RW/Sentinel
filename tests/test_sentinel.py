"""Unit tests for the hand-built pipeline pieces (run: python -m pytest or python -m unittest)."""

import os
import shutil
import tempfile
import unittest
from unittest import mock

import numpy as np

from sentinel.chunker import Chunk, chunk_documents, load_documents, _strip_markdown
from sentinel.claims import contextualize_query
from sentinel.embedder import CachedEmbedder, HashingTfidfEmbedder
from sentinel.retrieval import BM25, EvidenceHit, HybridIndex, tokenize
from sentinel.scoring import trust_score
from sentinel.verifier import (
    RELEVANCE_GATE,
    Verdict,
    _mock_verify,
    _nli_verify,
    _numbers,
    verify_claim,
)


def _hit(text, doc="d.txt", vector_score=1.0):
    return EvidenceHit(Chunk(0, doc, text), 1.0, vector_score, 1.0)


class TestChunker(unittest.TestCase):
    def test_chunking_respects_paragraphs_and_size(self):
        docs = {"a.txt": ("One sentence here. " * 30) + "\n\nSecond paragraph."}
        chunks = chunk_documents(docs, max_words=40)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c.text.split()) <= 60 for c in chunks))
        self.assertEqual(chunks[-1].text, "Second paragraph.")


class TestStripMarkdown(unittest.TestCase):
    def test_headings_removed_words_kept(self):
        out = _strip_markdown("## Solar Capacity\nPlain text line.")
        self.assertNotIn("#", out)
        self.assertIn("Solar Capacity", out)
        self.assertIn("Plain text line.", out)

    def test_bullets_removed_words_kept(self):
        out = _strip_markdown("- first item\n* second item\n+ third item")
        for marker in ("-", "*", "+"):
            self.assertNotIn(marker, out)
        self.assertIn("first item", out)
        self.assertIn("second item", out)
        self.assertIn("third item", out)

    def test_emphasis_and_inline_code_removed_words_kept(self):
        out = _strip_markdown("The plant is **very large** and *modern*, run by `robots`.")
        self.assertNotIn("*", out)
        self.assertNotIn("`", out)
        self.assertIn("very large", out)
        self.assertIn("modern", out)
        self.assertIn("robots", out)

    def test_markdown_stripped_before_chunking(self):
        docs = {"a.md": "# Heading\n\n- The station has **480** megawatts of capacity."}
        chunks = chunk_documents(docs)
        joined = " ".join(c.text for c in chunks)
        self.assertNotIn("#", joined)
        self.assertNotIn("*", joined)
        self.assertIn("480", joined)
        self.assertIn("Heading", joined)


class TestTokenize(unittest.TestCase):
    def test_unicode_tokens_keep_accents(self):
        self.assertEqual(tokenize("café"), ["café"])

    def test_commas_inside_numbers_are_stripped(self):
        toks = tokenize("costs 1,200 dollars")
        self.assertIn("1200", toks)
        self.assertNotIn("1", toks)
        self.assertNotIn("200", toks)

    def test_stopwords_still_removed(self):
        self.assertEqual(tokenize("the cat sat on the mat"), ["cat", "sat", "mat"])


class TestBM25(unittest.TestCase):
    def test_relevant_doc_scores_highest(self):
        corpus = [
            tokenize("the cat sat on the mat"),
            tokenize("solar power station in chile"),
            tokenize("dogs bark loudly at night"),
        ]
        bm25 = BM25(corpus)
        scores = bm25.score(tokenize("solar station chile"))
        self.assertEqual(int(scores.argmax()), 1)

    def test_unknown_terms_score_zero(self):
        bm25 = BM25([tokenize("alpha beta"), tokenize("gamma delta")])
        self.assertEqual(bm25.score(tokenize("zzz qqq")).sum(), 0.0)

    def test_empty_corpus_returns_empty_scores(self):
        bm25 = BM25([])
        scores = bm25.score(tokenize("anything at all"))
        self.assertIsInstance(scores, np.ndarray)
        self.assertEqual(len(scores), 0)


class TestHybridIndex(unittest.TestCase):
    def test_search_returns_topical_chunk_first(self):
        chunks = [
            Chunk(0, "a.txt", "The plant has an installed capacity of 480 megawatts."),
            Chunk(1, "b.txt", "Robots clean the panels at night to save water."),
        ]
        index = HybridIndex(chunks, HashingTfidfEmbedder())
        hits = index.search("What is the installed capacity in megawatts?", top_k=2)
        self.assertEqual(hits[0].chunk.chunk_id, 0)


class TestContextualizeQuery(unittest.TestCase):
    def test_pronoun_claim_gets_question_content_words(self):
        claim = "It has an installed capacity of 950 megawatts."
        question = "What is the total capacity of the Cerro Dominador solar plant?"
        out = contextualize_query(claim, question)
        self.assertTrue(out.startswith(claim))
        self.assertNotEqual(out, claim)
        self.assertIn("Cerro", out)
        self.assertIn("Dominador", out)
        self.assertIn("solar", out)
        # Words already present in the claim are not appended again.
        self.assertEqual(out.count("capacity"), 1)

    def test_claim_without_pronouns_unchanged(self):
        claim = "Chile completed construction of a large solar station in 2021."
        question = "When was the Cerro Dominador solar plant finished?"
        self.assertEqual(contextualize_query(claim, question), claim)


class TestCachedEmbedder(unittest.TestCase):
    def test_second_embed_is_all_cache_hits_and_identical(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        db_path = os.path.join(tmpdir, "cache.db")

        emb = CachedEmbedder(HashingTfidfEmbedder(), db_path)
        self.addCleanup(emb.db.close)  # close before rmtree (LIFO cleanup)

        texts = [
            "solar power station in chile",
            "robots clean the panels at night",
            "the cat sat on the mat",
        ]
        first = emb.embed(texts)
        self.assertEqual(emb.hits, 0)
        self.assertEqual(emb.misses, len(texts))

        second = emb.embed(texts)
        self.assertEqual(emb.hits, len(texts))
        self.assertEqual(emb.misses, len(texts))  # no new misses
        np.testing.assert_array_equal(first, second)

    def test_cache_persists_across_instances(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        db_path = os.path.join(tmpdir, "cache.db")
        texts = ["alpha beta gamma", "delta epsilon"]

        emb1 = CachedEmbedder(HashingTfidfEmbedder(), db_path)
        self.addCleanup(emb1.db.close)
        first = emb1.embed(texts)

        emb2 = CachedEmbedder(HashingTfidfEmbedder(), db_path)
        self.addCleanup(emb2.db.close)
        second = emb2.embed(texts)
        self.assertEqual(emb2.hits, len(texts))
        self.assertEqual(emb2.misses, 0)
        np.testing.assert_array_equal(first, second)


class TestMockVerifier(unittest.TestCase):
    def test_supported(self):
        v, _ = _mock_verify(
            "The station is located in the Atacama Desert.",
            [_hit("The station is located in the Atacama Desert in Chile.")],
        )
        self.assertEqual(v, "SUPPORTED")

    def test_contradicted_on_number_mismatch(self):
        v, _ = _mock_verify(
            "It has an installed capacity of 950 megawatts.",
            [_hit("It has an installed capacity of 480 megawatts.")],
        )
        self.assertEqual(v, "CONTRADICTED")

    def test_unsupported_on_low_overlap(self):
        v, _ = _mock_verify(
            "The plant won a famous international engineering award.",
            [_hit("Robots clean the panels at night to save water.")],
        )
        self.assertEqual(v, "UNSUPPORTED")

    def test_stray_negation_in_other_sentence_does_not_contradict(self):
        # Sentence-level matching: the 'not' lives in an unrelated sentence of
        # the same chunk and must not flip the verdict to CONTRADICTED.
        v, _ = _mock_verify(
            "The station is located in the Atacama Desert.",
            [
                _hit(
                    "The station is located in the Atacama Desert in Chile. "
                    "It does not rain much in the region."
                )
            ],
        )
        self.assertEqual(v, "SUPPORTED")

    def test_negation_in_matching_sentence_still_contradicts(self):
        v, _ = _mock_verify(
            "The station is located in the Atacama Desert.",
            [_hit("The station is not located in the Atacama Desert.")],
        )
        self.assertEqual(v, "CONTRADICTED")

    def test_comma_formatted_numbers_match(self):
        # '1,200' in the claim must equal '1200' in the evidence.
        v, _ = _mock_verify(
            "The plant has a capacity of 1,200 megawatts.",
            [_hit("The plant has a capacity of 1200 megawatts.")],
        )
        self.assertEqual(v, "SUPPORTED")

    def test_numbers_helper_normalizes_commas(self):
        self.assertEqual(_numbers("1,200 units and 3.5 percent"), {"1200", "3.5"})


class TestVerifyClaimModes(unittest.TestCase):
    def test_mode_mock_returns_mock_verdict(self):
        v = verify_claim(
            "The station is located in the Atacama Desert.",
            [_hit("The station is located in the Atacama Desert in Chile.")],
            mode="mock",
        )
        self.assertIsInstance(v, Verdict)
        self.assertEqual(v.method, "mock")
        self.assertEqual(v.verdict, "SUPPORTED")

    def test_mode_gemini_without_key_raises_runtime_error(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("GEMINI_API_KEY", None)
            with self.assertRaises(RuntimeError):
                verify_claim(
                    "The sky is blue.",
                    [_hit("The sky is blue over the desert.")],
                    mode="gemini",
                )


class _FakeNLI:
    """Stands in for NliVerifier without loading any model."""

    def __init__(self, verdict="CONTRADICTED", reason="model disagrees", confidence=0.99, best_idx=0):
        self.result = (verdict, reason, confidence, best_idx)

    def verify(self, claim, premises):
        return self.result


class TestNliRelevanceGate(unittest.TestCase):
    def test_gate_constant_is_sane(self):
        self.assertIsInstance(RELEVANCE_GATE, float)
        self.assertGreater(RELEVANCE_GATE, 0.0)
        self.assertLess(RELEVANCE_GATE, 1.0)

    def test_contradiction_below_gate_downgraded_to_unsupported(self):
        hit = _hit("Totally unrelated evidence text.", vector_score=RELEVANCE_GATE - 0.3)
        v = _nli_verify(_FakeNLI(), "The plant produces solar power.", [hit])
        self.assertEqual(v.verdict, "UNSUPPORTED")
        self.assertEqual(v.method, "nli")
        self.assertIsNone(v.confidence)
        self.assertIn("relevance", v.reason.lower())

    def test_contradiction_above_gate_stands(self):
        hit = _hit("The plant produces no solar power.", vector_score=RELEVANCE_GATE + 0.3)
        v = _nli_verify(_FakeNLI(), "The plant produces solar power.", [hit])
        self.assertEqual(v.verdict, "CONTRADICTED")
        self.assertEqual(v.method, "nli")
        self.assertEqual(v.confidence, 0.99)
        self.assertIn("d.txt", v.reason)


class TestScoring(unittest.TestCase):
    def _v(self, verdict):
        return Verdict("c", verdict, "r", [], "mock")

    def test_score_mixes_credits(self):
        vs = [self._v("SUPPORTED"), self._v("CONTRADICTED"), self._v("UNSUPPORTED")]
        self.assertEqual(trust_score(vs), 43.3)

    def test_all_supported_is_100(self):
        self.assertEqual(trust_score([self._v("SUPPORTED")] * 4), 100.0)

    def test_empty_is_0(self):
        self.assertEqual(trust_score([]), 0.0)


if __name__ == "__main__":
    unittest.main()
