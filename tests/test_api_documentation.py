import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_openapi_schema_generation():
    """
    Verify that the /openapi.json endpoint returns a valid JSON response 
    containing all defined routes.
    """
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "openapi" in schema
    assert "paths" in schema
    # Check for core routes
    assert "/parse-expense" in schema["paths"]
    assert "/tasks/" in schema["paths"]
    assert "/expenses/" in schema["paths"]

def test_swagger_ui_accessibility():
    """
    Verify that the /docs endpoint returns an HTML response for the Swagger UI.
    """
    response = client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "swagger" in response.text.lower()

def test_redoc_accessibility():
    """
    Verify that the /redoc endpoint returns an HTML response for ReDoc.
    """
    response = client.get("/redoc")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "redoc" in response.text.lower()