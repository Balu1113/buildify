from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/projects/", include("projects.urls")),
    path("api/tasks/", include("tasks.urls")),
    path("api/expenses/", include("expenses.urls")),
    path("api/ai/", include("ai_services.urls")),
    path("api/pipeline/", include("pipeline.urls")),
]
