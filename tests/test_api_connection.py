"""
tests/test_api_connection.py — Google Gemini API Connectivity & Diagnostics Suite.

Distinguishes and isolates:
- API key existence & source (.env, os.environ, config/api_keys.json)
- API key format & length (safe masking)
- Authentication failure vs Permission / API not enabled
- Invalid model vs Invalid request
- Rate limit / Quota error
- Network error vs WebSockets 1007 schema errors
"""

import os
import sys
import io
import asyncio
from pathlib import Path

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.config import get_api_key, get_key_diagnostics, mask_key
from core import gemini


def run_diagnostics():
    print("=" * 60)
    print("       JARVIS GEMINI API DIAGNOSTICS & CONNECTIVITY        ")
    print("=" * 60)

    diag = get_key_diagnostics()
    print("1. Configuration Check:")
    print(f"   - API Key Found:       {'YES' if diag['exists'] else 'NO'}")
    print(f"   - Source Variable:     {diag['source']}")
    print(f"   - Masked Key:          {diag['masked']}")
    print(f"   - Key Length:          {diag['length']} chars")
    print(f"   - Surrounding Quotes:  {'YES (MALFORMED)' if diag['has_surrounding_quotes'] else 'No'}")
    print(f"   - Embedded Spaces:     {'YES (MALFORMED)' if diag['has_spaces'] else 'No'}")
    print(f"   - Format Valid:        {'YES' if diag['format_valid'] else 'NO'}")

    if not diag["exists"]:
        print("\n[FAIL] RESULT: [API Key Missing] Please provide GEMINI_API_KEY in .env or environment.")
        return False

    if not diag["format_valid"]:
        print("\n[FAIL] RESULT: [API Key Malformed] Check for extra spaces or quotes around the key.")
        return False

    key = get_api_key()

    print("\n2. Testing Direct Google Gemini REST API (Model: gemini-3.5-flash-lite)...")
    try:
        from google import genai
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents="Say 'OK' in one word.",
        )
        resp_text = (response.text or "").strip()
        print(f"   [SUCCESS] REST API SUCCESS: Received response: '{resp_text}'")
    except Exception as e:
        err_msg = str(e)
        print(f"   [FAIL] REST API Request Failed:")
        print(f"      - Error: {err_msg}")
        
        err_lower = err_msg.lower()
        if "api_key_invalid" in err_lower or "401" in err_lower or "invalid api key" in err_lower:
            print("      -> CLASSIFICATION: [Authentication Failure] Google Gemini API rejected the key. Verify key validity.")
        elif "permission_denied" in err_lower or "403" in err_lower or "service_disabled" in err_lower:
            print("      -> CLASSIFICATION: [Permission / API Not Enabled] Key valid, but Generative Language API is disabled in Cloud Console.")
        elif "not_found" in err_lower or "404" in err_lower:
            print("      -> CLASSIFICATION: [Invalid Model] Model name is deprecated or unavailable.")
        elif "resource_exhausted" in err_lower or "429" in err_lower:
            print("      -> CLASSIFICATION: [Rate Limit / Quota Exceeded] API rate limit reached.")
        elif "invalid_argument" in err_lower or "400" in err_lower:
            print("      -> CLASSIFICATION: [Invalid Request] Malformed payload or arguments.")
        elif any(k in err_lower for k in ("timeout", "getaddrinfo", "connectionrefused", "network", "offline")):
            print("      -> CLASSIFICATION: [Network Error] Could not connect to Google API endpoints.")
        else:
            print(f"      -> CLASSIFICATION: [Other Error] {err_msg}")
        return False

    print("\n3. Testing Core Gemini Fallback Ladder...")
    try:
        reply = gemini.text("Say hello in one word", tier=gemini.FAST, timeout_ms=10000)
        print(f"   [SUCCESS] Fallback Ladder SUCCESS: Model responded: '{reply[:60]}'")
    except Exception as e:
        print(f"   [WARN] Fallback Ladder Warning: {e}")

    print("\n4. Testing Tool Declarations & OpenAPI Schema Compliance...")
    from core.action_loader import discover_actions
    from core.plugin_loader import discover_plugins
    from main import TOOL_DECLARATIONS

    actions = discover_actions(BASE_DIR / "actions")
    plugins = discover_plugins(BASE_DIR / "plugins", core_tool_names=set())
    all_decls = TOOL_DECLARATIONS + actions.get_tool_declarations() + plugins.get_tool_declarations()
    
    schema_errors = []
    for i, tool in enumerate(all_decls):
        tname = tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", f"tool_{i}")
        props = tool.get("parameters", {}).get("properties", {}) if isinstance(tool, dict) else {}
        for p_name, p_val in props.items():
            if isinstance(p_val, dict) and p_val.get("type") == "ARRAY":
                if "items" not in p_val:
                    schema_errors.append(f"Tool [{i}] '{tname}' property '{p_name}' missing 'items'")

    if schema_errors:
        print(f"   [FAIL] Tool Schema Validation FAILED ({len(schema_errors)} errors):")
        for err in schema_errors:
            print(f"      - {err}")
        print("      -> CLASSIFICATION: [WebSockets 1007 Schema Error] Schema is missing array items.")
        return False
    else:
        print(f"   [SUCCESS] Tool Schema Validation SUCCESS: All {len(all_decls)} tools comply with Gemini OpenAPI requirements (no missing items fields).")

    print("\n" + "=" * 60)
    print("ALL CONNECTIVITY, AUTHENTICATION & SCHEMA CHECKS PASSED!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = run_diagnostics()
    sys.exit(0 if success else 1)
