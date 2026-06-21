import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import User


client = TestClient(app)


class FakeResponse:
    def __init__(self, body, status_code=200):
        self.body = body
        self.status_code = status_code
        self.is_error = status_code >= 400

    def json(self):
        return self.body

    def raise_for_status(self):
        if self.is_error:
            raise RuntimeError("respuesta simulada con error")


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, **kwargs):
        assert "open-meteo.com" in url
        return FakeResponse({"current": {"temperature_2m": 24.5, "relative_humidity_2m": 48}})

    async def post(self, url, **kwargs):
        assert "api.openai.com" in url
        return FakeResponse({"id": "resp_test", "output_text": "Respuesta de prueba", "output": []})


def test_complete_api_flow(monkeypatch):
    suffix = uuid.uuid4().hex[:10]
    email = f"integral-{suffix}@example.com"
    password = "password123"

    # Sistema y autenticación
    assert client.get("/health").json() == {"estado": "en línea"}
    registered = client.post("/auth/register", json={"email": email, "name": "Prueba Integral", "password": password})
    assert registered.status_code == 201
    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Usuarios
    assert client.get("/users/me", headers=headers).json()["email"] == email
    assert client.get("/users", headers=headers).status_code == 403

    # Tareas: CRUD completo
    created_task = client.post("/tasks", headers=headers, json={"title": "Tarea integral", "description": "Prueba", "completed": False})
    assert created_task.status_code == 201
    task_id = created_task.json()["id"]
    assert client.get(f"/tasks/{task_id}", headers=headers).status_code == 200
    updated_task = client.put(f"/tasks/{task_id}", headers=headers, json={"title": "Tarea actualizada", "completed": True})
    assert updated_task.status_code == 200 and updated_task.json()["completed"] is True
    assert client.delete(f"/tasks/{task_id}", headers=headers).status_code == 204

    # Elevar el usuario de prueba para verificar operaciones administrativas.
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        user.role = "admin"
        db.commit()

    # El JWT conserva el rol anterior, pero la autorización consulta el usuario actualizado.
    category = client.post("/categories", headers=headers, json={"name": f"Categoría {suffix}"})
    assert category.status_code == 201
    product = client.post("/products", headers=headers, json={"name": f"Producto {suffix}", "price": 125.5, "stock": 10, "category_id": category.json()["id"]})
    assert product.status_code == 201
    product_id = product.json()["id"]
    assert any(item["id"] == product_id for item in client.get("/products").json())

    # Ventas y pagos
    order = client.post("/orders", headers=headers, json={"product_id": product_id, "quantity": 2})
    assert order.status_code == 201 and order.json()["total"] == 251.0
    payment = client.post(f"/payments/orders/{order.json()['id']}", headers=headers)
    assert payment.status_code == 201 and payment.json()["estado"] == "pendiente"
    assert client.post(f"/payments/orders/{order.json()['id']}", headers=headers).status_code == 409

    # Proveedores externos simulados de forma determinista.
    monkeypatch.setattr("app.main.httpx.AsyncClient", FakeAsyncClient)
    weather = client.get("/weather", params={"latitude": 19.43, "longitude": -99.13})
    assert weather.status_code == 200 and weather.json()["current"]["temperature_2m"] == 24.5

    previous_key = settings.openai_api_key
    settings.openai_api_key = "test-key"
    try:
        ai = client.post("/ai/generate", headers=headers, json={"prompt": "Hola"})
        assert ai.status_code == 200 and ai.json()["texto"] == "Respuesta de prueba"
    finally:
        settings.openai_api_key = previous_key

