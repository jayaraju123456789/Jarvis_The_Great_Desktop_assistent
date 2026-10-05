# JARVIS CODEBASE AUDIT & ARCHITECTURAL TRANSFORMATION REPORT
**Project:** MARK LIV / JARVIS Autonomous Computer & Software Engineering Agent  
**Auditor:** Senior AI-Agent Architect, Automation & Systems Engineer  
**Date:** October 2026  
**Status:** Audit Completed — Implementation Roadmap Ready  

---

## 1. Executive Summary

The existing repository (an evolution of "Mark LIV / Jarvis by Kashur Engineer") represents an ambitious personal assistant featuring a 3D holographic avatar GUI (PyQt6), audio input/output streaming, Gemini Live preview connection, and modular tool action discovery.

However, **it is fundamentally architected as a conversational voice assistant rather than an autonomous computer-operating agent**. It relies on single-turn function execution mediated by an ephemeral voice WebSocket loop, lacks task planning, has no command line / terminal execution engine, tracks no process lifecycles, cannot safely control applications or browsers without collisions, cannot generate or edit formatted documents, and assumes operations succeed without independent verification ("fake success").

To transform JARVIS into a **reliable, fast, autonomous computer agent**, the system must be augmented with:
1. An autonomous multi-agent orchestrator with explicit task lifecycle (`Plan → Tool Selection → Execute → Observe → Verify → Recover → Report`).
2. An isolated, multi-session **Application & Process Registry** that tracks spawned PIDs/windows and guarantees safe, selective cleanup without killing user applications.
3. A robust **Terminal & Command Executor** with background daemon support, port detection, and structured outputs (`command`, `exit_code`, `stdout`, `stderr`, `duration`, `process_id`, `status`).
4. An autonomous **Software Engineering / Coding Agent** that designs, creates, installs dependencies for, executes, debugs, and independently verifies full-stack and script applications.
5. A comprehensive **Document Agent** capable of creating professional Microsoft Word (`.docx`), PDF, and spreadsheet files with headings, tables, citations, and styles.
6. A deep **Research Agent** supporting a rigorous academic workflow (`/research` workspace, paper gathering, extraction, synthesis, literature review, research gap detection, citation integrity checking, and `RESEARCH_VALIDATION_REPORT.md`).
7. An **Independent Verification & Self-Correction Engine** with error classification (syntax, dependency, runtime, timeout, port conflict, permission) and a closed-loop retry policy (max 3 attempts).
8. A unified, fast **Headless & CLI Execution Layer** alongside the PyQt6 GUI and FastAPI dashboard, allowing automated testing and scriptable computer use.

---

## 2. Current Architecture

```
[User Mic / Voice] ──────► [PyQt6 GUI (ui.py)] ──────► [JarvisLive (main.py)]
                                  │                            ▲
                                  ▼                            │ WebSocket
                          [Avatar & Audio]       [Google Gemini Live API (3.1-flash)]
                                                               │
                                                               ▼ FunctionCall
                                                     [core/action_loader.py]
                                                               │
                     ┌────────────────┬────────────────────────┼───────────────────────┬────────────────┐
                     ▼                ▼                        ▼                       ▼                ▼
            [browser_control]  [dev_agent]             [computer_control]     [file_controller]  [open_app]
             (Playwright lock)  (Subprocess timeout)   (PyAutoGUI mouse/keys) (Send2trash/CRUD)   (Blind Popen)
```

