import os
import shutil
import tempfile

from django.test import TestCase

from projects.models import Project
from projects.storage import line_stats, materialize_project, persist_workspace, save_generated_file


class MaterializeWorkspaceTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="Storage")
        self.tmp = tempfile.mkdtemp()
        self.project_dir = os.path.join(self.tmp, f"project_{self.project.pk}")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, relative, content="x"):
        path = os.path.join(self.project_dir, *relative.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)

    def _exists(self, relative):
        return os.path.exists(os.path.join(self.project_dir, *relative.split("/")))

    def test_clear_preserves_nested_excluded_dirs_and_removes_stale_files(self):
        save_generated_file(self.project, "frontend/package.json", "{}")
        save_generated_file(self.project, "backend/settings.py", "# settings")

        self._write("frontend/node_modules/pkg/index.js")
        self._write("backend/.venv/lib/python3.12/site.py")
        self._write(".venv/pyvenv.cfg")
        self._write(".pipeline/requirements/abc.sha256", "hash")
        self._write(".buildify/frontend_status.json", "{}")
        self._write("backend/__pycache__/settings.cpython-312.pyc")

        self._write("frontend/stale.js")
        self._write("stale_root.txt")
        self._write("backend/stale.py")

        materialize_project(self.project, self.project_dir, clear=True)

        for relative in (
            "frontend/node_modules/pkg/index.js",
            "backend/.venv/lib/python3.12/site.py",
            ".venv/pyvenv.cfg",
            ".pipeline/requirements/abc.sha256",
            ".buildify/frontend_status.json",
            "backend/__pycache__/settings.cpython-312.pyc",
        ):
            self.assertTrue(self._exists(relative), relative)

        for relative in ("frontend/stale.js", "stale_root.txt", "backend/stale.py"):
            self.assertFalse(self._exists(relative), relative)

        self.assertTrue(self._exists("frontend/package.json"))
        self.assertTrue(self._exists("backend/settings.py"))

    def test_clear_is_repeatable_and_survives_missing_workspace(self):
        save_generated_file(self.project, "main.py", "print(1)")
        materialize_project(self.project, self.project_dir, clear=True)
        materialize_project(self.project, self.project_dir, clear=True)
        self.assertTrue(self._exists("main.py"))

    def test_persist_skips_runtime_state_dirs(self):
        self._write("main.py", "print(1)")
        self._write(".pipeline/requirements/abc.sha256", "hash")
        self._write(".buildify/frontend_status.json", "{}")

        persisted = persist_workspace(self.project, self.project_dir)

        self.assertIn("main.py", persisted)
        self.assertNotIn(".pipeline/requirements/abc.sha256", persisted)
        self.assertNotIn(".buildify/frontend_status.json", persisted)


class LineStatsTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="Line Stats")

    def _stats(self, path):
        from projects.models import GeneratedFile

        return GeneratedFile.objects.get(project=self.project, path=path)

    def test_new_file_counts_every_line_as_added(self):
        save_generated_file(self.project, "app.py", "a\nb\nc")
        row = self._stats("app.py")
        self.assertEqual((row.line_count, row.added_lines, row.removed_lines), (3, 3, 0))

    def test_update_reports_line_delta_against_previous_content(self):
        save_generated_file(self.project, "app.py", "a\nb\nc")
        save_generated_file(self.project, "app.py", "a\nb\nc\nd")
        row = self._stats("app.py")
        self.assertEqual((row.line_count, row.added_lines, row.removed_lines), (4, 1, 0))

        save_generated_file(self.project, "app.py", "a\nX\nd")
        row = self._stats("app.py")
        self.assertEqual((row.line_count, row.added_lines, row.removed_lines), (3, 1, 2))

    def test_unchanged_rewrite_reports_zero_diff(self):
        save_generated_file(self.project, "app.py", "a\nb")
        save_generated_file(self.project, "app.py", "a\nb")
        row = self._stats("app.py")
        self.assertEqual((row.line_count, row.added_lines, row.removed_lines), (2, 0, 0))

    def test_line_stats_handles_edge_inputs(self):
        self.assertEqual(line_stats(None, ""), (0, 0, 0))
        self.assertEqual(line_stats("one\ntwo", "one\ntwo\nthree"), (3, 1, 0))
