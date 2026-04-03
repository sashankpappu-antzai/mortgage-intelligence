import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from jose import JWTError, jwt
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
    if not user or not user.hashed_password or not pwd_context.verify(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = _create_token(str(user.id), timedelta(minutes=settings.jwt_access_token_expire_minutes))
    refresh_token = _create_token(str(user.id), timedelta(days=settings.jwt_refresh_token_expire_days))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={"id": str(user.id), "email": user.email, "name": user.name, "role": user.role},
    )


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest, db: DB):
    try:
        payload = jwt.decode(req.refresh_token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id), User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

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


# --- Microsoft / Azure AD ---


class MicrosoftLoginRequest(BaseModel):
    code: str
    redirect_uri: str


class MicrosoftCompleteRequest(BaseModel):
    code: str
    redirect_uri: str
    role: UserRole = UserRole.LOAN_OFFICER
    tenant_name: str = "Default"


@router.get("/microsoft/config")
async def microsoft_config():
    """Return Azure AD config if configured, so frontend knows to show the button."""
    from ..auth.azure_ad import is_configured

    if not is_configured():
        return {"configured": False}
    return {
        "configured": True,
        "tenant_id": settings.azure_ad_tenant_id,
        "client_id": settings.azure_ad_client_id,
        "redirect_uri": settings.azure_ad_redirect_uri,
    }


@router.post("/microsoft")
async def microsoft_login(req: MicrosoftLoginRequest, db: DB):
    """Exchange Microsoft auth code. Returns tokens if user exists, or needs_role if new."""
    from ..auth.azure_ad import exchange_code_for_tokens, extract_user_info, is_configured

    if not is_configured():
        raise HTTPException(status_code=400, detail="Azure AD not configured")

    try:
        tokens = await exchange_code_for_tokens(req.code, req.redirect_uri)
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to exchange authorization code")

    user_info = extract_user_info(tokens["id_token"])
    oid = user_info["oid"]
    email = user_info["email"]

    # Look up by azure_ad_oid first, then by email
    result = await db.execute(select(User).where(User.azure_ad_oid == oid, User.is_active.is_(True)))
    user = result.scalar_one_or_none()

    if not user and email:
        result = await db.execute(select(User).where(User.email == email, User.is_active.is_(True)))
        user = result.scalar_one_or_none()
        if user and not user.azure_ad_oid:
            user.azure_ad_oid = oid
            await db.flush()

    if user:
        access_token = _create_token(str(user.id), timedelta(minutes=settings.jwt_access_token_expire_minutes))
        refresh_token = _create_token(str(user.id), timedelta(days=settings.jwt_refresh_token_expire_days))
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user={"id": str(user.id), "email": user.email, "name": user.name, "role": user.role},
        )

    # New user — frontend needs to collect role
    return {
        "needs_role": True,
        "email": email,
        "name": user_info["name"],
        "azure_ad_oid": oid,
    }


@router.post("/microsoft/complete", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def microsoft_complete(req: MicrosoftCompleteRequest, db: DB):
    """Complete Microsoft sign-in for new users — exchanges code again and creates user with chosen role."""
    from ..auth.azure_ad import exchange_code_for_tokens, extract_user_info, is_configured

    if not is_configured():
        raise HTTPException(status_code=400, detail="Azure AD not configured")

    try:
        tokens = await exchange_code_for_tokens(req.code, req.redirect_uri)
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to exchange authorization code")

    user_info = extract_user_info(tokens["id_token"])
    oid = user_info["oid"]
    email = user_info["email"]

    # Check not already registered
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User already exists. Use regular sign-in.")

    # Create or get tenant
    tenant_result = await db.execute(select(Tenant).where(Tenant.name == req.tenant_name))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        tenant = Tenant(name=req.tenant_name)
        db.add(tenant)
        await db.flush()

    user = User(
        email=email,
        name=user_info["name"],
        role=req.role,
        azure_ad_oid=oid,
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
