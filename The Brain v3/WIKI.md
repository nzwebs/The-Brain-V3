# The Brain v3 — Wiki

This repository's wiki content can be started here. You can copy this file into the GitHub Wiki or use it as documentation.

## Overview

- GUI: `gui_ollama_chat.py` — Tkinter frontend for two-agent Ollama chat and model management.
- CLI: `multi_ollama_chat.py` — command-line runner for two-agent conversations.

## How to ask direct questions

- Type your question into the chat input and press Send:
  - If no conversation is running, the text becomes the initial prompt.
  - If a conversation is running, the text is injected to both agents as a user message.

## Running smoke tests

Use `smoke_test.py` to run a headless validation locally. The GitHub Actions CI runs the same script.
