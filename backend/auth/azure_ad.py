"""Azure AD OAuth2 — token exchange and user info extraction."""

import httpx

from ..core.config import get_settings

settings = get_settings()


def is_configured() -> bool:
    """Check if Azure AD is configured."""
    return bool(settings.azure_ad_tenant_id and settings.azure_ad_client_id)


async def exchange_code_for_tokens(code: str, redirect_uri: str) -> dict:
    """Exchange authorization code for Azure AD tokens."""
    token_url = (
        f"https://login.microsoftonline.com/{settings.azure_ad_tenant_id}/oauth2/v2.0/token"
    )
    data = {
        "client_id": settings.azure_ad_client_id,
        "client_secret": settings.azure_ad_client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "scope": "openid profile email",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, data=data)
        resp.raise_for_status()
        return resp.json()


def extract_user_info(id_token: str) -> dict:
    """Decode the ID token (without full signature verification for code flow).

    In the authorization code flow, the token comes directly from Microsoft's
    token endpoint over HTTPS, so signature verification is optional per spec.
    """
    import jwt as pyjwt

    claims = pyjwt.decode(id_token, options={"verify_signature": False})
    return {
        "oid": claims.get("oid"),
        "email": claims.get("preferred_username") or claims.get("email", ""),
        "name": claims.get("name", ""),
    }
