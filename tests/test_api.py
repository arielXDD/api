import os
os.environ["DATABASE_URL"] = "sqlite:///./test.db"
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_register_login_and_tasks():
    assert client.get("/health").status_code == 200
    email = "test@example.com"
    client.post("/auth/register", json={"email": email, "name": "Tester", "password": "password123"})
    login = client.post("/auth/login", json={"email": email, "password": "password123"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    created = client.post("/tasks", headers=headers, json={"title": "Probar API", "completed": False})
    assert created.status_code == 201
    assert client.get("/tasks", headers=headers).json()[0]["title"] == "Probar API"

def test_validation_and_authentication_required():
    assert client.post("/auth/register", json={"email": "bad", "name": "x", "password": "1"}).status_code == 422
    assert client.get("/tasks").status_code in (401, 403)

