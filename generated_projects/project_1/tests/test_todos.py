import pytest
from apps.todos.models import Todo
from rest_framework import status
from django.contrib.auth import get_user_model

@pytest.mark.django_db
def test_todo_crud(authenticated_client, test_user):
    # Create
    response = authenticated_client.post('/api/todos/', {
        'title': 'Test Todo', 'description': 'Desc', 'status': 'pending', 'priority': 'low'
    })
    assert response.status_code == status.HTTP_201_CREATED
    
    # List
    response = authenticated_client.get('/api/todos/')
    assert len(response.data['results']) == 1
    
    # Detail
    todo_id = response.data['results'][0]['id']
    response = authenticated_client.get(f'/api/todos/{todo_id}/')
    assert response.status_code == status.HTTP_200_OK
    
    # Update
    response = authenticated_client.patch(f'/api/todos/{todo_id}/', {'status': 'completed'})
    assert response.data['status'] == 'completed'

@pytest.mark.django_db
def test_user_isolation(api_client, test_user):
    other_user = get_user_model().objects.create_user(username='other', password='password')
    Todo.objects.create(user=other_user, title='Other Todo')
    
    api_client.force_authenticate(user=test_user)
    response = api_client.get('/api/todos/')
    assert response.data['count'] == 0

@pytest.mark.django_db
def test_dashboard_metrics(authenticated_client, test_user):
    Todo.objects.create(user=test_user, title='P', status=Todo.Status.PENDING, priority=Todo.Priority.HIGH)
    Todo.objects.create(user=test_user, title='C', status=Todo.Status.COMPLETED)
    
    response = authenticated_client.get('/api/todos/dashboard/')
    assert response.status_code == status.HTTP_200_OK
    assert response.data['total'] == 2
    assert response.data['pending'] == 1
    assert response.data['completed'] == 1
    assert response.data['high_priority'] == 1

@pytest.mark.django_db
def test_filtering_and_sorting(authenticated_client, test_user):
    Todo.objects.create(user=test_user, title='A', status=Todo.Status.PENDING)
    Todo.objects.create(user=test_user, title='B', status=Todo.Status.COMPLETED)
    
    # Search
    res = authenticated_client.get('/api/todos/?search=A')
    assert res.data['count'] == 1
    
    # Filter
    res = authenticated_client.get('/api/todos/?status=2')
    assert res.data['count'] == 1