### Key Components:
- **`main.py`**: Monolithic entry point (2,359 lines) implementing `JarvisLive`. Couples voice audio streaming, Gemini Live WebSockets (`models/gemini-3.1-flash-live-preview`), UI state management, and direct tool dispatch. Cannot be run headlessly or driven programmatically via text commands without modifying core loops.
- **`core/action_loader.py`**: Dynamic tool discovery scanning `actions/*.py` for module-level `TOOL` dicts. Handlers accept `(parameters, player, speak, response, session_memory)` and return arbitrary strings.
- **`core/gemini.py`**: Central fallback ladder for non-live calls (`FAST`, `SMART`, `SEARCH`). Tries throwaway Live sessions first to preserve REST quota, falling back to `gemini-2.5-flash`. Ignores OS environment variables for keys.
- **`core/llm_client.py`**: Local LLM client supporting Ollama and OpenAI-compatible endpoints (LM Studio, LocalAI), but orphaned from most actions which import `core.gemini`.
- **`actions/browser_control.py`**: Playwright automation (1,133 lines) attempting to open the user's real browser profile.
- **`actions/computer_control.py`**: PyAutoGUI/pyperclip wrapper for coordinate clicking, typing, hotkeys, and full-screen screenshots.
- **`actions/dev_agent.py` & `actions/code_helper.py`**: Code generation using LLM prompts, writing to `~/Desktop/JarvisProjects`. Runs commands with `subprocess.run(timeout=30)`.
- **`actions/file_controller.py` & `actions/file_processor.py`**: File management and multi-format inspection (images, pdfs, audio, docx text extraction).
- **`actions/open_app.py`**: Subprocess launcher using system commands or Start Menu keystrokes.
- **`memory/memory_manager.py`**: JSON-backed key-value store (`memory/long_term.json`) with categorization and prompt truncation.
- **`dashboard/server.py`**: FastAPI server on port 8000 providing an encrypted mobile web interface.

---

## 3. Existing Capabilities (What Works Today)

1. **Live Bidirectional Audio Streaming**: When Gemini Live API is connected, bidirectional audio streaming with viseme-based mouth animation works smoothly.
2. **Modular Tool Discovery**: Clean `TOOL` specification schema allows modules in `actions/` to be registered dynamically at startup without altering `main.py`.
3. **Basic File CRUD**: `actions/file_controller.py` reliably creates, moves, copies, lists, and sends files to the OS recycle bin with undo stack support.
4. **Basic Web Search**: `actions/web_search.py` provides Google Grounding search and DuckDuckGo fallback with circuit breaker protection against rate limits.
5. **Basic Desktop Input**: `actions/computer_control.py` successfully moves mouse, types text, presses hotkeys, and reads clipboard via PyAutoGUI and Pyperclip.
6. **Multi-Format File Summarization**: `actions/file_processor.py` can parse text from PDFs, extract text from docx, and describe images via Gemini vision.

---

## 4. Broken Capabilities & Root-Cause Analysis

### A. Browser Automation Collision & Profile Lockup
- **Symptom**: Calling `browser_control` frequently hangs, crashes, or fails to start browser sessions.
- **Root Cause**: In `actions/browser_control.py` (lines 574–589), the session launches via `engine_obj.launch_persistent_context(profile, ...)` pointing directly to the user's **active default browser profile** (e.g. `%LOCALAPPDATA%\Google\Chrome\User Data`). If the user already has Chrome or Edge open on their laptop, the OS locks `SingletonLock` / `SingletonCookie`. Playwright crashes with `Target closed` or `Process singleton lock`.
- **Additional Defect**: Browser threads remain running in background daemon threads (`BrowserThread-{browser_name}`) without clean shutdown guarantees or orphan process reaping.

### B. Dev Agent Timeout & "Fake Success"
- **Symptom**: Creating web servers, Streamlit apps, or GUI programs either hangs for 30 seconds or claims success when nothing is actually running.
- **Root Cause**: In `actions/dev_agent.py` (line 305):
  ```python
  result = subprocess.run(parts, capture_output=True, text=True, timeout=timeout, cwd=str(project_dir))
  ```
  `subprocess.run` is a **blocking synchronous call**. For long-running apps (Streamlit, Flask, FastAPI, Tkinter), it inevitably triggers `subprocess.TimeoutExpired`. The exception handler lines (324–325) state:
  ```python
  except subprocess.TimeoutExpired:
      return f"Timed out after {timeout}s — long-running app (server/GUI) is likely working."
  ```
  This is a blatant **false positive ("fake success")**. The process is terminated by the timeout handler or left orphaned in memory. No port check is performed, no browser verification is launched, and no process handle is saved to allow stopping it later.

