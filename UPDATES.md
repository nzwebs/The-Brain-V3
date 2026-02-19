# Updates — 2026-02-19

This file records the user-visible changes made on 2026-02-19.

## UI & Interaction
- Added quick single-agent ask buttons: `Ask A` and `Ask B` for one-shot queries.
- Per-agent animated waiting indicators while Ask calls run.
- Ask calls run in background threads to keep the GUI responsive.
- `From` sender field moved to the same line as the send input; input width increased.
- Memory controls consolidated into a dedicated memory row; `Merge final answer` checkbox moved there.
- Removed the separate "Open Final Window" button (final window auto-opens after live merge).

## Conversation behavior
- Improved truncation: replies are now clipped at word boundaries to avoid mid-word ellipses.
- Added a one-shot continuation attempt when a model's reply appears cut off mid-sentence.
- Injected user messages now include the sender name (if set) and a short memory summary as a system note so both agents receive the same real info as single-agent asks.
- Live-merge Phase 1 now includes sender and memory summary in the system prompt.

## Files changed
- `gui_ollama_chat.py`: UI layout, Ask A/B handlers, truncation and continuation logic, memory injection, removal of Open Final Window button.
- Docs updated: `CHANGELOG.md`, `README.md`, `WIKI.md`, `WORKING_NOTE.md`, `todo.md`.
- Created `UPDATES.md` (this file).

