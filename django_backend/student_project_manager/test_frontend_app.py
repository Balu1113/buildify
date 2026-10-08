import tempfile
from pathlib import Path

from django.test import TestCase, override_settings


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
                response = self.client.get("/static/@vite/client")
        self.assertEqual(response.status_code, 404)
