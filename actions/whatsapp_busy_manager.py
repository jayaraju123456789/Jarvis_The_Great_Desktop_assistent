"""
whatsapp_busy_manager.py — Advanced Missed-Call Detection, Busy Schedule Evaluation,
and Automated Busy-Reply Dispatcher for JARVIS WhatsApp Desktop Automation.

Features:
- Monitor Health Lifecycle: STOPPED, RUNNING, APP_UNAVAILABLE, RECOVERING, ERROR.
- Non-Intrusive Process & Window Monitoring (no continuous screenshot capture).
- Accurate Call-State Detection: RINGING, ANSWERED, DECLINED, MISSED, UNKNOWN.
- 7-Point Safety Verification Gate before automated reply dispatch.
- Idempotency & Frequency-Capped Rate Limiting (15m window per contact).
- Non-Blind Retry Safeguards: Verifies chat evidence on timeouts before retrying.
- WhatsApp Closure & Recovery Lifecycle with Transparent Downtime Reporting.
- Concurrency-safe single worker loop and clean exit via atexit.
"""

import os
import sys
import json
import time
import uuid
import atexit
import hashlib
import threading
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union

# Threading lock for thread-safe config and event log updates
_BUSY_LOCK = threading.RLock()


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _get_busy_config_path() -> Path:
    p = _get_base_dir() / "config" / "busy_reply_config.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _get_missed_calls_path() -> Path:
    p = _get_base_dir() / "config" / "missed_calls.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


DEFAULT_BUSY_CONFIG: Dict[str, Any] = {
    "auto_reply_enabled": False,
    "require_confirmation": False,
    "busy_schedule": {
        "enabled": True,
        "days": [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ],
        "start_time": "09:00",
        "end_time": "18:00",
        "timezone": "local",
    },
    "busy_reply_message": "Hi, I’m busy right now and couldn’t answer your call. I’ll get back to you as soon as possible.",
    "follow_up_enabled": True,
    "follow_up_delay_minutes": 30,
    "duplicate_prevention_enabled": True,
    "rate_limit_minutes_per_contact": 15,
    "min_ring_duration_seconds": 12.0,
    "allowed_contacts": [],
    "excluded_contacts": [],
}


def load_busy_config() -> Dict[str, Any]:
    """Load busy-reply configuration from JSON with fallback to defaults."""
    with _BUSY_LOCK:
        p = _get_busy_config_path()
        if not p.exists():
            save_busy_config(DEFAULT_BUSY_CONFIG)
            return dict(DEFAULT_BUSY_CONFIG)
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(cfg, dict):
                # Merge defaults for any missing keys
                merged = dict(DEFAULT_BUSY_CONFIG)
                merged.update(cfg)
                if "busy_schedule" in cfg and isinstance(cfg["busy_schedule"], dict):
                    sched = dict(DEFAULT_BUSY_CONFIG["busy_schedule"])
                    sched.update(cfg["busy_schedule"])
                    merged["busy_schedule"] = sched
                return merged
        except Exception:
            pass
        return dict(DEFAULT_BUSY_CONFIG)


def save_busy_config(config_data: Dict[str, Any]) -> bool:
    """Save busy-reply configuration to persistent JSON storage."""
    with _BUSY_LOCK:
        p = _get_busy_config_path()
        try:
            p.write_text(json.dumps(config_data, indent=2, ensure_ascii=False), encoding="utf-8")
            return True
        except Exception as e:
            print(f"[BusyManager] Failed saving busy config: {e}")
            return False


