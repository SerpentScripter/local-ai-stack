"""
Git Worktree Routes
API endpoints for managing git worktrees for agent isolation
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from ..worktree_manager import (
    get_worktree_manager,
    WorktreeStatus,
    GitError
)

router = APIRouter(prefix="/worktree", tags=["worktree"])


class CreateWorktreeRequest(BaseModel):
    """Request to create a new worktree"""
    session_id: str
    project_path: str
    base_branch: str = "main"
    branch_prefix: str = "agent"


class CommitRequest(BaseModel):
    """Request to commit changes"""
    message: str
    author: Optional[str] = "AI Agent <agent@local-ai-hub>"


class MergeRequest(BaseModel):
    """Request to merge worktree"""
    squash: bool = False
    delete_after: bool = True


@router.get("/")
def list_worktrees(status: Optional[str] = None):
    """
    List all worktrees.

    Args:
        status: Optional filter by status (creating, active, merging, merged, conflict, deleted, error)
    """
    manager = get_worktree_manager()

    worktree_status = None
    if status:
        try:
            worktree_status = WorktreeStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Valid values: {[s.value for s in WorktreeStatus]}"
            )

    worktrees = manager.list_worktrees(worktree_status)

    return [
        {
            "worktree_id": wt.worktree_id,
            "session_id": wt.session_id,
            "project_path": wt.project_path,
            "worktree_path": wt.worktree_path,
            "branch_name": wt.branch_name,
            "base_branch": wt.base_branch,
            "status": wt.status.value,
            "created_at": wt.created_at.isoformat(),
            "updated_at": wt.updated_at.isoformat(),
            "commit_count": wt.commit_count,
            "error_message": wt.error_message
        }
        for wt in worktrees
    ]


@router.post("/")
def create_worktree(request: CreateWorktreeRequest):
    """
    Create a new isolated worktree for agent development.

    This creates a new git branch and worktree, allowing the agent
    to make changes in isolation without affecting other work.
    """
    manager = get_worktree_manager()

    try:
        worktree = manager.create_worktree(
            session_id=request.session_id,
            project_path=request.project_path,
            base_branch=request.base_branch,
            branch_prefix=request.branch_prefix
        )

        return {
            "worktree_id": worktree.worktree_id,
            "session_id": worktree.session_id,
            "project_path": worktree.project_path,
            "worktree_path": worktree.worktree_path,
            "branch_name": worktree.branch_name,
            "base_branch": worktree.base_branch,
            "status": worktree.status.value,
            "created_at": worktree.created_at.isoformat(),
            "error_message": worktree.error_message
        }

    except GitError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statuses")
def list_valid_statuses():
    """List all valid worktree statuses"""
    return {
        "statuses": [s.value for s in WorktreeStatus],
        "descriptions": {
            "creating": "Worktree is being created",
            "active": "Worktree is active and ready for use",
            "merging": "Worktree is being merged to base branch",
            "merged": "Worktree has been merged to base branch",
            "conflict": "Merge conflict detected",
            "deleted": "Worktree has been deleted",
            "error": "An error occurred"
        }
    }


@router.post("/cleanup")
def cleanup_stale_worktrees(max_age_hours: int = 24):
    """
    Clean up worktrees that have been inactive for too long.

    Args:
        max_age_hours: Maximum age in hours before cleanup (default: 24)
    """
    manager = get_worktree_manager()
    cleaned = manager.cleanup_stale_worktrees(max_age_hours)

    return {
        "cleaned": cleaned,
        "message": f"Cleaned up {cleaned} stale worktrees"
    }


@router.get("/{worktree_id}")
def get_worktree(worktree_id: str):
    """Get a specific worktree"""
    manager = get_worktree_manager()
    worktree = manager.get_worktree(worktree_id)

    if not worktree:
        raise HTTPException(status_code=404, detail="Worktree not found")

    return {
        "worktree_id": worktree.worktree_id,
        "session_id": worktree.session_id,
        "project_path": worktree.project_path,
        "worktree_path": worktree.worktree_path,
        "branch_name": worktree.branch_name,
        "base_branch": worktree.base_branch,
        "status": worktree.status.value,
        "created_at": worktree.created_at.isoformat(),
        "updated_at": worktree.updated_at.isoformat(),
        "commit_count": worktree.commit_count,
        "files_changed": worktree.files_changed,
        "merge_commit": worktree.merge_commit,
        "error_message": worktree.error_message,
        "metadata": worktree.metadata
    }


@router.get("/{worktree_id}/status")
def get_worktree_status(worktree_id: str):
    """
    Get detailed status of a worktree including git status.

    Returns uncommitted changes, commits ahead, and changed files.
    """
    manager = get_worktree_manager()

    try:
        return manager.get_worktree_status(worktree_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/session/{session_id}")
def get_worktrees_by_session(session_id: str):
    """Get all worktrees for a specific session"""
    manager = get_worktree_manager()
    worktrees = manager.get_worktrees_by_session(session_id)

    return [
        {
            "worktree_id": wt.worktree_id,
            "worktree_path": wt.worktree_path,
            "branch_name": wt.branch_name,
            "status": wt.status.value,
            "commit_count": wt.commit_count
        }
        for wt in worktrees
    ]


@router.post("/{worktree_id}/commit")
def commit_changes(worktree_id: str, request: CommitRequest):
    """
    Commit all changes in the worktree.

    Stages all changes and creates a commit with the provided message.
    """
    manager = get_worktree_manager()

    try:
        result = manager.commit_changes(
            worktree_id=worktree_id,
            message=request.message,
            author=request.author
        )
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except GitError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{worktree_id}/check-merge")
def check_merge_status(worktree_id: str):
    """
    Check if the worktree can be cleanly merged back to base.

    Performs a dry-run merge to detect potential conflicts.
    """
    manager = get_worktree_manager()

    try:
        return manager.check_merge_status(worktree_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{worktree_id}/merge")
def merge_worktree(worktree_id: str, request: MergeRequest):
    """
    Merge the worktree branch back to the base branch.

    Args:
        squash: If True, squash all commits into one
        delete_after: If True, delete the worktree after successful merge
    """
    manager = get_worktree_manager()

    try:
        result = manager.merge_to_base(
            worktree_id=worktree_id,
            squash=request.squash,
            delete_after=request.delete_after
        )
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except GitError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{worktree_id}")
def delete_worktree(worktree_id: str, force: bool = False):
    """
    Delete a worktree and its branch.

    Args:
        force: Force delete even if there are uncommitted changes
    """
    manager = get_worktree_manager()

    success = manager.delete_worktree(worktree_id, force=force)

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Failed to delete worktree. Use force=true to force delete."
        )

    return {"deleted": True, "worktree_id": worktree_id}


@router.get("/{worktree_id}/diff")
def get_diff(worktree_id: str, file_path: Optional[str] = None):
    """
    Get the diff of changes in the worktree.

    Args:
        file_path: Optional specific file to diff
    """
    manager = get_worktree_manager()

    try:
        diff = manager.get_diff(worktree_id, file_path)
        return {"diff": diff}

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{worktree_id}/log")
def get_log(worktree_id: str, limit: int = 10):
    """
    Get commit log for the worktree branch.

    Args:
        limit: Maximum number of commits to return
    """
    manager = get_worktree_manager()

    try:
        commits = manager.get_log(worktree_id, limit)
        return {"commits": commits}

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


