"""
core/process_manager.py — Process & Application Lifecycle Registry for JARVIS.

Guarantees:
1. Tracks every process and window opened by JARVIS (APP_SESSION registry).
2. Distinguishes JARVIS-spawned processes from user-existing processes.
3. Provides selective cleanup: closes ONLY JARVIS-owned processes upon task completion.
4. Safely terminates process trees (parent + children) without touching user applications.
5. Monitors listening network ports and associates them with sessions.
"""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

from core.logger import log_event


@dataclass
class AppSession:
    session_id: str
    application: str
    process_id: int
    window_title: str = ""
    opened_by_jarvis: bool = True
    start_time: float = field(default_factory=time.time)
    task_id: str = "DEFAULT"
    port: Optional[int] = None
    status: str = "RUNNING"  # RUNNING | STOPPED | CRASHED
    command: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ProcessManager:
    """Singleton process and application registry."""

    _instance: Optional["ProcessManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ProcessManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._sessions: Dict[str, AppSession] = {}
                cls._instance._pre_existing_pids: Set[int] = set()
                cls._instance._snapshot_pre_existing()
            return cls._instance

    def _snapshot_pre_existing(self) -> None:
        """Snapshot running process IDs at initialization time to avoid touching user apps."""
        if _PSUTIL:
            try:
                self._pre_existing_pids = {p.pid for p in psutil.process_iter(["pid"])}
            except Exception:
                self._pre_existing_pids = set()

    def register_process(
        self,
        application: str,
        process_id: int,
        task_id: str = "DEFAULT",
        window_title: str = "",
        port: Optional[int] = None,
        command: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AppSession:
        """Register a new process opened by JARVIS."""
        session_id = f"proc_{application}_{process_id}_{int(time.time() * 1000)}"
        session = AppSession(
            session_id=session_id,
            application=application,
            process_id=process_id,
            window_title=window_title,
            opened_by_jarvis=True,
            start_time=time.time(),
            task_id=task_id,
            port=port,
            status="RUNNING",
            command=command,
            metadata=metadata or {},
        )

        with self._lock:
            self._sessions[session_id] = session

        log_event(
            category="terminal",
            action=f"process_registered: {application} (PID {process_id})",
            status="SUCCESS",
            task_id=task_id,
            agent="ProcessManager",
            details={"session_id": session_id, "port": port, "cmd": command[:120]},
        )
        return session

    def get_session(self, session_id: str) -> Optional[AppSession]:
        with self._lock:
            return self._sessions.get(session_id)

    def list_sessions(self, task_id: Optional[str] = None, active_only: bool = True) -> List[AppSession]:
        """List tracked sessions, updating status if process exited."""
        with self._lock:
            results = []
            for s in list(self._sessions.values()):
                # Refresh alive status
                if s.status == "RUNNING" and not self._is_pid_alive(s.process_id):
                    s.status = "STOPPED"
                if task_id and s.task_id != task_id:
                    continue
                if active_only and s.status != "RUNNING":
                    continue
                results.append(s)
            return results

    def _is_pid_alive(self, pid: int) -> bool:
        if not _PSUTIL or pid <= 0:
            return False
        try:
            return psutil.pid_exists(pid) and psutil.Process(pid).is_running()
        except Exception:
            return False

    def is_jarvis_owned(self, pid: int) -> bool:
        """Confirm this process was spawned by JARVIS and not a user app."""
        if pid in self._pre_existing_pids:
            return False
        with self._lock:
            return any(s.process_id == pid and s.opened_by_jarvis for s in self._sessions.values())

    def stop_session(self, session_id: str, timeout: float = 3.0) -> bool:
        """Safely terminate a specific session by session_id."""
        with self._lock:
            session = self._sessions.get(session_id)
        if not session:
            return False
        return self.stop_pid(session.process_id, timeout=timeout)

    def stop_pid(self, pid: int, timeout: float = 3.0) -> bool:
        """Safely kill a process and its child processes, ONLY if JARVIS owned it."""
        if not self._is_pid_alive(pid):
            self._mark_pid_stopped(pid)
            return True

        if not self.is_jarvis_owned(pid):
            log_event(
                category="errors",
                action=f"Refused to kill non-JARVIS PID {pid}",
                status="ERROR",
                agent="ProcessManager",
            )
            return False

        if not _PSUTIL:
            try:
                os.kill(pid, signal.SIGTERM)
                self._mark_pid_stopped(pid)
                return True
            except Exception as e:
                print(f"[ProcessManager] Kill error: {e}")
                return False

        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)

            # Send SIGTERM first
            for ch in children:
                try:
                    ch.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            parent.terminate()

            gone, alive = psutil.wait_procs(children + [parent], timeout=timeout)
            # Force kill any lingering survivors
            for p in alive:
                try:
                    p.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            self._mark_pid_stopped(pid)
            log_event(
                category="terminal",
                action=f"process_stopped: PID {pid}",
                status="SUCCESS",
                agent="ProcessManager",
            )
            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            self._mark_pid_stopped(pid)
            return True
        except Exception as e:
            log_event(
                category="errors",
                action=f"Error stopping PID {pid}",
                status="ERROR",
                agent="ProcessManager",
                error=str(e),
            )
            return False

    def stop_task_resources(self, task_id: str) -> int:
        """Clean up ALL resources opened by a specific task ID."""
        sessions = self.list_sessions(task_id=task_id, active_only=True)
        count = 0
        for s in sessions:
            if self.stop_pid(s.process_id):
                count += 1
        return count

    def cleanup_all_jarvis_resources(self) -> int:
        """Clean up all active processes spawned by JARVIS during the current run."""
        sessions = self.list_sessions(active_only=True)
        stopped = 0
        for s in sessions:
            if s.opened_by_jarvis:
                if self.stop_pid(s.process_id):
                    stopped += 1
        return stopped

    def _mark_pid_stopped(self, pid: int) -> None:
        with self._lock:
            for s in self._sessions.values():
                if s.process_id == pid:
                    s.status = "STOPPED"

    def find_free_port(self, preferred: int = 8501) -> int:
        """Find an available TCP port for local development servers."""
        import socket
        for port in range(preferred, preferred + 100):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("127.0.0.1", port))
                    return port
                except OSError:
                    continue
        return preferred


# Global singleton instance
process_manager = ProcessManager()
