import pytest
from apps.accounts.models import User

@pytest.mark.django_db
def test_user_creation():
    user = User.objects.create_user(
        username='newuser',
        email='new@example.com',
        password='securepassword'
    )
    assert user.username == 'newuser'
    assert user.email == 'new@example.com'
    assert user.check_password('securepassword')

@pytest.mark.django_db
def test_user_string_representation():
    user = User.objects.create_user(
        username='stringtest',
        email='string@example.com',
        password='password123'
    )
    assert str(user) == 'stringtest'