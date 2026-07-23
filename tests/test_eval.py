"""Tests for sentinel.evalharness.run_eval.

Uses a tiny synthetic corpus + eval set in a temp dir and only the "mock"
verifier tier, so no NLI inference runs. stdout/stderr are captured to keep
the test output clean (the harness prints its report).
"""

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from sentinel.evalharness import run_eval

DOCS = {
    "plant.txt": (
        "The Aurora station is located in the Atacama Desert in Chile. "
        "The station has an installed capacity of 480 megawatts."
    ),
    "ops.txt": (
        "Robots clean the panels at night to save water. "
        "The cleaning system needs very little maintenance."
    ),
    "history.txt": "Construction of the station began in 2016 and finished in 2019.",
}

CASES = [
    {"claim": "The Aurora station is located in the Atacama Desert.", "label": "SUPPORTED"},
    {"claim": "Robots clean the panels at night to save water.", "label": "SUPPORTED"},
    {"claim": "The station has an installed capacity of 950 megawatts.", "label": "CONTRADICTED"},
    {"claim": "The plant won a famous international engineering award.", "label": "UNSUPPORTED"},
]

VERDICTS = ("SUPPORTED", "CONTRADICTED", "UNSUPPORTED")


class TestRunEval(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sentinel_eval_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.docs_dir = self.tmp / "docs"
        self.docs_dir.mkdir()
        for name, text in DOCS.items():
            (self.docs_dir / name).write_text(text, encoding="utf-8")
        self.log_dir = self.tmp / "logs"

    def _write_eval_set(self, cases) -> str:
        path = self.tmp / "eval_set.json"
        path.write_text(json.dumps({"cases": cases}), encoding="utf-8")
        return str(path)

    def _run(self, eval_set, sources=None, verifiers=("mock",)):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = run_eval(
                eval_set=eval_set,
                sources=str(self.docs_dir) if sources is None else sources,
                verifiers=list(verifiers),
                top_k=3,
                log_dir=str(self.log_dir),
            )
        return rc, out.getvalue(), err.getvalue()

    def _eval_files(self):
        return list(self.log_dir.glob("eval_*.json")) if self.log_dir.is_dir() else []

    # ------------------------------------------------------------ happy path

    def test_happy_path_returns_0_and_writes_summary(self):
        rc, out, err = self._run(self._write_eval_set(CASES))
        self.assertEqual(rc, 0, f"stderr: {err}")

        files = self._eval_files()
        self.assertEqual(len(files), 1, f"expected one eval_*.json, got {files}")
        summary = json.loads(files[0].read_text(encoding="utf-8"))

        self.assertEqual(summary["config"]["verifiers"], ["mock"])
        self.assertEqual(summary["config"]["num_cases"], len(CASES))

        stats = summary["tiers"]["mock"]
        self.assertIn("accuracy", stats)
        self.assertIsInstance(stats["accuracy"], float)
        self.assertGreaterEqual(stats["accuracy"], 0.0)
        self.assertLessEqual(stats["accuracy"], 1.0)
        self.assertEqual(stats["total"], len(CASES))
        self.assertEqual(stats["correct"], round(stats["accuracy"] * len(CASES)))
        for verdict in VERDICTS:
            self.assertIn(verdict, stats["per_label_recall"])
            self.assertIn(verdict, stats["confusion_matrix"])

        # The mock heuristic resolves this tiny, unambiguous set perfectly.
        self.assertEqual(stats["accuracy"], 1.0)

        self.assertEqual(len(summary["cases"]), len(CASES))
        for row, case in zip(summary["cases"], CASES):
            self.assertEqual(row["gold"], case["label"])
            self.assertIn(row["predicted"]["mock"], VERDICTS)

        self.assertIn("accuracy", out)  # human report printed to stdout

    # ------------------------------------------------------------ error paths

    def test_invalid_label_returns_1_without_raising(self):
        cases = [CASES[0], {"claim": "Some claim about the station.", "label": "MAYBE"}]
        rc, _, err = self._run(self._write_eval_set(cases))
        self.assertEqual(rc, 1)
        self.assertIn("invalid label", err)
        self.assertEqual(self._eval_files(), [])

    def test_missing_eval_set_returns_1(self):
        rc, _, err = self._run(str(self.tmp / "does_not_exist.json"))
        self.assertEqual(rc, 1)
        self.assertIn("eval set not found", err)
        self.assertEqual(self._eval_files(), [])

    def test_missing_sources_folder_returns_1(self):
        rc, _, err = self._run(
            self._write_eval_set(CASES), sources=str(self.tmp / "no_such_docs")
        )
        self.assertEqual(rc, 1)
        self.assertIn("Source folder not found", err)
        self.assertEqual(self._eval_files(), [])

    def test_unknown_verifier_tier_returns_1(self):
        rc, _, err = self._run(self._write_eval_set(CASES), verifiers=("turbo",))
        self.assertEqual(rc, 1)
        self.assertIn("unknown verifier tier", err)
        self.assertEqual(self._eval_files(), [])


if __name__ == "__main__":
    unittest.main()
