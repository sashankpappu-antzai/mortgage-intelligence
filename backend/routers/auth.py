import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from ..core.config import get_settings
from ..core.rate_limit import limiter
from ..db.models.tenant import Tenant
from ..db.models.user import User
from ..dependencies import DB, CurrentUser
from ..shared.types import UserRole

settings = get_settings()

router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# In trial / hosted-demo mode, every signup gets a fresh isolated tenant and a
# fixed default role.  Role + tenant are server-assigned — never trust the client.
_DEFAULT_TRIAL_ROLE = UserRole.LOAN_OFFICER


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


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


def _issue_tokens(user: User) -> TokenResponse:
    access_token = _create_token(
        str(user.id), timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    refresh_token = _create_token(
        str(user.id), timedelta(days=settings.jwt_refresh_token_expire_days)
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={"id": str(user.id), "email": user.email, "name": user.name, "role": user.role},
    )


def _trial_tenant_name(email: str, display_name: str) -> str:
    # Fresh-tenant-per-signup ensures no cross-prospect data leakage in trial.
    short = (display_name or email.split("@", 1)[0]).strip()
    return f"{short}'s workspace ({uuid.uuid4().hex[:6]})"


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, req: RegisterRequest, db: DB):
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        # Avoid account-enumeration: same shape as the success path but with no token.
        raise HTTPException(status_code=400, detail="Registration could not be completed")

    # Each registration creates a brand-new tenant.  Role is server-assigned —
    # the client cannot elect ADMIN or join an existing tenant.
    tenant = Tenant(name=_trial_tenant_name(req.email, req.name))
    db.add(tenant)
    await db.flush()

    user = User(
        email=req.email,
        name=req.name,
        hashed_password=pwd_context.hash(req.password),
        role=_DEFAULT_TRIAL_ROLE,
        tenant_id=tenant.id,
    )
    db.add(user)
    await db.flush()
    return _issue_tokens(user)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, req: LoginRequest, db: DB):
    result = await db.execute(select(User).where(User.email == req.email, User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if not user or not user.hashed_password or not pwd_context.verify(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return _issue_tokens(user)


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
async def refresh(request: Request, req: RefreshRequest, db: DB):
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
    return _issue_tokens(user)


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
    # role and tenant_name are NOT accepted from the client — server-assigned.


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
@limiter.limit("10/minute")
async def microsoft_login(request: Request, req: MicrosoftLoginRequest, db: DB):
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
        return _issue_tokens(user)

    # New user — frontend confirms then calls /complete (no role choice exposed)
    return {
        "needs_signup": True,
        "email": email,
        "name": user_info["name"],
        "azure_ad_oid": oid,
    }


@router.post("/microsoft/complete", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def microsoft_complete(request: Request, req: MicrosoftCompleteRequest, db: DB):
    """Complete Microsoft sign-in for new users — server assigns role + tenant."""
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

    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User already exists. Use regular sign-in.")

    tenant = Tenant(name=_trial_tenant_name(email, user_info["name"]))
    db.add(tenant)
    await db.flush()

    user = User(
        email=email,
        name=user_info["name"],
        role=_DEFAULT_TRIAL_ROLE,
        azure_ad_oid=oid,
        tenant_id=tenant.id,
    )
    db.add(user)
    await db.flush()
    return _issue_tokens(user)
