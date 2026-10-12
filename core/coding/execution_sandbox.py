"""
core/coding/execution_sandbox.py — Safe Execution Sandbox & Git Checkpoint Manager for JARVIS.

Guarantees:
1. Real Windows Desktop resolution accounting for OneDrive and redirected user folders.
2. Workspace directory isolation and path traversal prevention.
3. Automated Git checkpoints (init, commit, diff, rollback) for change tracking and safety.
4. Secret sanitization across prompts, logs, and state files.
5. Controlled command execution with strict timeouts and dangerous command prevention.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from core.logger import log_event
from tools.terminal_executor import CommandResult, TerminalExecutor


def resolve_real_desktop() -> Path:
    """
    Resolve the user's real Windows Desktop directory.
    Accurately accounts for OneDrive folder redirection, Windows User Shell Folders registry,
    and environmental overrides rather than assuming C:\\Users\\<user>\\Desktop.
    """
    # 1. On Windows, check registry for redirected Desktop path (e.g. OneDrive)
    if platform.system() == "Windows":
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            ) as key:
                val, _ = winreg.QueryValueEx(key, "Desktop")
                expanded = os.path.expandvars(val)
                p = Path(expanded)
                if p.exists() and p.is_dir():
                    return p
        except Exception:
            pass

    # 2. Check OneDrive environment variable
    onedrive = os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer") or os.environ.get("OneDriveCommercial")
    if onedrive:
        od_desktop = Path(onedrive) / "Desktop"
        if od_desktop.exists() and od_desktop.is_dir():
            return od_desktop

    # 3. Check core file_explorer service if available
    try:
        from core.file_explorer import file_explorer
        known = file_explorer.get_known_directories()
        if "desktop" in known and known["desktop"].exists():
            return known["desktop"]
    except Exception:
        pass

    # 4. Standard home directory fallback
    home_desktop = Path.home() / "Desktop"
    if home_desktop.exists():
        return home_desktop

    # Default to home directory if Desktop cannot be resolved
    return Path.home()


# Patterns representing sensitive secrets that must never be leaked
_SECRET_PATTERNS = [
    re.compile(r"(AIza[0-9A-Za-z-_]{30,45})"),                   # Google API key (39 chars standard)
    re.compile(r"(sk-[a-zA-Z0-9]{20,})"),                         # OpenAI key
    re.compile(r"(ghp_[0-9a-zA-Z]{36})"),                         # GitHub personal token
    re.compile(r"(gho_[0-9a-zA-Z]{36})"),                         # GitHub oauth token
    re.compile(r"(hf_[a-zA-Z0-9]{34,})"),                         # Hugging Face token
    re.compile(r"(xox[baprs]-[0-9a-zA-Z-]+)"),                    # Slack token
    re.compile(r"(Bearer\s+[a-zA-Z0-9_\-\.]{20,})", re.IGNORECASE),
    re.compile(r"((?:api[_-]?key|secret|password|token)\s*[:=]\s*['\"]?)([^'\"\s\r\n]{8,})(['\"]?)", re.IGNORECASE),
]


def sanitize_secrets(text: str) -> str:
    """Mask credentials and API tokens from strings before logging or LLM transmission."""
    if not text:
        return text
    sanitized = text
    for pattern in _SECRET_PATTERNS:
        if pattern.groups == 3:
            sanitized = pattern.sub(r"\1[REDACTED_SECRET]\3", sanitized)
        else:
            sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)
    return sanitized


@dataclass
class GitCheckpoint:
    commit_hash: str
    message: str
    timestamp: float
    files_affected: List[str] = field(default_factory=list)


class ExecutionSandbox:
    """
    Manages isolated execution spaces for software engineering projects:
    - Resolves verified workspace locations on Desktop
    - Creates and maintains Git repositories for safe rollback
    - Enforces safety boundaries and command execution limits
    """

    def __init__(self, base_workspace: Optional[Path] = None):
        self.real_desktop = resolve_real_desktop()
        self.default_root = base_workspace or (self.real_desktop / "JarvisProjects")
        self.default_root.mkdir(parents=True, exist_ok=True)

    def prepare_project_workspace(
        self,
        project_name: str,
        custom_parent: Optional[Path] = None,
        init_git: bool = True,
    ) -> Path:
        """
        Create and initialize a safe project directory.
        If init_git is True, initializes a Git repository and creates an initial checkpoint.
        """
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", project_name.strip()).strip("._")
        parent_dir = custom_parent or self.default_root
        project_dir = (parent_dir / safe_name).resolve()
        project_dir.mkdir(parents=True, exist_ok=True)

        if init_git:
            self.init_git(project_dir)

        log_event("agent", f"Workspace prepared: {project_dir}", "INFO", "SANDBOX", "ExecutionSandbox")
        return project_dir

    def is_path_within_workspace(self, target_path: Path, workspace_root: Path) -> bool:
        """Verify that target_path is strictly contained within workspace_root (anti-path-traversal)."""
        try:
            resolved_target = target_path.resolve()
            resolved_root = workspace_root.resolve()
            return resolved_root == resolved_target or resolved_root in resolved_target.parents
        except Exception:
            return False

    def init_git(self, project_dir: Path) -> bool:
        """Initialize git repo in project_dir if not present."""
        git_dir = project_dir / ".git"
        if git_dir.exists():
            return True

        try:
            res = TerminalExecutor.execute("git init", cwd=project_dir, timeout=10)
            if res.exit_code == 0:
                # Configure local dummy author if not set
                TerminalExecutor.execute('git config user.name "JARVIS Engineer"', cwd=project_dir, timeout=5)
                TerminalExecutor.execute('git config user.email "jarvis@local.agent"', cwd=project_dir, timeout=5)
                # Create .gitignore if none exists
                gi = project_dir / ".gitignore"
                if not gi.exists():
                    gi.write_text(
                        "__pycache__/\n*.pyc\n.env\n*.log\nnode_modules/\n.venv/\nvenv/\n*.egg-info/\noutputs/checkpoints/\n",
                        encoding="utf-8",
                    )
                self.create_checkpoint(project_dir, "Initial project scaffolding by JARVIS")
                return True
        except Exception as e:
            log_event("agent", f"Git init skipped/failed: {e}", "WARNING", "SANDBOX", "ExecutionSandbox")
        return False

    def create_checkpoint(self, project_dir: Path, message: str) -> Optional[GitCheckpoint]:
        """Stage all changes and commit a verified checkpoint."""
        if not (project_dir / ".git").exists():
            return None
        try:
            # Stage all files
            add_res = TerminalExecutor.execute("git add -A", cwd=project_dir, timeout=15)
            if add_res.exit_code != 0:
                return None

            clean_msg = sanitize_secrets(message).replace('"', '\\"')
            commit_res = TerminalExecutor.execute(f'git commit -m "{clean_msg}"', cwd=project_dir, timeout=15)
            # If nothing to commit, return latest commit hash
            rev_res = TerminalExecutor.execute("git rev-parse HEAD", cwd=project_dir, timeout=10)
            commit_hash = rev_res.stdout.strip() if rev_res.exit_code == 0 else "unknown"

            # Check modified files (separate initial root commit from subsequent commits)
            has_parent = (
                TerminalExecutor.execute("git rev-parse --verify HEAD~1", cwd=project_dir, timeout=5).exit_code == 0
            )
            if has_parent:
                stat_res = TerminalExecutor.execute("git diff --name-only HEAD~1 HEAD", cwd=project_dir, timeout=10)
            else:
                stat_res = TerminalExecutor.execute("git diff-tree --no-commit-id --name-only -r --root HEAD", cwd=project_dir, timeout=10)
            files = [f.strip() for f in stat_res.stdout.splitlines() if f.strip()]

            import time
            return GitCheckpoint(
                commit_hash=commit_hash,
                message=message,
                timestamp=time.time(),
                files_affected=files,
            )
        except Exception as e:
            log_event("agent", f"Git checkpoint failed: {e}", "WARNING", "SANDBOX", "ExecutionSandbox")
            return None

    def get_diff(self, project_dir: Path, compare_with: str = "HEAD~1") -> str:
        """Get git diff of project."""
        if not (project_dir / ".git").exists():
            return ""
        try:
            if compare_with == "HEAD~1":
                has_parent = (
                    TerminalExecutor.execute("git rev-parse --verify HEAD~1", cwd=project_dir, timeout=5).exit_code == 0
                )
                if not has_parent:
                    res = TerminalExecutor.execute("git diff-tree -p --root HEAD", cwd=project_dir, timeout=15)
                    if res.exit_code == 0:
                        return res.stdout
                    st_res = TerminalExecutor.execute("git status --short", cwd=project_dir, timeout=10)
                    return st_res.stdout
            res = TerminalExecutor.execute(f"git diff {compare_with}", cwd=project_dir, timeout=15)
            if res.exit_code == 0:
                return res.stdout
            # Fallback to status if no prior commit
            st_res = TerminalExecutor.execute("git status --short", cwd=project_dir, timeout=10)
            return st_res.stdout
        except Exception as e:
            return f"Error retrieving git diff: {e}"

    def rollback_to_checkpoint(self, project_dir: Path, commit_hash: Optional[str] = None) -> bool:
        """Rollback working tree to clean state or specific commit hash."""
        if not (project_dir / ".git").exists():
            return False
        try:
            if commit_hash:
                res = TerminalExecutor.execute(f"git reset --hard {commit_hash}", cwd=project_dir, timeout=15)
            else:
                res = TerminalExecutor.execute("git reset --hard HEAD", cwd=project_dir, timeout=15)
            clean_res = TerminalExecutor.execute("git clean -fd", cwd=project_dir, timeout=15)
            return res.exit_code == 0 and clean_res.exit_code == 0
        except Exception as e:
            log_event("agent", f"Git rollback error: {e}", "ERROR", "SANDBOX", "ExecutionSandbox")
            return False

    def safe_write_file(
        self,
        project_dir: Path,
        rel_path: str,
        content: str,
        backup_existing: bool = True,
    ) -> Tuple[bool, str]:
        """
        Safely write a file inside project_dir, preventing path traversal.
        Optionally creates a .bak backup of an existing file.
        """
        target = (project_dir / rel_path).resolve()
        if not self.is_path_within_workspace(target, project_dir):
            return False, f"Path traversal blocked: '{rel_path}' is outside project directory."

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if backup_existing and target.exists():
                bak_path = target.with_suffix(target.suffix + ".bak")
                shutil.copy2(target, bak_path)

            target.write_text(content, encoding="utf-8")
            return True, f"Successfully wrote {rel_path}"
        except Exception as e:
            return False, f"Failed to write {rel_path}: {e}"

    def execute_command_safely(
        self,
        command: str,
        project_dir: Path,
        timeout: int = 60,
        is_daemon: bool = False,
        expected_port: Optional[int] = None,
        task_id: str = "DEFAULT",
    ) -> CommandResult:
        """Execute command within project_dir using TerminalExecutor safety guarantees."""
        sanitized_cmd = sanitize_secrets(command)
        log_event("agent", f"Executing in sandbox: {sanitized_cmd}", "INFO", task_id, "ExecutionSandbox")

        return TerminalExecutor.execute(
            command=command,
            cwd=project_dir,
            timeout=timeout,
            is_daemon=is_daemon,
            expected_port=expected_port,
            task_id=task_id,
        )


# Global instance
sandbox = ExecutionSandbox()
