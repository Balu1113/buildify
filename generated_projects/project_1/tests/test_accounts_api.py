import pytest
from django.urls import reverse
from rest_framework import status

@pytest.mark.django_db
def test_register_endpoint(api_client):
    url = reverse('auth-register')
    payload = {
        'username': 'newreg',
        'email': 'newreg@example.com',
        'password': 'password123',
        'password_confirm': 'password123'
    }
    response = api_client.post(url, payload)
    assert response.status_code == status.HTTP_201_CREATED
    assert 'access' in response.data
    assert 'refresh' in response.data
    assert response.data['user']['username'] == 'newreg'

@pytest.mark.django_db
def test_login_endpoint(api_client, user):
    url = reverse('auth-login')
    payload = {
        'username': user.username,
        'password': 'password123'
    }
    response = api_client.post(url, payload)
    assert response.status_code == status.HTTP_200_OK
    assert 'access' in response.data
    assert 'user' in response.data

@pytest.mark.django_db
def test_login_failure(api_client, user):
    url = reverse('auth-login')
    payload = {
        'username': user.username,
        'password': 'wrongpassword'
    }
    response = api_client.post(url, payload)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

@pytest.mark.django_db
def test_token_refresh(api_client, user):
    from rest_framework_simplejwt.tokens import RefreshToken
    refresh = RefreshToken.for_user(user)
    url = reverse('auth-token-refresh')
    payload = {'refresh': str(refresh)}
    response = api_client.post(url, payload)
    assert response.status_code == status.HTTP_200_OK
    assert 'access' in response.data

@pytest.mark.django_db
def test_user_detail_authenticated(authenticated_client, user):
    url = reverse('auth-user-detail')
    response = authenticated_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data['username'] == user.username

@pytest.mark.django_db
def test_user_detail_unauthenticated(api_client):
    url = reverse('auth-user-detail')
    response = api_client.get(url)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

@pytest.mark.django_db
def test_logout_success(authenticated_client, user):
    # Need a real refresh token to blacklist
    from rest_framework_simplejwt.tokens import RefreshToken
    refresh = RefreshToken.for_user(user)
    refresh_str = str(refresh)
    
    url = reverse('auth-logout')
    response = authenticated_client.post(url, {'refresh': refresh_str})
    assert response.status_code == status.HTTP_205_RESET_CONTENT

@pytest.mark.django_db
def test_logout_failure_missing_token(authenticated_client):
    url = reverse('auth-logout')
    response = authenticated_client.post(url, {})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'detail' in response.data

@pytest.mark.django_db
def test_health_check(api_client):
    url = reverse('health-check')
    response = api_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data['status'] == 'healthy'