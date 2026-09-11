from django.db import models
from django.conf import settings

class Todo(models.Model):
    class Priority(models.IntegerChoices):
        LOW = 1, 'low'
        MEDIUM = 2, 'medium'
        HIGH = 3, 'high'

    class Status(models.IntegerChoices):
        PENDING = 1, 'pending'
        COMPLETED = 2, 'completed'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='todos')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.IntegerField(choices=Status.choices, default=Status.PENDING)
    priority = models.IntegerField(choices=Priority.choices, default=Priority.LOW)
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        db_table = 'todos'

    def __str__(self):
        return self.title