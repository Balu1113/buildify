from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Task, Status
from .serializers import TaskSerializer


class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.all()
    serializer_class = TaskSerializer

    def get_queryset(self):
        queryset = Task.objects.all()
        task_status = self.request.query_params.get("status")
        priority = self.request.query_params.get("priority")
        project_id = self.request.query_params.get("project_id")

        if task_status:
            queryset = queryset.filter(status=task_status)
        if priority:
            queryset = queryset.filter(priority=priority)
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = serializer.save()

        if not request.data.get("priority"):
            self._auto_suggest_priority(task)

        self._auto_run_pipeline(task.project_id, task.status)

        return Response(TaskSerializer(task).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        previous_project_id = self.get_object().project_id
        response = super().update(request, *args, **kwargs)
        data = response.data
        if previous_project_id != data["project"]:
            self._auto_run_pipeline(data["project"], data["status"])
        return response

    def _auto_run_pipeline(self, project_id, task_status):
        if project_id is None or task_status == Status.DONE:
            return
        try:
            from pipeline.service import start_pipeline_for_project

            start_pipeline_for_project(project_id)
        except Exception:
            pass

    def _auto_suggest_priority(self, task):
        from ai_services.gemini_ai import suggest_task_priority

        try:
            priority = suggest_task_priority(
                title=task.title, description=task.description or ""
            )
            task.priority = priority
            task.save(update_fields=["priority"])
        except Exception:
            pass

    @action(detail=False, methods=["post"], url_path="suggest-priority")
    def suggest_priority(self, request):
        from ai_services.gemini_ai import suggest_task_priority

        title = request.data.get("title", "")
        description = request.data.get("description", "")

        if not title:
            return Response(
                {"error": "title is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        priority = suggest_task_priority(title=title, description=description)
        return Response({"suggested_priority": priority})
