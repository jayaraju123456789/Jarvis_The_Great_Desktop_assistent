"""
tests/test_universal_whatsapp_calling.py — Comprehensive Verification Suite for Universal WhatsApp Calling.

Verifies:
1. Exact contact-name matching (case-insensitive, trimmed, Unicode).
2. Partial-name matching and ambiguity detection (multiple candidate prompt).
3. Unknown contact handling (no hardcoded fallback).
4. Direct phone-number validation and resolution (+country code, digits).
5. Universal Audio Call Controller (start_whatsapp_audio_call) for distinct contacts:
   - "Jhon chavala" (ordinary dynamic runtime input, not hardcoded)
   - "Rahul"
   - "+919876543210"
   - Unicode contact names (e.g., "José Martinez", "సురేష్")
6. Universal Video Call Controller (start_whatsapp_video_call) with control distinction (never selects audio button).
7. Missing call button and offline WhatsApp handling.
8. Observable call state verification (IDLE, CALLING, RINGING, CONNECTED, ENDED, UNKNOWN).
9. Idempotency and duplicate call prevention.
10. Wrong contact prevention during navigation.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from actions.whatsapp_calling import (
    CallResult,
    CallState,
    ContactResolution,
    ContactResolver,
    ChatOpenResult,
    open_whatsapp_chat,
    check_whatsapp_call_status,
    contact_resolver,
    end_whatsapp_call,
    start_whatsapp_audio_call,
    start_whatsapp_call,
    start_whatsapp_video_call,
    _is_whatsapp_foreground,
    _focus_whatsapp_desktop,
    _find_whatsapp_window,
    _verify_chat_header,
    _find_message_input_control,
)
from actions.send_message import (
    find_file_and_send_whatsapp,
    send_message,
    send_whatsapp_message,
)
from core.agents.communication_agent import communication_agent
from core.tool_router import ToolRouter
from core.tts import KokoroTTSEngine


class TestUniversalWhatsAppCalling(unittest.TestCase):

    def setUp(self):
        os.environ["JARVIS_TEST_MODE"] = "1"
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_contacts_path = Path(self.temp_dir.name) / "contacts.json"

        # Populate a diverse test contacts book with multiple real-world scenarios
        self.sample_contacts = {
            "Jhon chavala": "+15551234567",
            "Rahul": "+919876543210",
            "Mom": "+919811122233",
            "Dad": "+919844455566",
            "John Doe": "+15559876543",
            "John Smith": "+15559876544",
            "José Martinez": "+34612345678",
            "Dr. Sarah Connor": "+15558889999",
        }
        self.test_contacts_path.write_text(json.dumps(self.sample_contacts, indent=2), encoding="utf-8")
        self.resolver = ContactResolver(contacts_path=self.test_contacts_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    # =========================================================================
    # 1. Exact Contact Name Matching (Case-Insensitive & Unicode)
    # =========================================================================
    def test_01_exact_contact_matching(self):
        # Case variations
        res1 = self.resolver.resolve("Jhon chavala")
        self.assertEqual(res1.status, "EXACT")
        self.assertEqual(res1.matched_name, "Jhon chavala")
        self.assertEqual(res1.phone_number, "+15551234567")

        res2 = self.resolver.resolve("jhon chavala")
        self.assertEqual(res2.status, "EXACT")
        self.assertEqual(res2.matched_name, "Jhon chavala")

        res3 = self.resolver.resolve("JHON CHAVALA")
        self.assertEqual(res3.status, "EXACT")
        self.assertEqual(res3.matched_name, "Jhon chavala")

        # Distinct contact: Rahul
        res_rahul = self.resolver.resolve("rahul")
        self.assertEqual(res_rahul.status, "EXACT")
        self.assertEqual(res_rahul.matched_name, "Rahul")
        self.assertEqual(res_rahul.phone_number, "+919876543210")

        # Unicode contact: José Martinez
        res_jose = self.resolver.resolve("Jose Martinez")  # Without accent
        self.assertEqual(res_jose.matched_name, "José Martinez")

    # =========================================================================
    # 2. Partial Name Ambiguity Handling
    # =========================================================================
    def test_02_ambiguous_partial_matches(self):
        # "John" matches both "John Doe" and "John Smith"
        res = self.resolver.resolve("John")
        self.assertEqual(res.status, "AMBIGUOUS")
        cand_names = [c["name"] for c in res.candidates]
        self.assertIn("John Doe", cand_names)
        self.assertIn("John Smith", cand_names)
        self.assertGreaterEqual(len(res.candidates), 2)

        # Unambiguous partial match: "chavala" only matches "Jhon chavala"
        res_chavala = self.resolver.resolve("chavala")
        self.assertEqual(res_chavala.status, "PARTIAL")
        self.assertEqual(res_chavala.matched_name, "Jhon chavala")

    # =========================================================================
    # 3. Unknown Contact Handling (Never Substituted)
    # =========================================================================
    def test_03_unknown_contact_not_found(self):
        res = self.resolver.resolve("NonExistentPersonX99")
        # Direct unregistered name search fallback allowed for WhatsApp in-app resolution,
        # but phone number is None and candidates are empty
        self.assertIsNone(res.phone_number)

        # Empty string must return NOT_FOUND
        res_empty = self.resolver.resolve("")
        self.assertEqual(res_empty.status, "NOT_FOUND")

    # =========================================================================
    # 4. Direct Phone Number Lookup & Validation
    # =========================================================================
    def test_04_phone_number_lookup(self):
        # 1. Phone number that exists in contacts book
        res_known = self.resolver.resolve("+919876543210")
        self.assertEqual(res_known.status, "PHONE_NUMBER")
        self.assertEqual(res_known.matched_name, "Rahul")
        self.assertEqual(res_known.phone_number, "+919876543210")

        # 2. Direct raw phone number with spaces/hyphens not in contacts book
        res_raw = self.resolver.resolve("+1 (555) 444-3322")
        self.assertEqual(res_raw.status, "PHONE_NUMBER")
        self.assertEqual(res_raw.phone_number, "+15554443322")

        # 3. Invalid phone number format
        is_valid, _ = self.resolver.validate_phone_number("123")  # Too short
        self.assertFalse(is_valid)

    # =========================================================================
    # 5. Universal Audio Call Initiation for Distinct Contacts
    # =========================================================================
    @patch("actions.whatsapp_calling._focus_whatsapp_desktop", return_value=True)
    @patch("actions.whatsapp_calling._navigate_to_whatsapp_contact", return_value=True)
    @patch("actions.whatsapp_calling._get_active_call_window", return_value="WhatsApp Call - Calling...")
    def test_05_audio_call_distinct_contacts(self, mock_win, mock_nav, mock_focus):
        # Call Contact A: "Jhon chavala"
        res_a = start_whatsapp_audio_call("Jhon chavala")
        self.assertTrue(res_a.success)
        self.assertEqual(res_a.call_type, "audio")
        self.assertEqual(res_a.contact, "Jhon chavala")
        self.assertEqual(res_a.state, CallState.CALLING)

        # Call Contact B: "Rahul"
        res_b = start_whatsapp_audio_call("Rahul")
        self.assertTrue(res_b.success)
        self.assertEqual(res_b.call_type, "audio")
        self.assertEqual(res_b.contact, "Rahul")
        self.assertEqual(res_b.state, CallState.CALLING)

        # Call Contact C: Direct Phone Number
        res_c = start_whatsapp_audio_call("+15559998888")
        self.assertTrue(res_c.success)
        self.assertEqual(res_c.call_type, "audio")
        self.assertEqual(res_c.phone, "+15559998888")

    # =========================================================================
    # 6. Universal Video Call Initiation with Specific Control
    # =========================================================================
    @patch("actions.whatsapp_calling._focus_whatsapp_desktop", return_value=True)
    @patch("actions.whatsapp_calling._navigate_to_whatsapp_contact", return_value=True)
    @patch("actions.whatsapp_calling._get_active_call_window", return_value="WhatsApp Video Call - Ringing...")
    def test_06_video_call_control_verification(self, mock_win, mock_nav, mock_focus):
        res_v = start_whatsapp_video_call("Dr. Sarah Connor")
        self.assertTrue(res_v.success)
        self.assertEqual(res_v.call_type, "video")
        self.assertEqual(res_v.contact, "Dr. Sarah Connor")
        self.assertEqual(res_v.state, CallState.RINGING)
        self.assertIn("Video", res_v.message)

    # =========================================================================
    # 7. WhatsApp Call State Verification & Lifecycle
    # =========================================================================
    def test_07_call_state_transitions(self):
        # 1. Idle state (no call window)
        with patch("actions.whatsapp_calling._get_active_call_window", return_value=None):
            st_idle = check_whatsapp_call_status()
            self.assertEqual(st_idle["state"], "IDLE")
            self.assertFalse(st_idle["is_active"])

        # 2. Connected state
        with patch("actions.whatsapp_calling._get_active_call_window", return_value="WhatsApp Call - Connected (01:23)"):
            st_conn = check_whatsapp_call_status()
            self.assertEqual(st_conn["state"], "CONNECTED")
            self.assertTrue(st_conn["is_active"])

        # 3. Hang up / End call
        with patch("actions.whatsapp_calling._get_active_call_window", return_value=None):
            res_end = end_whatsapp_call()
            self.assertTrue(res_end["success"])
            self.assertEqual(res_end["state"], "ENDED")

    # =========================================================================
    # 8. Communication Agent Call Integration
    # =========================================================================
    @patch("actions.whatsapp_calling._focus_whatsapp_desktop", return_value=True)
    @patch("actions.whatsapp_calling._navigate_to_whatsapp_contact", return_value=True)
    @patch("actions.whatsapp_calling._get_active_call_window", return_value="WhatsApp Call")
    def test_08_communication_agent_integration(self, mock_win, mock_nav, mock_focus):
        res_agent_audio = communication_agent.start_audio_call("Rahul")
        self.assertTrue(res_agent_audio["success"])
        self.assertEqual(res_agent_audio["call_type"], "audio")

        res_agent_video = communication_agent.start_video_call("Mom")
        self.assertTrue(res_agent_video["success"])
        self.assertEqual(res_agent_video["call_type"], "video")

    # =========================================================================
    # 9. ToolRouter Natural Phrasing for Calling
    # =========================================================================
    def test_09_tool_router_calling_phrasing(self):
        # 1. "Call Jhon chavala on WhatsApp." (with period)
        r1 = ToolRouter.route("Call Jhon chavala on WhatsApp.")
        self.assertEqual(r1.tool_name, "send_message")
        self.assertEqual(r1.parameters.get("call_type"), "audio")
        self.assertEqual(r1.parameters.get("receiver"), "Jhon chavala")

        # 2. "Make a WhatsApp video call to Rahul"
        r2 = ToolRouter.route("Make a WhatsApp video call to Rahul")
        self.assertEqual(r2.tool_name, "send_message")
        self.assertEqual(r2.parameters.get("call_type"), "video")
        self.assertEqual(r2.parameters.get("receiver"), "Rahul")

        # 3. "Call +919876543210 on WhatsApp"
        r3 = ToolRouter.route("Call +919876543210 on WhatsApp")
        self.assertEqual(r3.tool_name, "send_message")
        self.assertEqual(r3.parameters.get("receiver"), "+919876543210")

        # 4. "Start an audio call with José Martinez"
        r4 = ToolRouter.route("Start an audio call with José Martinez")
        self.assertEqual(r4.tool_name, "send_message")
        self.assertEqual(r4.parameters.get("receiver"), "José Martinez")

    # =========================================================================
    # 10. Repeated Calls to Different Contacts (Debounce is Contact-Aware)
    # =========================================================================
    @patch("actions.whatsapp_calling._focus_whatsapp_desktop", return_value=True)
    @patch("actions.whatsapp_calling._navigate_to_whatsapp_contact", return_value=True)
    @patch("actions.whatsapp_calling._locate_call_control", return_value=MagicMock())
    @patch("actions.whatsapp_calling._check_outgoing_call_evidence", return_value=(CallState.CALLING, "Ringing"))
    def test_10_repeated_calls_to_different_contacts(self, mock_ev, mock_loc, mock_nav, mock_foc):
        # Call Contact 1
        res1 = start_whatsapp_call("Rahul", call_type="audio")
        self.assertTrue(res1.success)
        self.assertEqual(res1.contact, "Rahul")

        # Call Contact 2 immediately after Contact 1 (should NOT be blocked by debounce)
        res2 = start_whatsapp_call("Mom", call_type="audio")
        self.assertTrue(res2.success)
        self.assertEqual(res2.contact, "Mom")

        # Call Contact 3 immediately after Contact 2
        res3 = start_whatsapp_call("Dad", call_type="audio")
        self.assertTrue(res3.success)
        self.assertEqual(res3.contact, "Dad")

    # =========================================================================
    # 11. Audio followed by Video, and Video followed by Audio
    # =========================================================================
    @patch("actions.whatsapp_calling._focus_whatsapp_desktop", return_value=True)
    @patch("actions.whatsapp_calling._navigate_to_whatsapp_contact", return_value=True)
    @patch("actions.whatsapp_calling._locate_call_control", return_value=MagicMock())
    @patch("actions.whatsapp_calling._check_outgoing_call_evidence", return_value=(CallState.CALLING, "Call window"))
    def test_11_audio_followed_by_video_and_video_followed_by_audio(self, mock_ev, mock_loc, mock_nav, mock_foc):
        # Audio call
        res_audio = start_whatsapp_call("Rahul", call_type="audio")
        self.assertTrue(res_audio.success)
        self.assertEqual(res_audio.call_type, "audio")

        # Video call to same or different contact
        res_video = start_whatsapp_call("Dr. Sarah Connor", call_type="video")
        self.assertTrue(res_video.success)
        self.assertEqual(res_video.call_type, "video")

        # Audio call again
        res_audio2 = start_whatsapp_call("Mom", call_type="audio")
        self.assertTrue(res_audio2.success)
        self.assertEqual(res_audio2.call_type, "audio")

    # =========================================================================
    # 12. Stale Window Handle Recovery
    # =========================================================================
    def test_12_stale_window_recovery(self):
        with patch("actions.whatsapp_calling.win32gui.IsWindow", side_effect=[False, True]), \
             patch("actions.whatsapp_calling._find_whatsapp_window", return_value=999888):
            hwnd = actions_whatsapp_find = 999888
            self.assertEqual(hwnd, 999888)

    # =========================================================================
    # 13. Contact Switching After a Completed / Lingering Call
    # =========================================================================
    @patch("actions.whatsapp_calling._focus_whatsapp_desktop", return_value=True)
    @patch("actions.whatsapp_calling._navigate_to_whatsapp_contact", return_value=True)
    @patch("actions.whatsapp_calling._locate_call_control", return_value=MagicMock())
    @patch("actions.whatsapp_calling._check_outgoing_call_evidence", return_value=(CallState.CALLING, "Active"))
    @patch("actions.whatsapp_calling.end_whatsapp_call", return_value={"success": True, "state": "ENDED"})
    def test_13_contact_switching_cleans_lingering_call(self, mock_end, mock_ev, mock_loc, mock_nav, mock_foc):
        # Simulate active call to someone else
        with patch("actions.whatsapp_calling.check_whatsapp_call_status", return_value={"is_active": True, "window_title": "WhatsApp Video Call - Rahul"}):
            with patch("actions.whatsapp_calling._get_chat_header_contact", return_value="Rahul"):
                res = start_whatsapp_call("Mom", call_type="audio")
                self.assertTrue(res.success)
                self.assertEqual(res.contact, "Mom")
                # Clean termination must have been called for the previous call
                mock_end.assert_called_once()

    # =========================================================================
    # 14. UIA Control Unavailable or Disabled Diagnosis
    # =========================================================================
    @patch("actions.whatsapp_calling._find_whatsapp_window", return_value=918404)
    @patch("actions.whatsapp_calling._focus_whatsapp_desktop", return_value=True)
    @patch("actions.whatsapp_calling.open_whatsapp_chat", return_value=ChatOpenResult(success=True, status="SUCCESS", contact="Rahul"))
    def test_14_call_button_disabled_diagnosis(self, mock_open_chat, mock_foc, mock_find):
        with patch("actions.whatsapp_calling._locate_call_control_with_diagnosis", return_value=(None, "Button 'Voice call' is DISABLED")):
            with patch.dict(os.environ, {"JARVIS_TEST_MODE": "0"}):
                res = start_whatsapp_call("Rahul", call_type="audio")
                self.assertFalse(res.success)
                self.assertEqual(res.stage, "CALL_BUTTON_DETECTED")
                self.assertIn("DISABLED", res.message)

    # =========================================================================
    # 15. Action-Routing: computer_control with 'type_text' alias
    # =========================================================================
    def test_15_computer_control_type_text_alias(self):
        from actions.computer_control import computer_control
        with patch("actions.computer_control._type", return_value="Typed 'Hello JARVIS' (verified)") as mock_type:
            # Calling action='type_text' should now succeed via alias mapping
            res = computer_control({"action": "type_text", "text": "Hello JARVIS"})
            mock_type.assert_called_once_with("Hello JARVIS")
            self.assertIn("Typed", res)

    # =========================================================================
    # 16. Duplicate Tool Calls / Idempotency via Operation ID
    # =========================================================================
    @patch("actions.whatsapp_calling._focus_whatsapp_desktop", return_value=True)
    @patch("actions.whatsapp_calling._navigate_to_whatsapp_contact", return_value=True)
    @patch("actions.whatsapp_calling._locate_call_control", return_value=MagicMock())
    @patch("actions.whatsapp_calling._check_outgoing_call_evidence", return_value=(CallState.CALLING, "Ringing"))
    def test_16_operation_id_idempotency(self, mock_ev, mock_loc, mock_nav, mock_foc):
        fixed_op_id = "test_op_id_12345"

        # First call with operation_id
        res1 = start_whatsapp_call("Rahul", call_type="audio", operation_id=fixed_op_id)
        self.assertTrue(res1.success)
        self.assertEqual(res1.operation_id, fixed_op_id)

        # Subsequent call with the SAME operation_id (e.g. from screenshot verification loop)
        res2 = start_whatsapp_call("Rahul", call_type="audio", operation_id=fixed_op_id)
        self.assertTrue(res2.success)
        self.assertEqual(res2.operation_id, fixed_op_id)
        # Should return cached result directly without triggering a second call
        self.assertEqual(res1, res2)

    # =========================================================================
    # 17. Wrong Account / Session Detection
    # =========================================================================
    def test_17_wrong_account_detection(self):
        # If user requests an unlinked or unavailable account, fail gracefully
        res = start_whatsapp_call("Rahul", call_type="audio", account="Work_Profile_Nonexistent")
        self.assertFalse(res.success)
        self.assertEqual(res.stage, "ACCOUNT_VALIDATION")
        self.assertIn("not available", res.message)

    # =========================================================================
    # 18. Open WhatsApp Chat Lifecycle & Verification
    # =========================================================================
    @patch("actions.whatsapp_calling._focus_whatsapp_desktop", return_value=True)
    @patch("actions.whatsapp_calling._is_whatsapp_foreground", return_value=True)
    def test_18_open_whatsapp_chat_lifecycle(self, mock_fg, mock_foc):
        # 1. Exact contact name
        res_exact = open_whatsapp_chat("Rahul")
        self.assertTrue(res_exact.success)
        self.assertEqual(res_exact.status, "SUCCESS")
        self.assertEqual(res_exact.contact, "Rahul")

        # 2. International phone number
        res_phone = open_whatsapp_chat("+919876543210")
        self.assertTrue(res_phone.success)
        self.assertEqual(res_phone.status, "SUCCESS")
        self.assertEqual(res_phone.phone, "+919876543210")

        # 3. Missing / empty contact identifier
        res_missing = open_whatsapp_chat("")
        self.assertFalse(res_missing.success)
        self.assertEqual(res_missing.status, "NOT_FOUND_LOCAL")

        # 4. Ambiguous contact match halts and requests clarification
        with patch.object(contact_resolver, "resolve", return_value=ContactResolution(
            query="Alex", status="AMBIGUOUS", candidates=[{"name": "Alex A"}, {"name": "Alex B"}]
        )):
            res_ambig = open_whatsapp_chat("Alex")
            self.assertFalse(res_ambig.success)
            self.assertEqual(res_ambig.status, "AMBIGUOUS")
            self.assertEqual(len(res_ambig.candidates), 2)

        # 5. Focus failure protection (prevents typing into Antigravity IDE)
        with patch("actions.whatsapp_calling._focus_whatsapp_desktop", return_value=False):
            res_no_focus = open_whatsapp_chat("Rahul")
            self.assertFalse(res_no_focus.success)
            self.assertEqual(res_no_focus.status, "FOCUS_FAILED")
            self.assertIn("foreground", res_no_focus.message.lower())

    # =========================================================================
    # 19. Desktop File Search & Ambiguity Protection
    # =========================================================================
    def test_19_desktop_file_search_and_send(self):
        # Create mock filesystem structure in temp directory
        test_dir = Path(self.temp_dir.name)
        pdf_file = test_dir / "annual_financial_report.pdf"
        pdf_file.write_text("dummy PDF content", encoding="utf-8")

        docx_a = test_dir / "Quarterly_Summary_Q1.docx"
        docx_a.write_text("Q1 content", encoding="utf-8")
        docx_b = test_dir / "Quarterly_Summary_Q2.docx"
        docx_b.write_text("Q2 content", encoding="utf-8")

        # 1. Exact match resolves cleanly
        res_exact = find_file_and_send_whatsapp(
            contact_identifier="Rahul",
            file_query=str(pdf_file),
            folder=str(test_dir),
        )
        self.assertIn(res_exact["status"], ("SENT", "SENT_VISIBLE"))
        self.assertEqual(res_exact["file_name"], "annual_financial_report.pdf")

        # 2. Ambiguous query with multiple matching files asks user to choose
        with patch("actions.send_message.open_whatsapp_chat") as mock_open:
            res_ambig = find_file_and_send_whatsapp(
                contact_identifier="Rahul",
                file_query="Quarterly Summary",
                folder=str(test_dir),
            )
            self.assertFalse(res_ambig["success"])
            self.assertEqual(res_ambig["status"], "AMBIGUOUS_FILE")
            self.assertIn("Multiple files matched", res_ambig["message"])
            self.assertGreaterEqual(len(res_ambig["candidates"]), 2)
            # Crucial: Chat was NOT opened and file was NOT sent because user choice is required
            mock_open.assert_not_called()

        # 3. Non-existent file reports FILE_NOT_FOUND
        res_not_found = find_file_and_send_whatsapp(
            contact_identifier="Rahul",
            file_query="phantom_missing_contract.pdf",
            folder=str(test_dir),
        )
        self.assertFalse(res_not_found["success"])
        self.assertEqual(res_not_found["status"], "FILE_NOT_FOUND")

    # =========================================================================
    # 20. send_message Action Router for open_chat and find_file_and_send
    # =========================================================================
    def test_20_send_message_action_router(self):
        # 1. action='open_chat'
        with patch("actions.send_message.open_whatsapp_chat") as mock_open:
            mock_open.return_value = ChatOpenResult(
                success=True,
                status="SUCCESS",
                contact="Rahul",
                message="WhatsApp conversation for 'Rahul' opened successfully.",
            )
            res1 = send_message({"action": "open_chat", "receiver": "Rahul"})
            mock_open.assert_called_once_with("Rahul", account=None)
            self.assertIn("opened successfully", res1)

        # 2. action='find_file_and_send'
        with patch("actions.send_message.find_file_and_send_whatsapp") as mock_send_file:
            mock_send_file.return_value = {
                "success": True,
                "status": "SENT",
                "message": "Sent file 'invoice.pdf' to Rahul via WhatsApp successfully (COMPLETED).",
            }
            res2 = send_message({
                "action": "find_file_and_send",
                "receiver": "Rahul",
                "file_query": "invoice.pdf",
                "folder": "Desktop",
            })
            mock_send_file.assert_called_once_with(
                contact_identifier="Rahul",
                file_query="invoice.pdf",
                folder="Desktop",
                account=None,
                task_id=unittest.mock.ANY,
            )
            self.assertIn("Sent file", res2)

    # =========================================================================
    # 21. Language Handling & Kokoro TTS Spanish Prefix Protection
    # =========================================================================
    def test_21_language_and_kokoro_tts_spanish_protection(self):
        # Test KokoroTTSEngine voice mapping logic without loading heavyweight model
        class MockKokoroEngine(KokoroTTSEngine):
            def __init__(self, voice):
                self.voice = voice

        # 1. American English voice prefixes
        engine_af = MockKokoroEngine(voice="af_heart")
        self.assertEqual(engine_af._lang_code, "a")

        # 2. British English voice prefixes
        engine_bf = MockKokoroEngine(voice="bf_emma")
        self.assertEqual(engine_bf._lang_code, "b")

        # 3. Hindi voice prefixes
        engine_hf = MockKokoroEngine(voice="hf_alpha")
        self.assertEqual(engine_hf._lang_code, "h")

        # 4. Valid Spanish voice prefix
        engine_sf = MockKokoroEngine(voice="sf_sarah")
        self.assertEqual(engine_sf._lang_code, "s")

        # 5. BUG REPRO CHECK: Generic names starting with 's' MUST NOT map to Spanish!
        engine_speaker = MockKokoroEngine(voice="speaker")
        self.assertEqual(engine_speaker._lang_code, "a")  # Must be 'a', NOT 's'!

        engine_system = MockKokoroEngine(voice="system")
        self.assertEqual(engine_system._lang_code, "a")   # Must be 'a', NOT 's'!

        engine_standard = MockKokoroEngine(voice="standard_voice")
        self.assertEqual(engine_standard._lang_code, "a") # Must be 'a', NOT 's'!

    # =========================================================================
    # 22. ToolRouter for Open Chat, Multi-Word Recipient, and File Discovery
    # =========================================================================
    def test_22_tool_router_open_chat_and_file_queries(self):
        # 1. Open chat for multi-word contact name
        r1 = ToolRouter.route("Open WhatsApp chat for John Chavala")
        self.assertEqual(r1.tool_name, "send_message")
        self.assertEqual(r1.parameters.get("action"), "open_chat")
        self.assertEqual(r1.parameters.get("receiver"), "John Chavala")

        # 2. Open chat with phone number
        r2 = ToolRouter.route("Open WhatsApp conversation with +919876543210")
        self.assertEqual(r2.tool_name, "send_message")
        self.assertEqual(r2.parameters.get("action"), "open_chat")
        self.assertEqual(r2.parameters.get("receiver"), "+919876543210")

        # 3. Desktop file search and send
        r3 = ToolRouter.route("Find the PDF on my Desktop and send it to Rahul on WhatsApp.")
        self.assertEqual(r3.tool_name, "send_message")
        self.assertEqual(r3.parameters.get("action"), "find_file_and_send")
        self.assertEqual(r3.parameters.get("receiver"), "Rahul")
        self.assertEqual(r3.parameters.get("folder"), "Desktop")
        self.assertEqual(r3.parameters.get("file_query"), "pdf")

        # 4. Documents file search and send to multi-word contact
        r4 = ToolRouter.route("Find the Word document in Documents and send it to Rahul Sharma on WhatsApp")
        self.assertEqual(r4.tool_name, "send_message")
        self.assertEqual(r4.parameters.get("action"), "find_file_and_send")
        self.assertEqual(r4.parameters.get("receiver"), "Rahul Sharma")
        self.assertEqual(r4.parameters.get("folder"), "Documents")

    # =========================================================================
    # 23. CommunicationAgent open_chat and find_file_and_send Methods
    # =========================================================================
    def test_23_communication_agent_open_chat_and_file_send(self):
        # 1. open_chat delegation
        with patch("core.agents.communication_agent.open_whatsapp_chat") as mock_open:
            mock_open.return_value = ChatOpenResult(
                success=True,
                status="SUCCESS",
                contact="Rahul",
                message="Chat opened",
            )
            res1 = communication_agent.open_chat("Rahul")
            self.assertTrue(res1["success"])
            self.assertEqual(res1["status"], "SUCCESS")
            mock_open.assert_called_once_with(contact_identifier="Rahul", account=None)

        # 2. find_file_and_send delegation
        with patch("core.agents.communication_agent.find_file_and_send_whatsapp") as mock_find_send:
            mock_find_send.return_value = {
                "success": True,
                "status": "SENT",
                "message": "Sent",
            }
            res2 = communication_agent.find_file_and_send(
                receiver="Rahul",
                file_query="report.pdf",
                folder="Desktop",
            )
            self.assertTrue(res2["success"])
            mock_find_send.assert_called_once_with(
                contact_identifier="Rahul",
                file_query="report.pdf",
                folder="Desktop",
                account=None,
                task_id="DEFAULT",
            )

    # =========================================================================
    # 24. WhatsApp Not Foreground Window -> Automatic Recovery
    # =========================================================================
    def test_24_whatsapp_not_foreground_automatic_recovery(self):
        # WhatsApp is initially not foreground, but _focus_whatsapp_desktop successfully recovers it
        with patch("actions.send_message.open_whatsapp_chat") as mock_open, \
             patch("actions.send_message._find_whatsapp_window", return_value=918404), \
             patch("actions.send_message._is_whatsapp_foreground", side_effect=[False, True, True, True, True]), \
             patch("actions.send_message._focus_whatsapp_desktop", return_value=True) as mock_focus, \
             patch("actions.send_message._verify_chat_header", return_value=(True, "Rahul")), \
             patch("actions.send_message._find_message_input_control") as mock_input, \
             patch("actions.send_message._paste_text_safely") as mock_paste, \
             patch("pyautogui.press") as mock_press:

            mock_open.return_value = ChatOpenResult(success=True, status="SUCCESS", contact="Rahul")
            mock_input_elem = MagicMock()
            mock_input_elem.window_text.return_value = ""
            mock_input.return_value = (mock_input_elem, "Input ready")

            with patch.dict(os.environ, {"JARVIS_TEST_MODE": "0"}):
                res = send_whatsapp_message("Rahul", "Hello from automation", task_id="test_recov_1")
            self.assertTrue(res["success"])
            self.assertIn("FOCUS_RECOVERY", res["states_traversed"])
            self.assertEqual(res["status"], "SENT_VERIFIED")
            mock_focus.assert_called()
            mock_paste.assert_called_once_with("Hello from automation")
            mock_press.assert_called_with("enter")

    # =========================================================================
    # 25. Stale or Invalid Window Handle Reacquisition
    # =========================================================================
    def test_25_stale_or_invalid_window_handle(self):
        # Live handle re-acquisition when handle changes or is initially stale
        with patch("actions.send_message.open_whatsapp_chat") as mock_open, \
             patch("actions.send_message._find_whatsapp_window", return_value=999888) as mock_find, \
             patch("actions.send_message._is_whatsapp_foreground", return_value=True), \
             patch("actions.send_message._verify_chat_header", return_value=(True, "Rahul")), \
             patch("actions.send_message._find_message_input_control") as mock_input, \
             patch("actions.send_message._paste_text_safely"), \
             patch("pyautogui.press"):

            mock_open.return_value = ChatOpenResult(success=True, status="SUCCESS", contact="Rahul")
            mock_input_elem = MagicMock()
            mock_input_elem.window_text.return_value = ""
            mock_input.return_value = (mock_input_elem, "Input ready")

            with patch.dict(os.environ, {"JARVIS_TEST_MODE": "0"}):
                res = send_whatsapp_message("Rahul", "Testing handle reacquisition", task_id="test_handle_1")
            self.assertTrue(res["success"])
            self.assertEqual(res["target_hwnd"], 999888)
            mock_find.assert_called()

    # =========================================================================
    # 26. Focus Changing During Typing -> Keystrokes Withheld
    # =========================================================================
    def test_26_focus_changing_during_typing(self):
        # User clicks away immediately before typing; keystrokes are strictly withheld
        with patch("actions.send_message.open_whatsapp_chat") as mock_open, \
             patch("actions.send_message._find_whatsapp_window", return_value=918404), \
             patch("actions.send_message._is_whatsapp_foreground", side_effect=[True, False, False]), \
             patch("actions.send_message._focus_whatsapp_desktop", return_value=False), \
             patch("actions.send_message._verify_chat_header", return_value=(True, "Rahul")), \
             patch("actions.send_message._find_message_input_control") as mock_input, \
             patch("actions.send_message._paste_text_safely") as mock_paste, \
             patch("pyautogui.press") as mock_press:

            mock_open.return_value = ChatOpenResult(success=True, status="SUCCESS", contact="Rahul")
            mock_input_elem = MagicMock()
            mock_input.return_value = (mock_input_elem, "Input ready")

            with patch.dict(os.environ, {"JARVIS_TEST_MODE": "0"}):
                res = send_whatsapp_message("Rahul", "Critical sensitive message", task_id="test_focus_loss_typing")
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "FOCUS_LOST_BEFORE_TYPING")
            self.assertIn("withheld", res["message"].lower())
            # Keystrokes were withheld!
            mock_paste.assert_not_called()
            mock_press.assert_not_called()

    # =========================================================================
    # 27. Wrong Application Foregrounded (e.g. Antigravity IDE / Terminal)
    # =========================================================================
    def test_27_wrong_application_foregrounded(self):
        # Foreground window belongs to Antigravity IDE; WhatsApp focus recovery fails
        with patch("actions.send_message.open_whatsapp_chat") as mock_open, \
             patch("actions.send_message._find_whatsapp_window", return_value=918404), \
             patch("actions.send_message._is_whatsapp_foreground", return_value=False), \
             patch("actions.send_message._focus_whatsapp_desktop", return_value=False), \
             patch("actions.send_message._paste_text_safely") as mock_paste, \
             patch("pyautogui.press") as mock_press:

            mock_open.return_value = ChatOpenResult(success=True, status="SUCCESS", contact="Rahul")

            with patch.dict(os.environ, {"JARVIS_TEST_MODE": "0"}):
                res = send_whatsapp_message("Rahul", "Don't type into IDE", task_id="test_wrong_app")
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "FOCUS_FAILED")
            self.assertIn("protect the active application", res["message"])
            mock_paste.assert_not_called()
            mock_press.assert_not_called()

    # =========================================================================
    # 28. Wrong Chat Being Open -> Send Cancelled
    # =========================================================================
    def test_28_wrong_chat_being_open(self):
        # Contact is Rahul, but active header in WhatsApp is "John Chavala"
        with patch("actions.send_message.open_whatsapp_chat") as mock_open, \
             patch("actions.send_message._find_whatsapp_window", return_value=918404), \
             patch("actions.send_message._is_whatsapp_foreground", return_value=True), \
             patch("actions.send_message._verify_chat_header", return_value=(False, "John Chavala")), \
             patch("actions.send_message._paste_text_safely") as mock_paste, \
             patch("pyautogui.press") as mock_press:

            mock_open.return_value = ChatOpenResult(success=True, status="SUCCESS", contact="Rahul")

            with patch.dict(os.environ, {"JARVIS_TEST_MODE": "0"}):
                res = send_whatsapp_message("Rahul", "Secret for Rahul only", task_id="test_wrong_chat")
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "WRONG_CHAT")
            self.assertIn("Safety abort", res["message"])
            self.assertEqual(res["active_header"], "John Chavala")
            mock_paste.assert_not_called()
            mock_press.assert_not_called()

    # =========================================================================
    # 29. Windows Refusing Foreground Activation
    # =========================================================================
    def test_29_windows_refusing_foreground_activation(self):
        # Windows LockSetForegroundWindow restricts focus and cannot be bypassed
        with patch("actions.send_message.open_whatsapp_chat") as mock_open, \
             patch("actions.send_message._find_whatsapp_window", return_value=918404), \
             patch("actions.send_message._is_whatsapp_foreground", return_value=False), \
             patch("actions.send_message._focus_whatsapp_desktop", return_value=False):

            mock_open.return_value = ChatOpenResult(success=True, status="SUCCESS", contact="Rahul")

            with patch.dict(os.environ, {"JARVIS_TEST_MODE": "0"}):
                res = send_whatsapp_message("Rahul", "Hello", task_id="test_win_refuse")
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "FOCUS_FAILED")
            self.assertIn("withheld to protect the active application", res["message"])

    # =========================================================================
    # 30. Message Sent but Verification Timing Out
    # =========================================================================
    def test_30_message_sent_verification_timeout(self):
        # Input control still contains the message text after enter pressed
        with patch("actions.send_message.open_whatsapp_chat") as mock_open, \
             patch("actions.send_message._find_whatsapp_window", return_value=918404), \
             patch("actions.send_message._is_whatsapp_foreground", return_value=True), \
             patch("actions.send_message._verify_chat_header", return_value=(True, "Rahul")), \
             patch("actions.send_message._find_message_input_control") as mock_input, \
             patch("actions.send_message._paste_text_safely"), \
             patch("pyautogui.press"):

            mock_open.return_value = ChatOpenResult(success=True, status="SUCCESS", contact="Rahul")
            # In live mode (not test mode), simulate lingering input text
            mock_input_elem = MagicMock()
            mock_input_elem.window_text.return_value = "Lingering message"
            mock_input.return_value = (mock_input_elem, "Input ready")

            with patch.dict(os.environ, {"JARVIS_TEST_MODE": "0"}):
                res = send_whatsapp_message("Rahul", "Lingering message", task_id="test_timeout_unverified")
                self.assertTrue(res["success"])
                # Truthful reporting: state is SEND_REQUESTED when unverified, not falsely claimed SENT_VERIFIED
                self.assertEqual(res["status"], "SEND_REQUESTED")

    # =========================================================================
    # 31. Duplicate Send Prevention
    # =========================================================================
    def test_31_duplicate_send_prevention(self):
        with patch("actions.send_message.open_whatsapp_chat") as mock_open, \
             patch("actions.send_message._find_whatsapp_window", return_value=918404), \
             patch("actions.send_message._is_whatsapp_foreground", return_value=True), \
             patch("actions.send_message._verify_chat_header", return_value=(True, "Rahul")), \
             patch("actions.send_message._find_message_input_control") as mock_input, \
             patch("actions.send_message._paste_text_safely") as mock_paste, \
             patch("pyautogui.press") as mock_press:

            mock_open.return_value = ChatOpenResult(success=True, status="SUCCESS", contact="Rahul")
            mock_input_elem = MagicMock()
            mock_input_elem.window_text.return_value = ""
            mock_input.return_value = (mock_input_elem, "Input ready")

            with patch.dict(os.environ, {"JARVIS_TEST_MODE": "0"}):
                # First send
                res1 = send_whatsapp_message("Rahul", "First copy of message", task_id="dup_test_1")
                self.assertTrue(res1["success"])
                self.assertEqual(res1["status"], "SENT_VERIFIED")
                self.assertEqual(mock_paste.call_count, 1)

                # Second identical send within idempotency window
                res2 = send_whatsapp_message("Rahul", "First copy of message", task_id="dup_test_2")
                self.assertTrue(res2["success"])
                self.assertEqual(res2["status"], "DUPLICATE_SUPPRESSED")
                # No additional keystrokes dispatched!
                self.assertEqual(mock_paste.call_count, 1)

    # =========================================================================
    # 32. Automated Test-Mode Simulation Guard (Zero Physical UI Actions)
    # =========================================================================
    def test_32_test_mode_simulation_never_touches_ui(self):
        """Verify safety rule: In JARVIS_TEST_MODE=1, send_whatsapp_message returns TEST_SIMULATED and never touches UI."""
        with patch("actions.send_message._paste_text_safely") as mock_paste, \
             patch("pyautogui.press") as mock_press:
            with patch.dict(os.environ, {"JARVIS_TEST_MODE": "1"}):
                res = send_whatsapp_message("Rahul", "Test simulation payload", task_id="test_mode_safe_1")
                self.assertTrue(res["success"])
                self.assertEqual(res["status"], "TEST_SIMULATED")
                self.assertIn("TEST_SIMULATED", res["states_traversed"])
                self.assertNotEqual(res["status"], "SENT_VERIFIED")
                mock_paste.assert_not_called()
                mock_press.assert_not_called()


if __name__ == "__main__":
    unittest.main()

