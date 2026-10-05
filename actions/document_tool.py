"""
actions/document_tool.py — Discoverable Word / Document Generation Tool for JARVIS.

Allows JARVIS to generate professional Microsoft Word (.docx) documents with
headings, tables, callout boxes, and references, and open them in Microsoft Word.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.agents.document_agent import document_agent


def document_tool(parameters: Optional[Dict[str, Any]] = None, **kwargs) -> str:
    """Handler for the document_tool action."""
    params = parameters or {}
    action = params.get("action", "create").lower().strip()
    title = params.get("title", "Untitled Document")
    subtitle = params.get("subtitle", "")
    filename = params.get("filename")
    open_in_word = bool(params.get("open_in_word", True))
    task_id = params.get("task_id", "DEFAULT")

    # Sections can be provided as a list of dicts or a JSON string
    raw_sections = params.get("sections", [])
    if isinstance(raw_sections, str):
        try:
            sections = json.loads(raw_sections)
        except Exception:
            # Fall back to a single paragraph
            sections = [{"type": "paragraph", "text": raw_sections}]
    elif isinstance(raw_sections, list):
        sections = raw_sections
    else:
        sections = []

    # If simple content was provided instead of structured sections:
    content = params.get("content")
    if not sections and content:
        # Split into headings and paragraphs if markdown-like
        parsed_sections = []
        for block in content.split("\n\n"):
            block = block.strip()
            if not block:
                continue
            if block.startswith("# "):
                parsed_sections.append({"type": "heading", "level": 1, "text": block[2:].strip()})
            elif block.startswith("## "):
                parsed_sections.append({"type": "heading", "level": 2, "text": block[3:].strip()})
            elif block.startswith("### "):
                parsed_sections.append({"type": "heading", "level": 3, "text": block[4:].strip()})
            elif block.startswith("- ") or block.startswith("* "):
                items = [line.lstrip("-* ").strip() for line in block.splitlines() if line.strip()]
                parsed_sections.append({"type": "bullet_list", "items": items})
            else:
                parsed_sections.append({"type": "paragraph", "text": block})
        sections = parsed_sections

    if action in ("create", "write"):
        if not sections:
            return "Error: No content or sections provided for document creation."

        res = document_agent.create_document(
            title=title,
            subtitle=subtitle,
            sections=sections,
            filename=filename,
            open_in_word=open_in_word,
            task_id=task_id,
        )

        out_lines = [
            f"✅ Document successfully created!",
            f"File: {res['file_path']}",
            f"Size: {res['size_bytes']:,} bytes",
            f"Verification: {res['verification']}",
        ]
        if res["opened_in_viewer"]:
            out_lines.append("Opened in Word / default viewer for the user.")
        return "\n".join(out_lines)

    return f"Unknown document action: '{action}'. Available: create."


TOOL = {
    "name": "document_tool",
    "description": "Creates professional Microsoft Word (.docx) documents with headings, paragraphs, formatted bullet lists, comparison tables, and references. Automatically saves to disk and can open in Word. Use whenever the user asks to write a document, paper, essay, report, or Word document.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "create (default)",
            },
            "title": {
                "type": "STRING",
                "description": "Document title (e.g. 'Introduction to Diabetic Retinopathy')",
            },
            "subtitle": {
                "type": "STRING",
                "description": "Optional subtitle or topic summary",
            },
            "filename": {
                "type": "STRING",
                "description": "Target filename ending in .docx (e.g. 'diabetic_retinopathy.docx')",
            },
            "content": {
                "type": "STRING",
                "description": "Text content with markdown headings (#, ##), paragraphs, and bullet points",
            },
            "sections": {
                "type": "ARRAY",
                "description": "Structured sections: [{\"type\": \"heading\"|\"paragraph\"|\"table\"|\"bullet_list\"|\"callout\"|\"references\", ...}]",
            },
            "open_in_word": {
                "type": "BOOLEAN",
                "description": "Whether to launch the created document in Microsoft Word / system viewer (default: true)",
            },
        },
        "required": ["title"],
    },
    "handler": document_tool,
}
