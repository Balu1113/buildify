import django_filters
from .models import Todo

class TodoFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(method='filter_status')
    priority = django_filters.CharFilter(method='filter_priority')

    class Meta:
        model = Todo
        fields = {
            'due_date': ['exact', 'lt', 'gt', 'gte', 'lte'],
        }

    def filter_status(self, queryset, name, value):
        if not value:
            return queryset
        val_str = str(value).lower()
        mapping = {'pending': Todo.Status.PENDING, 'completed': Todo.Status.COMPLETED, '1': 1, '2': 2}
        if val_str in mapping:
            return queryset.filter(status=mapping[val_str])
        return queryset.filter(status=value)

    def filter_priority(self, queryset, name, value):
        if not value:
            return queryset
        val_str = str(value).lower()
        mapping = {'low': Todo.Priority.LOW, 'medium': Todo.Priority.MEDIUM, 'high': Todo.Priority.HIGH, '1': 1, '2': 2, '3': 3}
        if val_str in mapping:
            return queryset.filter(priority=mapping[val_str])
        return queryset.filter(priority=value)
