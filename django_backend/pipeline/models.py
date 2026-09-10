import uuid

from django.db import models
from projects.models import Project


class PipelineRun(models.Model):
    class Stage(models.TextChoices):
        PLANNING = "planning", "Planning"
        DEVELOPING = "developing", "Developing"
        TESTING = "testing", "Testing"
        DEBUGGING = "debugging", "Debugging"
        REVIEWING = "reviewing", "Reviewing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="pipeline_runs")
    stage = models.CharField(max_length=20, choices=Stage.choices, default=Stage.PLANNING)
    current_task = models.CharField(max_length=255, blank=True, default="")
    total_tasks = models.IntegerField(default=0)
    completed_tasks = models.IntegerField(default=0)
    log = models.TextField(blank=True, default="")
    error = models.TextField(blank=True, default="")
    stream_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Pipeline for {self.project.name} - {self.stage}"

    def append_log(self, message):
        self.log = f"{self.log}\n{message}"
        PipelineRun.objects.filter(pk=self.pk).update(log=self.log)

    def flush_log(self):
        """Save log to database without updating updated_at timestamp."""
        PipelineRun.objects.filter(pk=self.pk).update(log=self.log)
