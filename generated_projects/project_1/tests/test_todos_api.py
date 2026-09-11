import pytest
from rest_framework import status
from apps.todos.models import Todo

@pytest.mark.django_db
def test_todo_crud(authenticated_client, user):
    # Create
    res = authenticated_client.post('/api/todos/', {
        'title': 'Test Todo', 'description': 'Desc', 'status': 'pending', 'priority': 'medium'
    })
    assert res.status_code == status.HTTP_201_CREATED
    
    # List
    res = authenticated_client.get('/api/todos/')
    assert res.data['count'] == 1
    
    # Update
    todo_id = res.data['results'][0]['id']
    res = authenticated_client.patch(f'/api/todos/{todo_id}/', {'title': 'Updated'})
    assert res.data['title'] == 'Updated'
    
    # Delete
    res = authenticated_client.delete(f'/api/todos/{todo_id}/')
    assert res.status_code == status.HTTP_204_NO_CONTENT

@pytest.mark.django_db
def test_todo_user_isolation(authenticated_client, user):
    from django.contrib.auth import get_user_model
    other = get_user_model().objects.create_user(username='other', password='pw')
    Todo.objects.create(title='Other Task', user=other)
    
    res = authenticated_client.get('/api/todos/')
    assert res.data['count'] == 0

@pytest.mark.django_db
def test_dashboard_metrics(authenticated_client, user):
    Todo.objects.create(title='1', user=user, status=Todo.Status.PENDING)
    Todo.objects.create(title='2', user=user, status=Todo.Status.COMPLETED)
    
    res = authenticated_client.get('/api/todos/dashboard/')
    assert res.data['total'] == 2
    assert res.data['pending'] == 1
    assert res.data['completed'] == 1