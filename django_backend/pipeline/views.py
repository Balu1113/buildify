from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import PipelineRun
from .serializers import PipelineRunSerializer
from tasks.models import Task


class PipelineRunViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PipelineRun.objects.all()
    serializer_class = PipelineRunSerializer

    def get_queryset(self):
        queryset = PipelineRun.objects.all()
        project_id = self.request.query_params.get("project_id")
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        return queryset

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        pipeline = self.get_object()
        has_unfinished_tasks = Task.objects.filter(
            project_id=pipeline.project_id,
            status__in=["todo", "in_progress"],
        ).exists()
        if pipeline.stage != PipelineRun.Stage.FAILED and not (
            pipeline.stage == PipelineRun.Stage.COMPLETED and has_unfinished_tasks
        ):
            return Response(
                {"error": "Pipeline is already running or completed"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from .service import run_pipeline
        run_pipeline(pipeline.project_id)
        return Response({"status": "restarted"})

    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        pipeline = self.get_object()
        if pipeline.stage in (PipelineRun.Stage.COMPLETED, PipelineRun.Stage.FAILED):
            return Response(
                {"error": "Pipeline is not running"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pipeline.stage = PipelineRun.Stage.FAILED
        pipeline.error = "Pipeline stop requested"
        pipeline.append_log("[Stop requested] Waiting for the current agent step to finish...")
        pipeline.save(update_fields=["stage", "error", "log"])
        return Response({"status": "stopping"})
