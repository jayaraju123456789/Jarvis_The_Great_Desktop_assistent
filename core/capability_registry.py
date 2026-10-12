"""
core/capability_registry.py — Central Capability Registry & Artifact Router for JARVIS.

Enforces:
1. Capability-based tool lookup (LLM / planner selects from verified capabilities).
2. Artifact Type Detection:
   - Word (.docx) -> document_tool
   - Excel (.xlsx) -> excel_tool
   - CSV (.csv) -> csv_tool
   - PowerPoint (.pptx) -> presentation_tool
   - Google Docs -> google_docs_tool
   - Google Forms -> google_forms_tool
   - Google Sheets -> google_sheets_tool
   - Google Slides -> google_slides_tool
   - PDF -> file_converter / pdf tools
3. Strict execution priority:
   1. Native API
   2. Python Library (openpyxl, csv, python-docx, python-pptx)
   3. Application-specific automation
   4. Windows UI Automation
   5. Browser automation
   6. PyAutoGUI as final fallback ONLY
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


class ArtifactType(str, Enum):
    WORD = "WORD"
    EXCEL = "EXCEL"
    CSV = "CSV"
    PPTX = "PPTX"
    GOOGLE_DOCS = "GOOGLE_DOCS"
    GOOGLE_FORMS = "GOOGLE_FORMS"
    GOOGLE_SHEETS = "GOOGLE_SHEETS"
    GOOGLE_SLIDES = "GOOGLE_SLIDES"
    PDF = "PDF"
    UNKNOWN = "UNKNOWN"


class ToolPriority(int, Enum):
    NATIVE_API = 1
    PYTHON_LIBRARY = 2
    APP_AUTOMATION = 3
    WINDOWS_UI = 4
    BROWSER_AUTOMATION = 5
    PYAUTOGUI_FALLBACK = 6


@dataclass
class CapabilityDef:
    capability: str
    tool_name: str
    action: str
    priority: ToolPriority
    description: str
    parameters_schema: Dict[str, Any]


CAPABILITIES: Dict[str, CapabilityDef] = {
    # ── Excel / Spreadsheet Capabilities ──
    "excel.create": CapabilityDef(
        capability="excel.create",
        tool_name="excel_tool",
        action="create",
        priority=ToolPriority.PYTHON_LIBRARY,
        description="Creates formatted .xlsx spreadsheet with headers, rows, freeze panes, and verification.",
        parameters_schema={"filename": "str", "num_records": "int", "title": "str"},
    ),
    # ── CSV Capabilities ──
    "csv.create": CapabilityDef(
        capability="csv.create",
        tool_name="csv_tool",
        action="create",
        priority=ToolPriority.PYTHON_LIBRARY,
        description="Creates standard CSV file with headers, rows, and assertive verification.",
        parameters_schema={"filename": "str", "num_records": "int"},
    ),
    "csv.read": CapabilityDef(
        capability="csv.read",
        tool_name="csv_tool",
        action="read",
        priority=ToolPriority.PYTHON_LIBRARY,
        description="Reads and inspects CSV records.",
        parameters_schema={"filename": "str"},
    ),
    "csv.convert_to_xlsx": CapabilityDef(
        capability="csv.convert_to_xlsx",
        tool_name="csv_tool",
        action="convert_to_xlsx",
        priority=ToolPriority.PYTHON_LIBRARY,
        description="Converts CSV to Excel workbook (.xlsx).",
        parameters_schema={"filename": "str"},
    ),
    # ── Word / Document Capabilities ──
    "word.create": CapabilityDef(
        capability="word.create",
        tool_name="document_tool",
        action="create",
        priority=ToolPriority.PYTHON_LIBRARY,
        description="Creates Microsoft Word (.docx) document with styled headings, sections, and embedded images.",
        parameters_schema={"title": "str", "filename": "str", "content": "str"},
    ),
    # ── PowerPoint Capabilities ──
    "powerpoint.create": CapabilityDef(
        capability="powerpoint.create",
        tool_name="presentation_tool",
        action="create",
        priority=ToolPriority.PYTHON_LIBRARY,
        description="Creates Microsoft PowerPoint (.pptx) presentation.",
        parameters_schema={"title": "str", "content": "str"},
    ),
    # ── Google Docs Capabilities ──
    "google_docs.create": CapabilityDef(
        capability="google_docs.create",
        tool_name="google_docs_tool",
        action="create",
        priority=ToolPriority.NATIVE_API,
        description="Creates online Google Doc via Google Docs API v1.",
        parameters_schema={"title": "str", "content": "str"},
    ),
    "google_docs.read": CapabilityDef(
        capability="google_docs.read",
        tool_name="google_docs_tool",
        action="read",
        priority=ToolPriority.NATIVE_API,
        description="Reads Google Doc via Docs API.",
        parameters_schema={"document_id": "str"},
    ),
    # ── Google Forms Capabilities ──
    "google_forms.create": CapabilityDef(
        capability="google_forms.create",
        tool_name="google_forms_tool",
        action="create",
        priority=ToolPriority.NATIVE_API,
        description="Creates online Google Form via Google Forms API v1 with structured questions.",
        parameters_schema={"title": "str", "description": "str", "questions": "list"},
    ),
    # ── Google Sheets Capabilities ──
    "google_sheets.create": CapabilityDef(
        capability="google_sheets.create",
        tool_name="google_sheets_tool",
        action="create",
        priority=ToolPriority.NATIVE_API,
        description="Creates online Google Sheet via Google Sheets API v4.",
        parameters_schema={"title": "str", "num_records": "int"},
    ),
    # ── Google Slides Capabilities ──
    "google_slides.create": CapabilityDef(
        capability="google_slides.create",
        tool_name="google_slides_tool",
        action="create",
        priority=ToolPriority.NATIVE_API,
        description="Creates online Google Slides presentation via Google Slides API v1.",
        parameters_schema={"title": "str", "num_slides": "int"},
    ),
    # ── Google Drive Capabilities ──
    "google_drive.search": CapabilityDef(
        capability="google_drive.search",
        tool_name="google_drive_tool",
        action="search",
        priority=ToolPriority.NATIVE_API,
        description="Searches files and folders in Google Drive.",
        parameters_schema={"query": "str"},
    ),
    "google_drive.upload": CapabilityDef(
        capability="google_drive.upload",
        tool_name="google_drive_tool",
        action="upload",
        priority=ToolPriority.NATIVE_API,
        description="Uploads local file to Google Drive.",
        parameters_schema={"file_path": "str"},
    ),
    # ── Gmail / Email Capabilities ──
    "email.send": CapabilityDef(
        capability="email.send",
        tool_name="gmail_tool",
        action="send_email",
        priority=ToolPriority.NATIVE_API,
        description="Sends email with optional attachment via Gmail API v1.",
        parameters_schema={"to": "str", "subject": "str", "body": "str", "attachment_path": "str"},
    ),
    "email.monitor": CapabilityDef(
        capability="email.monitor",
        tool_name="gmail_tool",
        action="search_emails",
        priority=ToolPriority.NATIVE_API,
        description="Searches / monitors unread emails in Gmail.",
        parameters_schema={"query": "str"},
    ),
    # ── WhatsApp / Messaging Capabilities ──
    "whatsapp.send_message": CapabilityDef(
        capability="whatsapp.send_message",
        tool_name="send_message",
        action="send",
        priority=ToolPriority.APP_AUTOMATION,
        description="Dispatches text message or attachment via WhatsApp with duplicate protection.",
        parameters_schema={"receiver": "str", "message_text": "str", "attachment_path": "str"},
    ),
    "whatsapp.voice_message": CapabilityDef(
        capability="whatsapp.voice_message",
        tool_name="send_message",
        action="voice_message",
        priority=ToolPriority.APP_AUTOMATION,
        description="Synthesizes or records voice memo and delivers genuine .wav note to WhatsApp recipient.",
        parameters_schema={"receiver": "str", "voice_text": "str", "from_mic": "bool", "duration": "float"},
    ),
    "whatsapp.send_file": CapabilityDef(
        capability="whatsapp.send_file",
        tool_name="send_message",
        action="send_file",
        priority=ToolPriority.APP_AUTOMATION,
        description="Dispatches document or file attachment (PDF, DOCX, XLSX, PPTX, CSV, images) to one or more recipients via WhatsApp.",
        parameters_schema={"receiver": "str", "file_path": "str", "file_query": "str", "message_text": "str"},
    ),
    "whatsapp.start_call": CapabilityDef(
        capability="whatsapp.start_call",
        tool_name="whatsapp_calling",
        action="start_call",
        priority=ToolPriority.APP_AUTOMATION,
        description="Initiates verified audio or video call to contact on WhatsApp Desktop.",
        parameters_schema={"receiver": "str", "call_type": "str", "account": "str"},
    ),
    "whatsapp.monitor_call": CapabilityDef(
        capability="whatsapp.monitor_call",
        tool_name="whatsapp_calling",
        action="monitor_call",
        priority=ToolPriority.APP_AUTOMATION,
        description="Supervises active WhatsApp call lifecycle, enforcing state machine and max duration limits.",
        parameters_schema={"receiver": "str", "call_type": "str", "max_duration_seconds": "float"},
    ),
    "whatsapp.end_call": CapabilityDef(
        capability="whatsapp.end_call",
        tool_name="whatsapp_calling",
        action="end_call",
        priority=ToolPriority.APP_AUTOMATION,
        description="Safely terminates active WhatsApp call while protecting unrelated windows.",
        parameters_schema={},
    ),
    "whatsapp.call_status": CapabilityDef(
        capability="whatsapp.call_status",
        tool_name="whatsapp_calling",
        action="status",
        priority=ToolPriority.APP_AUTOMATION,
        description="Checks status of active WhatsApp call (IDLE, CALLING, RINGING, CONNECTED, ENDED).",
        parameters_schema={},
    ),
    "whatsapp.detect_incoming_call": CapabilityDef(
        capability="whatsapp.detect_incoming_call",
        tool_name="whatsapp_calling",
        action="detect_incoming",
        priority=ToolPriority.APP_AUTOMATION,
        description="Detects incoming WhatsApp call ringing or notifying on desktop and identifies caller.",
        parameters_schema={},
    ),
    "whatsapp.respond_incoming_call": CapabilityDef(
        capability="whatsapp.respond_incoming_call",
        tool_name="whatsapp_calling",
        action="respond_incoming",
        priority=ToolPriority.APP_AUTOMATION,
        description="Responds to incoming WhatsApp call ('accept', 'decline', 'ignore').",
        parameters_schema={"action": "str"},
    ),
    "whatsapp.record_missed_call": CapabilityDef(
        capability="whatsapp.record_missed_call",
        tool_name="whatsapp_calling",
        action="record_missed",
        priority=ToolPriority.APP_AUTOMATION,
        description="Persists missed call event into storage log.",
        parameters_schema={"caller": "str", "call_type": "str", "notes": "str"},
    ),
    "whatsapp.get_missed_calls": CapabilityDef(
        capability="whatsapp.get_missed_calls",
        tool_name="whatsapp_calling",
        action="get_missed",
        priority=ToolPriority.APP_AUTOMATION,
        description="Queries recorded missed calls and response states.",
        parameters_schema={"unresponded_only": "bool"},
    ),
    "whatsapp.send_authorized_reply": CapabilityDef(
        capability="whatsapp.send_authorized_reply",
        tool_name="whatsapp_calling",
        action="authorized_reply",
        priority=ToolPriority.APP_AUTOMATION,
        description="Sends user-authorized reply to caller without hallucinating or inventing text.",
        parameters_schema={"receiver": "str", "reply_text": "str"},
    ),
    "whatsapp.busy_config": CapabilityDef(
        capability="whatsapp.busy_config",
        tool_name="whatsapp_calling",
        action="busy_config",
        priority=ToolPriority.APP_AUTOMATION,
        description="Queries or configures WhatsApp busy-time schedule and auto-reply preferences.",
        parameters_schema={"action": "str", "auto_reply_enabled": "bool", "busy_reply_message": "str"},
    ),
    "whatsapp.process_missed_call": CapabilityDef(
        capability="whatsapp.process_missed_call",
        tool_name="whatsapp_calling",
        action="process_missed",
        priority=ToolPriority.APP_AUTOMATION,
        description="Processes a missed call through idempotency, schedule validation, auto-reply, and follow-up.",
        parameters_schema={"caller": "str", "call_type": "str", "force_auto_reply": "bool"},
    ),
    "whatsapp.call_monitor": CapabilityDef(
        capability="whatsapp.call_monitor",
        tool_name="whatsapp_calling",
        action="call_monitor",
        priority=ToolPriority.APP_AUTOMATION,
        description="Controls background observer for WhatsApp incoming, ringing, and missed calls.",
        parameters_schema={"action": "str"},
    ),
    # ── Shared File Explorer Capabilities ──
    "file_explorer.search": CapabilityDef(
        capability="file_explorer.search",
        tool_name="file_controller",
        action="find",
        priority=ToolPriority.PYTHON_LIBRARY,
        description="Searches files across user directories by query, extension, type, dates, sizes, or content.",
        parameters_schema={"name": "str", "extension": "str", "path": "str"},
    ),
    "file_explorer.list": CapabilityDef(
        capability="file_explorer.list",
        tool_name="file_controller",
        action="list",
        priority=ToolPriority.PYTHON_LIBRARY,
        description="Lists directory entries with comprehensive file metadata.",
        parameters_schema={"path": "str"},
    ),
    "file_explorer.create": CapabilityDef(
        capability="file_explorer.create",
        tool_name="file_controller",
        action="create_file",
        priority=ToolPriority.PYTHON_LIBRARY,
        description="Creates file on filesystem and asserts its byte existence.",
        parameters_schema={"path": "str", "content": "str"},
    ),
    # ── System Control Capabilities ──
    "system_control.volume": CapabilityDef(
        capability="system_control.volume",
        tool_name="computer_settings",
        action="volume",
        priority=ToolPriority.NATIVE_API,
        description="Controls master speaker volume level and mute state.",
        parameters_schema={"setting": "str", "value": "int"},
    ),
    "system_control.brightness": CapabilityDef(
        capability="system_control.brightness",
        tool_name="computer_settings",
        action="brightness",
        priority=ToolPriority.NATIVE_API,
        description="Controls monitor display brightness.",
        parameters_schema={"setting": "str", "value": "int"},
    ),
    "system_control.diagnostics": CapabilityDef(
        capability="system_control.diagnostics",
        tool_name="computer_settings",
        action="battery",
        priority=ToolPriority.NATIVE_API,
        description="Inspects CPU, RAM, Disk, and battery diagnostics.",
        parameters_schema={"setting": "str"},
    ),
    # ── Creative & Diagram Capabilities ──
    "creative.flowchart": CapabilityDef(
        capability="creative.flowchart",
        tool_name="drawing_tool",
        action="draw",
        priority=ToolPriority.PYTHON_LIBRARY,
        description="Generates deterministic high-resolution flowchart image and launches in Paint.",
        parameters_schema={"shape": "str", "title": "str", "steps": "list"},
    ),
    "creative.architecture": CapabilityDef(
        capability="creative.architecture",
        tool_name="drawing_tool",
        action="draw",
        priority=ToolPriority.PYTHON_LIBRARY,
        description="Generates multi-tier system architecture diagram.",
        parameters_schema={"shape": "str", "title": "str", "components": "list"},
    ),
    "creative.professional_pencil_sketch": CapabilityDef(
        capability="creative.professional_pencil_sketch",
        tool_name="drawing_tool",
        action="draw",
        priority=ToolPriority.PYTHON_LIBRARY,
        description="Generates professional human-like pencil sketches with accurate contours and realistic graphite shading.",
        parameters_schema={"style": "str", "profile": "str", "image_path": "str", "open_in_paint": "bool"},
    ),
    # ── Research Capabilities ──
    "research.prisma_review": CapabilityDef(
        capability="research.prisma_review",
        tool_name="research_tool",
        action="prisma_review",
        priority=ToolPriority.PYTHON_LIBRARY,
        description="Executes PRISMA 2020 14-step systematic literature review workflow.",
        parameters_schema={"research_question": "str"},
    ),
    # ── Desktop Control Capabilities ──
    "desktop.open_app": CapabilityDef(
        capability="desktop.open_app",
        tool_name="open_app",
        action="open",
        priority=ToolPriority.APP_AUTOMATION,
        description="Opens desktop application or brings existing instance to foreground with readiness verification.",
        parameters_schema={"app_name": "str", "reuse_existing": "bool"},
    ),
    "desktop.close_app": CapabilityDef(
        capability="desktop.close_app",
        tool_name="open_app",
        action="close",
        priority=ToolPriority.APP_AUTOMATION,
        description="Gracefully closes desktop application with unsaved document detection.",
        parameters_schema={"app_name": "str", "force": "bool", "save_if_prompted": "bool"},
    ),
    "desktop.focus_window": CapabilityDef(
        capability="desktop.focus_window",
        tool_name="system_navigation_agent",
        action="switch_to_window",
        priority=ToolPriority.WINDOWS_UI,
        description="Brings specified application window to foreground safely with thread-attachment.",
        parameters_schema={"window_title": "str"},
    ),
    "desktop.minimize_window": CapabilityDef(
        capability="desktop.minimize_window",
        tool_name="system_navigation_agent",
        action="minimize_application",
        priority=ToolPriority.WINDOWS_UI,
        description="Minimizes target application window safely.",
        parameters_schema={"app_name": "str"},
    ),
    "desktop.restore_window": CapabilityDef(
        capability="desktop.restore_window",
        tool_name="system_navigation_agent",
        action="restore_application",
        priority=ToolPriority.WINDOWS_UI,
        description="Restores minimized target application window safely.",
        parameters_schema={"app_name": "str"},
    ),
    "desktop.get_state": CapabilityDef(
        capability="desktop.get_state",
        tool_name="system_navigation_agent",
        action="get_application_state",
        priority=ToolPriority.WINDOWS_UI,
        description="Inspects window readiness, responsiveness, modal dialogs, and visibility.",
        parameters_schema={"app_name": "str"},
    ),
    "desktop.set_text": CapabilityDef(
        capability="desktop.set_text",
        tool_name="system_navigation_agent",
        action="type_into_window",
        priority=ToolPriority.WINDOWS_UI,
        description="Enters text into specific accessible UI control and verifies content.",
        parameters_schema={"app_name": "str", "text": "str", "control_name": "str", "auto_id": "str"},
    ),
    "desktop.click_control": CapabilityDef(
        capability="desktop.click_control",
        tool_name="system_navigation_agent",
        action="click_control",
        priority=ToolPriority.WINDOWS_UI,
        description="Clicks accessible button, menu, or control via Windows UI Automation.",
        parameters_schema={"app_name": "str", "control_name": "str", "auto_id": "str"},
    ),
    "desktop.get_text": CapabilityDef(
        capability="desktop.get_text",
        tool_name="system_navigation_agent",
        action="get_control_text",
        priority=ToolPriority.WINDOWS_UI,
        description="Reads current text or value from accessible control within target window.",
        parameters_schema={"app_name": "str", "control_name": "str", "auto_id": "str"},
    ),
    # ── Universal File Conversion & Compression Capabilities ──
    "conversion.convert": CapabilityDef(
        capability="conversion.convert",
        tool_name="convert_file",
        action="convert",
        priority=ToolPriority.PYTHON_LIBRARY,
        description="Converts documents, spreadsheets, presentations, images, audio, and video authentically.",
        parameters_schema={"input_file": "str", "target_format": "str", "output_path": "str"},
    ),
    "conversion.docx_to_pdf": CapabilityDef(
        capability="conversion.docx_to_pdf",
        tool_name="convert_file",
        action="convert_docx_to_pdf",
        priority=ToolPriority.APP_AUTOMATION,
        description="Converts Microsoft Word (.docx) to PDF with authentic layout preservation and assertive verification.",
        parameters_schema={"input_file": "str", "output_path": "str"},
    ),
    "conversion.pdf_to_docx": CapabilityDef(
        capability="conversion.pdf_to_docx",
        tool_name="convert_file",
        action="convert_pdf_to_docx",
        priority=ToolPriority.APP_AUTOMATION,
        description="Converts PDF documents into editable Microsoft Word (.docx) files.",
        parameters_schema={"input_file": "str", "output_path": "str"},
    ),
    "conversion.pdf_to_pptx": CapabilityDef(
        capability="conversion.pdf_to_pptx",
        tool_name="convert_file",
        action="convert_pdf_to_pptx",
        priority=ToolPriority.PYTHON_LIBRARY,
        description="Converts PDF pages into PowerPoint presentation slides (page-faithful or editable modes).",
        parameters_schema={"input_file": "str", "mode": "str", "output_path": "str"},
    ),
    "conversion.images_to_pdf": CapabilityDef(
        capability="conversion.images_to_pdf",
        tool_name="convert_file",
        action="convert_images_to_pdf",
        priority=ToolPriority.PYTHON_LIBRARY,
        description="Compiles one or multiple images into a clean, formatted PDF document.",
        parameters_schema={"image_paths": "list", "output_path": "str", "page_size": "str"},
    ),
    "conversion.images_to_pptx": CapabilityDef(
        capability="conversion.images_to_pptx",
        tool_name="convert_file",
        action="convert_images_to_pptx",
        priority=ToolPriority.PYTHON_LIBRARY,
        description="Creates PowerPoint presentation (.pptx) from images in full-image or presentation layout mode.",
        parameters_schema={"image_paths": "list", "output_path": "str", "mode": "str"},
    ),
    "conversion.video_compress": CapabilityDef(
        capability="conversion.video_compress",
        tool_name="convert_file",
        action="compress_video",
        priority=ToolPriority.PYTHON_LIBRARY,
        description="Compresses video authentically using FFmpeg with balanced, high quality, max, or target size presets.",
        parameters_schema={"input_file": "str", "mode": "str", "target_size_mb": "float", "output_path": "str"},
    ),
    "conversion.file_compress": CapabilityDef(
        capability="conversion.file_compress",
        tool_name="convert_file",
        action="compress_file",
        priority=ToolPriority.PYTHON_LIBRARY,
        description="Compresses Office documents, images, or ZIP archives with assertive integrity verification.",
        parameters_schema={"input_file": "str", "output_path": "str"},
    ),
    # ── Autonomous Coding Capabilities ──
    "coding.develop": CapabilityDef(
        capability="coding.develop",
        tool_name="coding_agent",
        action="develop_full_stack_project",
        priority=ToolPriority.PYTHON_LIBRARY,
        description="Autonomous full-stack application development lifecycle with specialist agents, testing, and delivery reports.",
        parameters_schema={"name": "str", "requirement": "str"},
    ),
    "coding.research": CapabilityDef(
        capability="coding.research",
        tool_name="coding_agent",
        action="research_github",
        priority=ToolPriority.PYTHON_LIBRARY,
        description="Searches, statically inspects, and compares open-source GitHub repositories.",
        parameters_schema={"query": "str", "language": "str"},
    ),
    "coding.modify": CapabilityDef(
        capability="coding.modify",
        tool_name="coding_agent",
        action="modify_and_test_project",
        priority=ToolPriority.PYTHON_LIBRARY,
        description="Analyzes existing codebase, diagnoses root cause, applies surgical edits, and runs tests.",
        parameters_schema={"project_path": "str", "file_modifications": "dict", "test_command": "str"},
    ),
    # ── Machine Learning & Deep Learning Capabilities ──
    "ml.project": CapabilityDef(
        capability="ml.project",
        tool_name="coding_agent",
        action="train_ml_project",
        priority=ToolPriority.PYTHON_LIBRARY,
        description="Autonomous Machine Learning & Deep Learning project creation, dataset verification, training, and evaluation.",
        parameters_schema={"name": "str", "requirement": "str", "custom_dataset_path": "str"},
    ),
}


class CapabilityRegistry:
    """Manages tool selection by declared capabilities and artifact intent."""

    @staticmethod
    def get_capability(name: str) -> Optional[CapabilityDef]:
        return CAPABILITIES.get(name)

    @staticmethod
    def detect_artifact_type(request: str) -> ArtifactType:
        """Analyze user query and identify the exact artifact requested."""
        low = request.lower()

        # Google Forms (Must precede generic checks)
        if any(w in low for w in ("google form", "google forms", "gform", "create a form on google", "google questionnaire")):
            return ArtifactType.GOOGLE_FORMS

        # Google Docs (Must precede generic doc checks)
        if any(w in low for w in ("google doc", "google document", "gdoc", "google docs")):
            return ArtifactType.GOOGLE_DOCS

        # Google Sheets (Must precede generic sheet/excel checks)
        if any(w in low for w in ("google sheet", "google sheets", "gsheet")):
            return ArtifactType.GOOGLE_SHEETS

        # Google Slides (Must precede generic presentation checks)
        if any(w in low for w in ("google slide", "google slides", "gslides")):
            return ArtifactType.GOOGLE_SLIDES

        # CSV (Must precede Excel / generic spreadsheet checks)
        if any(w in low for w in ("csv", ".csv", "comma separated")):
            return ArtifactType.CSV

        # Excel
        if any(w in low for w in ("excel", "xlsx", "xls", "excel sheet", "excel file", "excel dataset")):
            return ArtifactType.EXCEL

        # PowerPoint
        if any(w in low for w in ("powerpoint", "pptx", "ppt", "presentation", "slides", "slide deck")):
            return ArtifactType.PPTX

        # Word
        if any(w in low for w in ("word document", "docx", ".doc", "doc file", "create a document", "write a document", "word file")):
            return ArtifactType.WORD

        # PDF
        if "pdf" in low or ".pdf" in low:
            return ArtifactType.PDF

        return ArtifactType.UNKNOWN

    @staticmethod
    def _extract_topic(request: str, default: str) -> str:
        """Helper to extract topic dynamically from natural language query."""
        m_top = re.search(r"(?:about|on|titled|for|regarding|named|with)\s+['\"]?([^'\",\.]+)['\"]?", request, re.IGNORECASE)
        if m_top:
            cand = m_top.group(1).strip()
            # Filter out non-topic qualifiers
            if len(cand) > 2 and cand.lower() not in ("save", "desktop", "please", "me", "a"):
                return cand.title()
        return default

    @staticmethod
    def route_artifact_creation(request: str) -> Optional[Tuple[str, str, Dict[str, Any]]]:
        """
        Route request to (tool_name, action, parameters).
        Returns None if not an artifact creation request.
        """
        artifact = CapabilityRegistry.detect_artifact_type(request)

        # 1. EXCEL
        if artifact == ArtifactType.EXCEL:
            m_wc = re.search(r"(\d[\d,]*)\s*(?:records?|patients?|rows?)\b", request, re.IGNORECASE)
            num_recs = int(m_wc.group(1).replace(",", "")) if m_wc else 1000
            title = CapabilityRegistry._extract_topic(request, "Financial and Analytics Dataset")
            fname_slug = re.sub(r"[^a-zA-Z0-9]+", "_", title.lower()).strip("_") or "dataset"
            filename = f"{fname_slug}.xlsx"
            return (
                "excel_tool",
                "create",
                {"filename": filename, "num_records": num_recs, "title": title},
            )

        # 2. CSV
        if artifact == ArtifactType.CSV:
            m_wc = re.search(r"(\d[\d,]*)\s*(?:records?|patients?|rows?)\b", request, re.IGNORECASE)
            num_recs = int(m_wc.group(1).replace(",", "")) if m_wc else 1000
            title = CapabilityRegistry._extract_topic(request, "Export Data")
            fname_slug = re.sub(r"[^a-zA-Z0-9]+", "_", title.lower()).strip("_") or "dataset"
            filename = f"{fname_slug}.csv"
            return (
                "csv_tool",
                "create",
                {"filename": filename, "num_records": num_recs},
            )

        # 3. GOOGLE FORMS
        if artifact == ArtifactType.GOOGLE_FORMS:
            title = CapabilityRegistry._extract_topic(request, "Autonomous Feedback and Registration Form")
            return (
                "google_forms_tool",
                "create",
                {
                    "title": title,
                    "description": f"Form for {title} created autonomously by JARVIS via official Google Forms API.",
                },
            )

        # 4. GOOGLE DOCS
        if artifact == ArtifactType.GOOGLE_DOCS:
            title = CapabilityRegistry._extract_topic(request, "Executive Research Notes")
            return (
                "google_docs_tool",
                "create",
                {"title": title, "content": f"# {title}\n\nGenerated autonomously by JARVIS via Google Docs API.\n"},
            )

        # 5. GOOGLE SHEETS
        if artifact == ArtifactType.GOOGLE_SHEETS:
            m_wc = re.search(r"(\d[\d,]*)\s*(?:records?|patients?|rows?)\b", request, re.IGNORECASE)
            num_recs = int(m_wc.group(1).replace(",", "")) if m_wc else 1000
            title = CapabilityRegistry._extract_topic(request, "Business Performance Sheet")
            return (
                "google_sheets_tool",
                "create",
                {"title": title, "num_records": num_recs},
            )

        # 6. GOOGLE SLIDES
        if artifact == ArtifactType.GOOGLE_SLIDES:
            m_sl = re.search(r"(\d+)\s*(?:slides?|slide)\b", request, re.IGNORECASE)
            num_slides = int(m_sl.group(1)) if m_sl else 5
            title = CapabilityRegistry._extract_topic(request, "Technical Architecture Presentation")
            return (
                "google_slides_tool",
                "create",
                {"title": title, "num_slides": num_slides},
            )

        return None
