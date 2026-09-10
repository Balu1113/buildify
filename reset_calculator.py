"""Reset calculator project tasks and pipeline runs for a clean retry."""
import os
import sys
import django

os.chdir(os.path.join(os.path.dirname(__file__), "django_backend"))
sys.path.insert(0, ".")
os.environ["DJANGO_SETTINGS_MODULE"] = "student_project_manager.settings"
django.setup()

from projects.models import Project
from tasks.models import Task
from pipeline.models import PipelineRun

projects = Project.objects.filter(name__icontains="calculator")
print(f"Found {projects.count()} calculator project(s).")

for p in projects:
    updated = Task.objects.filter(project=p).update(status="todo")
    print(f"  Reset {updated} tasks to 'todo' for: {p.name} (id={p.id})")
    deleted_count, _ = PipelineRun.objects.filter(project=p).delete()
    print(f"  Deleted {deleted_count} pipeline run(s).")

print("\nDone. You can now re-run the pipeline from the UI.")
