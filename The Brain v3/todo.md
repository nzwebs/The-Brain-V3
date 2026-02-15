# Project TODO — The Brain v3

**Last updated:** 2026-02-14

## Summary
This file tracks the implementation status and next steps for the GUI + CLI two-agent Ollama project.

---

## Completed
- Settings UI: main + "Ollama Settings" tab
- Per-agent runtime controls: temperature, max tokens, top_p, stop, streaming
- Runtime options wired: `chat_with_ollama()` accepts runtime dicts from GUI
- Model management UI: pull, refresh, remove for A/B/Both
- Model list auto-refresh: all lists update on startup and URL changes
- Fixed: duplicate input fields in Agent Settings
- Add prompt engineering improvements

## In Progress
- Settings tab model management menu rebuilt (done)
- Model lists reliably update and display (done)
- Robust error/status feedback for model actions (done)
- Pull action shows progress/status in persistent log (done)
- Implement push-to-cloud: needs standardization
- Persistence & security: settings persist to `gui_config.json`; secure cloud auth not yet implemented

## Planned / Not Started
- Show installed models + sizes (probe server for size/metadata)
- Cloud sign-in UI: OAuth/Token flow, secure credential storage
- Full push workflow: push/publish models between servers (API dependent)
- Testing & QA: unit/integration/manual tests
- Docs & README: usage, scripts, model-management caveats

## Implementation Notes
- Avoid widget duplication in Agent Settings (one set per agent)
- `gui_config.json` stores all runtime and model settings
- Model discovery: tries `/v1/models`, `/models`, `/api/models`; merges unique IDs
- Remove/unpull: tries DELETE then POST `/unpull` as fallback
- Runtime options: passed to `ollama.Client.chat(...)` if supported

## Next Steps
1. Implement installed-models view with size/metadata (requires server endpoint confirmation)
2. Add credentials store (OS keystore or encrypted file) and cloud sign-in button skeleton
3. Polish UI status messages and add per-operation progress indicators

# Project TODO — The Brain v3

**Last updated:** 2026-02-15

This file tracks the current status and next steps for the GUI + CLI two-agent Ollama project.

## Completed (recent)
- Centralized Settings tab with model management and persona presets.
- Added persona-file selectors in Settings (loads file contents into Chat persona fields).
- Brain viewer and Wipe Brain action implemented.
- Live turn count and status updates in the Chat UI.
- Restored agent name fields (Ava / Orion) and persisted them.
- Thread-safety hardening: worker threads no longer update Tk widgets directly (uses queue/root.after).
- Timeout wrapper for Ollama calls to improve Stop responsiveness.

## Current / In Progress
- Full GUI manual testing and polish (smoke tests passing).
- Persisting persona-file selections (saved to `gui_config.json`) and loading on startup (done).

## Planned / Backlog
- Show installed models with metadata/size (requires server support).
- Add credentials store and cloud sign-in UI (OAuth/token flow).
- Add more automated tests and CI workflow.

## Next Actions (recommended)
1. Push recent commits to remote (if desired).
2. Manual GUI verification: test pulls, model refresh, persona-file loads, and wipe-brain.
3. Add unit/integration tests for the worker queue and model-fetch logic.

## How to Run Quick Smoke Test
1. Run the headless smoke test (simulates conversation without network):
```sh
python smoke_test.py
```

2. Or launch the GUI for interactive testing:
```sh
python gui_ollama_chat.py
```

## File References
- GUI: `gui_ollama_chat.py`
- CLI: `multi_ollama_chat.py`
- Personas: `personas.json`, `persona_ava_prompt.txt`, `persona_orion_prompt.txt`

---
End of TODO
