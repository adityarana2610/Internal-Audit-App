"""
auth.py — Authentication dependency for Bank Operational Audit Tool.

Fails closed:
- Rejects unauthenticated requests when API_AUTH_TOKEN is empty or missing.
- Protects all sensitive operational, rule management, and policy endpoints via Bearer token.
"""
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import settings

security = HTTPBearer(auto_error=False)


def require_auth(credentials: HTTPAuthorizationCredentials = Security(security)) -> HTTPAuthorizationCredentials:
    """
    Enforces mandatory Bearer token authentication across all audit & policy routes.
    Fails closed: requests are rejected if the server has no token configured or if
    the client does not supply a valid matching Bearer token.
    """
    expected_token = getattr(settings, "api_auth_token", "")
    if not expected_token:
        raise HTTPException(
            status_code=500,
            detail="Security misconfiguration: API_AUTH_TOKEN must be configured on the server. Please set API_AUTH_TOKEN in your environment or .env file.",
        )

    if not credentials or not credentials.credentials or credentials.credentials != expected_token:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Access requires a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return credentials
