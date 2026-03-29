"""Azure AD OAuth2 authentication dependency."""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2AuthorizationCodeBearer
import jwt

from ..core.config import get_settings

settings = get_settings()

azure_ad_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl=(
        f"https://login.microsoftonline.com/{settings.azure_ad_tenant_id}/oauth2/v2.0/authorize"
    ),
    tokenUrl=(
        f"https://login.microsoftonline.com/{settings.azure_ad_tenant_id}/oauth2/v2.0/token"
    ),
)

_JWKS_URI = (
    f"https://login.microsoftonline.com/{settings.azure_ad_tenant_id}/discovery/v2.0/keys"
)


async def get_current_user(token: str = Depends(azure_ad_scheme)) -> dict:
    """Validate the Azure AD JWT and return the decoded claims."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        jwks_client = jwt.PyJWKClient(_JWKS_URI)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.azure_ad_client_id,
        )
        return payload
    except jwt.PyJWTError:
        raise credentials_exception
