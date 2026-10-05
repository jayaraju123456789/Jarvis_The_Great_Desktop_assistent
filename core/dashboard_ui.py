"""
core/dashboard_ui.py — Professional Agent Status Dashboard for JARVIS.

Renders modern real-time HUD progress in both terminal and web dashboard:
- Active Status & Task ID
- Current Agent & Subtask
- Visual Progress Bar (████████░░ 80%)
- Active Tools Matrix (File System, Terminal, Browser, Python, Document Engine, Research)
- Error Counter & Step Metrics
"""

from __future__ import annotations

import os
import sys
import time

for _stream in ("stdout", "stderr"):
    try:
        _s = getattr(sys, _stream, None)
        if _s is not None and hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from typing import Dict, List, Optional


class AgentDashboard:
    """Renders a sleek, responsive text and state dashboard for autonomous execution."""

    @staticmethod
    def render_terminal(
        task_id: str,
        goal: str,
        agent: str,
        current_action: str,
        completed_steps: int,
        total_steps: int,
        active_tools: Optional[List[str]] = None,
        errors: int = 0,
        status: str = "ACTIVE",
    ) -> str:
        width = 62
        pct = int((completed_steps / total_steps * 100)) if total_steps > 0 else 0
        filled = int(pct / 10)
        bar = "#" * filled + "-" * (10 - filled)

        default_tools = ["File System", "Terminal", "Browser", "Python", "Document Engine", "Research Engine"]
        tools_list = active_tools or default_tools
        tools_line = " ".join(f"[{t}]" for t in tools_list[:4])
        tools_line2 = " ".join(f"[{t}]" for t in tools_list[4:])

        lines = [
            "+" + "-" * (width - 2) + "+",
            f"|  JARVIS AUTONOMOUS AGENT                   STATUS: {status:<10} |",
            "+" + "-" * (width - 2) + "+",
            f"|  Task ID:        {task_id:<42} |",
            f"|  Goal:           {goal[:42]:<42} |",
            f"|  Active Agent:   {agent:<42} |",
            f"|  Progress:       [{bar}] {pct:>3}%                       |",
            f"|  Current Action: {current_action[:42]:<42} |",
            "+" + "-" * (width - 2) + "+",
            f"|  Tools: {tools_line:<49} |",
        ]
        if tools_line2:
            lines.append(f"|         {tools_line2:<49} |")
        lines.extend([
            f"|  Steps:          {completed_steps}/{total_steps} Completed       Errors: {errors:<11} |",
            "+" + "-" * (width - 2) + "+",
        ])
        return "\n".join(lines)


# Quick terminal test
if __name__ == "__main__":
    print(AgentDashboard.render_terminal(
        task_id="JARVIS-2026-001",
        goal="Building Student Management Application",
        agent="Coding Agent",
        current_action="Running integration tests & verifying localhost",
        completed_steps=8,
        total_steps=10,
    ))
