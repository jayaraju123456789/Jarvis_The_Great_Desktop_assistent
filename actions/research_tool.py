"""
actions/research_tool.py — Discoverable Research Tool for JARVIS.

Enables JARVIS to conduct structured literature reviews, extract findings from
papers, compare studies, formulate research gaps, and produce validated research papers.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from core.agents.research_agent import research_agent


def research_tool(parameters: Optional[Dict[str, Any]] = None, **kwargs) -> str:
    """Handler for the research_tool action."""
    params = parameters or {}
    action = params.get("action", "generate_paper").lower().strip()
    topic = params.get("topic", "Autonomous AI Agents in Software Engineering")
    guidelines = params.get("guidelines", "")
    sources = params.get("sources", [])
    task_id = params.get("task_id", "DEFAULT")

    if isinstance(sources, str):
        try:
            sources = json.loads(sources)
        except Exception:
            sources = []

    if action == "generate_paper":
        res = research_agent.generate_research_paper(
            topic=topic,
            guidelines=guidelines,
            sources=sources,
            task_id=task_id,
        )

        return (
            f"✅ Research Paper Generated Successfully!\n"
            f"Title: {res['title']}\n"
            f"DOCX Document: {res['docx_path']}\n"
            f"Markdown Draft: {res['markdown_path']}\n"
            f"Validation Report: {res['validation_report']}\n"
            f"Citations Verified: {res['sources_count']}"
        )

    elif action == "add_source":
        src = research_agent.add_source(
            title=params.get("title", ""),
            authors=params.get("authors", ""),
            year=str(params.get("year", "2024")),
            venue=params.get("venue", ""),
            doi_or_url=params.get("doi_or_url", ""),
            summary=params.get("summary", ""),
            key_findings=params.get("key_findings", []),
            limitations=params.get("limitations", []),
        )
        return f"Added source: {src.title} ({src.authors}, {src.year})"

    elif action == "list_sources":
        sources_list = research_agent.load_sources()
        if not sources_list:
            return "No sources currently registered in the /research workspace."
        lines = ["Registered research sources:"]
        for s in sources_list:
            lines.append(f" - [{s.id}] {s.authors} ({s.year}): {s.title}")
        return "\n".join(lines)

    return f"Unknown research action: '{action}'. Available: generate_paper, add_source, list_sources."


TOOL = {
    "name": "research_tool",
    "description": "Performs deep academic and literature research, tracks authentic citations, identifies research gaps, and synthesizes structured research papers (DOCX, Markdown, and validation report). Use whenever the user asks for a research paper, literature review, or scientific investigation.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "generate_paper | add_source | list_sources (default: generate_paper)",
            },
            "topic": {
                "type": "STRING",
                "description": "Research topic (e.g. 'AI-based mental health support systems')",
            },
            "guidelines": {
                "type": "STRING",
                "description": "User-provided guidelines, formatting constraints, or specific focus areas",
            },
            "sources": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT"
                },
                "description": "Optional list of sources [{\"title\": \"...\", \"authors\": \"...\", \"year\": 2024, ...}]",
            },
        },
        "required": ["action", "topic"],
    },
    "handler": research_tool,
}
