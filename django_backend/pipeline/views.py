from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from .models import PipelineRun
from .serializers import PipelineRunSerializer
from tasks.models import Task

# Stages where a worker is (or can be) actively running. History filters use
# this to answer "what is live", and clear_history never deletes these runs so
# an active build can always be stopped or continued.
RUNNING_STAGES = (
    PipelineRun.Stage.PLANNING,
    PipelineRun.Stage.DEVELOPING,
    PipelineRun.Stage.TESTING,
    PipelineRun.Stage.DEBUGGING,
    PipelineRun.Stage.REVIEWING,
)


def _parse_time_bound(value, field_name):
    parsed = parse_datetime(value)
    if parsed is None:
        raise ValidationError(
            {field_name: "Use an ISO 8601 datetime, e.g. 2026-10-09T14:30:00Z."}
        )
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _apply_history_filters(queryset, params):
    """Filter pipeline runs by a named time range.

    Supported ``range`` values: ``live`` (running now), ``hour`` (last hour),
    ``day`` (last 24 hours), ``custom`` (explicit ``start``/``end`` bounds),
    and ``all`` (default). Unknown values fall back to ``all``.
    """
    range_name = (params.get("range") or "all").lower()
    now = timezone.now()
    if range_name == "live":
        return queryset.filter(stage__in=RUNNING_STAGES)
    if range_name == "hour":
        return queryset.filter(created_at__gte=now - timedelta(hours=1))
    if range_name == "day":
        return queryset.filter(created_at__gte=now - timedelta(days=1))
    if range_name == "custom":
        start = params.get("start")
        end = params.get("end")
        if not start and not end:
            raise ValidationError(
                {"start": "A custom range requires a start and/or end datetime."}
            )
        if start:
            queryset = queryset.filter(
                created_at__gte=_parse_time_bound(start, "start")
            )
        if end:
            queryset = queryset.filter(
                created_at__lte=_parse_time_bound(end, "end")
            )
        return queryset
    return queryset


def _apply_sort(queryset, params):
    if (params.get("sort") or "newest").lower() == "oldest":
        return queryset.order_by("created_at")
    return queryset.order_by("-created_at")


class PipelineRunViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PipelineRun.objects.all()
    serializer_class = PipelineRunSerializer

    def get_queryset(self):
        queryset = PipelineRun.objects.all()
        project_id = self.request.query_params.get("project_id")
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        queryset = _apply_history_filters(queryset, self.request.query_params)
        return _apply_sort(queryset, self.request.query_params)

    @action(detail=False, methods=["post"])
    def clear_history(self, request):
        """Delete finished runs for a project, optionally scoped by range.

        Live (running) runs are always kept so an active build is never
        removed from under the worker or the UI.
        """
        project_id = request.query_params.get(
            "project_id"
        ) or request.data.get("project_id")
        if not project_id:
            return Response(
                {"error": "project_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        queryset = PipelineRun.objects.filter(project_id=project_id)
        queryset = queryset.exclude(stage__in=RUNNING_STAGES)
        queryset = _apply_history_filters(queryset, request.query_params)
        deleted, _details = queryset.delete()
        return Response({"deleted": deleted})

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        pipeline = self.get_object()
        has_unfinished_tasks = Task.objects.filter(
            project_id=pipeline.project_id,
            status__in=["todo", "in_progress"],
        ).exists()
        can_resume_finalization = pipeline.finalization_state in {
            PipelineRun.FinalizationState.PENDING,
            PipelineRun.FinalizationState.FAILED,
        } and not has_unfinished_tasks
        if pipeline.finalization_state == PipelineRun.FinalizationState.ACCEPTED:
            return Response(
                {"error": "Project is already accepted"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if pipeline.stage != PipelineRun.Stage.FAILED and not can_resume_finalization:
            return Response(
                {"error": "Pipeline is already running or completed"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from .service import run_pipeline
        started = run_pipeline(pipeline.project_id, pipeline_id=pipeline.id)
        if not started:
            return Response(
                {"error": "Pipeline is already running"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response({"status": "restarted"})

    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        pipeline = self.get_object()
        if pipeline.stage in (PipelineRun.Stage.COMPLETED, PipelineRun.Stage.FAILED):
            return Response(
                {"error": "Pipeline is not running"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .service import request_pipeline_stop

        request_pipeline_stop(pipeline.project_id)
        pipeline.stage = PipelineRun.Stage.FAILED
        pipeline.error = "Pipeline stop requested"
        pipeline.append_log("[Stop requested] Waiting for the current agent step to finish...")
        pipeline.save(update_fields=["stage", "error", "log"])
        return Response({"status": "stopping"})
