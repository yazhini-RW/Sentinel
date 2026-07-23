"""Tests for sentinel.report — HTML report generation and writing.

Pure string-level tests: no models, no network, no server.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from sentinel.report import generate_html_report, write_report


def _make_log(**overrides) -> dict:
    """A minimal but complete run log, overridable per test."""
    log = {
        "timestamp": "2026-07-17T00:00:00+00:00",
        "run_id": "run_20260717_000000_000000",
        "input": {
            "question": "What is the capacity of the station?",
            "answer": "The station has a capacity of 480 megawatts.",
            "sources_folder": "samples/docs",
        },
        "config": {"top_k": 3, "verifier": "mock", "gemini_enabled": False, "cache": True},
        "steps": {
            "index": {
                "documents": ["plant.txt"],
                "num_chunks": 1,
                "embedder": "hashing-tfidf-fallback-512",
                "chunks": [],
            },
            "verification": [
                {
                    "claim": "The station has a capacity of 480 megawatts.",
                    "verdict": "SUPPORTED",
                    "reason": "Key terms appear in plant.txt.",
                    "method": "mock",
                    "confidence": 0.9,
                    "evidence": [
                        {
                            "chunk_id": 0,
                            "doc": "plant.txt",
                            "text": (
                                "The station has a capacity of 480 megawatts. "
                                "Robots clean the panels at night."
                            ),
                            "bm25_score": 1.0,
                            "vector_score": 0.9,
                            "hybrid_score": 0.95,
                        }
                    ],
                }
            ],
        },
        "result": {
            "trust_score": 100.0,
            "verdict_counts": {"SUPPORTED": 1, "CONTRADICTED": 0, "UNSUPPORTED": 0},
            "elapsed_seconds": 0.5,
        },
    }
    log.update(overrides)
    return log


class TestGenerateHtmlReport(unittest.TestCase):
    def test_hostile_content_is_escaped(self):
        """Claims, evidence, question and doc names are untrusted text: raw
        <script> / <img onerror=...> markup must never survive unescaped."""
        log = _make_log()
        log["input"]["question"] = '<script>alert("question")</script> what is it?'
        log["input"]["answer"] = 'answer with <script>alert("answer")</script>'
        log["steps"]["index"]["documents"] = ['<script>docs</script>.txt']
        item = log["steps"]["verification"][0]
        item["claim"] = 'hostile claim <script>alert("claim")</script> here'
        item["reason"] = 'reason <img src=x onerror=alert(1)> text'
        item["evidence"][0]["doc"] = '<b>evil</b>.txt'
        item["evidence"][0]["text"] = (
            'hostile claim <script>alert("claim")</script> here. '
            "Another sentence with <img src=x onerror=alert(2)> markup."
        )

        out = generate_html_report(log)

        self.assertNotIn("<script", out)
        self.assertNotIn("<img", out)
        self.assertNotIn("<b>evil</b>", out)
        # The content is still there — escaped, not dropped.
        self.assertIn("&lt;script&gt;", out)
        self.assertIn("&lt;img", out)

    def test_hostile_text_inside_mark_is_escaped(self):
        """The best-match sentence goes through the <mark> path, which escapes
        per-part; hostile markup in that sentence must come out escaped too."""
        log = _make_log()
        item = log["steps"]["verification"][0]
        item["claim"] = "hostile payload <script>alert(1)</script> claim"
        item["evidence"][0]["text"] = (
            "hostile payload <script>alert(1)</script> claim. Unrelated filler here."
        )

        out = generate_html_report(log)

        self.assertNotIn("<script", out)
        self.assertIn("<mark>", out)
        marked = out.split("<mark>", 1)[1].split("</mark>", 1)[0]
        self.assertIn("&lt;script&gt;", marked)

    def test_none_trust_score_renders_na_gauge(self):
        log = _make_log(
            result={"trust_score": None, "verdict_counts": {}, "note": "no claims extracted"}
        )
        out = generate_html_report(log)
        self.assertIn("gauge-na", out)
        self.assertIn(">n/a<", out)

    def test_empty_log_dict_does_not_crash(self):
        out = generate_html_report({})
        self.assertTrue(out.startswith("<!DOCTYPE html>"))
        self.assertIn("gauge-na", out)  # no result -> score is None
        self.assertIn("No verifiable factual claims", out)

    def test_best_matching_evidence_sentence_is_marked(self):
        out = generate_html_report(_make_log())
        self.assertIn(
            "<mark>The station has a capacity of 480 megawatts.</mark>", out
        )
        # The non-matching sentence is present but NOT wrapped in <mark>.
        self.assertIn("Robots clean the panels at night.", out)
        self.assertNotIn("<mark>Robots", out)

    def test_no_mark_when_nothing_overlaps(self):
        log = _make_log()
        log["steps"]["verification"][0]["evidence"][0]["text"] = (
            "Completely unrelated words about zebras dancing tango."
        )
        out = generate_html_report(log)
        self.assertNotIn("<mark>", out)


class TestWriteReport(unittest.TestCase):
    def test_writes_utf8_html_next_to_json_path(self):
        tmpdir = Path(tempfile.mkdtemp(prefix="sentinel_report_test_"))
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        json_path = tmpdir / "run_20260717_000000_000000.json"

        log = _make_log()
        log["input"]["question"] = "Où est le café — señor?"  # non-ASCII round trip
        out = write_report(log, json_path)

        self.assertEqual(out, json_path.with_suffix(".html"))
        self.assertEqual(out.parent, json_path.parent)
        self.assertTrue(out.is_file())

        raw = out.read_bytes()
        text = raw.decode("utf-8")  # must be valid UTF-8 (raises otherwise)
        self.assertIn("Où est le café — señor?", text)
        self.assertIn("<!DOCTYPE html>", text)

    def test_accepts_string_path(self):
        tmpdir = Path(tempfile.mkdtemp(prefix="sentinel_report_test_"))
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        json_path = tmpdir / "run_1.json"
        out = write_report(_make_log(), str(json_path))
        self.assertEqual(out, tmpdir / "run_1.html")
        self.assertTrue(out.is_file())


if __name__ == "__main__":
    unittest.main()
