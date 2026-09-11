import pytest
from apps.accounts.serializers import RegisterSerializer, UserSerializer
from apps.accounts.models import User

@pytest.mark.django_db
def test_register_serializer_valid_data():
    data = {
        'username': 'validuser',
        'email': 'valid@example.com',
        'password': 'password123',
        'password_confirm': 'password123'
    }
    serializer = RegisterSerializer(data=data)
    assert serializer.is_valid(), serializer.errors

@pytest.mark.django_db
def test_register_serializer_password_mismatch():
    data = {
        'username': 'user1',
        'email': 'user1@example.com',
        'password': 'password123',
        'password_confirm': 'differentpassword'
    }
    serializer = RegisterSerializer(data=data)
    assert not serializer.is_valid()
    assert 'password' in serializer.errors

@pytest.mark.django_db
def test_register_serializer_duplicate_email():
    User.objects.create_user(username='existing', email='duplicate@example.com', password='password123')
    data = {
        'username': 'newuser',
        'email': 'duplicate@example.com',
        'password': 'password123',
        'password_confirm': 'password123'
    }
    serializer = RegisterSerializer(data=data)
    assert not serializer.is_valid()
    assert 'email' in serializer.errors

@pytest.mark.django_db
def test_register_serializer_password_too_short():
    data = {
        'username': 'user1',
        'email': 'user1@example.com',
        'password': '123',
        'password_confirm': '123'
    }
    serializer = RegisterSerializer(data=data)
    assert not serializer.is_valid()
    assert 'password' in serializer.errors

@pytest.mark.django_db
def test_user_serializer():
    user = User.objects.create_user(username='u', email='e@e.com', password='p')
    serializer = UserSerializer(user)
    assert serializer.data['username'] == 'u'
    assert serializer.data['email'] == 'e@e.com'