def update_busy_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update specific busy-reply settings."""
    with _BUSY_LOCK:
        current = load_busy_config()
        for k, v in updates.items():
            if k == "busy_schedule" and isinstance(v, dict):
                current["busy_schedule"].update(v)
            else:
                current[k] = v
        save_busy_config(current)
        return current


def is_whatsapp_process_running() -> bool:
    """
    Check whether WhatsApp Desktop process is running without capturing screenshots or invoking heavy UI trees.
    """
    if os.environ.get("JARVIS_TEST_MODE") == "1":
        return os.environ.get("MOCK_WHATSAPP_CLOSED") != "1"

    target_procs = {"whatsapp.exe", "whatsapp.root.exe", "whatsappdesktop.exe"}
    try:
        import psutil
        for p in psutil.process_iter(attrs=["name"]):
            try:
                pname = (p.info.get("name") or "").lower()
                if pname in target_procs:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass

    # Secondary check: fast top-level Win32 window lookup without enumeration
    try:
        import win32gui
        hwnd = win32gui.FindWindow("WinUIDesktopWin32WindowClass", None)
        if hwnd and win32gui.IsWindow(hwnd):
            return True
    except Exception:
        pass

    return False


def is_within_busy_schedule(
    dt: Optional[datetime] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """
    Check whether a given datetime falls within the configured busy schedule.
    Handles same-day ranges (e.g. 09:00 - 18:00) and overnight spans (e.g. 22:00 - 06:00).
    """
    cfg = config or load_busy_config()
    sched = cfg.get("busy_schedule", {})
    if not sched.get("enabled", True):
        return True, "Busy schedule constraint is disabled; auto-reply is active all the time."

    check_dt = dt or datetime.now()
    day_name = check_dt.strftime("%A")

    active_days = sched.get("days", [])
    if active_days and day_name not in active_days:
        return False, f"Current day ({day_name}) is not in active busy days list ({active_days})."

    start_str = sched.get("start_time", "09:00").strip()
    end_str = sched.get("end_time", "18:00").strip()

    try:
        sh, sm = map(int, start_str.split(":"))
        eh, em = map(int, end_str.split(":"))
        start_time = dt_time(sh, sm)
        end_time = dt_time(eh, em)
    except Exception as e:
        return True, f"Failed parsing start/end times ({start_str}, {end_str}): {e}. Defaulting to active."

    cur_time = check_dt.time()

    if start_time <= end_time:
        # Standard same-day window (e.g., 09:00 to 18:00)
        in_range = start_time <= cur_time <= end_time
    else:
        # Overnight window (e.g., 22:00 to 06:00)
        in_range = cur_time >= start_time or cur_time <= end_time

    if in_range:
        return True, f"Current time ({cur_time.strftime('%H:%M')}) is within busy hours ({start_str} - {end_str})."
    else:
        return False, f"Current time ({cur_time.strftime('%H:%M')}) is outside busy hours ({start_str} - {end_str})."


def can_reply_to_contact(
    contact_identifier: str,
    config: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """
    Determine if an automated reply is permitted for the given contact.
    Evaluates:
    1. Excluded contacts (denylist)
    2. Allowed contacts (allowlist, if non-empty)
    3. Rate limiting / frequency capping (15-minute cooldown per contact)
    """
    cfg = config or load_busy_config()
    c_clean = contact_identifier.strip().lower()

    # 1. Denylist check
    excluded = [str(x).strip().lower() for x in cfg.get("excluded_contacts", []) if str(x).strip()]
    for ex in excluded:
        if ex in c_clean or c_clean in ex:
            return False, f"Contact '{contact_identifier}' is in the excluded contacts list."

    # 2. Allowlist check
    allowed = [str(x).strip().lower() for x in cfg.get("allowed_contacts", []) if str(x).strip()]
    if allowed:
        matched = any(al in c_clean or c_clean in al for al in allowed)
        if not matched:
            return False, f"Contact '{contact_identifier}' is not in the allowed contacts list."

    # 3. Rate limiting check (avoid spamming repeated callers)
    rate_limit_mins = cfg.get("rate_limit_minutes_per_contact", 15)
    if rate_limit_mins > 0:
        recent_cutoff = datetime.now() - timedelta(minutes=rate_limit_mins)
        missed_log = load_missed_call_records()
        for rec in reversed(missed_log):
            if rec.get("responded") and rec.get("response_timestamp"):
                r_caller = rec.get("caller", "").strip().lower()
                if (r_caller in c_clean or c_clean in r_caller) and rec.get("status") in ("SENT", "DELIVERED"):
                    try:
                        resp_time = datetime.fromisoformat(rec["response_timestamp"])
                        if resp_time > recent_cutoff:
                            mins_ago = int((datetime.now() - resp_time).total_seconds() / 60)
                            return False, f"Rate limited: already replied to '{contact_identifier}' {mins_ago}m ago (window: {rate_limit_mins}m)."
                    except Exception:
                        pass

    return True, f"Contact '{contact_identifier}' is eligible for automated busy reply."


def generate_event_idempotency_key(caller: str, call_type: str, timestamp_str: str) -> str:
    """Generate a deterministic idempotency key for a call event to prevent duplicate responses."""
    try:
        dt = datetime.fromisoformat(timestamp_str)
        # Round timestamp to the nearest 2-minute bucket
        bucket = dt.strftime("%Y%m%d_%H") + f"_{(dt.minute // 2) * 2:02d}"
    except Exception:
        bucket = timestamp_str[:16]
    raw = f"{caller.strip().lower()}_{call_type.strip().lower()}_{bucket}"
    return f"idemp_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"


def load_missed_call_records() -> List[Dict[str, Any]]:
    """Retrieve all recorded call records from JSON storage."""
    with _BUSY_LOCK:
        p = _get_missed_calls_path()
        if not p.exists():
            return []
        try:
            records = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(records, list):
                return records
        except Exception:
            pass
        return []


def save_missed_call_records(records: List[Dict[str, Any]]) -> bool:
    """Persist call records to JSON storage."""
    with _BUSY_LOCK:
        p = _get_missed_calls_path()
        try:
            p.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
            return True
        except Exception as e:
            print(f"[BusyManager] Failed writing call records: {e}")
            return False


def schedule_follow_up_reminder(
    contact_name: str,
    delay_minutes: int = 30,
    note: str = "",
) -> Dict[str, Any]:
    """
    Schedule a native JARVIS reminder via actions/reminder.py to follow up with a caller.
    """
    try:
        from actions.reminder import reminder
        target_dt = datetime.now() + timedelta(minutes=delay_minutes)
        date_str = target_dt.strftime("%Y-%m-%d")
        time_str = target_dt.strftime("%H:%M")
        msg = f"Follow up with WhatsApp caller '{contact_name}'. ({note or 'Missed call busy follow-up'})"

        rem_res = reminder({
            "date": date_str,
            "time": time_str,
            "message": msg,
        })
        return {
            "success": "Reminder set" in rem_res or "registered" in rem_res.lower(),
            "target_time": f"{date_str} {time_str}",
            "message": rem_res,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed scheduling follow-up reminder: {e}",
        }


def evaluate_call_outcome(
    caller: str,
    call_type: str = "audio",
    ring_duration: float = 0.0,
    config: Optional[Dict[str, Any]] = None,
    evidence: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str, Dict[str, Any]]:
    """
    Conservatively evaluate call outcome using multi-signal evidence.
    Distinguishes:
    - ANSWERED: Connected call active.
    - DECLINED: User explicitly declined via JARVIS command or recorded decline.
    - MISSED: Call rang for full sustained duration (>= min_ring_duration_seconds)
              AND has verified corroborating evidence (missed call notification toast,
              unread badge counter, or verified signal). Ring duration ALONE is NEVER
              treated as proof that a call was missed.
    - UNKNOWN: Inconclusive, contradictory, unverified sustained ring, short ring,
               caller cancellation, physical mouse decline, or popup dismissal.

    CRITICAL SAFETY RULES:
    1. Ring duration alone is NEVER treated as proof of a missed call.
    2. A physical mouse click on Decline, a caller cancellation, or a popup disappearance
       cannot be reliably distinguished out-of-process without intrusive chat switching.
       If corroborating missed-call evidence is absent, the outcome ALWAYS fails safe to UNKNOWN.
    3. UNKNOWN events NEVER trigger automatic replies.
    """
    from actions.whatsapp_calling import (
        check_whatsapp_call_status,
        was_recently_declined,
        detect_missed_call_notification,
        detect_whatsapp_unread_badge,
    )

    cfg = config or load_busy_config()
    min_ring = float(cfg.get("min_ring_duration_seconds", 12.0))
    ev = evidence or {}

    # Signal 0: Contradictory signal check
    active_status = check_whatsapp_call_status()
    is_active = bool(active_status.get("is_active") or ev.get("is_active"))
    is_declined = bool(was_recently_declined(caller) or ev.get("declined"))

    if ev.get("contradictory") or (is_active and is_declined):
        return (
            "UNKNOWN",
            f"Contradictory call signals detected for '{caller}'; outcome inconclusive (UNKNOWN).",
            {"signal": "contradictory_evidence"},
        )

    # Signal 1: Check if call was answered (connected session active)
    if is_active:
        return "ANSWERED", f"Call with '{caller}' connected (ANSWERED).", {"signal": "active_call_session"}

    # Signal 2: Check if call was explicitly declined (via JARVIS action or recorded decline)
    if is_declined:
        return "DECLINED", f"Call from '{caller}' was explicitly DECLINED by user.", {"signal": "explicit_decline"}

    # Signal 3: App health / abrupt termination check
    if not is_whatsapp_process_running() or ev.get("app_closed"):
        return "UNKNOWN", f"WhatsApp closed abruptly during call; outcome inconclusive (UNKNOWN).", {"signal": "app_closed"}

    # Signal 4: Short ring duration check (< min_ring_duration_seconds)
    if ring_duration < min_ring:
        reason = (
            f"Call from '{caller}' ceased after {ring_duration:.1f}s (below {min_ring:.1f}s threshold). "
            f"Caller cancellation, physical Decline click, or popup dismissal cannot be differentiated; "
            f"auto-reply safely suppressed (UNKNOWN)."
        )
        return "UNKNOWN", reason, {
            "signal": "short_duration_inconclusive",
            "ring_duration": ring_duration,
            "threshold": min_ring,
        }

    # Signal 5: Sustained ring duration (>= min_ring_duration_seconds)
    # CRITICAL: Ring duration alone is NEVER proof of a missed call!
    # Evaluate caller-specific corroborating evidence (missed call notification toast matching caller, or verified signal).
    # NOTE: A generic unread badge on WhatsApp main window title cannot prove a specific caller's call was missed
    # because pre-existing or unrelated unread messages from other chats also increment the badge.
    has_toast = ev.get("has_missed_call_notification") or ev.get("missed_call_toast")
    if has_toast is None and not ev.get("unverified"):
        try:
            has_toast = detect_missed_call_notification(caller)
        except Exception:
            has_toast = False

    has_badge = ev.get("has_unread_badge")
    if has_badge is None and not ev.get("unverified"):
        try:
            has_badge = detect_whatsapp_unread_badge()
        except Exception:
            has_badge = False

    verified_signal = ev.get("verified_missed") or ev.get("corroborated")

    # Strict caller-specific corroboration: generic unread badge is recorded as supplemental context
    # but CANNOT independently corroborate a missed call for this caller.
    has_corroborating_evidence = bool(has_toast or verified_signal)

    if has_corroborating_evidence:
        corroborating_data = {
            "signal": "confirmed_missed_call",
            "ring_duration": ring_duration,
            "threshold": min_ring,
            "has_missed_call_notification": bool(has_toast),
            "has_unread_badge": bool(has_badge),
            "verified_signal": bool(verified_signal),
        }
        reason = f"Call from '{caller}' confirmed as MISSED ({ring_duration:.1f}s) with corroborating evidence (caller-specific notification/verified signal)."
        return "MISSED", reason, corroborating_data

    # Without corroborating evidence, physical mouse decline, caller cancellation, or popup dismissal
    # cannot be reliably distinguished. Must fail safely to UNKNOWN.
    reason = (
        f"Call from '{caller}' ceased after {ring_duration:.1f}s without corroborating missed-call evidence. "
        f"Manual physical Decline click, caller cancellation, or popup dismissal cannot be reliably distinguished; "
        f"auto-reply safely suppressed (UNKNOWN)."
    )
    return "UNKNOWN", reason, {
        "signal": "sustained_ring_unverified_ambiguous",
        "ring_duration": ring_duration,
        "threshold": min_ring,
    }


def process_missed_call_lifecycle(
    caller: str,
    call_type: str = "audio",
    call_state: str = "MISSED",
    timestamp: Optional[str] = None,
    notes: str = "",
    force_auto_reply: bool = False,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    End-to-end processing pipeline for a detected call event.
    Enforces the 7 Strict Safety Rules:
    1. Validation of call state: only genuine MISSED calls trigger replies (UNKNOWN or DECLINED are skipped).
    2. Idempotency & duplicate check: prevents reprocessing same call bucket.
    3. Master auto_reply_enabled check.
    4. Busy schedule check: validates time and active days.
    5. Contact eligibility & rate-limiting check: denylist, allowlist, and 15m frequency cap.
    6. Confirmation requirement check.
    7. Dispatch of reply with non-blind retries: verifies evidence before retrying.
    8. Follow-up reminder scheduling.
    """
    op_id = task_id or f"mc_evt_{uuid.uuid4().hex[:8]}"
    ts = timestamp or datetime.now().isoformat()
    clean_caller = (caller or "Unknown").strip()
    norm_state = (call_state or "UNKNOWN").upper().strip()

    idemp_key = generate_event_idempotency_key(clean_caller, call_type, ts)
    cfg = load_busy_config()

    # Rule 1: Call-state validation (Must be genuinely MISSED; never UNKNOWN or DECLINED)
    if norm_state != "MISSED":
        return {
            "success": False,
            "event_id": op_id,
            "idempotency_key": idemp_key,
            "caller": clean_caller,
            "call_state": norm_state,
            "status": "SKIPPED_NOT_MISSED",
            "delivery_status": "SKIPPED",
            "reply_text": None,
            "message": f"Call state is '{norm_state}' (not 'MISSED'). No busy reply permitted.",
        }

    # Rule 2: Idempotency & duplicate prevention check
    records = load_missed_call_records()
    if cfg.get("duplicate_prevention_enabled", True):
        for rec in records:
            if rec.get("idempotency_key") == idemp_key:
                if rec.get("status") in ("SENT", "DELIVERED", "REPLY_PENDING", "PROCESSING", "DETECTED") or rec.get("responded"):
                    return {
                        "success": True,
                        "event_id": rec.get("id", op_id),
                        "idempotency_key": idemp_key,
                        "caller": clean_caller,
                        "call_state": "MISSED",
                        "status": "DUPLICATE_SUPPRESSED",
                        "delivery_status": rec.get("delivery_status", "ALREADY_PROCESSED"),
                        "message": f"Duplicate event suppressed: reply already processed for key '{idemp_key}'.",
                        "existing_record": rec,
                    }

    # Prepare base record
    event_record = {
        "id": op_id,
        "idempotency_key": idemp_key,
        "caller": clean_caller,
        "call_type": call_type,
        "call_state": norm_state,
        "timestamp": ts,
        "notes": notes,
        "status": "DETECTED",
        "responded": False,
        "reply_text": None,
        "response_timestamp": None,
        "delivery_status": "PENDING",
        "follow_up_scheduled": False,
        "follow_up_details": None,
    }

    # Rule 3: Master auto-reply switch check
    auto_enabled = cfg.get("auto_reply_enabled", False) or force_auto_reply
    if not auto_enabled:
        event_record["status"] = "VERIFIED"
        event_record["delivery_status"] = "DISABLED"
        event_record["notes"] += " [Auto-reply disabled in settings]"
        records.append(event_record)
        save_missed_call_records(records)
        return {
            "success": True,
            "event_id": op_id,
            "idempotency_key": idemp_key,
            "caller": clean_caller,
            "call_state": norm_state,
            "status": "VERIFIED_AUTO_REPLY_DISABLED",
            "delivery_status": "DISABLED",
            "message": f"Recorded missed call from '{clean_caller}'. Auto-reply is disabled in settings.",
            "record": event_record,
        }

    # Rule 4: Busy schedule check
    is_busy, busy_reason = is_within_busy_schedule(datetime.fromisoformat(ts) if "T" in ts else None, cfg)
    if not is_busy and not force_auto_reply:
        event_record["status"] = "VERIFIED"
        event_record["delivery_status"] = "OUTSIDE_BUSY_HOURS"
        event_record["notes"] += f" [{busy_reason}]"
        records.append(event_record)
        save_missed_call_records(records)
        return {
            "success": True,
            "event_id": op_id,
            "idempotency_key": idemp_key,
            "caller": clean_caller,
            "call_state": norm_state,
            "status": "OUTSIDE_BUSY_HOURS",
            "delivery_status": "OUTSIDE_BUSY_HOURS",
            "message": f"Missed call from '{clean_caller}' recorded, but current time is outside busy hours ({busy_reason}).",
            "record": event_record,
        }

    # Rule 5: Contact eligibility & rate-limiting check
    can_reply, contact_reason = can_reply_to_contact(clean_caller, cfg)
    if not can_reply and not force_auto_reply:
        event_record["status"] = "VERIFIED"
        event_record["delivery_status"] = "SUPPRESSED"
        event_record["notes"] += f" [{contact_reason}]"
        records.append(event_record)
        save_missed_call_records(records)
        return {
            "success": True,
            "event_id": op_id,
            "idempotency_key": idemp_key,
            "caller": clean_caller,
            "call_state": norm_state,
            "status": "CONTACT_SUPPRESSED",
            "delivery_status": "SUPPRESSED",
            "message": f"Auto-reply suppressed for '{clean_caller}': {contact_reason}",
            "record": event_record,
        }

    # Rule 6: Confirmation requirement check
    if cfg.get("require_confirmation", False) and not force_auto_reply:
        event_record["status"] = "REPLY_PENDING_CONFIRMATION"
        event_record["delivery_status"] = "VERIFICATION_REQUIRED"
        records.append(event_record)
        save_missed_call_records(records)
        return {
            "success": True,
            "event_id": op_id,
            "idempotency_key": idemp_key,
            "caller": clean_caller,
            "call_state": norm_state,
            "status": "REPLY_PENDING_CONFIRMATION",
            "delivery_status": "VERIFICATION_REQUIRED",
            "message": f"Auto-reply prepared for '{clean_caller}' but requires manual user confirmation per settings.",
            "record": event_record,
        }

    # Rule 7: Sending mechanism with non-blind retry verification
    reply_msg = cfg.get("busy_reply_message") or DEFAULT_BUSY_CONFIG["busy_reply_message"]
    event_record["status"] = "REPLY_PENDING"
    event_record["reply_text"] = reply_msg

    from actions.whatsapp_calling import (
        send_authorized_reply,
        contact_resolver,
        _verify_whatsapp_outgoing_bubble,
        _find_whatsapp_window,
    )

    # Resolve contact for clean target identifier
    res = contact_resolver.resolve(clean_caller)
    target_id = res.matched_name if res.status in ("EXACT", "PARTIAL") else (res.phone_number or clean_caller)

    send_success = False
    send_result: Dict[str, Any] = {}
    max_retries = 2

    for attempt in range(1, max_retries + 1):
        try:
            send_result = send_authorized_reply(
                contact_identifier=target_id,
                reply_text=reply_msg,
                task_id=f"{op_id}_send_{attempt}",
            )
            if send_result.get("success"):
                send_success = True
                break
            else:
                # Check if failure was an uncertain timeout after clicking Send
                ret_status = send_result.get("status", "")
                if ret_status in ("SEND_REQUESTED", "TIMEOUT", "UNCERTAIN"):
                    # Non-blind retry check: inspect if outgoing bubble already appeared
                    hwnd = _find_whatsapp_window()
                    if hwnd:
                        is_visible, v_status, _ = _verify_whatsapp_outgoing_bubble(hwnd, reply_msg, timeout=2.0)
                        if is_visible:
                            send_success = True
                            send_result["status"] = v_status
                            break
                    # If outcome cannot be safely verified, withhold blind retry to prevent sending duplicate text
                    event_record["status"] = "UNKNOWN"
                    event_record["delivery_status"] = "VERIFICATION_REQUIRED"
                    event_record["notes"] += f" [Send outcome uncertain ({ret_status}); withheld retry to prevent duplicate messages]"
                    break

                time.sleep(1.0)
        except Exception as e:
            send_result = {"success": False, "error": str(e)}
            time.sleep(1.0)

    if send_success:
        event_record["status"] = "SENT"
        event_record["responded"] = True
        event_record["response_timestamp"] = datetime.now().isoformat()
        event_record["delivery_status"] = send_result.get("status", "SENT")
    elif event_record["status"] != "UNKNOWN":
        event_record["status"] = "FAILED"
        event_record["delivery_status"] = "FAILED"
        event_record["notes"] += f" [Send failed: {send_result.get('error', send_result.get('message', 'Unknown'))}]"

    # Step 8: Follow-up reminder scheduling
    if send_success and cfg.get("follow_up_enabled", True):
        delay = int(cfg.get("follow_up_delay_minutes", 30))
        rem_info = schedule_follow_up_reminder(
            contact_name=clean_caller,
            delay_minutes=delay,
            note="Follow-up after missed call busy reply",
        )
        event_record["follow_up_scheduled"] = rem_info.get("success", False)
        event_record["follow_up_details"] = rem_info

    records.append(event_record)
    save_missed_call_records(records)

    return {
        "success": send_success,
        "event_id": op_id,
        "idempotency_key": idemp_key,
        "caller": clean_caller,
        "call_state": norm_state,
        "status": event_record["status"],
        "delivery_status": event_record["delivery_status"],
        "reply_text": reply_msg,
        "follow_up_scheduled": event_record.get("follow_up_scheduled", False),
        "message": f"Busy reply successfully sent to '{clean_caller}'." if send_success else f"Failed to send busy reply to '{clean_caller}': {send_result.get('message', 'Unknown error')}",
        "record": event_record,
    }


