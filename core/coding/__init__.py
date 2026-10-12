"""
core/coding/__init__.py — Central Autonomous Coding Agent Package for JARVIS.
"""

from core.coding.execution_sandbox import (
    ExecutionSandbox,
    GitCheckpoint,
    resolve_real_desktop,
    sanitize_secrets,
    sandbox,
)
from core.coding.project_analyzer import (
    CodebaseOverview,
    ProjectAnalyzer,
    project_analyzer,
)
from core.coding.github_researcher import (
    GitHubResearcher,
    RepoDeepInspection,
    RepoSummary,
    github_researcher,
)
from core.coding.project_memory import (
    StructuredProjectMemory,
    TaskStepRecord,
)
from core.coding.specialist_agents import (
    ArchitecturePlan,
    Architect,
    IntegrationCoordinator,
    RequirementAnalyst,
    RequirementSpec,
    SecurityReviewer,
)
from core.coding.test_debugger import (
    AutonomousTestDebugger,
    VerificationOutcome,
    test_debugger,
)
from core.coding.delivery_reporter import (
    DeliveryReporter,
    delivery_reporter,
)

__all__ = [
    "ExecutionSandbox",
    "GitCheckpoint",
    "resolve_real_desktop",
    "sanitize_secrets",
    "sandbox",
    "CodebaseOverview",
    "ProjectAnalyzer",
    "project_analyzer",
    "GitHubResearcher",
    "RepoDeepInspection",
    "RepoSummary",
    "github_researcher",
    "StructuredProjectMemory",
    "TaskStepRecord",
    "ArchitecturePlan",
    "Architect",
    "IntegrationCoordinator",
    "RequirementAnalyst",
    "RequirementSpec",
    "SecurityReviewer",
    "AutonomousTestDebugger",
    "VerificationOutcome",
    "test_debugger",
    "DeliveryReporter",
    "delivery_reporter",
]
