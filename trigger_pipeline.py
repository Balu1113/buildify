"""Trigger the pipeline for the calculator project (project_id=8)."""
import os
import sys
import django

os.chdir(os.path.join(os.path.dirname(__file__), "django_backend"))
sys.path.insert(0, ".")
os.environ["DJANGO_SETTINGS_MODULE"] = "student_project_manager.settings"
django.setup()

from projects.models import Project
from pipeline.service import run_pipeline

# Find the calculator project
projects = list(Project.objects.filter(name__icontains="calculator"))
if not projects:
    print("ERROR: No calculator project found!")
    sys.exit(1)

project = projects[0]
print(f"Triggering pipeline for: {project.name} (id={project.id})")
run_pipeline(project.id)
print(f"Pipeline thread started for project_id={project.id}.")
print("Monitor progress in the UI or check logs.")
