"""
core/agents/document_agent.py — Professional Word / Document Generator for JARVIS.

Builds high-quality Microsoft Word (.docx) documents with:
- Standard typographic hierarchy (Title, Subtitle, Heading 1–4)
- Formatted paragraphs, lead intros, and callout callouts
- Styled comparison and data tables
- Numbered and bulleted lists
- Academic references and citations section
- Automated verification of created files
- Optional OS launch into Microsoft Word / system viewer
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import docx
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement, parse_xml
    from docx.oxml.ns import nsdecls, qn
    from docx.shared import Inches, Pt, RGBColor
    _DOCX_AVAILABLE = True
except ImportError:
    _DOCX_AVAILABLE = False

from core.logger import log_event
from core.process_manager import process_manager

_OS = platform.system()


def _set_cell_background(cell, fill_hex: str):
    """Set background color of a table cell."""
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tc_pr.append(shd)


def _set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """Set padding in a table cell (in twips, 1/20th of a pt)."""
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tc_pr.append(tc_mar)


class DocumentAgent:
    """Creates and manages Microsoft Word (.docx) documents."""

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or (Path.home() / "Desktop" / "JarvisDocuments")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def create_document(
        self,
        title: str,
        sections: List[Dict[str, Any]],
        filename: Optional[str] = None,
        subtitle: str = "",
        author: str = "JARVIS Autonomous Agent",
        open_in_word: bool = False,
        task_id: str = "DEFAULT",
    ) -> Dict[str, Any]:
        """
        Create a rich Word document.
        sections format:
        [
          {"type": "heading", "level": 1, "text": "Introduction"},
          {"type": "paragraph", "text": "This is a detailed paragraph..."},
          {"type": "callout", "title": "Key Finding", "text": "Important takeaway..."},
          {"type": "bullet_list", "items": ["Item 1", "Item 2"]},
          {"type": "table", "headers": ["Model", "Accuracy"], "rows": [["GPT-4", "92%"], ["Gemini", "94%"]]},
          {"type": "references", "items": ["Smith et al. (2025)...", "Johnson (2024)..."]}
        ]
        """
        if not _DOCX_AVAILABLE:
            raise RuntimeError("python-docx is not installed. Please install with: pip install python-docx")

        start_time = datetime.now()
        safe_name = filename or f"{title.lower().replace(' ', '_')[:40]}.docx"
        if not safe_name.endswith(".docx"):
            safe_name += ".docx"
        file_path = self.output_dir / safe_name

        doc = Document()

        # Page setup: Standard Letter, 1 inch margins
        sections_obj = doc.sections
        for s in sections_obj:
            s.top_margin = Inches(1.0)
            s.bottom_margin = Inches(1.0)
            s.left_margin = Inches(1.0)
            s.right_margin = Inches(1.0)

        # Style configuration
        normal_style = doc.styles["Normal"]
        normal_font = normal_style.font
        normal_font.name = "Calibri"
        normal_font.size = Pt(11)
        normal_font.color.rgb = RGBColor(0x22, 0x22, 0x22)

        # Title
        p_title = doc.add_paragraph()
        p_title.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p_title.paragraph_format.space_before = Pt(0)
        p_title.paragraph_format.space_after = Pt(4)
        run_title = p_title.add_run(title)
        run_title.font.name = "Segoe UI"
        run_title.font.size = Pt(26)
        run_title.font.bold = True
        run_title.font.color.rgb = RGBColor(0x0F, 0x3D, 0x6E)  # Deep Navy

        # Subtitle
        if subtitle:
            p_sub = doc.add_paragraph()
            p_sub.paragraph_format.space_after = Pt(12)
            run_sub = p_sub.add_run(subtitle)
            run_sub.font.name = "Calibri"
            run_sub.font.size = Pt(13)
            run_sub.font.italic = True
            run_sub.font.color.rgb = RGBColor(0x55, 0x66, 0x77)

        # Metadata Header (Author, Date)
        p_meta = doc.add_paragraph()
        p_meta.paragraph_format.space_after = Pt(24)
        run_meta = p_meta.add_run(f"Author: {author}  |  Generated: {datetime.now().strftime('%B %d, %Y')}")
        run_meta.font.size = Pt(9.5)
        run_meta.font.color.rgb = RGBColor(0x77, 0x88, 0x99)

        # Process each section
        for sec in sections:
            stype = sec.get("type", "paragraph")

            if stype == "heading":
                lvl = int(sec.get("level", 1))
                h = doc.add_heading(sec.get("text", ""), level=lvl)
                h.paragraph_format.keep_with_next = True
                h.paragraph_format.space_before = Pt(16 if lvl == 1 else 10)
                h.paragraph_format.space_after = Pt(6)
                if h.runs:
                    h.runs[0].font.name = "Segoe UI"
                    h.runs[0].font.color.rgb = RGBColor(0x1B, 0x36, 0x5D) if lvl == 1 else RGBColor(0x2E, 0x5B, 0x88)

            elif stype == "paragraph":
                p = doc.add_paragraph()
                p.paragraph_format.space_after = Pt(8)
                p.paragraph_format.line_spacing = 1.15
                text = sec.get("text", "")
                # Handle basic inline bolding if specified
                p.add_run(text)

            elif stype == "bullet_list":
                items = sec.get("items", [])
                for item in items:
                    bp = doc.add_paragraph(style="List Bullet")
                    bp.paragraph_format.space_after = Pt(3)
                    bp.add_run(str(item))

            elif stype == "numbered_list":
                items = sec.get("items", [])
                for item in items:
                    np = doc.add_paragraph(style="List Number")
                    np.paragraph_format.space_after = Pt(3)
                    np.add_run(str(item))

            elif stype == "callout":
                # Rendered as a single-cell highlighted card
                table = doc.add_table(rows=1, cols=1)
                table.alignment = WD_TABLE_ALIGNMENT.CENTER
                cell = table.cell(0, 0)
                _set_cell_background(cell, "F0F4F8")  # Soft ice blue
                _set_cell_margins(cell, top=140, bottom=140, left=200, right=200)

                cp = cell.paragraphs[0]
                cp.paragraph_format.space_after = Pt(4)
                if sec.get("title"):
                    tr = cp.add_run(f"📌 {sec['title']}\n")
                    tr.font.bold = True
                    tr.font.color.rgb = RGBColor(0x0F, 0x3D, 0x6E)
                body_run = cp.add_run(sec.get("text", ""))
                body_run.font.italic = True
                body_run.font.size = Pt(10)

                doc.add_paragraph().paragraph_format.space_after = Pt(6)

            elif stype == "table":
                headers = sec.get("headers", [])
                rows = sec.get("rows", [])
                if headers or rows:
                    tbl = doc.add_table(rows=1 if headers else 0, cols=len(headers) if headers else len(rows[0]))
                    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
                    tbl.style = "Table Grid"

                    if headers:
                        hdr_cells = tbl.rows[0].cells
                        for i, h_text in enumerate(headers):
                            hdr_cells[i].text = str(h_text)
                            _set_cell_background(hdr_cells[i], "1B365D")  # Dark Blue
                            _set_cell_margins(hdr_cells[i], top=100, bottom=100, left=120, right=120)
                            p = hdr_cells[i].paragraphs[0]
                            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                            if p.runs:
                                p.runs[0].font.bold = True
                                p.runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

                    for r_idx, row_data in enumerate(rows):
                        row_cells = tbl.add_row().cells
                        bg_col = "F9FBFC" if r_idx % 2 == 1 else "FFFFFF"
                        for c_idx, cell_value in enumerate(row_data):
                            if c_idx < len(row_cells):
                                row_cells[c_idx].text = str(cell_value)
                                _set_cell_background(row_cells[c_idx], bg_col)
                                _set_cell_margins(row_cells[c_idx], top=80, bottom=80, left=120, right=120)

                    doc.add_paragraph().paragraph_format.space_after = Pt(8)

            elif stype == "references":
                h = doc.add_heading("References", level=1)
                h.paragraph_format.space_before = Pt(18)
                h.paragraph_format.space_after = Pt(8)
                for ref in sec.get("items", []):
                    rp = doc.add_paragraph()
                    rp.paragraph_format.left_indent = Inches(0.5)
                    rp.paragraph_format.first_line_indent = Inches(-0.5)  # Hanging indent
                    rp.paragraph_format.space_after = Pt(5)
                    rr = rp.add_run(str(ref))
                    rr.font.size = Pt(9.5)

        # Save document
        doc.save(str(file_path))

        # Verification step
        file_exists = file_path.exists()
        file_size = file_path.stat().st_size if file_exists else 0

        log_event(
            category="agent",
            action=f"create_document: {safe_name}",
            status="SUCCESS" if file_exists else "FAILED",
            task_id=task_id,
            agent="DocumentAgent",
            details={"path": str(file_path), "bytes": file_size},
        )

        opened = False
        if open_in_word and file_exists:
            opened = self.open_in_system_viewer(file_path, task_id=task_id)

        return {
            "success": file_exists,
            "file_path": str(file_path),
            "file_name": safe_name,
            "size_bytes": file_size,
            "opened_in_viewer": opened,
            "verification": f"Verified: Document written and saved to disk ({file_size:,} bytes).",
        }

    def open_in_system_viewer(self, file_path: Path, task_id: str = "DEFAULT") -> bool:
        """Open the generated document in the OS default application (Word / LibreOffice)."""
        try:
            if _OS == "Windows":
                proc = subprocess.Popen(["cmd.exe", "/c", "start", "", str(file_path)], shell=False)
                process_manager.register_process(
                    application="WINWORD",
                    process_id=proc.pid,
                    task_id=task_id,
                    command=f"start {file_path}",
                )
                return True
            elif _OS == "Darwin":
                subprocess.Popen(["open", str(file_path)])
                return True
            else:
                subprocess.Popen(["xdg-open", str(file_path)])
                return True
        except Exception as e:
            print(f"[DocumentAgent] Viewer launch warning: {e}")
            return False


# Global instance
document_agent = DocumentAgent()
