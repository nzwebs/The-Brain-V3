# Smoke tests: [![Smoke tests](https://github.com/REDACTED/REPO/actions/workflows/smoke-tests.yml/badge.svg)](https://github.com/REDACTED/REPO/actions/workflows/smoke-tests.yml)

# Recent Improvements

- Settings tab model management menu rebuilt: now reliable and robust
- Model lists always update and display after refresh, pull, or remove
- Persistent log/status box: all errors, actions, and progress are visible and copyable
- Pull action shows progress and result in log/status and busy indicator
- Fixed: blank model lists after refresh (now always show status or models)
- Fixed: agent B model refresh hanging (now shows progress and errors)
- Fixed: NameError and widget initialization bugs in Settings tab
- Fixed: model management actions (pull/remove) always refresh lists and show feedback
- All fixes validated and working in GUI
 - Settings tab model management menu rebuilt: now reliable and robust
 - Model lists always update and display after refresh, pull, or remove
 - Added persona-file selectors in the Settings tab; selecting a persona file loads its contents into the Chat persona entries
 - Thread-safety hardening: worker threads (model fetch / conversation) schedule UI updates on the main thread; smoke tests pass
 - Persistent log/status box: all errors, actions, and progress are visible and copyable
 - Pull action shows progress and result in log/status and busy indicator
 - Fixed: blank model lists after refresh (now always show status or models)
 - Fixed: agent B model refresh hanging (now shows progress and errors)
 - Fixed: NameError and widget initialization bugs in Settings tab
 - Fixed: model management actions (pull/remove) always refresh lists and show feedback
 - All fixes validated and working in GUI

# The Brain v3 — Multi-Ollama Chat

Modern Python project for running and managing conversations between two Ollama servers, with both CLI and GUI interfaces.

## Project Structure

```
The Brain v3/
├── gui_config.json         # Persistent GUI settings
├── gui_ollama_chat.py      # Tkinter GUI for two-agent chat
├── multi_ollama_chat.py    # CLI for two-agent chat
├── personas.json           # Persona templates
├── requirements.txt        # Python dependencies
├── start.bat               # CLI launcher
├── start_gui.bat           # GUI launcher
├── start_gui_newwindow.bat # GUI launcher (new window)
├── start_gui_no_console.bat# GUI launcher (no console)
├── todo.md                 # Project TODOs
├── README.md               # This file
├── .gitignore              # Ignore Python/cache files
└── __pycache__/            # Python bytecode (ignored)
```

## Prerequisites

- Python 3.10+
- Ollama server(s) running and accessible at the configured URLs
 - `requests` is required for model pull/remove actions (added to `requirements.txt`)

## Installation

```sh
pip install -r requirements.txt
```

## Usage

### CLI

Run a conversation between two agents:

```sh
python multi_ollama_chat.py --topic "the benefits of remote work" --turns 4
```

Override endpoints/models with environment variables:

- `AGENT_A_URL`, `AGENT_A_MODEL`, `AGENT_A_NAME`
- `AGENT_B_URL`, `AGENT_B_MODEL`, `AGENT_B_NAME`

Example:

```sh
AGENT_B_URL="http://192.168.127.121:11434" AGENT_B_MODEL="llama2" python multi_ollama_chat.py
```

While running, type `stop` (or `q`/`quit`) and press Enter to end early.

Log the conversation:

```sh
python multi_ollama_chat.py --log chat_log.txt
```

### Personas and Reply Length

- `--persona-a` / `--persona-b`: set persona for each agent (or use env vars)
- `--max-chars N`: truncate replies
- `--short-turn`: force short replies

Example:


```sh
python multi_ollama_chat.py --humanize --greeting "Hello, how are you?" \
  --persona-a "soft-spoken" --persona-a-age 45 --persona-a-background "retired teacher who likes gardening" --persona-a-quirk "uses polite phrasing" \
  --persona-b "cheerful" --persona-b-age 28 --persona-b-background "startup developer" --persona-b-quirk "uses slang" \
  --short-turn --turns 10 --log chat_log.txt
```

Specify per-agent models:

- `--model-a NAME` and `--model-b NAME` let you choose the model served by each Ollama server (overrides `AGENT_A_MODEL` / `AGENT_B_MODEL` environment variables).

Example:

```powershell
python "multi_ollama_chat.py" --model-a "llama2" --model-b "llama2" --humanize --turns 10
```


### Optional Spelling Correction

If the `autocorrect` package is installed (default in requirements.txt), replies are lightly spell-checked. Remove it from requirements.txt to disable.

---


## GUI Features

- Modern, user-friendly interface for two-agent conversations
- Agent settings and runtime options at the top
- Tooltips for all options
- Tabbed interface: Chat and Settings
- Model management: pull, refresh, remove models per agent
- Auto-refresh of model lists and connectivity indicators at startup: When you launch the GUI, both agent model lists and server connectivity indicators are automatically refreshed. No manual action is needed; the lists and status dots update as soon as the application starts and whenever you change agent URLs.
- Real-time chat output
- Persistent configuration (auto-saved and loaded)

**All settings are saved on exit and restored on next launch.**

### Launch the GUI

```sh
python gui_ollama_chat.py
```

---

**Note:**
As of February 2026, the agent A and B online/offline status indicators are updated immediately at GUI startup (not just after a delay). This ensures the connectivity dots reflect the true server state as soon as the application launches.

For more, see code comments and the GUI Settings tab.

## Direct questions (how Send/Enter works)

- If you type text in the chat box and press **Send** or **Enter** while no conversation is running, the text will be used as the initial prompt (greeting) for the new conversation — equivalent to asking a single LLM question.
- If a conversation is already running, typing in the chat box and pressing **Send** will inject that text as a user message to both agents without modifying the greeting field — both agents will receive and answer the question in sequence.

This behavior lets you either start a focused Q&A (type a question then Send) or interrupt an ongoing multi-turn exchange with an injected question.

