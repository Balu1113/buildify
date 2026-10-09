import os
import shutil
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase

from pipeline import service
from pipeline.models import PipelineRun
from projects.models import Project
from tasks.models import Task


class PipelinePhaseOrderingTests(TestCase):
    """Plan -> develop every task -> only then test, debug, and review."""

    def setUp(self):
        service._active_projects.clear()
        service._pending_projects.clear()
        self.project = Project.objects.create(name="Phased")
        self.project_dir = os.path.join(
            settings.GENERATED_PROJECTS_DIR, f"project_{self.project.pk}"
        )
        Task.objects.create(project=self.project, title="Task one", status="todo")
        Task.objects.create(project=self.project, title="Task two", status="todo")
        self.calls = []

    def tearDown(self):
        service._active_projects.clear()
        service._pending_projects.clear()
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def _record(self, name, pipeline):
        self.calls.append((name, pipeline.stage))

    def _developer(self, *args, **kwargs):
        self._record("developer", args[5])
        return {"files": {"main.py": "print('hello')"}}

    def _tester_pass(self, *args, **kwargs):
        self._record("tester", args[5])
        return {"passed": True, "test_files": {}}

    def _tester_first_fails(self, *args, **kwargs):
        self._record("tester", args[5])
        failures = [call for call in self.calls if call[0] == "tester"]
        if len(failures) == 1:
            return {"passed": False, "test_output": "boom", "test_files": {}}
        return {"passed": True, "test_files": {}}

    def _debugger(self, *args, **kwargs):
        self._record("debugger", args[5])
        return {"fixed": True, "diagnosis": "fixed it", "files": {}}

    def _reviewer(self, *args, **kwargs):
        self._record("reviewer", args[4])
        return {"overall_status": "approved", "score": 9, "findings": []}

    def _run_worker(self, tester=None):
        with patch(
            "pipeline.service._run_developer", side_effect=self._developer
        ), patch(
            "pipeline.service._run_tester",
            side_effect=tester or self._tester_pass,
        ), patch(
            "pipeline.service._run_debugger", side_effect=self._debugger
        ), patch(
            "pipeline.service._run_reviewer", side_effect=self._reviewer
        ), patch(
            "pipeline.service._execute_pytest",
            return_value={"passed": True, "output": "all good"},
        ), patch(
            "pipeline.service._run_finalization", return_value=True
        ), patch(
            "pipeline.service._generate_project_readme"
        ):
            service._run_pipeline_worker(self.project.id)

    def _assert_development_precedes_verification(self):
        names = [name for name, _stage in self.calls]
        self.assertEqual(names.count("developer"), 2)
        last_developer = max(
            index for index, name in enumerate(names) if name == "developer"
        )
        first_verification = min(
            index
            for index, name in enumerate(names)
            if name in {"tester", "debugger", "reviewer"}
        )
        self.assertLess(
            last_developer,
            first_verification,
            "testing/debugging/reviewing started before every task was developed",
        )
        expected_stage = {
            "developer": PipelineRun.Stage.DEVELOPING,
            "tester": PipelineRun.Stage.TESTING,
            "debugger": PipelineRun.Stage.DEBUGGING,
            "reviewer": PipelineRun.Stage.REVIEWING,
        }
        for name, stage in self.calls:
            self.assertEqual(
                stage,
                expected_stage[name],
                f"{name} ran while stage was '{stage}'",
            )

    def test_all_tasks_developed_before_any_verification(self):
        self._run_worker()

        self._assert_development_precedes_verification()

        pipeline = PipelineRun.objects.get(project=self.project)
        self.assertEqual(pipeline.stage, PipelineRun.Stage.COMPLETED)
        self.assertEqual(pipeline.completed_tasks, 2)
        self.assertLess(
            pipeline.log.index("[Phase] DEVELOPING"),
            pipeline.log.index("[Phase] VERIFY"),
        )
        self.assertFalse(
            Task.objects.filter(project=self.project)
            .exclude(status="done")
            .exists()
        )

    def test_debugger_runs_only_after_development_finishes(self):
        self._run_worker(tester=self._tester_first_fails)

        self._assert_development_precedes_verification()

        names = [name for name, _stage in self.calls]
        self.assertIn("debugger", names)
        self.assertEqual(
            [stage for name, stage in self.calls if name == "debugger"],
            [PipelineRun.Stage.DEBUGGING],
        )

        pipeline = PipelineRun.objects.get(project=self.project)
        self.assertEqual(pipeline.stage, PipelineRun.Stage.COMPLETED)