### C. Application Opening Without Tracking or Closure ("Blind Popen")
- **Symptom**: JARVIS opens apps (e.g., Notepad, Word, Chrome, Terminal) but cannot close them selectively, and terminates user windows if asked to close.
- **Root Cause**: In `actions/open_app.py`, applications are started via `subprocess.Popen(app_name, shell=True)` with the return value discarded immediately. No PID is logged, no window handle is tracked, and no `APP_SESSION` registry exists. There is no `close_app` action in `open_app.py`. If a script attempts `taskkill /f /im chrome.exe`, it destroys the user's personal browser tabs and unsaved work.

### D. Word & Document Editing Does Not Work
- **Symptom**: Asking JARVIS to "Open Word and write a report on X" produces either a blank Word window or a brief chat reply.
- **Root Cause**: 
  1. `actions/open_app.py` simply launches `winword.exe`. It has zero capability to inject text, headings, or formatting into Word.
  2. `actions/file_processor.py` only implements `_read_content()` and `to_word` (which converts PDF text to a raw text `.docx`). It has **zero document creation tools**.
  3. No component exposes a document builder capable of creating structured `.docx` files with titles, headings (H1–H4), executive summaries, stylized tables, headers, footers, and references.

### E. Fragile Code Generation & Inability to Build Projects Reliably
- **Symptom**: Complex or multi-file coding projects fail silently or fail at runtime.
- **Root Cause**: Code generation in `dev_agent.py` relies on a single-pass JSON response. If the LLM generates markdown fences or non-JSON preamble, `json.loads` fails. When dependencies are installed, `sys.executable -m pip install` is run without virtual environment isolation, risking contamination of the host Python environment.

### F. Long Tasks Cause Latency Explosion
- **Symptom**: Latency increases dramatically across turns.
- **Root Cause**: `JarvisLive` maintains all conversational logs, function inputs, and viseme audio buffers in memory. Tools concatenate giant string contents (up to 40,000 characters) into prompt contexts without semantic filtering, summarization, or token budgeting.

### G. Subprocess Failures Lack Recovery Loops
- **Symptom**: Any terminal or command error halts execution immediately with an error string.
- **Root Cause**: There is no error classifier or remediation planner. Errors such as `ModuleNotFoundError`, `Address already in use`, `Permission denied`, or `SyntaxError` are dumped as raw text rather than triggering an automated fix-and-verify cycle.

---

## 5. Missing Capabilities (Critical Gaps)

1. **Generic Terminal & Shell Execution Engine**: No tool exists in `actions/` to execute arbitrary shell/PowerShell/terminal commands, capture exit codes, stream stdout/stderr, or detect listening network ports.
2. **Autonomous Multi-Agent Orchestrator**: No central orchestrator exists that can take a high-level goal, generate a multi-step dependency graph, assign subtasks to specialized agents, verify outputs, and handle self-correction.
3. **Application & Process Session Registry**: No central registry tracks what JARVIS spawned (PID, start time, window title, task ID) vs. pre-existing user software.
4. **Document Generation Engine (Word / DOCX / PDF / Excel)**: Completely missing. No capability to generate styled documents, tables, citations, or reports.
5. **Research Agent & Academic Workflow**: Missing entirely. No pipeline for query generation, source collection, paper extraction, literature synthesis, research gap identification, citation validation, or quality assurance reporting.
6. **Independent Verification & Testing Agent**: No component independently confirms that files exist, code compiles, tests pass, web apps serve HTTP 200, or UI elements render.
7. **Task State Persistence (`PROJECT_STATE.json`)**: No ability to checkpoint long-running multi-step projects and resume if interrupted.
8. **Headless / Programmatic CLI Runner**: Cannot run tasks autonomously without the PyQt6 GUI and microphone.

