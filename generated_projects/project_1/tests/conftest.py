import os, sys
import pytest
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django; django.setup()

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def test_user(db):
    User = get_user_model()
    return User.objects.create_user(username='testuser', password='password123', email='test@example.com')

@pytest.fixture
def user(test_user):
    return test_user

@pytest.fixture
def auth_headers(user):
    from rest_framework_simplejwt.tokens import RefreshToken
    refresh = RefreshToken.for_user(user)
    return {'HTTP_AUTHORIZATION': f'Bearer {refresh.access_token}'}

@pytest.fixture
def authenticated_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client
