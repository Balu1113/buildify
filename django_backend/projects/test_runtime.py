import hashlib
import os
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from projects import runtime


class GeneratedEnvTests(SimpleTestCase):
    def test_strips_host_database_and_secret_config(self):
        os.environ["DATABASE_URL"] = "postgres://host/db"
        os.environ["DJANGO_SECRET_KEY"] = "host-secret"
        os.environ["DJANGO_SETTINGS_MODULE"] = "student_project_manager.settings"
        os.environ["SECRET_KEY"] = "host-secret-2"
        try:
            env = runtime.generated_env()
        finally:
            for key in ("DATABASE_URL", "DJANGO_SECRET_KEY", "DJANGO_SETTINGS_MODULE", "SECRET_KEY"):
                os.environ.pop(key, None)

        self.assertNotIn("DATABASE_URL", env)
        self.assertNotIn("DJANGO_SECRET_KEY", env)
        self.assertNotIn("DJANGO_SETTINGS_MODULE", env)
        self.assertNotIn("SECRET_KEY", env)
        self.assertEqual(env["DATABASE_ENGINE"], "sqlite3")
        self.assertEqual(env["DJANGO_ALLOWED_HOSTS"], "localhost,127.0.0.1")

    def test_pythonpath_roots_are_prepended(self):
        env = runtime.generated_env(["/tmp/proj"])
        self.assertTrue(env["PYTHONPATH"].startswith("/tmp/proj"))


class RequirementsReadyTests(SimpleTestCase):
    def test_requires_venv_and_matching_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            backend = project_dir / "backend"
            backend.mkdir()
            requirements = backend / "requirements.txt"
            requirements.write_text("django\n", encoding="utf-8")

            self.assertFalse(runtime.requirements_ready(str(project_dir)))

            python_name = "Scripts\\python.exe" if os.name == "nt" else "bin/python"
            venv_python = project_dir / ".venv" / python_name
            venv_python.parent.mkdir(parents=True)
            venv_python.write_text("", encoding="utf-8")

            self.assertFalse(runtime.requirements_ready(str(project_dir)))

            marker_key = hashlib.sha256(str(requirements).encode()).hexdigest()
            marker = project_dir / ".pipeline" / "requirements" / f"{marker_key}.sha256"
            marker.parent.mkdir(parents=True)
            content_hash = hashlib.sha256(requirements.read_bytes()).hexdigest()
            marker.write_text(content_hash, encoding="ascii")

            self.assertTrue(runtime.requirements_ready(str(project_dir)))

    def test_finds_backend_requirements(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            (project_dir / "backend").mkdir()
            (project_dir / "backend" / "manage.py").write_text("", encoding="utf-8")
            (project_dir / "backend" / "requirements.txt").write_text("django\n", encoding="utf-8")

            found = runtime.find_requirements_files(str(project_dir))
            self.assertEqual(len(found), 1)
            self.assertTrue(found[0].endswith("requirements.txt"))
            self.assertIn("backend", found[0])


class InstallDependenciesTests(SimpleTestCase):
    def test_install_without_requirements_creates_project_venv(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok, message = runtime.install_python_dependencies(tmp)
            self.assertTrue(ok, message)
            python_name = "Scripts\\python.exe" if os.name == "nt" else "bin/python"
            self.assertTrue(os.path.exists(os.path.join(tmp, ".venv", python_name)))
            self.assertTrue(runtime.requirements_ready(tmp))
