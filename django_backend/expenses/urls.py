from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ExpenseViewSet, CategoryViewSet

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("", ExpenseViewSet, basename="expense")

urlpatterns = [
    path("", include(router.urls)),
]
