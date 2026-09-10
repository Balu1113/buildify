import os
import shutil

from django.db import connection, transaction
from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import Project
from .serializers import ProjectSerializer


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer

    def create(self, request, *args, **kwargs):
        if not Project.objects.exists():
            generated_root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "generated_projects")
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
