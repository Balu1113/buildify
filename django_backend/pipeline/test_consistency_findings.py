import os
import shutil
import tempfile

from django.test import SimpleTestCase

from pipeline import service


SETTINGS_SOURCE = """\
import os

SECRET_KEY = "test"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    {installed_extra}
]

ROOT_URLCONF = "smartcalc_backend.urls"
"""


URLS_SOURCE = """\
from django.urls import path, include

urlpatterns = [
    path("api/", include("calculator.urls")),
]
"""


MODELS_SOURCE = """\
from django.db import models


class Calculation(models.Model):
    expression = models.CharField(max_length=100)
"""


class GeneratedConsistencyFindingsTests(SimpleTestCase):
    def setUp(self):
        self.project_dir = tempfile.mkdtemp(prefix="buildify_consistency_")
        self.addCleanup(shutil.rmtree, self.project_dir, True)

    def _write(self, relative_path, content):
        path = os.path.join(self.project_dir, relative_path.replace("/", os.sep))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)

    def _build_project(self, installed_extra):
        self._write("backend/manage.py", "import os, sys\nfrom django.core.management import execute_from_command_line\nif __name__ == '__main__':\n    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartcalc_backend.settings')\n    execute_from_command_line(sys.argv)\n")
        self._write("backend/smartcalc_backend/__init__.py", "")
        self._write(
            "backend/smartcalc_backend/settings.py",
            SETTINGS_SOURCE.format(installed_extra=installed_extra),
        )
        self._write("backend/smartcalc_backend/urls.py", URLS_SOURCE)
        self._write("backend/smartcalc_backend/wsgi.py", "application = None\n")
        self._write("backend/smartcalc_backend/asgi.py", "application = None\n")
        self._write("backend/calculator/__init__.py", "")
        self._write("backend/calculator/models.py", MODELS_SOURCE)
        self._write("backend/calculator/urls.py", "urlpatterns = []\n")
        self._write("backend/requirements.txt", "Django\n")

    def _failure_types(self):
        findings = service._generated_consistency_findings(self.project_dir)
        return [finding["failure_type"] for finding in findings], findings

    def test_model_app_missing_from_installed_apps_is_flagged(self):
        self._build_project("")
        failure_types, findings = self._failure_types()
        self.assertIn("unregistered_model_app", failure_types)
        finding = next(f for f in findings if f["failure_type"] == "unregistered_model_app")
        self.assertEqual(finding["affected_path_or_module"], "calculator")
        self.assertEqual(finding["severity"], "critical")

    def test_registered_model_app_is_not_flagged(self):
        self._build_project('"calculator",')
        failure_types, _ = self._failure_types()
        self.assertNotIn("unregistered_model_app", failure_types)

    def test_models_with_explicit_app_label_are_not_flagged(self):
        self._build_project("")
        self._write(
            "backend/calculator/models.py",
            MODELS_SOURCE.replace(
                "class Calculation(models.Model):",
                "class Calculation(models.Model):\n    class Meta:\n        app_label = \"calculator\"",
            ),
        )
        failure_types, _ = self._failure_types()
        self.assertNotIn("unregistered_model_app", failure_types)

    def test_appconfig_name_mismatch_is_flagged(self):
        self._build_project('"calculator",')
        self._write(
            "backend/calculator/apps.py",
            "from django.apps import AppConfig\n\n\n"
            "class CalculatorConfig(AppConfig):\n"
            "    name = 'apps.calculator'\n",
        )
        failure_types, findings = self._failure_types()
        self.assertIn("appconfig_name_mismatch", failure_types)
        finding = next(f for f in findings if f["failure_type"] == "appconfig_name_mismatch")
        self.assertEqual(finding["affected_path_or_module"], "apps.calculator")

    def test_matching_appconfig_name_is_not_flagged(self):
        self._build_project('"calculator",')
        self._write(
            "backend/calculator/apps.py",
            "from django.apps import AppConfig\n\n\n"
            "class CalculatorConfig(AppConfig):\n"
            "    name = 'calculator'\n",
        )
        failure_types, _ = self._failure_types()
        self.assertNotIn("appconfig_name_mismatch", failure_types)
