import shutil
import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from ai_services import generated_views
from projects.models import Project
from projects.storage import save_generated_file

MAIN_PY = """
import http.server
import os

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = ("generated:" + self.path).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass

port = int(os.environ.get("PORT") or "0")
server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
server.serve_forever()
"""


class GeneratedPreviewFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="preview-tester", password="x"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.project = Project.objects.create(name="Preview Flow")
        self.project_id = f"project_{self.project.pk}"
        save_generated_file(self.project, "main.py", MAIN_PY)
        self.project_dir = os.path.join(
            settings.GENERATED_PROJECTS_DIR, f"project_{self.project.pk}"
        )

    def tearDown(self):
        generated_views._stop_process(self.project_id)
        generated_views._preview_jobs.pop(self.project_id, None)
        generated_views._auto_repair_jobs.pop(self.project_id, None)
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def test_run_proxy_and_root_dispatch_end_to_end(self):
        run = self.client.post(f"/api/ai/generated/{self.project_id}/run/")
        self.assertEqual(run.status_code, 200, run.content)
        payload = run.json()
        self.assertEqual(payload.get("status"), "running", payload)
        token = payload["preview_token"]
        self.assertTrue(token)

        # The run response also sets the preview cookie so the iframe works
        # without appending the token to every URL.
        cookie_name = generated_views._preview_cookie_name(self.project.pk)
        self.assertIn(cookie_name, run.cookies)

        # Cookie-only access (no query token) is authorized.
        cookie_only = self.client.get(
            f"/api/ai/generated/{self.project_id}/preview/hello"
        )
        self.assertEqual(cookie_only.status_code, 200, cookie_only.content)
        self.assertEqual(cookie_only.content, b"generated:/hello")

        # A client with neither token nor cookie is still denied.
        fresh = APIClient()
        fresh.force_authenticate(user=self.user)
        denied = fresh.get(
            f"/api/ai/generated/{self.project_id}/preview/hello"
        )
        self.assertEqual(denied.status_code, 403, denied.content)

        # Requests under the preview prefix are proxied to the app.
        preview = self.client.get(
            f"/api/ai/generated/{self.project_id}/preview/hello",
            {"preview_token": token},
        )
        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertEqual(preview.content, b"generated:/hello")

        # Root-level requests with a preview referer (and the cookie set by
        # the preview response) dispatch to the same generated process.
        referer = f"http://testserver/api/ai/generated/{self.project_id}/preview/"
        root = self.client.get("/hello", HTTP_REFERER=referer)
        self.assertEqual(root.status_code, 200, root.content)
        self.assertEqual(root.content, b"generated:/hello")

        # The dashboard SPA still serves client routes for normal requests.
        from django.test import override_settings
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "index.html").write_text("<html>spa</html>", encoding="utf-8")
            with override_settings(FRONTEND_BUILD_DIR=Path(tmp)):
                spa = self.client.get("/dashboard")
                self.assertEqual(spa.status_code, 200)
                self.assertEqual(b"".join(spa.streaming_content), b"<html>spa</html>")

        stop = self.client.post(f"/api/ai/generated/{self.project_id}/stop/")
        self.assertEqual(stop.status_code, 200)
        self.assertEqual(stop.json().get("status"), "stopped")

    def test_preview_reports_not_running_before_token_check(self):
        resp = self.client.get(f"/api/ai/generated/{self.project_id}/preview/")
        self.assertEqual(resp.status_code, 409, resp.content)
        self.assertEqual(resp.json().get("status"), "not_running")

    def test_new_run_clears_stale_failed_repair_job(self):
        generated_views._set_auto_repair_job(
            self.project_id,
            status="failed",
            stage="auto_repair",
            message="stale failure from a previous attempt",
        )

        # Status polls report the stale failure until a new run starts.
        stale = self.client.get(f"/api/ai/generated/{self.project_id}/status/")
        self.assertEqual(stale.status_code, 200)
        self.assertEqual(stale.json().get("status"), "failed")

        run = self.client.post(f"/api/ai/generated/{self.project_id}/run/")
        self.assertEqual(run.status_code, 200, run.content)
        self.assertEqual(run.json().get("status"), "running", run.json())
        self.assertIsNone(generated_views._get_auto_repair_job(self.project_id))

        after = self.client.get(f"/api/ai/generated/{self.project_id}/status/")
        self.assertEqual(after.status_code, 200)
        self.assertEqual(after.json().get("status"), "running", after.json())

        stop = self.client.post(f"/api/ai/generated/{self.project_id}/stop/")
        self.assertEqual(stop.status_code, 200)

    def test_files_endpoint_exposes_live_line_stats(self):
        resp = self.client.get(f"/api/ai/generated/{self.project_id}/files/")
        self.assertEqual(resp.status_code, 200, resp.content)
        files = resp.json()["files"]
        main_py = next(f for f in files if f["path"] == "main.py")
        self.assertEqual(main_py["lines"], len(MAIN_PY.splitlines()))
        self.assertEqual(main_py["added_lines"], len(MAIN_PY.splitlines()))
        self.assertEqual(main_py["removed_lines"], 0)
        self.assertIn("updated_at", main_py)
