"""
Git Worktree Manager
Provides safe parallel development in isolated git worktrees for AI agents.

Based on Auto-Claude pattern:
- Each agent session gets its own isolated worktree
- Safe parallel development without conflicts
- Automatic branch management
- Merge-back with conflict detection
"""
import subprocess
import os
import shutil
import uuid
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Any
from enum import Enum


class WorktreeStatus(Enum):
    """Status of a worktree"""
    CREATING = "creating"
    ACTIVE = "active"
    MERGING = "merging"
    MERGED = "merged"
    CONFLICT = "conflict"
    DELETED = "deleted"
    ERROR = "error"


@dataclass
class Worktree:
    """Represents an isolated git worktree"""
    worktree_id: str
    session_id: str
    project_path: str  # Original repo path
    worktree_path: str  # Isolated worktree path
    branch_name: str
    base_branch: str
    status: WorktreeStatus = WorktreeStatus.CREATING
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    commit_count: int = 0
    files_changed: List[str] = field(default_factory=list)
    merge_commit: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class WorktreeManager:
    """
    Manages git worktrees for isolated agent development.

    Each agent session can request an isolated worktree where it can
    make changes without affecting the main branch or other agents.
    """

    # Default base directory for worktrees
    WORKTREE_BASE_DIR = Path("D:/SHARED/AI_Models/worktrees")

    def __init__(self, base_dir: Optional[Path] = None):
        """Initialize the worktree manager"""
        self.base_dir = base_dir or self.WORKTREE_BASE_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._worktrees: Dict[str, Worktree] = {}
        self._listeners: Dict[str, List[callable]] = {}

    def _run_git(self, cmd: List[str], cwd: str, check: bool = True) -> subprocess.CompletedProcess:
        """Run a git command"""
        full_cmd = ["git"] + cmd
        result = subprocess.run(
            full_cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            shell=True  # Windows compatibility
        )
        if check and result.returncode != 0:
            raise GitError(f"Git command failed: {' '.join(full_cmd)}\n{result.stderr}")
        return result

    def create_worktree(
        self,
        session_id: str,
        project_path: str,
        base_branch: str = "main",
        branch_prefix: str = "agent"
    ) -> Worktree:
        """
        Create an isolated worktree for an agent session.

        Args:
            session_id: Unique identifier for the session
            project_path: Path to the original git repository
            base_branch: Branch to base the worktree on
            branch_prefix: Prefix for the new branch name

        Returns:
            Worktree object with paths and status
        """
        project_path = Path(project_path).resolve()

        # Verify it's a git repository
        if not (project_path / ".git").exists():
            raise GitError(f"Not a git repository: {project_path}")

        # Generate unique identifiers
        worktree_id = f"wt-{uuid.uuid4().hex[:8]}"
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        branch_name = f"{branch_prefix}/{session_id}-{timestamp}"

        # Create worktree directory
        worktree_path = self.base_dir / worktree_id

        worktree = Worktree(
            worktree_id=worktree_id,
            session_id=session_id,
            project_path=str(project_path),
            worktree_path=str(worktree_path),
            branch_name=branch_name,
            base_branch=base_branch
        )

        try:
            # Fetch latest from remote (if exists)
            self._run_git(["fetch", "--all"], str(project_path), check=False)

            # Create new branch and worktree
            self._run_git(
                ["worktree", "add", "-b", branch_name, str(worktree_path), base_branch],
                str(project_path)
            )

            worktree.status = WorktreeStatus.ACTIVE
            worktree.updated_at = datetime.now()

        except GitError as e:
            worktree.status = WorktreeStatus.ERROR
            worktree.error_message = str(e)

        self._worktrees[worktree_id] = worktree
        self._emit("worktree_created", worktree)

        return worktree

    def get_worktree(self, worktree_id: str) -> Optional[Worktree]:
        """Get a worktree by ID"""
        return self._worktrees.get(worktree_id)

    def get_worktrees_by_session(self, session_id: str) -> List[Worktree]:
        """Get all worktrees for a session"""
        return [wt for wt in self._worktrees.values() if wt.session_id == session_id]

    def list_worktrees(self, status: Optional[WorktreeStatus] = None) -> List[Worktree]:
        """List all worktrees, optionally filtered by status"""
        if status:
            return [wt for wt in self._worktrees.values() if wt.status == status]
        return list(self._worktrees.values())

    def get_worktree_status(self, worktree_id: str) -> Dict[str, Any]:
        """
        Get detailed status of a worktree including git status.
        """
        worktree = self._worktrees.get(worktree_id)
        if not worktree:
            raise ValueError(f"Worktree not found: {worktree_id}")

        result = {
            "worktree_id": worktree.worktree_id,
            "status": worktree.status.value,
            "branch_name": worktree.branch_name,
            "base_branch": worktree.base_branch,
            "created_at": worktree.created_at.isoformat(),
            "updated_at": worktree.updated_at.isoformat()
        }

        if worktree.status == WorktreeStatus.ACTIVE:
            # Get git status
            try:
                status_result = self._run_git(
                    ["status", "--porcelain"],
                    worktree.worktree_path,
                    check=False
                )
                result["uncommitted_changes"] = len(status_result.stdout.strip().split("\n")) if status_result.stdout.strip() else 0

                # Get commit count ahead of base
                log_result = self._run_git(
                    ["rev-list", "--count", f"{worktree.base_branch}..HEAD"],
                    worktree.worktree_path,
                    check=False
                )
                result["commits_ahead"] = int(log_result.stdout.strip()) if log_result.stdout.strip() else 0

                # Get changed files
                diff_result = self._run_git(
                    ["diff", "--name-only", worktree.base_branch],
                    worktree.worktree_path,
                    check=False
                )
                result["changed_files"] = diff_result.stdout.strip().split("\n") if diff_result.stdout.strip() else []

            except Exception as e:
                result["git_error"] = str(e)

        return result

    def commit_changes(
        self,
        worktree_id: str,
        message: str,
        author: str = "AI Agent <agent@local-ai-hub>"
    ) -> Dict[str, Any]:
        """
        Commit all changes in the worktree.

        Args:
            worktree_id: ID of the worktree
            message: Commit message
            author: Git author string

        Returns:
            Dict with commit hash and details
        """
        worktree = self._worktrees.get(worktree_id)
        if not worktree:
            raise ValueError(f"Worktree not found: {worktree_id}")

        if worktree.status != WorktreeStatus.ACTIVE:
            raise ValueError(f"Worktree not active: {worktree.status.value}")

        try:
            # Stage all changes
            self._run_git(["add", "-A"], worktree.worktree_path)

            # Check if there are changes to commit
            status = self._run_git(["status", "--porcelain"], worktree.worktree_path)
            if not status.stdout.strip():
                return {"committed": False, "message": "No changes to commit"}

            # Commit
            self._run_git(
                ["commit", "-m", message, "--author", author],
                worktree.worktree_path
            )

            # Get commit hash
            hash_result = self._run_git(["rev-parse", "HEAD"], worktree.worktree_path)
            commit_hash = hash_result.stdout.strip()

            worktree.commit_count += 1
            worktree.updated_at = datetime.now()

            self._emit("worktree_committed", worktree, commit_hash)

            return {
                "committed": True,
                "commit_hash": commit_hash,
                "message": message,
                "commit_count": worktree.commit_count
            }

        except GitError as e:
            return {"committed": False, "error": str(e)}

    def check_merge_status(self, worktree_id: str) -> Dict[str, Any]:
        """
        Check if the worktree can be cleanly merged back to base.

        Returns:
            Dict with merge status and potential conflicts
        """
        worktree = self._worktrees.get(worktree_id)
        if not worktree:
            raise ValueError(f"Worktree not found: {worktree_id}")

        try:
            # Try a dry-run merge
            result = self._run_git(
                ["merge", "--no-commit", "--no-ff", worktree.base_branch],
                worktree.worktree_path,
                check=False
            )

            # Check for conflicts
            status = self._run_git(
                ["diff", "--name-only", "--diff-filter=U"],
                worktree.worktree_path,
                check=False
            )
            conflicts = status.stdout.strip().split("\n") if status.stdout.strip() else []

            # Abort the merge
            self._run_git(["merge", "--abort"], worktree.worktree_path, check=False)

            can_merge = len(conflicts) == 0 and result.returncode == 0

            return {
                "can_merge": can_merge,
                "conflicts": conflicts,
                "message": "Clean merge possible" if can_merge else f"Conflicts detected: {len(conflicts)} files"
            }

        except GitError as e:
            # Try to abort any partial merge
            self._run_git(["merge", "--abort"], worktree.worktree_path, check=False)
            return {"can_merge": False, "error": str(e)}

    def merge_to_base(
        self,
        worktree_id: str,
        squash: bool = False,
        delete_after: bool = True
    ) -> Dict[str, Any]:
        """
        Merge the worktree branch back to the base branch.

        Args:
            worktree_id: ID of the worktree
            squash: If True, squash all commits into one
            delete_after: If True, delete the worktree after merge

        Returns:
            Dict with merge result
        """
        worktree = self._worktrees.get(worktree_id)
        if not worktree:
            raise ValueError(f"Worktree not found: {worktree_id}")

        worktree.status = WorktreeStatus.MERGING
        worktree.updated_at = datetime.now()

        try:
            # First, commit any uncommitted changes
            status = self._run_git(["status", "--porcelain"], worktree.worktree_path)
            if status.stdout.strip():
                self.commit_changes(worktree_id, "Auto-commit before merge")

            # Switch to base branch in main repo
            self._run_git(["checkout", worktree.base_branch], worktree.project_path)

            # Pull latest changes
            self._run_git(["pull", "--ff-only"], worktree.project_path, check=False)

            # Merge the worktree branch
            merge_args = ["merge"]
            if squash:
                merge_args.append("--squash")
            merge_args.append(worktree.branch_name)

            result = self._run_git(merge_args, worktree.project_path, check=False)

            if result.returncode != 0:
                # Conflict detected
                worktree.status = WorktreeStatus.CONFLICT
                worktree.error_message = result.stderr
                self._emit("worktree_conflict", worktree)

                return {
                    "merged": False,
                    "status": "conflict",
                    "message": "Merge conflicts detected. Manual resolution required.",
                    "conflicts": result.stderr
                }

            # If squash, we need to commit
            if squash:
                self._run_git(
                    ["commit", "-m", f"Squash merge: {worktree.session_id}"],
                    worktree.project_path
                )

            # Get merge commit
            hash_result = self._run_git(["rev-parse", "HEAD"], worktree.project_path)
            worktree.merge_commit = hash_result.stdout.strip()
            worktree.status = WorktreeStatus.MERGED
            worktree.updated_at = datetime.now()

            self._emit("worktree_merged", worktree)

            # Delete worktree if requested
            if delete_after:
                self.delete_worktree(worktree_id)

            return {
                "merged": True,
                "status": "merged",
                "merge_commit": worktree.merge_commit,
                "squashed": squash
            }

        except GitError as e:
            worktree.status = WorktreeStatus.ERROR
            worktree.error_message = str(e)
            return {"merged": False, "error": str(e)}

    def delete_worktree(self, worktree_id: str, force: bool = False) -> bool:
        """
        Delete a worktree and its branch.

        Args:
            worktree_id: ID of the worktree
            force: Force delete even if there are uncommitted changes

        Returns:
            True if deleted successfully
        """
        worktree = self._worktrees.get(worktree_id)
        if not worktree:
            return False

        try:
            # Remove the worktree
            remove_args = ["worktree", "remove"]
            if force:
                remove_args.append("--force")
            remove_args.append(worktree.worktree_path)

            self._run_git(remove_args, worktree.project_path, check=False)

            # Delete the branch (if not merged)
            if worktree.status != WorktreeStatus.MERGED:
                delete_args = ["branch", "-D" if force else "-d", worktree.branch_name]
                self._run_git(delete_args, worktree.project_path, check=False)

            # Clean up directory if it still exists
            worktree_path = Path(worktree.worktree_path)
            if worktree_path.exists():
                shutil.rmtree(worktree_path, ignore_errors=True)

            worktree.status = WorktreeStatus.DELETED
            worktree.updated_at = datetime.now()

            self._emit("worktree_deleted", worktree)

            return True

        except GitError:
            return False

    def get_diff(self, worktree_id: str, file_path: Optional[str] = None) -> str:
        """
        Get the diff of changes in the worktree.

        Args:
            worktree_id: ID of the worktree
            file_path: Optional specific file to diff

        Returns:
            Diff string
        """
        worktree = self._worktrees.get(worktree_id)
        if not worktree:
            raise ValueError(f"Worktree not found: {worktree_id}")

        cmd = ["diff", worktree.base_branch]
        if file_path:
            cmd.extend(["--", file_path])

        result = self._run_git(cmd, worktree.worktree_path, check=False)
        return result.stdout

    def get_log(self, worktree_id: str, limit: int = 10) -> List[Dict[str, str]]:
        """
        Get commit log for the worktree branch.
        """
        worktree = self._worktrees.get(worktree_id)
        if not worktree:
            raise ValueError(f"Worktree not found: {worktree_id}")

        result = self._run_git(
            ["log", f"-{limit}", "--pretty=format:%H|%s|%an|%ai"],
            worktree.worktree_path,
            check=False
        )

        commits = []
        for line in result.stdout.strip().split("\n"):
            if line and "|" in line:
                parts = line.split("|", 3)
                commits.append({
                    "hash": parts[0],
                    "message": parts[1] if len(parts) > 1 else "",
                    "author": parts[2] if len(parts) > 2 else "",
                    "date": parts[3] if len(parts) > 3 else ""
                })

        return commits

    def cleanup_stale_worktrees(self, max_age_hours: int = 24) -> int:
        """
        Clean up worktrees that have been inactive for too long.

        Args:
            max_age_hours: Maximum age in hours before cleanup

        Returns:
            Number of worktrees cleaned up
        """
        cleaned = 0
        now = datetime.now()

        for worktree_id, worktree in list(self._worktrees.items()):
            age_hours = (now - worktree.updated_at).total_seconds() / 3600

            if age_hours > max_age_hours and worktree.status in [
                WorktreeStatus.ACTIVE,
                WorktreeStatus.ERROR
            ]:
                if self.delete_worktree(worktree_id, force=True):
                    cleaned += 1

        return cleaned

    # Event system
    def on(self, event: str, callback: callable):
        """Register an event listener"""
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)

    def off(self, event: str, callback: callable):
        """Remove an event listener"""
        if event in self._listeners:
            self._listeners[event] = [cb for cb in self._listeners[event] if cb != callback]

    def _emit(self, event: str, *args):
        """Emit an event to listeners"""
        if event in self._listeners:
            for callback in self._listeners[event]:
                try:
                    callback(*args)
                except Exception:
                    pass


class GitError(Exception):
    """Git command error"""
    pass


# Singleton instance
_worktree_manager: Optional[WorktreeManager] = None


def get_worktree_manager() -> WorktreeManager:
    """Get the singleton worktree manager instance"""
    global _worktree_manager
    if _worktree_manager is None:
        _worktree_manager = WorktreeManager()
    return _worktree_manager
