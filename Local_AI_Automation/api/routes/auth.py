"""
Authentication Routes
Handles token generation and API key management
"""
import os
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List

from ..auth import (
    create_access_token,
    create_api_key,
    require_auth,
    AUTH_ENABLED
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Simple user store - in production, use a proper database
# For local use, we use environment variables or a simple config
ADMIN_USERNAME = os.getenv("API_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("API_ADMIN_PASSWORD", "localai2024")


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ApiKeyRequest(BaseModel):
    name: str
    scopes: Optional[List[str]] = None


@router.get("/status")
def auth_status():
    """Check if authentication is enabled"""
    return {
        "auth_enabled": AUTH_ENABLED,
        "message": "Set API_AUTH_ENABLED=true to require authentication"
    }


@router.post("/token", response_model=TokenResponse)
def login(request: LoginRequest):
    """
    Get an access token using username/password

    Default credentials (change via environment variables):
    - Username: admin (API_ADMIN_USER)
    - Password: localai2024 (API_ADMIN_PASSWORD)
    """
    if request.username != ADMIN_USERNAME or request.password != ADMIN_PASSWORD:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    token = create_access_token(
        data={
            "sub": request.username,
            "type": "user"
        }
    )

    return TokenResponse(
        access_token=token,
        expires_in=60 * 24 * 60  # 24 hours in seconds
    )


@router.post("/api-key")
def generate_api_key(
    request: ApiKeyRequest,
    user: dict = Depends(require_auth)
):
    """
    Generate a new API key (requires authentication)

    API keys are long-lived tokens for programmatic access.
    """
    return create_api_key(
        name=request.name,
        scopes=request.scopes
    )


@router.get("/me")
def get_current_user_info(user: dict = Depends(require_auth)):
    """Get information about the current authenticated user"""
    return {
        "user": user.get("sub"),
        "type": user.get("type"),
        "scopes": user.get("scopes", [])
    }
