from urllib.parse import urlparse

from django.contrib import admin
from django.conf import settings
from django.http import FileResponse, Http404
from django.urls import include, path, re_path

from ai_services import generated_views


def _dispatch_preview_request(request):
    """Route root-level requests (assets, SPA routes) to a running preview.

    The generated app lives under /api/ai/generated/<id>/preview/, but its
    dev server references assets at root paths (e.g. /@vite/client,
    /static/js/bundle.js). Requests carrying a preview referer are forwarded
    to the generated frontend process instead of the Buildify SPA.
    """
    referer = urlparse(request.META.get("HTTP_REFERER") or "").path
    parts = referer.split("/")
    # ["", "api", "ai", "generated", "project_1", "preview", ...]
    if (
        len(parts) < 6
        or parts[1] != "api"
        or parts[2] != "ai"
        or parts[3] != "generated"
        or parts[5] != "preview"
    ):
        return None
    project_id = parts[4]
    project = generated_views._resolve_project(project_id)
    if project is None:
        return None
    if not generated_views._has_preview_access(request, project):
        return None
    return generated_views.preview_project(
        request, project_id, request.path.lstrip("/")
    )


def frontend_app(request):
    """Serve the React entry point for client-side routes in the unified deploy."""
    preview_response = _dispatch_preview_request(request)
    if preview_response is not None:
        return preview_response
    static_prefix = "/" + settings.STATIC_URL.lstrip("/")
    if request.path.startswith(static_prefix):
        raise Http404("Static asset not found")
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
    re_path(r"^(?!api/|admin/).*$", frontend_app, name="frontend-app"),
]
