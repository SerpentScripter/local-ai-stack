"""
Automated Update Manager with Rollback
Manages updates for all components of the Local AI Hub

Features:
- Version tracking for all components
- Update availability checking
- Automated updates with health validation
- Rollback capability on failure
- Update history and audit trail
"""
import json
import os
import subprocess
import shutil
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .database import get_db
from .logging_config import api_logger


class ComponentType(Enum):
    """Types of updatable components"""
    OLLAMA_MODEL = "ollama_model"
    DOCKER_IMAGE = "docker_image"
    PYTHON_PACKAGE = "python_package"
    SYSTEM_CONFIG = "system_config"


class UpdateStatus(Enum):
    """Status of an update operation"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class ComponentVersion:
    """Version info for a component"""
    component_id: str
    component_type: ComponentType
    name: str
    current_version: str
    latest_version: Optional[str]
    update_available: bool
    last_checked: datetime
    last_updated: Optional[datetime]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UpdateOperation:
    """Record of an update operation"""
    id: str
    component_id: str
    from_version: str
    to_version: str
    status: UpdateStatus
    started_at: datetime
    completed_at: Optional[datetime]
    backup_path: Optional[str]
    error_message: Optional[str]
    rollback_available: bool


class UpdateManager:
    """
    Manages automated updates with rollback capability

    Supports:
    - Ollama models
    - Docker images (via compose)
    - Python packages
    - System configurations
    """

    def __init__(self):
        self._backup_dir = Path(os.environ.get(
            "UPDATE_BACKUP_DIR",
            "D:/SHARED/AI_Models/backups"
        ))
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self):
        """Initialize update tracking tables"""
        try:
            with get_db() as conn:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS component_versions (
                        component_id TEXT PRIMARY KEY,
                        component_type TEXT NOT NULL,
                        name TEXT NOT NULL,
                        current_version TEXT,
                        latest_version TEXT,
                        update_available INTEGER DEFAULT 0,
                        last_checked TEXT,
                        last_updated TEXT,
                        metadata TEXT
                    );

                    CREATE TABLE IF NOT EXISTS update_history (
                        id TEXT PRIMARY KEY,
                        component_id TEXT NOT NULL,
                        from_version TEXT,
                        to_version TEXT,
                        status TEXT NOT NULL,
                        started_at TEXT NOT NULL,
                        completed_at TEXT,
                        backup_path TEXT,
                        error_message TEXT,
                        rollback_available INTEGER DEFAULT 0
                    );

                    CREATE INDEX IF NOT EXISTS idx_update_component
                    ON update_history(component_id);

                    CREATE INDEX IF NOT EXISTS idx_update_status
                    ON update_history(status);
                """)
        except Exception as e:
            api_logger.error(f"Failed to init update tables: {e}")

    # ==================== Version Checking ====================

    async def check_all_updates(self) -> List[ComponentVersion]:
        """Check for updates on all tracked components"""
        components = []

        # Check Ollama models
        components.extend(await self._check_ollama_models())

        # Check Docker images
        components.extend(await self._check_docker_images())

        return components

    async def _check_ollama_models(self) -> List[ComponentVersion]:
        """Check for Ollama model updates"""
        import httpx

        models = []

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get("http://localhost:11434/api/tags")

                if response.status_code == 200:
                    data = response.json()
                    installed = data.get("models", [])

                    for model in installed:
                        name = model.get("name", "unknown")
                        modified = model.get("modified_at", "")
                        size = model.get("size", 0)

                        # Parse version from modified date or digest
                        digest = model.get("digest", "")[:12]
                        current_version = digest if digest else modified[:10]

                        # Check for newer version (would need Ollama registry API)
                        # For now, flag models older than 30 days
                        update_available = False
                        try:
                            mod_date = datetime.fromisoformat(modified.replace("Z", "+00:00"))
                            age_days = (datetime.utcnow() - mod_date.replace(tzinfo=None)).days
                            update_available = age_days > 30
                        except Exception:
                            pass

                        component = ComponentVersion(
                            component_id=f"ollama:{name}",
                            component_type=ComponentType.OLLAMA_MODEL,
                            name=name,
                            current_version=current_version,
                            latest_version=None,  # Would need registry check
                            update_available=update_available,
                            last_checked=datetime.utcnow(),
                            last_updated=None,
                            metadata={"size": size}
                        )
                        models.append(component)
                        self._save_component(component)

        except Exception as e:
            api_logger.error(f"Failed to check Ollama models: {e}")

        return models

    async def _check_docker_images(self) -> List[ComponentVersion]:
        """Check for Docker image updates"""
        images = []

        # Define tracked images
        tracked_images = [
            ("open-webui", "ghcr.io/open-webui/open-webui:latest"),
            ("langflow", "langflowai/langflow:latest"),
            ("n8n", "n8nio/n8n:latest"),
        ]

        for name, image in tracked_images:
            try:
                # Get current image digest
                result = subprocess.run(
                    ["docker", "image", "inspect", image, "--format", "{{.Id}}"],
                    capture_output=True, text=True, timeout=30
                )

                current_digest = result.stdout.strip()[:12] if result.returncode == 0 else "unknown"

                # Check for updates (pull with --dry-run isn't supported, so we check age)
                result = subprocess.run(
                    ["docker", "image", "inspect", image, "--format", "{{.Created}}"],
                    capture_output=True, text=True, timeout=30
                )

                update_available = False
                if result.returncode == 0:
                    try:
                        created = datetime.fromisoformat(result.stdout.strip().replace("Z", "+00:00"))
                        age_days = (datetime.utcnow() - created.replace(tzinfo=None)).days
                        update_available = age_days > 14  # Flag images > 14 days old
                    except Exception:
                        pass

                component = ComponentVersion(
                    component_id=f"docker:{name}",
                    component_type=ComponentType.DOCKER_IMAGE,
                    name=name,
                    current_version=current_digest,
                    latest_version=None,
                    update_available=update_available,
                    last_checked=datetime.utcnow(),
                    last_updated=None,
                    metadata={"image": image}
                )
                images.append(component)
                self._save_component(component)

            except Exception as e:
                api_logger.error(f"Failed to check Docker image {name}: {e}")

        return images

    def _save_component(self, component: ComponentVersion):
        """Save component version info"""
        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO component_versions
                    (component_id, component_type, name, current_version, latest_version,
                     update_available, last_checked, last_updated, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    component.component_id,
                    component.component_type.value,
                    component.name,
                    component.current_version,
                    component.latest_version,
                    1 if component.update_available else 0,
                    component.last_checked.isoformat(),
                    component.last_updated.isoformat() if component.last_updated else None,
                    json.dumps(component.metadata)
                ))
        except Exception as e:
            api_logger.error(f"Failed to save component: {e}")

    # ==================== Update Operations ====================

    async def update_component(
        self,
        component_id: str,
        create_backup: bool = True
    ) -> UpdateOperation:
        """
        Update a specific component

        Args:
            component_id: Component to update
            create_backup: Whether to create a backup first

        Returns:
            UpdateOperation with result
        """
        import uuid

        # Get component info
        component = self.get_component(component_id)
        if not component:
            raise ValueError(f"Component not found: {component_id}")

        operation_id = f"upd_{uuid.uuid4().hex[:12]}"
        operation = UpdateOperation(
            id=operation_id,
            component_id=component_id,
            from_version=component.current_version,
            to_version="pending",
            status=UpdateStatus.IN_PROGRESS,
            started_at=datetime.utcnow(),
            completed_at=None,
            backup_path=None,
            error_message=None,
            rollback_available=False
        )

        self._save_operation(operation)

        try:
            # Create backup if requested
            if create_backup:
                backup_path = await self._create_backup(component)
                operation.backup_path = str(backup_path)
                operation.rollback_available = True

            # Perform the update based on component type
            if component.component_type == ComponentType.OLLAMA_MODEL:
                new_version = await self._update_ollama_model(component)
            elif component.component_type == ComponentType.DOCKER_IMAGE:
                new_version = await self._update_docker_image(component)
            else:
                raise ValueError(f"Unsupported component type: {component.component_type}")

            # Verify update succeeded with health check
            healthy = await self._health_check(component)

            if healthy:
                operation.to_version = new_version
                operation.status = UpdateStatus.COMPLETED
                operation.completed_at = datetime.utcnow()

                # Update component version
                component.current_version = new_version
                component.last_updated = datetime.utcnow()
                component.update_available = False
                self._save_component(component)

            else:
                # Rollback if health check fails
                if operation.backup_path:
                    await self._rollback(operation)
                    operation.status = UpdateStatus.ROLLED_BACK
                    operation.error_message = "Health check failed after update"
                else:
                    operation.status = UpdateStatus.FAILED
                    operation.error_message = "Health check failed, no backup available"

        except Exception as e:
            operation.status = UpdateStatus.FAILED
            operation.error_message = str(e)
            operation.completed_at = datetime.utcnow()

            # Attempt rollback
            if operation.backup_path and operation.rollback_available:
                try:
                    await self._rollback(operation)
                    operation.status = UpdateStatus.ROLLED_BACK
                except Exception as re:
                    operation.error_message += f" | Rollback failed: {str(re)}"

        self._save_operation(operation)
        return operation

    async def _create_backup(self, component: ComponentVersion) -> Path:
        """Create a backup before update"""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{component.component_id.replace(':', '_')}_{timestamp}"
        backup_path = self._backup_dir / backup_name

        if component.component_type == ComponentType.OLLAMA_MODEL:
            # For Ollama models, store the current digest
            backup_path.mkdir(parents=True, exist_ok=True)
            with open(backup_path / "manifest.json", "w") as f:
                json.dump({
                    "component_id": component.component_id,
                    "version": component.current_version,
                    "name": component.name,
                    "backed_up_at": datetime.utcnow().isoformat()
                }, f)

        elif component.component_type == ComponentType.DOCKER_IMAGE:
            # Save Docker image
            image = component.metadata.get("image", "")
            if image:
                backup_file = backup_path.with_suffix(".tar")
                result = subprocess.run(
                    ["docker", "save", "-o", str(backup_file), image],
                    capture_output=True, timeout=300
                )
                if result.returncode != 0:
                    raise Exception(f"Failed to backup Docker image: {result.stderr.decode()}")
                return backup_file

        return backup_path

    async def _update_ollama_model(self, component: ComponentVersion) -> str:
        """Update an Ollama model"""
        model_name = component.name

        # Pull latest version
        result = subprocess.run(
            ["ollama", "pull", model_name],
            capture_output=True, text=True, timeout=600
        )

        if result.returncode != 0:
            raise Exception(f"Ollama pull failed: {result.stderr}")

        # Get new digest
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get("http://localhost:11434/api/tags")
            if response.status_code == 200:
                models = response.json().get("models", [])
                for model in models:
                    if model.get("name") == model_name:
                        return model.get("digest", "")[:12]

        return "updated"

    async def _update_docker_image(self, component: ComponentVersion) -> str:
        """Update a Docker image"""
        image = component.metadata.get("image", "")
        if not image:
            raise ValueError("No image specified for Docker component")

        # Pull latest
        result = subprocess.run(
            ["docker", "pull", image],
            capture_output=True, text=True, timeout=300
        )

        if result.returncode != 0:
            raise Exception(f"Docker pull failed: {result.stderr}")

        # Get new digest
        result = subprocess.run(
            ["docker", "image", "inspect", image, "--format", "{{.Id}}"],
            capture_output=True, text=True, timeout=30
        )

        new_digest = result.stdout.strip()[:12] if result.returncode == 0 else "updated"

        # Restart container (assumes docker-compose)
        container_name = component.name
        subprocess.run(
            ["docker", "compose", "restart", container_name],
            capture_output=True, timeout=60
        )

        return new_digest

    async def _health_check(self, component: ComponentVersion) -> bool:
        """Verify component is healthy after update"""
        import httpx

        await asyncio.sleep(5)  # Give service time to start

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if component.component_type == ComponentType.OLLAMA_MODEL:
                    # Test model with simple prompt
                    response = await client.post(
                        "http://localhost:11434/api/generate",
                        json={
                            "model": component.name,
                            "prompt": "Hello",
                            "stream": False
                        },
                        timeout=60.0
                    )
                    return response.status_code == 200

                elif component.component_type == ComponentType.DOCKER_IMAGE:
                    # Check service health endpoint
                    health_endpoints = {
                        "open-webui": "http://localhost:3000",
                        "langflow": "http://localhost:7860",
                        "n8n": "http://localhost:5678/healthz",
                    }
                    endpoint = health_endpoints.get(component.name)
                    if endpoint:
                        response = await client.get(endpoint)
                        return response.status_code < 500

        except Exception as e:
            api_logger.error(f"Health check failed: {e}")
            return False

        return True

    async def _rollback(self, operation: UpdateOperation):
        """Rollback a failed update"""
        if not operation.backup_path:
            raise ValueError("No backup path available for rollback")

        backup_path = Path(operation.backup_path)
        component = self.get_component(operation.component_id)

        if not component:
            raise ValueError("Component not found for rollback")

        if component.component_type == ComponentType.DOCKER_IMAGE:
            # Load backed up image
            if backup_path.suffix == ".tar":
                result = subprocess.run(
                    ["docker", "load", "-i", str(backup_path)],
                    capture_output=True, timeout=300
                )
                if result.returncode != 0:
                    raise Exception(f"Failed to restore Docker image: {result.stderr.decode()}")

                # Restart container
                subprocess.run(
                    ["docker", "compose", "restart", component.name],
                    capture_output=True, timeout=60
                )

        elif component.component_type == ComponentType.OLLAMA_MODEL:
            # For Ollama, we'd need to keep the old model file
            # This is a simplified version - full implementation would copy model blobs
            api_logger.warning(f"Ollama model rollback not fully implemented for {component.name}")

    def _save_operation(self, operation: UpdateOperation):
        """Save update operation to database"""
        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO update_history
                    (id, component_id, from_version, to_version, status, started_at,
                     completed_at, backup_path, error_message, rollback_available)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    operation.id,
                    operation.component_id,
                    operation.from_version,
                    operation.to_version,
                    operation.status.value,
                    operation.started_at.isoformat(),
                    operation.completed_at.isoformat() if operation.completed_at else None,
                    operation.backup_path,
                    operation.error_message,
                    1 if operation.rollback_available else 0
                ))
        except Exception as e:
            api_logger.error(f"Failed to save operation: {e}")

    # ==================== Query Methods ====================

    def get_component(self, component_id: str) -> Optional[ComponentVersion]:
        """Get a specific component"""
        try:
            with get_db() as conn:
                row = conn.execute(
                    "SELECT * FROM component_versions WHERE component_id = ?",
                    (component_id,)
                ).fetchone()

                if row:
                    return ComponentVersion(
                        component_id=row["component_id"],
                        component_type=ComponentType(row["component_type"]),
                        name=row["name"],
                        current_version=row["current_version"],
                        latest_version=row["latest_version"],
                        update_available=bool(row["update_available"]),
                        last_checked=datetime.fromisoformat(row["last_checked"]),
                        last_updated=datetime.fromisoformat(row["last_updated"]) if row["last_updated"] else None,
                        metadata=json.loads(row["metadata"]) if row["metadata"] else {}
                    )
        except Exception:
            pass
        return None

    def get_all_components(self) -> List[Dict[str, Any]]:
        """Get all tracked components"""
        try:
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT * FROM component_versions ORDER BY name"
                ).fetchall()

                return [
                    {
                        "component_id": row["component_id"],
                        "type": row["component_type"],
                        "name": row["name"],
                        "current_version": row["current_version"],
                        "latest_version": row["latest_version"],
                        "update_available": bool(row["update_available"]),
                        "last_checked": row["last_checked"],
                        "last_updated": row["last_updated"]
                    }
                    for row in rows
                ]
        except Exception:
            return []

    def get_update_history(
        self,
        component_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get update history"""
        try:
            with get_db() as conn:
                if component_id:
                    rows = conn.execute("""
                        SELECT * FROM update_history
                        WHERE component_id = ?
                        ORDER BY started_at DESC
                        LIMIT ?
                    """, (component_id, limit)).fetchall()
                else:
                    rows = conn.execute("""
                        SELECT * FROM update_history
                        ORDER BY started_at DESC
                        LIMIT ?
                    """, (limit,)).fetchall()

                return [dict(row) for row in rows]

        except Exception:
            return []

    def get_pending_updates(self) -> List[Dict[str, Any]]:
        """Get components with available updates"""
        try:
            with get_db() as conn:
                rows = conn.execute("""
                    SELECT * FROM component_versions
                    WHERE update_available = 1
                    ORDER BY name
                """).fetchall()

                return [
                    {
                        "component_id": row["component_id"],
                        "type": row["component_type"],
                        "name": row["name"],
                        "current_version": row["current_version"],
                        "latest_version": row["latest_version"]
                    }
                    for row in rows
                ]
        except Exception:
            return []

    def cleanup_old_backups(self, days: int = 30) -> int:
        """Clean up backups older than specified days"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        removed = 0

        try:
            for item in self._backup_dir.iterdir():
                if item.stat().st_mtime < cutoff.timestamp():
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                    removed += 1
        except Exception as e:
            api_logger.error(f"Backup cleanup failed: {e}")

        return removed


# Global instance
_update_manager: Optional[UpdateManager] = None


def get_update_manager() -> UpdateManager:
    """Get the global UpdateManager instance"""
    global _update_manager
    if _update_manager is None:
        _update_manager = UpdateManager()
    return _update_manager
