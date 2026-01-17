"""
Secrets Manager
Secure storage for API keys, tokens, and sensitive configuration

Uses multiple backends:
1. Windows Credential Manager (via keyring) - primary
2. Encrypted file storage - fallback
3. Environment variables - legacy support
"""
import os
import json
import base64
import hashlib
import secrets as py_secrets
from pathlib import Path
from typing import Optional, Dict, Any
from functools import lru_cache
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Try to import keyring (Windows Credential Manager)
try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

from .logging_config import api_logger


# Configuration
SERVICE_NAME = "LocalAIHub"
SECRETS_DIR = Path(__file__).parent.parent / "data" / "secrets"
SECRETS_FILE = SECRETS_DIR / "vault.enc"
KEY_FILE = SECRETS_DIR / ".keyfile"


class SecretsManager:
    """
    Secure secrets management with multiple storage backends

    Priority order:
    1. Environment variables (for container/CI deployment)
    2. OS credential store (Windows Credential Manager)
    3. Encrypted file storage (fallback)
    """

    def __init__(self):
        self._cache: Dict[str, str] = {}
        self._fernet: Optional[Fernet] = None
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        """Ensure storage directories exist"""
        SECRETS_DIR.mkdir(parents=True, exist_ok=True)

        # Set restrictive permissions on secrets directory
        if os.name == 'nt':  # Windows
            import subprocess
            # Remove inheritance and set owner-only access
            try:
                subprocess.run(
                    ['icacls', str(SECRETS_DIR), '/inheritance:r', '/grant:r', f'{os.environ.get("USERNAME", "SYSTEM")}:F'],
                    capture_output=True, check=False
                )
            except Exception:
                pass  # Best effort

    def _get_encryption_key(self) -> bytes:
        """Get or create the encryption key for file-based storage"""
        if KEY_FILE.exists():
            with open(KEY_FILE, 'rb') as f:
                salt = f.read()
        else:
            salt = py_secrets.token_bytes(16)
            with open(KEY_FILE, 'wb') as f:
                f.write(salt)
            # Restrict key file permissions
            if os.name == 'nt':
                import subprocess
                try:
                    subprocess.run(
                        ['icacls', str(KEY_FILE), '/inheritance:r', '/grant:r', f'{os.environ.get("USERNAME", "SYSTEM")}:F'],
                        capture_output=True, check=False
                    )
                except Exception:
                    pass

        # Derive key from machine-specific data + salt
        machine_id = self._get_machine_id()
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(machine_id.encode()))
        return key

    def _get_machine_id(self) -> str:
        """Get a machine-specific identifier for key derivation"""
        # Combine multiple sources for machine identity
        identifiers = []

        # Windows machine GUID
        if os.name == 'nt':
            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Cryptography"
                )
                machine_guid, _ = winreg.QueryValueEx(key, "MachineGuid")
                identifiers.append(machine_guid)
                winreg.CloseKey(key)
            except Exception:
                pass

        # Fallback to username + hostname
        identifiers.append(os.environ.get("USERNAME", "user"))
        identifiers.append(os.environ.get("COMPUTERNAME", "localhost"))

        return ":".join(identifiers)

    @property
    def fernet(self) -> Fernet:
        """Lazy-initialize Fernet cipher"""
        if self._fernet is None:
            key = self._get_encryption_key()
            self._fernet = Fernet(key)
        return self._fernet

    def _load_file_vault(self) -> Dict[str, str]:
        """Load secrets from encrypted file"""
        if not SECRETS_FILE.exists():
            return {}

        try:
            with open(SECRETS_FILE, 'rb') as f:
                encrypted = f.read()
            decrypted = self.fernet.decrypt(encrypted)
            return json.loads(decrypted.decode())
        except Exception as e:
            api_logger.warning(f"Failed to load secrets vault: {e}")
            return {}

    def _save_file_vault(self, vault: Dict[str, str]) -> None:
        """Save secrets to encrypted file"""
        try:
            data = json.dumps(vault).encode()
            encrypted = self.fernet.encrypt(data)
            with open(SECRETS_FILE, 'wb') as f:
                f.write(encrypted)
        except Exception as e:
            api_logger.error(f"Failed to save secrets vault: {e}")
            raise

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get a secret value

        Priority:
        1. Cache
        2. Environment variable
        3. OS credential store
        4. Encrypted file

        Args:
            key: Secret key name
            default: Default value if not found

        Returns:
            Secret value or default
        """
        # Check cache first
        if key in self._cache:
            return self._cache[key]

        # Check environment variable
        env_key = f"LOCALAI_{key.upper()}"
        env_value = os.environ.get(env_key)
        if env_value:
            self._cache[key] = env_value
            return env_value

        # Check OS credential store
        if KEYRING_AVAILABLE:
            try:
                value = keyring.get_password(SERVICE_NAME, key)
                if value:
                    self._cache[key] = value
                    return value
            except Exception as e:
                api_logger.debug(f"Keyring lookup failed for {key}: {e}")

        # Check encrypted file
        vault = self._load_file_vault()
        if key in vault:
            self._cache[key] = vault[key]
            return vault[key]

        return default

    def set(self, key: str, value: str, use_keyring: bool = True) -> bool:
        """
        Store a secret value

        Args:
            key: Secret key name
            value: Secret value
            use_keyring: Try OS credential store first (default True)

        Returns:
            True if stored successfully
        """
        # Update cache
        self._cache[key] = value

        # Try OS credential store first
        if use_keyring and KEYRING_AVAILABLE:
            try:
                keyring.set_password(SERVICE_NAME, key, value)
                api_logger.info(f"Secret '{key}' stored in OS credential manager")
                return True
            except Exception as e:
                api_logger.debug(f"Keyring storage failed for {key}: {e}")

        # Fall back to encrypted file
        vault = self._load_file_vault()
        vault[key] = value
        self._save_file_vault(vault)
        api_logger.info(f"Secret '{key}' stored in encrypted vault")
        return True

    def delete(self, key: str) -> bool:
        """
        Delete a secret

        Args:
            key: Secret key name

        Returns:
            True if deleted (or didn't exist)
        """
        # Remove from cache
        self._cache.pop(key, None)

        # Remove from OS credential store
        if KEYRING_AVAILABLE:
            try:
                keyring.delete_password(SERVICE_NAME, key)
            except Exception:
                pass

        # Remove from encrypted file
        vault = self._load_file_vault()
        if key in vault:
            del vault[key]
            self._save_file_vault(vault)

        api_logger.info(f"Secret '{key}' deleted")
        return True

    def list_keys(self) -> list:
        """
        List all stored secret keys (not values)

        Returns:
            List of key names
        """
        keys = set()

        # From encrypted file
        vault = self._load_file_vault()
        keys.update(vault.keys())

        # Note: Keyring doesn't support listing, so we only list file-based secrets

        return sorted(keys)

    def rotate(self, key: str) -> Optional[str]:
        """
        Rotate a secret by generating a new random value

        Args:
            key: Secret key name

        Returns:
            New secret value if rotated, None if key didn't exist
        """
        if self.get(key) is None:
            return None

        new_value = py_secrets.token_urlsafe(32)
        self.set(key, new_value)
        api_logger.info(f"Secret '{key}' rotated")
        return new_value

    def generate_secret(self, length: int = 32) -> str:
        """Generate a cryptographically secure random secret"""
        return py_secrets.token_urlsafe(length)


# Global singleton instance
_manager: Optional[SecretsManager] = None


def get_secrets_manager() -> SecretsManager:
    """Get the global SecretsManager instance"""
    global _manager
    if _manager is None:
        _manager = SecretsManager()
    return _manager


# Convenience functions
def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get a secret value"""
    return get_secrets_manager().get(key, default)


def set_secret(key: str, value: str) -> bool:
    """Store a secret value"""
    return get_secrets_manager().set(key, value)


def delete_secret(key: str) -> bool:
    """Delete a secret"""
    return get_secrets_manager().delete(key)


# Pre-defined secret keys for the application
class SecretKeys:
    """Standard secret key names used by the application"""
    API_SECRET_KEY = "api_secret_key"
    JWT_SECRET = "jwt_secret"
    OLLAMA_API_KEY = "ollama_api_key"
    OPENAI_API_KEY = "openai_api_key"
    ANTHROPIC_API_KEY = "anthropic_api_key"
    SLACK_WEBHOOK_URL = "slack_webhook_url"
    SLACK_BOT_TOKEN = "slack_bot_token"
    GITHUB_TOKEN = "github_token"
    N8N_API_KEY = "n8n_api_key"
    ENCRYPTION_KEY = "encryption_key"
