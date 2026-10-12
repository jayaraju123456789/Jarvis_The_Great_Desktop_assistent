"""
core/coding/project_analyzer.py — Existing Codebase Analysis & Minimal-Diff Modifier for JARVIS.

Capabilities:
1. Static inspection of existing codebases (architecture, manifest, entry points, tests).
2. AST analysis for Python files (functions, classes, imports, syntax validity).
3. Call path and symbol tracing across modules.
4. Root cause diagnosis from runtime errors/tracebacks.
5. Minimal-change surgical edits preserving existing coding style and conventions.
6. Post-modification syntax verification and automated rollback on syntax corruption.
"""

from __future__ import annotations

import ast
import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from core.logger import log_event


@dataclass
class CodebaseOverview:
    project_path: str
    project_name: str
    primary_language: str
    frameworks: List[str] = field(default_factory=list)
    manifests_found: List[str] = field(default_factory=list)
    entry_points: List[str] = field(default_factory=list)
    test_files: List[str] = field(default_factory=list)
    total_files: int = 0
    structure_summary: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ProjectAnalyzer:
    """Inspects, traces, and safely modifies existing software repositories."""

    MANIFEST_MAP = {
        "requirements.txt": ("Python", "pip"),
        "pyproject.toml": ("Python", "poetry/flit/setuptools"),
        "setup.py": ("Python", "setuptools"),
        "Pipfile": ("Python", "pipenv"),
        "package.json": ("JavaScript/TypeScript", "npm/yarn"),
        "pom.xml": ("Java", "maven"),
        "build.gradle": ("Java/Kotlin", "gradle"),
        "Cargo.toml": ("Rust", "cargo"),
        "go.mod": ("Go", "go-modules"),
    }

    ENTRY_CANDIDATES = [
        "main.py", "app.py", "server.py", "wsgi.py", "asgi.py", "manage.py",
        "index.js", "server.js", "app.js", "index.ts", "main.go",
    ]

    def inspect_codebase(self, project_path: Union[str, Path], max_files: int = 200) -> CodebaseOverview:
        """Thoroughly audit the layout, technology stack, and structure of a project."""
        p = Path(project_path).resolve()
        if not p.exists() or not p.is_dir():
            raise FileNotFoundError(f"Directory not found: {project_path}")

        manifests_found = []
        deps: List[str] = []
        lang = "Unknown"
        frameworks: Set[str] = set()

        # Check manifests
        for manifest_name, (manifest_lang, _) in self.MANIFEST_MAP.items():
            m_path = p / manifest_name
            if m_path.exists():
                manifests_found.append(manifest_name)
                if lang == "Unknown":
                    lang = manifest_lang

                # Extract dependencies
                if manifest_name == "requirements.txt":
                    try:
                        content = m_path.read_text(encoding="utf-8", errors="ignore")
                        for line in content.splitlines():
                            line = line.strip()
                            if line and not line.startswith("#"):
                                dep_clean = re.split(r"[><=~;]", line)[0].strip()
                                if dep_clean:
                                    deps.append(dep_clean)
                    except Exception:
                        pass
                elif manifest_name == "package.json":
                    try:
                        pkg = json.loads(m_path.read_text(encoding="utf-8", errors="ignore"))
                        deps.extend(list(pkg.get("dependencies", {}).keys()))
                        deps.extend(list(pkg.get("devDependencies", {}).keys()))
                    except Exception:
                        pass

        # Detect Frameworks from dependencies
        deps_lower = {d.lower() for d in deps}
        if any(d in deps_lower for d in ("fastapi", "uvicorn")):
            frameworks.add("FastAPI")
        if "flask" in deps_lower:
            frameworks.add("Flask")
        if "django" in deps_lower:
            frameworks.add("Django")
        if "streamlit" in deps_lower:
            frameworks.add("Streamlit")
        if any(d in deps_lower for d in ("torch", "torchvision")):
            frameworks.add("PyTorch")
        if "tensorflow" in deps_lower:
            frameworks.add("TensorFlow")
        if any(d in deps_lower for d in ("sklearn", "scikit-learn")):
            frameworks.add("scikit-learn")
        if "react" in deps_lower:
            frameworks.add("React")
        if "express" in deps_lower:
            frameworks.add("Express.js")

        # Scan files
        entry_points = []
        test_files = []
        file_tree: Dict[str, List[str]] = {}
        total_files = 0

        # Skip virtualenvs and heavy caches
        skip_dirs = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache", ".idea", ".vscode"}

        for root, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            rel_dir = os.path.relpath(root, p)
            if rel_dir == ".":
                rel_dir = ""

            tracked_files = []
            for f in files:
                total_files += 1
                if total_files > max_files:
                    break

                rel_file = os.path.join(rel_dir, f).replace("\\", "/") if rel_dir else f
                tracked_files.append(f)

                # Check entry candidate
                if f in self.ENTRY_CANDIDATES:
                    entry_points.append(rel_file)

                # Check test candidate
                if f.startswith("test_") or f.endswith("_test.py") or ".test." in f or ".spec." in f:
                    test_files.append(rel_file)

            if tracked_files and len(file_tree) < 25:
                file_tree[rel_dir or "."] = tracked_files[:15]

        if lang == "Unknown":
            # Infer from file extensions
            py_count = len(list(p.glob("*.py")))
            js_count = len(list(p.glob("*.js"))) + len(list(p.glob("*.ts")))
            if py_count > js_count:
                lang = "Python"
            elif js_count > 0:
                lang = "JavaScript/TypeScript"

        return CodebaseOverview(
            project_path=str(p),
            project_name=p.name,
            primary_language=lang,
            frameworks=sorted(list(frameworks)),
            manifests_found=manifests_found,
            entry_points=entry_points,
            test_files=test_files,
            total_files=total_files,
            structure_summary=file_tree,
            dependencies=deps[:50],
        )

    def analyze_python_file(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Parse Python source file and extract AST nodes (classes, functions, imports, docstring)."""
        p = Path(file_path).resolve()
        if not p.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content, filename=str(p))

            docstring = ast.get_docstring(tree) or ""
            classes = []
            functions = []
            imports = []

            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                    classes.append({"name": node.name, "methods": methods, "line": node.lineno})
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.append({
                        "name": node.name,
                        "args": [a.arg for a in node.args.args],
                        "line": node.lineno,
                    })
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    for alias in node.names:
                        imports.append(f"{mod}.{alias.name}" if mod else alias.name)

            return {
                "success": True,
                "file": str(p),
                "is_syntax_valid": True,
                "docstring": docstring,
                "classes": classes,
                "functions": functions,
                "imports": imports,
                "line_count": len(content.splitlines()),
            }
        except SyntaxError as e:
            return {
                "success": False,
                "is_syntax_valid": False,
                "error": f"SyntaxError at line {e.lineno}: {e.msg}",
                "line": e.lineno,
                "offset": e.offset,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def search_symbols_or_references(
        self,
        project_path: Union[str, Path],
        query: str,
        file_extensions: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Search for symbol definitions, method calls, or error strings across files."""
        p = Path(project_path).resolve()
        matches = []
        exts = file_extensions or [".py", ".js", ".ts", ".html", ".css", ".json", ".sql", ".sh", ".yaml", ".yml"]
        pattern = re.compile(re.escape(query), re.IGNORECASE)

        skip_dirs = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache"}

        for root, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for f in files:
                f_path = Path(root) / f
                if f_path.suffix.lower() not in exts:
                    continue

                try:
                    content = f_path.read_text(encoding="utf-8", errors="ignore")
                    lines = content.splitlines()
                    for idx, line in enumerate(lines, 1):
                        if pattern.search(line):
                            matches.append({
                                "file": str(f_path.relative_to(p)),
                                "line_number": idx,
                                "line_content": line.strip()[:160],
                            })
                            if len(matches) >= 50:
                                return matches
                except Exception:
                    continue

        return matches

    def diagnose_root_cause(
        self,
        project_path: Union[str, Path],
        error_output: str,
    ) -> Dict[str, Any]:
        """
        Analyze a stack trace or error log to isolate root cause and pinpoint target files/lines.
        """
        p = Path(project_path).resolve()
        diagnosis: Dict[str, Any] = {
            "error_type": "unknown",
            "root_cause": "",
            "target_file": None,
            "target_line": None,
            "recommended_action": "",
        }

        # 1. Check for Python Traceback
        tb_matches = re.findall(r'File ["\']([^"\']+\.py)["\'],\s+line\s+(\d+)', error_output)
        if tb_matches:
            # Filter matches belonging to the project
            project_tb = []
            for file_path_str, line_num in tb_matches:
                cand = Path(file_path_str)
                # Check if file exists in project
                rel_cand = p / cand.name
                if cand.exists() or rel_cand.exists():
                    project_tb.append((file_path_str, int(line_num)))

            if project_tb:
                target_f, line_no = project_tb[-1]
                diagnosis["target_file"] = Path(target_f).name
                diagnosis["target_line"] = line_no

        # 2. Categorize error
        low_err = error_output.lower()
        if "modulenotfounderror" in low_err or "no module named" in low_err:
            diagnosis["error_type"] = "dependency_error"
            m = re.search(r"no module named ['\"]([^'\"]+)['\"]", low_err)
            pkg = m.group(1).split(".")[0] if m else "missing_package"
            diagnosis["root_cause"] = f"Missing Python package: {pkg}"
            diagnosis["recommended_action"] = f"Install dependency via 'pip install {pkg}'"
        elif "syntaxerror" in low_err:
            diagnosis["error_type"] = "syntax_error"
            diagnosis["root_cause"] = "Invalid Python syntax"
            diagnosis["recommended_action"] = "Repair syntax at target line"
        elif "zerodivisionerror" in low_err:
            diagnosis["error_type"] = "zero_division"
            diagnosis["root_cause"] = "Division by zero without guard"
            diagnosis["recommended_action"] = "Add zero-check or default value"
        elif "filenotfounderror" in low_err:
            diagnosis["error_type"] = "path_error"
            diagnosis["root_cause"] = "File path does not exist"
            diagnosis["recommended_action"] = "Ensure absolute or verified path exists before access"
        elif "keyerror" in low_err:
            diagnosis["error_type"] = "key_error"
            diagnosis["root_cause"] = "Missing dictionary key"
            diagnosis["recommended_action"] = "Use .get() or check key presence"
        elif "typeerror" in low_err:
            diagnosis["error_type"] = "type_error"
            diagnosis["root_cause"] = "Type mismatch or unexpected arguments"
            diagnosis["recommended_action"] = "Cast type or verify function parameters"
        else:
            diagnosis["error_type"] = "runtime_error"
            diagnosis["root_cause"] = error_output.strip().splitlines()[-1] if error_output.strip() else "Unknown failure"
            diagnosis["recommended_action"] = "Inspect logic around failure site"

        return diagnosis

    def apply_minimal_edit(
        self,
        project_path: Union[str, Path],
        relative_file_path: str,
        target_snippet: str,
        replacement_snippet: str,
    ) -> Tuple[bool, str]:
        """
        Perform a surgical replacement of target_snippet with replacement_snippet.
        Verifies syntax validity if Python file; restores original if syntax fails.
        """
        p = Path(project_path).resolve()
        target_f = (p / relative_file_path).resolve()

        if not target_f.exists():
            return False, f"File does not exist: {relative_file_path}"

        orig_content = target_f.read_text(encoding="utf-8")
        if target_snippet not in orig_content:
            return False, f"Target snippet not found in {relative_file_path}."

        # Perform replacement
        new_content = orig_content.replace(target_snippet, replacement_snippet, 1)

        # If Python, verify AST
        if target_f.suffix.lower() == ".py":
            try:
                ast.parse(new_content, filename=str(target_f))
            except SyntaxError as e:
                return False, f"Edit rejected: would produce SyntaxError at line {e.lineno}: {e.msg}"

        # Backup & write
        bak_file = target_f.with_suffix(target_f.suffix + ".bak")
        bak_file.write_text(orig_content, encoding="utf-8")
        target_f.write_text(new_content, encoding="utf-8")

        log_event("agent", f"Applied minimal edit to {relative_file_path}", "INFO", "ANALYZER", "ProjectAnalyzer")
        return True, f"Successfully patched {relative_file_path}."


# Global instance
project_analyzer = ProjectAnalyzer()