---

## 6. Performance & Scalability Bottlenecks

1. **Synchronous Subprocess Blocking**: Commands run synchronously on executor threads with coarse timeouts (30s, 60s, 120s), locking workers.
2. **Lack of Parallel Execution**: Multi-source research, multi-file inspection, and independent test executions are strictly sequential.
3. **Token Inefficiency**: Full file contents and session histories are repeatedly stuffed into prompts without summarization or AST indexing.
4. **Uncached Operations**: Web searches and model inferences repeat for identical queries without cache lookups.

---

## 7. Security & Human Confirmation Problems

1. **Plaintext API Keys**: `config/api_keys.json` stores keys in cleartext; `.env` file loading is not supported in `core/gemini.py`.
2. **Unconfirmed Destructive File Operations**: While `actions/file_controller.py` uses `send2trash`, recursive folder modifications or potential overwrite operations lack human-in-the-loop gates.
3. **Arbitrary Code Execution in Sandbox**: `actions/desktop.py` uses `exec()` with a homebrewed sandbox dictionary that can be bypassed or cause side-effects.

---

## 8. Reliability & State Management Problems

1. **"Fake Success" Reporting**: The system reports tasks as "Done" based on prompt completion or timeouts rather than verifiable evidence.
2. **Zombie & Orphan Processes**: Terminated or timed-out background servers remain listening on ports (e.g. 8501 for Streamlit, 8000 for FastAPI).
3. **No Rollback on Failed Multi-Step Tasks**: If step 4 of 6 fails, steps 1–3 leave partial or corrupt state on disk without clean recovery.

---

## 9. Top 10 Fundamental Problems

| # | Problem | Impact | Root Cause |
|---|---------|--------|------------|
| 1 | **No Autonomous Task Orchestrator & Planner** | Cannot execute multi-step requests; only does single reactive tool calls | Architecture is built around real-time voice streaming rather than agentic planning |
| 2 | **No Real Terminal / Command Executor Tool** | Cannot run build scripts, shell commands, servers, or CLI tools | Omission of shell execution tool with structured output in `actions/` |
| 3 | **No Process / Window Session Registry** | Leaves orphan servers; cannot close opened apps safely without killing user apps | Subprocesses spawned with discarded PIDs and no registry |
| 4 | **Browser Profile Locking & Crash** | Browser automation fails if user has Chrome/Edge open | Playwright targets the live default profile directly instead of an isolated automated profile |
| 5 | **No Document Generation (DOCX/PDF)** | Cannot fulfill user document/essay/report generation requests | No document generation engine; `file_processor` only reads text |
| 6 | **No Research Workflow or Literature Agent** | Cannot research topics, synthesize literature, or write academic papers | No pipeline for paper search, metadata extraction, research gap analysis, or citation checking |
| 7 | **Fake Success & Lack of Independent Verification** | Tells user tasks are complete when they failed or timed out | No verification step after execution; returns "Done" on exceptions |
| 8 | **Dev Agent Blocks & Kills Long-Running Apps** | Cannot build or test web apps, Streamlit dashboards, or background services | Uses blocking `subprocess.run` with timeout that kills the server |
| 9 | **Hard-Coded Config & Missing Environment Variables** | Fails if `config/api_keys.json` is missing or keys are set via env | Keys only read from JSON; `.env` / `os.environ` ignored |
| 10 | **Tightly Coupled to PyQt GUI & Audio Hardware** | Impossible to run automated benchmarks, CI, or headless tasks | `main.py` entrypoint requires PyQt6 window, mic, speaker, and live model |

---

## 10. Target Architecture

