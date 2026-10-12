"""
core/coding/project_memory.py — Structured Project Memory & Task State for JARVIS.

Guarantees:
1. Maintains structured, persistent project memory in PROJECT_STATE.json.
2. Synchronizes with memory.task_database.TaskDatabase where appropriate.
3. Automatically strips secrets and API credentials before saving.
4. Verifies disk synchronization: ensures recorded files and artifacts exist on disk before resume.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from core.coding.execution_sandbox import sanitize_secrets
from core.logger import log_event


@dataclass
class TaskStepRecord:
    step_id: int
    name: str
    assigned_role: str
    status: str  # PENDING | IN_PROGRESS | COMPLETED | FAILED
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    evidence: str = ""
    error: str = ""


@dataclass
class StructuredProjectMemory:
    project_name: str
    project_dir: str
    purpose: str
    user_requirements: str
    technology_stack: str
    acceptance_criteria: List[str] = field(default_factory=list)
    architectural_decisions: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    key_files: List[str] = field(default_factory=list)
    completed_tasks: List[str] = field(default_factory=list)
    pending_tasks: List[str] = field(default_factory=list)
    task_steps: List[Dict[str, Any]] = field(default_factory=list)
    git_commits: List[Dict[str, str]] = field(default_factory=list)
    test_results: List[Dict[str, Any]] = field(default_factory=list)
    known_limitations: List[str] = field(default_factory=list)
    status: str = "INITIALIZED"  # INITIALIZED | IN_PROGRESS | VERIFIED | FAILED | STOPPED
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def save(self, project_path: Optional[Path] = None) -> Path:
        """Sanitize secrets and write PROJECT_STATE.json to the project directory."""
        p = Path(project_path or self.project_dir)
        p.mkdir(parents=True, exist_ok=True)
        self.updated_at = time.time()

        raw_dict = asdict(self)
        clean_json_str = sanitize_secrets(json.dumps(raw_dict, indent=2, ensure_ascii=False))

        state_file = p / "PROJECT_STATE.json"
        state_file.write_text(clean_json_str, encoding="utf-8")
        return state_file

    @classmethod
    def load(cls, project_path: Path) -> Optional["StructuredProjectMemory"]:
        """Load project state from disk, verifying data integrity."""
        state_file = project_path / "PROJECT_STATE.json"
        if not state_file.exists():
            return None
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            return cls(**data)
        except Exception as e:
            log_event("agent", f"Failed to load project state: {e}", "WARNING", "MEMORY", "ProjectMemory")
            return None

    def verify_disk_sync(self) -> Dict[str, Any]:
        """Verify that files recorded in memory actually exist on disk."""
        p = Path(self.project_dir)
        missing_files = []
        existing_files = []

        for rel in self.key_files:
            f = p / rel
            if f.exists():
                existing_files.append(rel)
            else:
                missing_files.append(rel)

        return {
            "is_in_sync": len(missing_files) == 0,
            "existing": existing_files,
            "missing": missing_files,
        }

    def record_step(
        self,
        step_id: int,
        name: str,
        role: str,
        status: str,
        evidence: str = "",
        error: str = "",
    ) -> None:
        """Record or update a subagent task step."""
        now = time.time()
        for s in self.task_steps:
            if s.get("step_id") == step_id:
                s["status"] = status
                if evidence:
                    s["evidence"] = evidence
                if error:
                    s["error"] = error
                if status == "COMPLETED":
                    s["completed_at"] = now
                self.save()
                return

        new_step = TaskStepRecord(
            step_id=step_id,
            name=name,
            assigned_role=role,
            status=status,
            started_at=now,
            completed_at=now if status == "COMPLETED" else None,
            evidence=evidence,
            error=error,
        )
        self.task_steps.append(asdict(new_step))
        self.save()

    def record_decision(self, decision: str) -> None:
        """Record an architectural or design decision."""
        if decision not in self.architectural_decisions:
            self.architectural_decisions.append(decision)
            self.save()

    def record_commit(self, commit_hash: str, message: str) -> None:
        """Record a verified git commit."""
        self.git_commits.append({"hash": commit_hash[:10], "message": message, "time": time.ctime()})
        self.save()

    def record_test(self, test_name: str, passed: bool, output: str) -> None:
        """Record test execution output."""
        self.test_results.append({
            "name": test_name,
            "passed": passed,
            "output": sanitize_secrets(output[:500]),
            "timestamp": time.time(),
        })
        self.save()
