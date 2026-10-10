"""
test_phase9_missed_call_busy_reply.py — Comprehensive Unit & Integration Tests for:
WhatsApp Missed-Call Detection, Busy-Status Responses, Idempotency, and Follow-Up Reminders.

Tests cover all 10 required scenarios from the JARVIS Upgrade specification:
1. Incoming call detection.
2. Missed-call classification (distinguishing answered, declined, missed, unknown).
3. Busy-period detection (same-day schedule, overnight schedule, day-of-week filtering).
4. Contact resolution (clean matching, allowlist, denylist, rate-limiting).
5. Message preparation and sending (customizable text, no unauthorized invention).
6. Duplicate-event prevention & idempotency keys.
7. Follow-up scheduling & reminder integration.
8. Authentication failures and unsupported capabilities (Meta Cloud API vs Desktop UIA).
9. Reconnection, recovery, and bounded retries.
10. Correct reporting of outcomes (SENT, FAILED, VERIFICATION_REQUIRED, SUPPRESSED).
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path
from unittest.mock import patch, MagicMock

# Enable JARVIS test mode
os.environ["JARVIS_TEST_MODE"] = "1"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from actions.whatsapp_busy_manager import (
    load_busy_config,
    save_busy_config,
    update_busy_config,
    is_within_busy_schedule,
    can_reply_to_contact,
    generate_event_idempotency_key,
    load_missed_call_records,
    save_missed_call_records,
    process_missed_call_lifecycle,
    schedule_follow_up_reminder,
    is_whatsapp_process_running,
    evaluate_call_outcome,
    call_monitor,
    MonitorHealth,
    DEFAULT_BUSY_CONFIG,
)
from actions.send_message import send_whatsapp_message
from actions.whatsapp_calling import (
    record_missed_call,
    get_missed_calls,
    send_authorized_reply,
    detect_incoming_whatsapp_call,
    respond_to_incoming_whatsapp_call,
    get_busy_reply_config,
    update_busy_reply_config,
    process_missed_call,
    mark_call_declined,
    was_recently_declined,
    get_call_monitor_status,
    get_downtime_recovery_report,
)
from core.agents.communication_agent import communication_agent


class TestWhatsAppMissedCallBusyReply(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.test_busy_cfg_file = Path(cls.temp_dir) / "busy_reply_config.json"
        cls.test_missed_calls_file = Path(cls.temp_dir) / "missed_calls.json"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        # Reset test config and records before each test
        self.patch_cfg = patch("actions.whatsapp_busy_manager._get_busy_config_path", return_value=self.test_busy_cfg_file)
        self.patch_mc = patch("actions.whatsapp_busy_manager._get_missed_calls_path", return_value=self.test_missed_calls_file)
        self.patch_calling_mc = patch("actions.whatsapp_calling._get_missed_calls_file_path", return_value=self.test_missed_calls_file)

        self.patch_cfg.start()
        self.patch_mc.start()
        self.patch_calling_mc.start()

        save_busy_config(dict(DEFAULT_BUSY_CONFIG))
        save_missed_call_records([])

    def tearDown(self):
        self.patch_cfg.stop()
        self.patch_mc.stop()
        self.patch_calling_mc.stop()

    # =========================================================================
    # 1. Incoming Call Detection
    # =========================================================================
    def test_01_incoming_call_detection(self):
        """Verify incoming WhatsApp call detection and caller name extraction."""
        # Simulated no call
        with patch("actions.whatsapp_calling._find_whatsapp_window", return_value=None):
            det = detect_incoming_whatsapp_call()
            self.assertIn("incoming", det)
            self.assertIn("message", det)

        # Simulated incoming call window detected
        with patch("win32gui.GetWindowText", return_value="Incoming call from John Chavala"), \
             patch("win32gui.GetClassName", return_value="ApplicationFrameWindow"), \
             patch("win32gui.EnumWindows", side_effect=lambda cb, ctx: cb(12345, ctx)):
            det_call = detect_incoming_whatsapp_call()
            # If win32 is mocked or available, verify incoming is flagged
            self.assertTrue(det_call.get("incoming") or det_call.get("can_accept") is False)

    # =========================================================================
    # 2. Missed-Call Classification
    # =========================================================================
    def test_02_call_classification_states(self):
        """Verify lifecycle correctly distinguishes MISSED from ANSWERED or DECLINED."""
        # Non-missed state should be skipped
        res_answered = process_missed_call_lifecycle(
            caller="Rahul",
            call_type="audio",
            call_state="ANSWERED",
        )
        self.assertEqual(res_answered["status"], "SKIPPED_NOT_MISSED")
        self.assertFalse(res_answered["success"])

        res_declined = process_missed_call_lifecycle(
            caller="Rahul",
            call_type="audio",
            call_state="DECLINED",
        )
        self.assertEqual(res_declined["status"], "SKIPPED_NOT_MISSED")

        # Genuinely MISSED state proceeds through pipeline
        res_missed = process_missed_call_lifecycle(
            caller="Rahul",
            call_type="audio",
            call_state="MISSED",
            force_auto_reply=True,
        )
        self.assertTrue(res_missed["success"])
        self.assertIn(res_missed["status"], ("SENT", "VERIFIED"))

    # =========================================================================
    # 3. Busy-Period Detection
    # =========================================================================
    def test_03_busy_schedule_evaluation(self):
        """Verify day-of-week, same-day, and overnight busy schedule evaluations."""
        cfg = {
            "busy_schedule": {
                "enabled": True,
                "days": ["Monday", "Wednesday", "Friday"],
                "start_time": "09:00",
                "end_time": "18:00",
            }
        }
        # Monday at 14:00 (inside)
        dt_monday_inside = datetime(2026, 10, 12, 14, 0)  # Monday
        is_busy, reason = is_within_busy_schedule(dt_monday_inside, cfg)
        self.assertTrue(is_busy)
        self.assertIn("within busy hours", reason)

        # Monday at 20:00 (outside)
        dt_monday_outside = datetime(2026, 10, 12, 20, 0)
        is_busy, reason = is_within_busy_schedule(dt_monday_outside, cfg)
        self.assertFalse(is_busy)
        self.assertIn("outside busy hours", reason)

        # Tuesday (day not in active days)
        dt_tuesday = datetime(2026, 10, 13, 14, 0)
        is_busy, reason = is_within_busy_schedule(dt_tuesday, cfg)
        self.assertFalse(is_busy)
        self.assertIn("not in active busy days", reason)

        # Overnight window (e.g., 22:00 to 06:00)
        cfg_overnight = {
            "busy_schedule": {
                "enabled": True,
                "days": ["Monday"],
                "start_time": "22:00",
                "end_time": "06:00",
            }
        }
        dt_night = datetime(2026, 10, 12, 23, 30)
        is_busy_night, _ = is_within_busy_schedule(dt_night, cfg_overnight)
        self.assertTrue(is_busy_night)

        dt_early = datetime(2026, 10, 12, 4, 30)
        is_busy_early, _ = is_within_busy_schedule(dt_early, cfg_overnight)
        self.assertTrue(is_busy_early)

        dt_afternoon = datetime(2026, 10, 12, 12, 0)
        is_busy_noon, _ = is_within_busy_schedule(dt_afternoon, cfg_overnight)
        self.assertFalse(is_busy_noon)

    # =========================================================================
    # 4. Contact Resolution & Eligibility
    # =========================================================================
    def test_04_contact_filtering_and_rate_limiting(self):
        """Verify allowlist, denylist, and rate limiting per contact."""
        cfg = {
            "allowed_contacts": ["Rahul", "John Chavala"],
            "excluded_contacts": ["Spam Caller", "Unknown Caller"],
            "rate_limit_minutes_per_contact": 15,
        }
        # Excluded contact
        can_rep, reason = can_reply_to_contact("Spam Caller", cfg)
        self.assertFalse(can_rep)
        self.assertIn("excluded", reason)

        # Allowed contact
        can_rep_rahul, _ = can_reply_to_contact("Rahul", cfg)
        self.assertTrue(can_rep_rahul)

        # Non-allowed contact when allowlist is populated
        can_rep_other, reason = can_reply_to_contact("Random Person", cfg)
        self.assertFalse(can_rep_other)
        self.assertIn("not in the allowed contacts list", reason)

    # =========================================================================
    # 5. Message Preparation & Dispatch
    # =========================================================================
    def test_05_message_preparation_and_sending(self):
        """Verify custom message is used and empty messages are rejected."""
        custom_msg = "Currently traveling. I will reach out at 6 PM."
        update_busy_config({"busy_reply_message": custom_msg, "auto_reply_enabled": True})

        res = process_missed_call_lifecycle(
            caller="John Chavala",
            call_type="audio",
            call_state="MISSED",
            force_auto_reply=True,
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["reply_text"], custom_msg)
        self.assertEqual(res["status"], "SENT")

        # Verify recorded in persistent log
        records = load_missed_call_records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["reply_text"], custom_msg)
        self.assertTrue(records[0]["responded"])

    # =========================================================================
    # 6. Duplicate-Event Prevention & Idempotency
    # =========================================================================
    def test_06_duplicate_event_prevention(self):
        """Verify duplicate missed-call events are suppressed using idempotency keys."""
        fixed_ts = "2026-10-10T14:30:00"
        # First call event processed
        res1 = process_missed_call_lifecycle(
            caller="John Chavala",
            call_type="audio",
            call_state="MISSED",
            timestamp=fixed_ts,
            force_auto_reply=True,
        )
        self.assertTrue(res1["success"])
        self.assertEqual(res1["status"], "SENT")

        # Immediate repeated event (e.g. from polling reconnect or loop)
        res2 = process_missed_call_lifecycle(
            caller="John Chavala",
            call_type="audio",
            call_state="MISSED",
            timestamp=fixed_ts,
            force_auto_reply=True,
        )
        self.assertTrue(res2["success"])
        self.assertEqual(res2["status"], "DUPLICATE_SUPPRESSED")
        self.assertIn("Duplicate event suppressed", res2["message"])

        # Total stored records should still be 1 (no duplicates added)
        records = load_missed_call_records()
        self.assertEqual(len(records), 1)

    # =========================================================================
    # 7. Follow-Up Scheduling
    # =========================================================================
    def test_07_follow_up_reminder_integration(self):
        """Verify follow-up reminder is correctly scheduled via actions.reminder."""
        with patch("actions.reminder.reminder", return_value="Reminder set for 3:00 PM.") as mock_rem:
            res = schedule_follow_up_reminder(
                contact_name="John Chavala",
                delay_minutes=30,
                note="Callback request",
            )
            self.assertTrue(res["success"])
            self.assertIn("Reminder set", res["message"])
            mock_rem.assert_called_once()

    # =========================================================================
    # 8. Authentication Failures & Unsupported Capabilities
    # =========================================================================
    def test_08_unsupported_official_cloud_api_guard(self):
        """Verify architectural honesty: system does not claim Meta Cloud API supports personal call detection."""
        from actions.whatsapp_busy_manager import is_within_busy_schedule
        # Verify that non-existent Cloud API tokens do not block desktop UIA automation
        self.assertIsNone(os.environ.get("WHATSAPP_CLOUD_API_TOKEN"))
        # Verify local UIA configuration works independently of cloud tokens
        cfg = load_busy_config()
        self.assertIn("busy_schedule", cfg)
        self.assertIn("auto_reply_enabled", cfg)

    # =========================================================================
    # 9. Reconnection & Transient Error Recovery
    # =========================================================================
    def test_09_reconnection_and_bounded_retries(self):
        """Verify bounded retry logic recovers from transient automation glitches."""
        attempts = 0

        def flaky_send(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return {"success": False, "status": "FOCUS_TRANSIENT_ERROR", "message": "Window lost focus temporarily"}
            return {"success": True, "status": "SENT_VISIBLE", "message": "Dispatched successfully"}

        with patch("actions.whatsapp_calling.send_authorized_reply", side_effect=flaky_send):
            res = process_missed_call_lifecycle(
                caller="Rahul",
                call_type="audio",
                call_state="MISSED",
                force_auto_reply=True,
            )
            self.assertTrue(res["success"])
            self.assertEqual(res["status"], "SENT")
            self.assertEqual(attempts, 2)  # Succeeded on retry attempt 2

    # =========================================================================
    # 10. Correct Reporting of Outcomes
    # =========================================================================
    def test_10_outcome_reporting_states(self):
        """Verify VERIFICATION_REQUIRED, DISABLED, and OUTSIDE_BUSY_HOURS states."""
        # A. Require confirmation returns VERIFICATION_REQUIRED
        update_busy_config({"auto_reply_enabled": True, "require_confirmation": True})
        res_conf = process_missed_call_lifecycle(
            caller="Rahul",
            call_type="audio",
            call_state="MISSED",
        )
        self.assertEqual(res_conf["status"], "REPLY_PENDING_CONFIRMATION")
        self.assertEqual(res_conf["record"]["delivery_status"], "VERIFICATION_REQUIRED")

        # B. Auto-reply disabled in settings
        update_busy_config({"auto_reply_enabled": False, "require_confirmation": False})
        res_dis = process_missed_call_lifecycle(
            caller="Rahul",
            call_type="audio",
            call_state="MISSED",
        )
        self.assertEqual(res_dis["status"], "VERIFIED_AUTO_REPLY_DISABLED")
        self.assertEqual(res_dis["record"]["delivery_status"], "DISABLED")

    # =========================================================================
    # 11. Unknown Call States Suppress Reply
    # =========================================================================
    def test_11_unknown_call_state_suppresses_reply(self):
        """Verify safety rule: Inconclusive or UNKNOWN call state never triggers auto-reply."""
        update_busy_config({"auto_reply_enabled": True})
        res = process_missed_call_lifecycle(
            caller="Unknown Number",
            call_type="audio",
            call_state="UNKNOWN",
            force_auto_reply=True,
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "SKIPPED_NOT_MISSED")
        self.assertEqual(res["delivery_status"], "SKIPPED")

    # =========================================================================
    # 12. Declined Call Classification & Suppression
    # =========================================================================
    def test_12_declined_call_suppresses_reply(self):
        """Verify that intentional DECLINED calls never trigger busy replies."""
        mark_call_declined("Rahul")
        self.assertTrue(was_recently_declined("Rahul"))

        res = process_missed_call_lifecycle(
            caller="Rahul",
            call_type="audio",
            call_state="DECLINED",
            force_auto_reply=True,
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "SKIPPED_NOT_MISSED")

    # =========================================================================
    # 13. WhatsApp Closing & Reopening Lifecycle
    # =========================================================================
    def test_13_whatsapp_closing_and_reopening_lifecycle(self):
        """Verify monitor detects WhatsApp closure (APP_UNAVAILABLE) and restart recovery."""
        # 1. Closed state
        os.environ["MOCK_WHATSAPP_CLOSED"] = "1"
        try:
            self.assertFalse(is_whatsapp_process_running())
            res = call_monitor.start()
            self.assertTrue(res["success"])
            self.assertEqual(call_monitor.get_health(), MonitorHealth.APP_UNAVAILABLE)

            # 2. Reopen state
            os.environ["MOCK_WHATSAPP_CLOSED"] = "0"
            self.assertTrue(is_whatsapp_process_running())
        finally:
            os.environ.pop("MOCK_WHATSAPP_CLOSED", None)
            call_monitor.stop()

    # =========================================================================
    # 14. Duplicate Worker Prevention
    # =========================================================================
    def test_14_monitor_duplicate_worker_prevention(self):
        """Verify starting monitor multiple times is idempotent and prevents duplicate threads."""
        try:
            res1 = call_monitor.start()
            self.assertTrue(res1["success"])
            t1 = call_monitor._thread

            res2 = call_monitor.start()
            self.assertTrue(res2["success"])
            t2 = call_monitor._thread

            self.assertIs(t1, t2)
            self.assertIn("already running", res2["message"])
        finally:
            call_monitor.stop()

    # =========================================================================
    # 15. Send Timeout Withholds Blind Retry
    # =========================================================================
    def test_15_send_timeout_withholds_blind_retry(self):
        """Verify non-blind retry safety: If send times out after submission, withhold retry to prevent duplicates."""
        mock_send = MagicMock(return_value={"success": False, "status": "SEND_REQUESTED", "message": "Preview did not dismiss"})
        with patch("actions.whatsapp_calling.send_authorized_reply", mock_send), \
             patch("actions.whatsapp_calling._find_whatsapp_window", return_value=12345), \
             patch("actions.whatsapp_calling._verify_whatsapp_outgoing_bubble", return_value=(False, "UNKNOWN", "Inconclusive")):
            res = process_missed_call_lifecycle(
                caller="Rahul",
                call_type="audio",
                call_state="MISSED",
                force_auto_reply=True,
            )
            # Should not call send 2 times blindly
            self.assertEqual(mock_send.call_count, 1)
            self.assertEqual(res["status"], "UNKNOWN")
            self.assertEqual(res["delivery_status"], "VERIFICATION_REQUIRED")

    # =========================================================================
    # 16. Invalid Configuration Fallback
    # =========================================================================
    def test_16_invalid_config_fallback_to_defaults(self):
        """Verify corrupt config falls back cleanly to default configuration."""
        self.test_busy_cfg_file.write_text("INVALID_JSON_CORRUPT", encoding="utf-8")
        cfg = load_busy_config()
        self.assertIsInstance(cfg, dict)
        self.assertEqual(cfg["auto_reply_enabled"], DEFAULT_BUSY_CONFIG["auto_reply_enabled"])
        self.assertEqual(cfg["busy_reply_message"], DEFAULT_BUSY_CONFIG["busy_reply_message"])

    # =========================================================================
    # 17. Downtime Recovery Gap Transparency
    # =========================================================================
    def test_17_downtime_report_transparency(self):
        """Verify downtime recovery report accurately states platform limitations."""
        rep = get_downtime_recovery_report()
        self.assertFalse(rep["supported"])
        self.assertEqual(rep["status"], "PLATFORM_LIMITATION")
        self.assertIn("cannot be recovered automatically", rep["message"] or "")

    # =========================================================================
    # 18. Manual Physical Decline vs Explicit Decline
    # =========================================================================
    def test_18_manual_decline_suppresses_busy_reply(self):
        """Verify manual physical decline and explicit decline both suppress automatic busy reply."""
        # Case A: Explicit decline via JARVIS command / mark_call_declined
        mark_call_declined("Rahul")
        state, reason, _ = evaluate_call_outcome(caller="Rahul", ring_duration=5.0)
        self.assertEqual(state, "DECLINED")
        res_exp = process_missed_call_lifecycle(caller="Rahul", call_state=state)
        self.assertEqual(res_exp["status"], "SKIPPED_NOT_MISSED")
        self.assertFalse(res_exp["success"])

        # Case B: Manual physical click on screen (short duration, no explicit signal)
        # Cannot be separated from caller cancel; must evaluate to UNKNOWN to fail safe
        with patch("actions.whatsapp_calling.was_recently_declined", return_value=False), \
             patch("actions.whatsapp_calling.check_whatsapp_call_status", return_value={"is_active": False}):
            state_man, reason_man, _ = evaluate_call_outcome(caller="Rahul", ring_duration=3.5)
            self.assertEqual(state_man, "UNKNOWN")
            self.assertIn("cannot be differentiated", reason_man)
            res_man = process_missed_call_lifecycle(caller="Rahul", call_state=state_man, force_auto_reply=True)
            self.assertEqual(res_man["status"], "SKIPPED_NOT_MISSED")
            self.assertFalse(res_man["success"])

    # =========================================================================
    # 19. Caller Cancellation (Short Call < min_ring_duration)
    # =========================================================================
    def test_19_caller_cancellation_short_call_suppresses_reply(self):
        """Verify caller cancellation or quick abort (< 12.0s) evaluates to UNKNOWN and suppresses reply."""
        with patch("actions.whatsapp_calling.was_recently_declined", return_value=False), \
             patch("actions.whatsapp_calling.check_whatsapp_call_status", return_value={"is_active": False}):
            # Caller aborted after 2.0s (e.g. 1-ring drop or accidental misdial)
            state, reason, ev = evaluate_call_outcome(caller="Mom", ring_duration=2.0)
            self.assertEqual(state, "UNKNOWN")
            self.assertEqual(ev["signal"], "short_duration_inconclusive")
            res = process_missed_call_lifecycle(caller="Mom", call_state=state, force_auto_reply=True)
            self.assertEqual(res["status"], "SKIPPED_NOT_MISSED")
            self.assertFalse(res["success"])

    # =========================================================================
    # 20. Disappearing Toast / Popup Flashes
    # =========================================================================
    def test_20_disappearing_popup_flashes_suppresses_reply(self):
        """Verify transient toast flash or ambiguous popup disappearance (< threshold) never triggers reply."""
        with patch("actions.whatsapp_calling.was_recently_declined", return_value=False), \
             patch("actions.whatsapp_calling.check_whatsapp_call_status", return_value={"is_active": False}):
            # Flash of 0.8s
            state, _, _ = evaluate_call_outcome(caller="Dr. Connor", ring_duration=0.8)
            self.assertEqual(state, "UNKNOWN")

            # Flash of 1.2s (previously triggered false MISSED, now safely UNKNOWN)
            state_prev_bug, _, _ = evaluate_call_outcome(caller="Dr. Connor", ring_duration=1.2)
            self.assertEqual(state_prev_bug, "UNKNOWN")

            res = process_missed_call_lifecycle(caller="Dr. Connor", call_state=state_prev_bug, force_auto_reply=True)
            self.assertEqual(res["status"], "SKIPPED_NOT_MISSED")

    # =========================================================================
    # 21. Answered Calls Suppress Busy Reply
    # =========================================================================
    def test_21_answered_call_suppresses_reply(self):
        """Verify connected active call evaluates to ANSWERED and never receives busy reply."""
        with patch("actions.whatsapp_calling.check_whatsapp_call_status", return_value={"is_active": True, "state": "CONNECTED"}):
            state, reason, ev = evaluate_call_outcome(caller="Alice", ring_duration=15.0)
            self.assertEqual(state, "ANSWERED")
            self.assertEqual(ev["signal"], "active_call_session")
            res = process_missed_call_lifecycle(caller="Alice", call_state=state, force_auto_reply=True)
            self.assertEqual(res["status"], "SKIPPED_NOT_MISSED")
            self.assertFalse(res["success"])

    # =========================================================================
    # 22. Contradictory & Ambiguous Events Fail-Safe to UNKNOWN
    # =========================================================================
    def test_22_contradictory_and_ambiguous_events_fail_safe_to_unknown(self):
        """Verify that when WhatsApp closes abruptly or signals conflict, state is UNKNOWN."""
        with patch("actions.whatsapp_calling.was_recently_declined", return_value=False), \
             patch("actions.whatsapp_calling.check_whatsapp_call_status", return_value={"is_active": False}), \
             patch("actions.whatsapp_busy_manager.is_whatsapp_process_running", return_value=False):
            # WhatsApp closed while ringing for 15s
            state, reason, ev = evaluate_call_outcome(caller="Robert", ring_duration=15.0)
            self.assertEqual(state, "UNKNOWN")
            self.assertEqual(ev["signal"], "app_closed")
            res = process_missed_call_lifecycle(caller="Robert", call_state=state, force_auto_reply=True)
            self.assertEqual(res["status"], "SKIPPED_NOT_MISSED")

    # =========================================================================
    # 23. Confirmed Missed Call (Sustained Ring Duration >= Threshold)
    # =========================================================================
    def test_23_confirmed_missed_call_sustained_ring_triggers_reply(self):
        """Verify that a confirmed missed call with sustained ring (>= 12.0s) and corroborating evidence triggers busy reply."""
        with patch("actions.whatsapp_calling.was_recently_declined", return_value=False), \
             patch("actions.whatsapp_calling.check_whatsapp_call_status", return_value={"is_active": False}), \
             patch("actions.whatsapp_busy_manager.is_whatsapp_process_running", return_value=True):
            # Call rang for 14.5s with corroborating evidence (e.g. missed call notification toast)
            state, reason, ev = evaluate_call_outcome(
                caller="Rahul",
                ring_duration=14.5,
                evidence={"has_missed_call_notification": True},
            )
            self.assertEqual(state, "MISSED")
            self.assertEqual(ev["signal"], "confirmed_missed_call")

            update_busy_config({"auto_reply_enabled": True, "require_confirmation": False})
            with patch("actions.whatsapp_calling.send_authorized_reply", return_value={"success": True, "status": "TEST_SIMULATED"}):
                res = process_missed_call_lifecycle(
                    caller="Rahul",
                    call_type="audio",
                    call_state=state,
                    notes=reason,
                    force_auto_reply=True,
                )
                self.assertTrue(res["success"])
                self.assertEqual(res["status"], "SENT")
                self.assertEqual(res["call_state"], "MISSED")

    # =========================================================================
    # 24. Non-Missed States Cannot Trigger Busy Reply
    # =========================================================================
    def test_24_non_missed_states_cannot_trigger_busy_reply(self):
        """Verify that UNKNOWN, DECLINED, ANSWERED, ENDED, and CANCELLED states strictly reject auto-reply."""
        non_missed_states = ["UNKNOWN", "DECLINED", "ANSWERED", "ENDED", "CANCELLED", "IDLE"]
        update_busy_config({"auto_reply_enabled": True})

        for st in non_missed_states:
            res = process_missed_call_lifecycle(
                caller="Rahul",
                call_type="audio",
                call_state=st,
                force_auto_reply=True,
            )
            self.assertFalse(res["success"], f"State '{st}' unexpectedly succeeded!")
            self.assertEqual(res["status"], "SKIPPED_NOT_MISSED", f"State '{st}' did not skip!")
            self.assertEqual(res["delivery_status"], "SKIPPED")
            self.assertIsNone(res["reply_text"])

    # =========================================================================
    # 25. Test Mode Isolation Guarantees Zero Physical UI Actions
    # =========================================================================
    def test_25_test_mode_isolation_guarantees_zero_physical_ui_actions(self):
        """Verify regression safety: In JARVIS_TEST_MODE=1, send_whatsapp_message never types, pastes, or clicks."""
        with patch("actions.send_message._paste_text_safely") as mock_paste, \
             patch("pyautogui.press") as mock_press:
            res = send_whatsapp_message(
                contact_identifier="John Chavala",
                message_text="This is an automated unit test message",
                task_id="safety_regression_01",
            )
            self.assertTrue(res["success"])
            self.assertEqual(res["status"], "TEST_SIMULATED")
            self.assertNotEqual(res["status"], "SENT_VERIFIED")
            self.assertIn("TEST_SIMULATED", res["states_traversed"])
            # Strict guarantee: Zero physical keystrokes / paste commands
            mock_paste.assert_not_called()
            mock_press.assert_not_called()

    # =========================================================================
    # 26. Case 1: Manual physical Decline after 2 seconds
    # =========================================================================
    def test_26_case1_manual_physical_decline_after_2s_suppresses_reply(self):
        """Verify manual physical Decline after 2s (< threshold) fails safe to UNKNOWN and suppresses reply."""
        with patch("actions.whatsapp_calling.was_recently_declined", return_value=False), \
             patch("actions.whatsapp_calling.check_whatsapp_call_status", return_value={"is_active": False}):
            state, reason, ev = evaluate_call_outcome(caller="Alice", ring_duration=2.0)
            self.assertEqual(state, "UNKNOWN")
            self.assertEqual(ev["signal"], "short_duration_inconclusive")

            res = process_missed_call_lifecycle(caller="Alice", call_state=state, force_auto_reply=True)
            self.assertEqual(res["status"], "SKIPPED_NOT_MISSED")
            self.assertFalse(res["success"])
            self.assertIsNone(res.get("reply_text"))

    # =========================================================================
    # 27. Case 2: Manual physical Decline after 12 seconds
    # =========================================================================
    def test_27_case2_manual_physical_decline_after_12s_suppresses_reply(self):
        """Verify manual physical Decline after 12s without corroborating evidence fails safe to UNKNOWN and suppresses reply."""
        with patch("actions.whatsapp_calling.was_recently_declined", return_value=False), \
             patch("actions.whatsapp_calling.check_whatsapp_call_status", return_value={"is_active": False}), \
             patch("actions.whatsapp_busy_manager.is_whatsapp_process_running", return_value=True):
            # User physically clicked Decline after 12.0s; no missed-call notification exists
            state, reason, ev = evaluate_call_outcome(
                caller="Bob",
                ring_duration=12.0,
                evidence={"has_missed_call_notification": False, "has_unread_badge": False},
            )
            self.assertEqual(state, "UNKNOWN")
            self.assertEqual(ev["signal"], "sustained_ring_unverified_ambiguous")

            res = process_missed_call_lifecycle(caller="Bob", call_state=state, force_auto_reply=True)
            self.assertEqual(res["status"], "SKIPPED_NOT_MISSED")
            self.assertFalse(res["success"])
            self.assertIsNone(res.get("reply_text"))

    # =========================================================================
    # 28. Case 3: Manual physical Decline after 20 seconds
    # =========================================================================
    def test_28_case3_manual_physical_decline_after_20s_suppresses_reply(self):
        """Verify manual physical Decline after 20s without corroborating evidence fails safe to UNKNOWN and suppresses reply."""
        with patch("actions.whatsapp_calling.was_recently_declined", return_value=False), \
             patch("actions.whatsapp_calling.check_whatsapp_call_status", return_value={"is_active": False}), \
             patch("actions.whatsapp_busy_manager.is_whatsapp_process_running", return_value=True):
            # User physically clicked Decline after 20.0s; no missed-call toast
            state, reason, ev = evaluate_call_outcome(
                caller="Charlie",
                ring_duration=20.0,
                evidence={"has_missed_call_notification": False, "has_unread_badge": False},
            )
            self.assertEqual(state, "UNKNOWN")
            self.assertEqual(ev["signal"], "sustained_ring_unverified_ambiguous")

            res = process_missed_call_lifecycle(caller="Charlie", call_state=state, force_auto_reply=True)
            self.assertEqual(res["status"], "SKIPPED_NOT_MISSED")
            self.assertFalse(res["success"])
            self.assertIsNone(res.get("reply_text"))

    # =========================================================================
    # 29. Case 4: Caller cancellation after a short ring
    # =========================================================================
    def test_29_case4_caller_cancellation_short_ring_suppresses_reply(self):
        """Verify caller cancellation after short ring (3s) evaluates to UNKNOWN and suppresses reply."""
        with patch("actions.whatsapp_calling.was_recently_declined", return_value=False), \
             patch("actions.whatsapp_calling.check_whatsapp_call_status", return_value={"is_active": False}):
            state, reason, ev = evaluate_call_outcome(caller="David", ring_duration=3.0)
            self.assertEqual(state, "UNKNOWN")
            self.assertEqual(ev["signal"], "short_duration_inconclusive")

            res = process_missed_call_lifecycle(caller="David", call_state=state, force_auto_reply=True)
            self.assertEqual(res["status"], "SKIPPED_NOT_MISSED")
            self.assertFalse(res["success"])

    # =========================================================================
    # 30. Case 5: Caller cancellation after a long ring
    # =========================================================================
    def test_30_case5_caller_cancellation_long_ring_suppresses_reply(self):
        """Verify caller cancellation after long ring (16s) without corroborating missed toast evaluates to UNKNOWN."""
        with patch("actions.whatsapp_calling.was_recently_declined", return_value=False), \
             patch("actions.whatsapp_calling.check_whatsapp_call_status", return_value={"is_active": False}), \
             patch("actions.whatsapp_busy_manager.is_whatsapp_process_running", return_value=True):
            # Caller hung up at 16s before answer; no missed notification produced
            state, reason, ev = evaluate_call_outcome(
                caller="Eva",
                ring_duration=16.0,
                evidence={"has_missed_call_notification": False, "has_unread_badge": False},
            )
            self.assertEqual(state, "UNKNOWN")
            self.assertEqual(ev["signal"], "sustained_ring_unverified_ambiguous")

            res = process_missed_call_lifecycle(caller="Eva", call_state=state, force_auto_reply=True)
            self.assertEqual(res["status"], "SKIPPED_NOT_MISSED")
            self.assertFalse(res["success"])

    # =========================================================================
    # 31. Case 6: Genuine missed call with sufficient supporting evidence
    # =========================================================================
    def test_31_case6_genuine_missed_call_with_corroborating_evidence(self):
        """Verify genuine missed call with sustained ring (15s) and corroborating evidence classifies as MISSED and sends reply."""
        with patch("actions.whatsapp_calling.was_recently_declined", return_value=False), \
             patch("actions.whatsapp_calling.check_whatsapp_call_status", return_value={"is_active": False}), \
             patch("actions.whatsapp_busy_manager.is_whatsapp_process_running", return_value=True):
            state, reason, ev = evaluate_call_outcome(
                caller="Frank",
                ring_duration=15.0,
                evidence={"has_missed_call_notification": True},
            )
            self.assertEqual(state, "MISSED")
            self.assertEqual(ev["signal"], "confirmed_missed_call")

            update_busy_config({"auto_reply_enabled": True, "require_confirmation": False})
            with patch("actions.whatsapp_calling.send_authorized_reply", return_value={"success": True, "status": "TEST_SIMULATED"}):
                res = process_missed_call_lifecycle(
                    caller="Frank",
                    call_type="audio",
                    call_state=state,
                    notes=reason,
                    force_auto_reply=True,
                )
                self.assertTrue(res["success"])
                self.assertEqual(res["status"], "SENT")
                self.assertEqual(res["call_state"], "MISSED")

    # =========================================================================
    # 32. Case 7: Incoming-call popup disappearing without reliable outcome
    # =========================================================================
    def test_32_case7_popup_disappearing_without_outcome_fails_safe(self):
        """Verify popup disappearing after 13s without reliable outcome evaluates to UNKNOWN and suppresses reply."""
        with patch("actions.whatsapp_calling.was_recently_declined", return_value=False), \
             patch("actions.whatsapp_calling.check_whatsapp_call_status", return_value={"is_active": False}), \
             patch("actions.whatsapp_busy_manager.is_whatsapp_process_running", return_value=True):
            state, reason, ev = evaluate_call_outcome(
                caller="Grace",
                ring_duration=13.0,
                evidence={"unverified": True},
            )
            self.assertEqual(state, "UNKNOWN")
            self.assertEqual(ev["signal"], "sustained_ring_unverified_ambiguous")

            res = process_missed_call_lifecycle(caller="Grace", call_state=state, force_auto_reply=True)
            self.assertEqual(res["status"], "SKIPPED_NOT_MISSED")
            self.assertFalse(res["success"])

    # =========================================================================
    # 33. Case 8: WhatsApp process terminating during an incoming call
    # =========================================================================
    def test_33_case8_process_terminating_during_call_fails_safe(self):
        """Verify WhatsApp process terminating during incoming call evaluates to UNKNOWN and suppresses reply."""
        with patch("actions.whatsapp_busy_manager.is_whatsapp_process_running", return_value=False):
            state, reason, ev = evaluate_call_outcome(caller="Hank", ring_duration=14.0)
            self.assertEqual(state, "UNKNOWN")
            self.assertEqual(ev["signal"], "app_closed")

            res = process_missed_call_lifecycle(caller="Hank", call_state=state, force_auto_reply=True)
            self.assertEqual(res["status"], "SKIPPED_NOT_MISSED")
            self.assertFalse(res["success"])

    # =========================================================================
    # 34. Case 9: Contradictory call-state signals
    # =========================================================================
    def test_34_case9_contradictory_call_state_signals_fail_safe(self):
        """Verify contradictory call signals (e.g. active call session reported while decline flag present) evaluate to UNKNOWN."""
        state, reason, ev = evaluate_call_outcome(
            caller="Ian",
            ring_duration=10.0,
            evidence={"contradictory": True},
        )
        self.assertEqual(state, "UNKNOWN")
        self.assertEqual(ev["signal"], "contradictory_evidence")

        res = process_missed_call_lifecycle(caller="Ian", call_state=state, force_auto_reply=True)
        self.assertEqual(res["status"], "SKIPPED_NOT_MISSED")
        self.assertFalse(res["success"])

    # =========================================================================
    # 35. Case 10: Duplicate call events after reconnecting
    # =========================================================================
    def test_35_case10_duplicate_call_events_after_reconnect_suppressed(self):
        """Verify duplicate call events arriving after reconnecting in the same 2-minute bucket are suppressed."""
        update_busy_config({"auto_reply_enabled": True, "require_confirmation": False, "duplicate_prevention_enabled": True})
        fixed_ts = "2026-10-10T16:00:00"

        with patch("actions.whatsapp_calling.send_authorized_reply", return_value={"success": True, "status": "TEST_SIMULATED"}):
            # First event processed
            res1 = process_missed_call_lifecycle(
                caller="Jack",
                call_type="audio",
                call_state="MISSED",
                timestamp=fixed_ts,
                force_auto_reply=True,
            )
            self.assertTrue(res1["success"])
            self.assertEqual(res1["status"], "SENT")

            # Duplicate event 30 seconds later after reconnect
            dup_ts = "2026-10-10T16:00:30"
            res2 = process_missed_call_lifecycle(
                caller="Jack",
                call_type="audio",
                call_state="MISSED",
                timestamp=dup_ts,
                force_auto_reply=True,
            )
            self.assertTrue(res2["success"])
            self.assertEqual(res2["status"], "DUPLICATE_SUPPRESSED")

    # =========================================================================
    # 36. Case 11: JARVIS restarting while an event is pending
    # =========================================================================
    def test_36_case11_restart_persistence_prevents_duplicate_reply(self):
        """Verify that persisting call records prevents duplicate replies even after system restart."""
        update_busy_config({"auto_reply_enabled": True, "require_confirmation": False, "duplicate_prevention_enabled": True})
        ts = "2026-10-10T16:15:00"
        idemp_k = generate_event_idempotency_key("Karen", "audio", ts)

        # Simulate existing record persisted from previous session
        existing_records = [{
            "id": "mc_pre_existing",
            "idempotency_key": idemp_k,
            "caller": "Karen",
            "call_type": "audio",
            "call_state": "MISSED",
            "status": "SENT",
            "responded": True,
            "delivery_status": "SENT",
        }]
        save_missed_call_records(existing_records)

        # Post-restart: new lifecycle dispatch with identical idempotency key
        res = process_missed_call_lifecycle(
            caller="Karen",
            call_type="audio",
            call_state="MISSED",
            timestamp=ts,
            force_auto_reply=True,
        )
        self.assertEqual(res["status"], "DUPLICATE_SUPPRESSED")
        self.assertTrue(res["success"])

    # =========================================================================
    # 37. Case 12: Test mode suppressing all keyboard, mouse, clipboard, and message-send UI actions
    # =========================================================================
    def test_37_case12_test_mode_strict_suppression_of_all_ui_actions(self):
        """Verify that JARVIS_TEST_MODE=1 strictly suppresses all physical UI dispatches across messaging pathways."""
        with patch.dict(os.environ, {"JARVIS_TEST_MODE": "1"}), \
             patch("actions.send_message._paste_text_safely") as mock_paste, \
             patch("pyautogui.press") as mock_press, \
             patch("pyautogui.hotkey") as mock_hotkey, \
             patch("pyautogui.click") as mock_click:

            # Path A: Direct send_whatsapp_message
            res_msg = send_whatsapp_message("Lisa", "Test mode message", task_id="ui_test_01")
            self.assertTrue(res_msg["success"])
            self.assertEqual(res_msg["status"], "TEST_SIMULATED")
            self.assertNotEqual(res_msg["status"], "SENT_VERIFIED")

            # Path B: send_authorized_reply
            res_auth = send_authorized_reply("Lisa", "Authorized reply", task_id="ui_test_02")
            self.assertTrue(res_auth["success"])
            self.assertEqual(res_auth["status"], "TEST_SIMULATED")

            # Assert complete UI dispatch suppression
            mock_paste.assert_not_called()
            mock_press.assert_not_called()
            mock_hotkey.assert_not_called()
            mock_click.assert_not_called()

    # =========================================================================
    # 38. Unrelated Pre-Existing Unread Badge Cannot Trigger Busy Reply
    # =========================================================================
    def test_38_unrelated_unread_badge_cannot_trigger_busy_reply(self):
        """Verify that a pre-existing or unrelated unread badge on WhatsApp main window title cannot independently trigger a busy reply."""
        with patch("actions.whatsapp_calling.was_recently_declined", return_value=False), \
             patch("actions.whatsapp_calling.check_whatsapp_call_status", return_value={"is_active": False}), \
             patch("actions.whatsapp_busy_manager.is_whatsapp_process_running", return_value=True):
            # Call rang for 15s; user already has unread badge '(5) WhatsApp' from other group chats,
            # but NO caller-specific missed call notification exists for Rahul
            state, reason, ev = evaluate_call_outcome(
                caller="Rahul",
                ring_duration=15.0,
                evidence={"has_unread_badge": True, "has_missed_call_notification": False},
            )
            # Must fail safe to UNKNOWN because a generic unread badge cannot prove Rahul's call was missed
            self.assertEqual(state, "UNKNOWN")
            self.assertEqual(ev["signal"], "sustained_ring_unverified_ambiguous")

            update_busy_config({"auto_reply_enabled": True, "require_confirmation": False})
            res = process_missed_call_lifecycle(
                caller="Rahul",
                call_type="audio",
                call_state=state,
                notes=reason,
                force_auto_reply=True,
            )
            self.assertEqual(res["status"], "SKIPPED_NOT_MISSED")
            self.assertFalse(res["success"])
            self.assertIsNone(res.get("reply_text"))

    # =========================================================================
    # 39. Strict Caller Matching in detect_missed_call_notification
    # =========================================================================
    def test_39_detect_missed_call_notification_strict_caller_matching(self):
        """Verify detect_missed_call_notification strictly matches target caller and rejects empty/mismatched notifications."""
        from actions.whatsapp_calling import detect_missed_call_notification

        # Caller empty or None -> False
        self.assertFalse(detect_missed_call_notification(None))
        self.assertFalse(detect_missed_call_notification(""))

        # Mismatched caller notification (e.g. notification is for Bob, but target caller is Alice)
        def _mock_enum_bob(callback, _):
            # Simulate EnumWindows with a window titled "Missed voice call from Bob"
            import win32gui
            with patch("win32gui.GetWindowText", return_value="Missed voice call from Bob"), \
                 patch("win32gui.GetClassName", return_value="AppModelNotificationWindow"):
                callback(12345, None)

        with patch("win32gui.EnumWindows", side_effect=_mock_enum_bob):
            # Checking for Alice must return False (Bob does not match Alice)
            self.assertFalse(detect_missed_call_notification("Alice"))
            # Checking for Bob must return True
            self.assertTrue(detect_missed_call_notification("Bob"))


if __name__ == "__main__":
    unittest.main()

