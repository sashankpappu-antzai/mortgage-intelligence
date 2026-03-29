import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy import select

from ..core.config import get_settings
from ..dependencies import DB, CurrentUser

settings = get_settings()
from ..db.models.tenant import Tenant
from ..db.models.user import User
from ..shared.types import UserRole

router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: UserRole = UserRole.LOAN_OFFICER
    tenant_name: str = "Default"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    tenant_id: str


def _create_token(user_id: str, expires_delta: timedelta) -> str:
    expire = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(
        {"sub": user_id, "exp": expire},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, db: DB):
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create or get tenant
    tenant_result = await db.execute(select(Tenant).where(Tenant.name == req.tenant_name))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        tenant = Tenant(name=req.tenant_name)
        db.add(tenant)
        await db.flush()

    user = User(
        email=req.email,
        name=req.name,
        hashed_password=pwd_context.hash(req.password),
        role=req.role,
        tenant_id=tenant.id,
    )
    db.add(user)
    await db.flush()

    access_token = _create_token(str(user.id), timedelta(minutes=settings.jwt_access_token_expire_minutes))
    refresh_token = _create_token(str(user.id), timedelta(days=settings.jwt_refresh_token_expire_days))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={"id": str(user.id), "email": user.email, "name": user.name, "role": user.role},
    )


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: DB):
    result = await db.execute(select(User).where(User.email == req.email, User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if not user or not pwd_context.verify(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = _create_token(str(user.id), timedelta(minutes=settings.jwt_access_token_expire_minutes))
    refresh_token = _create_token(str(user.id), timedelta(days=settings.jwt_refresh_token_expire_days))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={"id": str(user.id), "email": user.email, "name": user.name, "role": user.role},
    )


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser):
    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name,
        role=user.role,
        tenant_id=str(user.tenant_id),
    )
