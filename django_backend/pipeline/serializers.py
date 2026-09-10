from rest_framework import serializers
from .models import PipelineRun


class PipelineRunSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source="project.name", read_only=True)
    ai_model = serializers.CharField(source="project.ai_model", read_only=True)

    class Meta:
        model = PipelineRun
        fields = [
            "id",
            "project",
            "project_name",
            "ai_model",
            "stage",
            "current_task",
            "total_tasks",
            "completed_tasks",
            "log",
            "error",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