class MonitorHealth:
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    APP_UNAVAILABLE = "APP_UNAVAILABLE"
    RECOVERING = "RECOVERING"
    ERROR = "ERROR"


class WhatsAppCallMonitor:
    """
    Lightweight, resilient call lifecycle observer for WhatsApp Desktop.
    Features:
    - Monitors process health and exposes state: STOPPED, RUNNING, APP_UNAVAILABLE, RECOVERING, ERROR.
    - Prevents duplicate worker loops using concurrency locks.
    - Uses lightweight polling without capturing screenshots.
    - Bounded retries and exponential backoff for transient RPC/COM errors.
    - Distinguishes ANSWERED, DECLINED, MISSED, and UNKNOWN call outcomes.
    - Clean shutdown via atexit.
    - Transparent reporting of downtime monitoring gaps.
    """

    def __init__(self, poll_interval: float = 2.0):
        self.poll_interval = poll_interval
        self._running = False
        self._health = MonitorHealth.STOPPED
        self._thread: Optional[threading.Thread] = None
        self._monitor_lock = threading.Lock()
        self._current_call: Optional[Dict[str, Any]] = None
        self._last_state_change = datetime.now().isoformat()
        self._downtime_start: Optional[float] = None
        self._total_downtime_seconds: float = 0.0
        self._downtime_events: List[Dict[str, Any]] = []
        self._consecutive_errors: int = 0

    def start(self) -> Dict[str, Any]:
        """Start background monitor thread with single-worker guarantee."""
        with self._monitor_lock:
            if self._running and self._thread and self._thread.is_alive():
                return {"success": True, "health": self._health, "message": "Call monitor is already running."}
            self._running = True
            self._health = MonitorHealth.RUNNING if is_whatsapp_process_running() else MonitorHealth.APP_UNAVAILABLE
            self._last_state_change = datetime.now().isoformat()
            self._consecutive_errors = 0
            self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="WhatsAppCallMonitor")
            self._thread.start()
            return {"success": True, "health": self._health, "message": f"Call monitor started with health: {self._health}."}

    def stop(self) -> Dict[str, Any]:
        """Stop background monitor thread cleanly."""
        with self._monitor_lock:
            self._running = False
            self._health = MonitorHealth.STOPPED
            self._last_state_change = datetime.now().isoformat()
            if self._thread:
                self._thread.join(timeout=3.0)
                self._thread = None
            return {"success": True, "health": MonitorHealth.STOPPED, "message": "Call monitor stopped cleanly."}

    def is_running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    def get_health(self) -> str:
        """Return the current monitor health state."""
        if not self._running:
            return MonitorHealth.STOPPED
        return self._health

    def get_status(self) -> Dict[str, Any]:
        """Return full diagnostic snapshot of the call monitor."""
        return {
            "running": self.is_running(),
            "health": self.get_health(),
            "last_state_change": self._last_state_change,
            "active_call": self._current_call,
            "consecutive_errors": self._consecutive_errors,
            "total_downtime_seconds": round(self._total_downtime_seconds, 1),
            "downtime_events_count": len(self._downtime_events),
        }

    def get_downtime_recovery_report(self) -> Dict[str, Any]:
        """
        Transparently report downtime gaps and platform capabilities.
        Factual truth: Personal VoIP calls arriving when WhatsApp is closed cannot be recovered
        without intrusive desktop UI navigation to Calls history.
        """
        return {
            "supported": False,
            "status": "PLATFORM_LIMITATION",
            "message": "Calls received while WhatsApp Desktop was completely closed cannot be recovered automatically via desktop UI. Official Meta WhatsApp Cloud API does not support personal VoIP call webhooks, and local desktop notifications do not persist closed-app call queues without intrusive UI navigation.",
            "total_downtime_seconds": round(self._total_downtime_seconds, 1),
            "downtime_events": list(self._downtime_events[-5:]),
        }

    def _monitor_loop(self):
        from actions.whatsapp_calling import (
            detect_incoming_whatsapp_call,
            check_whatsapp_call_status,
            was_recently_declined,
        )

        while self._running:
            current_sleep = self.poll_interval

            try:
                # 1. Process availability check (no screenshots or heavy UIA)
                app_alive = is_whatsapp_process_running()

                if not app_alive:
                    if self._health != MonitorHealth.APP_UNAVAILABLE:
                        self._health = MonitorHealth.APP_UNAVAILABLE
                        self._last_state_change = datetime.now().isoformat()
                        self._downtime_start = time.time()
                        if self._current_call:
                            # WhatsApp terminated abruptly while ringing
                            c_info = self._current_call
                            self._current_call = None
                            print(f"[CallMonitor] ⚠️ WhatsApp closed abruptly during incoming call from '{c_info['caller']}'.")
                            process_missed_call_lifecycle(
                                caller=c_info["caller"],
                                call_type=c_info["call_type"],
                                call_state="UNKNOWN",
                                notes="WhatsApp closed abruptly during call; state marked UNKNOWN.",
                            )
                        print("[CallMonitor] ⚠️ WhatsApp Desktop process is unavailable. Pausing UI monitoring.")

                    # Sleep with backoff while app is unavailable (4.0s)
                    time.sleep(4.0)
                    continue

                else:
                    # App is alive!
                    if self._health == MonitorHealth.APP_UNAVAILABLE:
                        self._health = MonitorHealth.RECOVERING
                        self._last_state_change = datetime.now().isoformat()
                        if self._downtime_start:
                            dt_gap = time.time() - self._downtime_start
                            self._total_downtime_seconds += dt_gap
                            self._downtime_events.append({
                                "start": datetime.fromtimestamp(self._downtime_start).isoformat(),
                                "duration_seconds": round(dt_gap, 1),
                            })
                            self._downtime_start = None
                            print(f"[CallMonitor] 🔄 WhatsApp Desktop reopened after {round(dt_gap, 1)}s downtime. Reinitializing monitor...")
                        time.sleep(1.0)  # Brief stabilization period
                        self._health = MonitorHealth.RUNNING
                        self._consecutive_errors = 0

                # 2. Query incoming call state
                det = detect_incoming_whatsapp_call()
                self._consecutive_errors = 0
                if self._health != MonitorHealth.RUNNING:
                    self._health = MonitorHealth.RUNNING

                is_incoming = det.get("incoming", False)
                caller = det.get("caller") or "Unknown"
                call_type = det.get("call_type") or "audio"

                if is_incoming:
                    if not self._current_call:
                        self._current_call = {
                            "caller": caller,
                            "call_type": call_type,
                            "detected_at": time.time(),
                            "state": "RINGING",
                        }
                        print(f"[CallMonitor] 📞 Incoming WhatsApp call ringing from '{caller}' ({call_type}).")
                else:
                    if self._current_call:
                        # Call was ringing and now ceased
                        c_info = self._current_call
                        self._current_call = None
                        ring_duration = time.time() - c_info.get("detected_at", time.time())

                        # Conservative multi-signal outcome evaluation
                        outcome_state, outcome_reason, outcome_evidence = evaluate_call_outcome(
                            caller=c_info["caller"],
                            call_type=c_info["call_type"],
                            ring_duration=ring_duration,
                        )

                        if outcome_state == "ANSWERED":
                            print(f"[CallMonitor] ✅ Call with '{c_info['caller']}' connected (ANSWERED).")
                        elif outcome_state == "DECLINED":
                            print(f"[CallMonitor] 🛑 Call from '{c_info['caller']}' was explicitly DECLINED by user.")
                        elif outcome_state == "MISSED":
                            print(f"[CallMonitor] ⚠️ Call from '{c_info['caller']}' verified as MISSED ({ring_duration:.1f}s). Triggering busy workflow...")
                            process_missed_call_lifecycle(
                                caller=c_info["caller"],
                                call_type=c_info["call_type"],
                                call_state="MISSED",
                                notes=outcome_reason,
                            )
                        else:
                            # Inconclusive, short call, manual decline, or caller cancellation
                            print(f"[CallMonitor] ❓ Call from '{c_info['caller']}' outcome is UNKNOWN: {outcome_reason}")
                            process_missed_call_lifecycle(
                                caller=c_info["caller"],
                                call_type=c_info["call_type"],
                                call_state="UNKNOWN",
                                notes=outcome_reason,
                            )

            except Exception as e:
                self._consecutive_errors += 1
                if self._consecutive_errors >= 5:
                    self._health = MonitorHealth.ERROR
                # Exponential backoff on transient errors
                backoff_factor = min(1.5 ** self._consecutive_errors, 6.0)
                current_sleep = min(self.poll_interval * backoff_factor, 15.0)

            time.sleep(current_sleep)


# Global singleton monitor instance with clean atexit registration
call_monitor = WhatsAppCallMonitor()
try:
    atexit.register(call_monitor.stop)
except Exception:
    pass
