"""API key authentication via X-API-Key header with constant-time comparison."""

import hmac

from fastapi import Depends, Request, Security
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_admin_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


class AuthenticationError(Exception):
    """Raised when API key authentication fails."""

    def __init__(self, message: str = "Missing or invalid API key"):
        self.message = message
        super().__init__(message)


async def _authentication_error_handler(request: Request, exc: AuthenticationError):
    """Exception handler that returns structured error JSON at top level."""
    return JSONResponse(
        status_code=401,
        content={
            "error": {
                "code": "UNAUTHORIZED",
                "message": exc.message,
                "details": {},
            }
        },
    )


def install_auth_error_handler(app) -> None:
    """Register the AuthenticationError exception handler on a FastAPI app."""
    app.add_exception_handler(AuthenticationError, _authentication_error_handler)


def create_api_key_dependency(expected_key: str):
    """Create a FastAPI dependency that validates the X-API-Key header.

    Uses hmac.compare_digest for constant-time comparison to prevent
    timing attacks.
    """

    async def verify_api_key(api_key: str | None = Security(_header)):
        if api_key is None or not hmac.compare_digest(api_key, expected_key):
            raise AuthenticationError()
        return api_key

    return Depends(verify_api_key)


def create_admin_key_dependency(expected_key: str | None):
    """Create a FastAPI dependency that validates the X-Admin-Key header.

    If expected_key is None or empty, all requests are rejected (admin
    endpoints disabled).
    """

    async def verify_admin_key(
        admin_key: str | None = Security(_admin_header),
    ):
        if not expected_key:
            raise AuthenticationError("Admin endpoints are not configured")
        if admin_key is None or not hmac.compare_digest(admin_key, expected_key):
            raise AuthenticationError("Missing or invalid admin key")
        return admin_key

    return Depends(verify_admin_key)
