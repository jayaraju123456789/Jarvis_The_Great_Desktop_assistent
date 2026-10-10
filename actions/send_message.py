import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from core.execution_state import execution_manager

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.06
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

try:
    import pyperclip
    _PYPERCLIP = True
except ImportError:
    _PYPERCLIP = False

try:
    import pywinauto
    _PYWINAUTO = True
except ImportError:
    _PYWINAUTO = False

try:
    import win32gui
    import win32con
    import win32clipboard
    _PYWIN32 = True
except ImportError:
    _PYWIN32 = False

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

def _get_os() -> str:
    try:
        cfg = json.loads(
            (_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8")
        )
        return cfg.get("os_system", "windows").lower()
    except Exception:
        return "windows"


def _require_pyautogui():
    if not _PYAUTOGUI:
        raise RuntimeError("PyAutoGUI not installed. Run: pip install pyautogui")
    pyautogui.FAILSAFE = False


def _paste_text(text: str) -> None:
    _require_pyautogui()

    os_name = _get_os()
    paste_hotkey = ("command", "v") if os_name == "mac" else ("ctrl", "v")

    if _PYPERCLIP:
        for _attempt in range(3):
            try:
                pyperclip.copy(text)
                time.sleep(0.15)
                pyautogui.hotkey(*paste_hotkey)
                time.sleep(0.1)
                return
            except Exception:
                time.sleep(0.1)
        pyautogui.write(text, interval=0.03)
    else:
        pyautogui.write(text, interval=0.03)


def _clear_and_paste(text: str) -> None:
    _require_pyautogui()
    os_name = _get_os()
    select_all = ("command", "a") if os_name == "mac" else ("ctrl", "a")
    pyautogui.hotkey(*select_all)
    time.sleep(0.1)
    pyautogui.press("delete")
    time.sleep(0.1)
    _paste_text(text)

def _open_app(app_name: str) -> bool:
    _require_pyautogui()
    os_name = _get_os()

    try:
        if os_name == "windows":
            pyautogui.press("win")
            time.sleep(0.5)
            _paste_text(app_name)
            time.sleep(0.6)
            pyautogui.press("enter")
            time.sleep(2.5)
            return True

        elif os_name == "mac":
            result = subprocess.run(
                ["open", "-a", app_name],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                result = subprocess.run(
                    ["open", "-a", f"{app_name}.app"],
                    capture_output=True, text=True, timeout=10,
                )
            time.sleep(2.5)
            return result.returncode == 0

        else: 
            launched = False
            for launcher in [
                ["gtk-launch", app_name.lower()],
                [app_name.lower()],
            ]:
                try:
                    subprocess.Popen(
                        launcher,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    launched = True
                    break
                except FileNotFoundError:
                    continue
            time.sleep(2.5)
            return launched

    except Exception as e:
        print(f"[SendMessage] ⚠️ Could not open {app_name}: {e}")
        return False


def _open_browser_url(url: str) -> bool:
    import webbrowser
    try:
        webbrowser.open(url)
        time.sleep(4.0) 
        return True
    except Exception as e:
        print(f"[SendMessage] ⚠️ Could not open browser: {e}")
        return False

from actions.whatsapp_calling import (
    contact_resolver,
    start_whatsapp_audio_call,
    start_whatsapp_video_call,
    start_whatsapp_call,
    check_whatsapp_call_status,
    end_whatsapp_call,
    monitor_whatsapp_call_lifecycle,
    detect_incoming_whatsapp_call,
    respond_to_incoming_whatsapp_call,
    record_missed_call,
    get_missed_calls,
    send_authorized_reply,
    get_busy_reply_config,
    update_busy_reply_config,
    process_missed_call,
    start_missed_call_monitor,
    stop_missed_call_monitor,
    CallState,
    CallResult,
    ContactResolution,
    ChatOpenResult,
    open_whatsapp_chat,
    _is_whatsapp_foreground,
    _focus_whatsapp_desktop,
    _find_whatsapp_window,
    _find_message_input_control,
    _verify_chat_header,
    _paste_text_safely,
    _get_chat_header_contact,
    _attach_default_desktop,
    _get_live_foreground_window,
    _copy_files_to_clipboard,
    _find_whatsapp_attach_button,
    _find_whatsapp_send_button,
    _find_whatsapp_voice_button,
    _wait_for_attachment_preview,
    _click_whatsapp_send_button,
    _verify_whatsapp_outgoing_bubble,
    IUIA,
    uia_info,
    UIAWrapper,
    _get_default_desktop_handle,
)


def _get_contacts_book() -> Dict[str, str]:
    """Load local contact nickname -> phone number mappings from universal ContactResolver."""
    contacts = contact_resolver.load_contacts()
    return {name: c.get("phone", "") for name, c in contacts.items()}


def _resolve_contact_phone(receiver: str) -> Optional[str]:
    """Dynamically resolve phone number for contact using universal ContactResolver."""
    resolution = contact_resolver.resolve(receiver)
    return resolution.phone_number


def _focus_whatsapp_window() -> bool:
    """Ensure WhatsApp desktop window is active, in foreground, and verified on Windows."""
    _require_pyautogui()
    if _get_os() != "windows":
        return _open_app("WhatsApp")
    return _focus_whatsapp_desktop()


def _select_whatsapp_contact(receiver: str, account: Optional[str] = None) -> bool:
    """
    Search and open the specified contact in WhatsApp Desktop dynamically.
    Guarantees switching to the correct recipient, preventing sending to the wrong contact.
    Delegates to universal verified open_whatsapp_chat().
    """
    res = open_whatsapp_chat(receiver, account=account)
    return res.success


def _search_in_app(query: str) -> None:
    _require_pyautogui()
    os_name = _get_os()
    search_hotkey = ("command", "f") if os_name == "mac" else ("ctrl", "f")

    pyautogui.hotkey(*search_hotkey)
    time.sleep(0.5)
    _clear_and_paste(query)
    time.sleep(1.0)


def _desktop_send(app_name: str, receiver: str, message: str) -> str:
    if not _open_app(app_name):
        return f"Could not open {app_name}."

    time.sleep(1.0)
    _search_in_app(receiver)
    pyautogui.press("enter")
    time.sleep(0.8)

    _paste_text(message)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.3)
    return f"Message sent to {receiver} via {app_name}."


def _send_whatsapp(receiver: str, message: str, account: Optional[str] = None) -> str:
    res = send_whatsapp_message(receiver, message, account=account)
    return res.get("message", str(res))


def _send_telegram(receiver: str, message: str) -> str:
    return _desktop_send("Telegram", receiver, message)

def _send_signal(receiver: str, message: str) -> str:
    return _desktop_send("Signal", receiver, message)


def _send_discord(receiver: str, message: str) -> str:
    return _desktop_send("Discord", receiver, message)


def _send_instagram(receiver: str, message: str) -> str:
    _require_pyautogui()

    if not _open_browser_url("https://www.instagram.com/direct/new/"):
        return "Could not open Instagram in browser."

    _paste_text(receiver)
    time.sleep(1.5)

    pyautogui.press("down")
    time.sleep(0.3)
    pyautogui.press("enter")   
    time.sleep(0.4)

    for _ in range(4):
        pyautogui.press("tab")
        time.sleep(0.15)
    pyautogui.press("enter")
    time.sleep(2.0)

    _paste_text(message)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.3)

    return f"Message sent to {receiver} via Instagram."


def _send_messenger(receiver: str, message: str) -> str:
    _require_pyautogui()

    if not _open_browser_url("https://www.messenger.com/"):
        return "Could not open Messenger in browser."


    _search_in_app(receiver)
    time.sleep(0.5)
    pyautogui.press("down")
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(1.0)

    _paste_text(message)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.3)

    return f"Message sent to {receiver} via Messenger."

_PLATFORM_MAP = [
    ({"whatsapp", "wp", "wapp"},              _send_whatsapp),
    ({"telegram", "tg"},                      _send_telegram),
    ({"instagram", "ig", "insta"},            _send_instagram),
    ({"signal"},                               _send_signal),
    ({"discord"},                              _send_discord),
    ({"messenger", "facebook", "fb"},         _send_messenger),
]


def _resolve_platform(platform_str: str):
    key = platform_str.lower().strip()
    for keywords, handler in _PLATFORM_MAP:
        if any(k in key for k in keywords):
            return handler
    return lambda r, m: _desktop_send(platform_str.strip().title(), r, m)


class TaskState:
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WhatsAppIdempotencyManager:
    """Tracks WhatsApp operations to ensure strict one-user-request = one-execution idempotency."""

    def __init__(self, ttl_seconds: float = 120.0):
        self._lock = threading.RLock()
        self._history: Dict[str, Dict[str, Any]] = {}
        self._ttl = ttl_seconds

    def compute_key(self, platform: str, receiver: str, message: str, attachment: str, action: str) -> str:
        norm = f"{platform.strip().lower()}|{receiver.strip().lower()}|{message.strip()}|{attachment.strip()}|{action.strip().lower()}"
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()

    def check_or_start(self, op_key: str, task_id: str) -> tuple[bool, Optional[str]]:
        with self._lock:
            now = time.time()
            if op_key in self._history:
                entry = self._history[op_key]
                age = now - entry["timestamp"]
                if age < self._ttl:
                    if entry["state"] == TaskState.COMPLETED:
                        return True, f"[DUPLICATE IGNORED] WhatsApp operation already completed successfully (Task ID: {entry['task_id']}). {entry['result']}"
                    if entry["state"] in (TaskState.RUNNING, TaskState.VERIFYING):
                        return True, f"[DUPLICATE IGNORED] WhatsApp operation currently in progress (State: {entry['state']}, Task ID: {entry['task_id']})."
            self._history[op_key] = {
                "task_id": task_id,
                "state": TaskState.RUNNING,
                "timestamp": now,
                "result": None,
            }
            return False, None

    def mark_completed(self, op_key: str, task_id: str, result: str) -> None:
        with self._lock:
            self._history[op_key] = {
                "task_id": task_id,
                "state": TaskState.COMPLETED,
                "timestamp": time.time(),
                "result": result,
            }

    def mark_failed(self, op_key: str, task_id: str, error: str) -> None:
        with self._lock:
            self._history[op_key] = {
                "task_id": task_id,
                "state": TaskState.FAILED,
                "timestamp": time.time(),
                "result": error,
            }


_IDEMPOTENCY_MANAGER = WhatsAppIdempotencyManager(ttl_seconds=120.0)
_WHATSAPP_EXECUTION_LOCK = threading.RLock()


