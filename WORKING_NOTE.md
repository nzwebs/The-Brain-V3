Summary of current work — resume notes

Date: 2026-02-17

What I changed (key files):
- `gui_ollama_chat.py`
  - Added Stage-1 persistent brain: load/save `brain.json` and simple fact extraction.
  - Added Memory UI: `Enable Memory`, `View Memory`, `Clear Memory` buttons.
  - Facts extracted from user messages when `Enable Memory` is on; saved to `brain.json`.
  - Broadcasts memory updates into running conversations (memory-update payloads).
  - Per-turn relevance filtering: `_get_relevant_facts()` selects up to 4 relevant facts by keyword overlap and injects a short system note (`Relevant user facts: ...`) into model calls.
  - Added `_format_fact()` to present facts in friendlier phrases (e.g., "Name: Alex", "Lives in Seattle").

- `tools/test_memory.py`
  - Script to exercise fact extraction and print `brain.json` and memory summary.

- `tools/auto_memory_demo.py`
  - Automated demo that monkeypatches model calls (no network) to show message payloads and memory injection behavior.

Current runtime behavior / notes:
- Memory is opt-in via the "Enable Memory" checkbox; facts are recorded only when enabled at the time of sending.
- Facts persist in `brain.json` at the repo root. The viewer shows formatted facts (human-friendly).
- When conversation starts, a short memory summary is added to agents' system prompts.
- When a fact is added during a running conversation, a memory-update payload is enqueued and both agents receive a `system` note with the update immediately.
- Each model call receives a per-turn `system` note containing up to 4 relevant facts (keyword-overlap), not the whole brain.

How to resume / quick checks:
- Run the GUI:
  - `python gui_ollama_chat.py`
  - Enable `Enable Memory`, send statements like "My name is ...", click `View Memory` to inspect.
- Run unit demo (no network):
  - `python tools/test_memory.py` (adds sample facts and prints `brain.json`).
  - `python tools/auto_memory_demo.py` (starts a simulated conversation, injects a fact while running, prints model-call payloads to show injected memory).
- Inspect stored facts: `e:\The Brain v3\brain.json`.

Next recommended tasks (short-term, prioritized):
1) Prefer most recent value per kind (e.g., latest `name`) when summarizing facts — reduces duplicates.
2) Add optional agent confirmations for newly added facts (prompt tweak / small system message behavior).
3) Improve relevance retrieval with embeddings (advanced; optional later).
4) UI polish: tooltip wording, default memory setting, and opt-in reminder.
5) Add integration tests that run the demo scripts and verify `brain.json` updates.

If you'd like, I can implement task (1) now (prefer latest per kind) and then (2). Which do you want next?

Recent edits (2026-02-19):
- Added quick single-agent Ask buttons (`Ask A`, `Ask B`) and per-agent animated waiting indicators.
- Moved `From` sender field onto the same line as the send input and widened the input field.
- Ask calls are non-blocking (run in background threads) so the UI remains responsive.
- Memory controls moved into a dedicated memory row; `Merge final answer` checkbox moved there as well.
- Improved truncation logic to cut at word boundaries and added a single continuation attempt when replies appear truncated mid-sentence.
- Removed the separate "Open Final Window" button (live merge now auto-opens final window).