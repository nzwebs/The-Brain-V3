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

## How to Test the GUI
1. Launch the GUI:
	```sh
	python gui_ollama_chat.py
	```
2. In "Ollama Settings" click `Refresh List`, select a model, then `Pull Selected → Both` and observe status messages
3. In Agent panes, tweak temperature / max tokens / top_p / stop and run a short conversation

## File References
- GUI: gui_ollama_chat.py
- CLI: multi_ollama_chat.py
- Personas: personas.json

## Best Practices
- Always update widgets from the main thread
- Pass correct widget reference to update functions

---
End of TODO
