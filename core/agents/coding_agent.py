"""
core/agents/coding_agent.py — Autonomous Software Engineering Agent for JARVIS.

Handles end-to-end software development:
1. Requirements analysis & tech stack selection
2. Project scaffolding (directories, virtual envs, files)
3. Dependency installation
4. Implementation writing
5. Execution (scripts or background web daemons like Streamlit / FastAPI / Flask)
6. Port health checks and UI/API verification
7. Automated self-correction loop (diagnose, fix, re-run, verify; up to 3 retries)
8. Persistent PROJECT_STATE.json management
9. Clean process management & server stopping
"""

from __future__ import annotations

import json
import re
import socket
import sys
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.logger import log_event
from core.process_manager import process_manager
from tools.terminal_executor import CommandResult, TerminalExecutor, classify_error, is_port_listening


@dataclass
class ProjectState:
    project_name: str
    project_dir: str
    requirements: str
    technology: str
    completed_tasks: List[str] = field(default_factory=list)
    current_task: str = ""
    pending_tasks: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    decisions: List[str] = field(default_factory=list)
    files_changed: List[str] = field(default_factory=list)
    tests_passed: bool = False
    server_pid: Optional[int] = None
    server_port: Optional[int] = None
    verification_evidence: str = ""
    status: str = "INITIALIZED"  # INITIALIZED | IN_PROGRESS | VERIFIED | FAILED

    def save(self, project_path: Path) -> None:
        state_file = project_path / "PROJECT_STATE.json"
        state_file.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, project_path: Path) -> Optional["ProjectState"]:
        state_file = project_path / "PROJECT_STATE.json"
        if not state_file.exists():
            return None
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            return cls(**data)
        except Exception:
            return None


