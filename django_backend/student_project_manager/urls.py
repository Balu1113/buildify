from django.contrib import admin
from django.conf import settings
from django.http import FileResponse, Http404
from django.urls import include, path, re_path

def frontend_app(request):
    """Serve the React entry point for client-side routes in the unified deploy."""
    index_file = settings.FRONTEND_BUILD_DIR / "index.html"
    if not index_file.is_file():
        raise Http404("Frontend build is not available")
    return FileResponse(index_file.open("rb"), content_type="text/html")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/projects/", include("projects.urls")),
    path("api/tasks/", include("tasks.urls")),
    path("api/expenses/", include("expenses.urls")),
    path("api/ai/", include("ai_services.urls")),
    path("api/pipeline/", include("pipeline.urls")),
    re_path(r"^(?!api/|admin/|static/).*$", frontend_app, name="frontend-app"),
]