```
                                  USER REQUEST
                        (Voice / Text / CLI / API)
                                    │
                                    ▼
                     ┌──────────────────────────────┐
                     │     ORCHESTRATOR AGENT       │
                     │  - Intent & Requirement Parse│
                     │  - Plan Graph Generation     │
                     │  - State & Progress Tracker  │
                     │  - PROJECT_STATE.json        │
                     └──────────────┬───────────────┘
                                    │
       ┌────────────────────────────┼────────────────────────────┐
       ▼                            ▼                            ▼
┌──────────────┐             ┌──────────────┐             ┌──────────────┐
│ CODING AGENT │             │RESEARCH AGENT│             │DOCUMENT AGENT│
│ - Architecture             │ - Discovery  │             │ - DOCX/PDF   │
│ - Code Gen   │             │ - Extraction │             │ - Headings   │
│ - Dev Server │             │ - Gap Anal.  │             │ - Tables     │
│ - Debugging  │             │ - Synthesis  │             │ - Citations  │
└──────┬───────┘             └──────┬───────┘             └──────┬───────┘
       │                            │                            │
       └────────────────────────────┼────────────────────────────┘
                                    │
                                    ▼
       ┌─────────────────────────────────────────────────────────┐
       │                   CORE TOOL PLATFORM                    │
       │ ┌──────────────────────┐       ┌──────────────────────┐ │
       │ │  TERMINAL EXECUTOR   │       │   BROWSER AUTOMATION │ │
       │ │  - Structured Result │       │   - Isolated Profile │ │
       │ │  - Async & Daemons   │       │   - DOM Readiness    │ │
       │ │  - Port/PID Tracking │       │   - Verified Cleanup │ │
       │ └──────────────────────┘       └──────────────────────┘ │
       │ ┌──────────────────────┐       ┌──────────────────────┐ │
       │ │  PROCESS REGISTRY    │       │   FILE SYSTEM INTEL  │ │
       │ │  - APP_SESSION Track │       │   - Safe Operations  │ │
       │ │  - Selective Cleanup │       │   - Inspection/Index │ │
       │ └──────────────────────┘       └──────────────────────┘ │
       └────────────────────────────┬────────────────────────────┘
                                    │
                                    ▼
                     ┌──────────────────────────────┐
                     │ VERIFICATION & RECOVERY LOOP │
                     │  - Assertive Verification    │
                     │  - Error Classifier          │
                     │  - Retry Policy (Max 3)      │
                     │  - Evidence Collection       │
                     └──────────────┬───────────────┘
                                    │
                                    ▼
                             FINAL RESPONSE
                     - Completed Accomplishments
                     - Files Created/Modified
                     - Verification Evidence
                     - Issues / Next Steps
```

---

## 11. Priority Breakdown

### P0 — Critical (Must Have for Reliability & Operation)
1. **Application & Process Registry (`core/process_manager.py`)**: Track every PID, window title, start time, and port spawned by JARVIS. Provide deterministic, selective cleanup that never touches user applications.
2. **Terminal & Command Executor (`tools/terminal_executor.py` & `actions/terminal_tool.py`)**: Asynchronous, non-blocking command execution with structured `CommandResult` (command, exit_code, stdout, stderr, duration, pid, status), port detection, and background daemon support.
3. **Isolated Browser Session Controller (`actions/browser_control.py` refactor)**: Guarantee isolated automation profiles (`--user-data-dir`) so JARVIS never collides with or locks the user's running Chrome/Edge. Explicit readiness detection and clean teardown.
4. **Environment & API Key Loader (`core/config.py`)**: Support `.env`, `os.environ` (`GEMINI_API_KEY`, `GOOGLE_API_KEY`), and `config/api_keys.json` with clear diagnostics.
5. **Headless & CLI Runner (`agent_runner.py` / `jarvis_cli.py`)**: Enable natural-language instruction execution via CLI, scripts, and tests without requiring microphone/PyQt6.
6. **Orchestrator Agent & Task Manager (`core/orchestrator.py`)**: Stateful `Plan → Tool Selection → Execute → Observe → Verify → Recover → Report` lifecycle with `PROJECT_STATE.json` persistence.

