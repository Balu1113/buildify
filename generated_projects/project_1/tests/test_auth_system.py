import pytest
from rest_framework import status
from django.contrib.auth import get_user_model

User = get_user_model()

@pytest.mark.django_db
def test_registration_flow(api_client):
    url = '/api/auth/register/'
    data = {
        'username': 'newuser',
        'email': 'new@example.com',
        'password': 'password123',
        'password_confirm': 'password123'
    }
    response = api_client.post(url, data, format='json')
    assert response.status_code == status.HTTP_201_CREATED
    assert 'access' in response.data
    assert User.objects.filter(username='newuser').exists()

@pytest.mark.django_db
def test_login_flow(api_client, user):
    url = '/api/auth/login/'
    response = api_client.post(url, {'username': 'testuser', 'password': 'password123'}, format='json')
    assert response.status_code == status.HTTP_200_OK
    assert 'access' in response.data
    assert 'refresh' in response.data

@pytest.mark.django_db
def test_token_refresh(api_client, user):
    from rest_framework_simplejwt.tokens import RefreshToken
    refresh = RefreshToken.for_user(user)
    response = api_client.post('/api/auth/token/refresh/', {'refresh': str(refresh)})
    assert response.status_code == status.HTTP_200_OK
    assert 'access' in response.data

@pytest.mark.django_db
def test_unauthenticated_access_denied(api_client):
    response = api_client.get('/api/todos/')
    assert response.status_code == status.HTTP_401_UNAUTHORIZED