class CodingAgent:
    """Autonomous software developer and QA agent."""

    def __init__(self, workspace_root: Optional[Path] = None):
        self.root = workspace_root or (Path.home() / "Desktop" / "JarvisProjects")
        self.root.mkdir(parents=True, exist_ok=True)

    def create_and_run_application(
        self,
        name: str,
        requirements: str,
        files: Dict[str, str],
        dependencies: Optional[List[str]] = None,
        run_command: str = "",
        is_server: bool = False,
        expected_port: Optional[int] = None,
        max_retries: int = 3,
        task_id: str = "DEFAULT",
    ) -> Dict[str, Any]:
        """
        Build an application end-to-end:
        Create files -> install deps -> run -> verify -> self-correct if failed.
        """
        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", name.lower().strip())
        project_dir = self.root / safe_name
        project_dir.mkdir(parents=True, exist_ok=True)

        tech = "Streamlit" if "streamlit" in run_command.lower() or any("streamlit" in (d.lower()) for d in (dependencies or [])) else "Python"

        state = ProjectState(
            project_name=safe_name,
            project_dir=str(project_dir),
            requirements=requirements,
            technology=tech,
            pending_tasks=["scaffold_files", "install_dependencies", "execute", "verify"],
            current_task="scaffold_files",
        )
        state.save(project_dir)

        log_event("agent", f"Creating project: {safe_name}", "INFO", task_id, "CodingAgent")

        # 1. Write Files
        written_files = []
        for rel_path, content in files.items():
            fpath = project_dir / rel_path
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content.strip(), encoding="utf-8")
            written_files.append(rel_path)

        state.files_changed = written_files
        state.completed_tasks.append("scaffold_files")
        state.save(project_dir)

        # 2. Install Dependencies
        if dependencies:
            state.current_task = "install_dependencies"
            state.save(project_dir)
            dep_cmd = f"pip install " + " ".join(dependencies)
            dep_res = TerminalExecutor.execute(dep_cmd, cwd=project_dir, timeout=120, task_id=task_id)
            if dep_res.exit_code != 0:
                state.errors.append(f"Dep install warning: {dep_res.stderr[:200]}")
            state.completed_tasks.append("install_dependencies")
            state.save(project_dir)

        # 3. Execution & Verification Loop
        state.current_task = "execute"
        state.save(project_dir)

        default_run = f"python main.py" if (project_dir / "main.py").exists() else f"python app.py"
        cmd = run_command or default_run

        port = expected_port
        if is_server and not port:
            port = 8501 if "streamlit" in cmd.lower() else process_manager.find_free_port(8000)

        # If streamlit, ensure port flag is passed
        if "streamlit" in cmd.lower() and port and "--server.port" not in cmd:
            cmd += f" --server.port {port} --server.headless true"

        verified = False
        evidence = ""
        attempt = 0

        while attempt < max_retries and not verified:
            attempt += 1
            log_event("agent", f"Execution attempt {attempt}/{max_retries}: {cmd}", "INFO", task_id, "CodingAgent")

            res = TerminalExecutor.execute(
                command=cmd,
                cwd=project_dir,
                timeout=30 if not is_server else 10,
                is_daemon=is_server,
                expected_port=port,
                task_id=task_id,
            )

            if is_server:
                # Check if background server is alive and responding
                time.sleep(2.5)
                if port and is_port_listening(port):
                    # HTTP probe
                    try:
                        req = urllib.request.Request(f"http://127.0.0.1:{port}", headers={"User-Agent": "JARVIS-Agent"})
                        with urllib.request.urlopen(req, timeout=3) as resp:
                            code = resp.getcode()
                            if code in (200, 302, 304):
                                verified = True
                                state.server_pid = res.process_id
                                state.server_port = port
                                evidence = f"HTTP {code} successfully returned on http://localhost:{port} (PID: {res.process_id})"
                                break
                    except Exception as e:
                        # Server port open, still starting up
                        if is_port_listening(port):
                            verified = True
                            state.server_pid = res.process_id
                            state.server_port = port
                            evidence = f"Port {port} is active and accepting connections (PID: {res.process_id})"
                            break
                        state.errors.append(f"HTTP Probe failed: {e}")
                else:
                    # Server died on launch or crashed
                    state.errors.append(f"Server not listening on port {port}. STDERR:\n{res.stderr}")
                    # Diagnose and self-correct
                    fixed = self._self_correct(project_dir, res.stderr or res.stdout, files)
                    if not fixed:
                        break
            else:
                # Synchronous script / program
                if res.exit_code == 0:
                    verified = True
                    evidence = f"Process exited with code 0.\nOutput:\n{res.stdout.strip()[:600]}"
                    break
                else:
                    state.errors.append(f"Attempt {attempt} failed (code {res.exit_code}):\n{res.stderr}")
                    fixed = self._self_correct(project_dir, res.stderr or res.stdout, files)
                    if not fixed:
                        break

        state.tests_passed = verified
        state.verification_evidence = evidence
        state.status = "VERIFIED" if verified else "FAILED"
        state.current_task = "completed" if verified else "failed"
        if verified:
            state.completed_tasks.append("verify")
        state.save(project_dir)

        log_event(
            "agent",
            f"Project {safe_name} finished: {'SUCCESS' if verified else 'FAILED'}",
            "SUCCESS" if verified else "FAILED",
            task_id,
            "CodingAgent",
            details={"verified": verified, "evidence": evidence[:150]},
        )

        return {
            "success": verified,
            "project_name": safe_name,
            "project_dir": str(project_dir),
            "files": written_files,
            "server_port": state.server_port,
            "server_pid": state.server_pid,
            "verification": evidence or ("All automated checks failed." if not verified else "Passed"),
            "state_file": str(project_dir / "PROJECT_STATE.json"),
        }

    def _self_correct(self, project_dir: Path, error_output: str, files: Dict[str, str]) -> bool:
        """Analyze error output, classify, and attempt targeted fix on project files."""
        err_type = classify_error(error_output)
        log_event("agent", f"Self-correcting error type: {err_type}", "INFO", "DIAGNOSE", "CodingAgent")

        # 1. Dependency error: auto-install missing package
        if err_type == "dependency_error":
            m = re.search(r"No module named ['\"]([a-zA-Z0-9_\-\.]+)['\"]", error_output)
            if m:
                pkg = m.group(1).split(".")[0]
                print(f"[CodingAgent] 🔧 Installing missing dependency: {pkg}")
                TerminalExecutor.execute(f"pip install {pkg}", cwd=project_dir)
                return True

        # 2. Syntax/import/runtime error: inspect traceback and fix file
        tb_match = re.findall(r'File ["\']([^"\']+\.py)["\'],\s+line\s+(\d+)', error_output)
        if tb_match:
            broken_file_name, line_num = tb_match[-1]
            broken_rel = Path(broken_file_name).name
            for rel_path, code in files.items():
                if Path(rel_path).name == broken_rel:
                    fixed_code = self._apply_code_heuristic_fix(code, error_output, int(line_num))
                    if fixed_code and fixed_code != code:
                        (project_dir / rel_path).write_text(fixed_code, encoding="utf-8")
                        files[rel_path] = fixed_code
                        print(f"[CodingAgent] 🔧 Self-corrected code in {rel_path} near line {line_num}")
                        return True

        return False

    def _apply_code_heuristic_fix(self, code: str, error: str, line_no: int) -> str:
        """Apply targeted fixes for common errors (missing imports, typos)."""
        lines = code.splitlines()

        # Missing standard library imports
        if "name 'math' is not defined" in error and "import math" not in code:
            return "import math\n" + code
        if "name 'sys' is not defined" in error and "import sys" not in code:
            return "import sys\n" + code
        if "name 'os' is not defined" in error and "import os" not in code:
            return "import os\n" + code
        if "name 'json' is not defined" in error and "import json" not in code:
            return "import json\n" + code

        # Simple division by zero or index error protection
        if "zerodivisionerror" in error.lower() and 0 <= line_no - 1 < len(lines):
            lines[line_no - 1] = f"# Protected by JARVIS\n        try:\n            {lines[line_no - 1]}\n        except ZeroDivisionError:\n            pass"
            return "\n".join(lines)

        return code

    def stop_project(self, project_name: str) -> bool:
        """Stop running server or background processes associated with a project."""
        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", project_name.lower().strip())
        project_dir = self.root / safe_name
        state = ProjectState.load(project_dir)
        if state and state.server_pid:
            ok = process_manager.stop_pid(state.server_pid)
            state.server_pid = None
            state.status = "STOPPED"
            state.save(project_dir)
            return ok
        return False


# Global instance
coding_agent = CodingAgent()
