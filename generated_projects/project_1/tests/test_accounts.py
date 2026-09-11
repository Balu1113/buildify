import pytest
from django.urls import reverse

@pytest.mark.django_db
def test_registration_success(api_client):
    """Test successful user registration."""
    url = reverse('auth-register')
    payload = {
        'username': 'newuser',
        'email': 'new@example.com',
        'password': 'securepassword123',
        'password_confirm': 'securepassword123'
    }
    response = api_client.post(url, payload)
    
    assert response.status_code == 201
    assert 'access' in response.data
    assert 'refresh' in response.data
    assert response.data['user']['username'] == 'newuser'

@pytest.mark.django_db
def test_registration_mismatched_passwords(api_client):
    """Test registration validation for password mismatch."""
    url = reverse('auth-register')
    payload = {
        'username': 'newuser',
        'email': 'new@example.com',
        'password': 'password123',
        'password_confirm': 'differentpassword'
    }
    response = api_client.post(url, payload)
    
    assert response.status_code == 400
    assert 'password' in response.data

@pytest.mark.django_db
def test_login_success(api_client):
    """Test successful login and JWT retrieval."""
    from apps.accounts.models import User
    User.objects.create_user(username='loginuser', email='login@example.com', password='password123')
    
    url = reverse('auth-login')
    payload = {
        'username': 'loginuser',
        'password': 'password123'
    }
    response = api_client.post(url, payload)
    
    assert response.status_code == 200
    assert 'access' in response.data
    assert 'refresh' in response.data

@pytest.mark.django_db
def test_unauthenticated_access_to_user_detail(api_client):
    """Verify that unauthenticated users cannot access protected routes."""
    from apps.accounts.models import User
    u = User.objects.create_user(username='secretuser', email='s@e.com', password='pw')
    
    # Note: The URL pattern for user detail is api/auth/user/
    # but since it uses get_object() based on request.user, 
    # we test the endpoint logic.
    url = reverse('auth-user-detail')
    response = api_client.get(url)
    
    assert response.status_code == 401

@pytest.mark.django_db
def test_user_detail_authenticated(api_client, auth_headers, user):
    """Verify authenticated user can retrieve their own details."""
    url = reverse('auth-user-detail')
    response = api_client.get(url, **auth_headers)
    
    assert response.status_code == 200
    assert response.data['username'] == user.username
    assert response.data['email'] == user.email
