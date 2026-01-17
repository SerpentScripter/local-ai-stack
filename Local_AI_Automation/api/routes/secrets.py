"""
Secrets Management Routes
API endpoints for secure secrets storage
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List

from ..auth import require_auth, AUTH_ENABLED
from ..secrets_manager import get_secrets_manager, SecretKeys

router = APIRouter(prefix="/secrets", tags=["secrets"])


class SecretCreate(BaseModel):
    """Request to store a secret"""
    key: str = Field(..., min_length=1, max_length=128, description="Secret key name")
    value: str = Field(..., min_length=1, description="Secret value")


class SecretResponse(BaseModel):
    """Response for secret operations"""
    key: str
    status: str
    message: Optional[str] = None


class SecretKeyInfo(BaseModel):
    """Information about a stored secret key"""
    key: str
    description: Optional[str] = None


# Standard secret key descriptions
SECRET_KEY_DESCRIPTIONS = {
    SecretKeys.API_SECRET_KEY: "Master API secret for signing",
    SecretKeys.JWT_SECRET: "JWT token signing key",
    SecretKeys.OLLAMA_API_KEY: "Ollama API authentication",
    SecretKeys.OPENAI_API_KEY: "OpenAI API key",
    SecretKeys.ANTHROPIC_API_KEY: "Anthropic/Claude API key",
    SecretKeys.SLACK_WEBHOOK_URL: "Slack incoming webhook URL",
    SecretKeys.SLACK_BOT_TOKEN: "Slack bot OAuth token",
    SecretKeys.GITHUB_TOKEN: "GitHub personal access token",
    SecretKeys.N8N_API_KEY: "n8n automation API key",
    SecretKeys.ENCRYPTION_KEY: "General encryption key",
}


def check_auth_required():
    """Secrets management always requires auth when auth is enabled"""
    if AUTH_ENABLED:
        return Depends(require_auth)
    return None


@router.get("/", response_model=List[SecretKeyInfo])
def list_secrets(user: dict = Depends(require_auth) if AUTH_ENABLED else None):
    """
    List all stored secret keys (not values)

    Returns keys stored in the secrets vault.
    """
    manager = get_secrets_manager()
    keys = manager.list_keys()

    return [
        SecretKeyInfo(
            key=k,
            description=SECRET_KEY_DESCRIPTIONS.get(k)
        )
        for k in keys
    ]


@router.get("/available")
def list_available_secrets():
    """
    List standard secret key names that can be configured

    This endpoint is public to help users know what to configure.
    """
    return {
        "standard_keys": [
            {"key": k, "description": v}
            for k, v in SECRET_KEY_DESCRIPTIONS.items()
        ],
        "note": "You can also store custom secrets with any key name"
    }


@router.post("/", response_model=SecretResponse)
def set_secret_value(
    secret: SecretCreate,
    user: dict = Depends(require_auth) if AUTH_ENABLED else None
):
    """
    Store a secret value

    The value is encrypted and stored securely using:
    1. Windows Credential Manager (if available)
    2. Encrypted file storage (fallback)
    """
    manager = get_secrets_manager()

    # Prevent overwriting certain system secrets via API
    protected_keys = [SecretKeys.JWT_SECRET, SecretKeys.API_SECRET_KEY]
    if secret.key in protected_keys:
        raise HTTPException(
            status_code=403,
            detail=f"Cannot modify protected secret '{secret.key}' via API"
        )

    success = manager.set(secret.key, secret.value)

    if success:
        return SecretResponse(
            key=secret.key,
            status="stored",
            message="Secret stored securely"
        )
    else:
        raise HTTPException(status_code=500, detail="Failed to store secret")


@router.delete("/{key}", response_model=SecretResponse)
def delete_secret_value(
    key: str,
    user: dict = Depends(require_auth) if AUTH_ENABLED else None
):
    """
    Delete a stored secret

    Removes the secret from all storage backends.
    """
    manager = get_secrets_manager()

    # Prevent deleting certain system secrets
    protected_keys = [SecretKeys.JWT_SECRET, SecretKeys.API_SECRET_KEY]
    if key in protected_keys:
        raise HTTPException(
            status_code=403,
            detail=f"Cannot delete protected secret '{key}'"
        )

    manager.delete(key)

    return SecretResponse(
        key=key,
        status="deleted",
        message="Secret removed from storage"
    )


@router.post("/{key}/rotate", response_model=SecretResponse)
def rotate_secret(
    key: str,
    user: dict = Depends(require_auth) if AUTH_ENABLED else None
):
    """
    Rotate a secret by generating a new random value

    Generates a cryptographically secure random value
    and stores it, replacing the old value.
    """
    manager = get_secrets_manager()

    # Prevent rotating certain system secrets via API
    protected_keys = [SecretKeys.JWT_SECRET, SecretKeys.API_SECRET_KEY]
    if key in protected_keys:
        raise HTTPException(
            status_code=403,
            detail=f"Cannot rotate protected secret '{key}' via API"
        )

    new_value = manager.rotate(key)

    if new_value:
        return SecretResponse(
            key=key,
            status="rotated",
            message="New secret value generated"
        )
    else:
        raise HTTPException(status_code=404, detail=f"Secret '{key}' not found")


@router.get("/status")
def secrets_status():
    """
    Get status of secrets storage backends

    Shows which storage backends are available.
    """
    from ..secrets_manager import KEYRING_AVAILABLE, SECRETS_FILE

    return {
        "backends": {
            "os_credential_store": {
                "available": KEYRING_AVAILABLE,
                "description": "Windows Credential Manager"
            },
            "encrypted_file": {
                "available": True,
                "path": str(SECRETS_FILE),
                "description": "AES-encrypted local file"
            },
            "environment_variables": {
                "available": True,
                "prefix": "LOCALAI_",
                "description": "Environment variables (legacy)"
            }
        },
        "encryption": {
            "algorithm": "Fernet (AES-128-CBC + HMAC-SHA256)",
            "key_derivation": "PBKDF2-HMAC-SHA256 (480000 iterations)"
        }
    }
