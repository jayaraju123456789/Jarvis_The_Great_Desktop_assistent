"""
jarvis_cli.py — Command-Line Interface and Headless Autonomous Runner for JARVIS.

Usage:
    python jarvis_cli.py "Create a simple Python calculator application."
    python jarvis_cli.py "Create a DOCX document containing a one-page explanation of artificial intelligence."
    python jarvis_cli.py --test-all
"""

from __future__ import annotations

import argparse
import sys
import time

from core.logger import log_event
from core.orchestrator import orchestrator


def main():
    parser = argparse.ArgumentParser(description="JARVIS Autonomous Computer Agent CLI")
    parser.add_argument("instruction", nargs="?", default="", help="Natural language instruction for JARVIS")
    parser.add_argument("--test-all", action="store_true", help="Execute the complete suite of 8 self-test scenarios")

    args = parser.parse_args()

    if args.test_all:
        print("\n" + "=" * 70)
        print("  JARVIS AUTONOMOUS AGENT — FULL SELF-TEST SUITE VERIFICATION")
        print("=" * 70 + "\n")
        from tests import test_jarvis_suite
        test_jarvis_suite.run_all_tests()
        sys.exit(0)

    if not args.instruction:
        print("Usage: python jarvis_cli.py \"<your instruction here>\"")
        print("       python jarvis_cli.py --test-all")
        sys.exit(1)

    print(f"\n[JARVIS] Instruction received: \"{args.instruction}\"\n")
    start = time.time()
    response = orchestrator.plan_and_execute(args.instruction)
    elapsed = time.time() - start

    print("\n" + "=" * 60)
    print(response)
    print("=" * 60)
    print(f"Execution completed in {elapsed:.2f} seconds.\n")


if __name__ == "__main__":
    main()