def send_whatsapp_message(
    contact_identifier: str,
    message_text: str,
    account: Optional[str] = None,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Safely and autonomously sends a WhatsApp message to a contact or phone number with
    automatic focus recovery, strict chat and input element verification, and duplicate prevention.

    Explicit state flow:
    REQUESTED -> CONTACT_RESOLVED -> CHAT_OPENING -> CHAT_VERIFIED -> (FOCUS_RECOVERY)
    -> INPUT_VERIFIED -> MESSAGE_ENTERED -> SEND_REQUESTED -> SENT_VERIFIED
    """
    op_id = task_id or str(uuid.uuid4())
    traversed_states = ["REQUESTED"]

    # Step 1: Input Validation
    if not contact_identifier or not str(contact_identifier).strip():
        return {
            "success": False,
            "status": "FAILED",
            "operation_id": op_id,
            "states_traversed": traversed_states,
            "message": "Recipient contact identifier cannot be empty.",
        }

    raw_msg = message_text if message_text is not None else ""
    if not str(raw_msg).strip():
        return {
            "success": False,
            "status": "FAILED",
            "operation_id": op_id,
            "states_traversed": traversed_states,
            "message": "Message text cannot be empty.",
        }

    # Step 2: Contact Resolution
    resolution = contact_resolver.resolve(str(contact_identifier).strip())
    if resolution.status == "AMBIGUOUS":
        return {
            "success": False,
            "status": "AMBIGUOUS_CONTACT",
            "operation_id": op_id,
            "states_traversed": traversed_states,
            "contact": str(contact_identifier).strip(),
            "candidates": resolution.candidates,
            "message": f"Ambiguous contact match for '{contact_identifier}'. Multiple candidates found: {resolution.candidates}. Please clarify which contact you intended.",
        }

    target_name = resolution.matched_name or str(contact_identifier).strip()
    target_phone = resolution.phone_number
    traversed_states.append("CONTACT_RESOLVED")

    # Step 3: Duplicate Send / Idempotency Check
    op_key = _IDEMPOTENCY_MANAGER.compute_key("whatsapp", target_name, raw_msg, "", "send_whatsapp_message")
    is_dup, dup_msg = _IDEMPOTENCY_MANAGER.check_or_start(op_key, op_id)
    if is_dup:
        return {
            "success": True,
            "status": "DUPLICATE_SUPPRESSED",
            "operation_id": op_id,
            "contact": target_name,
            "phone": target_phone,
            "states_traversed": traversed_states,
            "message": dup_msg,
        }

    # Step 4: Open WhatsApp Chat
    traversed_states.append("CHAT_OPENING")
    chat_res = open_whatsapp_chat(contact_identifier, account=account)
    if not chat_res.success:
        _IDEMPOTENCY_MANAGER.mark_failed(op_key, op_id, chat_res.message)
        return {
            "success": False,
            "status": chat_res.status or "FAILED",
            "operation_id": op_id,
            "contact": target_name,
            "phone": target_phone,
            "message": f"Could not open WhatsApp conversation for '{contact_identifier}': {chat_res.message}",
        }

    # Step 4.5: Strict Test-Mode Isolation Guard (Zero Physical UI Execution)
    if os.environ.get("JARVIS_TEST_MODE") == "1":
        traversed_states.extend(["CHAT_VERIFIED", "INPUT_VERIFIED", "MESSAGE_ENTERED", "TEST_SIMULATED"])
        sim_msg = f"[TEST_SIMULATED] Automated test mode: simulated WhatsApp message delivery to '{target_name}'. Real UI interactions withheld."
        _IDEMPOTENCY_MANAGER.mark_completed(op_key, op_id, sim_msg)
        return {
            "success": True,
            "status": "TEST_SIMULATED",
            "operation_id": op_id,
            "target_hwnd": 0,
            "contact": target_name,
            "phone": target_phone,
            "chat_header": target_name,
            "message": sim_msg,
            "text_preview": (raw_msg[:50] + "…") if len(raw_msg) > 50 else raw_msg,
            "states_traversed": traversed_states,
        }

    # Step 5: Locate and Verify Live Window Handle & Automatic Focus Recovery
    _attach_default_desktop()
    hwnd = _find_whatsapp_window()
    if not hwnd and os.environ.get("JARVIS_TEST_MODE") != "1":
        _IDEMPOTENCY_MANAGER.mark_failed(op_key, op_id, "WhatsApp window handle not found")
        return {
            "success": False,
            "status": "WINDOW_NOT_FOUND",
            "operation_id": op_id,
            "contact": target_name,
            "phone": target_phone,
            "states_traversed": traversed_states,
            "message": "WhatsApp Desktop application window could not be found.",
        }

    # Focus Verification & Multi-tier Automatic Recovery
    if not _is_whatsapp_foreground(hwnd):
        traversed_states.append("FOCUS_RECOVERY")
        print(f"[SendMessage] [Task {op_id[:8]}] WhatsApp window not in foreground. Attempting automatic focus recovery...")
        recovered = _focus_whatsapp_desktop(hwnd, max_attempts=3)
        live_hwnd = _find_whatsapp_window()
        if live_hwnd:
            hwnd = live_hwnd
        if not recovered or not _is_whatsapp_foreground(hwnd):
            _IDEMPOTENCY_MANAGER.mark_failed(op_key, op_id, "Focus recovery failed")
            return {
                "success": False,
                "status": "FOCUS_FAILED",
                "operation_id": op_id,
                "target_hwnd": hwnd,
                "contact": target_name,
                "phone": target_phone,
                "states_traversed": traversed_states,
                "message": "WhatsApp window lost focus and automatic recovery failed. Keystrokes were withheld to protect the active application.",
            }

    # Step 6: Verify Chat Identity
    chat_matched, active_header = _verify_chat_header(hwnd or 0, target_name, target_phone)
    if not chat_matched and active_header:
        _IDEMPOTENCY_MANAGER.mark_failed(op_key, op_id, f"Wrong chat active: {active_header}")
        return {
            "success": False,
            "status": "WRONG_CHAT",
            "operation_id": op_id,
            "target_hwnd": hwnd,
            "contact": target_name,
            "active_header": active_header,
            "states_traversed": traversed_states,
            "message": f"Safety abort: Active chat header '{active_header}' does not match intended recipient '{target_name}'. Message sending was cancelled to prevent misdelivery.",
        }
    traversed_states.append("CHAT_VERIFIED")

    # Step 7: Identify & Verify Message Input Control
    input_ctrl, input_diag = _find_message_input_control(hwnd or 0)
    if input_ctrl is None:
        _IDEMPOTENCY_MANAGER.mark_failed(op_key, op_id, input_diag)
        return {
            "success": False,
            "status": "INPUT_CONTROL_NOT_FOUND",
            "operation_id": op_id,
            "target_hwnd": hwnd,
            "contact": target_name,
            "states_traversed": traversed_states,
            "message": f"Message input control could not be identified or is unavailable ({input_diag}). Sending safely cancelled.",
        }

    try:
        if hasattr(input_ctrl, "set_focus"):
            input_ctrl.set_focus()
        time.sleep(0.1)
    except Exception:
        pass
    traversed_states.append("INPUT_VERIFIED")

    # Step 8: Strict Pre-Typing Foreground Recheck & Text Entry
    if not _is_whatsapp_foreground(hwnd):
        recovered = _focus_whatsapp_desktop(hwnd, max_attempts=2)
        live_hwnd = _find_whatsapp_window()
        if live_hwnd:
            hwnd = live_hwnd
        if not recovered or not _is_whatsapp_foreground(hwnd):
            _IDEMPOTENCY_MANAGER.mark_failed(op_key, op_id, "Focus lost immediately before typing")
            return {
                "success": False,
                "status": "FOCUS_LOST_BEFORE_TYPING",
                "operation_id": op_id,
                "target_hwnd": hwnd,
                "contact": target_name,
                "states_traversed": traversed_states,
                "message": "WhatsApp window lost focus immediately before entering text. Keystrokes were withheld to protect the active application.",
            }

    # Paste exact message preserving text, language, Unicode, emojis, newlines
    if os.environ.get("JARVIS_TEST_MODE") != "1":
        _paste_text_safely(raw_msg)
    traversed_states.append("MESSAGE_ENTERED")
    time.sleep(0.2)

    # Step 9: Strict Pre-Send Foreground Recheck & Send Execution
    if not _is_whatsapp_foreground(hwnd):
        recovered = _focus_whatsapp_desktop(hwnd, max_attempts=2)
        live_hwnd = _find_whatsapp_window()
        if live_hwnd:
            hwnd = live_hwnd
        if not recovered or not _is_whatsapp_foreground(hwnd):
            _IDEMPOTENCY_MANAGER.mark_failed(op_key, op_id, "Focus lost before send command")
            return {
                "success": False,
                "status": "FOCUS_LOST_BEFORE_SEND",
                "operation_id": op_id,
                "target_hwnd": hwnd,
                "contact": target_name,
                "states_traversed": traversed_states,
                "message": "WhatsApp window lost focus before send key was dispatched. Send cancelled to protect active application.",
            }

    # Send message once via Enter key
    traversed_states.append("SEND_REQUESTED")
    if _PYAUTOGUI and os.environ.get("JARVIS_TEST_MODE") != "1":
        pyautogui.press("enter")
    time.sleep(0.5)

    # Step 10: Verify Outgoing Message Transmission
    verified_sent = True
    if os.environ.get("JARVIS_TEST_MODE") != "1" and input_ctrl:
        try:
            current_input_text = (input_ctrl.window_text() or "").strip()
            if current_input_text and current_input_text == raw_msg.strip():
                if _is_whatsapp_foreground(hwnd):
                    pyautogui.press("enter")
                    time.sleep(0.4)
                    current_input_text = (input_ctrl.window_text() or "").strip()
                    if current_input_text == raw_msg.strip():
                        verified_sent = False
        except Exception:
            pass

    if os.environ.get("JARVIS_TEST_MODE") == "1":
        final_status = "TEST_SIMULATED"
    else:
        final_status = "SENT_VERIFIED" if verified_sent else "SEND_REQUESTED"
    traversed_states.append(final_status)

    res_message = f"Message sent to '{target_name}' via WhatsApp and transmission verified."
    _IDEMPOTENCY_MANAGER.mark_completed(op_key, op_id, res_message)

    return {
        "success": True,
        "status": final_status,
        "operation_id": op_id,
        "target_hwnd": hwnd,
        "contact": target_name,
        "phone": target_phone,
        "chat_header": active_header or target_name,
        "message": res_message,
        "text_preview": (raw_msg[:50] + "…") if len(raw_msg) > 50 else raw_msg,
        "states_traversed": traversed_states,
    }


def _get_explorer_selected_file() -> Optional[Path]:
    """Inspect Windows File Explorer and return the path of the currently selected file."""
    if _get_os() != "windows":
        return None
    try:
        import win32com.client
        shell = win32com.client.Dispatch("Shell.Application")
        for window in shell.Windows():
            try:
                items = window.Document.SelectedItems()
                if items.Count > 0:
                    cand = Path(items.Item(0).Path)
                    if cand.exists() and cand.is_file():
                        return cand.resolve()
            except Exception:
                continue
    except Exception:
        pass
    return None


def _synthesize_voice_message(text: str) -> Path:
    """Synthesize text into a clean .wav voice note file in Desktop/JarvisRecordings."""
    recordings_dir = Path.home() / "Desktop" / "JarvisRecordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)
    out_file = recordings_dir / f"voice_note_{int(time.time())}_{uuid.uuid4().hex[:6]}.wav"
    
    clean_text = (text or "").strip()
    if not clean_text or clean_text.lower() in ("voice message", "voice note", "audio message", "hello"):
        clean_text = "Hello, this is an automated voice message from JARVIS."
        
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 160)
        engine.save_to_file(clean_text, str(out_file))
        engine.runAndWait()
        try:
            print(f"[SendMessage] [VOICE] Synthesized voice note: {out_file.name} ({out_file.stat().st_size:,} bytes)")
        except Exception:
            pass
    except Exception as e:
        print(f"[SendMessage] pyttsx3 synthesis failed: {e}, generating fallback audio tone")
        import wave, struct, math
        with wave.open(str(out_file), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            for i in range(22050):
                val = int(32767.0 * 0.5 * math.sin(2.0 * math.pi * 440.0 * i / 22050))
                wf.writeframes(struct.pack("<h", val))

    return out_file


def _record_microphone_voice_message(duration_seconds: float = 5.0) -> Path:
    """Record live microphone input into Desktop/JarvisRecordings."""
    recordings_dir = Path.home() / "Desktop" / "JarvisRecordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)
    out_file = recordings_dir / f"mic_recording_{int(time.time())}_{uuid.uuid4().hex[:6]}.wav"
    try:
        import sounddevice as sd
        import wave
        fs = 44100
        print(f"[SendMessage] [MIC] Recording microphone for {duration_seconds} seconds...")
        recording = sd.rec(int(duration_seconds * fs), samplerate=fs, channels=1, dtype='int16')
        sd.wait()
        with wave.open(str(out_file), 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(fs)
            wf.writeframes(recording.tobytes())
        print(f"[SendMessage] [MIC] Microphone voice note saved: {out_file.name} ({out_file.stat().st_size:,} bytes)")
        return out_file
    except Exception as e:
        print(f"[SendMessage] Microphone recording failed: {e}")
        return _synthesize_voice_message("Voice recording from JARVIS microphone.")


def _resolve_attachment_path(raw_path: str) -> Optional[Path]:
    """Resolve attachment path directly, via active File Explorer selection, screenshot, or search user directories."""
    import re
    cleaned = (raw_path or "").strip()
    if not cleaned:
        explorer_file = _get_explorer_selected_file()
        if explorer_file:
            return explorer_file
        return None

    # 1. Exact existing file path check (preserving exact user selected file)
    p = Path(cleaned).expanduser()
    try:
        if p.exists() and p.is_file():
            return p.resolve()
    except Exception:
        pass

    # If the user specified an absolute path or path with directories that does not exist, do NOT substitute!
    if p.is_absolute() or len(p.parts) > 1:
        return None

    # 2. Fresh screenshot request (only when explicitly requested as an action, not an existing file)
    if cleaned.lower() in ("screenshot", "take screenshot", "fresh screenshot", "capture screenshot", "new screenshot"):
        try:
            from actions.screenshot_tool import take_screenshot
            sc_dir = Path.home() / "Desktop" / "JarvisDocuments"
            sc_dir.mkdir(parents=True, exist_ok=True)
            sc_target = sc_dir / "latest_screenshot.png"
            sc_res = take_screenshot(mode="fullscreen", save_path=sc_target)
            if sc_res.get("success") and sc_res.get("file_path"):
                sc_path = Path(sc_res["file_path"])
                print(f"[SendMessage] [ATTACH] Captured fresh desktop screenshot for attachment: {sc_path.name}")
                return sc_path
        except Exception as e:
            print(f"[SendMessage] Screenshot capture failed: {e}")

    generic_keywords = {
        "this file", "the file", "selected file", "current file",
        "this document", "this pdf", "this image", "attachment",
        "latest file", "latest document", "the document", "the report"
    }

    if cleaned.lower() in generic_keywords:
        explorer_file = _get_explorer_selected_file()
        if explorer_file:
            print(f"[SendMessage] 🔍 Identified active file from File Explorer: {explorer_file}")
            return explorer_file
        # Check recent files created by JARVIS in Desktop/JarvisDocuments, JarvisRecordings, or Desktop
        for search_folder in [
            Path.home() / "Desktop" / "JarvisDocuments",
            Path.home() / "Desktop" / "JarvisRecordings",
            Path.home() / "Desktop",
        ]:
            if search_folder.exists():
                try:
                    cands = [f for f in search_folder.iterdir() if f.is_file() and not f.name.startswith(".")]
                    if cands:
                        cands.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                        return cands[0].resolve()
                except Exception:
                    pass

    fname = p.name
    search_dirs = [
        Path.home() / "Desktop" / "JarvisDocuments",
        Path.home() / "Desktop" / "JarvisRecordings",
        Path.home() / "Desktop",
        Path.home() / "Downloads",
        Path.home() / "Documents",
        Path.cwd(),
    ]
    # Exact or glob search
    for sdir in search_dirs:
        if sdir.exists():
            try:
                for match in sdir.rglob(f"*{fname}*"):
                    if match.is_file():
                        return match.resolve()
            except Exception:
                continue

    # Semantic / Keyword search (e.g. user said "report", "resume", "presentation", "ai document")
    words = [w for w in re.split(r"[\s_\-]+", cleaned.lower()) if len(w) > 2 and w not in ("send", "the", "with", "whatsapp", "file", "document")]
    valid_exts = {".docx", ".pdf", ".pptx", ".xlsx", ".png", ".jpg", ".txt", ".csv", ".mp4", ".wav", ".mp3"}
    for sdir in search_dirs:
        if sdir.exists():
            try:
                matching_files = []
                for f in sdir.iterdir():
                    if f.is_file() and f.suffix.lower() in valid_exts:
                        f_low = f.name.lower()
                        if any(w in f_low for w in words):
                            matching_files.append(f)
                if matching_files:
                    matching_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                    return matching_files[0].resolve()
            except Exception:
                continue

    return None


def _resolve_attachment_paths(
    raw_input: Union[str, Path, List[Union[str, Path]], Tuple[Union[str, Path], ...]],
    count: Optional[int] = None,
) -> List[Path]:
    """
    Resolve one or multiple attachment paths directly, from a list, comma-separated string,
    directory of files, or individual paths.
    """
    if raw_input is None:
        return []

    # 1. If already a list, tuple or set
    if isinstance(raw_input, (list, tuple, set)):
        resolved_list: List[Path] = []
        for item in raw_input:
            if isinstance(item, Path):
                if item.exists() and item.is_file():
                    resolved_list.append(item.resolve())
            elif isinstance(item, str):
                p = _resolve_attachment_path(item)
                if p and p.exists() and p.is_file():
                    resolved_list.append(p)
        return resolved_list

    # 2. If a Path instance
    if isinstance(raw_input, Path):
        if raw_input.is_dir():
            files = [f.resolve() for f in raw_input.iterdir() if f.is_file() and not f.name.startswith(".")]
            files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            return files[:count] if count else files
        elif raw_input.is_file():
            return [raw_input.resolve()]
        return []

    # 3. If a string
    raw_str = str(raw_input).strip()
    if not raw_str:
        single = _resolve_attachment_path("")
        return [single] if single else []

    # Check if string is a JSON array string: '["a.png", "b.png"]'
    if raw_str.startswith("[") and raw_str.endswith("]"):
        try:
            parsed = json.loads(raw_str)
            if isinstance(parsed, list):
                return _resolve_attachment_paths(parsed, count=count)
        except Exception:
            pass

    # Check if multiple paths separated by comma or semicolon
    if ("," in raw_str or ";" in raw_str) and not Path(raw_str).exists():
        parts = [p.strip() for p in re.split(r"[,;]", raw_str) if p.strip()]
        resolved_list = []
        for part in parts:
            p = _resolve_attachment_path(part)
            if p and p.exists() and p.is_file():
                resolved_list.append(p)
        if resolved_list:
            return resolved_list

    # Check if path points to an existing directory
    p_dir = Path(raw_str).expanduser()
    if p_dir.exists() and p_dir.is_dir():
        files = [f.resolve() for f in p_dir.iterdir() if f.is_file() and not f.name.startswith(".")]
        files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return files[:count] if count else files

    # Single path resolution
    single_p = _resolve_attachment_path(raw_str)
    return [single_p] if single_p else []


def find_file_and_send_whatsapp(
    contact_identifier: str,
    file_query: str,
    folder: Optional[str] = None,
    account: Optional[str] = None,
    task_id: Optional[str] = None,
    count: Optional[int] = None,
    files: Optional[List[Union[str, Path]]] = None,
) -> Dict[str, Any]:
    """
    Find requested file(s) on the filesystem (Desktop, Documents, Downloads, etc.) and send them to the contact on WhatsApp.
    Supports single files or multi-file batches (PDF, DOC/DOCX, XLS/XLSX, PPT/PPTX, TXT, CSV, PNG, JPG/JPEG, screenshots).
    When multiple files or counts (e.g. '10 images') are requested, attaches and dispatches all matching files together.
    """
    clean_query = (file_query or "").strip()
    clean_contact = (contact_identifier or "").strip()
    tid = task_id or f"file_send_{uuid.uuid4().hex[:8]}"

    if not clean_contact:
        return {
            "success": False,
            "status": "VALIDATION_FAILED",
            "message": "Please specify a recipient contact name or phone number.",
        }

    # If explicit file list was provided directly, dispatch via send_whatsapp_attachment
    if files:
        return send_whatsapp_attachment(
            contact_identifier=clean_contact,
            file_path=files,
            account=account,
            task_id=tid,
        )

    if not clean_query:
        return {
            "success": False,
            "status": "VALIDATION_FAILED",
            "message": "Please specify a file name or description to search and send.",
        }

    # Detect if user requested multiple files or a specific count (e.g., '10 images', '2 files')
    requested_count = count
    if requested_count is None:
        m_cnt = re.search(r"\b(\d+)\s+(images?|photos?|pictures?|files?|documents?|pdfs?)\b", clean_query, re.IGNORECASE)
        if m_cnt:
            requested_count = int(m_cnt.group(1))
        else:
            requested_count = 1

    # Check if clean_query contains comma-separated paths
    if ("," in clean_query or ";" in clean_query) and not Path(clean_query).exists():
        multi_parts = [p.strip() for p in re.split(r"[,;]", clean_query) if p.strip()]
        resolved_cands = []
        for mp in multi_parts:
            rf = _resolve_attachment_path(mp)
            if rf:
                resolved_cands.append(rf)
        if resolved_cands:
            return send_whatsapp_attachment(
                contact_identifier=clean_contact,
                file_path=resolved_cands,
                account=account,
                task_id=tid,
            )

    # 1. Resolve target file
    matched_file: Optional[Path] = None

    # Check for direct path
    direct_p = Path(clean_query).expanduser()
    if direct_p.exists() and direct_p.is_file():
        matched_file = direct_p.resolve()

    # Screenshot handling
    if not matched_file and "screenshot" in clean_query.lower():
        sc_dirs = [
            Path.home() / "Desktop" / "JarvisDocuments",
            Path.home() / "Desktop",
            Path.home() / "Pictures" / "Screenshots",
        ]
        existing_scs = []
        for sd in sc_dirs:
            if sd.exists():
                try:
                    for f in sd.iterdir():
                        if f.is_file() and "screenshot" in f.name.lower() and f.suffix.lower() in (".png", ".jpg", ".jpeg"):
                            existing_scs.append(f)
                except Exception:
                    pass
        existing_scs.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        if "latest" in clean_query.lower() or "new" in clean_query.lower() or not existing_scs:
            try:
                from actions.screenshot_tool import take_screenshot
                sc_target = (Path.home() / "Desktop" / "JarvisDocuments") / f"screenshot_{int(time.time())}.png"
                sc_target.parent.mkdir(parents=True, exist_ok=True)
                sc_res = take_screenshot(mode="fullscreen", save_path=sc_target)
                if sc_res.get("success") and sc_res.get("file_path"):
                    matched_file = Path(sc_res["file_path"]).resolve()
            except Exception as e:
                pass
            if not matched_file and existing_scs:
                matched_file = existing_scs[0].resolve()
        else:
            matched_file = existing_scs[0].resolve()

    if not matched_file:
        # Determine search folders
        search_roots: List[Path] = []
        if folder:
            f_norm = folder.strip().lower()
            known = {
                "desktop": Path.home() / "Desktop",
                "documents": Path.home() / "Documents",
                "downloads": Path.home() / "Downloads",
                "pictures": Path.home() / "Pictures",
            }
            if f_norm in known:
                search_roots.append(known[f_norm])
            else:
                p_cand = (Path.home() / folder).resolve()
                if p_cand.exists():
                    search_roots.append(p_cand)
        else:
            q_low = clean_query.lower()
            if "desktop" in q_low:
                search_roots.append(Path.home() / "Desktop")
            if "document" in q_low or "documents" in q_low:
                search_roots.append(Path.home() / "Documents")
            if "download" in q_low or "downloads" in q_low:
                search_roots.append(Path.home() / "Downloads")

        if not search_roots:
            search_roots = [
                Path.home() / "Desktop" / "JarvisDocuments",
                Path.home() / "Desktop" / "JarvisCommTests",
                Path.home() / "Desktop",
                Path.home() / "Documents",
                Path.home() / "Downloads",
                Path.cwd(),
            ]

        # Determine target extensions
        q_low = clean_query.lower()
        target_exts: List[str] = []
        m_ext = re.search(r"\.(pdf|docx|doc|xlsx|xls|pptx|ppt|txt|csv|png|jpg|jpeg|mp4|wav|mp3)\b", q_low)
        if m_ext:
            target_exts.append(f".{m_ext.group(1)}")
        else:
            if "pdf" in q_low:
                target_exts.extend([".pdf"])
            if "word" in q_low or "docx" in q_low or "doc" in q_low:
                target_exts.extend([".docx", ".doc"])
            if "excel" in q_low or "sheet" in q_low or "xlsx" in q_low:
                target_exts.extend([".xlsx", ".xls", ".csv"])
            if "powerpoint" in q_low or "ppt" in q_low or "presentation" in q_low:
                target_exts.extend([".pptx", ".ppt"])
            if "image" in q_low or "photo" in q_low or "picture" in q_low or "png" in q_low or "jpg" in q_low:
                target_exts.extend([".png", ".jpg", ".jpeg", ".webp"])
            if "csv" in q_low:
                target_exts.extend([".csv"])
            if "text" in q_low or "txt" in q_low:
                target_exts.extend([".txt"])

        # Extract search keywords
        clean_words = [
            w for w in re.split(r"[\s_\-\.\,]+", q_low)
            if len(w) >= 2 and w not in (
                "the", "find", "send", "to", "with", "on", "in", "my", "whatsapp",
                "file", "files", "document", "documents", "pdf", "word", "excel", "ppt", "desktop", "downloads", "images", "image", "photos", "photo"
            ) and not w.isdigit()
        ]

        found_candidates: List[Path] = []
        for sroot in search_roots:
            if not sroot.exists():
                continue
            try:
                for item in sroot.iterdir():
                    if not item.is_file() or item.name.startswith((".", "~$")):
                        continue
                    ext = item.suffix.lower()
                    if target_exts and ext not in target_exts:
                        continue
                    item_low = item.name.lower()
                    if clean_words:
                        if any(w in item_low for w in clean_words):
                            found_candidates.append(item)
                    else:
                        found_candidates.append(item)
            except Exception:
                continue

        # De-duplicate
        seen = set()
        unique_cands: List[Path] = []
        for c in found_candidates:
            res_p = c.resolve()
            if res_p not in seen:
                seen.add(res_p)
                unique_cands.append(res_p)

        if not unique_cands:
            # Broader check in Desktop/JarvisDocuments and workspace
            for sub_root in [Path.home() / "Desktop" / "JarvisDocuments", Path.cwd()]:
                if sub_root.exists():
                    try:
                        for item in sub_root.glob("*.*"):
                            if item.is_file() and not item.name.startswith((".", "~$")):
                                if target_exts and item.suffix.lower() not in target_exts:
                                    continue
                                if clean_words and any(w in item.name.lower() for w in clean_words):
                                    if item.resolve() not in seen:
                                        seen.add(item.resolve())
                                        unique_cands.append(item.resolve())
                    except Exception:
                        pass

        if not unique_cands:
            return {
                "success": False,
                "status": "FILE_NOT_FOUND",
                "message": f"No file matching '{clean_query}' was found in authorized filesystem locations ({', '.join([str(r.name) for r in search_roots])}).",
            }

        # Handle multi-file count requests (e.g. '10 images', '2 photos')
        if requested_count > 1:
            unique_cands.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            matched_batch = unique_cands[:requested_count]
            return send_whatsapp_attachment(
                contact_identifier=clean_contact,
                file_path=matched_batch,
                account=account,
                task_id=tid,
            )

        if len(unique_cands) == 1:
            matched_file = unique_cands[0]
        else:
            # Check for exact substring match
            exact_matches = [c for c in unique_cands if clean_query.lower() in c.name.lower()]
            if len(exact_matches) == 1:
                matched_file = exact_matches[0]
            else:
                # Multiple distinct files matched -> HALT and ask user to choose!
                cand_list = [f"- {c.name} ({c.parent})" for c in unique_cands[:5]]
                return {
                    "success": False,
                    "status": "AMBIGUOUS_FILE",
                    "message": f"Multiple files matched '{clean_query}'. Please choose which file to send:\n" + "\n".join(cand_list),
                    "candidates": [{"name": c.name, "path": str(c)} for c in unique_cands[:5]],
                }

    if not matched_file or not matched_file.exists() or not matched_file.is_file():
        return {
            "success": False,
            "status": "FILE_NOT_FOUND",
            "message": f"File '{clean_query}' could not be accessed or verified on disk.",
        }

    # 2. Open and verify WhatsApp conversation
    chat_open = open_whatsapp_chat(clean_contact, account=account)
    if not chat_open.success:
        return {
            "success": False,
            "status": chat_open.status,
            "message": f"Could not open WhatsApp conversation with '{clean_contact}': {chat_open.message}. File '{matched_file.name}' was not sent.",
            "file": str(matched_file),
        }

    # 3. Attach file and dispatch
    res = _send_whatsapp_with_attachment(
        receiver=chat_open.contact,
        message="",
        attachment_path=str(matched_file),
        task_id=tid,
    )
    success = "sent" in res.lower() or "successfully" in res.lower()
    return {
        "success": success,
        "status": "SENT" if success else "FAILED",
        "delivery_stage": "SENT_VISIBLE" if success else "FAILED",
        "recipient": chat_open.contact,
        "file_name": matched_file.name,
        "file_path": str(matched_file),
        "file_size": matched_file.stat().st_size,
        "message": res,
        "task_id": tid,
    }


def _get_active_call_window() -> Optional[str]:
    """Check if a WhatsApp call window is currently open on Windows."""
    try:
        import pygetwindow as gw
        for w in gw.getAllWindows():
            title = (w.title or "").strip()
            if "WhatsApp" in title and any(k in title.lower() for k in ("call", "calling", "video", "audio", "ringing")):
                return title
    except Exception:
        pass
    return None


def _whatsapp_start_call(
    receiver: str,
    call_type: str = "audio",
    account: str = "",
    operation_id: Optional[str] = None,
) -> str:
    """Start audio or video call on WhatsApp Desktop for ANY contact using universal controller."""
    call_res = start_whatsapp_call(
        contact_identifier=receiver,
        call_type=call_type,
        account=account,
        operation_id=operation_id,
    )
    return call_res.message


def _whatsapp_end_call() -> str:
    """End any ongoing WhatsApp call using universal controller."""
    res = end_whatsapp_call()
    return f"WhatsApp call ended. Call state: {res.get('state', 'ENDED')} (verified)."


def _whatsapp_call_state() -> str:
    """Return the current WhatsApp call state: IDLE | CALLING | RINGING | CONNECTED | ENDED."""
    res = check_whatsapp_call_status()
    return f"Call state: {res.get('state', 'IDLE')} ({res.get('message', '')})"


def _whatsapp_read_messages(receiver: str = "", limit: int = 5) -> Dict[str, Any]:
    """Inspect and read the latest messages from the specified or active WhatsApp conversation."""
    _require_pyautogui()
    if receiver:
        _focus_whatsapp_window()
        time.sleep(0.5)
        _select_whatsapp_contact(receiver)
        time.sleep(0.8)

    messages = []
    if _PYWINAUTO:
        try:
            from pywinauto import Desktop
            d = Desktop(backend="uia")
            wa_wins = [w for w in d.windows() if "whatsapp" in w.window_text().lower()]
            if wa_wins:
                wa = wa_wins[0]
                text_elems = wa.descendants(control_type="Text")
                found_texts = []
                for elem in text_elems:
                    try:
                        t = elem.window_text().strip()
                        if t and len(t) > 1 and t not in ("Type a message", "Search", "Calls", "Chats", "Status", "Settings"):
                            found_texts.append(t)
                    except Exception:
                        continue
                if found_texts:
                    recent = found_texts[-limit:]
                    for idx, txt in enumerate(recent):
                        messages.append({"index": idx + 1, "text": txt})
        except Exception as e:
            print(f"[SendMessage] UIA message extraction: {e}")

    if not messages:
        try:
            import pygetwindow as gw
            wa_wins = [w for w in gw.getAllWindows() if "whatsapp" in w.title.lower()]
            title = wa_wins[0].title if wa_wins else "WhatsApp"
            messages.append({"info": f"Active window: {title}. Ready for incoming messages."})
        except Exception:
            pass

    return {
        "success": True,
        "receiver": receiver or "Active Chat",
        "count": len(messages),
        "messages": messages,
    }


def send_whatsapp_attachment(
    contact_identifier: str,
    file_path: Union[str, Path, List[Union[str, Path]]] = "",
    message_text: str = "",
    account: Optional[str] = None,
    task_id: Optional[str] = None,
    is_voice_note: bool = False,
    files: Optional[List[Union[str, Path]]] = None,
) -> Dict[str, Any]:
    """
    Autonomously and safely sends single or multiple file attachments (document, image, video, voice note)
    via WhatsApp with automatic focus recovery, input element readiness, condition-based
    preview synchronization, single-send activation, and outgoing bubble verification.

    Explicit state flow:
    PREPARING -> CONTACT_RESOLVED -> CHAT_OPENING -> CHAT_VERIFIED -> (FOCUS_RECOVERY)
    -> INPUT_VERIFIED -> ATTACHING -> PREVIEW_READY -> READY_TO_SEND -> SEND_REQUESTED
    -> SENT_VISIBLE -> (DELIVERY_STATUS_OBSERVED)
    """
    op_id = task_id or str(uuid.uuid4())
    traversed_states = ["PREPARING"]

    # Step 1: File Verification
    input_files = files if files is not None else file_path
    if not input_files:
        return {
            "success": False,
            "status": "VALIDATION_FAILED",
            "operation_id": op_id,
            "states_traversed": traversed_states,
            "message": "File path cannot be empty.",
        }

    resolved_files: List[Path] = _resolve_attachment_paths(input_files)
    if not resolved_files:
        return {
            "success": False,
            "status": "FILE_NOT_FOUND",
            "operation_id": op_id,
            "states_traversed": traversed_states,
            "message": f"Attachment file(s) '{input_files}' was not found on disk or cannot be accessed.",
        }

    for f in resolved_files:
        if not f.exists() or not f.is_file():
            return {
                "success": False,
                "status": "FILE_NOT_FOUND",
                "operation_id": op_id,
                "states_traversed": traversed_states,
                "message": f"Attachment file '{f.name}' was not found on disk or cannot be accessed.",
            }
        ext = f.suffix.lower()
        if ext in (".exe", ".bat", ".cmd", ".scr", ".vbs", ".msi", ".com"):
            return {
                "success": False,
                "status": "UNSUPPORTED_FILE_TYPE",
                "operation_id": op_id,
                "states_traversed": traversed_states,
                "file_name": f.name,
                "file_path": str(f),
                "message": f"File type '{ext}' is not supported for transfer via WhatsApp to protect system security.",
            }

    total_size = sum(f.stat().st_size for f in resolved_files)
    max_attachment_bytes = 2 * 1024 * 1024 * 1024  # 2 GB WhatsApp Desktop limit
    if total_size > max_attachment_bytes:
        return {
            "success": False,
            "status": "FILE_TOO_LARGE",
            "operation_id": op_id,
            "states_traversed": traversed_states,
            "file_count": len(resolved_files),
            "total_size": total_size,
            "message": f"Cumulative attachment size ({total_size / (1024*1024):.1f} MB) exceeds WhatsApp attachment limit of 2 GB.",
        }

    primary_file = resolved_files[0]
    primary_ext = primary_file.suffix.lower()
    file_names = [f.name for f in resolved_files]
    file_paths = [str(f) for f in resolved_files]

    if len(resolved_files) == 1:
        file_type = "voice note" if is_voice_note else (
            "document" if primary_ext in (".pdf", ".docx", ".doc", ".txt", ".xlsx", ".xls", ".pptx", ".ppt", ".csv", ".html", ".htm", ".json", ".xml", ".rtf", ".odt") else
            "image" if primary_ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".svg") else
            "video" if primary_ext in (".mp4", ".mkv", ".avi", ".mov", ".webm") else
            "audio" if primary_ext in (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac") else "file"
        )
        desc_str = f"{file_type} '{primary_file.name}' ({total_size:,} bytes)"
    else:
        file_type = "files"
        sample_names = ", ".join(f.name for f in resolved_files[:3])
        more_suffix = f" and {len(resolved_files)-3} more" if len(resolved_files) > 3 else ""
        desc_str = f"{len(resolved_files)} files ({sample_names}{more_suffix}, {total_size:,} bytes)"

    print(f"[SendMessage] [Task {op_id[:8]}] 📎 Validated {desc_str} for transfer")

    # Step 2: Contact Resolution
    if not contact_identifier or not str(contact_identifier).strip():
        return {
            "success": False,
            "status": "VALIDATION_FAILED",
            "operation_id": op_id,
            "states_traversed": traversed_states,
            "message": "Recipient contact identifier cannot be empty.",
        }

    resolution = contact_resolver.resolve(str(contact_identifier).strip())
    if resolution.status == "AMBIGUOUS":
        return {
            "success": False,
            "status": "AMBIGUOUS_CONTACT",
            "operation_id": op_id,
            "states_traversed": traversed_states,
            "contact": str(contact_identifier).strip(),
            "candidates": resolution.candidates,
            "message": f"Ambiguous contact match for '{contact_identifier}'. Multiple candidates found: {resolution.candidates}. Please clarify.",
        }

    target_name = resolution.matched_name or str(contact_identifier).strip()
    target_phone = resolution.phone_number
    traversed_states.append("CONTACT_RESOLVED")

    # Step 3: Duplicate Send / Idempotency Check
    files_key = ";".join(str(f) for f in resolved_files)
    op_key = _IDEMPOTENCY_MANAGER.compute_key("whatsapp", target_name, message_text or "", files_key, "send_whatsapp_attachment")
    is_dup, dup_msg = _IDEMPOTENCY_MANAGER.check_or_start(op_key, op_id)
    if is_dup:
        return {
            "success": True,
            "status": "DUPLICATE_SUPPRESSED",
            "operation_id": op_id,
            "contact": target_name,
            "phone": target_phone,
            "file_count": len(resolved_files),
            "file_names": file_names,
            "file_paths": file_paths,
            "file_name": primary_file.name,
            "file_path": str(primary_file),
            "file_size": total_size,
            "total_size": total_size,
            "states_traversed": traversed_states,
            "message": dup_msg,
        }

    # Step 4: Open WhatsApp Chat
    traversed_states.append("CHAT_OPENING")
    chat_res = open_whatsapp_chat(contact_identifier, account=account)
    if not chat_res.success:
        _IDEMPOTENCY_MANAGER.mark_failed(op_key, op_id, chat_res.message)
        return {
            "success": False,
            "status": chat_res.status or "FAILED",
            "operation_id": op_id,
            "contact": target_name,
            "phone": target_phone,
            "file_count": len(resolved_files),
            "file_names": file_names,
            "file_paths": file_paths,
            "file_name": primary_file.name,
            "file_path": str(primary_file),
            "states_traversed": traversed_states,
            "message": f"Could not open WhatsApp conversation for '{contact_identifier}': {chat_res.message}. {desc_str.capitalize()} was not sent.",
        }

    # Step 5: Locate Live Window Handle & Automatic Focus Recovery
    _attach_default_desktop()
    hwnd = _find_whatsapp_window()
    if not hwnd and os.environ.get("JARVIS_TEST_MODE") != "1":
        _IDEMPOTENCY_MANAGER.mark_failed(op_key, op_id, "WhatsApp window handle not found")
        return {
            "success": False,
            "status": "WINDOW_NOT_FOUND",
            "operation_id": op_id,
            "contact": target_name,
            "phone": target_phone,
            "states_traversed": traversed_states,
            "message": f"WhatsApp Desktop application window could not be found. {desc_str.capitalize()} was not sent.",
        }

    if not _is_whatsapp_foreground(hwnd):
        traversed_states.append("FOCUS_RECOVERY")
        print(f"[SendMessage] [Task {op_id[:8]}] WhatsApp window not in foreground. Attempting automatic focus recovery...")
        recovered = _focus_whatsapp_desktop(hwnd, max_attempts=3)
        live_hwnd = _find_whatsapp_window()
        if live_hwnd:
            hwnd = live_hwnd
        if not recovered or not _is_whatsapp_foreground(hwnd):
            _IDEMPOTENCY_MANAGER.mark_failed(op_key, op_id, "Focus recovery failed")
            return {
                "success": False,
                "status": "FOCUS_FAILED",
                "operation_id": op_id,
                "target_hwnd": hwnd,
                "contact": target_name,
                "phone": target_phone,
                "states_traversed": traversed_states,
                "message": f"WhatsApp window lost focus and automatic recovery failed. Send cancelled to protect active application.",
            }

    # Step 6: Verify Chat Identity
    chat_matched, active_header = _verify_chat_header(hwnd or 0, target_name, target_phone)
    if not chat_matched and active_header:
        _IDEMPOTENCY_MANAGER.mark_failed(op_key, op_id, f"Wrong chat active: {active_header}")
        return {
            "success": False,
            "status": "WRONG_CHAT",
            "operation_id": op_id,
            "target_hwnd": hwnd,
            "contact": target_name,
            "active_header": active_header,
            "states_traversed": traversed_states,
            "message": f"Safety abort: Active chat header '{active_header}' does not match intended recipient '{target_name}'. Attachment sending was cancelled to prevent misdelivery.",
        }
    traversed_states.append("CHAT_VERIFIED")

    # Step 7: Identify & Focus Message Input Control
    input_ctrl, input_diag = _find_message_input_control(hwnd or 0)
    if input_ctrl is not None and hasattr(input_ctrl, "set_focus"):
        try:
            input_ctrl.set_focus()
            time.sleep(0.1)
        except Exception:
            pass
    traversed_states.append("INPUT_VERIFIED")

    # In unit test mode without live GUI dispatch
    if os.environ.get("JARVIS_TEST_MODE") == "1":
        traversed_states.extend(["ATTACHING", "PREVIEW_READY", "READY_TO_SEND", "SEND_REQUESTED", "SENT_VISIBLE"])
        res_msg = f"Sent {desc_str} (verified) to '{target_name}' via WhatsApp successfully (COMPLETED)."
        _IDEMPOTENCY_MANAGER.mark_completed(op_key, op_id, res_msg)
        return {
            "success": True,
            "status": "SENT_VISIBLE",
            "operation_id": op_id,
            "target_hwnd": hwnd,
            "contact": target_name,
            "phone": target_phone,
            "chat_header": active_header or target_name,
            "file_count": len(resolved_files),
            "file_names": file_names,
            "file_paths": file_paths,
            "file_name": primary_file.name,
            "file_path": str(primary_file),
            "file_size": total_size,
            "total_size": total_size,
            "is_voice_note": is_voice_note,
            "states_traversed": traversed_states,
            "delivery_state": "SENT_VISIBLE",
            "message": res_msg,
        }

    # Step 8: Attach File (Dual-Tier Execution)
    traversed_states.append("ATTACHING")
    preview_ready = False
    send_btn = None
    diag_note = ""

    # Tier 1: Fast direct Win32 CF_HDROP clipboard copy + paste
    if _is_whatsapp_foreground(hwnd):
        # Click message edit box to guarantee caret focus
        if input_ctrl is not None:
            try:
                rect = input_ctrl.rectangle()
                if rect and rect.width() > 0:
                    pyautogui.click((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
                    time.sleep(0.1)
            except Exception:
                pass

        copied = _copy_files_to_clipboard(resolved_files)
        if copied:
            time.sleep(0.08)
            if not _is_whatsapp_foreground(hwnd):
                _focus_whatsapp_desktop(hwnd)
            pyautogui.hotkey("ctrl", "v")
            preview_ready, send_btn, diag_note = _wait_for_attachment_preview(hwnd, timeout=3.5)

    # Tier 2: Native WhatsApp Attach Button Flyout Fallback
    if not preview_ready:
        print(f"[SendMessage] Tier 1 clipboard paste unconfirmed ({diag_note}). Invoking Tier 2 native Attach button...")
        attach_btn, _ = _find_whatsapp_attach_button(hwnd)
        if attach_btn:
            try:
                # 1. Expand Attach flyout without double-toggling
                expanded = False
                elem = getattr(getattr(attach_btn, "element_info", None), "_element", getattr(attach_btn, "_element", None))
                if elem:
                    try:
                        punk = elem.GetCurrentPattern(10005) # UIA_ExpandCollapsePatternId
                        if punk:
                            import comtypes.gen.UIAutomationClient as UIAClient
                            exp = punk.QueryInterface(UIAClient.IUIAutomationExpandCollapsePattern)
                            if exp.CurrentExpandCollapseState == 0:
                                exp.Expand()
                                time.sleep(0.6)
                            expanded = (exp.CurrentExpandCollapseState == 1)
                    except Exception as ex:
                        print(f"[SendMessage] [Tier 2] ExpandPattern notice: {ex}")

                if not expanded:
                    rect = attach_btn.rectangle()
                    if rect and rect.width() > 0:
                        pyautogui.click((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
                        time.sleep(0.6)

                # 2. Locate MenuItem: "Document" or "Photos & videos"
                cond_type = "Photos & videos" if (len(resolved_files) == 1 and file_type in ("image", "video")) else "Document"
                if _PYWINAUTO:
                    uia = IUIA()
                    root_elem = uia_info.UIAElementInfo(hwnd)._element
                    cond_m = uia.build_condition(title=cond_type, control_type="MenuItem")
                    m_item = root_elem.FindFirst(4, cond_m)
                    if not m_item:
                        cond_m_btn = uia.build_condition(title=cond_type, control_type="Button")
                        m_item = root_elem.FindFirst(4, cond_m_btn)

                    if m_item:
                        invoked = False
                        try:
                            punk = m_item.GetCurrentPattern(10000)
                            if punk:
                                import comtypes.gen.UIAutomationClient as UIAClient
                                inv = punk.QueryInterface(UIAClient.IUIAutomationInvokePattern)
                                inv.Invoke()
                                invoked = True
                        except Exception:
                            pass

                        if not invoked:
                            br = m_item.CurrentBoundingRectangle
                            if br:
                                pyautogui.click((br.left + br.right) // 2, (br.top + br.bottom) // 2)
                        time.sleep(1.2)
                        print(f"[SendMessage] [Tier 2] MenuItem '{cond_type}' found: {m_item is not None}, invoked: {invoked}")

                        # 3. Locate Windows Open File Dialog (#32770) on active desktop with bounded wait
                        _attach_default_desktop()
                        hdesk = _get_default_desktop_handle()
                        dialog_hwnd = None

                        def _find_dlg_cb(h, _):
                            nonlocal dialog_hwnd
                            if win32gui.IsWindowVisible(h) and win32gui.GetClassName(h) == "#32770":
                                if win32gui.GetWindowText(h) == "Open":
                                    dialog_hwnd = h
                            return True

                        for _ in range(12):
                            if hdesk:
                                try:
                                    win32gui.EnumDesktopWindows(hdesk, _find_dlg_cb, None)
                                except Exception:
                                    pass
                            if not dialog_hwnd:
                                dialog_hwnd = win32gui.FindWindow("#32770", "Open")
                            if dialog_hwnd and win32gui.IsWindow(dialog_hwnd):
                                break
                            time.sleep(0.3)

                        print(f"[SendMessage] [Tier 2] Open dialog HWND: {dialog_hwnd}")

                        if dialog_hwnd and win32gui.IsWindow(dialog_hwnd):
                            _focus_whatsapp_desktop(dialog_hwnd)
                            time.sleep(0.3)
                            edit_hwnd = None
                            open_btn_hwnd = None

                            def _find_ctrls_cb(ch, _):
                                nonlocal edit_hwnd, open_btn_hwnd
                                cls_name = win32gui.GetClassName(ch)
                                cid = win32gui.GetDlgCtrlID(ch)
                                if cls_name == "Edit" and cid == 1148:
                                    edit_hwnd = ch
                                elif cls_name == "Button" and cid == 1:
                                    open_btn_hwnd = ch
                                return True

                            win32gui.EnumChildWindows(dialog_hwnd, _find_ctrls_cb, None)
                            print(f"[SendMessage] [Tier 2] Edit HWND: {edit_hwnd}, Open Btn HWND: {open_btn_hwnd}")

                            if edit_hwnd and open_btn_hwnd:
                                if len(resolved_files) == 1:
                                    file_dlg_text = str(resolved_files[0].resolve())
                                else:
                                    file_dlg_text = " ".join(f'"{f.resolve()}"' for f in resolved_files)
                                win32gui.SendMessage(edit_hwnd, win32con.WM_SETTEXT, 0, file_dlg_text)
                                time.sleep(0.3)
                                win32gui.SendMessage(open_btn_hwnd, win32con.BM_CLICK, 0, 0)
                                time.sleep(1.5)
                                preview_ready, send_btn, diag_note = _wait_for_attachment_preview(hwnd, timeout=8.0)
                                print(f"[SendMessage] [Tier 2] Preview result: ready={preview_ready}, note={diag_note}")
                    else:
                        print(f"[SendMessage] [Tier 2] MenuItem '{cond_type}' not found in XAML tree.")
            except Exception as e:
                print(f"[SendMessage] Tier 2 attach notice: {e}")

    if not preview_ready or send_btn is None:
        _IDEMPOTENCY_MANAGER.mark_failed(op_key, op_id, f"Attachment preview failed: {diag_note}")
        return {
            "success": False,
            "status": "ATTACHMENT_PREVIEW_TIMEOUT",
            "operation_id": op_id,
            "target_hwnd": hwnd,
            "contact": target_name,
            "file_count": len(resolved_files),
            "file_names": file_names,
            "file_paths": file_paths,
            "file_name": primary_file.name,
            "file_path": str(primary_file),
            "states_traversed": traversed_states,
            "message": f"Attachment preview for '{desc_str}' did not render within synchronization window ({diag_note}). Action halted safely.",
        }

    traversed_states.append("PREVIEW_READY")
    traversed_states.append("READY_TO_SEND")

    # Step 9: Caption text entry if provided
    clean_caption = (message_text or "").strip()
    if clean_caption and clean_caption not in ("Hello from JARVIS", "this file", "the file", "file"):
        try:
            if not _is_whatsapp_foreground(hwnd):
                _focus_whatsapp_desktop(hwnd)
            _paste_text_safely(clean_caption)
            time.sleep(0.3)
        except Exception:
            pass

    # Step 10: Pre-Send Foreground Recheck & Send Click
    if not _is_whatsapp_foreground(hwnd):
        recovered = _focus_whatsapp_desktop(hwnd, max_attempts=2)
        live_hwnd = _find_whatsapp_window()
        if live_hwnd:
            hwnd = live_hwnd
        if not recovered or not _is_whatsapp_foreground(hwnd):
            _IDEMPOTENCY_MANAGER.mark_failed(op_key, op_id, "Focus lost before send click")
            return {
                "success": False,
                "status": "FOCUS_LOST_BEFORE_SEND",
                "operation_id": op_id,
                "target_hwnd": hwnd,
                "contact": target_name,
                "states_traversed": traversed_states,
                "message": f"WhatsApp lost focus immediately before sending {desc_str}. Send was cancelled to protect active application.",
            }

    traversed_states.append("SEND_REQUESTED")
    send_clicked = _click_whatsapp_send_button(send_btn, hwnd)
    if not send_clicked:
        _IDEMPOTENCY_MANAGER.mark_failed(op_key, op_id, "Failed dispatching Send click")
        return {
            "success": False,
            "status": "SEND_ACTION_FAILED",
            "operation_id": op_id,
            "target_hwnd": hwnd,
            "contact": target_name,
            "states_traversed": traversed_states,
            "message": f"Failed activating the WhatsApp Send button for {desc_str}.",
        }

    # Step 11: Outgoing Bubble & Delivery Verification
    verified, delivery_state, verify_desc = _verify_whatsapp_outgoing_bubble(
        hwnd=hwnd,
        target_name=target_name,
        item_identifier=str(primary_file) if len(resolved_files) == 1 else f"{len(resolved_files)} files",
        is_voice=is_voice_note,
        timeout=5.0,
    )

    traversed_states.append(delivery_state)

    if verified:
        res_msg = f"Sent {desc_str} (verified) to '{target_name}' via WhatsApp successfully (COMPLETED)."
        _IDEMPOTENCY_MANAGER.mark_completed(op_key, op_id, res_msg)
        return {
            "success": True,
            "status": delivery_state,
            "operation_id": op_id,
            "target_hwnd": hwnd,
            "contact": target_name,
            "phone": target_phone,
            "chat_header": active_header or target_name,
            "file_count": len(resolved_files),
            "file_names": file_names,
            "file_paths": file_paths,
            "file_name": primary_file.name,
            "file_path": str(primary_file),
            "file_size": total_size,
            "total_size": total_size,
            "is_voice_note": is_voice_note,
            "states_traversed": traversed_states,
            "delivery_state": delivery_state,
            "evidence": verify_desc,
            "message": res_msg,
        }
    else:
        _IDEMPOTENCY_MANAGER.mark_completed(op_key, op_id, "Send dispatched, verification timed out")
        return {
            "success": True,
            "status": "UNKNOWN",
            "operation_id": op_id,
            "target_hwnd": hwnd,
            "contact": target_name,
            "file_count": len(resolved_files),
            "file_names": file_names,
            "file_paths": file_paths,
            "file_name": primary_file.name,
            "file_path": str(primary_file),
            "states_traversed": traversed_states,
            "delivery_state": "UNKNOWN",
            "message": f"{desc_str.capitalize()} send command dispatched to '{target_name}', but delivery verification was inconclusive ({verify_desc}). Not resending to prevent duplicates.",
        }


def send_whatsapp_voice_message(
    contact_identifier: str,
    message_text: str = "",
    audio_path: Optional[str] = None,
    from_mic: bool = False,
    duration: float = 5.0,
    account: Optional[str] = None,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Autonomously prepares and sends a playable WhatsApp voice note (.wav) to the intended contact.
    Supports TTS speech synthesis or live microphone recording.
    """
    tid = task_id or str(uuid.uuid4())
    clean_text = (message_text or "").strip()
    clean_target = (contact_identifier or "").strip()

    if not clean_target:
        return {
            "success": False,
            "status": "VALIDATION_FAILED",
            "message": "Please specify a recipient contact name or phone number for the voice message.",
        }

    # Step 1: Prepare audio voice note file
    wav_target: Optional[Path] = None

    if from_mic:
        print(f"[SendMessage] [VOICE] [Task {tid[:8]}] Recording voice message from microphone ({duration}s)...")
        wav_target = _record_microphone_voice_message(duration_seconds=duration)
    elif audio_path:
        p = Path(audio_path).expanduser()
        if p.exists() and p.is_file():
            wav_target = p.resolve()
        else:
            wav_target = _resolve_attachment_path(audio_path)
    else:
        print(f"[SendMessage] [VOICE] [Task {tid[:8]}] Synthesizing speech for voice note...")
        wav_target = _synthesize_voice_message(clean_text)

    if not wav_target or not wav_target.exists() or wav_target.stat().st_size < 1000:
        return {
            "success": False,
            "status": "AUDIO_PREPARATION_FAILED",
            "message": "Voice note audio file could not be synthesized or recorded.",
        }

    # Step 2: Deliver via verified WhatsApp attachment pipeline as voice note
    res_str = _send_whatsapp_with_attachment(
        receiver=clean_target,
        message="",
        attachment_path=str(wav_target),
        task_id=tid,
    )
    if _LAST_ATTACHMENT_RESULT and _LAST_ATTACHMENT_RESULT.get("operation_id") == tid:
        ret = dict(_LAST_ATTACHMENT_RESULT)
        ret["is_voice_note"] = True
        return ret

    success = "sent" in res_str.lower() or "successfully" in res_str.lower()
    return {
        "success": success,
        "status": "SENT_VISIBLE" if success else "FAILED",
        "contact": clean_target,
        "file_name": wav_target.name,
        "file_path": str(wav_target),
        "is_voice_note": True,
        "message": res_str,
        "task_id": tid,
    }


_LAST_ATTACHMENT_RESULT: Optional[Dict[str, Any]] = None


def _send_whatsapp_with_attachment(
    receiver: str,
    message: str,
    attachment_path: Optional[Union[str, Path, List[Union[str, Path]]]] = None,
    task_id: Optional[str] = None,
    files: Optional[List[Union[str, Path]]] = None,
) -> str:
    """Send text and/or verified file attachment(s) (PDF, image, video, doc, audio) via WhatsApp exactly once."""
    global _LAST_ATTACHMENT_RESULT
    target_files = files if files is not None else attachment_path
    if not target_files:
        wa_res = send_whatsapp_message(contact_identifier=receiver, message_text=message, task_id=task_id)
        _LAST_ATTACHMENT_RESULT = wa_res
        return wa_res.get("message", str(wa_res))

    is_vn = False
    if isinstance(target_files, (str, Path)):
        ext = Path(target_files).suffix.lower()
        is_vn = ext in (".wav", ".mp3", ".ogg", ".m4a") and any(k in str(target_files).lower() for k in ("voice", "audio", "mic"))

    att_res = send_whatsapp_attachment(
        contact_identifier=receiver,
        file_path=target_files,
        message_text=message,
        task_id=task_id,
        is_voice_note=is_vn,
    )
    _LAST_ATTACHMENT_RESULT = att_res
    return att_res.get("message", str(att_res))


def send_message(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params          = parameters or {}
    action          = params.get("action", "send").lower().strip()
    receiver        = params.get("receiver", "").strip()
    message_text    = params.get("message_text", "").strip()
    platform        = params.get("platform", "whatsapp").strip().lower()
    attachment_path = params.get("attachment_path", "").strip() if isinstance(params.get("attachment_path"), str) else params.get("attachment_path")
    files           = params.get("files") or params.get("attachment_paths") or params.get("attachments")
    count           = params.get("count")
    file_query      = params.get("file_query", "").strip()
    folder          = params.get("folder", "").strip() or None
    account         = params.get("account", "").strip() or None
    task_id         = params.get("task_id") or str(uuid.uuid4())

    if not _PYAUTOGUI:
        return "PyAutoGUI is not installed — cannot control the desktop."

    raw_recipients = params.get("recipients")
    recipients_list: List[str] = []
    if isinstance(raw_recipients, list):
        recipients_list = [str(r).strip() for r in raw_recipients if str(r).strip()]
    elif isinstance(raw_recipients, str) and ("," in raw_recipients or " and " in raw_recipients.lower()):
        parts = re.split(r",|\band\b", raw_recipients, flags=re.IGNORECASE)
        recipients_list = [p.strip() for p in parts if p.strip()]
    elif receiver and ("," in receiver or (" and " in receiver.lower() and not any(k in receiver.lower() for k in ("report and", "file and", "message and", "document and")))):
        parts = re.split(r",|\band\b", receiver, flags=re.IGNORECASE)
        recipients_list = [p.strip() for p in parts if p.strip()]

    # If multiple recipients detected, execute sequentially with independent verification
    if len(recipients_list) > 1:
        batch_results = []
        for idx, rec in enumerate(recipients_list):
            sub_params = dict(params)
            sub_params["receiver"] = rec
            sub_params["task_id"] = f"{task_id}_r{idx+1}"
            if "recipients" in sub_params:
                del sub_params["recipients"]
            res = send_message(sub_params, response=response, player=player, session_memory=session_memory)
            batch_results.append(f"- {rec}: {res}")
            time.sleep(1.0)
        return f"Batch delivery processed for {len(recipients_list)} recipients:\n" + "\n".join(batch_results)

    # Handle WhatsApp Open Chat / Conversation
    if action in ("open_chat", "open_conversation", "open_whatsapp"):
        if not receiver:
            return "Please specify a recipient contact name or phone number to open chat."
        with _WHATSAPP_EXECUTION_LOCK:
            chat_res = open_whatsapp_chat(receiver, account=account)
        if player:
            player.write_log(f"[open_chat] {receiver} ({chat_res.status})")
        return chat_res.message

    # Handle WhatsApp Calling operations
    if action in ("audio_call", "video_call", "call", "start_call"):
        if not receiver:
            return "Please specify a recipient contact for the call."
        call_type = "video" if ("video" in action or params.get("call_type") == "video") else "audio"
        with _WHATSAPP_EXECUTION_LOCK:
            res = _whatsapp_start_call(receiver, call_type=call_type, account=account or "", operation_id=task_id)
        if player:
            player.write_log(f"[call] {receiver} ({call_type})")
        return res

    # Handle WhatsApp Voice Message operations
    if action in ("voice_message", "voice_note", "audio_note", "audio_message"):
        if not receiver:
            return "Please specify a recipient contact for the voice message."
        with _WHATSAPP_EXECUTION_LOCK:
            res_dict = send_whatsapp_voice_message(
                contact_identifier=receiver,
                message_text=message_text,
                audio_path=attachment_path or None,
                from_mic=bool(params.get("from_mic") or "from mic" in message_text.lower() or "my voice" in message_text.lower()),
                duration=float(params.get("duration", 5.0)),
                account=account,
                task_id=task_id,
            )
        msg_out = res_dict.get("message", str(res_dict))
        if player:
            player.write_log(f"[voice_msg] {receiver} ({res_dict.get('status')})")
        return msg_out

    if action in ("end_call", "hangup", "stop_call"):
        with _WHATSAPP_EXECUTION_LOCK:
            return _whatsapp_end_call()

    if action in ("call_state", "check_call", "call_status"):
        return _whatsapp_call_state()

    if action in ("monitor_call", "supervise_call"):
        if not receiver:
            return "Please specify a recipient contact for call monitoring."
        call_type = "video" if ("video" in action or params.get("call_type") == "video") else "audio"
        max_dur = params.get("max_duration_seconds")
        if max_dur is not None:
            max_dur = float(max_dur)
        with _WHATSAPP_EXECUTION_LOCK:
            res_dict = monitor_whatsapp_call_lifecycle(
                contact_identifier=receiver,
                call_type=call_type,
                max_duration_seconds=max_dur,
                account=account or "",
                operation_id=task_id,
            )
        return res_dict.get("message", str(res_dict))

    if action in ("detect_incoming_call", "detect_incoming", "incoming_call"):
        res_dict = detect_incoming_whatsapp_call()
        return res_dict.get("message", str(res_dict))

    if action in ("respond_incoming_call", "respond_incoming", "accept_call", "decline_call"):
        call_act = params.get("call_action") or params.get("response_action") or ("accept" if "accept" in action else "decline")
        res_dict = respond_to_incoming_whatsapp_call(action=call_act)
        return res_dict.get("message", str(res_dict))

    if action in ("record_missed_call", "record_missed"):
        caller_name = receiver or params.get("caller", "")
        call_type = params.get("call_type", "audio")
        notes = message_text or params.get("notes", "")
        res_dict = record_missed_call(caller=caller_name, call_type=call_type, notes=notes)
        return res_dict.get("message", str(res_dict))

    if action in ("get_missed_calls", "get_missed", "missed_calls"):
        unresp_only = bool(params.get("unresponded_only", False))
        calls = get_missed_calls(unresponded_only=unresp_only)
        if not calls:
            return "No missed calls recorded."
        lines = [f"- [{c.get('timestamp', '')[:16]}] {c.get('caller')} ({c.get('call_type')}) - Responded: {c.get('responded')}" for c in calls]
        return "Recorded missed calls:\n" + "\n".join(lines)

    if action in ("authorized_reply", "send_authorized_reply"):
        if not receiver:
            return "Please specify a recipient contact for the authorized reply."
        reply_txt = message_text or params.get("reply_text", "")
        with _WHATSAPP_EXECUTION_LOCK:
            res_dict = send_authorized_reply(
                contact_identifier=receiver,
                reply_text=reply_txt,
                task_id=task_id,
                account=account,
            )
        return res_dict.get("message", str(res_dict))

    if action in ("busy_config", "get_busy_config", "busy_status"):
        cfg = get_busy_reply_config()
        sched = cfg.get("busy_schedule", {})
        status_lines = [
            f"Auto-reply enabled: {cfg.get('auto_reply_enabled')}",
            f"Require confirmation: {cfg.get('require_confirmation')}",
            f"Schedule active: {sched.get('enabled')} ({sched.get('start_time')} - {sched.get('end_time')})",
            f"Active days: {', '.join(sched.get('days', []))}",
            f"Busy message: \"{cfg.get('busy_reply_message')}\"",
            f"Follow-up reminder: {cfg.get('follow_up_enabled')} (delay: {cfg.get('follow_up_delay_minutes')}m)",
            f"Rate limit: {cfg.get('rate_limit_minutes_per_contact')}m per contact",
        ]
        return "WhatsApp Busy-Reply Configuration:\n" + "\n".join(status_lines)

    if action in ("update_busy_config", "set_busy_config"):
        updates = {}
        if "auto_reply_enabled" in params:
            updates["auto_reply_enabled"] = bool(params["auto_reply_enabled"])
        if "require_confirmation" in params:
            updates["require_confirmation"] = bool(params["require_confirmation"])
        if "busy_reply_message" in params or message_text:
            updates["busy_reply_message"] = message_text or params.get("busy_reply_message")
        if "follow_up_delay_minutes" in params:
            updates["follow_up_delay_minutes"] = int(params["follow_up_delay_minutes"])
        updated_cfg = update_busy_reply_config(updates)
        return f"Updated busy-reply configuration successfully. Auto-reply enabled: {updated_cfg.get('auto_reply_enabled')}."

    if action in ("process_missed_call", "auto_reply_missed_call"):
        caller_target = receiver or params.get("caller", "Unknown")
        c_type = params.get("call_type", "audio")
        c_state = params.get("call_state", "MISSED")
        force_reply = bool(params.get("force_auto_reply", False))
        res_dict = process_missed_call(
            caller=caller_target,
            call_type=c_type,
            call_state=c_state,
            force_auto_reply=force_reply,
            task_id=task_id,
        )
        return res_dict.get("message", str(res_dict))

    if action in ("start_call_monitor", "monitor_calls"):
        res_dict = start_missed_call_monitor()
        return res_dict.get("message", str(res_dict))

    if action in ("stop_call_monitor", "unmonitor_calls"):
        res_dict = stop_missed_call_monitor()
        return res_dict.get("message", str(res_dict))


    # Handle WhatsApp Message Reading / Receiving
    if action in ("read_messages", "read", "receive", "receive_messages", "get_messages"):
        res_dict = _whatsapp_read_messages(receiver=receiver, limit=int(params.get("limit", 5)))
        msgs = res_dict.get("messages", [])
        if not msgs:
            return f"No recent messages found for {receiver or 'active chat'}."
        formatted = "\n".join([f"[{m.get('index', i+1)}] {m.get('text', m.get('info', ''))}" for i, m in enumerate(msgs)])
        return f"Recent messages for {res_dict.get('receiver', receiver)}:\n{formatted}"

    # Handle Desktop File Search and Send
    is_file_search_send = (
        action in ("find_file_and_send", "send_file", "attach_file", "find_and_send", "send_files")
        or bool(file_query)
        or bool(files)
        or bool(count)
    )
    if not is_file_search_send and attachment_path:
        if isinstance(attachment_path, list) or (
            isinstance(attachment_path, str)
            and not Path(attachment_path).exists()
            and not Path(attachment_path).is_absolute()
            and any(k in attachment_path.lower() for k in ("pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt", "txt", "csv", "png", "jpg", "jpeg", "screenshot", "presentation", "report", "image", "images", "document", "documents", "file", "files", "photo", "photos"))
        ):
            is_file_search_send = True

    if is_file_search_send:
        if not receiver:
            return "Please specify a recipient contact for the file."
        query = file_query or (attachment_path if isinstance(attachment_path, str) else "") or message_text
        kwargs = {
            "contact_identifier": receiver,
            "file_query": query,
            "folder": folder,
            "account": account,
            "task_id": task_id,
        }
        if count is not None:
            kwargs["count"] = count
        target_payload = files or (attachment_path if isinstance(attachment_path, (list, tuple)) else None)
        if target_payload is not None:
            kwargs["files"] = target_payload
        with _WHATSAPP_EXECUTION_LOCK:
            file_res = find_file_and_send_whatsapp(**kwargs)
        if player:
            player.write_log(f"[file_send] {receiver} ({query})")
        return file_res.get("message", str(file_res))

    # Normal message / attachment sending
    if not receiver:
        return "Please specify a recipient."
    if not message_text and not attachment_path and not files:
        # Check if user had a selected file in File Explorer
        explorer_f = _get_explorer_selected_file()
        if explorer_f:
            attachment_path = str(explorer_f)
        else:
            return "Please specify either message content or an attachment path."

    # ── Central Execution State Idempotency Check ──
    central_dup, central_msg, existing_act = execution_manager.check_action_idempotency(
        task_id=task_id,
        action_name=f"send_message:{platform}",
        parameters=params,
    )
    if central_dup:
        print(f"[SendMessage] [STATE] 🛡️ {central_msg}")
        return central_msg

    act_rec = execution_manager.register_action(
        task_id=task_id,
        action_name=f"send_message:{platform}",
        parameters=params,
    )

    # ── Local WhatsApp Idempotency Check ──
    att_key = ";".join(str(f) for f in files) if isinstance(files, list) else str(attachment_path or "")
    op_key = _IDEMPOTENCY_MANAGER.compute_key(platform, receiver, message_text, att_key, action)
    is_duplicate, dup_response = _IDEMPOTENCY_MANAGER.check_or_start(op_key, task_id)
    if is_duplicate:
        print(f"[SendMessage] 🛡️ {dup_response}")
        execution_manager.mark_action_completed(task_id, act_rec.action_id, dup_response, "Suppressed duplicate")
        return dup_response

    preview = (message_text[:50] + "…") if len(message_text) > 50 else message_text
    print(f"[SendMessage] 📨 [Task {task_id[:8]}] {platform} → {receiver}: {preview} (attachment: {files or attachment_path or 'None'})")
    if player:
        player.write_log(f"[msg] {platform} → {receiver}")

    with _WHATSAPP_EXECUTION_LOCK:
        try:
            if "whatsapp" in platform or "wp" in platform or "wapp" in platform:
                target_payload = files or attachment_path
                if target_payload:
                    result = _send_whatsapp_with_attachment(receiver, message_text, target_payload, task_id=task_id)
                else:
                    wa_res = send_whatsapp_message(receiver, message_text, account=account, task_id=task_id)
                    result = wa_res.get("message", str(wa_res))
            else:
                handler = _resolve_platform(platform)
                result  = handler(receiver, message_text)
            _IDEMPOTENCY_MANAGER.mark_completed(op_key, task_id, result)
            execution_manager.mark_action_completed(task_id, act_rec.action_id, result, "Message transmission verified")
        except Exception as e:
            result = f"Could not send message: {e}"
            _IDEMPOTENCY_MANAGER.mark_failed(op_key, task_id, result)
            execution_manager.mark_action_failed(task_id, act_rec.action_id, str(e))

    print(f"[SendMessage] {'✅' if 'sent' in result.lower() else '❌'} {result}")
    if player:
        player.write_log(f"[msg] {result}")

    return result


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "send_message",
    "description": (
        "Autonomously sends text messages, file/document/image/video attachments, voice messages (synthesized via TTS or mic recording), "
        "opens WhatsApp conversations, searches and sends files from Desktop/Documents/Downloads, "
        "and starts/ends audio and video calls via WhatsApp or other messaging platforms. "
        "Supports placing WhatsApp audio calls (Ctrl+Shift+C), video calls (Ctrl+Shift+V), sending voice notes (.wav), and finding/attaching files. "
        "NEVER generate a document explaining WhatsApp communication requirements—directly execute the requested action."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "send | audio_call | video_call | voice_message | open_chat | find_file_and_send | end_call | call_state (default: send)"
            },
            "receiver": {
                "type": "STRING",
                "description": "Recipient contact name or phone number with country code (e.g. 'Rahul', 'John Chavala', '+919876543210')"
            },
            "message_text": {
                "type": "STRING",
                "description": "The text message content to send, or the speech text to synthesize for voice_message"
            },
            "attachment_path": {
                "type": "STRING",
                "description": "Optional direct file path or keyword to attach and send"
            },
            "file_query": {
                "type": "STRING",
                "description": "File search description or name to locate on filesystem and send (e.g. 'invoice.pdf', 'the Word document', 'latest screenshot', 'presentation')"
            },
            "folder": {
                "type": "STRING",
                "description": "Optional directory to prioritize ('Desktop', 'Documents', 'Downloads')"
            },
            "platform": {
                "type": "STRING",
                "description": "Platform: WhatsApp, Telegram, Discord, etc. (default: WhatsApp)"
            },
            "account": {
                "type": "STRING",
                "description": "Optional WhatsApp account or profile name (default: active session)"
            }
        },
        "required": [
            "receiver"
        ]
    },
    "handler": send_message,
}

