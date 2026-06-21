from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session
import httpx
from .config import settings
from .database import Base, engine, get_db
from .models import Category, Order, Payment, Product, Task, User
from .schemas import AIRequest, CategoryIn, Login, OrderIn, OrderOut, ProductIn, ProductOut, Register, TaskIn, TaskOut, UserOut
from .security import admin, current_user, hash_password, token_for, verify_password
from .ui import api_portal, reference_portal, swagger_portal

Base.metadata.create_all(engine)
tags_metadata = [
    {"name": "Autenticación", "description": "Registro, inicio de sesión y emisión de tokens JWT."},
    {"name": "Usuarios", "description": "Perfil personal y administración de cuentas."},
    {"name": "Tareas", "description": "Gestión de tareas privadas de cada usuario."},
    {"name": "Productos y ventas", "description": "Catálogo, inventario, categorías y pedidos."},
    {"name": "Pagos", "description": "Pagos asociados a pedidos, sin registros duplicados."},
    {"name": "Clima", "description": "Condiciones meteorológicas por coordenadas."},
    {"name": "Inteligencia artificial", "description": "Generación de texto mediante OpenAI."},
    {"name": "Sistema", "description": "Disponibilidad del servicio."},
]
app = FastAPI(title="API Atlas: 7 APIs", version="1.1.0", description="Servicio REST documentado en español.", openapi_tags=tags_metadata, docs_url=None, redoc_url=None)

@app.get("/", include_in_schema=False)
def portal(): return api_portal()

@app.get("/assets/logo.png", include_in_schema=False)
def logo(): return FileResponse(Path(__file__).resolve().parent.parent / "logo.png", media_type="image/png")

@app.get("/docs", include_in_schema=False)
def docs(): return swagger_portal(app.openapi())

@app.get("/redoc", include_in_schema=False)
def reference(): return reference_portal()

@app.get("/health", summary="Estado del sistema", description="Confirma que el servidor está disponible para recibir solicitudes.", tags=["Sistema"])
def health(): return {"estado": "en línea"}

# 1 y 4: usuarios y autenticación
@app.post("/auth/register", summary="Registrar usuario", response_model=UserOut, status_code=201, tags=["Autenticación"])
def register(data: Register, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == data.email)): raise HTTPException(409, "El correo ya existe")
    user = User(email=data.email, name=data.name, password_hash=hash_password(data.password))
    db.add(user); db.commit(); db.refresh(user); return user

@app.post("/auth/login", summary="Iniciar sesión", tags=["Autenticación"])
def login(data: Login, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email))
    if not user or not verify_password(data.password, user.password_hash): raise HTTPException(401, "Credenciales incorrectas")
    return {"access_token": token_for(user), "token_type": "bearer"}

@app.get("/users/me", summary="Mi perfil", response_model=UserOut, tags=["Usuarios"])
def me(user: User = Depends(current_user)): return user

@app.get("/users", summary="Listar usuarios", response_model=list[UserOut], tags=["Usuarios"])
def users(_: User = Depends(admin), db: Session = Depends(get_db)): return db.scalars(select(User)).all()

# 2: tareas CRUD, aisladas por propietario
@app.post("/tasks", summary="Crear tarea", response_model=TaskOut, status_code=201, tags=["Tareas"])
def create_task(data: TaskIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = Task(**data.model_dump(), owner_id=user.id); db.add(item); db.commit(); db.refresh(item); return item

@app.get("/tasks", summary="Listar mis tareas", response_model=list[TaskOut], tags=["Tareas"])
def list_tasks(user: User = Depends(current_user), db: Session = Depends(get_db)): return db.scalars(select(Task).where(Task.owner_id == user.id)).all()

def owned_task(task_id: int, user: User, db: Session):
    item = db.get(Task, task_id)
    if not item or item.owner_id != user.id: raise HTTPException(404, "Tarea no encontrada")
    return item

@app.get("/tasks/{task_id}", summary="Obtener tarea", response_model=TaskOut, tags=["Tareas"])
def get_task(task_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)): return owned_task(task_id, user, db)

