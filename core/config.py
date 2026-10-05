"""
core/config.py — Centralized Configuration & Secrets Management for JARVIS.

Handles loading API keys and system settings from:
1. Environment variables (GEMINI_API_KEY, GOOGLE_API_KEY)
2. .env file in project root
3. config/api_keys.json (legacy fallback)

Never logs secrets or sensitive tokens.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_KEYS_JSON_PATH = CONFIG_DIR / "api_keys.json"
ENV_PATH = BASE_DIR / ".env"
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)


def load_dotenv(path: Path = ENV_PATH) -> None:
    """Lightweight .env parser without mandatory external dependencies."""
    if not path.exists():
        return
    try:
        content = path.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("\"'")
            if key and key not in os.environ:
                os.environ[key] = val
    except Exception as e:
        print(f"[Config] Warning: could not parse .env: {e}")


# Initialize .env on module import
load_dotenv()


def get_api_key(refresh: bool = False) -> str:
    """
    Retrieve Gemini API key with priority:
    1. os.environ['GEMINI_API_KEY']
    2. os.environ['GOOGLE_API_KEY']
    3. config/api_keys.json ('gemini_api_key')
    """
    if refresh:
        load_dotenv()

    # 1. Environment variables
    env_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if env_key and env_key.strip():
        return env_key.strip()

    # 2. JSON file
    if API_KEYS_JSON_PATH.exists():
        try:
            data = json.loads(API_KEYS_JSON_PATH.read_text(encoding="utf-8"))
            key = data.get("gemini_api_key", "").strip()
            if key:
                return key
        except Exception:
            pass

    return ""


def get_setting(key: str, default: Any = None) -> Any:
    """Retrieve an arbitrary configuration setting from config/api_keys.json or env."""
    env_val = os.environ.get(key.upper())
    if env_val is not None:
        return env_val

    if API_KEYS_JSON_PATH.exists():
        try:
            data = json.loads(API_KEYS_JSON_PATH.read_text(encoding="utf-8"))
            if key in data:
                return data[key]
        except Exception:
            pass

    return default


def mask_key(key: str) -> str:
    """Mask sensitive key safely without exposing secrets (e.g. AIzaSy****abcd or AQ.Ab8****pC7Q)."""
    if not key:
        return "<none>"
    key = key.strip()
    if len(key) <= 8:
        return "****"
    return f"{key[:6]}****{key[-4:]}"


def get_key_diagnostics() -> dict:
    """Inspect API key status safely without exposing secrets."""
    load_dotenv()
    source = "none"
    key = ""
    
    if os.environ.get("GEMINI_API_KEY", "").strip():
        source = "os.environ['GEMINI_API_KEY']"
        key = os.environ.get("GEMINI_API_KEY", "").strip()
    elif os.environ.get("GOOGLE_API_KEY", "").strip():
        source = "os.environ['GOOGLE_API_KEY']"
        key = os.environ.get("GOOGLE_API_KEY", "").strip()
    elif API_KEYS_JSON_PATH.exists():
        try:
            data = json.loads(API_KEYS_JSON_PATH.read_text(encoding="utf-8"))
            k = data.get("gemini_api_key", "").strip()
            if k:
                source = "config/api_keys.json"
                key = k
        except Exception:
            pass

    has_quotes = key.startswith(('"', "'")) or key.endswith(('"', "'"))
    has_spaces = " " in key

    return {
        "exists": bool(key),
        "source": source,
        "length": len(key) if key else 0,
        "masked": mask_key(key),
        "has_surrounding_quotes": has_quotes,
        "has_spaces": has_spaces,
        "format_valid": bool(key and len(key) >= 20 and not has_quotes and not has_spaces),
    }


def sanitize_for_log(text: str) -> str:
    """Scrub known API keys and sensitive tokens from log messages."""
    key = get_api_key()
    if key and len(key) > 6 and key in text:
        masked = mask_key(key)
        text = text.replace(key, masked)
    return text

