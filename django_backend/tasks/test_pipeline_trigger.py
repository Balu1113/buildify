from unittest.mock import patch

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from pipeline.models import PipelineRun
from projects.models import Project
from tasks.models import Task


class TaskAssignmentPipelineTriggerTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pass1234")
        self.client.force_authenticate(self.user)
        self.project = Project.objects.create(name="Demo Project")

    @patch("pipeline.service.run_pipeline", return_value=True)
    def test_create_with_project_starts_pipeline(self, run_pipeline):
        response = self.client.post(
            "/api/tasks/",
            {"title": "New task", "priority": "medium", "project": self.project.id},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        run_pipeline.assert_called_once_with(self.project.id)

    @patch("pipeline.service.run_pipeline", return_value=True)
    def test_create_without_project_does_not_start_pipeline(self, run_pipeline):
        response = self.client.post(
            "/api/tasks/",
            {"title": "Loose task", "priority": "medium"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        run_pipeline.assert_not_called()

    @patch("pipeline.service.run_pipeline", return_value=True)
    def test_create_done_task_does_not_start_pipeline(self, run_pipeline):
        response = self.client.post(
            "/api/tasks/",
            {
                "title": "Finished task",
                "priority": "medium",
                "status": "done",
                "project": self.project.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        run_pipeline.assert_not_called()

    @patch("pipeline.service.run_pipeline", return_value=True)
    def test_update_assigning_project_starts_pipeline(self, run_pipeline):
        task = Task.objects.create(title="Unassigned")
        response = self.client.put(
            f"/api/tasks/{task.id}/",
            {
                "title": task.title,
                "priority": task.priority,
                "status": task.status,
                "project": self.project.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        run_pipeline.assert_called_once_with(self.project.id)

    @patch("pipeline.service.run_pipeline", return_value=True)
    def test_status_change_on_assigned_task_does_not_start_pipeline(self, run_pipeline):
        task = Task.objects.create(title="Assigned", project=self.project)
        response = self.client.put(
            f"/api/tasks/{task.id}/",
            {
                "title": task.title,
                "priority": task.priority,
                "status": "in_progress",
                "project": self.project.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        run_pipeline.assert_not_called()

    @patch("pipeline.service.run_pipeline", return_value=True)
    def test_existing_unfinished_run_is_reused(self, run_pipeline):
        run = PipelineRun.objects.create(
            project=self.project,
            stage=PipelineRun.Stage.FAILED,
            finalization_state=PipelineRun.FinalizationState.PENDING,
        )
        response = self.client.post(
            "/api/tasks/",
            {"title": "Task", "priority": "medium", "project": self.project.id},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        run_pipeline.assert_called_once_with(self.project.id, pipeline_id=run.id)

    @patch("pipeline.service.run_pipeline", return_value=True)
    def test_accepted_run_opens_fresh_run(self, run_pipeline):
        PipelineRun.objects.create(
            project=self.project,
            stage=PipelineRun.Stage.COMPLETED,
            finalization_state=PipelineRun.FinalizationState.ACCEPTED,
        )
        response = self.client.post(
            "/api/tasks/",
            {"title": "Task", "priority": "medium", "project": self.project.id},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        run_pipeline.assert_called_once_with(self.project.id)
