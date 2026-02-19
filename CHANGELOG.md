# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]
- Improve Send/Enter behavior: direct question starts a conversation or injects into a running session.
- Add interactive user-injection queue so typed messages go to agents during runs.
- Remove experimental `brain.py`/`brain.json` subsystem.
- Add README clarification about Send/Enter behavior.
- Add CI workflow to run headless smoke tests.

## [2026-02-19] v1.0.1
- UI: added "Ask A" and "Ask B" single-question buttons and animated per-agent waiting indicators.
- Made single-line input wider and placed the `From` sender field on the same line as the input.
- Non-blocking agent calls: Ask buttons now run model calls in background threads to keep the UI responsive.
- Memory controls moved into a dedicated memory row; "Merge final answer" checkbox moved into that row.
- Improved truncation and added a one-shot continuation attempt to reduce mid-sentence truncation.
- Removed the redundant "Open Final Window" button (final window auto-opens after live merge).

## [2026-02-15] v1.0.0
- Initial public release of The Brain v3 (local GUI + model management).
