import json
import tempfile
from pathlib import Path

from django.core import signing
from django.test import TestCase, override_settings

from ai_services.generated_views import PREVIEW_TOKEN_SALT
from projects.models import Project


class FrontendAppTests(TestCase):
    def test_serves_index_html_for_spa_routes(self):
        body = "<html><body>Buildify</body></html>"
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "index.html").write_text(body, encoding="utf-8")
            with override_settings(FRONTEND_BUILD_DIR=Path(tmp)):
                response = self.client.get("/projects")
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response["Content-Type"].startswith("text/html"))
                self.assertEqual(b"".join(response.streaming_content), body.encode())

    def test_missing_build_returns_404(self):
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(FRONTEND_BUILD_DIR=Path(tmp)):
                response = self.client.get("/projects")
        self.assertEqual(response.status_code, 404)

    def test_missing_static_asset_returns_404_not_spa_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(FRONTEND_BUILD_DIR=Path(tmp)):
                response = self.client.get("/static/does-not-exist.js")
        self.assertEqual(response.status_code, 404)


class PreviewRootDispatchTests(TestCase):
    def _preview_referer(self, project):
        return f"http://testserver/api/ai/generated/project_{project.pk}/preview/"

    def _preview_cookie(self, project):
        token = signing.dumps(
            {"project_id": project.pk, "user_id": 1},
            salt=PREVIEW_TOKEN_SALT,
        )
        return f"buildify_preview_{project.pk}={token}"

    def test_root_asset_with_preview_referer_reaches_preview(self):
        project = Project.objects.create(name="Dispatch")
        response = self.client.get(
            "/static/js/bundle.js",
            HTTP_REFERER=self._preview_referer(project),
            HTTP_COOKIE=self._preview_cookie(project),
        )
        # Dispatched to the preview proxy, which reports no running process
        # (without dispatch this would be a plain static 404).
        self.assertEqual(response.status_code, 409)
        payload = json.loads(response.content)
        self.assertEqual(payload.get("status"), "not_running")

    def test_root_spa_route_with_preview_referer_reaches_preview(self):
        project = Project.objects.create(name="DispatchRoute")
        response = self.client.get(
            "/login",
            HTTP_REFERER=self._preview_referer(project),
            HTTP_COOKIE=self._preview_cookie(project),
        )
        self.assertEqual(response.status_code, 409)
        payload = json.loads(response.content)
        self.assertEqual(payload.get("status"), "not_running")

    def test_root_asset_without_preview_cookie_is_not_dispatched(self):
        project = Project.objects.create(name="NoCookie")
        response = self.client.get(
            "/static/js/bundle.js",
            HTTP_REFERER=self._preview_referer(project),
        )
        # No valid preview cookie: no dispatch, and static misses are 404s.
        self.assertEqual(response.status_code, 404)

    def test_preview_runtime_declares_router_basename(self):
        from ai_services.generated_views import _preview_runtime_script

        script = _preview_runtime_script(7)
        self.assertIn("__BUILDIFY_PREVIEW_BASENAME__", script)
        self.assertIn("/api/ai/generated/project_7/preview", script)
