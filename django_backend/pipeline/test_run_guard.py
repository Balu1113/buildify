import os
import shutil
import threading
import time
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase

from pipeline import service
from pipeline.models import PipelineRun
from projects.models import Project
from tasks.models import Task


class RunPipelineGuardTests(TestCase):
    def setUp(self):
        service._active_projects.clear()
        service._pending_projects.clear()

    def tearDown(self):
        service._active_projects.clear()
        service._pending_projects.clear()

    @patch("pipeline.service._run_pipeline_worker")
    def test_second_start_is_rejected_while_active(self, worker):
        release = threading.Event()
        worker.side_effect = lambda *args, **kwargs: release.wait(5)
        try:
            self.assertTrue(service.run_pipeline(999))
            self.assertFalse(service.run_pipeline(999))
        finally:
            release.set()
            for _ in range(200):
                if not service._active_projects:
                    break
                time.sleep(0.01)

    @patch("pipeline.service._run_pipeline_worker")
    def test_same_project_can_start_after_previous_run_finishes(self, worker):
        worker.return_value = None
        self.assertTrue(service.run_pipeline(999))
        for _ in range(200):
            if not service._active_projects:
                break
            time.sleep(0.01)
        self.assertTrue(service.run_pipeline(999))
        for _ in range(200):
            if not service._active_projects:
                break
            time.sleep(0.01)


class FinishPipelineRunTests(TestCase):
    def setUp(self):
        service._active_projects.clear()
        service._pending_projects.clear()
        self.project = Project.objects.create(name="Demo")

    def tearDown(self):
        service._active_projects.clear()
        service._pending_projects.clear()

    @patch("pipeline.service.start_pipeline_for_project")
    def test_pending_assignment_restarts_after_deferral(self, start):
        Task.objects.create(title="Todo", project=self.project, status="todo")
        PipelineRun.objects.create(
            project=self.project,
            stage=PipelineRun.Stage.FAILED,
            error=service.FINALIZATION_DEFERRAL_ERROR,
        )
        service._pending_projects.add(self.project.id)
        service._finish_pipeline_run(self.project.id)
        start.assert_called_once_with(self.project.id)

    @patch("pipeline.service.start_pipeline_for_project")
    def test_pending_assignment_restarts_after_completed_run(self, start):
        Task.objects.create(title="New todo", project=self.project, status="todo")
        PipelineRun.objects.create(
            project=self.project,
            stage=PipelineRun.Stage.COMPLETED,
            finalization_state=PipelineRun.FinalizationState.ACCEPTED,
        )
        service._pending_projects.add(self.project.id)
        service._finish_pipeline_run(self.project.id)
        start.assert_called_once_with(self.project.id)

    @patch("pipeline.service.start_pipeline_for_project")
    def test_no_restart_after_user_stop(self, start):
        Task.objects.create(title="Todo", project=self.project, status="todo")
        PipelineRun.objects.create(
            project=self.project,
            stage=PipelineRun.Stage.FAILED,
            error="Pipeline stop requested",
        )
        service._pending_projects.add(self.project.id)
        service._finish_pipeline_run(self.project.id)
        start.assert_not_called()

    @patch("pipeline.service.start_pipeline_for_project")
    def test_no_restart_when_nothing_pending(self, start):
        Task.objects.create(title="Todo", project=self.project, status="todo")
        PipelineRun.objects.create(
            project=self.project,
            stage=PipelineRun.Stage.FAILED,
            error=service.FINALIZATION_DEFERRAL_ERROR,
        )
        service._finish_pipeline_run(self.project.id)
        start.assert_not_called()

    @patch("pipeline.service.start_pipeline_for_project")
    def test_no_restart_when_all_tasks_done(self, start):
        Task.objects.create(title="Done", project=self.project, status="done")
        PipelineRun.objects.create(
            project=self.project,
            stage=PipelineRun.Stage.FAILED,
            error=service.FINALIZATION_DEFERRAL_ERROR,
        )
        service._pending_projects.add(self.project.id)
        service._finish_pipeline_run(self.project.id)
        start.assert_not_called()


class ResumeStoppedPipelineTests(TestCase):
    """stage == FAILED is also the stop signal; resuming must clear it."""

    def setUp(self):
        self.project = Project.objects.create(name="Resume")
        self.project_dir = os.path.join(
            settings.GENERATED_PROJECTS_DIR, f"project_{self.project.pk}"
        )

    def tearDown(self):
        shutil.rmtree(self.project_dir, ignore_errors=True)

    @patch("pipeline.service._repair_workspace")
    @patch("pipeline.service._run_developer")
    def test_continue_unfinished_gets_past_the_first_stop_check(self, developer, repair):
        # The first agent call raises: reaching it at all proves the run
        # passed the hydration-time stop-check that used to raise
        # PipelineStopped immediately after "[Workspace] Hydrated ...".
        developer.side_effect = RuntimeError("reached-developer")
        Task.objects.create(title="Build it", project=self.project, status="todo")
        pipeline = PipelineRun.objects.create(
            project=self.project,
            stage=PipelineRun.Stage.FAILED,
            error="Pipeline stop requested",
        )

        service._run_pipeline_worker(self.project.id, pipeline_id=pipeline.id)

        pipeline.refresh_from_db()
        self.assertIn("[Developer] Generating implementation...", pipeline.log)
        self.assertGreater(developer.call_count, 1)
        # The run ended through the normal retry-exhaustion path, not the
        # stop-check firing on the stale FAILED stage.
        self.assertIn("failed after", pipeline.error)
        self.assertNotIn("stopped by user", pipeline.error)

    @patch("pipeline.service._repair_workspace")
    @patch("pipeline.service._run_developer")
    def test_stop_request_during_agent_step_is_not_lost(self, developer, repair):
        # A Stop click lands mid-agent-step; stage transitions afterwards
        # overwrite stage, so the explicit stop request must still win.
        def stop_then_interrupt(*args, **kwargs):
            service.request_pipeline_stop(self.project.id)
            raise RuntimeError("agent interrupted")

        developer.side_effect = stop_then_interrupt
        Task.objects.create(title="Build it", project=self.project, status="todo")
        pipeline = PipelineRun.objects.create(
            project=self.project,
            stage=PipelineRun.Stage.FAILED,
            error="Pipeline stop requested",
        )

        service._run_pipeline_worker(self.project.id, pipeline_id=pipeline.id)

        pipeline.refresh_from_db()
        self.assertEqual(pipeline.error, "Pipeline stopped by user")
        self.assertIn("[Stopped] Pipeline stopped by user", pipeline.log)
        # Stop wins on the next checkpoint instead of the pipeline quietly
        # retrying after the stop: the developer ran once, then the attempt
        # loop raised before invoking it again.
        self.assertEqual(developer.call_count, 1)
