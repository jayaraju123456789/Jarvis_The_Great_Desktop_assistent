"""
core/logger.py — Structured Logging System for JARVIS.

Produces structured events in:
    logs/agent.log
    logs/browser.log
    logs/terminal.log
    logs/errors.log
    logs/research.log

Sanitizes secrets, timestamps events, and tracks task execution.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time

for _stream in ("stdout", "stderr"):
    try:
        _s = getattr(sys, _stream, None)
        if _s is not None and hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from core.config import LOGS_DIR, sanitize_for_log

_LOCK = threading.Lock()
_LOGGERS: dict[str, logging.Logger] = {}


def _get_file_logger(category: str) -> logging.Logger:
    with _LOCK:
        if category in _LOGGERS:
            return _LOGGERS[category]

        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOGS_DIR / f"{category}.log"

        logger = logging.getLogger(f"jarvis.{category}")
        logger.setLevel(logging.INFO)
        logger.propagate = False

        # Avoid duplicate handlers
        if not logger.handlers:
            handler = logging.FileHandler(str(log_file), encoding="utf-8")
            formatter = logging.Formatter("%(message)s")
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        _LOGGERS[category] = logger
        return logger


def log_event(
    category: str,
    action: str,
    status: str = "INFO",
    task_id: str = "",
    agent: str = "JARVIS",
    duration: float = 0.0,
    error: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> None:
    """Log a structured JSON event to the respective category log."""
    event = {
        "timestamp": datetime.now().isoformat(),
        "task_id": task_id or "TASK-SYSTEM",
        "agent": agent,
        "action": action,
        "status": status.upper(),
        "duration_sec": round(duration, 3),
        "error": error or "",
        "details": details or {},
    }

    raw_json = json.dumps(event, ensure_ascii=False)
    sanitized = sanitize_for_log(raw_json)

    logger = _get_file_logger(category)
    logger.info(sanitized)

    # If status is an error or error is provided, also log to errors.log
    if error or status.upper() in ("ERROR", "FAILED"):
        err_logger = _get_file_logger("errors")
        err_logger.info(sanitized)

    # Console output for observability
    prefix = f"[{agent}][{category.upper()}]"
    if status.upper() in ("ERROR", "FAILED"):
        print(f"\033[91m{prefix} ❌ {action}: {error or status}\033[0m")
    elif status.upper() == "SUCCESS":
        print(f"\033[92m{prefix} ✅ {action} ({duration:.2f}s)\033[0m")
    else:
        print(f"{prefix} ℹ️ {action}")
