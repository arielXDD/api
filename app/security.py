from datetime import datetime, timedelta, timezone
import bcrypt, jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from .config import settings
from .database import get_db
from .models import User

bearer = HTTPBearer()

def hash_password(value: str) -> str:
    return bcrypt.hashpw(value.encode(), bcrypt.gensalt()).decode()

def verify_password(value: str, hashed: str) -> bool:
    return bcrypt.checkpw(value.encode(), hashed.encode())

def token_for(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    return jwt.encode({"sub": str(user.id), "role": user.role, "exp": exp}, settings.jwt_secret, algorithm="HS256")

def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=["HS256"])
        user = db.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(401, "Token inválido o vencido")
    if not user or not user.active:
        raise HTTPException(401, "Usuario no disponible")
    return user

def admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin": raise HTTPException(403, "Se requiere rol admin")
    return user

