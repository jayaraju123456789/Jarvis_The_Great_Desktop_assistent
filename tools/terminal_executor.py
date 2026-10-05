"""
tools/terminal_executor.py — Reliable Command & Terminal Execution for JARVIS.

Supports:
1. Synchronous commands with full stdout/stderr and exit code capture.
2. Background daemons (e.g. servers, watchers) with PID/port tracking.
3. Structured CommandResult dataclass.
4. Auto-detection of listening ports and health checks.
5. Integration with core.process_manager.
"""

from __future__ import annotations

import os
import platform
import re
import shlex
import socket
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.logger import log_event
from core.process_manager import process_manager

_OS = platform.system()


@dataclass
class CommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration: float
    process_id: int
    status: str  # SUCCESS | FAILED | TIMEOUT | RUNNING_IN_BACKGROUND
    port: Optional[int] = None
    error_type: Optional[str] = None  # syntax | dependency | runtime | permission | timeout | none

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        lines = [
            f"Command: {self.command}",
            f"Status: {self.status} (exit code: {self.exit_code})",
            f"Duration: {self.duration:.2f}s | PID: {self.process_id}",
        ]
        if self.port:
            lines.append(f"Listening Port: {self.port}")
        if self.stdout:
            lines.append(f"STDOUT:\n{self.stdout.strip()}")
        if self.stderr:
            lines.append(f"STDERR:\n{self.stderr.strip()}")
        if self.error_type and self.error_type != "none":
            lines.append(f"Error Classification: {self.error_type}")
        return "\n".join(lines)


def classify_error(output: str, exit_code: int = 1) -> str:
    """Classify the root cause of a command failure."""
    if exit_code == 0:
        return "none"
    low = output.lower()
    if any(k in low for k in ("modulenotfounderror", "no module named", "cannot import name")):
        return "dependency_error"
    if any(k in low for k in ("syntaxerror", "invalid syntax")):
        return "syntax_error"
    if any(k in low for k in ("permissiondenied", "access is denied", "permission denied")):
        return "permission_error"
    if any(k in low for k in ("address already in use", "wsaeaddrinuse", "port is already in use")):
        return "port_conflict"
    if any(k in low for k in ("timed out", "timeout expired", "timeoutexpired")):
        return "timeout"
    if any(k in low for k in ("connectionrefused", "connection refused", "network unreachable")):
        return "network_error"
    if any(k in low for k in ("command not found", "is not recognized as an internal or external command")):
        return "command_not_found"
    return "runtime_error"


