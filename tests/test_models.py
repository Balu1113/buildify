import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.database import Base
from models.expense_models import User, Category, Expense
from sqlalchemy.exc import IntegrityError

@pytest.fixture
def db_session():
    # Use an in-memory SQLite database for testing
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)

def test_model_creation(db_session):
    # Test User creation
    user = User(email="test@example.com", hashed_password="password123")
    db_session.add(user)
    db_session.commit()
    
    # Test Category creation
    cat = Category(name="Food")
    db_session.add(cat)
    db_session.commit()
    
    saved_user = db_session.query(User).filter_by(email="test@example.com").first()
    saved_cat = db_session.query(Category).filter_by(name="Food").first()
    
    assert saved_user is not None
    assert saved_user.email == "test@example.com"
    assert saved_cat is not None
    assert saved_cat.name == "Food"

def test_relationships(db_session):
    user = User(email="rel@example.com", hashed_password="pw")
    db_session.add(user)
    db_session.commit()
    
    expense = Expense(amount=50.0, description="Groceries", user_id=user.id)
    db_session.add(expense)
    db_session.commit()
    
    user_record = db_session.query(User).filter_by(email="rel@example.com").first()
    assert len(user_record.expenses) == 1
    assert user_record.expenses[0].amount == 50.0
    assert user_record.expenses[0].description == "Groceries"

def test_unique_constraints(db_session):
    # Test unique email constraint
    user1 = User(email="unique@example.com", hashed_password="pw")
    user2 = User(email="unique@example.com", hashed_password="pw")
    db_session.add(user1)
    db_session.commit()
    
    db_session.add(user2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Test unique category name constraint
    cat1 = Category(name="Utilities")
    cat2 = Category(name="Utilities")
    db_session.add(cat1)
    db_session.commit()
    
    db_session.add(cat2)
    with pytest.raises(IntegrityError):
        db_session.commit()