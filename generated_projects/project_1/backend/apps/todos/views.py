from rest_framework import viewsets, permissions, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from .models import Todo
from .serializers import TodoSerializer
from .filters import TodoFilter

class TodoViewSet(viewsets.ModelViewSet):
    serializer_class = TodoSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = TodoFilter
    search_fields = ['title', 'description']
    ordering_fields = ['created_at', 'due_date', 'priority', 'status']

    def get_queryset(self):
        return Todo.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class DashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user_todos = Todo.objects.filter(user=request.user)
        data = {
            'total': user_todos.count(),
            'pending': user_todos.filter(status=Todo.Status.PENDING).count(),
            'completed': user_todos.filter(status=Todo.Status.COMPLETED).count(),
            'high_priority': user_todos.filter(priority=Todo.Priority.HIGH).count(),
        }
        return Response(data)