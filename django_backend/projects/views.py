import os
import shutil

from django.db import connection, transaction
from django.conf import settings
from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import Project
from .serializers import ProjectSerializer


GENERATED_PROJECTS_ROOT = settings.GENERATED_PROJECTS_DIR


def _remove_orphaned_workspaces():
    if not os.path.isdir(GENERATED_PROJECTS_ROOT):
        return
    active_ids = {str(project_id) for project_id in Project.objects.values_list("id", flat=True)}
    for entry in os.listdir(GENERATED_PROJECTS_ROOT):
        if not entry.startswith("project_") or not os.path.isdir(os.path.join(GENERATED_PROJECTS_ROOT, entry)):
            continue
        project_id = entry.removeprefix("project_")
        if project_id not in active_ids:
            shutil.rmtree(os.path.join(GENERATED_PROJECTS_ROOT, entry), ignore_errors=True)


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer

    def list(self, request, *args, **kwargs):
        _remove_orphaned_workspaces()
        return super().list(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        project = self.get_object()
        project_dir = os.path.join(GENERATED_PROJECTS_ROOT, f"project_{project.id}")
        response = super().destroy(request, *args, **kwargs)
        if os.path.isdir(project_dir):
            shutil.rmtree(project_dir, ignore_errors=True)
        return response

    def create(self, request, *args, **kwargs):
        if not Project.objects.exists():
            generated_root = GENERATED_PROJECTS_ROOT
            if os.path.isdir(generated_root):
                for entry in os.listdir(generated_root):
                    path = os.path.join(generated_root, entry)
                    if entry.startswith("project_") and os.path.isdir(path):
                        shutil.rmtree(path, ignore_errors=True)
            with transaction.atomic():
                with connection.cursor() as cursor:
                    if connection.vendor == "sqlite":
                        cursor.execute("DELETE FROM sqlite_sequence WHERE name = 'projects_project'")
                    elif connection.vendor == "postgresql":
                        cursor.execute("ALTER SEQUENCE projects_project_id_seq RESTART WITH 1")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = serializer.save()

        project_dir = os.path.join(GENERATED_PROJECTS_ROOT, f"project_{project.id}")
        # Database IDs can be reused after a reset; never let an old artifact
        # directory become the workspace for a new project.
        if os.path.isdir(project_dir):
            shutil.rmtree(project_dir, ignore_errors=True)

        from pipeline.service import run_pipeline
        run_pipeline(project.id)

        return Response(
            {
                **ProjectSerializer(project).data,
                "tasks_created": 0,
                "pipeline_started": True,
            },
            status=status.HTTP_201_CREATED,
        )
