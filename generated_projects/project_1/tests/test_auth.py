import pytest
from rest_framework import status
from django.contrib.auth import get_user_model

User = get_user_model()

@pytest.mark.django_db
class TestAuthFlow:
    def test_registration_success(self, api_client):
        data = {
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'password123',
            'password_confirm': 'password123'
        }
        response = api_client.post('/api/auth/register/', data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert 'access' in response.data

    def test_registration_mismatch_password(self, api_client):
        data = {'username': 'newuser', 'email': 'a@b.com', 'password': '1', 'password_confirm': '2'}
        response = api_client.post('/api/auth/register/', data, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_login_success(self, api_client, user):
        data = {'username': 'testuser', 'password': 'password123'}
        response = api_client.post('/api/auth/login/', data, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data

    def test_invalid_login(self, api_client):
        response = api_client.post('/api/auth/login/', {'username': 'wrong', 'password': 'password'}, format='json')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_token_refresh(self, api_client, user):
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        response = api_client.post('/api/auth/token/refresh/', {'refresh': str(refresh)}, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data

    def test_unauthenticated_access_denied(self, api_client):
        response = api_client.get('/api/todos/')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED