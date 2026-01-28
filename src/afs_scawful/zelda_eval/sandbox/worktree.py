"""
Git worktree manager for isolated Oracle-of-Secrets testing.

Creates isolated git worktrees where model-generated patches can be
applied and tested without affecting the main codebase.
"""

import subprocess
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal
import uuid


@dataclass
class SandboxConfig:
    """Configuration for sandbox management."""

    oracle_repo: Path = field(
        default_factory=lambda: Path("~/src/hobby/oracle-of-secrets").expanduser()
    )
    sandbox_base: Path = field(
        default_factory=lambda: Path("~/.context/workspaces/zelda-eval").expanduser()
    )
    max_concurrent: int = 3
    cleanup_after_hours: int = 24
    default_branch: str = "main"


@dataclass
class Sandbox:
    """An isolated git worktree sandbox."""

    id: str
    worktree_path: Path
    branch_name: str
    created_at: datetime
    session_id: str | None = None
    status: Literal["active", "building", "testing", "cleanup", "error"] = "active"
    error_message: str | None = None

    def exists(self) -> bool:
        """Check if the worktree still exists."""
        return self.worktree_path.exists()


class WorktreeManager:
    """
    Manage git worktrees for isolated testing.

    Each sandbox is a separate git worktree where patches can be
    applied, built, and tested independently.
    """

    def __init__(self, config: SandboxConfig | None = None):
        self.config = config or SandboxConfig()
        self._active_sandboxes: dict[str, Sandbox] = {}

        # Ensure sandbox base exists
        self.config.sandbox_base.mkdir(parents=True, exist_ok=True)

        # Verify oracle repo exists
        if not self.config.oracle_repo.exists():
            raise FileNotFoundError(
                f"Oracle-of-Secrets repo not found at {self.config.oracle_repo}"
            )

    def create_sandbox(
        self,
        session_id: str | None = None,
        base_branch: str | None = None,
    ) -> Sandbox:
        """
        Create a new isolated worktree sandbox.

        Args:
            session_id: Optional session ID to associate with sandbox
            base_branch: Branch to base the worktree on (default: main)

        Returns:
            Sandbox object with path and metadata
        """
        sandbox_id = f"sandbox-{uuid.uuid4().hex[:8]}"
        branch_name = f"eval/{sandbox_id}"
        base = base_branch or self.config.default_branch

        worktree_path = self.config.sandbox_base / sandbox_id

        try:
            # Create new branch and worktree
            subprocess.run(
                [
                    "git",
                    "worktree",
                    "add",
                    "-b",
                    branch_name,
                    str(worktree_path),
                    base,
                ],
                cwd=self.config.oracle_repo,
                check=True,
                capture_output=True,
                text=True,
            )

            sandbox = Sandbox(
                id=sandbox_id,
                worktree_path=worktree_path,
                branch_name=branch_name,
                created_at=datetime.now(),
                session_id=session_id,
                status="active",
            )

            self._active_sandboxes[sandbox_id] = sandbox
            return sandbox

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to create worktree: {e.stderr}")

    def apply_patch(
        self,
        sandbox_id: str,
        file_path: str,
        content: str,
        create_backup: bool = True,
    ) -> bool:
        """
        Apply a patch (file content) to a sandbox.

        Args:
            sandbox_id: ID of the sandbox
            file_path: Relative path within the sandbox
            content: New file content
            create_backup: Whether to backup the original file

        Returns:
            True if successful
        """
        sandbox = self._active_sandboxes.get(sandbox_id)
        if not sandbox:
            raise ValueError(f"Unknown sandbox: {sandbox_id}")

        target_path = sandbox.worktree_path / file_path

        # Create backup if file exists
        if create_backup and target_path.exists():
            backup_path = target_path.with_suffix(target_path.suffix + ".bak")
            shutil.copy2(target_path, backup_path)

        # Ensure parent directory exists
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Write new content
        target_path.write_text(content)

        return True

    def get_file(self, sandbox_id: str, file_path: str) -> str | None:
        """Read a file from a sandbox."""
        sandbox = self._active_sandboxes.get(sandbox_id)
        if not sandbox:
            return None

        target_path = sandbox.worktree_path / file_path
        if not target_path.exists():
            return None

        return target_path.read_text()

    def list_modified_files(self, sandbox_id: str) -> list[str]:
        """List files that have been modified in the sandbox."""
        sandbox = self._active_sandboxes.get(sandbox_id)
        if not sandbox:
            return []

        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=sandbox.worktree_path,
                capture_output=True,
                text=True,
                check=True,
            )
            # Parse git status output
            files = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    # Format: "XY filename" or "XY original -> renamed"
                    parts = line[3:].split(" -> ")
                    files.append(parts[-1])
            return files
        except subprocess.CalledProcessError:
            return []

    def commit_changes(
        self,
        sandbox_id: str,
        message: str,
    ) -> bool:
        """Commit all changes in a sandbox."""
        sandbox = self._active_sandboxes.get(sandbox_id)
        if not sandbox:
            return False

        try:
            # Stage all changes
            subprocess.run(
                ["git", "add", "-A"],
                cwd=sandbox.worktree_path,
                check=True,
                capture_output=True,
            )

            # Commit
            subprocess.run(
                ["git", "commit", "-m", message],
                cwd=sandbox.worktree_path,
                check=True,
                capture_output=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def cleanup_sandbox(
        self,
        sandbox_id: str,
        keep_on_error: bool = True,
    ) -> bool:
        """
        Remove a sandbox worktree and branch.

        Args:
            sandbox_id: ID of the sandbox to remove
            keep_on_error: If True, don't delete on error status

        Returns:
            True if cleanup successful
        """
        sandbox = self._active_sandboxes.get(sandbox_id)
        if not sandbox:
            return False

        if keep_on_error and sandbox.status == "error":
            return False

        try:
            # Remove worktree
            subprocess.run(
                ["git", "worktree", "remove", str(sandbox.worktree_path), "--force"],
                cwd=self.config.oracle_repo,
                check=True,
                capture_output=True,
            )

            # Delete branch
            subprocess.run(
                ["git", "branch", "-D", sandbox.branch_name],
                cwd=self.config.oracle_repo,
                check=True,
                capture_output=True,
            )

            del self._active_sandboxes[sandbox_id]
            return True

        except subprocess.CalledProcessError:
            # Force cleanup if git commands fail
            if sandbox.worktree_path.exists():
                shutil.rmtree(sandbox.worktree_path, ignore_errors=True)

            if sandbox_id in self._active_sandboxes:
                del self._active_sandboxes[sandbox_id]

            return True

    def cleanup_stale(self) -> int:
        """
        Remove sandboxes older than cleanup_after_hours.

        Returns:
            Number of sandboxes cleaned up
        """
        now = datetime.now()
        stale_ids = []

        for sandbox_id, sandbox in self._active_sandboxes.items():
            age_hours = (now - sandbox.created_at).total_seconds() / 3600
            if age_hours > self.config.cleanup_after_hours:
                stale_ids.append(sandbox_id)

        for sandbox_id in stale_ids:
            self.cleanup_sandbox(sandbox_id, keep_on_error=False)

        return len(stale_ids)

    def list_sandboxes(self) -> list[Sandbox]:
        """List all active sandboxes."""
        return list(self._active_sandboxes.values())

    def get_sandbox(self, sandbox_id: str) -> Sandbox | None:
        """Get a sandbox by ID."""
        return self._active_sandboxes.get(sandbox_id)
