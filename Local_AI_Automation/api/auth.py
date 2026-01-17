"""
Authentication Module
JWT-based authentication for the Local AI Hub API
"""
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional
from functools import lru_cache

import jwt
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .secrets_manager import get_secret, set_secret, SecretKeys

# Security configuration
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("API_TOKEN_EXPIRE_MINUTES", 60 * 24))  # 24 hours default


@lru_cache()
def get_secret_key() -> str:
    """
    Get the JWT secret key from secure storage

    Checks in order:
    1. Secrets manager (OS credential store / encrypted file)
    2. Environment variable (legacy)
    3. Generates and stores a new secret
    """
    # Try secrets manager first
    secret = get_secret(SecretKeys.JWT_SECRET)
    if secret:
        return secret

    # Check legacy environment variable
    env_secret = os.getenv("API_SECRET_KEY")
    if env_secret:
        # Migrate to secrets manager
        set_secret(SecretKeys.JWT_SECRET, env_secret)
        return env_secret

    # Generate new secret and store it
    new_secret = secrets.token_urlsafe(32)
    set_secret(SecretKeys.JWT_SECRET, new_secret)
    return new_secret



# Security scheme
security = HTTPBearer(auto_error=False)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token

    Args:
        data: Payload data to encode in the token
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    })
    return jwt.encode(to_encode, get_secret_key(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT token

    Args:
        token: JWT token string

    Returns:
        Decoded payload dictionary

    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        payload = jwt.decode(token, get_secret_key(), algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> Optional[dict]:
    """
    Dependency to get the current authenticated user

    Returns None if no token is provided (for optional auth)
    Raises HTTPException if token is invalid
    """
    if credentials is None:
        return None

    token = credentials.credentials
    return decode_token(token)


def require_auth(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> dict:
    """
    Dependency that requires valid authentication

    Raises HTTPException if not authenticated
    """
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return decode_token(credentials.credentials)


def create_api_key(name: str, scopes: list = None) -> dict:
    """
    Create a new API key for programmatic access

    Args:
        name: Name/description for the API key
        scopes: Optional list of permission scopes

    Returns:
        Dictionary with key details and token
    """
    key_id = secrets.token_urlsafe(8)
    token = create_access_token(
        data={
            "sub": f"api_key:{key_id}",
            "name": name,
            "scopes": scopes or ["read", "write"],
            "type": "api_key"
        },
        expires_delta=timedelta(days=365)  # API keys last 1 year
    )
    return {
        "key_id": key_id,
        "name": name,
        "token": token,
        "expires_in_days": 365
    }


# Middleware to check if auth is enabled
AUTH_ENABLED = os.getenv("API_AUTH_ENABLED", "false").lower() == "true"


def optional_auth(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> Optional[dict]:
    """
    Optional authentication - returns user if token provided, None otherwise
    Used for endpoints that work both authenticated and unauthenticated
    """
    if not AUTH_ENABLED:
        return {"sub": "anonymous", "auth_disabled": True}

    if credentials is None:
        return None

    try:
        return decode_token(credentials.credentials)
    except HTTPException:
        return None
