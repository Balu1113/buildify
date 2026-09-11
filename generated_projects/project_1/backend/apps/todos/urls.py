from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TodoViewSet, DashboardView

router = DefaultRouter()
router.register(r'', TodoViewSet, basename='todo')

urlpatterns = [
    path('dashboard/', DashboardView.as_view(), name='todo-dashboard'),
    path('', include(router.urls)),
]