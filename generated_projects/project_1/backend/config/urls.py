from django.contrib import admin
from django.urls import path, include
from rest_framework.views import APIView
from rest_framework.response import Response

class HealthCheckView(APIView):
    def get(self, request, *args, **kwargs):
        return Response({'status': 'healthy', 'service': 'backend'})

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', HealthCheckView.as_view(), name='health-check'),
    path('api/auth/', include('apps.accounts.urls')),
    path('api/todos/', include('apps.todos.urls')),
]