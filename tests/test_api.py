"""Integration tests for sentinel.api using FastAPI's TestClient.

Performance notes (deliberate):
- ONE TestClient for the whole module (setUpClass + context-manager enter) —
  the app lifespan warms the embedding + NLI models, which is expensive and
  must happen exactly once.
- Every /verify request forces verifier="mock" so no NLI inference ever runs.
- sources_path points at the small samples/docs corpus.
"""

import tempfile
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from sentinel.api import LOG_DIR, MAX_FILE_BYTES, app

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLES_DOCS = str(PROJECT_ROOT / "samples" / "docs")

QUESTION = "What is the installed capacity of the Aurora Solar Array?"
ANSWER = (
    "The Aurora Solar Array has an installed capacity of 480 megawatts. "
    "It is located in the Atacama Desert in Chile."
)
UPLOAD_TEXT = (
    b"The Aurora Solar Array has an installed capacity of 480 megawatts. "
    b"It is located in the Atacama Desert in Chile. "
    b"Robots clean the panels at night to save water."
)


class TestSentinelApi(unittest.TestCase):
    client: TestClient

    @classmethod
    def setUpClass(cls):
        # Entering the context manager runs the lifespan (model warm-up, once).
        cls._client_cm = TestClient(app)
        cls.client = cls._client_cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._client_cm.__exit__(None, None, None)

    # ------------------------------------------------------------- helpers

    def _form(self, **overrides) -> dict:
        data = {
            "question": QUESTION,
            "answer": ANSWER,
            "verifier": "mock",
            "sources_path": SAMPLES_DOCS,
        }
        data.update(overrides)
        return {k: v for k, v in data.items() if v is not None}

    def _cleanup_run(self, run_id: str) -> None:
        for suffix in (".json", ".html"):
            try:
                (LOG_DIR / run_id).with_suffix(suffix).unlink()
            except FileNotFoundError:
                pass

    # --------------------------------------------------------------- health

    def test_health_reports_ok_and_default_verifier(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        self.assertIsInstance(body["default_verifier"], str)
        self.assertTrue(body["default_verifier"])

    # --------------------------------------------------------------- verify

    def test_verify_with_sources_path_mock(self):
        resp = self.client.post("/verify", data=self._form())
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()

        run_id = body["run_id"]
        self.addCleanup(self._cleanup_run, run_id)
        self.assertTrue(run_id.startswith("run_"))

        self.assertIn("trust_score", body["result"])
        self.assertIsInstance(body["result"]["trust_score"], (int, float))

        verification = body["steps"]["verification"]
        self.assertIsInstance(verification, list)
        self.assertGreaterEqual(len(verification), 1)
        for item in verification:
            self.assertEqual(item["method"], "mock")
            self.assertIn(item["verdict"], ("SUPPORTED", "CONTRADICTED", "UNSUPPORTED"))

        # Both artifacts were persisted to the log directory.
        self.assertTrue((LOG_DIR / run_id).with_suffix(".json").is_file())
        self.assertTrue((LOG_DIR / run_id).with_suffix(".html").is_file())

    def test_verify_with_uploaded_txt_file(self):
        files = [("files", ("facts.txt", UPLOAD_TEXT, "text/plain"))]
        resp = self.client.post(
            "/verify", data=self._form(sources_path=None), files=files
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.addCleanup(self._cleanup_run, body["run_id"])
        self.assertEqual(body["input"]["sources_folder"], "(uploaded files)")
        self.assertIsInstance(body["steps"]["verification"], list)

    # ---------------------------------------------------------- error cases

    def test_missing_sources_is_400(self):
        resp = self.client.post("/verify", data=self._form(sources_path=None))
        self.assertEqual(resp.status_code, 400)

    def test_bad_verifier_is_400(self):
        resp = self.client.post("/verify", data=self._form(verifier="quantum"))
        self.assertEqual(resp.status_code, 400)

    def test_top_k_out_of_range_is_400(self):
        for bad in ("0", "999"):
            with self.subTest(top_k=bad):
                resp = self.client.post("/verify", data=self._form(top_k=bad))
                self.assertEqual(resp.status_code, 400)

    def test_exe_upload_is_400(self):
        files = [("files", ("malware.exe", b"MZ binary junk", "application/octet-stream"))]
        resp = self.client.post(
            "/verify", data=self._form(sources_path=None), files=files
        )
        self.assertEqual(resp.status_code, 400)

    def test_oversized_upload_is_413(self):
        files = [("files", ("big.txt", b"a" * (MAX_FILE_BYTES + 1), "text/plain"))]
        resp = self.client.post(
            "/verify", data=self._form(sources_path=None), files=files
        )
        self.assertEqual(resp.status_code, 413)

    def test_whitespace_only_question_is_400(self):
        resp = self.client.post("/verify", data=self._form(question="   \t "))
        self.assertEqual(resp.status_code, 400)

    def test_all_empty_uploads_is_400(self):
        files = [("files", ("blank.txt", b"   \n\t  ", "text/plain"))]
        resp = self.client.post(
            "/verify", data=self._form(sources_path=None), files=files
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["detail"], "All uploaded files were empty")

    # ------------------------------------------------------------------ runs

    def test_runs_returns_a_list(self):
        resp = self.client.get("/runs")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_runs_bad_id_format_is_400(self):
        resp = self.client.get("/runs/run_abc-not-valid")
        self.assertEqual(resp.status_code, 400)

    def test_runs_valid_format_but_nonexistent_is_404(self):
        resp = self.client.get("/runs/run_00000000_000000_000000")
        self.assertEqual(resp.status_code, 404)

    # ------------------------------------------------- cross-site protections

    def test_cross_site_origin_post_is_403(self):
        resp = self.client.post(
            "/verify",
            data=self._form(),
            headers={"Origin": "https://evil.example"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_allowed_ui_origin_post_is_not_blocked(self):
        resp = self.client.post(
            "/verify",
            data=self._form(),
            headers={"Origin": "http://localhost:3000"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.addCleanup(self._cleanup_run, resp.json()["run_id"])

    def test_foreign_host_header_is_rejected(self):
        # DNS-rebinding guard: only localhost host names are trusted.
        resp = self.client.get("/health", headers={"Host": "evil.example"})
        self.assertEqual(resp.status_code, 400)

    def test_overlong_answer_is_413(self):
        resp = self.client.post(
            "/verify", data=self._form(answer="x" * 60_000)
        )
        self.assertEqual(resp.status_code, 413)

    # ------------------------------------------------- filename sanitization

    def test_traversal_filename_is_sanitized(self):
        """A hostile client filename like '..\\..\\<marker>.txt' must be reduced
        to its basename: the upload succeeds and no marker-named file appears
        outside the (deleted) temp dir — in particular not in the project root,
        the logs dir, or next to the OS temp dir. A unique marker is used so
        unrelated files in shared folders can't false-positive this test."""
        marker = f"sentinel_traversal_{uuid.uuid4().hex}"
        files = [("files", (f"..\\..\\{marker}.txt", UPLOAD_TEXT, "text/plain"))]
        resp = self.client.post(
            "/verify", data=self._form(sources_path=None), files=files
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.addCleanup(self._cleanup_run, resp.json()["run_id"])

        tmp = Path(tempfile.gettempdir())
        for folder in (PROJECT_ROOT, PROJECT_ROOT / "logs", tmp, tmp.parent):
            if not folder.is_dir():
                continue
            leaked = [p.name for p in folder.iterdir() if marker in p.name.lower()]
            self.assertEqual(leaked, [], f"sanitization leak in {folder}: {leaked}")


if __name__ == "__main__":
    unittest.main()
