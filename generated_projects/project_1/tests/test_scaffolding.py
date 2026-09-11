import pytest
from django.conf import settings
from django.urls import reverse
from rest_framework import status

def test_settings_load_successfully():
    """Verify that basic Django settings are loaded correctly."""
    assert settings.SECRET_KEY is not None
    assert isinstance(settings.DEBUG, bool)
    assert '*' in settings.ALLOWED_HOSTS

def test_installed_apps_contain_required_packages():
    """Verify that essential apps are configured in INSTALLED_APPS."""
    required_apps = [
        'rest_framework',
        'rest_framework_simplejwt',
        'corsheaders',
        'django_filters',
    ]
    for app in required_apps:
        assert app in settings.INSTALLED_APPS

def test_middleware_order_and_cors():
    """Verify that CorsMiddleware is placed first in middleware configuration."""
    assert 'corsheaders.middleware.CorsMiddleware' in settings.MIDDLEWARE
    assert settings.MIDDLEWARE[0] == 'corsheaders.middleware.CorsMiddleware'

def test_simple_jwt_configuration():
    """Verify JWT configuration settings are correctly initialized."""
    assert hasattr(settings, 'SIMPLE_JWT')
    jwt_settings = settings.SIMPLE_JWT
    assert jwt_settings['AUTH_HEADER_TYPES'] == ('Bearer',)
    assert jwt_settings['ALGORITHM'] == 'HS256'
    assert 'ACCESS_TOKEN_LIFETIME' in jwt_settings
    assert 'REFRESH_TOKEN_LIFETIME' in jwt_settings

def test_rest_framework_configuration():
    """Verify DRF is configured with JWT auth and standard permissions."""
    assert hasattr(settings, 'REST_FRAMEWORK')
    drf_settings = settings.REST_FRAMEWORK
    assert 'rest_framework_simplejwt.authentication.JWTAuthentication' in drf_settings['DEFAULT_AUTHENTICATION_CLASSES']
    assert 'rest_framework.permissions.IsAuthenticated' in drf_settings['DEFAULT_PERMISSION_CLASSES']
    assert 'django_filters.rest_framework.DjangoFilterBackend' in drf_settings['DEFAULT_FILTER_BACKENDS']

def test_health_check_endpoint(api_client):
    """Verify that the backend health check API is responsive and returns success status."""
    url = reverse('health-check')
    response = api_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data['status'] == 'healthy'
    assert data['service'] == 'backend'
