"""
auth.py — Authentication dependency for Bank Operational Audit Tool.

Fails closed:
- Rejects unauthenticated requests when API_AUTH_TOKEN is empty or missing.
- Rejects default 'vault-audit-secret-token' in non-development environments.
- Protects all sensitive operational, rule management, and policy endpoints.
"""
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import settings

security = HTTPBearer(auto_error=False)


def require_auth(credentials: HTTPAuthorizationCredentials = Security(security)) -> HTTPAuthorizationCredentials:
    """
    Enforces mandatory Bearer token authentication across all audit & policy routes.
    """
    expected_token = getattr(settings, "api_auth_token", "")
    if not expected_token:
        raise HTTPException(
            status_code=500,
            detail="Security misconfiguration: API_AUTH_TOKEN must be configured.",
        )

    if settings.environment.lower() != "development" and expected_token == "vault-audit-secret-token":
        raise HTTPException(
            status_code=500,
            detail="Production security misconfiguration: Default API_AUTH_TOKEN cannot be used outside development.",
        )

    if not credentials or not credentials.credentials or credentials.credentials != expected_token:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Access requires a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return credentials
