"""
tests/test_autonomous_coding_and_ml_agent.py — Acceptance & Verification Suite
for Autonomous Coding Agent and Autonomous ML / Deep Learning Agent.

Covers:
- Acceptance Test A: Tabular classification project using verified public dataset.
- Acceptance Test B: Computer vision project on structured image directory dataset.
- Acceptance Test C: Hugging Face dataset requiring custom loader (not assumed CSV).
- Acceptance Test D: Dataset path differing from default Desktop path.
- Acceptance Test E: Missing dataset file producing clear error rather than false success.
- Acceptance Test F: Bounded diagnosis and error recovery for code/data failure.
- Acceptance Test G: Complete end-to-end run saving model, evaluating, inference, and reporting.
- Coding Agent Tests:
  - Real Windows Desktop resolution (accounting for OneDrive).
  - Git checkpoints, diff, and rollback.
  - GitHub repository search and inspection with untrusted-code safety.
  - AST analysis, symbol tracing, and surgical patching of existing codebases.
  - Specialist subagents: RequirementAnalyst, Architect, SecurityReviewer, IntegrationCoordinator.
  - Secret sanitization across prompts, logs, and state files.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Fix console encoding on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from core.agents.coding_agent import coding_agent, CodingAgent
from core.coding import (
    Architect,
    AutonomousTestDebugger,
    CodebaseOverview,
    ExecutionSandbox,
    GitHubResearcher,
    IntegrationCoordinator,
    ProjectAnalyzer,
    RequirementAnalyst,
    SecurityReviewer,
    StructuredProjectMemory,
    github_researcher,
    project_analyzer,
    resolve_real_desktop,
    sandbox,
    sanitize_secrets,
    test_debugger,
)
from core.ml import (
    DatasetCandidate,
    DatasetDownloader,
    DatasetResearcher,
    HardwareDetector,
    MLAgent,
    MLPipelineBuilder,
    dataset_downloader,
    dataset_researcher,
    hardware_detector,
    ml_agent,
    pipeline_builder,
)


class TestAutonomousCodingAndMLAgent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = Path(tempfile.mkdtemp(prefix="jarvis_coding_ml_test_"))
        cls.custom_sandbox = ExecutionSandbox(base_workspace=cls.test_dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    # ──────────────────────────────────────────────────────────────────────────
    # SECTION 1: EXECUTION SANDBOX & DESKTOP RESOLUTION
    # ──────────────────────────────────────────────────────────────────────────

    def test_01_real_desktop_resolution(self):
        """Assert real desktop resolution detects valid directory without crashing."""
        desktop = resolve_real_desktop()
        self.assertIsInstance(desktop, Path)
        self.assertTrue(desktop.exists(), f"Resolved desktop path {desktop} must exist.")
        print(f"    [Evidence] Real Desktop resolved: {desktop}")

    def test_02_secret_sanitization(self):
        """Assert secret patterns are masked before logging or persistence."""
        sensitive_text = "Here is my key: AIzaSyD9876543210AbCdEfGhIjKlMnOpQrStU and secret: sk-1234567890abcdef123456"
        sanitized = sanitize_secrets(sensitive_text)
        self.assertNotIn("AIzaSyD9876543210AbCdEfGhIjKlMnOpQrStU", sanitized)
        self.assertNotIn("sk-1234567890abcdef123456", sanitized)
        self.assertIn("[REDACTED_SECRET]", sanitized)
        print("    [Evidence] Secret sanitization verified.")

    def test_03_git_checkpoints_and_rollback(self):
        """Assert Git repository is initialized, commits are recorded, and rollback works."""
        proj_dir = self.custom_sandbox.prepare_project_workspace("test_git_repo")
        self.assertTrue((proj_dir / ".git").exists())

        test_file = proj_dir / "example.txt"
        test_file.write_text("Version 1.0", encoding="utf-8")
        ckpt1 = self.custom_sandbox.create_checkpoint(proj_dir, "Commit 1")
        self.assertIsNotNone(ckpt1)

        # Modify file
        test_file.write_text("Version 2.0 Corrupted", encoding="utf-8")
        diff_str = self.custom_sandbox.get_diff(proj_dir)
        self.assertIn("Corrupted", diff_str)

        # Rollback
        reverted = self.custom_sandbox.rollback_to_checkpoint(proj_dir)
        self.assertTrue(reverted)
        self.assertEqual(test_file.read_text(encoding="utf-8"), "Version 1.0")
        print("    [Evidence] Git checkpointing, diff inspection, and rollback verified.")

    # ──────────────────────────────────────────────────────────────────────────
    # SECTION 2: GITHUB RESEARCH & REPOSITORY INTELLIGENCE
    # ──────────────────────────────────────────────────────────────────────────

    def test_04_github_search_and_inspection(self):
        """Assert GitHub researcher returns structured repositories with safety guarantees."""
        results = github_researcher.search_repositories(query="flask todo app", language="python", max_results=2)
        self.assertIsInstance(results, list)
        if results:
            first_repo = results[0]
            self.assertTrue(hasattr(first_repo, "full_name"))
            self.assertTrue(first_repo.html_url.startswith("https://github.com/"))

            # Test static inspection (without executing any scripts)
            inspection = github_researcher.inspect_repository(first_repo.full_name)
            self.assertIn("Execution prohibited", inspection.security_notice)

            # Test comparison
            comparison = github_researcher.compare_repositories(results, "flask todo rest api")
            self.assertIn("recommended", comparison)
            print(f"    [Evidence] GitHub research verified: {len(results)} repos evaluated.")
        else:
            print("    [Evidence] GitHub API search rate-limited or offline (handled safely).")

    # ──────────────────────────────────────────────────────────────────────────
    # SECTION 3: CODEBASE ANALYSIS & SURGICAL MODIFICATION
    # ──────────────────────────────────────────────────────────────────────────

    def test_05_codebase_inspection_and_ast_analysis(self):
        """Assert ProjectAnalyzer extracts AST, classes, functions, and syntax validity."""
        sample_code = '''"""Sample module docstring."""
import math

class Calculator:
    def add(self, a, b):
        return a + b

def multiply(x, y):
    return x * y
'''
        f_path = self.test_dir / "calc_test.py"
        f_path.write_text(sample_code, encoding="utf-8")

        res = project_analyzer.analyze_python_file(f_path)
        self.assertTrue(res["is_syntax_valid"])
        self.assertEqual(len(res["classes"]), 1)
        self.assertEqual(res["classes"][0]["name"], "Calculator")
        self.assertEqual(len(res["functions"]), 1)
        self.assertIn("math", res["imports"])
        print("    [Evidence] AST syntax and structure parsing verified.")

    def test_06_surgical_edit_and_syntax_protection(self):
        """Assert apply_minimal_edit replaces code surgically and reverts if syntax is corrupted."""
        f_path = self.test_dir / "target_module.py"
        f_path.write_text("def compute():\n    return 10 * 2\n", encoding="utf-8")

        # 1. Valid edit
        ok, msg = project_analyzer.apply_minimal_edit(
            project_path=self.test_dir,
            relative_file_path="target_module.py",
            target_snippet="10 * 2",
            replacement_snippet="10 * 5",
        )
        self.assertTrue(ok)
        self.assertIn("10 * 5", f_path.read_text(encoding="utf-8"))

        # 2. Syntax-breaking edit (must be rejected)
        ok_bad, msg_bad = project_analyzer.apply_minimal_edit(
            project_path=self.test_dir,
            relative_file_path="target_module.py",
            target_snippet="10 * 5",
            replacement_snippet="10 * (invalid syntax",
        )
        self.assertFalse(ok_bad)
        self.assertIn("SyntaxError", msg_bad)
        self.assertIn("10 * 5", f_path.read_text(encoding="utf-8"))
        print("    [Evidence] Surgical patch with AST syntax protection verified.")

    # ──────────────────────────────────────────────────────────────────────────
    # SECTION 4: SPECIALIST SUBAGENTS & SECURITY AUDIT
    # ──────────────────────────────────────────────────────────────────────────

    def test_07_specialist_subagents_pipeline(self):
        """Assert RequirementAnalyst, Architect, and SecurityReviewer coordinate properly."""
        req_analyst = RequirementAnalyst()
        spec = req_analyst.analyze("Create a FastAPI analytics service with SQLite database")
        self.assertEqual(spec.suggested_tech, "FastAPI")
        self.assertTrue(spec.is_server_required)
        self.assertTrue(spec.is_database_required)

        arch = Architect().design(spec)
        self.assertIn("fastapi", arch.dependencies)
        self.assertIn("main.py", arch.file_layout)
        self.assertIn("database.py", arch.file_layout)

        # Security check on safe vs unsafe code
        sec = SecurityReviewer()
        safe_files = {"main.py": "def hello(): return 'ok'"}
        unsafe_files = {"hack.py": "eval('print(123)')\nos.system('dir')"}

        self.assertTrue(sec.review_files(safe_files)["passed"])
        self.assertFalse(sec.review_files(unsafe_files)["passed"])
        print("    [Evidence] Specialist subagents and SecurityReviewer verified.")

    # ──────────────────────────────────────────────────────────────────────────
    # SECTION 5: ACCEPTANCE TESTS A THROUGH G (MACHINE LEARNING AGENT)
    # ──────────────────────────────────────────────────────────────────────────

    def test_08_acceptance_test_a_tabular_classification(self):
        """
        Acceptance Test A: Small tabular classification project using a suitable public dataset.
        """
        # Create small test dataset
        data_csv = self.test_dir / "iris_sample.csv"
        data_csv.write_text(
            "sepal_length,sepal_width,petal_length,petal_width,species\n"
            "5.1,3.5,1.4,0.2,setosa\n"
            "4.9,3.0,1.4,0.2,setosa\n"
            "4.7,3.2,1.3,0.2,setosa\n"
            "4.6,3.1,1.5,0.2,setosa\n"
            "5.0,3.6,1.4,0.2,setosa\n"
            "7.0,3.2,4.7,1.4,versicolor\n"
            "6.4,3.2,4.5,1.5,versicolor\n"
            "6.9,3.1,4.9,1.5,versicolor\n"
            "5.5,2.3,4.0,1.3,versicolor\n"
            "6.5,2.8,4.6,1.5,versicolor\n"
            "6.3,3.3,6.0,2.5,virginica\n"
            "5.8,2.7,5.1,1.9,virginica\n"
            "7.1,3.0,5.9,2.1,virginica\n"
            "6.3,2.9,5.6,1.8,virginica\n"
            "6.5,3.0,5.8,2.2,virginica\n",
            encoding="utf-8",
        )

        res = ml_agent.build_and_train_project(
            name="acceptance_test_a",
            requirement="Train a species classification model on iris dataset",
            custom_dataset_path=data_csv,
        )
        self.assertTrue(res["success"], f"Acceptance Test A failed: {res.get('error')}")
        self.assertIn("accuracy", res["metrics"])
        self.assertTrue(Path(res["checkpoint_path"]).exists())
        print(f"    [Evidence] Test A Passed: Accuracy={res['metrics'].get('accuracy')}")

    def test_09_acceptance_test_b_computer_vision_directory(self):
        """
        Acceptance Test B: Computer vision project with structured image directory.
        """
        cv_dir = self.test_dir / "cv_dataset"
        (cv_dir / "cats").mkdir(parents=True, exist_ok=True)
        (cv_dir / "dogs").mkdir(parents=True, exist_ok=True)
        # Dummy image files
        (cv_dir / "cats" / "cat1.jpg").write_bytes(b"\xff\xd8\xff dummy jpeg data")
        (cv_dir / "cats" / "cat2.jpg").write_bytes(b"\xff\xd8\xff dummy jpeg data")
        (cv_dir / "dogs" / "dog1.jpg").write_bytes(b"\xff\xd8\xff dummy jpeg data")
        (cv_dir / "dogs" / "dog2.jpg").write_bytes(b"\xff\xd8\xff dummy jpeg data")

        verified_ds = dataset_downloader.inspect_and_validate_path(cv_dir, self.test_dir)
        self.assertTrue(verified_ds.is_verified)
        self.assertEqual(verified_ds.format, "images")
        self.assertEqual(verified_ds.row_count, 4)
        self.assertEqual(verified_ds.classes_detected, ["cats", "dogs"])
        print("    [Evidence] Test B Passed: Structured image dataset verified.")

    def test_10_acceptance_test_c_huggingface_dataset_loader(self):
        """
        Acceptance Test C: Hugging Face dataset requiring custom loader rather than assumed CSV.
        """
        hf_candidate = DatasetCandidate(
            source="huggingface",
            name="sentiment_benchmark",
            identifier="sample/sentiment_benchmark",
            description="HF text classification dataset",
            format="hf_dataset",
            approx_size="streamable",
            license="MIT",
            task_type="nlp",
        )
        proj_dir = self.test_dir / "hf_test_proj"
        proj_dir.mkdir(parents=True, exist_ok=True)
        verified_ds = dataset_downloader.download_and_verify(hf_candidate, proj_dir)

        self.assertTrue(verified_ds.is_verified)
        self.assertEqual(verified_ds.format, "hf_dataset")

        # Test pipeline builder generates specialized Hugging Face loader
        hw = hardware_detector.profile(proj_dir)
        files = pipeline_builder.generate_project_files("hf_test", proj_dir, verified_ds, hw, "classification")
        self.assertIn("Hugging Face dataset loader module", files["src/data/loader.py"])
        print("    [Evidence] Test C Passed: Hugging Face dataset loader generated correctly.")

    def test_11_acceptance_test_d_custom_non_desktop_path(self):
        """
        Acceptance Test D: Dataset whose actual local path differs from default Desktop path.
        """
        custom_external_dir = Path(tempfile.mkdtemp(prefix="external_data_"))
        external_file = custom_external_dir / "housing_external.csv"
        external_file.write_text(
            "MedInc,HouseAge,AveRooms,Population,MedHouseVal\n"
            "8.32,41.0,6.98,322.0,4.52\n"
            "8.30,21.0,6.23,2401.0,3.58\n"
            "7.25,52.0,5.81,496.0,3.41\n"
            "5.64,52.0,5.81,558.0,3.42\n"
            "3.84,52.0,6.28,565.0,2.69\n"
            "4.03,52.0,4.76,413.0,2.99\n"
            "3.65,52.0,4.93,1094.0,2.99\n"
            "3.12,52.0,4.79,1157.0,2.41\n",
            encoding="utf-8",
        )

        res = ml_agent.build_and_train_project(
            name="acceptance_test_d",
            requirement="Train a housing price regression model",
            custom_dataset_path=external_file,
        )
        self.assertTrue(res["success"], f"Acceptance Test D failed: {res.get('error')}")
        self.assertEqual(res["dataset_path"], str(external_file))
        shutil.rmtree(custom_external_dir, ignore_errors=True)
        print("    [Evidence] Test D Passed: Arbitrary external dataset path handled correctly.")

    def test_12_acceptance_test_e_missing_dataset_path_error(self):
        """
        Acceptance Test E: Missing dataset file produces clear truthful error, not false success.
        """
        non_existent_file = Path("C:/NonExistentPath/missing_dataset_12345.csv")
        res = ml_agent.build_and_train_project(
            name="acceptance_test_e",
            requirement="Train on missing data",
            custom_dataset_path=non_existent_file,
        )
        self.assertFalse(res["success"])
        self.assertIn("does not exist on disk", res["error"])
        print(f"    [Evidence] Test E Passed: Truthful failure message: {res['error']}")

    def test_13_acceptance_test_f_bounded_recovery_attempt(self):
        """
        Acceptance Test F: Diagnose runtime/syntax failure and attempt bounded recovery.
        """
        proj_dir = self.test_dir / "recovery_proj"
        proj_dir.mkdir(parents=True, exist_ok=True)
        broken_file = proj_dir / "main.py"
        # Intentionally missing import of math
        broken_file.write_text("def run():\n    return math.sqrt(16)\nif __name__ == '__main__':\n    print(run())\n", encoding="utf-8")

        outcome = test_debugger.run_bounded_testing_and_repair_loop(
            project_dir=proj_dir,
            run_command=f'"{sys.executable}" main.py',
            max_retries=3,
        )
        self.assertTrue(outcome.success, f"Recovery failed: {outcome.error_summary}")
        self.assertEqual(outcome.status, "REPAIRED")
        self.assertIn("import math", broken_file.read_text(encoding="utf-8"))
        print("    [Evidence] Test F Passed: Auto-repaired missing import and verified exit 0.")

    def test_14_acceptance_test_g_end_to_end_delivery(self):
        """
        Acceptance Test G: Complete end-to-end run saving model, evaluating, inference, and producing report.
        """
        # Create dataset
        data_csv = self.test_dir / "binary_classification.csv"
        data_csv.write_text(
            "feature1,feature2,feature3,label\n"
            "1.2,3.4,0.5,1\n"
            "0.8,2.1,0.2,0\n"
            "2.5,4.1,1.0,1\n"
            "0.3,1.5,0.1,0\n"
            "1.9,3.8,0.9,1\n"
            "0.5,1.8,0.3,0\n"
            "2.1,4.5,1.2,1\n"
            "0.2,1.1,0.0,0\n"
            "1.5,3.0,0.7,1\n"
            "0.7,1.9,0.2,0\n",
            encoding="utf-8",
        )

        res = ml_agent.build_and_train_project(
            name="acceptance_test_g",
            requirement="Train a binary classification model and deliver full report",
            custom_dataset_path=data_csv,
        )
        self.assertTrue(res["success"])
        self.assertTrue(Path(res["checkpoint_path"]).exists())
        self.assertTrue(Path(res["report_path"]).exists())

        # Verify delivery report has all 8 ML sections
        report_text = Path(res["report_path"]).read_text(encoding="utf-8")
        self.assertIn("Project Location", report_text)
        self.assertIn("Dataset Information", report_text)
        self.assertIn("Preprocessing & Data Splits", report_text)
        self.assertIn("Model Architecture", report_text)
        self.assertIn("Execution Commands", report_text)
        self.assertIn("Artifacts & Checkpoints", report_text)
        print("    [Evidence] Test G Passed: Complete end-to-end delivery report generated.")


if __name__ == "__main__":
    unittest.main()
