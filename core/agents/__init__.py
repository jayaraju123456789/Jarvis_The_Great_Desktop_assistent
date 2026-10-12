"""
core/agents/__init__.py — Central Domain-Specific Specialist Sub-Agents for JARVIS.

All agents share:
- The centralized File Explorer & File System service (core.file_explorer.file_explorer)
- Persistent Task & State Memory (memory.task_database.TaskDatabase)
- The Capability Registry & Process Manager (core.capability_registry, core.process_manager)
"""

from core.file_explorer import file_explorer, FileExplorerService
from core.agents.communication_agent import communication_agent, CommunicationAgent
from core.agents.system_control_agent import system_control_agent, SystemControlAgent
from core.agents.google_workspace_agent import google_workspace_agent, GoogleWorkspaceAgent
from core.agents.document_agent import document_agent, DocumentAgent
from core.agents.research_agent import research_agent, ResearchAgent
from core.agents.creative_agent import creative_agent, CreativeAgent
from core.agents.coding_agent import coding_agent, CodingAgent
from core.agents.system_navigation_agent import system_navigation_agent, SystemNavigationAgent
from core.agents.presentation_agent import presentation_agent, PresentationAgent
from core.agents.skill_learner_agent import skill_learner_agent, SkillLearnerAgent
from core.agents.universal_file_conversion_agent import universal_file_conversion_agent, UniversalFileConversionAgent
from core.ml.ml_agent import ml_agent, MLAgent

__all__ = [
    "file_explorer",
    "FileExplorerService",
    "communication_agent",
    "CommunicationAgent",
    "system_control_agent",
    "SystemControlAgent",
    "google_workspace_agent",
    "GoogleWorkspaceAgent",
    "document_agent",
    "DocumentAgent",
    "research_agent",
    "ResearchAgent",
    "creative_agent",
    "CreativeAgent",
    "coding_agent",
    "CodingAgent",
    "ml_agent",
    "MLAgent",
    "system_navigation_agent",
    "SystemNavigationAgent",
    "presentation_agent",
    "PresentationAgent",
    "skill_learner_agent",
    "SkillLearnerAgent",
    "universal_file_conversion_agent",
    "UniversalFileConversionAgent",
]
