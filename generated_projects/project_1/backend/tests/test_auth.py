import pytest
from django.urls import reverse
from rest_framework import status
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


@pytest.mark.django_db
def test_registration_success(api_client):
    url = reverse('auth-register')
    payload = {
        'username': 'brandnewuser',
        'email': 'brandnew@example.com',
        'password': 'StrongPassword123!',
        'password_confirm': 'StrongPassword123!'
    }
    response = api_client.post(url, payload)
    assert response.status_code == status.HTTP_201_CREATED
    assert 'access' in response.data
    assert 'refresh' in response.data
    assert response.data['user']['username'] == 'brandnewuser'
    assert response.data['user']['email'] == 'brandnew@example.com'
    assert User.objects.filter(username='brandnewuser').exists()


@pytest.mark.django_db
def test_registration_mismatched_password(api_client):
    url = reverse('auth-register')
    payload = {
        'username': 'mismatchuser',
        'email': 'mismatch@example.com',
        'password': 'StrongPassword123!',
        'password_confirm': 'DifferentPassword123!'
    }
    response = api_client.post(url, payload)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'password' in response.data


@pytest.mark.django_db
def test_registration_duplicate_email(api_client, user):
    url = reverse('auth-register')
    payload = {
        'username': 'uniqueuser',
        'email': user.email,
        'password': 'StrongPassword123!',
        'password_confirm': 'StrongPassword123!'
    }
    response = api_client.post(url, payload)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'email' in response.data


@pytest.mark.django_db
def test_registration_duplicate_username(api_client, user):
    url = reverse('auth-register')
    payload = {
        'username': user.username,
        'email': 'unique@example.com',
        'password': 'StrongPassword123!',
        'password_confirm': 'StrongPassword123!'
    }
    response = api_client.post(url, payload)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'username' in response.data


@pytest.mark.django_db
def test_registration_weak_password(api_client):
    url = reverse('auth-register')
    payload = {
        'username': 'weakuser',
        'email': 'weak@example.com',
        'password': '123',
        'password_confirm': '123'
    }
    response = api_client.post(url, payload)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'password' in response.data


@pytest.mark.django_db
def test_registration_missing_fields(api_client):
    url = reverse('auth-register')
    # Missing email
    payload = {
        'username': 'missingemail',
        'password': 'StrongPassword123!',
        'password_confirm': 'StrongPassword123!'
    }
    response = api_client.post(url, payload)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'email' in response.data

    # Missing username
    payload = {
        'email': 'missingusername@example.com',
        'password': 'StrongPassword123!',
        'password_confirm': 'StrongPassword123!'
    }
    response = api_client.post(url, payload)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'username' in response.data


@pytest.mark.django_db
def test_login_success(api_client, user):
    url = reverse('auth-login')
    payload = {
        'username': user.username,
        'password': 'password123'
    }
    response = api_client.post(url, payload)
    assert response.status_code == status.HTTP_200_OK
    assert 'access' in response.data
    assert 'refresh' in response.data
    assert response.data['user']['username'] == user.username
    assert response.data['user']['email'] == user.email


@pytest.mark.django_db
def test_login_invalid_credentials(api_client, user):
    url = reverse('auth-login')
    payload = {
        'username': user.username,
        'password': 'wrongpassword'
    }
    response = api_client.post(url, payload)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_login_nonexistent_user(api_client):
    url = reverse('auth-login')
    payload = {
        'username': 'nonexistent',
        'password': 'password123'
    }
    response = api_client.post(url, payload)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_token_refresh(api_client, user):
    refresh = RefreshToken.for_user(user)
    url = reverse('auth-token-refresh')
    response = api_client.post(url, {'refresh': str(refresh)})
    assert response.status_code == status.HTTP_200_OK
    assert 'access' in response.data


@pytest.mark.django_db
def test_token_refresh_invalid_token(api_client):
    url = reverse('auth-token-refresh')
    response = api_client.post(url, {'refresh': 'invalidtoken'})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_token_refresh_missing_token(api_client):
    url = reverse('auth-token-refresh')
    response = api_client.post(url, {})
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_user_detail_authenticated(authenticated_client, user):
    url = reverse('auth-user-detail')
    response = authenticated_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data['username'] == user.username
    assert response.data['email'] == user.email


@pytest.mark.django_db
def test_user_detail_unauthenticated(api_client):
    url = reverse('auth-user-detail')
    response = api_client.get(url)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_logout_success(authenticated_client, user):
    refresh = RefreshToken.for_user(user)
    url = reverse('auth-logout')
    response = authenticated_client.post(url, {'refresh': str(refresh)})
    assert response.status_code == status.HTTP_205_RESET_CONTENT


@pytest.mark.django_db
def test_logout_missing_refresh_token(authenticated_client):
    url = reverse('auth-logout')
    response = authenticated_client.post(url, {})
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_logout_invalid_refresh_token(authenticated_client):
    url = reverse('auth-logout')
    response = authenticated_client.post(url, {'refresh': 'invalidtoken'})
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_logout_already_blacklisted_token(authenticated_client, user):
    refresh = RefreshToken.for_user(user)
    url = reverse('auth-logout')
    # First logout should succeed
    response = authenticated_client.post(url, {'refresh': str(refresh)})
    assert response.status_code == status.HTTP_205_RESET_CONTENT
    
    # Second logout with same token should fail
    response = authenticated_client.post(url, {'refresh': str(refresh)})
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_jwt_authentication_required_for_protected_endpoints(api_client):
    # Test accessing protected endpoint without authentication
    url = reverse('auth-user-detail')
    response = api_client.get(url)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_jwt_authentication_with_valid_token(authenticated_client, user):
    # Test accessing protected endpoint with valid token
    url = reverse('auth-user-detail')
    response = authenticated_client.get(url)
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_jwt_authentication_with_invalid_token(api_client):
    # Test accessing protected endpoint with invalid token
    url = reverse('auth-user-detail')
    api_client.credentials(HTTP_AUTHORIZATION='Bearer invalidtoken')
    response = api_client.get(url)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_custom_user_model_attributes(user):
    """Test that the custom User model has the expected attributes"""
    assert hasattr(user, 'email')
    assert hasattr(user, 'username')
    assert hasattr(user, 'first_name')
    assert hasattr(user, 'last_name')
    assert hasattr(user, 'date_joined')
    assert user.email == 'test@example.com'
    assert user.username == 'testuser'


@pytest.mark.django_db
def test_user_serializer_fields(user):
    """Test that UserSerializer includes expected fields"""
    from apps.accounts.serializers import UserSerializer
    serializer = UserSerializer(user)
    data = serializer.data
    
    expected_fields = {'id', 'username', 'email', 'first_name', 'last_name', 'date_joined'}
    assert set(data.keys()) == expected_fields
    assert data['username'] == user.username
    assert data['email'] == user.email


@pytest.mark.django_db
def test_register_serializer_validation():
    """Test RegisterSerializer validation methods"""
    from apps.accounts.serializers import RegisterSerializer
    
    # Test password validation
    serializer = RegisterSerializer(data={
        'username': 'testuser',
        'email': 'test@example.com',
        'password': 'short',
        'password_confirm': 'short'
    })
    assert not serializer.is_valid()
    assert 'password' in serializer.errors
    
    # Test password confirmation validation
    serializer = RegisterSerializer(data={
        'username': 'testuser',
        'email': 'test@example.com',
        'password': 'StrongPassword123!',
        'password_confirm': 'DifferentPassword123!'
    })
    assert not serializer.is_valid()
    assert 'password' in serializer.errors