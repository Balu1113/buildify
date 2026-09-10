from django.urls import path
from . import views
from . import generated_views

urlpatterns = [
    path("parse-expense/", views.parse_expense, name="parse-expense"),
    path("plan-project/", views.plan_project_view, name="plan-project"),
    path("review-code/", views.review_code_view, name="review-code"),
    path("generated/", generated_views.list_projects, name="generated-projects"),
    path("generated/<str:project_id>/files/", generated_views.project_files, name="generated-files"),
    path("generated/<str:project_id>/file/", generated_views.read_file, name="generated-file"),
    path("generated/<str:project_id>/modify/", generated_views.modify_project, name="generated-modify"),
    path("generated/<str:project_id>/save/", generated_views.save_file, name="generated-save"),
    path("generated/<str:project_id>/run/", generated_views.run_project, name="generated-run"),
    path("generated/<str:project_id>/stop/", generated_views.stop_project, name="generated-stop"),
    path("generated/<str:project_id>/status/", generated_views.run_status, name="generated-status"),
]
