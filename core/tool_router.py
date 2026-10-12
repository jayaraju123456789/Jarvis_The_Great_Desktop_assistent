"""
core/tool_router.py — Deterministic & Intelligent Tool Router for JARVIS.

Decides which tool should execute a task without making redundant LLM calls
for simple, deterministic operations:

- "Open WhatsApp" / "Close Notepad"  → Windows Application Tool
- "Open report.docx" / "Close file"  → File / Windows UI Tool
- "Create a folder" / "Move file"    → File System Tool
- "Search Google" / "Open browser"   → Playwright Browser Tool
- "Draw a circle" / "Draw rectangle" → Drawing Tool
- "Send message to Rahul"            → Communication / WhatsApp Tool
- "Create a Python calculator"       → Autonomous Coding Agent
- "Create a Word document on AI"     → Document Agent

Complex tasks that cannot be satisfied in a single deterministic step are
routed to the Task Planner for multi-step graph execution.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from core.capability_registry import CapabilityRegistry
from core.logger import log_event


@dataclass
class RouteDecision:
    is_deterministic: bool
    tool_name: str
    action: str
    parameters: Dict[str, Any]
    rationale: str


class ToolRouter:
    """Fast, deterministic router for JARVIS operations."""

    @staticmethod
    def route(request: str) -> Optional[RouteDecision]:
        """
        Analyze request and return a deterministic RouteDecision, or None
        if the request requires LLM multi-step planning.
        """
        raw = request.strip()
        low = raw.lower()

        # Multi-Step Workflow Detection (Pass to Orchestrator for Sequential Planning)
        has_create = any(w in low for w in ("create", "write", "generate", "build", "make"))
        has_convert = "convert" in low or ("pdf" in low and any(w in low for w in ("word", "docx", "document")))
        has_send = any(w in low for w in ("send", "whatsapp", "share", "mail", "email"))
        has_monitor = any(w in low for w in ("monitor", "watch", "check email", "when a new", "when an email", "when new email"))

        if has_monitor and (has_send or "whatsapp" in low or "notify" in low):
            return None  # Multi-step monitor + notify passed to Orchestrator

        if (has_create and (has_convert or has_send) and any(c in low for c in (" and ", " then ", "save it in", "save in"))) or \
           (has_convert and has_send) or \
           (low.count(" and ") >= 2 and not any(w in low for w in ("draw", "paint", "sketch", "color", "screen", "image", "picture"))):
            return None

        # ── CAPABILITY-BASED ARTIFACT CREATION (Excel, CSV, Google Docs/Sheets/Slides, Word, PPTX) ──
        if has_create and not (has_convert or (has_send and any(c in low for c in (" and ", " then ")))):
            artifact_route = CapabilityRegistry.route_artifact_creation(raw)
            if artifact_route:
                t_name, t_act, t_params = artifact_route
                return RouteDecision(
                    is_deterministic=True,
                    tool_name=t_name,
                    action=t_act,
                    parameters=t_params,
                    rationale=f"Capability Router selected '{t_name}' for artifact '{t_act}' operation.",
                )

        # ── 0. TASK LIFECYCLE MANAGEMENT (PAUSE / RESUME / CANCEL) ───────────
        if any(w in low for w in ("pause this task", "pause the task", "pause current task", "stop this task for now", "pause task")):
            return RouteDecision(
                is_deterministic=True,
                tool_name="task_manager",
                action="pause",
                parameters={"action": "pause"},
                rationale="Routed directly to Task Manager to pause active task.",
            )
        if any(w in low for w in ("cancel this task", "cancel the task", "cancel current task", "cancel task", "abort this task")):
            return RouteDecision(
                is_deterministic=True,
                tool_name="task_manager",
                action="cancel",
                parameters={"action": "cancel"},
                rationale="Routed directly to Task Manager to cancel active task.",
            )
        if any(w in low for w in ("resume the task", "resume task", "resume previous task", "continue previous task", "resume this task")):
            return RouteDecision(
                is_deterministic=True,
                tool_name="task_manager",
                action="resume",
                parameters={"action": "resume"},
                rationale="Routed directly to Task Manager to resume task.",
            )

        # ── 1. DRAWING & COLORING ──────────────────────────────────────────────
        m_draw = re.search(r"\b(?:draw|sketch|paint|illustrate|color|render)\s+(?:a\s+|an\s+|the\s+|this\s+|that\s+)?(circle|rectangle|square|triangle|line|arrow|star|diamond|polygon|flowchart|diagram|illustration|building|house|plot|chart|shape|freehand|man|person|human|character|portrait|face|flower|rose|plant|tree|nature|landscape|mountain|sunset|scenery|car|vehicle|automobile|bird|dog|cat|image|picture|photo|screen)", low)
        is_paint_draw = "draw in paint" in low or "draw on paint" in low or ("paint" in low and ("draw" in low or "sketch" in low or "color" in low or "artwork" in low))
        is_color_cmd = any(w in low for w in ("apply color", "apply colors", "add color", "add colors", "draw with color", "draw in color", "color the drawing", "color this", "fill color", "colorize", "colored drawing"))
        is_face_drawing_cmd = (
            any(w in low for w in (
                "face character drawing", "character drawing", "face drawing", "portrait drawing",
                "draw face", "draw character", "draw a face", "draw a character", "draw portrait",
                "draw face character", "draw character face", "face character",
                "ఫేస్ క్యారెక్టర్", "ఫేస్ డ్రాయింగ్", "క్యారెక్టర్ డ్రాయింగ్", "ముఖం డ్రాయింగ్"
            ))
            or ("ఫేస్" in low and "డ్రాయింగ్" in low)
        ) and not any(w in low for w in ("requirements", "tools for", "guide on", "implementation plan"))
        is_image_draw = (
            any(w in low for w in (
                "draw image", "draw picture", "draw photo", "draw this picture", "draw screen",
                "draw this image", "draw the picture", "draw that image", "draw that picture",
                "draw what is on screen", "visible in screen", "visible on screen", "what visible in screen",
                "picture out layer", "image layout", "from that layout draw", "showing an image",
                "showing and image", "crop and draw"
            ))
            or bool(re.search(r"\bvisible\s+(?:on|in)\s+(?:the\s+|my\s+)?screen\b", low))
            or bool(re.search(r"\bdraw\s+(?:what(?:'s|\s+is)?\s+)?visible\b", low))
            or ("screen" in low and any(w in low for w in ("draw", "picture", "image", "layout", "photo")))
        )
        has_flowchart_rejection = any(w in low for w in (
            "dont want flowchat", "dont want flowchart", "not flowchat", "not flowchart",
            "no flowchart", "drawing flowchat", "drawing flowchart"
        ))

        is_prof_sketch_cmd = (
            any(w in low for w in (
                "professional pencil sketch", "professional sketch", "pencil sketch",
                "graphite sketch", "hand drawn sketch", "hand-drawn sketch", "human-style pencil",
                "human style pencil", "pencil portrait", "accurate outer boundaries",
                "clean pencil outline", "realistic shading", "accurate contours",
                "detailed graphite sketch", "pencil drawing", "graphite drawing",
                "pencil outline", "graphite outline", "graphite portrait",
                "neat pencil sketch", "neat pencile sketch", "neat sketch",
                "pencile sketch", "pencile drawing", "pencile outline", "pencile",
                "how human draw", "human draw", "human drawing",
                "simple pencil sketch", "simple pencile sketch", "simple pencil", "simple pencile"
            ))
            or (("sketch" in low or "draw" in low or "portrait" in low or "car" in low) and any(w in low for w in ("pencil", "pencile", "graphite", "shading", "outer boundaries", "accurate contours", "human draw")))
        )

        if m_draw or is_paint_draw or is_color_cmd or is_image_draw or is_face_drawing_cmd or is_prof_sketch_cmd:
            is_actual_man = bool(re.search(r"\b(?:draw|sketch|paint|illustrate)\s+(?:a\s+|an\s+|the\s+)?(?:man|person|portrait|human|character|face)\b", low))
            if is_face_drawing_cmd:
                raw_subj = "character"
            elif is_image_draw or has_flowchart_rejection:
                raw_subj = "image"
            elif m_draw:
                matched_subj = m_draw.group(1).lower()
                raw_subj = "image" if matched_subj in ("image", "picture", "photo", "screen") else (
                    "character" if matched_subj in ("character", "portrait", "face") else (
                        "illustration" if (matched_subj in ("flowchart", "diagram") and has_flowchart_rejection) else matched_subj
                    )
                )
            elif is_actual_man:
                raw_subj = "character" if any(w in low for w in ("character", "portrait", "face")) else "man"
            else:
                raw_subj = (
                    "flower" if "flower" in low else (
                        "tree" if "tree" in low else (
                            "car" if "car" in low else (
                                "landscape" if "landscape" in low else (
                                    "sunset" if "sunset" in low else ("image" if is_image_draw else "illustration")
                                )
                            )
                        )
                    )
                )

            if raw_subj == "shape":
                raw_subj = "circle"
            open_paint = is_paint_draw or is_image_draw or is_face_drawing_cmd or is_prof_sketch_cmd or "in paint" in low or "open in paint" in low or "show in paint" in low
            geometric = ("circle", "rectangle", "square", "triangle", "line", "arrow", "star", "diamond", "polygon", "flowchart")
            
            if is_face_drawing_cmd:
                shape_val = "character"
                source_val = "screen"
            elif is_image_draw or has_flowchart_rejection:
                shape_val = "image"
                source_val = "screen"
            else:
                shape_val = raw_subj if raw_subj in geometric else ("character" if raw_subj in ("character", "face", "portrait") else ("image" if (raw_subj in ("image", "picture", "photo", "screen") or is_image_draw) else "illustration"))
                source_val = "screen" if shape_val in ("image", "screen", "character") else "canvas"

            m_file = re.search(r"['\"]?([a-zA-Z0-9_\-\\\/\.]+\.(?:png|jpg|jpeg|bmp|webp))['\"]?", raw, re.IGNORECASE)
            file_cand = m_file.group(1).strip() if m_file else None

            if is_prof_sketch_cmd:
                prof_profile = (
                    "vehicle" if any(w in low for w in ("car", "vehicle", "automobile", "truck", "bike"))
                    else ("portrait" if any(w in low for w in ("portrait", "face", "person", "human", "character", "man", "girl", "woman")) else "auto")
                )
                prof_params = {
                    "shape": "image",
                    "source": "file" if file_cand else "screen",
                    "subject": raw_subj,
                    "style": "professional_pencil_sketch",
                    "colorize": False,
                    "crop_subject": True,
                    "mode": "professional_pencil_sketch",
                    "profile": prof_profile,
                    "open": True,
                    "open_in_paint": True,
                }
                if file_cand:
                    prof_params["image_path"] = file_cand
                return RouteDecision(
                    is_deterministic=True,
                    tool_name="drawing_tool",
                    action="draw",
                    parameters=prof_params,
                    rationale=f"Routed directly to Drawing Tool for Professional Hand-Drawn Pencil Sketch (profile={prof_profile}, accurate contours, graphite shading, open_in_paint=True).",
                )

            return RouteDecision(
                is_deterministic=True,
                tool_name="drawing_tool",
                action="draw",
                parameters={
                    "shape": shape_val,
                    "source": "file" if file_cand else source_val,
                    "subject": raw_subj,
                    "style": "color",
                    "colorize": True,
                    "crop_subject": True,
                    "mode": "image",
                    "open": True,
                    "open_in_paint": open_paint,
                    **({"image_path": file_cand} if file_cand else {}),
                },
                rationale=f"Routed directly to Drawing Tool for subject '{raw_subj}' (source={source_val}, colorized=True, crop_subject=True, open_in_paint={open_paint}).",
            )

        # ── 1B. SCREENSHOTS ───────────────────────────────────────────────────
        if any(w in low for w in ("screenshot", "take a screenshot", "capture screen", "capture desktop", "capture window", "snip")) and "debug" not in low and not any(w in low for w in ("send", "share", "whatsapp", "mail", "email", "to ")):
            m_win = re.search(r"(?:screenshot\s+of|capture\s+(?:the\s+)?window\s+of|screenshot\s+)(?:the\s+)?([a-zA-Z0-9_\-\s]+?)(?:$|\s+window)", raw, re.IGNORECASE)
            win_target = ""
            if m_win:
                cand = m_win.group(1).strip()
                if cand.lower() not in ("desktop", "screen", "my screen", "my desktop", "fullscreen", "active", "active window"):
                    win_target = cand

            mode = "window" if win_target else ("active_window" if "active" in low else "fullscreen")
            return RouteDecision(
                is_deterministic=True,
                tool_name="screenshot_tool",
                action="screenshot",
                parameters={"mode": mode, "window_title": win_target},
                rationale=f"Routed directly to Screenshot Tool (mode: '{mode}', target: '{win_target or 'Desktop'}').",
            )

        # ── 1C. GOOGLE DRIVE UPLOAD ──────────────────────────────────────────
        if any(w in low for w in ("upload to google drive", "upload to drive", "save to google drive", "save to drive")):
            m_f = re.search(r"(?:upload|save)\s+(?:this\s+)?(?:file|document)?\s*['\"]?(\S+\.[a-zA-Z0-9]+)?['\"]?\s+(?:to\s+(?:google\s+)?drive)", raw, re.IGNORECASE)
            file_to_upload = m_f.group(1).strip() if m_f and m_f.group(1) else ""
            return RouteDecision(
                is_deterministic=True,
                tool_name="google_drive_tool",
                action="upload",
                parameters={"action": "upload", "file_path": file_to_upload},
                rationale="Routed directly to Google Drive API Tool to upload file.",
            )

        # ── 1D. AI VIDEO GENERATION ──────────────────────────────────────────
        is_video_gen = (
            any(w in low for w in (
                "generate video", "generate an ai video", "generate ai video",
                "create video", "create an ai video", "create ai video",
                "make video", "make an ai video", "make ai video",
                "video generation", "ai video generation", "text to video",
                "render video", "render an ai video", "generate a video",
                "create a video", "make a video", "ai video of", "ai video about"
            ))
            or (("generate" in low or "create" in low or "make" in low or "render" in low) and "video" in low and not any(w in low for w in ("youtube", "play video", "search video", "watch video", "call", "audio call")))
        )
        if is_video_gen and not any(w in low for w in ("youtube", "play", "watch", "requirements", "guide on", "tools for", "video call", "audio call", "call")):
            m_prompt = re.search(r"(?:prompt\s*:\s*|of\s+|about\s+|for\s+)(.+)$", raw, re.IGNORECASE)
            v_prompt = m_prompt.group(1).strip() if m_prompt else re.sub(r"^(?:please\s+)?(?:generate|create|make|render)\s+(?:an?\s+)?(?:ai\s+)?video\s*(?:of|about|for)?\s*", "", raw, flags=re.IGNORECASE).strip()
            if not v_prompt or v_prompt.lower() in ("video", "an ai video", "ai video"):
                v_prompt = "Futuristic artificial intelligence and autonomous system in motion"
            return RouteDecision(
                is_deterministic=True,
                tool_name="video_generation_tool",
                action="generate",
                parameters={
                    "action": "generate",
                    "prompt": v_prompt,
                    "open_video": True,
                },
                rationale=f"Routed directly to Video Generation Tool for prompt '{v_prompt}'.",
            )

        # ── 1C. COMMUNICATION & MESSAGING (WHATSAPP, CALLS, VOICE NOTES, FILES) ──
        # 1. End call / hang up
        if any(w in low for w in ("end call", "hang up", "stop call", "terminate call", "disconnect call", "cut the call", "end the call")):
            return RouteDecision(
                is_deterministic=True,
                tool_name="send_message",
                action="end_call",
                parameters={"action": "end_call", "platform": "whatsapp"},
                rationale="Routed directly to Communication Agent to end active call.",
            )

        # 2. Call status
        if any(w in low for w in ("call status", "check call", "is call active", "call state")):
            return RouteDecision(
                is_deterministic=True,
                tool_name="send_message",
                action="call_state",
                parameters={"action": "call_state", "platform": "whatsapp"},
                rationale="Routed directly to Communication Agent to inspect call state.",
            )

        # 2B. Incoming call detection & handling
        if any(w in low for w in ("check incoming call", "is there an incoming call", "incoming call status", "who is calling", "detect incoming call")):
            return RouteDecision(
                is_deterministic=True,
                tool_name="send_message",
                action="detect_incoming_call",
                parameters={"action": "detect_incoming_call", "platform": "whatsapp"},
                rationale="Routed directly to Communication Agent to detect incoming call.",
            )

        if any(w in low for w in ("accept call", "answer call", "pick up call", "pick up the call", "answer the call", "accept the call")):
            return RouteDecision(
                is_deterministic=True,
                tool_name="send_message",
                action="respond_incoming_call",
                parameters={"action": "respond_incoming_call", "call_action": "accept", "platform": "whatsapp"},
                rationale="Routed directly to Communication Agent to accept incoming call.",
            )

        if any(w in low for w in ("decline call", "reject call", "decline the call", "reject the call")):
            return RouteDecision(
                is_deterministic=True,
                tool_name="send_message",
                action="respond_incoming_call",
                parameters={"action": "respond_incoming_call", "call_action": "decline", "platform": "whatsapp"},
                rationale="Routed directly to Communication Agent to decline incoming call.",
            )

        # 2C. Missed calls query & authorized reply
        if any(w in low for w in ("check missed calls", "show missed calls", "missed calls", "who called me", "list missed calls")):
            return RouteDecision(
                is_deterministic=True,
                tool_name="send_message",
                action="get_missed_calls",
                parameters={"action": "get_missed_calls", "platform": "whatsapp"},
                rationale="Routed directly to Communication Agent to query missed calls.",
            )

        m_auth_reply = re.search(r"\b(?:reply\s+to\s+(?:missed\s+call\s+from\s+)?|send\s+reply\s+to\s+)([A-Za-z0-9\.\'\-\+]+(?:\s+[A-Za-z0-9\.\'\-\+]+)?)\s+(?:saying|that|with message|:)\s+(.+)$", raw, re.IGNORECASE)
        if m_auth_reply:
            rep_target = m_auth_reply.group(1).strip()
            rep_msg = m_auth_reply.group(2).strip()
            rep_target = re.sub(r"\s+(?:on|via)\s+whatsapp$", "", rep_target, flags=re.IGNORECASE).strip()
            return RouteDecision(
                is_deterministic=True,
                tool_name="send_message",
                action="authorized_reply",
                parameters={
                    "action": "authorized_reply",
                    "receiver": rep_target,
                    "message_text": rep_msg,
                    "platform": "whatsapp",
                },
                rationale=f"Routed directly to Communication Agent to send authorized reply to '{rep_target}'.",
            )

        # 2D. Busy-reply status, configuration, & monitor controls
        if any(w in low for w in ("busy status", "busy settings", "busy reply config", "auto reply settings", "auto reply status")):
            return RouteDecision(
                is_deterministic=True,
                tool_name="send_message",
                action="busy_config",
                parameters={"action": "busy_config", "platform": "whatsapp"},
                rationale="Routed directly to Communication Agent to query WhatsApp busy-reply status.",
            )

        if any(w in low for w in ("enable auto reply", "turn on auto reply", "enable busy reply", "turn on busy reply")):
            return RouteDecision(
                is_deterministic=True,
                tool_name="send_message",
                action="update_busy_config",
                parameters={"action": "update_busy_config", "auto_reply_enabled": True, "platform": "whatsapp"},
                rationale="Routed directly to Communication Agent to enable WhatsApp busy auto-reply.",
            )

        if any(w in low for w in ("disable auto reply", "turn off auto reply", "disable busy reply", "turn off busy reply")):
            return RouteDecision(
                is_deterministic=True,
                tool_name="send_message",
                action="update_busy_config",
                parameters={"action": "update_busy_config", "auto_reply_enabled": False, "platform": "whatsapp"},
                rationale="Routed directly to Communication Agent to disable WhatsApp busy auto-reply.",
            )

        if any(w in low for w in ("start call monitor", "start missed call monitor", "monitor missed calls")):
            return RouteDecision(
                is_deterministic=True,
                tool_name="send_message",
                action="start_call_monitor",
                parameters={"action": "start_call_monitor", "platform": "whatsapp"},
                rationale="Routed directly to Communication Agent to start background call monitor.",
            )

        if any(w in low for w in ("stop call monitor", "stop missed call monitor")):
            return RouteDecision(
                is_deterministic=True,
                tool_name="send_message",
                action="stop_call_monitor",
                parameters={"action": "stop_call_monitor", "platform": "whatsapp"},
                rationale="Routed directly to Communication Agent to stop background call monitor.",
            )

        # 3. Voice or Video Call: e.g. "call Rahul on whatsapp", "call Jhon chavala on whatsapp.", "video call Rahul", "make a whatsapp video call to my friend"
        clean_raw = raw.strip().rstrip(".!?,")
        m_call = re.search(
            r"\b(?:start|make|initiate)?\s*(?:a\s+)?(?:whatsapp\s+)?(video|audio|voice)?\s*call\s+(?:to\s+|with\s+)?(.+?)(?:\s+(?:on|via|through)\s+whatsapp)?$",
            clean_raw,
            re.IGNORECASE,
        )
        if not m_call and ("call" in low or "calling" in low):
            m_call = re.search(
                r"\b(video|audio|voice)?\s*call\s+(?:to\s+|with\s+)?(.+?)(?:\s+(?:on|via|through)\s+whatsapp)?$",
                clean_raw,
                re.IGNORECASE,
            )

        if m_call and not any(w in low for w in ("function", "method", "api", "tool", "help")):
            c_type = "video" if ("video" in low or (m_call.group(1) and "video" in m_call.group(1).lower())) else "audio"
            rec = m_call.group(2).strip()
            rec = re.sub(r"\s+(?:on|via|through)\s+whatsapp$", "", rec, flags=re.IGNORECASE).strip()
            if rec.lower().startswith("to "):
                rec = rec[3:].strip()
            if rec.lower().startswith("with "):
                rec = rec[5:].strip()

            if rec and len(rec) >= 2 and rec.lower() not in ("me", "system", "app"):
                return RouteDecision(
                    is_deterministic=True,
                    tool_name="send_message",
                    action=f"{c_type}_call",
                    parameters={
                        "action": f"{c_type}_call",
                        "receiver": rec,
                        "call_type": c_type,
                        "platform": "whatsapp",
                    },
                    rationale=f"Routed directly to Communication Agent to start WhatsApp {c_type} call with '{rec}'.",
                )

        # 4. Voice Note / Voice Message: e.g. "send voice note to Rahul saying I am busy", "send a voice message to Mom"
        m_vmsg = re.search(r"\b(?:send|record)\s+(?:a\s+)?(?:voice\s+note|voice\s+message|audio\s+message|audio\s+note)\s+(?:to\s+)?([a-zA-Z0-9_\+\s]+?)(?:\s+(?:saying|that|with message)\s+(.+))?$", raw, re.IGNORECASE)
        if m_vmsg:
            rec = m_vmsg.group(1).strip()
            rec = re.sub(r"\s+(?:on|via)\s+whatsapp$", "", rec, flags=re.IGNORECASE).strip()
            txt = m_vmsg.group(2).strip() if m_vmsg.group(2) else ""
            is_mic = any(w in low for w in ("mic", "my voice", "record"))
            return RouteDecision(
                is_deterministic=True,
                tool_name="send_message",
                action="voice_message",
                parameters={
                    "action": "voice_message",
                    "receiver": rec,
                    "message_text": txt,
                    "from_mic": is_mic,
                    "platform": "whatsapp",
                },
                rationale=f"Routed directly to Communication Agent to send voice note to '{rec}'.",
            )

        # 5. Read / Receive Messages: e.g. "read messages from Rahul", "check messages from Mom"
        m_read_msg = re.search(r"\b(?:read|check|receive|get)\s+(?:recent\s+)?messages\s+(?:from\s+|for\s+)?([a-zA-Z0-9_\+\s]+?)(?:\s+(?:on|via)\s+whatsapp)?$", raw, re.IGNORECASE)
        if m_read_msg:
            rec = m_read_msg.group(1).strip()
            rec = re.sub(r"\s+(?:on|via)\s+whatsapp$", "", rec, flags=re.IGNORECASE).strip()
            return RouteDecision(
                is_deterministic=True,
                tool_name="send_message",
                action="read_messages",
                parameters={
                    "action": "read_messages",
                    "receiver": rec,
                    "platform": "whatsapp",
                },
                rationale=f"Routed directly to Communication Agent to read messages from '{rec}'.",
            )

        # 6. Send File Attachment: e.g. "send file report.pdf to Rahul on whatsapp", "send report.pdf to Rahul on whatsapp"
        m_send_file = re.search(r"\b(?:send|share)\s+(?:file\s+|document\s+|image\s+|video\s+)?([a-zA-Z0-9_\-\.\:\/\\]+\.(?:pdf|docx|doc|txt|xlsx|pptx|png|jpg|jpeg|mp4|wav|mp3|csv|zip))\s+(?:to\s+|with\s+)?([a-zA-Z0-9_\+\s]+?)(?:\s+(?:on|via)\s+(?:whatsapp|telegram))?(?:\s+(?:saying|with message)\s+(.+))?$", raw, re.IGNORECASE)
        if m_send_file:
            f_target = m_send_file.group(1).strip()
            rec = m_send_file.group(2).strip()
            rec = re.sub(r"\s+(?:on|via)\s+(?:whatsapp|telegram)$", "", rec, flags=re.IGNORECASE).strip()
            caption = m_send_file.group(3).strip() if m_send_file.group(3) else ""
            plat = "telegram" if "telegram" in low else "whatsapp"
            return RouteDecision(
                is_deterministic=True,
                tool_name="send_message",
                action="send",
                parameters={
                    "action": "send",
                    "receiver": rec,
                    "attachment_path": f_target,
                    "message_text": caption,
                    "platform": plat,
                },
                rationale=f"Routed directly to Communication Agent to send file '{f_target}' to '{rec}' on {plat}.",
            )

        # 7. Send Direct Text Message: e.g. "send message to Rahul saying I will be late", "whatsapp Rahul hello"
        m_send_msg = re.search(r"\b(?:send\s+(?:a\s+)?message\s+to\s+|whatsapp\s+)([a-zA-Z0-9_\+\s]+?)\s+(?:saying|that|with message|:)\s+(.+)$", raw, re.IGNORECASE)
        if m_send_msg:
            rec = m_send_msg.group(1).strip()
            rec = re.sub(r"\s+(?:on|via)\s+whatsapp$", "", rec, flags=re.IGNORECASE).strip()
            msg_body = m_send_msg.group(2).strip()
            return RouteDecision(
                is_deterministic=True,
                tool_name="send_message",
                action="send",
                parameters={
                    "action": "send",
                    "receiver": rec,
                    "message_text": msg_body,
                    "platform": "whatsapp",
                },
                rationale=f"Routed directly to Communication Agent to send message to '{rec}'.",
            )

        # ── 2. WINDOWS APPLICATION OPEN / CLOSE ──────────────────────────────
        m_open_app = re.match(r"^(?:please\s+)?(?:open|launch|start)\s+([a-zA-Z0-9_\-\.\s\:\\/]+)$", raw, re.IGNORECASE)
        if m_open_app and not any(w in low for w in ("chat", "conversation", "folder", "directory", "browser and search", "calculator app", "application", "call", "audio call", "video call", "voice call", "voice message", "voice note", "email", "mail", "mass email", "video")):
            target = m_open_app.group(1).strip()
            # If target has a file extension or exists as a file, treat as open_file
            if ("." in target and not target.endswith(".exe")) or Path(target).is_file():
                return RouteDecision(
                    is_deterministic=True,
                    tool_name="open_app",
                    action="open_file",
                    parameters={"app_name": target, "action": "open_file"},
                    rationale=f"Routed directly to file launcher for '{target}'.",
                )
            return RouteDecision(
                is_deterministic=True,
                tool_name="open_app",
                action="open",
                parameters={"app_name": target, "action": "open"},
                rationale=f"Routed directly to Windows Application Tool for '{target}'.",
            )

        # ── 2B. CLOSE ALL TABS ────────────────────────────────────────────────
        if any(p in low for p in ("close all tabs", "close tabs", "close browser tabs", "exit all tabs")):
            return RouteDecision(
                is_deterministic=True,
                tool_name="computer_settings",
                action="close_all_tabs",
                parameters={"action": "close_all_tabs"},
                rationale="Routed directly to close all browser tabs with auto-confirmation.",
            )

        m_close_app = re.match(r"^(?:please\s+)?(?:close|exit|quit|kill|terminate)\s+([a-zA-Z0-9_\-\.\s\:\\/]+)$", raw, re.IGNORECASE)
        if m_close_app and not any(w in low for w in ("folder", "browser session", "tab")):
            target = m_close_app.group(1).strip()
            if ("." in target and not target.endswith(".exe")) or Path(target).is_file():
                return RouteDecision(
                    is_deterministic=True,
                    tool_name="open_app",
                    action="close_file",
                    parameters={"app_name": target, "action": "close_file"},
                    rationale=f"Routed directly to file window close for '{target}'.",
                )
            return RouteDecision(
                is_deterministic=True,
                tool_name="open_app",
                action="close",
                parameters={"app_name": target, "action": "close"},
                rationale=f"Routed directly to application close for '{target}'.",
            )

        # ── 3A-0. MASS EMAIL / MAIL MERGE CAMPAIGNS ───────────────────────────
        if any(w in low for w in ("mass email", "mail merge", "mass emailing", "bulk email", "email campaign", "email all recipients", "email recipients in", "send campaign")) or ("csv" in low and any(w in low for w in ("email", "mail", "gmail"))):
            m_csv = re.search(r"(\S+\.csv)", raw, re.IGNORECASE)
            csv_path = m_csv.group(1) if m_csv else ""
            m_subj = re.search(r"subject\s*:\s*([^,\.\n]+)", raw, re.IGNORECASE)
            subj = m_subj.group(1).strip() if m_subj else "Important Update from JARVIS"
            m_body = re.search(r"(?:saying|body|message)\s*:\s*(.+)$", raw, re.IGNORECASE)
            body = m_body.group(1).strip() if m_body else "Hello {{First_Name}},\n\nPlease review this update."
            m_att = re.search(r"(\S+\.(?:pdf|docx|png|jpg|txt|xlsx|pptx))", raw, re.IGNORECASE)
            att_file = m_att.group(1) if (m_att and m_att.group(1) != csv_path) else ""
            c_action = "draft" if "draft" in low else ("preview" if "preview" in low else "send")

            return RouteDecision(
                is_deterministic=True,
                tool_name="mass_email_tool",
                action=c_action,
                parameters={
                    "csv_file": csv_path,
                    "subject": subj,
                    "body": body,
                    "action": c_action,
                    "attachment_path": att_file or None,
                },
                rationale=f"Routed directly to Mass Email Tool for campaign ({c_action}) from '{csv_path or 'recent CSV'}'.",
            )

        # ── 3A. GMAIL / EMAIL OPERATIONS ─────────────────────────────────────
        if ("gmail" in low or ("draft" in low and any(w in low for w in ("email", "mail"))) or
            ("send" in low and any(w in low for w in ("email", "mail", "gmail")) and "whatsapp" not in low)):
            if ("convert" in low or "word document" in low or "docx" in low) and "draft" not in low:
                return None  # Pass multi-step combined workflow to Orchestrator

            m_to = re.search(r"\bto\s+([A-Za-z0-9_\.@]+)", raw, re.IGNORECASE)
            to_addr = m_to.group(1) if m_to else ""

            # Check for attachment
            m_file = re.search(r"(\S+\.(?:pdf|docx|png|jpg|txt|xlsx|pptx))", raw, re.IGNORECASE)
            att_path = m_file.group(1) if m_file else ""

            m_saying = re.search(r"(?:saying|body|message)\s*:\s*(.+)$", raw, re.IGNORECASE)
            m_subj = re.search(r"subject\s*:\s*([^,\.]+)", raw, re.IGNORECASE)
            subj = m_subj.group(1).strip() if m_subj else "Message from JARVIS"
            body = m_saying.group(1).strip() if m_saying else re.sub(r"(?:create\s+a\s+draft|draft\s+email|send\s+email|send\s+mail|to\s+[A-Za-z0-9_\.@]+|through\s+gmail|via\s+gmail|in\s+gmail)", "", raw, flags=re.IGNORECASE).strip()

            is_draft = "draft" in low
            action = "create_draft" if is_draft else "send_email"
            return RouteDecision(
                is_deterministic=True,
                tool_name="gmail_tool",
                action=action,
                parameters={
                    "action": action,
                    "to": to_addr or "Recipient",
                    "subject": subj,
                    "body": body or "I have completed the research document.",
                    "attachment_path": att_path,
                },
                rationale=f"Routed directly to Gmail API tool for {action} to '{to_addr or 'Recipient'}'.",
            )

        # ── 3B. WHATSAPP & MESSAGING ──────────────────────────────────────────
        # Check for WhatsApp requirement or meta-query (NEVER send as message)
        is_whatsapp_meta = any(k in low for k in ("requirements for", "prerequisites for", "limitations of", "what are the requirements", "requirements of", "requirements to"))
        if is_whatsapp_meta and "whatsapp" in low:
            return None

        def _extract_wa_recipient(text: str) -> str:
            # 1. Phone numbers with country code or digits: e.g. +91 9876543210, +919876543210, 9876543210
            m_p = re.search(r"(\+?\d[\d\s\-]{6,15}\d)", text)
            if m_p:
                cand = re.sub(r"[\s\-]", "", m_p.group(1))
                if len(cand) >= 7:
                    return cand

            # 2. "to <recipient(s)>" (supports single contact or comma/and separated contacts) or "with <recipient>" or "for <recipient>"
            m_multi = re.search(r"\b(?:to)\s+([A-Za-z0-9\.\'\-]+(?:\s+[A-Za-z0-9\.\'\-]+)?(?:\s*,\s*[A-Za-z0-9\.\'\-]+(?:\s+[A-Za-z0-9\.\'\-]+)?)*(?:\s+and\s+[A-Za-z0-9\.\'\-]+(?:\s+[A-Za-z0-9\.\'\-]+)?)?)(?:\s+(?:on|via|through|using)\s+whatsapp|\s+saying\b|\s+that\b|$)", text, re.IGNORECASE)
            if m_multi:
                c = m_multi.group(1).strip()
                if c.lower() not in ("whatsapp", "a", "the", "this", "my", "him", "her", "now", "chat", "call", "file", "document", "pdf", "word", "excel", "screenshot"):
                    return c
            m_t = re.search(r"\b(?:with|for)\s+([A-Za-z0-9\.\'\-]+(?:\s+[A-Za-z0-9\.\'\-]+)?)(?:\s+(?:on|via|through|using)\s+whatsapp|\s+saying\b|\s+that\b|\s+on\s+my\b|\s+in\s+my\b|\s+and\b|$)", text, re.IGNORECASE)
            if m_t:
                c = m_t.group(1).strip()
                if c.lower() not in ("whatsapp", "a", "the", "this", "my", "him", "her", "now", "chat", "call", "file", "document", "pdf", "word", "excel", "screenshot"):
                    return c

            # 3. Direct action pattern: "call <recipient>", "video call <recipient>", "open chat for <recipient>"
            m_a = re.search(r"\b(?:video\s+call|audio\s+call|voice\s+call|call|ring|phone|dm|ping|chat\s+with|open\s+chat\s+for|open\s+conversation\s+with|open\s+(?:the\s+)?chat\s+with)\s+([A-Za-z0-9\.\'\-]+(?:\s+[A-Za-z0-9\.\'\-]+)?)(?:\s+(?:on|via|through|using)\s+whatsapp|\s+saying\b|\s+now\b|$)", text, re.IGNORECASE)
            if m_a:
                c = m_a.group(1).strip()
                if c.lower() not in ("whatsapp", "a", "the", "this", "my", "him", "her", "now", "chat", "call", "file", "document", "pdf", "word", "excel", "screenshot"):
                    return c

            # 4. Pattern before "on whatsapp": "<recipient> on whatsapp"
            m_w = re.search(r"([A-Za-z0-9\.\'\-]+(?:\s+[A-Za-z0-9\.\'\-]+)?)\s+(?:on|via)\s+whatsapp\b", text, re.IGNORECASE)
            if m_w:
                c = m_w.group(1).strip()
                if c.lower() not in ("call", "chat", "message", "file", "send", "video", "audio", "voice"):
                    return c

            return ""

        # 3B-0. Open WhatsApp Chat / Conversation
        if (re.search(r"\b(?:open|launch|switch\s+to)\s+(?:the\s+)?(?:whatsapp\s+)?(?:chat|conversation|messages?)\b", low) or "open whatsapp chat" in low or "open chat" in low) and not any(w in low for w in ("call", "voice note", "send")):
            target_recipient = _extract_wa_recipient(raw)
            if target_recipient:
                return RouteDecision(
                    is_deterministic=True,
                    tool_name="send_message",
                    action="open_chat",
                    parameters={
                        "action": "open_chat",
                        "receiver": target_recipient,
                        "platform": "whatsapp",
                    },
                    rationale=f"Routed directly to open WhatsApp conversation for '{target_recipient}'.",
                )

        # 3B-1. Call termination
        if (re.search(r"\b(?:end|hang\s*up|stop|disconnect|cut)\s+(?:the\s+)?(?:whatsapp\s+)?call\b", low) or any(w in low for w in ("hang up", "hangup", "end the call", "end call", "stop the call", "cut the call", "cut call"))) and not any(w in low for w in ("start", "make", "video call")):
            return RouteDecision(
                is_deterministic=True,
                tool_name="send_message",
                action="end_call",
                parameters={"action": "end_call", "platform": "whatsapp"},
                rationale="Routed directly to terminate active WhatsApp call.",
            )

        # 3B-2. Call state inspection
        if any(w in low for w in ("call state", "call status", "check call", "is call connected", "is the call active", "is call active")) and ("call" in low or "whatsapp" in low):
            return RouteDecision(
                is_deterministic=True,
                tool_name="send_message",
                action="call_state",
                parameters={"action": "call_state", "platform": "whatsapp"},
                rationale="Routed directly to check active WhatsApp call state.",
            )

        # 3B-3. Voice & Video Calling
        is_call_request = any(w in low for w in ("video call", "audio call", "voice call", "call", "ring", "phone")) and (
            "whatsapp" in low or bool(re.search(r"\b(?:call|video\s+call|audio\s+call|voice\s+call|ring|make\s+(?:a\s+)?call|start\s+(?:a\s+|an\s+)?(?:video\s+|audio\s+|voice\s+)?call)\b", low))
        )
        if is_call_request and not any(w in low for w in ("end call", "end the call", "hang up", "hangup", "voice message", "voice note", "audio note", "create", "write")):
            is_video = "video" in low
            call_action = "video_call" if is_video else "audio_call"
            
            contact = _extract_wa_recipient(raw) or "Recipient"
                
            return RouteDecision(
                is_deterministic=True,
                tool_name="send_message",
                action=call_action,
                parameters={
                    "action": call_action,
                    "receiver": contact,
                    "platform": "whatsapp",
                },
                rationale=f"Routed directly to WhatsApp {call_action} for '{contact}'.",
            )

        # 3B-4. Voice Messages & Audio Notes
        is_voice_msg = any(w in low for w in ("voice message", "voice note", "audio message", "audio note", "send voice"))
        if is_voice_msg and not any(w in low for w in ("create document", "create report", "requirements")):
            contact = _extract_wa_recipient(raw) or "Recipient"
            
            m_saying = re.search(r"\b(?:saying|that)\s*[:\s]\s*(.+)$", raw, re.IGNORECASE)
            if m_saying:
                msg_text = m_saying.group(1).strip()
            else:
                msg_text = re.sub(r"^(?:please\s+)?(?:send\s+a\s+|send\s+)?(?:voice\s+message|voice\s+note|audio\s+message|audio\s+note)\s+(?:to\s+[A-Za-z0-9\.\'\-]+(?:\s+[A-Za-z0-9\.\'\-]+)?|with\s+[A-Za-z0-9\.\'\-]+)?\s*(?:on\s+whatsapp|via\s+whatsapp)?\s*", "", raw, flags=re.IGNORECASE).strip()
            
            return RouteDecision(
                is_deterministic=True,
                tool_name="send_message",
                action="voice_message",
                parameters={
                    "action": "voice_message",
                    "receiver": contact,
                    "message_text": msg_text or "Hello, this is a voice message from JARVIS.",
                    "platform": "whatsapp",
                },
                rationale=f"Routed directly to WhatsApp voice note synthesis and transmission to '{contact}'.",
            )

        # 3B-5. Messages & File Attachments
        if "whatsapp" in low or ("send" in low and any(w in low for w in ("message", "pdf", "file", "photo", "image", "document", "report", "screenshot", "presentation", "photos", "images", "files", "documents")) and not any(k in low for k in ("gmail", "email", "mail"))):
            if any(w in low for w in ("create", "write", "generate", "convert")) and (" and " in low or " then " in low):
                return None

            contact = _extract_wa_recipient(raw) or "Recipient"

            # Detect folder
            detected_folder = None
            if "desktop" in low:
                detected_folder = "Desktop"
            elif "document" in low or "documents" in low:
                detected_folder = "Documents"
            elif "download" in low or "downloads" in low:
                detected_folder = "Downloads"
            elif "picture" in low or "pictures" in low:
                detected_folder = "Pictures"

            # Check for count pattern (e.g. "10 images", "2 photos", "5 files")
            m_count = re.search(r"\b(\d+)\s+(images?|photos?|pictures?|files?|documents?|pdfs?)\b", low)
            detected_count = int(m_count.group(1)) if m_count else None

            # Check for multiple specific file names: e.g. "file1.jpg, file2.png"
            m_multi_files = re.findall(r"[\w\-]+\.(?:pdf|docx|doc|png|jpg|jpeg|mp4|txt|xlsx|xls|pptx|ppt|csv|wav|mp3)\b", raw, re.IGNORECASE)

            # Check for direct file or search query
            m_file = re.search(r"(\S+\.(?:pdf|docx|doc|png|jpg|jpeg|mp4|txt|xlsx|xls|pptx|ppt|csv|wav|mp3))", raw, re.IGNORECASE)
            att_path = ""
            if len(m_multi_files) > 1:
                att_path = ", ".join(m_multi_files)
            elif m_file:
                att_path = m_file.group(1)
            elif m_count:
                att_path = f"{m_count.group(1)} {m_count.group(2)}"
            else:
                for k in ("screenshot", "report", "document", "presentation", "pdf", "docx", "file", "photo", "image", "picture", "excel", "photos", "images", "files"):
                    if k in low:
                        att_path = k
                        break

            # Handle multi-recipients if contact contains comma or and
            recipients_param = None
            if "," in contact or " and " in contact.lower():
                r_parts = [p.strip() for p in re.split(r",|\band\b", contact, flags=re.IGNORECASE) if p.strip()]
                if len(r_parts) > 1:
                    recipients_param = r_parts

            # If user asks to search or find a file ("find the pdf", "10 images", multi-files, etc.)
            is_find_file = (
                bool(detected_count)
                or len(m_multi_files) > 1
                or any(w in low for w in ("find", "locate", "search", "latest screenshot"))
                or (detected_folder and att_path)
            )

            if is_find_file and att_path:
                params = {
                    "action": "find_file_and_send",
                    "receiver": contact,
                    "file_query": att_path,
                    "folder": detected_folder,
                    "platform": "whatsapp",
                }
                if detected_count:
                    params["count"] = detected_count
                if len(m_multi_files) > 1:
                    params["files"] = m_multi_files
                if recipients_param:
                    params["recipients"] = recipients_param

                return RouteDecision(
                    is_deterministic=True,
                    tool_name="send_message",
                    action="find_file_and_send",
                    parameters=params,
                    rationale=f"Routed directly to Desktop file search & WhatsApp transmission of '{att_path}' to '{contact}'.",
                )

            m_saying = re.search(r"(?:saying|that|body|message)\s*[:\s]\s*(.+)$", raw, re.IGNORECASE)
            if m_saying:
                msg_text = m_saying.group(1).strip()
            else:
                msg_text = re.sub(
                    r"(?:send\s+|to\s+[A-Za-z0-9\.\'\-]+(?:\s+[A-Za-z0-9\.\'\-]+)?|with\s+[A-Za-z0-9\.\'\-]+|whatsapp|through\s+whatsapp|via\s+whatsapp|on\s+whatsapp|"
                    r"the\s+file|this\s+file|the\s+document|this\s+document|the\s+report|this\s+report|screenshot)",
                    "", raw, flags=re.IGNORECASE
                ).strip()

            params = {
                "receiver": contact,
                "message_text": msg_text or ("Here is the requested file." if att_path else "Hello from JARVIS"),
                "attachment_path": att_path,
                "platform": "whatsapp",
            }
            if recipients_param:
                params["recipients"] = recipients_param
            if detected_count:
                params["count"] = detected_count
            if len(m_multi_files) > 1:
                params["files"] = m_multi_files

            return RouteDecision(
                is_deterministic=True,
                tool_name="send_message",
                action="send",
                parameters=params,
                rationale=f"Routed directly to WhatsApp communication workflow for '{contact}'.",
            )


        # ── 4. WEB BROWSER SEARCH / NAVIGATION ───────────────────────────────
        if (low.startswith("search ") or "search for " in low or "search google for " in low or "search web for " in low) and "download" not in low:
            query = re.sub(r"^(?:please\s+)?(?:search\s+for|search\s+google\s+for|search\s+web\s+for|search)\s+", "", raw, flags=re.IGNORECASE).strip()
            return RouteDecision(
                is_deterministic=True,
                tool_name="browser_control",
                action="search",
                parameters={"action": "search", "query": query, "engine": "duckduckgo"},
                rationale="Routed directly to Playwright isolated browser automation.",
            )

        # ── 5. FILE SYSTEM DISCOVERY & CRUD ──────────────────────────────────
        if re.search(r"\b(?:create\s+folder|make\s+folder|create\s+directory|mkdir)\b", low):
            m_dir = re.search(r"(?:folder|directory)\s+(?:called\s+|named\s+)?([A-Za-z0-9_\-\.]+)", raw, re.IGNORECASE)
            folder_name = m_dir.group(1) if m_dir else "NewFolder"
            target_path = Path.home() / "Desktop" / folder_name
            return RouteDecision(
                is_deterministic=True,
                tool_name="file_controller",
                action="create_folder",
                parameters={"action": "create_folder", "path": str(target_path)},
                rationale=f"Routed directly to File System Tool for directory '{folder_name}'.",
            )

        # 5B. File Search & Discovery across filesystem
        is_file_search = (
            any(low.startswith(p) for p in ("find my ", "search my computer for ", "search for the file ", "find the file ", "find all ", "locate the ", "search for files ", "where is my ", "find python file", "find docx", "find excel", "find pdf"))
            or (any(w in low for w in ("find", "search", "locate")) and any(w in low for w in ("file", "files", "document", "spreadsheet", "excel", "pdf", "docx", "presentation", "pptx", "script", "folder")) and not any(w in low for w in ("google", "browser", "youtube", "web", "internet", "flight", "news")))
        )
        if is_file_search and not any(w in low for w in ("create", "write", "generate", "send", "convert")):
            # Extract extension or query
            m_ext = re.search(r"\b(pdf|docx|xlsx|csv|pptx|png|jpg|jpeg|py|txt|json|zip)\b", low)
            ext_found = m_ext.group(1) if m_ext else ""
            
            # Clean query
            clean_q = re.sub(r"^(?:please\s+)?(?:find|search(?:\s+my\s+computer)?(?:\s+for)?|locate)\s+(?:my\s+|the\s+|all\s+)?", "", raw, flags=re.IGNORECASE).strip()
            clean_q = re.sub(r"\s*(?:files?|documents?|spreadsheet|presentation)\s*$", "", clean_q, flags=re.IGNORECASE).strip()

            search_path = "home"
            if "pictures" in low: search_path = "pictures"
            elif "documents" in low: search_path = "documents"
            elif "downloads" in low: search_path = "downloads"
            elif "desktop" in low: search_path = "desktop"

            return RouteDecision(
                is_deterministic=True,
                tool_name="file_controller",
                action="find",
                parameters={
                    "action": "find",
                    "name": clean_q,
                    "extension": ext_found,
                    "path": search_path,
                },
                rationale=f"Routed directly to Shared File Explorer search for query '{clean_q}' (ext: {ext_found or 'any'}, path: {search_path}).",
            )

        # 5C. List directory files
        if any(low.startswith(p) for p in ("list files", "show files", "what files are in", "ls ", "dir ")) or (any(w in low for w in ("list", "show")) and any(w in low for w in ("desktop", "documents", "downloads", "folder")) and not any(w in low for w in ("layout", "slide", "code", "app"))):
            target_dir = "desktop"
            if "documents" in low: target_dir = "documents"
            elif "downloads" in low: target_dir = "downloads"
            elif "pictures" in low: target_dir = "pictures"
            return RouteDecision(
                is_deterministic=True,
                tool_name="file_controller",
                action="list",
                parameters={"action": "list", "path": target_dir},
                rationale=f"Routed directly to list files in '{target_dir}'.",
            )

        # 5D. System Settings (Volume, Brightness, Wi-Fi, Diagnostics)
        if any(w in low for w in ("volume", "brightness", "wifi", "wi-fi", "bluetooth", "battery status", "system diagnostics", "mute", "unmute")) and not any(w in low for w in ("create", "write", "send")):
            if "volume" in low or "mute" in low:
                m_vol = re.search(r"\b(\d{1,3})\b", low)
                vol_val = int(m_vol.group(1)) if m_vol else (0 if "mute" in low else 50)
                setting_act = "mute" if "mute" in low and "unmute" not in low else "volume"
                return RouteDecision(
                    is_deterministic=True,
                    tool_name="computer_settings",
                    action=setting_act,
                    parameters={"setting": setting_act, "value": vol_val},
                    rationale=f"Routed directly to System Control for {setting_act}.",
                )
            elif "brightness" in low:
                m_br = re.search(r"\b(\d{1,3})\b", low)
                br_val = int(m_br.group(1)) if m_br else 70
                return RouteDecision(
                    is_deterministic=True,
                    tool_name="computer_settings",
                    action="brightness",
                    parameters={"setting": "brightness", "value": br_val},
                    rationale="Routed directly to System Control for brightness.",
                )
            elif "battery" in low:
                return RouteDecision(
                    is_deterministic=True,
                    tool_name="computer_settings",
                    action="battery",
                    parameters={"setting": "battery"},
                    rationale="Routed directly to inspect battery status.",
                )


        # ── 6. DOCUMENT GENERATION (WORD .DOCX & PATTERNS) ────────────────────
        is_doc_keyword = any(w in low for w in (
            "create a docx", "generate docx", "write a word document", "create a word document",
            "word document containing", "word document about", "document containing",
            "create a report", "write a report", "create a word doc", "generate a report",
            "create a document", "write a document", "draft a document", "create docx",
        ))
        is_pattern_doc = any(act in low for act in ("create", "generate", "write", "draft", "make", "produce", "build")) and any(pat in low for pat in (
            "biography", "product report", "product review", "comparative analysis", "comparison report",
            "step-by-step tutorial", "tutorial", "how-to guide", "research paper", "academic paper",
            "research proposal", "literature review", "systematic review", "business plan", "business proposal",
            "case study", "technical report", "system design document", "project report", "feasibility study",
            "historical analysis", "study guide", "policy report", "technical explainer", "scientific explainer",
            "incident report", "travel guide", "literary analysis", "country overview", "general overview"
        )) and not any(ppt_kw in low for ppt_kw in ("ppt", "presentation", "slides", "powerpoint"))

        if (is_doc_keyword or is_pattern_doc) and not any(k in low for k in ("google doc", "google document", "gdoc", "google form", "mental health", "pdf")):
            if any(w in low for w in ("convert", "send", "whatsapp")):
                return None
            m_topic = re.search(r"(?:about|on|explaining|for|of|containing\s+\d+[\d,]*\s+words\s+about)\s+(.+)$", raw, re.IGNORECASE)
            topic = m_topic.group(1).strip() if m_topic else raw.strip()
            m_wc = re.search(r"(\d[\d,]*)\s*words?\b", raw, re.IGNORECASE)
            target_words = int(m_wc.group(1).replace(",", "")) if m_wc else None
            doc_params: Dict[str, Any] = {
                "title": topic.title(),
                "instruction": raw,
            }
            if target_words:
                doc_params["target_words"] = target_words
            return RouteDecision(
                is_deterministic=True,
                tool_name="document_tool",
                action="create",
                parameters=doc_params,
                rationale=f"Routed directly to Document Agent for Word (.docx) generation on '{topic}' ({target_words or 'standard'} words).",
            )

        # ── 6B. PRESENTATION / PPT GENERATION ─────────────────────────────────
        if any(w in low for w in ("create a ppt", "generate ppt", "make a ppt", "create ppt", "create a presentation", "make a presentation", "generate presentation", "create a powerpoint", "create powerpoint", "powerpoint presentation", "make a powerpoint", "generate a presentation")) and not any(w in low for w in ("convert", "turn", "image", "images", "from image", "from images", "pdf", "combine")):
            m_topic = re.search(r"(?:about|on|explaining|for)\s+(.+)$", raw, re.IGNORECASE)
            topic = m_topic.group(1).strip() if m_topic else "Overview"
            m_sl = re.search(r"(\d+)\s*(?:slides?|slide)\b", raw, re.IGNORECASE)
            req_slides = int(m_sl.group(1)) if m_sl else None
            ppt_params: Dict[str, Any] = {
                "title": topic.title(),
                "subtitle": f"Executive Presentation on {topic.title()}",
            }
            if req_slides:
                ppt_params["slide_count"] = min(max(5, req_slides), 30)
            else:
                ppt_params["slide_count"] = 10
            return RouteDecision(
                is_deterministic=True,
                tool_name="presentation_tool",
                action="create",
                parameters=ppt_params,
                rationale=f"Routed directly to Presentation Agent for PowerPoint (.pptx) generation on '{topic}'.",
            )

        # ── 6C. PDF GENERATION ────────────────────────────────────────────────
        if any(w in low for w in ("create a pdf", "generate a pdf", "create pdf", "generate pdf", "make a pdf", "write a pdf")) and not any(w in low for w in ("convert", "send", "whatsapp")):
            m_topic = re.search(r"(?:about|on|explaining|for)\s+(.+)$", raw, re.IGNORECASE)
            topic = m_topic.group(1).strip() if m_topic else "Overview"
            pdf_fname = f"{re.sub(r'[^a-zA-Z0-9]+', '_', topic.lower()).strip('_') or 'document'}.pdf"
            return RouteDecision(
                is_deterministic=True,
                tool_name="document_tool",
                action="create",
                parameters={
                    "title": topic.title(),
                    "instruction": raw,
                    "target_format": "pdf",
                    "filename": pdf_fname,
                },
                rationale=f"Routed directly to Document Agent for PDF generation on '{topic}'.",
            )

        # ── 6B-2. PRESENTATION LAYOUTS CATALOG ────────────────────────────────
        if any(w in low for w in ("list layouts", "show layouts", "presentation layouts", "ppt layouts", "available layouts", "layout catalog")):
            return RouteDecision(
                is_deterministic=True,
                tool_name="presentation_tool",
                action="list_layouts",
                parameters={"action": "list_layouts"},
                rationale="Routed directly to Presentation Tool to list available human-centric layouts.",
            )

        # ── 6D. FILE CONVERSION & COMPRESSION ────────────────────────────────
        # A. Google Docs to PDF
        if ("google doc" in low or "gdoc" in low) and ("pdf" in low or "export" in low):
            m_gdoc = re.search(r"(?:doc|document|gdoc)?\s*(?:id|url)?\s*[:\s]?\s*([a-zA-Z0-9_\-\/:\.]+)", raw, re.IGNORECASE)
            target_doc = m_gdoc.group(1).strip() if m_gdoc else "this document"
            return RouteDecision(
                is_deterministic=True,
                tool_name="convert_file",
                action="gdoc_to_pdf",
                parameters={"input_file": target_doc, "action": "gdoc_to_pdf", "target_format": "pdf"},
                rationale=f"Routed directly to Google Docs to PDF export for '{target_doc}'.",
            )

        # B. Video compression
        if ("compress" in low or "reduce" in low or "shrink" in low) and any(w in low for w in ("video", "mp4", "mkv", "mov", "avi", "webm")):
            m_vid = re.search(r"(\S+\.(?:mp4|mov|mkv|avi|webm))", raw, re.IGNORECASE)
            vid_file = m_vid.group(1) if m_vid else "this file"
            mode = "balanced"
            if "high quality" in low or "best quality" in low or "preserving good quality" in low:
                mode = "high_quality"
            elif "maximum" in low or "smallest" in low or "max" in low:
                mode = "maximum"
            m_mb = re.search(r"(\d+(?:\.\d+)?)\s*(?:mb|megabytes?)\b", low)
            tgt_mb = float(m_mb.group(1)) if m_mb else None
            return RouteDecision(
                is_deterministic=True,
                tool_name="convert_file",
                action="compress_video",
                parameters={"input_file": vid_file, "action": "compress_video", "mode": mode, "target_size_mb": tgt_mb, "target_format": "mp4"},
                rationale=f"Routed directly to Video Compressor ({mode} mode) for '{vid_file}'.",
            )

        # C. Images to PowerPoint Presentation
        if ("image" in low or "images" in low or "photo" in low or "photos" in low) and any(w in low for w in ("powerpoint", "presentation", "slides", "pptx", "ppt")):
            m_multi_img = re.findall(r"[\w\-]+\.(?:png|jpg|jpeg|webp|bmp)\b", raw, re.IGNORECASE)
            img_target = m_multi_img if len(m_multi_img) > 1 else (m_multi_img[0] if m_multi_img else "this file")
            mode = "presentation" if "presentation" in low and "full" not in low else "full_image"
            return RouteDecision(
                is_deterministic=True,
                tool_name="convert_file",
                action="images_to_pptx",
                parameters={"input_file": img_target, "action": "images_to_pptx", "mode": mode, "target_format": "pptx"},
                rationale=f"Routed directly to PowerPoint Creation from Images ({mode} mode).",
            )

        # D. Images to PDF
        if ("image" in low or "images" in low or "photo" in low or "photos" in low) and "pdf" in low and not any(w in low for w in ("create a document", "docx", "word")):
            m_multi_img = re.findall(r"[\w\-]+\.(?:png|jpg|jpeg|webp|bmp)\b", raw, re.IGNORECASE)
            img_target = m_multi_img if len(m_multi_img) > 1 else (m_multi_img[0] if m_multi_img else "this file")
            psize = "Letter" if "letter" in low else ("A4" if "a4" in low else "fit_image")
            return RouteDecision(
                is_deterministic=True,
                tool_name="convert_file",
                action="images_to_pdf",
                parameters={"input_file": img_target, "action": "images_to_pdf", "page_size": psize, "target_format": "pdf"},
                rationale=f"Routed directly to Images-to-PDF compiler for '{img_target}'.",
            )

        # E. PDF to PowerPoint Slides
        if "pdf" in low and any(w in low for w in ("powerpoint", "slides", "pptx", "presentation")) and "convert" in low:
            m_pdf = re.search(r"(\S+\.pdf)", raw, re.IGNORECASE)
            pdf_file = m_pdf.group(1) if m_pdf else "this file"
            mode = "editable" if "editable" in low else "page_faithful"
            return RouteDecision(
                is_deterministic=True,
                tool_name="convert_file",
                action="pdf_to_pptx",
                parameters={"input_file": pdf_file, "action": "pdf_to_pptx", "mode": mode, "target_format": "pptx"},
                rationale=f"Routed directly to PDF to PowerPoint ({mode} mode) for '{pdf_file}'.",
            )

        # F. Compression for PDF, Office, or Images
        if any(w in low for w in ("compress", "reduce file size", "reduce size", "shrink")) and not any(w in low for w in ("video", "mp4")):
            m_f = re.search(r"(\S+\.(?:pdf|docx|pptx|xlsx|jpg|png|webp|zip))", raw, re.IGNORECASE)
            f_target = m_f.group(1) if m_f else "this file"
            ext = Path(f_target).suffix.lower()
            c_action = "compress_office" if ext in (".docx", ".pptx", ".xlsx") else ("compress_image" if ext in (".jpg", ".png", ".webp") else "compress_file")
            return RouteDecision(
                is_deterministic=True,
                tool_name="convert_file",
                action=c_action,
                parameters={"input_file": f_target, "action": c_action, "target_format": ext.lstrip(".") or "pdf"},
                rationale=f"Routed directly to File Compressor for '{f_target}'.",
            )

        # G. Standard File Conversion: "convert <file> to <format>" or "turn this into <format>"
        m_conv = re.search(r"\b(?:convert|turn)\s+(?:the\s+)?([a-zA-Z0-9_\-\.\\\/:\s]+?)\s+(?:in)?to\s+(?:a\s+|an\s+)?([a-zA-Z0-9]+)\b", low)
        if m_conv and not any(w in low for w in (" and ", " then ", "send", "whatsapp")):
            src_file = m_conv.group(1).strip()
            tgt_fmt = m_conv.group(2).strip().lower()
            return RouteDecision(
                is_deterministic=True,
                tool_name="convert_file",
                action="convert",
                parameters={"input_file": src_file, "target_format": tgt_fmt},
                rationale=f"Routed directly to Universal File Converter for '{src_file}' -> {tgt_fmt.upper()}.",
            )

        # ── 6E. POWERPOINT IMAGE INSERTION ───────────────────────────────────
        if any(w in low for w in ("insert image", "add image", "insert picture", "add picture")) and any(w in low for w in ("slide", "presentation", "powerpoint", "pptx")):
            m_slide = re.search(r"slide\s+(\d+)", low)
            slide_no = int(m_slide.group(1)) if m_slide else 1
            m_img = re.search(r"(\S+\.(?:png|jpg|jpeg|webp|bmp))", raw, re.IGNORECASE)
            m_pptx = re.search(r"(\S+\.pptx)", raw, re.IGNORECASE)
            img_target = m_img.group(1) if m_img else ""
            if not img_target:
                m_of = re.search(r"(?:image|picture)\s+(?:of\s+)?([A-Za-z0-9_\-\s]+?)(?:\s+(?:into|in|to)\s+|\s*$)", raw, re.IGNORECASE)
                if m_of:
                    img_target = m_of.group(1).strip()

            return RouteDecision(
                is_deterministic=True,
                tool_name="presentation_tool",
                action="insert_image",
                parameters={
                    "action": "insert_image",
                    "slide_number": slide_no,
                    "image_path": img_target,
                    "presentation_path": m_pptx.group(1) if m_pptx else "",
                },
                rationale=f"Routed directly to PowerPoint Tool for image insertion into slide {slide_no}.",
            )

        # ── 6F. WORD DOCUMENT IMAGE INSERTION ────────────────────────────────
        if any(w in low for w in ("insert image", "add image", "insert picture", "add picture")) and any(w in low for w in ("word", "document", "docx", "doc", "report")) and not any(w in low for w in ("slide", "presentation", "powerpoint", "pptx")):
            m_doc = re.search(r"(\S+\.docx)", raw, re.IGNORECASE)
            m_img = re.search(r"(\S+\.(?:png|jpg|jpeg|webp|bmp))", raw, re.IGNORECASE)
            img_target = m_img.group(1) if m_img else ""
            if not img_target:
                m_of = re.search(r"(?:image|picture)\s+(?:of\s+)?([A-Za-z0-9_\-\s]+?)(?:\s+(?:into|in|to)\s+|\s*$)", raw, re.IGNORECASE)
                if m_of:
                    img_target = m_of.group(1).strip()

            return RouteDecision(
                is_deterministic=True,
                tool_name="document_tool",
                action="insert_image",
                parameters={
                    "action": "insert_image",
                    "document_path": m_doc.group(1) if m_doc else "",
                    "image_path": img_target,
                },
                rationale="Routed directly to Word Document Tool for image insertion.",
            )

        # ── 6C. AUTONOMOUS SELF-LEARNING & TASK ACQUISITION ───────────────────
        if any(w in low for w in ("learn how to", "search internet to", "learn and execute", "find on internet and", "search online how to", "search internet and do", "learn and do")):
            m_task = re.search(r"(?:learn\s+how\s+to|search\s+internet\s+to|learn\s+and\s+execute|search\s+online\s+how\s+to|search\s+internet\s+and\s+do|learn\s+and\s+do)\s+(.+)$", raw, re.IGNORECASE)
            task_desc = m_task.group(1).strip() if m_task else raw
            return RouteDecision(
                is_deterministic=True,
                tool_name="self_learning_tool",
                action="learn_and_execute",
                parameters={"task_description": task_desc, "save_skill": True},
                rationale=f"Routed directly to Autonomous Self-Learning Agent to research, synthesize code, and execute: '{task_desc}'.",
            )

        # ── 7. AUTONOMOUS CODING, GITHUB RESEARCH & ML PROJECTS ──────────────
        if any(w in low for w in ("search github", "find github", "research github", "github repository")):
            return RouteDecision(
                is_deterministic=True,
                tool_name="coding_agent",
                action="research_github",
                parameters={"query": raw},
                rationale="Routed to Autonomous Coding Agent for GitHub repository research.",
            )

        if any(w in low for w in (
            "train model", "train a model", "machine learning", "deep learning", "train classifier",
            "train regression", "ml project", "kaggle dataset", "hugging face dataset", "train neural network"
        )):
            return RouteDecision(
                is_deterministic=True,
                tool_name="coding_agent",
                action="train_ml_project",
                parameters={"name": "jarvis_ml_project", "requirement": raw},
                rationale="Routed to Autonomous Machine Learning Agent for dataset research, pipeline creation, and training.",
            )

        if any(w in low for w in ("create a python", "build a python", "create an app", "create a simple", "build a calculator", "create a streamlit", "create a website", "write code for", "make a python calculator")):
            return RouteDecision(
                is_deterministic=True,
                tool_name="coding_agent",
                action="generate_and_build",
                parameters={"requirement": raw},
                rationale="Routed to Autonomous Coding Agent for software lifecycle execution.",
            )

        # ── 8. LIVE NEWS RETRIEVAL ───────────────────────────────────────────
        if any(w in low for w in ("news", "headlines", "overall news", "daily briefing")) or low in ("world", "india", "south india", "telangana", "andhra pradesh"):
            from actions.news_service import NewsService
            cat, topic = NewsService.identify_category_and_topic(raw)
            if cat != "ask_clarification":
                return RouteDecision(
                    is_deterministic=True,
                    tool_name="news_service",
                    action="get_live_news",
                    parameters={"category": cat, "topic": topic, "recency": "today"},
                    rationale=f"Routed directly to Live News Service for category '{cat}' (topic: '{topic}').",
                )

        # ── 9. DOWNLOAD & INSTALLATION ────────────────────────────────────────
        if any(w in low for w in ("download", "install")) and not any(w in low for w in ("create", "build a", "write code")):
            m_url = re.search(r"https?://[^\s\)\"\'>]+", raw)
            url_str = m_url.group(0) if m_url else ""
            clean_name = re.sub(r"\b(?:please\s+)?(?:download|install|and\s+install)\b", "", raw, flags=re.IGNORECASE).strip()
            return RouteDecision(
                is_deterministic=True,
                tool_name="download_manager",
                action="download",
                parameters={
                    "url": url_str,
                    "software_name": clean_name if not url_str else "",
                    "install": "install" in low,
                },
                rationale="Routed directly to Download & Installation Manager.",
            )

        # ── 10. COMPUTER SETTINGS (VOLUME / BRIGHTNESS) ───────────────────────
        if any(w in low for w in ("volume", "brightness", "mute", "unmute")):
            action = "volume_up"
            if "down" in low or "lower" in low or "decrease" in low:
                action = "volume_down" if "volume" in low else "brightness_down"
            elif "up" in low or "higher" in low or "increase" in low:
                action = "volume_up" if "volume" in low else "brightness_up"
            elif "mute" in low:
                action = "mute"
            elif "unmute" in low:
                action = "unmute"
            elif "set" in low or "to " in low:
                action = "volume_set"
            m_val = re.search(r"(\d+)", raw)
            val = m_val.group(1) if m_val else None
            return RouteDecision(
                is_deterministic=True,
                tool_name="computer_settings",
                action=action,
                parameters={"action": action, "value": val},
                rationale=f"Routed directly to Computer Settings for '{action}'.",
            )

        # Complex multi-step task requiring full planning graph
        return None