@app.put("/tasks/{task_id}", summary="Actualizar tarea", response_model=TaskOut, tags=["Tareas"])
def update_task(task_id: int, data: TaskIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = owned_task(task_id, user, db)
    for key, value in data.model_dump().items(): setattr(item, key, value)
    db.commit(); db.refresh(item); return item

@app.delete("/tasks/{task_id}", summary="Eliminar tarea", status_code=204, tags=["Tareas"])
def delete_task(task_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(owned_task(task_id, user, db)); db.commit(); return Response(status_code=204)

# 3: catálogo, inventario y pedidos
@app.post("/categories", summary="Crear categoría", status_code=201, tags=["Productos y ventas"])
def category(data: CategoryIn, _: User = Depends(admin), db: Session = Depends(get_db)):
    item = Category(name=data.name); db.add(item); db.commit(); db.refresh(item); return {"id": item.id, "nombre": item.name}

@app.post("/products", summary="Crear producto", response_model=ProductOut, status_code=201, tags=["Productos y ventas"])
def product(data: ProductIn, _: User = Depends(admin), db: Session = Depends(get_db)):
    if not db.get(Category, data.category_id): raise HTTPException(422, "Categoría inexistente")
    item = Product(**data.model_dump()); db.add(item); db.commit(); db.refresh(item); return item

@app.get("/products", summary="Listar productos", response_model=list[ProductOut], tags=["Productos y ventas"])
def products(db: Session = Depends(get_db)): return db.scalars(select(Product)).all()

@app.post("/orders", summary="Crear pedido", response_model=OrderOut, status_code=201, tags=["Productos y ventas"])
def order(data: OrderIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    product = db.get(Product, data.product_id)
    if not product: raise HTTPException(404, "Producto no encontrado")
    if product.stock < data.quantity: raise HTTPException(409, "Inventario insuficiente")
    product.stock -= data.quantity
    item = Order(user_id=user.id, product_id=product.id, quantity=data.quantity, total=round(product.price * data.quantity, 2))
    db.add(item); db.commit(); db.refresh(item); return item

# 5: pagos (flujo local; proveedor real se conecta mediante webhook/adaptador)
@app.post("/payments/orders/{order_id}", summary="Pagar pedido", status_code=201, tags=["Pagos"])
def pay(order_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order or order.user_id != user.id: raise HTTPException(404, "Pedido no encontrado")
    if db.scalar(select(Payment).where(Payment.order_id == order_id)): raise HTTPException(409, "El pago ya fue creado")
    payment = Payment(order_id=order.id, amount=order.total, status="pendiente", provider_reference=f"demo_{order.id}")
    db.add(payment); db.commit(); db.refresh(payment)
    return {"id": payment.id, "monto": payment.amount, "estado": payment.status, "modo": "demo" if not settings.stripe_secret_key else "proveedor_pendiente"}

# 6: clima con Open-Meteo, sin clave
@app.get("/weather", summary="Obtener clima", tags=["Clima"])
async def weather(latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180)):
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get("https://api.open-meteo.com/v1/forecast", params={"latitude": latitude, "longitude": longitude, "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"}); r.raise_for_status()
        except httpx.HTTPError: raise HTTPException(502, "Proveedor climático no disponible")
    return r.json()

# 7: IA; no se simula una respuesta como si fuera del proveedor
@app.post("/ai/generate", summary="Generar texto con IA", tags=["Inteligencia artificial"])
async def generate(data: AIRequest, _: User = Depends(current_user)):
    if not settings.openai_api_key: raise HTTPException(503, "Configure OPENAI_API_KEY")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post("https://api.openai.com/v1/responses", headers={"Authorization": f"Bearer {settings.openai_api_key}"}, json={"model": "gpt-4.1-mini", "input": data.prompt})
    if r.is_error: raise HTTPException(502, "Proveedor de IA rechazó la solicitud")
    body = r.json(); return {"id": body.get("id"), "texto": body.get("output_text", ""), "salida_cruda": body.get("output", [])}
