from rest_framework import serializers
from .models import Todo

class TodoSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(
        choices=[('pending', 'pending'), ('completed', 'completed')],
        default='pending'
    )
    priority = serializers.ChoiceField(
        choices=[('low', 'low'), ('medium', 'medium'), ('high', 'high')],
        default='low'
    )

    class Meta:
        model = Todo
        fields = ['id', 'title', 'description', 'status', 'priority', 'due_date', 'created_at', 'updated_at']

    def validate_status(self, value):
        mapping = {'pending': Todo.Status.PENDING, 'completed': Todo.Status.COMPLETED}
        return mapping.get(value, value)

    def validate_priority(self, value):
        mapping = {'low': Todo.Priority.LOW, 'medium': Todo.Priority.MEDIUM, 'high': Todo.Priority.HIGH}
        return mapping.get(value, value)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['status'] = instance.get_status_display()
        data['priority'] = instance.get_priority_display()
        return data