def is_port_listening(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> bool:
    """Check if a TCP port is actively listening."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


class TerminalExecutor:
    """Executes terminal commands reliably across platforms."""

    @staticmethod
    def execute(
        command: str,
        cwd: Optional[str | Path] = None,
        timeout: int = 60,
        is_daemon: bool = False,
        expected_port: Optional[int] = None,
        task_id: str = "DEFAULT",
        env: Optional[Dict[str, str]] = None,
    ) -> CommandResult:
        """
        Execute a shell command with structured output.
        If is_daemon=True, starts in background, verifies startup, registers PID, and returns immediately.
        """
        start_time = time.time()
        work_dir = Path(cwd).resolve() if cwd else Path.cwd()
        work_dir.mkdir(parents=True, exist_ok=True)

        full_env = os.environ.copy()
        full_env["PYTHONUNBUFFERED"] = "1"
        if env:
            full_env.update(env)

        # Ensure python alias uses active sys.executable when command begins with "python"
        cmd_str = command.strip()
        if cmd_str.startswith("python "):
            cmd_str = f'"{sys.executable}" ' + cmd_str[7:]
        elif cmd_str.startswith("pip "):
            cmd_str = f'"{sys.executable}" -m pip ' + cmd_str[4:]

        log_event(
            category="terminal",
            action=f"execute_command: {cmd_str[:80]}",
            status="INFO",
            task_id=task_id,
            agent="TerminalExecutor",
            details={"cwd": str(work_dir), "daemon": is_daemon},
        )

        if is_daemon:
            return TerminalExecutor._run_daemon(
                cmd_str=cmd_str,
                raw_command=command,
                work_dir=work_dir,
                expected_port=expected_port,
                task_id=task_id,
                env=full_env,
                start_time=start_time,
            )

        # Synchronous execution
        try:
            kwargs: Dict[str, Any] = {
                "cwd": str(work_dir),
                "env": full_env,
                "capture_output": True,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
                "timeout": timeout,
                "shell": True,
            }
            if _OS == "Windows":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            proc = subprocess.run(cmd_str, **kwargs)
            duration = time.time() - start_time
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            status = "SUCCESS" if proc.returncode == 0 else "FAILED"
            error_type = classify_error(stderr or stdout, proc.returncode)

            log_event(
                category="terminal",
                action=f"command_finished: {command[:60]}",
                status=status,
                task_id=task_id,
                agent="TerminalExecutor",
                duration=duration,
                error=stderr if status == "FAILED" else None,
            )

            return CommandResult(
                command=command,
                exit_code=proc.returncode,
                stdout=stdout,
                stderr=stderr,
                duration=duration,
                process_id=0,
                status=status,
                error_type=error_type,
            )

        except subprocess.TimeoutExpired as te:
            duration = time.time() - start_time
            stdout = te.stdout or "" if isinstance(te.stdout, str) else ""
            stderr = te.stderr or "" if isinstance(te.stderr, str) else ""
            return CommandResult(
                command=command,
                exit_code=-1,
                stdout=stdout,
                stderr=f"Execution timed out after {timeout} seconds.\n{stderr}",
                duration=duration,
                process_id=0,
                status="TIMEOUT",
                error_type="timeout",
            )
        except Exception as e:
            duration = time.time() - start_time
            return CommandResult(
                command=command,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration=duration,
                process_id=0,
                status="FAILED",
                error_type="runtime_error",
            )

    @staticmethod
    def _run_daemon(
        cmd_str: str,
        raw_command: str,
        work_dir: Path,
        expected_port: Optional[int],
        task_id: str,
        env: Dict[str, str],
        start_time: float,
    ) -> CommandResult:
        """Start a long-running process in background, track it, and verify port readiness."""
        try:
            kwargs: Dict[str, Any] = {
                "cwd": str(work_dir),
                "env": env,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "shell": True,
            }
            if _OS == "Windows":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            proc = subprocess.Popen(cmd_str, **kwargs)
            pid = proc.pid

            # Register with process manager
            session = process_manager.register_process(
                application=raw_command.split()[0],
                process_id=pid,
                task_id=task_id,
                port=expected_port,
                command=raw_command,
            )

            # Wait briefly to detect immediate startup crashes or verify port
            initial_wait = 2.0
            time.sleep(initial_wait)

            # Check if it died immediately
            if proc.poll() is not None:
                stdout, stderr = proc.communicate()
                out_txt = stdout.decode("utf-8", errors="replace") if stdout else ""
                err_txt = stderr.decode("utf-8", errors="replace") if stderr else ""
                error_type = classify_error(err_txt or out_txt, proc.returncode)
                return CommandResult(
                    command=raw_command,
                    exit_code=proc.returncode,
                    stdout=out_txt,
                    stderr=err_txt,
                    duration=time.time() - start_time,
                    process_id=pid,
                    status="FAILED",
                    error_type=error_type,
                )

            # If an expected port was specified, poll for readiness (up to 8s)
            listening = False
            if expected_port:
                for _ in range(12):
                    if is_port_listening(expected_port):
                        listening = True
                        break
                    time.sleep(0.5)

            return CommandResult(
                command=raw_command,
                exit_code=0,
                stdout=f"Process running in background (PID: {pid})." + (f" Port {expected_port} active." if listening else ""),
                stderr="",
                duration=time.time() - start_time,
                process_id=pid,
                status="RUNNING_IN_BACKGROUND",
                port=expected_port if listening else None,
                error_type="none",
            )
        except Exception as e:
            return CommandResult(
                command=raw_command,
                exit_code=-1,
                stdout="",
                stderr=f"Failed to start background process: {e}",
                duration=time.time() - start_time,
                process_id=0,
                status="FAILED",
                error_type="runtime_error",
            )
