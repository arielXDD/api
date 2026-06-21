from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class Register(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=8, max_length=72)

class Login(BaseModel):
    email: EmailStr
    password: str

class UserOut(ORM):
    id: int; email: EmailStr; name: str; role: str; active: bool

class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    description: str | None = None
    completed: bool = False

class TaskOut(TaskIn, ORM):
    id: int; owner_id: int

class CategoryIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)

class ProductIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    price: float = Field(gt=0)
    stock: int = Field(ge=0)
    category_id: int

class ProductOut(ProductIn, ORM):
    id: int

class OrderIn(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)

class OrderOut(ORM):
    id: int; user_id: int; product_id: int; quantity: int; total: float; status: str

class AIRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)

