from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from pipeline.models import PipelineRun
from projects.models import Project


class PipelineHistoryApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="history-tester", password="x"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.project = Project.objects.create(name="History Project")
        self.other_project = Project.objects.create(name="Other Project")

    def _run(self, project, stage=PipelineRun.Stage.COMPLETED, age=None):
        run = PipelineRun.objects.create(project=project, stage=stage)
        if age is not None:
            PipelineRun.objects.filter(pk=run.pk).update(
                created_at=timezone.now() - age
            )
        return run

    def test_default_returns_all_runs_newest_first(self):
        older = self._run(self.project, age=timedelta(hours=5))
        newer = self._run(self.project, age=timedelta(minutes=5))

        response = self.client.get("/api/pipeline/", {"project_id": self.project.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()], [newer.pk, older.pk]
        )

    def test_hour_filter_excludes_older_runs(self):
        old = self._run(self.project, age=timedelta(hours=2))
        recent = self._run(self.project, age=timedelta(minutes=10))

        response = self.client.get(
            "/api/pipeline/",
            {"project_id": self.project.pk, "range": "hour"},
        )

        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.json()]
        self.assertIn(recent.pk, ids)
        self.assertNotIn(old.pk, ids)

    def test_live_filter_returns_only_running_runs(self):
        running = self._run(self.project, stage=PipelineRun.Stage.DEVELOPING)
        done = self._run(self.project, stage=PipelineRun.Stage.COMPLETED)
        failed = self._run(self.project, stage=PipelineRun.Stage.FAILED)

        response = self.client.get(
            "/api/pipeline/",
            {"project_id": self.project.pk, "range": "live"},
        )

        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.json()]
        self.assertEqual(ids, [running.pk])
        self.assertNotIn(done.pk, ids)
        self.assertNotIn(failed.pk, ids)

    def test_custom_range_applies_start_and_end_bounds(self):
        outside_old = self._run(self.project, age=timedelta(days=3))
        inside = self._run(self.project, age=timedelta(hours=2))
        outside_new = self._run(
            self.project, age=timedelta(minutes=1)
        )
        now = timezone.now()
        response = self.client.get(
            "/api/pipeline/",
            {
                "project_id": self.project.pk,
                "range": "custom",
                "start": (now - timedelta(days=1)).isoformat(),
                "end": (now - timedelta(hours=1)).isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.json()]
        self.assertEqual(ids, [inside.pk])
        self.assertNotIn(outside_old.pk, ids)
        self.assertNotIn(outside_new.pk, ids)

    def test_custom_range_requires_a_bound(self):
        response = self.client.get(
            "/api/pipeline/",
            {"project_id": self.project.pk, "range": "custom"},
        )
        self.assertEqual(response.status_code, 400)

    def test_custom_range_rejects_unparseable_datetimes(self):
        response = self.client.get(
            "/api/pipeline/",
            {"project_id": self.project.pk, "range": "custom", "start": "not-a-date"},
        )
        self.assertEqual(response.status_code, 400)

    def test_sort_oldest_puts_first_run_first(self):
        older = self._run(self.project, age=timedelta(hours=5))
        newer = self._run(self.project, age=timedelta(minutes=5))

        response = self.client.get(
            "/api/pipeline/",
            {"project_id": self.project.pk, "sort": "oldest"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()], [older.pk, newer.pk]
        )

    def test_clear_history_deletes_finished_and_keeps_live(self):
        self._run(self.project, stage=PipelineRun.Stage.COMPLETED, age=timedelta(hours=2))
        self._run(self.project, stage=PipelineRun.Stage.FAILED, age=timedelta(minutes=30))
        live = self._run(self.project, stage=PipelineRun.Stage.TESTING)

        response = self.client.post(
            "/api/pipeline/clear_history/", {"project_id": self.project.pk}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted"], 2)
        remaining = list(
            PipelineRun.objects.filter(project=self.project).values_list("pk", flat=True)
        )
        self.assertEqual(remaining, [live.pk])

    def test_clear_history_is_scoped_to_one_project(self):
        cleared = self._run(self.project, stage=PipelineRun.Stage.COMPLETED)
        other_run = self._run(self.other_project, stage=PipelineRun.Stage.COMPLETED)

        response = self.client.post(
            "/api/pipeline/clear_history/", {"project_id": self.project.pk}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted"], 1)
        self.assertFalse(PipelineRun.objects.filter(pk=cleared.pk).exists())
        self.assertTrue(PipelineRun.objects.filter(pk=other_run.pk).exists())

    def test_clear_history_respects_time_range(self):
        old = self._run(self.project, stage=PipelineRun.Stage.COMPLETED, age=timedelta(hours=5))
        recent = self._run(self.project, stage=PipelineRun.Stage.COMPLETED, age=timedelta(minutes=10))

        response = self.client.post(
            f"/api/pipeline/clear_history/?project_id={self.project.pk}&range=hour"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted"], 1)
        self.assertTrue(PipelineRun.objects.filter(pk=old.pk).exists())
        self.assertFalse(PipelineRun.objects.filter(pk=recent.pk).exists())

    def test_clear_history_requires_project_id(self):
        response = self.client.post("/api/pipeline/clear_history/")
        self.assertEqual(response.status_code, 400)
