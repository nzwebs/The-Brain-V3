# Project TODO — The Brain v3

**Last updated:** 2026-02-14

## Summary
This file tracks the implementation status and next steps for the GUI + CLI two-agent Ollama project.

---

## In Progress
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

## Current / In Progress
- Full GUI manual testing and polish (smoke tests passing).

## Planned / Backlog
- Show installed models with metadata/size (requires server support).
- Add credentials store and cloud sign-in UI (OAuth/token flow).
- Add more automated tests and CI workflow.

## Next Actions (recommended)
1. Push recent commits to remote (if desired).
2. Manual GUI verification: test pulls, model refresh, persona-file loads, and wipe-brain.
3. Add unit/integration tests for the worker queue and model-fetch logic.

Updates (2026-02-19):
- Documentation updated: `CHANGELOG.md`, `README.md`, `WIKI.md`, `WORKING_NOTE.md` reflect recent UI/behavior changes (Ask A/B, non-blocking calls, indicators, truncation improvements).
- Removed redundant "Open Final Window" button; final window auto-opens after live merge.

Next: commit and push the changes to the remote repository.

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
