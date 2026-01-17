"""
Update Manager Routes
API endpoints for automated updates with rollback
"""
from fastapi import APIRouter, Query, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..update_manager import get_update_manager

router = APIRouter(prefix="/updates", tags=["updates"])


class UpdateRequest(BaseModel):
    """Request to update a component"""
    component_id: str
    create_backup: bool = True


@router.get("/check")
async def check_for_updates():
    """
    Check all components for available updates

    Scans:
    - Ollama models
    - Docker images
    """
    manager = get_update_manager()
    components = await manager.check_all_updates()

    updates_available = [c for c in components if c.update_available]

    return {
        "checked": len(components),
        "updates_available": len(updates_available),
        "components": [
            {
                "component_id": c.component_id,
                "type": c.component_type.value,
                "name": c.name,
                "current_version": c.current_version,
                "update_available": c.update_available
            }
            for c in components
        ]
    }


@router.get("/pending")
def get_pending_updates():
    """Get list of components with pending updates"""
    manager = get_update_manager()
    return manager.get_pending_updates()


@router.get("/components")
def list_components():
    """List all tracked components"""
    manager = get_update_manager()
    return manager.get_all_components()


@router.get("/component/{component_id}")
def get_component(component_id: str):
    """Get details for a specific component"""
    manager = get_update_manager()
    component = manager.get_component(component_id)

    if not component:
        raise HTTPException(status_code=404, detail="Component not found")

    return {
        "component_id": component.component_id,
        "type": component.component_type.value,
        "name": component.name,
        "current_version": component.current_version,
        "latest_version": component.latest_version,
        "update_available": component.update_available,
        "last_checked": component.last_checked.isoformat(),
        "last_updated": component.last_updated.isoformat() if component.last_updated else None,
        "metadata": component.metadata
    }


@router.post("/update")
async def update_component(request: UpdateRequest):
    """
    Update a specific component

    Creates a backup before updating (unless disabled).
    Performs health check after update.
    Rolls back automatically if health check fails.
    """
    manager = get_update_manager()

    try:
        operation = await manager.update_component(
            request.component_id,
            create_backup=request.create_backup
        )

        return {
            "operation_id": operation.id,
            "component_id": operation.component_id,
            "from_version": operation.from_version,
            "to_version": operation.to_version,
            "status": operation.status.value,
            "backup_created": operation.backup_path is not None,
            "rollback_available": operation.rollback_available,
            "error": operation.error_message
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-background")
async def update_component_background(
    request: UpdateRequest,
    background_tasks: BackgroundTasks
):
    """Update a component in the background"""

    async def run_update():
        manager = get_update_manager()
        await manager.update_component(
            request.component_id,
            create_backup=request.create_backup
        )

    background_tasks.add_task(run_update)

    return {
        "status": "scheduled",
        "component_id": request.component_id,
        "message": "Update will run in background. Check /updates/history for status."
    }


@router.post("/update-all")
async def update_all_components(
    background_tasks: BackgroundTasks,
    create_backup: bool = Query(True, description="Create backups before updating")
):
    """
    Update all components with pending updates

    Runs in background to avoid timeout.
    """
    manager = get_update_manager()
    pending = manager.get_pending_updates()

    if not pending:
        return {"status": "no_updates", "message": "No pending updates"}

    async def run_all_updates():
        for component in pending:
            try:
                await manager.update_component(
                    component["component_id"],
                    create_backup=create_backup
                )
            except Exception as e:
                api_logger.error(f"Failed to update {component['component_id']}: {e}")

    background_tasks.add_task(run_all_updates)

    return {
        "status": "scheduled",
        "components": [c["component_id"] for c in pending],
        "count": len(pending)
    }


@router.get("/history")
def get_update_history(
    component_id: Optional[str] = Query(None, description="Filter by component"),
    limit: int = Query(50, ge=1, le=500)
):
    """Get update operation history"""
    manager = get_update_manager()
    return manager.get_update_history(component_id, limit)


@router.post("/rollback/{operation_id}")
async def rollback_update(operation_id: str):
    """
    Rollback a specific update operation

    Only works if backup was created and rollback is available.
    """
    manager = get_update_manager()

    # Get operation
    history = manager.get_update_history()
    operation = next((h for h in history if h["id"] == operation_id), None)

    if not operation:
        raise HTTPException(status_code=404, detail="Operation not found")

    if not operation.get("rollback_available"):
        raise HTTPException(status_code=400, detail="Rollback not available for this operation")

    # Create UpdateOperation object and rollback
    from ..update_manager import UpdateOperation, UpdateStatus
    from datetime import datetime

    op = UpdateOperation(
        id=operation["id"],
        component_id=operation["component_id"],
        from_version=operation["from_version"],
        to_version=operation["to_version"],
        status=UpdateStatus(operation["status"]),
        started_at=datetime.fromisoformat(operation["started_at"]),
        completed_at=datetime.fromisoformat(operation["completed_at"]) if operation["completed_at"] else None,
        backup_path=operation["backup_path"],
        error_message=operation["error_message"],
        rollback_available=bool(operation["rollback_available"])
    )

    try:
        await manager._rollback(op)
        return {"status": "rolled_back", "operation_id": operation_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rollback failed: {str(e)}")


@router.post("/cleanup-backups")
def cleanup_old_backups(
    days: int = Query(30, ge=1, le=365, description="Remove backups older than N days")
):
    """Clean up old backup files"""
    manager = get_update_manager()
    removed = manager.cleanup_old_backups(days)

    return {
        "status": "completed",
        "backups_removed": removed
    }


@router.get("/summary")
async def get_update_summary():
    """Get a summary of update status across all components"""
    manager = get_update_manager()

    components = manager.get_all_components()
    history = manager.get_update_history(limit=10)

    updates_available = len([c for c in components if c.get("update_available")])
    recent_updates = len([h for h in history if h.get("status") == "completed"])
    recent_failures = len([h for h in history if h.get("status") == "failed"])

    return {
        "total_components": len(components),
        "updates_available": updates_available,
        "recent_updates": recent_updates,
        "recent_failures": recent_failures,
        "components_by_type": {
            "ollama_models": len([c for c in components if c.get("type") == "ollama_model"]),
            "docker_images": len([c for c in components if c.get("type") == "docker_image"])
        },
        "last_check": components[0].get("last_checked") if components else None
    }
