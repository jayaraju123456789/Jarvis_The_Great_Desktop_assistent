"""
actions/terminal_tool.py — Discoverable Terminal & Command Tool for JARVIS.

Enables JARVIS to run shell commands, compile software, install packages,
manage background services, and inspect outputs with structured results.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from tools.terminal_executor import CommandResult, TerminalExecutor
from core.process_manager import process_manager


def terminal_tool(parameters: Optional[Dict[str, Any]] = None, **kwargs) -> str:
    """Handler for the terminal_tool action."""
    params = parameters or {}
    action = params.get("action", "run").lower().strip()
    command = params.get("command", "").strip()
    cwd = params.get("cwd")
    timeout = int(params.get("timeout", 60))
    is_daemon = bool(params.get("is_daemon", False))
    expected_port = params.get("expected_port")
    if expected_port:
        try:
            expected_port = int(expected_port)
        except ValueError:
            expected_port = None
    pid = params.get("pid")
    task_id = params.get("task_id", "DEFAULT")

    if action == "run":
        if not command:
            return "Error: No command provided for run action."
        res: CommandResult = TerminalExecutor.execute(
            command=command,
            cwd=cwd,
            timeout=timeout,
            is_daemon=is_daemon,
            expected_port=expected_port,
            task_id=task_id,
        )
        return res.summary()

    elif action == "stop":
        if pid:
            try:
                target_pid = int(pid)
                ok = process_manager.stop_pid(target_pid)
                return f"Stopped process PID {target_pid}: {'Success' if ok else 'Failed or not owned by JARVIS'}."
            except ValueError:
                return f"Invalid PID: {pid}"
        return "Error: Specify 'pid' to stop."

    elif action == "list_processes":
        sessions = process_manager.list_sessions(active_only=True)
        if not sessions:
            return "No active processes currently managed by JARVIS."
        lines = ["Active JARVIS processes:"]
        for s in sessions:
            lines.append(f" - PID {s.process_id}: {s.application} (Port: {s.port or 'N/A'}, Status: {s.status})")
        return "\n".join(lines)

    elif action == "find_port":
        port = process_manager.find_free_port(int(params.get("preferred_port", 8501)))
        return f"Available port: {port}"

    return f"Unknown terminal action: '{action}'. Available: run, stop, list_processes, find_port."


TOOL = {
    "name": "terminal_tool",
    "description": "Executes shell and terminal commands (PowerShell/cmd/bash/python/pip/git/npm). Use this to run scripts, install packages, compile projects, launch local web apps or servers, check command output, and manage processes. Set is_daemon=true for servers or long-running applications.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "run | stop | list_processes | find_port (default: run)",
            },
            "command": {
                "type": "STRING",
                "description": "Command string to execute (e.g. 'pip install streamlit', 'python script.py', 'git status')",
            },
            "cwd": {
                "type": "STRING",
                "description": "Working directory path for the command",
            },
            "timeout": {
                "type": "INTEGER",
                "description": "Execution timeout in seconds (default: 60)",
            },
            "is_daemon": {
                "type": "BOOLEAN",
                "description": "Set to true for long-running services (Streamlit, web servers, background monitors)",
            },
            "expected_port": {
                "type": "INTEGER",
                "description": "TCP port that the daemon is expected to listen on (e.g. 8501, 8000)",
            },
            "pid": {
                "type": "INTEGER",
                "description": "Process ID to terminate when action is 'stop'",
            },
        },
        "required": ["action"],
    },
    "handler": terminal_tool,
}
