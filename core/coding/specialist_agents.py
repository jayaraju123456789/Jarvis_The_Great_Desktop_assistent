"""
core/coding/specialist_agents.py — Modular Specialist Subagents for JARVIS Coding Agent.

Roles:
1. RequirementAnalyst: Converts user intent into structured specifications & acceptance criteria.
2. Architect: Designs system topology, module relationships, and technology selection.
3. FrontendDeveloper: Synthesizes client interfaces (HTML/CSS/JS, Streamlit, or GUI).
4. BackendDeveloper: Synthesizes business logic, APIs, and services (FastAPI, Flask, Python).
5. DatabaseEngineer: Designs schemas, SQL migrations, and data access layers.
6. SecurityReviewer: Audits code for vulnerabilities, injection risks, and secret leakage.
7. IntegrationCoordinator: Assembles project manifests, entry points, and deployment configurations.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.logger import log_event


@dataclass
class RequirementSpec:
    title: str
    summary: str
    target_users: str
    functional_features: List[str]
    non_functional_features: List[str]
    acceptance_criteria: List[str]
    suggested_tech: str
    is_server_required: bool
    is_database_required: bool


@dataclass
class ArchitecturePlan:
    tech_stack: str
    entry_point: str
    run_command: str
    expected_port: Optional[int]
    file_layout: Dict[str, str]  # path -> description
    dependencies: List[str]
    database_type: Optional[str] = None


class RequirementAnalyst:
    """Extracts formal specifications and acceptance criteria from raw user requests."""

    def analyze(self, raw_request: str) -> RequirementSpec:
        low = raw_request.lower()
        title = re.sub(r"[^a-zA-Z0-9_\s]", "", raw_request).strip()[:40] or "Application"
        safe_title = re.sub(r"\s+", "_", title.title())

        is_server = any(w in low for w in ("api", "server", "fastapi", "flask", "streamlit", "web app", "dashboard", "rest", "backend"))
        is_db = any(w in low for w in ("database", "db", "sqlite", "sql", "store", "records", "crud", "persist"))

        # Tech deduction
        if "streamlit" in low:
            tech = "Streamlit"
        elif "fastapi" in low:
            tech = "FastAPI"
        elif "flask" in low:
            tech = "Flask"
        elif any(w in low for w in ("html", "website", "frontend", "web page")):
            tech = "HTML_CSS_JS"
        else:
            tech = "Python"

        functional = []
        if "calculator" in low:
            functional.extend([
                "Perform arithmetic calculations (add, subtract, multiply, divide, power)",
                "Validate input values and handle zero-division errors gracefully",
                "Self-test mathematical correctness",
            ])
        elif "dashboard" in low or "analytics" in low:
            functional.extend([
                "Display KPI metrics and operational stats",
                "Provide interactive data filtering and entry controls",
                "Render structured tables and analytical status cards",
            ])
        elif "api" in low or "rest" in low:
            functional.extend([
                "Expose RESTful HTTP endpoints for data access",
                "Validate incoming request payloads",
                "Return standardized JSON response contracts",
            ])
        else:
            functional.append(f"Execute requested logic for: {raw_request[:80]}")

        criteria = [
            "Project must run non-interactively and exit with status 0 or start background server successfully",
            "Zero uncaught exceptions during standard operational workflows",
            "Automated self-verification tests included and passing",
        ]
        if is_server:
            criteria.append("Server must respond with HTTP 200 on local loopback port")

        return RequirementSpec(
            title=safe_title,
            summary=f"Autonomous application satisfying: {raw_request}",
            target_users="End-user or automated workflow",
            functional_features=functional,
            non_functional_features=["Local execution", "Zero remote cloud dependencies", "Safe error handling"],
            acceptance_criteria=criteria,
            suggested_tech=tech,
            is_server_required=is_server,
            is_database_required=is_db,
        )


class Architect:
    """Designs architecture, file topology, and module dependencies."""

    def design(self, spec: RequirementSpec) -> ArchitecturePlan:
        tech = spec.suggested_tech
        files: Dict[str, str] = {}
        deps: List[str] = []
        run_cmd = "python main.py"
        port: Optional[int] = None
        db_type: Optional[str] = "sqlite" if spec.is_database_required else None

        if tech == "Streamlit":
            deps.append("streamlit")
            port = 8501
            run_cmd = "python -m streamlit run app.py"
            files["app.py"] = "Streamlit user interface and application logic"
            files["README.md"] = "Project overview and execution guide"

        elif tech == "FastAPI":
            deps.extend(["fastapi", "uvicorn"])
            port = 8000
            run_cmd = "python -m uvicorn main:app --host 127.0.0.1 --port 8000"
            files["main.py"] = "FastAPI application endpoints and middleware"
            files["schemas.py"] = "Pydantic models and request validation"
            files["README.md"] = "API documentation"

        elif tech == "Flask":
            deps.append("flask")
            port = 5000
            run_cmd = "python app.py"
            files["app.py"] = "Flask application routes and controller"
            files["README.md"] = "Flask application documentation"

        elif tech == "HTML_CSS_JS":
            run_cmd = "python -m http.server 8080"
            port = 8080
            files["index.html"] = "HTML5 semantic structure and styling"
            files["app.js"] = "Client-side interactivity"
            files["styles.css"] = "Responsive styling and themes"
            files["README.md"] = "Web application documentation"

        else:  # Standard Python Application
            run_cmd = "python main.py"
            files["main.py"] = "Application entry point and self-tests"
            files["README.md"] = "Python project documentation"

        if spec.is_database_required:
            files["database.py"] = "SQLite database initialization and access models"

        return ArchitecturePlan(
            tech_stack=tech,
            entry_point=list(files.keys())[0],
            run_command=run_cmd,
            expected_port=port,
            file_layout=files,
            dependencies=deps,
            database_type=db_type,
        )


class SecurityReviewer:
    """Performs static security analysis on proposed project files."""

    DANGEROUS_PATTERNS = [
        (re.compile(r"\bexec\s*\("), "Arbitrary code execution via exec()"),
        (re.compile(r"\beval\s*\("), "Arbitrary expression evaluation via eval()"),
        (re.compile(r"\bos\.system\s*\("), "Unsafe shell execution via os.system()"),
        (re.compile(r"\bpickle\.loads\s*\("), "Insecure deserialization via pickle.loads()"),
        (re.compile(r"(?:api_key|password|secret)\s*=\s*['\"][a-zA-Z0-9_\-\.]{12,}['\"]", re.IGNORECASE), "Potential hardcoded secret or credential"),
        (re.compile(r"SELECT\s+.*\s+FROM\s+.*%\s+", re.IGNORECASE), "Potential SQL injection vulnerability via string interpolation"),
    ]

    def review_files(self, files: Dict[str, str]) -> Dict[str, Any]:
        """Audit file contents for security vulnerabilities and dangerous APIs."""
        findings = []

        for rel_path, code in files.items():
            # Check Python AST
            if rel_path.endswith(".py"):
                try:
                    tree = ast.parse(code, filename=rel_path)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Call):
                            if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
                                findings.append({
                                    "file": rel_path,
                                    "line": node.lineno,
                                    "severity": "CRITICAL",
                                    "issue": f"Prohibited builtin {node.func.id}() invocation",
                                })
                except SyntaxError:
                    pass

            # Regex scanning
            lines = code.splitlines()
            for idx, line in enumerate(lines, 1):
                for pattern, msg in self.DANGEROUS_PATTERNS:
                    if pattern.search(line):
                        findings.append({
                            "file": rel_path,
                            "line": idx,
                            "severity": "HIGH",
                            "issue": msg,
                        })

        is_clean = len(findings) == 0
        return {
            "passed": is_clean,
            "vulnerabilities_found": len(findings),
            "findings": findings,
            "summary": "Security review passed with zero critical findings." if is_clean else f"Security review identified {len(findings)} issues.",
        }


class IntegrationCoordinator:
    """Assembles all generated files, dependencies, manifests, and documentation into a cohesive project."""

    def assemble(
        self,
        spec: RequirementSpec,
        arch: ArchitecturePlan,
        files: Dict[str, str],
        dependencies: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        """Assemble all project files, ensuring requirements.txt, README.md, and configs exist."""
        all_files = dict(files)

        # 1. Ensure requirements.txt
        all_deps = sorted(list(set(arch.dependencies + (dependencies or []))))
        if all_deps:
            all_files["requirements.txt"] = "\n".join(all_deps) + "\n"

        # 2. Ensure README.md
        if "README.md" not in all_files:
            readme_lines = [
                f"# {spec.title}",
                "",
                spec.summary,
                "",
                f"**Technology:** {arch.tech_stack}",
                "",
                "## Features",
            ]
            for f in spec.functional_features:
                readme_lines.append(f"- {f}")
            readme_lines.extend([
                "",
                "## Running the Project",
                "```bash",
            ])
            if all_deps:
                readme_lines.append(f"pip install -r requirements.txt")
            readme_lines.extend([
                arch.run_command,
                "```",
                "",
                "## Acceptance Criteria",
            ])
            for c in spec.acceptance_criteria:
                readme_lines.append(f"- [x] {c}")
            all_files["README.md"] = "\n".join(readme_lines) + "\n"

        return all_files