### P1 — Important (Core Functional Capabilities)
1. **Autonomous Coding Agent (`core/agents/coding_agent.py`)**: Full application lifecycle (requirements, files, virtual envs, dependencies, background server launch, port checking, self-debugging).
2. **Document Generation Agent (`core/agents/document_agent.py` & `actions/document_tool.py`)**: Full Word `.docx`, PDF, and structured report creator with styles, headings, tables, callouts, and bibliographies.
3. **Research Intelligence Agent (`core/agents/research_agent.py` & `actions/research_tool.py`)**: Multi-step academic research engine with `/research` workspace, PDF/paper ingestion, literature extraction, research gap identification, citation checking, and validation reports.
4. **Independent Verification & Testing Agent (`core/agents/verification_agent.py`)**: Verifies files exist, processes run, ports respond to HTTP requests, and code passes tests before declaring success.
5. **Self-Correction & Retry Engine (`core/recovery.py`)**: Classifies failures (syntax, dependency, runtime, timeout, port conflict, permission) and executes automated remediation strategies.

### P2 — Improvements & Polish
1. **Agent Status Dashboard UI**: Modern progress indicators, active agent display, step counters, and task tree.
2. **Memory System Integration**: Feed learned patterns from past failures into tool memory so repeated errors are avoided.
3. **Context Optimization**: Sliding-window context, file AST indexing, and model routing (fast model for classification, reasoning model for coding/research).
4. **Comprehensive Automated Test Suite (`tests/`)**: Automated verification for all 8 self-test scenarios required by the specification.

---

## 12. Minimum Changes Required & Implementation Roadmap

1. **Step 1: Core Process Manager & Terminal Engine**
   - Implement `core/process_manager.py` (Registry, PID tracking, window tracking, safe kill).
   - Implement `tools/terminal_executor.py` (Command execution, daemons, port detection, structured results).
   - Register `terminal_tool` in `actions/` so it is automatically discovered by `action_loader`.

2. **Step 2: Isolated Browser Controller Overhaul**
   - Refactor `actions/browser_control.py` to use dedicated automation user-data directories with fallback logic, explicit waits, DOM readiness checks, and session registry integration.

3. **Step 3: Document Generation Engine**
   - Implement `actions/document_tool.py` using `python-docx` for structured Word document generation (headings, tables, callout blocks, references, formatting).

4. **Step 4: Research Intelligence Workflow**
   - Implement `actions/research_tool.py` and `core/agents/research_agent.py` managing `/research` workspace, paper gathering, notes, synthesis, and validation reporting.

5. **Step 5: Autonomous Coding & Application Creation Agent**
   - Overhaul `actions/dev_agent.py` and implement `core/agents/coding_agent.py` to support real end-to-end software creation (directories, files, dependencies, running servers, checking ports, browser UI verification, safe process shutdown).

6. **Step 6: Master Orchestrator, Task Manager & Self-Correction Loop**
   - Implement `core/orchestrator.py` with multi-agent coordination, `PROJECT_STATE.json` persistence, and the 3-attempt recovery cycle.
   - Implement `jarvis_cli.py` / `agent_runner.py` for headless execution and programmatic automation.

7. **Step 7: Automated Self-Test Scenarios & Verification**
   - Execute all 8 required self-test scenarios:
     1. File Management
     2. Application Creation & Execution
     3. Web Browser Navigation & Isolated Cleanup
     4. Word Document Generation
     5. Coding & Server Lifecycle (Streamlit/FastAPI)
     6. Error Recovery (Broken Code Self-Correction)
     7. Research Literature Review & Validation Report
     8. Long Multi-Step Task Persistence
   - Validate and produce final implementation report.

---
*Audit Completed. Ready for Phase 1 Implementation.*
