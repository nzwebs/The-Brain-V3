#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui_ollama_chat.py - Tkinter GUI for managing and running two-agent Ollama conversations.
Restores the original feature set: per-agent URLs/models, model discovery, persona presets,
short-turn truncation, threaded conversation loop, and persistent config.
"""

from datetime import datetime
import json
import os
import queue
import threading
import time
import re
import sys
import traceback
import urllib.request
import urllib.error
from urllib.parse import urlparse
import socket

import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import requests

from multi_ollama_chat import chat_with_ollama

DEFAULT_PERSONAS_PATH = os.path.join(os.path.dirname(__file__), "personas.json")
DEFAULT_CONFIG = os.path.join(os.path.dirname(__file__), "gui_config.json")
import logging

# Module logger
logger = logging.getLogger(__name__)
if not logger.handlers:
    # Configure console + file logging at DEBUG for verbose diagnostics
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    try:
        fh = logging.FileHandler("gui_debug.log", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        logger.debug("Failed to create gui_debug.log file handler", exc_info=True)


class Tooltip:
    """Simple tooltip for Tkinter widgets."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _=None):
        if self.tipwindow:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 20
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(tw, text=self.text, background="#ffffe0", relief="solid", borderwidth=1)
        lbl.pack()

    def hide(self, _=None):
        if self.tipwindow:
            try:
                self.tipwindow.destroy()
            except tk.TclError as e:
                logger.debug("Tooltip.hide destroy failed: %s", e)
            self.tipwindow = None


class OllamaGUI:
    """Main GUI class for Ollama two-agent chat."""

    def _call_in_main(self, fn):
        """Run `fn` on the Tk main thread if possible, fall back safely."""
        try:
            self.root.after(0, fn)
        except (AttributeError, tk.TclError):
            fn()

    def _set_widget_value(self, entry, val):
        """Set a widget or variable value safely, ignore UI errors."""
        try:
            if isinstance(entry, ttk.Entry):
                entry.delete(0, tk.END)
                entry.insert(0, val)
            else:
                entry.set(val)
        except (AttributeError, tk.TclError) as e:
            logger.debug("_set_widget_value failed: %s", e)

    def _safe_set_button_state(self, button, state):
        """Safely set a Tk button state from any thread."""
        try:
            try:
                self._call_in_main(lambda: button.config(state=state))
            except (AttributeError, tk.TclError):
                button.config(state=state)
        except (AttributeError, tk.TclError) as e:
            logger.debug("_safe_set_button_state failed: %s", e)

    def _safe_update_models_text(self, agent, values):
        """Safely update models text widget from worker threads."""
        try:
            try:
                self._call_in_main(lambda: self._update_models_text(agent, values))
            except (AttributeError, tk.TclError):
                self._update_models_text(agent, values)
        except (AttributeError, tk.TclError) as e:
            logger.debug("_safe_update_models_text failed: %s", e)

    def _safe_messagebox(self, fn, title, msg):
        """Safely show a messagebox (fn is messagebox.showinfo/showerror)."""
        try:
            try:
                self._call_in_main(lambda: fn(title, msg))
            except (AttributeError, tk.TclError):
                fn(title, msg)
        except (AttributeError, tk.TclError) as e:
            logger.debug("_safe_messagebox failed: %s", e)

    def _on_send(self):
        # If there is text in the user input, use it as the greeting for the conversation.
        try:
            txt = self.user_input.get().strip()
        except (AttributeError, tk.TclError):
            txt = ""

        # Lightweight debug log
        try:
            with open("send_debug.log", "a", encoding="utf-8") as df:
                df.write(f"[{datetime.now().isoformat()}] _on_send called; txt={repr(txt)}\n")
        except OSError as e:
            logger.debug("_on_send: failed to write send_debug.log: %s", e)

        if not txt:
            try:
                self.start()
            except (TypeError, tk.TclError) as e:
                logger.debug("_on_send: start() failed: %s", e)
            return

        # Determine if a conversation thread is running
        thread_alive = False
        try:
            t = getattr(self, "thread", None)
            thread_alive = bool(t and t.is_alive())
        except AttributeError:
            thread_alive = False

        try:
            with open("send_debug.log", "a", encoding="utf-8") as df:
                df.write(f"[{datetime.now().isoformat()}] thread_alive={thread_alive}\n")
        except OSError as e:
            logger.debug("_on_send: failed to write thread_alive to send_debug.log: %s", e)

        # If the Start button appears disabled, consider the thread running
        try:
            if not thread_alive and hasattr(self, "start_btn") and self.start_btn is not None:
                try:
                    thread_alive = str(self.start_btn["state"]).lower() == "disabled"
                except (tk.TclError, AttributeError, KeyError) as e:
                    logger.debug("_on_send: checking start_btn state failed: %s", e)
        except (AttributeError, tk.TclError):
            logger.debug("_on_send: start_btn state check outer failed")

        if thread_alive:
            # ensure inbound queue exists
            try:
                if not hasattr(self, "to_worker_queue") or getattr(self, "to_worker_queue", None) is None:
                    self.to_worker_queue = queue.Queue()
            except AttributeError as e:
                logger.debug("_on_send: to_worker_queue init failed: %s", e)

            try:
                if self.to_worker_queue is not None:
                    try:
                        self.to_worker_queue.put(txt)
                    except (AttributeError, queue.Full) as e:
                        logger.debug("_on_send: to_worker_queue.put failed: %s", e)
                try:
                    self.queue.put(("user", txt))
                except (AttributeError, queue.Full) as e:
                    logger.debug("_on_send: self.queue.put failed: %s", e)
                try:
                    injected_msg = (
                        f"[{datetime.now().isoformat()}] action=injected "
                        f"txt={repr(txt)}\n"
                    )
                    with open("send_debug.log", "a", encoding="utf-8") as df:
                        df.write(injected_msg)
                except OSError as e:
                    logger.debug("_on_send: failed to append injected_msg to send_debug.log: %s", e)
            finally:
                try:
                    self.user_input.delete(0, tk.END)
                except (AttributeError, tk.TclError):
                    pass
            return

        # If no thread running, start a conversation with this greeting
        try:
            try:
                start_msg = (
                    f"[{datetime.now().isoformat()}] action=start_with_greeting "
                    f"txt={repr(txt)}\n"
                )
                with open("send_debug.log", "a", encoding="utf-8") as df:
                    df.write(start_msg)
            except OSError as e:
                logger.debug("thread worker: failed to write thread_error.log: %s", e)
            try:
                self.start(greeting=txt)
            except TypeError:
                try:
                    self.start()
                except (TypeError, tk.TclError, AttributeError):
                    pass
        finally:
            try:
                self.user_input.delete(0, tk.END)
            except (AttributeError, tk.TclError):
                pass

    def _on_stop(self):
        self.stop()

    def _clear_chat(self):
        self.chat_text.config(state="normal")
        self.chat_text.delete("1.0", "end")
        self.chat_text.insert("end", "Welcome to Ollama Two-Agent Chat!\n")
        self.chat_text.config(state="disabled")

    def _check_model_status(self, url, model, status_label):
        # Non-blocking check of a specific model on a server; updates status_label.
        def worker():
            try:
                if not url or not model:
                    try:
                        self.root.after(0, lambda: status_label.config(text="●", foreground="gray"))
                    except tk.TclError:
                        pass
                    return
                # Prefer fetching the model list and checking membership to avoid
                # servers that do not implement /v1/models/{model} (which may 404).
                list_url = url.rstrip("/") + "/v1/models"
                data = None
                attempts = []
                # Use requests with a small retry/backoff loop to reduce transient failures
                for attempt in range(3):
                    try:
                        attempts.append(f"GET {list_url} (attempt {attempt+1})")
                        resp = requests.get(list_url, timeout=3)
                        resp.raise_for_status()
                        try:
                            data = resp.json()
                        except Exception:
                            # fall back to raw text parsing
                            txt = resp.text or ""
                            if "\n" in txt:
                                data = [l.strip() for l in txt.splitlines() if l.strip()]
                            else:
                                data = None
                        break
                    except requests.RequestException as e:
                        logger.debug("_check_model_status: requests.get failed (%s): %s", list_url, e)
                        # small backoff
                        try:
                            time.sleep(0.5 * (2 ** attempt))
                        except Exception:
                            pass
                found = False
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            name = item.get("name") or item.get("model") or item.get("id")
                            if name == model:
                                found = True
                                break
                        else:
                            if str(item) == model:
                                found = True
                                break
                elif isinstance(data, dict):
                    # try common keys
                    for key in ("models", "results", "data"):
                        if key in data and isinstance(data[key], list):
                            for item in data[key]:
                                if isinstance(item, dict):
                                    n = item.get("name") or item.get("model") or item.get("id")
                                    if n == model:
                                        found = True
                                        break
                                else:
                                    if str(item) == model:
                                        found = True
                                        break
                            if found:
                                break
                if found:
                    try:
                        self.root.after(0, lambda: status_label.config(text="●", foreground="green"))
                    except tk.TclError as e:
                        logger.debug("_check_model_status: status_label update failed: %s", e)
                    return
            except (urllib.error.URLError, OSError, ValueError) as e:
                logger.debug("_check_model_status: request failed for %s %s: %s", url, model, e)
            try:
                self.root.after(0, lambda: status_label.config(text="●", foreground="red"))
            except tk.TclError as e:
                logger.debug("_check_model_status: status_label update failed: %s", e)

        try:
            threading.Thread(target=worker, daemon=True).start()
        except (RuntimeError, tk.TclError, AttributeError) as e:
            logger.debug("_check_model_status: failed to start worker: %s", e)

    def _check_server_status(self, url, status_label):
        def worker():
            try:
                req = urllib.request.Request(url.rstrip("/") + "/v1/models")
                # give server a few seconds to respond when checking status
                with urllib.request.urlopen(req, timeout=3) as resp:
                    if resp.status == 200:
                        try:
                            self.root.after(
                                0,
                                lambda: status_label.config(text="●", foreground="green"),
                            )
                        except tk.TclError:
                            pass
                        return
            except (urllib.error.URLError, OSError):
                logger.debug("_check_server_status: request failed for %s", url)
            try:
                self.root.after(0, lambda: status_label.config(text="●", foreground="red"))
            except tk.TclError as e:
                logger.debug("_check_server_status: status_label update failed: %s", e)

        threading.Thread(target=worker, daemon=True).start()

    def __init__(self, root):
        self.root = root
        root.title("Ollama Two-Agent Chat")
        self.queue = queue.Queue()
        # recent urls stored in memory, persisted on save
        self._recent_urls = {"a": [], "b": []}
        # --- Notebook and Tabs ---
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True)
        self.chat_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.chat_tab, text="Chat")
        self.settings_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.settings_tab, text="Settings")
        # Continue with rest of initialization
        self.thread = None
        self.stop_event = threading.Event()
        self._poll_queue()
        self._apply_theme("Dark")
        # Immediately poll connectivity after widgets are created
        self.root.after(200, self._poll_connectivity)
        self._models_info = {"a_settings": {}, "b_settings": {}}
        # initialize commonly-set GUI attributes to satisfy linters
        self.to_worker_queue = None
        self._model_status_log = []
        self.formatting_var = tk.StringVar(value="Plain")
        self.model_busy_var = tk.StringVar(value="")  # Use StringVar for status messages
        self.model_busy_label = None
        self.a_model_list = None
        self.a_model_entry = None
        self.refresh_a_btn = None
        self.pull_a_btn = None
        self.remove_a_btn = None
        self.b_model_list = None
        self.b_model_entry = None
        self.refresh_b_btn = None
        self.pull_b_btn = None
        self.remove_b_btn = None
        self.pull_both_btn = None
        self.model_details_text = None
        self.copy_all_btn = None
        self.pull_progress = None
        self.pull_progress_label = None
        self.cancel_pull_var = tk.BooleanVar(value=False)
        self.cancel_pull_btn = None
        self.a_api_path = None
        self.b_api_path = None
        self.persona_presets = {}
        self.a_persona_file_settings = None
        self.b_persona_file_settings = None
        self.start_btn = None
        # model refresh will be scheduled after UI widgets are initialized

    def _auto_select_first_model(self, agent):
        if agent == "a":
            if self.a_model_list is not None and self.a_model_list.size() > 0:
                self.a_model_list.selection_clear(0, "end")
                self.a_model_list.selection_set(0)
                self._show_model_details("a")
        elif agent == "b":
            if self.b_model_list is not None and self.b_model_list.size() > 0:
                self.b_model_list.selection_clear(0, "end")
                self.b_model_list.selection_set(0)
                self._show_model_details("b")
        # Restore model auto-refresh on URL change after widgets are created

        # --- Theme Application ---

    def _apply_theme(self, theme):
        style = ttk.Style()
        # Use default theme (vista/win10/clam)
        try:
            style.theme_use("vista")
        except tk.TclError:
            try:
                style.theme_use("xpnative")
            except tk.TclError:
                style.theme_use("clam")
        style.configure(".", background="SystemButtonFace", foreground="black")
        style.configure("TLabel", background="SystemButtonFace", foreground="black")
        style.configure("TFrame", background="SystemButtonFace")
        style.configure("TNotebook", background="SystemButtonFace")
        style.configure("TNotebook.Tab", background="SystemButtonFace", foreground="black")
        style.configure("TEntry", fieldbackground="white", foreground="black")
        style.configure("TCombobox", fieldbackground="white", foreground="black")
        style.configure("TButton", background="SystemButtonFace", foreground="black")

        # --- Agent Settings ---

        agent_frame = ttk.LabelFrame(self.chat_tab, text="Agent Settings")
        agent_frame.pack(fill="x", padx=16, pady=(12, 4), anchor="n")

        # Agent A controls
        ttk.Label(agent_frame, text="Agent A URL:").grid(
            row=0, column=0, sticky="w", padx=(0, 6), pady=6
        )
        self.a_url = ttk.Combobox(agent_frame, width=36, values=[])
        self.a_url.grid(row=0, column=1, sticky="w", pady=6)
        # Persist URLs when user edits them (focus-out or Enter)
        try:
            self.a_url.bind("<FocusOut>", lambda e: self.save_config())
            self.a_url.bind("<Return>", lambda e: self.save_config())
        except (AttributeError, tk.TclError) as e:
            logger.debug("a_url.bind failed: %s", e)
        self.a_manage_btn = ttk.Button(
            agent_frame, text="Manage", width=6, command=lambda: self._manage_urls("a")
        )
        self.a_manage_btn.grid(row=0, column=2, sticky="w", padx=(6, 0), pady=6)
        ttk.Label(agent_frame, text="Model:").grid(
            row=0, column=2, sticky="w", padx=(12, 6), pady=6
        )
        self.a_model = ttk.Combobox(agent_frame, width=24, values=[])
        self.a_model.grid(row=0, column=3, sticky="w", pady=6)
        self.a_model_status = ttk.Label(agent_frame, text="●", foreground="gray")
        self.a_model_status.grid(row=0, column=4, padx=6, pady=6)
        self.a_refresh_btn = ttk.Button(
            agent_frame,
            text="↻",
            width=3,
            command=lambda: (
                self.save_config(),
                self._fetch_models(
                    self.a_url.get().strip(),
                    self.a_model,
                    self.a_refresh_btn,
                    self.a_model_status,
                    None,
                ),
            ),
        )
        self.a_refresh_btn.grid(row=0, column=5, padx=6, pady=6)
        ttk.Label(agent_frame, text="Preset:").grid(
            row=0, column=6, sticky="w", padx=(12, 6), pady=6
        )
        self.a_preset = ttk.Combobox(agent_frame, width=20, values=[])
        self.a_preset.grid(row=0, column=7, sticky="w", pady=6)
        self.a_preset.bind(
            "<<ComboboxSelected>>",
            lambda e: self._apply_preset(
                self.a_preset.get(), self.a_age, self.a_quirk, self.a_persona
            ),
        )
        ttk.Label(agent_frame, text="Persona:").grid(
            row=1, column=0, sticky="w", padx=(0, 6), pady=6
        )
        self.a_persona = ttk.Entry(agent_frame, width=36)
        self.a_persona.grid(row=1, column=1, sticky="w", pady=6)
        # persona file selector moved to Settings tab
        ttk.Label(agent_frame, text="Name:").grid(row=1, column=6, sticky="w", padx=(12, 6), pady=6)
        self.a_name = ttk.Entry(agent_frame, width=12)
        self.a_name.grid(row=1, column=7, sticky="w", pady=6)
        ttk.Label(agent_frame, text="Age:").grid(row=1, column=2, sticky="w", padx=(12, 6), pady=6)
        self.a_age = ttk.Entry(agent_frame, width=12)
        self.a_age.grid(row=1, column=3, sticky="w", pady=6)
        ttk.Label(agent_frame, text="Quirk:").grid(
            row=1, column=4, sticky="w", padx=(12, 6), pady=6
        )
        # Gather all unique quirks from persona presets and add more
        extra_quirks = [
            "sarcastic",
            "mysterious",
            "hyper-logical",
            "minimalist",
            "storyteller",
            "humorous",
            "cryptic",
            "mentor-like",
            "philosophical",
            "AI expert",
            "hacker mindset",
            "playful",
            "visionary",
            "skeptical",
            "empathetic",
            "teacherly",
            "provocative",
            "zen",
            "repetitive",
            "random",
            "detailed",
        ]
        try:
            with open(DEFAULT_PERSONAS_PATH, "r", encoding="utf-8") as f:
                persona_data = json.load(f)
            quirks = set(v.get("quirk", "") for v in persona_data.values() if v.get("quirk"))
        except (OSError, json.JSONDecodeError, ValueError):
            quirks = set()
        quirks.update(extra_quirks)
        quirk_list = sorted(q for q in quirks if q)
        self.a_quirk = ttk.Combobox(agent_frame, width=20, values=quirk_list)
        self.a_quirk.grid(row=1, column=5, sticky="w", pady=6)
        self.a_quirk.set("")

        # Last-used endpoint label
        try:
            self.last_endpoint_var = tk.StringVar(value="")
            self.last_endpoint_label = ttk.Label(agent_frame, textvariable=self.last_endpoint_var, foreground="#555")
            self.last_endpoint_label.grid(row=2, column=0, columnspan=8, sticky="w", pady=(6, 0))
        except Exception:
            self.last_endpoint_var = None
            self.last_endpoint_label = None
        # Agent B controls
        ttk.Label(agent_frame, text="Agent B URL:").grid(
            row=2, column=0, sticky="w", padx=(0, 6), pady=6
        )
        self.b_url = ttk.Combobox(agent_frame, width=36, values=[])
        self.b_url.grid(row=2, column=1, sticky="w", pady=6)
        try:
            self.b_url.bind("<FocusOut>", lambda e: self.save_config())
            self.b_url.bind("<Return>", lambda e: self.save_config())
        except (AttributeError, tk.TclError) as e:
            logger.debug("b_url.bind failed: %s", e)
        self.b_manage_btn = ttk.Button(
            agent_frame, text="Manage", width=6, command=lambda: self._manage_urls("b")
        )
        self.b_manage_btn.grid(row=2, column=2, sticky="w", padx=(6, 0), pady=6)
        ttk.Label(agent_frame, text="Model:").grid(
            row=2, column=2, sticky="w", padx=(12, 6), pady=6
        )
        self.b_model = ttk.Combobox(agent_frame, width=24, values=[])
        self.b_model.grid(row=2, column=3, sticky="w", pady=6)
        self.b_model_status = ttk.Label(agent_frame, text="●", foreground="gray")
        self.b_model_status.grid(row=2, column=4, padx=6, pady=6)
        self.b_refresh_btn = ttk.Button(
            agent_frame,
            text="↻",
            width=3,
            command=lambda: (
                self.save_config(),
                self._fetch_models(
                    self.b_url.get().strip(),
                    self.b_model,
                    self.b_refresh_btn,
                    self.b_model_status,
                    None,
                ),
            ),
        )
        self.b_refresh_btn.grid(row=2, column=5, padx=6, pady=6)
        ttk.Label(agent_frame, text="Preset:").grid(
            row=2, column=6, sticky="w", padx=(12, 6), pady=6
        )
        self.b_preset = ttk.Combobox(agent_frame, width=20, values=[])
        self.b_preset.grid(row=2, column=7, sticky="w", pady=6)
        self.b_preset.bind(
            "<<ComboboxSelected>>",
            lambda e: self._apply_preset(
                self.b_preset.get(), self.b_age, self.b_quirk, self.b_persona
            ),
        )
        ttk.Label(agent_frame, text="Persona:").grid(
            row=3, column=0, sticky="w", padx=(0, 6), pady=6
        )
        self.b_persona = ttk.Entry(agent_frame, width=36)
        self.b_persona.grid(row=3, column=1, sticky="w", pady=6)
        # persona file selector moved to Settings tab
        ttk.Label(agent_frame, text="Name:").grid(row=3, column=6, sticky="w", padx=(12, 6), pady=6)
        self.b_name = ttk.Entry(agent_frame, width=12)
        self.b_name.grid(row=3, column=7, sticky="w", pady=6)
        ttk.Label(agent_frame, text="Age:").grid(row=3, column=2, sticky="w", padx=(12, 6), pady=6)
        self.b_age = ttk.Entry(agent_frame, width=12)
        self.b_age.grid(row=3, column=3, sticky="w", pady=6)
        ttk.Label(agent_frame, text="Quirk:").grid(
            row=3, column=4, sticky="w", padx=(12, 6), pady=6
        )
        self.b_quirk = ttk.Combobox(agent_frame, width=20, values=quirk_list)
        self.b_quirk.grid(row=3, column=5, sticky="w", pady=6)
        self.b_quirk.set("")

        # --- Separator ---
        ttk.Separator(self.chat_tab, orient="horizontal").pack(fill="x", padx=6, pady=6)

        # --- Runtime Options ---
        runtime_frame = ttk.LabelFrame(self.chat_tab, text="Runtime Options")
        runtime_frame.pack(fill="x", padx=6, pady=(0, 6), anchor="n")
        # ... (runtime options code remains unchanged) ...

        # --- Chat Output ---
        chat_frame = ttk.Frame(self.chat_tab)
        chat_frame.pack(fill="both", expand=True, padx=6, pady=6)
        self.chat_text = ScrolledText(chat_frame, wrap="word", height=20, state="normal")
        self.chat_text.pack(fill="both", expand=True)
        self.chat_text.insert("end", "Welcome to Ollama Two-Agent Chat!\n")
        self.chat_text.config(state="disabled")

        # --- Chat Controls ---
        controls_frame = ttk.Frame(self.chat_tab)
        controls_frame.pack(fill="x", padx=6, pady=(0, 6))
        self.user_input = ttk.Entry(controls_frame)
        self.user_input.pack(side="left", fill="x", expand=True, padx=(0, 6))
        try:
            self.user_input.bind("<Return>", lambda e: self._on_send())
        except (AttributeError, tk.TclError) as e:
            logger.debug("user_input.bind failed: %s", e)
        self.send_btn = ttk.Button(controls_frame, text="Send", command=self._on_send)
        self.send_btn.pack(side="left")
        self.stop_btn = ttk.Button(controls_frame, text="Stop", command=self._on_stop)
        self.stop_btn.pack(side="left", padx=(6, 0))
        self.clear_btn = ttk.Button(controls_frame, text="Clear Chat", command=self._clear_chat)
        self.clear_btn.pack(side="left", padx=(6, 0))

        # Chat-tab compact connection indicators (Agent A / Agent B)
        models_frame = ttk.Frame(controls_frame)
        models_frame.pack(side="right", padx=(6, 0))
        ttk.Label(models_frame, text="A").grid(row=0, column=0, sticky="e")
        self.a_status_dot = ttk.Label(models_frame, text="●", foreground="gray")
        self.a_status_dot.grid(row=0, column=1, padx=(6, 8))
        ttk.Label(models_frame, text="B").grid(row=1, column=0, sticky="e")
        self.b_status_dot = ttk.Label(models_frame, text="●", foreground="gray")
        self.b_status_dot.grid(row=1, column=1, padx=(6, 8))

        # --- Status Bar with Turn Count ---
        self.status_var = tk.StringVar(value="Ready.")
        self.turn_count_var = tk.StringVar(value="")
        status_frame = ttk.Frame(self.chat_tab)
        status_frame.pack(fill="x", side="bottom", padx=0, pady=(0, 0))
        status_label = ttk.Label(
            status_frame, textvariable=self.status_var, anchor="w", relief="sunken"
        )
        status_label.pack(side="left", fill="x", expand=True)
        turn_label = ttk.Label(
            status_frame,
            textvariable=self.turn_count_var,
            anchor="e",
            relief="sunken",
            width=12,
        )
        turn_label.pack(side="right")

        # Model management controls (pull/refresh/remove) moved to Settings tab

        # Runtime controls (temperature, max tokens, top_p, stop, stream)
        runtime_frame = ttk.LabelFrame(self.chat_tab, text="Runtime Options")
        runtime_frame.pack(fill="x", padx=6, pady=(0, 6))
        # common tooltip texts (kept short per-line to satisfy linters)
        temp_tip = (
            "Temperature: Controls randomness. Higher values = more creative, "
            "lower = more focused."
        )
        max_tokens_tip = (
            "Max Tokens: Maximum number of tokens (words/pieces) the model can generate "
            "in a response."
        )
        top_p_tip = (
            "Top-p: Nucleus sampling. Lower values = more focused, "
            "higher = more random."
        )
        stop_tip = (
            "Stop: Comma-separated list of tokens. Model will stop generating if any are "
            "produced."
        )
        stream_tip = (
            "Stream: If enabled, model output appears as it is generated (faster feedback)."
        )
        # --- Agent A runtime options with tooltips ---
        a_temp_label = ttk.Label(runtime_frame, text="A Temp:")
        a_temp_label.grid(row=0, column=0, sticky="w")
        self.a_temp = tk.DoubleVar(value=0.7)
        a_temp_spin = ttk.Spinbox(
            runtime_frame,
            from_=0.0,
            to=2.0,
            increment=0.01,
            textvariable=self.a_temp,
            width=6,
        )
        a_temp_spin.grid(row=0, column=1)
        Tooltip(a_temp_label, temp_tip)
        Tooltip(a_temp_spin, temp_tip)

        a_max_tokens_label = ttk.Label(runtime_frame, text="A Max Tokens:")
        a_max_tokens_label.grid(row=0, column=2, sticky="w")
        self.a_max_tokens = tk.IntVar(value=512)
        a_max_tokens_spin = ttk.Spinbox(
            runtime_frame, from_=1, to=4096, textvariable=self.a_max_tokens, width=7
        )
        a_max_tokens_spin.grid(row=0, column=3)
        Tooltip(a_max_tokens_label, max_tokens_tip)
        Tooltip(a_max_tokens_spin, max_tokens_tip)

        a_top_p_label = ttk.Label(runtime_frame, text="A Top-p:")
        a_top_p_label.grid(row=0, column=4, sticky="w")
        self.a_top_p = tk.DoubleVar(value=1.0)
        a_top_p_spin = ttk.Spinbox(
            runtime_frame,
            from_=0.0,
            to=1.0,
            increment=0.01,
            textvariable=self.a_top_p,
            width=6,
        )
        a_top_p_spin.grid(row=0, column=5)
        Tooltip(a_top_p_label, top_p_tip)
        Tooltip(a_top_p_spin, top_p_tip)

        a_stop_label = ttk.Label(runtime_frame, text="A Stop:")
        a_stop_label.grid(row=0, column=6, sticky="w")
        self.a_stop = ttk.Entry(runtime_frame, width=12)
        self.a_stop.grid(row=0, column=7)
        Tooltip(a_stop_label, stop_tip)
        Tooltip(self.a_stop, stop_tip)

        self.a_stream = tk.BooleanVar(value=False)
        a_stream_btn = ttk.Checkbutton(runtime_frame, text="A Stream", variable=self.a_stream)
        a_stream_btn.grid(row=0, column=8, padx=4)
        Tooltip(a_stream_btn, stream_tip)

        # --- Agent B runtime options with tooltips ---
        b_temp_label = ttk.Label(runtime_frame, text="B Temp:")
        b_temp_label.grid(row=1, column=0, sticky="w")
        self.b_temp = tk.DoubleVar(value=0.7)
        b_temp_spin = ttk.Spinbox(
            runtime_frame,
            from_=0.0,
            to=2.0,
            increment=0.01,
            textvariable=self.b_temp,
            width=6,
        )
        b_temp_spin.grid(row=1, column=1)
        Tooltip(b_temp_label, temp_tip)
        Tooltip(b_temp_spin, temp_tip)

        b_max_tokens_label = ttk.Label(runtime_frame, text="B Max Tokens:")
        b_max_tokens_label.grid(row=1, column=2, sticky="w")
        self.b_max_tokens = tk.IntVar(value=512)
        b_max_tokens_spin = ttk.Spinbox(
            runtime_frame, from_=1, to=4096, textvariable=self.b_max_tokens, width=7
        )
        b_max_tokens_spin.grid(row=1, column=3)
        Tooltip(b_max_tokens_label, max_tokens_tip)
        Tooltip(b_max_tokens_spin, max_tokens_tip)

        b_top_p_label = ttk.Label(runtime_frame, text="B Top-p:")
        b_top_p_label.grid(row=1, column=4, sticky="w")
        self.b_top_p = tk.DoubleVar(value=1.0)
        b_top_p_spin = ttk.Spinbox(
            runtime_frame,
            from_=0.0,
            to=1.0,
            increment=0.01,
            textvariable=self.b_top_p,
            width=6,
        )
        b_top_p_spin.grid(row=1, column=5)
        Tooltip(b_top_p_label, top_p_tip)
        Tooltip(b_top_p_spin, top_p_tip)

        b_stop_label = ttk.Label(runtime_frame, text="B Stop:")
        b_stop_label.grid(row=1, column=6, sticky="w")
        self.b_stop = ttk.Entry(runtime_frame, width=12)
        self.b_stop.grid(row=1, column=7)
        Tooltip(
            b_stop_label,
            "Stop: Comma-separated list of tokens. Model will stop generating if any are produced.",
        )
        Tooltip(
            self.b_stop,
            "Stop: Comma-separated list of tokens. Model will stop generating if any are produced.",
        )

        self.b_stream = tk.BooleanVar(value=False)
        b_stream_btn = ttk.Checkbutton(runtime_frame, text="B Stream", variable=self.b_stream)
        b_stream_btn.grid(row=1, column=8, padx=4)
        Tooltip(
            b_stream_btn,
            "Stream: If enabled, model output appears as it is generated (faster feedback).",
        )

        ctrl_frame = ttk.Frame(self.chat_tab)
        ctrl_frame.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Label(ctrl_frame, text="Topic").grid(row=0, column=0, sticky="w")
        self.topic = ttk.Entry(ctrl_frame, width=40)
        self.topic.insert(0, "the benefits of remote work")
        self.topic.grid(row=0, column=1, sticky="w")
        self.clear_topic_btn = ttk.Button(
            ctrl_frame, text="Clear Topic", command=lambda: self.topic.delete(0, "end")
        )
        self.clear_topic_btn.grid(row=0, column=1, sticky="e", padx=(0, 2))
        ttk.Label(ctrl_frame, text="Turns").grid(row=0, column=2, sticky="w")
        self.turns = tk.IntVar(value=10)
        ttk.Spinbox(ctrl_frame, from_=1, to=1000, textvariable=self.turns, width=5).grid(
            row=0, column=3
        )
        ttk.Label(ctrl_frame, text="Delay(s)").grid(row=0, column=4, sticky="w")
        self.delay = tk.DoubleVar(value=1.0)
        ttk.Spinbox(
            ctrl_frame,
            from_=0.0,
            to=60.0,
            increment=0.1,
            textvariable=self.delay,
            width=6,
        ).grid(row=0, column=5)
        self.humanize_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl_frame, text="Humanize", variable=self.humanize_var).grid(
            row=0, column=6, padx=6
        )
        ttk.Label(ctrl_frame, text="Greeting").grid(row=1, column=0, sticky="w")
        self.greeting = ttk.Entry(ctrl_frame, width=40)
        self.greeting.grid(row=1, column=1, sticky="w")
        ttk.Label(ctrl_frame, text="Max chars A").grid(row=1, column=2, sticky="w")
        self.max_chars_a = tk.IntVar(value=120)
        ttk.Spinbox(ctrl_frame, from_=0, to=10000, textvariable=self.max_chars_a, width=7).grid(
            row=1, column=3
        )
        # Place Max chars B on the same line as Max chars A
        ttk.Label(ctrl_frame, text="Max chars B").grid(row=1, column=4, sticky="w")
        self.max_chars_b = tk.IntVar(value=120)
        ttk.Spinbox(ctrl_frame, from_=0, to=10000, textvariable=self.max_chars_b, width=7).grid(
            row=1, column=5
        )
        # Move short-turn and log options to the next row to avoid overlap
        self.short_turn_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(ctrl_frame, text="Short-turn", variable=self.short_turn_var).grid(
            row=2, column=2, padx=6
        )
        self.log_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl_frame, text="Log to file", variable=self.log_var).grid(
            row=2, column=3, padx=6
        )
        self.log_path = ttk.Entry(ctrl_frame, width=30)
        self.log_path.insert(0, "")
        self.log_path.grid(row=2, column=4, sticky="w")
        self.close_on_exit_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            ctrl_frame, text="Close terminal on exit", variable=self.close_on_exit_var
        ).grid(row=2, column=5, padx=6)
        # Place run controls grouped to the right of the same row as max chars
        self.start_btn = ttk.Button(ctrl_frame, text="Start", command=self.start)
        self.start_btn.grid(row=1, column=6, padx=6)
        self.stop_btn = ttk.Button(ctrl_frame, text="Stop", command=self.stop, state="disabled")
        self.stop_btn.grid(row=1, column=7, padx=6)
        self.reset_btn = ttk.Button(ctrl_frame, text="Reset Defaults", command=self.reset_defaults)
        self.reset_btn.grid(row=1, column=8, padx=6)
        # Save & Exit button
        self.save_exit_btn = ttk.Button(
            ctrl_frame, text="Save && Exit", command=self._save_and_exit
        )
        self.save_exit_btn.grid(row=2, column=8, padx=6)

        self._model_status_log = []
        self._init_settings_tab()
        # Schedule model refreshes after settings tab is created
        try:
            self.root.after(100, self._refresh_a_models)
            self.root.after(200, self._refresh_b_models)
        except (AttributeError, tk.TclError) as e:
            logger.debug("scheduling model refresh failed: %s", e)
        # Load persona presets and populate preset selectors
        try:
            self.load_personas()
            preset_names = list(self.persona_presets.keys())
            try:
                if hasattr(self, "a_preset"):
                    self.a_preset["values"] = preset_names
                if hasattr(self, "b_preset"):
                    self.b_preset["values"] = preset_names
                if preset_names:
                    try:
                        self.a_preset.set(preset_names[0])
                    except (tk.TclError, AttributeError):
                        pass
                    try:
                        self.b_preset.set(preset_names[0])
                    except (tk.TclError, AttributeError):
                        pass
            except (AttributeError, KeyError, TypeError):
                pass
        except (OSError, json.JSONDecodeError, AttributeError, KeyError, TypeError, tk.TclError):
            pass

    def _init_settings_tab(self):
        # Clear and rebuild the Settings tab model management menu
        for widget in self.settings_tab.winfo_children():
            widget.destroy()
        st = ttk.Frame(self.settings_tab)
        st.pack(fill="both", expand=True, padx=12, pady=12)
        ttk.Label(st, text="Chat Output Formatting:").grid(
            row=0, column=0, sticky="w", padx=6, pady=4
        )
        self.formatting_var = tk.StringVar(value="plain")
        formatting_options = [
            ("plain", "Plain Text: No formatting, just text."),
            ("markdown", "Markdown: Supports *bold*, _italic_, code, lists, and more."),
            ("raw", "Raw Model Output: Shows exactly what the model returns."),
        ]
        row = 1
        for val, desc in formatting_options:
            rb = ttk.Radiobutton(st, text=val.capitalize(), variable=self.formatting_var, value=val)
            rb.grid(row=row, column=0, sticky="w", padx=12)
            ttk.Label(st, text=desc, wraplength=400, foreground="#555").grid(
                row=row, column=1, sticky="w", padx=4
            )
            row += 1

        # --- Persona Presets (moved here previously) ---
        persona_frame = ttk.LabelFrame(self.settings_tab, text="Personas")
        persona_frame.pack(fill="x", padx=6, pady=(12, 6))
        ttk.Label(persona_frame, text="Persona controls are available in the Chat tab.").grid(
            row=0, column=0, sticky="w", padx=4, pady=4
        )

        model_mgmt = ttk.LabelFrame(self.settings_tab, text="Model Management")
        model_mgmt.pack(fill="x", padx=6, pady=(12, 6))

        self.model_busy_var = tk.StringVar(value="")
        self.model_busy_label = ttk.Label(
            model_mgmt, textvariable=self.model_busy_var, foreground="blue"
        )
        self.model_busy_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))

        ttk.Label(model_mgmt, text="Agent A Models:").grid(row=1, column=0, sticky="w")
        self.a_model_list = tk.Listbox(model_mgmt, width=32, height=6)
        self.a_model_list.grid(row=2, column=0, sticky="w", padx=2)
        self.a_model_list.bind("<<ListboxSelect>>", lambda e: self._show_model_details("a"))
        self.a_model_entry = ttk.Entry(model_mgmt, width=30)
        self.a_model_entry.grid(row=3, column=0, sticky="w", padx=2, pady=(2, 0))
        self.a_model_entry.insert(0, "")
        self.refresh_a_btn = ttk.Button(
            model_mgmt,
            text="Refresh A",
            command=lambda: (
                self.save_config(),
                self._fetch_models(
                    self.a_url.get().strip(),
                    self.a_model,
                    self.refresh_a_btn,
                    self.a_model_status,
                    None,
                    agent="a_settings",
                ),
            ),
        )
        self.refresh_a_btn.grid(row=4, column=0, sticky="w", padx=2, pady=2)
        self.pull_a_btn = ttk.Button(
            model_mgmt,
            text="Pull → Agent A",
            command=lambda: self._pull_to_urls(
                [self.a_url.get().strip()], self._get_model_to_pull("a")
            ),
        )
        self.pull_a_btn.grid(row=5, column=0, padx=4, pady=2)
        self.remove_a_btn = ttk.Button(
            model_mgmt,
            text="Remove from A",
            command=lambda: self._remove_model(
                self.a_url.get().strip(), self._get_selected_model(self.a_model_list)
            ),
        )
        self.remove_a_btn.grid(row=6, column=0, padx=4, pady=2)

        ttk.Label(model_mgmt, text="Agent B Models:").grid(row=1, column=1, sticky="w")
        self.b_model_list = tk.Listbox(model_mgmt, width=32, height=6)
        self.b_model_list.grid(row=2, column=1, sticky="w", padx=2)
        self.b_model_list.bind("<<ListboxSelect>>", lambda e: self._show_model_details("b"))
        self.b_model_entry = ttk.Entry(model_mgmt, width=30)
        self.b_model_entry.grid(row=3, column=1, sticky="w", padx=2, pady=(2, 0))
        self.b_model_entry.insert(0, "")
        self.refresh_b_btn = ttk.Button(
            model_mgmt,
            text="Refresh B",
            command=lambda: (
                self.save_config(),
                self._fetch_models(
                    self.b_url.get().strip(),
                    self.b_model,
                    self.refresh_b_btn,
                    self.b_model_status,
                    None,
                    agent="b_settings",
                ),
            ),
        )
        self.refresh_b_btn.grid(row=4, column=1, sticky="w", padx=2, pady=2)
        self.pull_b_btn = ttk.Button(
            model_mgmt,
            text="Pull → Agent B",
            command=lambda: self._pull_to_urls(
                [self.b_url.get().strip()], self._get_model_to_pull("b")
            ),
        )
        self.pull_b_btn.grid(row=5, column=1, padx=4, pady=2)
        self.remove_b_btn = ttk.Button(
            model_mgmt,
            text="Remove from B",
            command=lambda: self._remove_model(
                self.b_url.get().strip(), self._get_selected_model(self.b_model_list)
            ),
        )
        self.remove_b_btn.grid(row=6, column=1, padx=4, pady=2)

        self.pull_both_btn = ttk.Button(
            model_mgmt,
            text="Pull → Both",
            command=lambda: self._pull_to_urls(
                [self.a_url.get().strip(), self.b_url.get().strip()],
                self._get_model_to_pull("both"),
            ),
        )
        self.pull_both_btn.grid(row=7, column=0, columnspan=2, padx=4, pady=2)

        self.model_details_text = tk.Text(
            model_mgmt,
            height=6,
            width=70,
            wrap="word",
            foreground="#222",
            background="#f8f8ff",
            borderwidth=1,
            relief="solid",
            cursor="xterm",
        )
        self.model_details_text.grid(row=8, column=0, columnspan=2, sticky="we", pady=(8, 2))
        self.model_details_text.config(state="normal")
        if self.model_details_text is not None:
            try:
                self.model_details_text.bind("<1>", lambda e: self.model_details_text.focus_set() if self.model_details_text else None)
            except (AttributeError, tk.TclError) as e:
                logger.debug("model_details_text.bind failed: %s", e)
        self.model_details_text.tag_configure("error", foreground="red")
        self.model_details_text.tag_configure("warning", foreground="orange")
        self.model_details_text.tag_configure("info", foreground="#222")
        self.copy_all_btn = ttk.Button(
            model_mgmt, text="Copy All", command=self._copy_model_details
        )
        self.copy_all_btn.grid(row=11, column=1, sticky="e", pady=(2, 6))

        # Pull progress widgets
        try:
            self.pull_progress = ttk.Progressbar(
                model_mgmt, length=360, mode="determinate", maximum=100
            )
            self.pull_progress.grid(row=9, column=0, columnspan=2, sticky="w", pady=(4, 2))
            self.pull_progress_label = ttk.Label(model_mgmt, text="")
            self.pull_progress_label.grid(row=10, column=0, sticky="w")
            self.cancel_pull_var = tk.BooleanVar(value=False)
            self.cancel_pull_btn = ttk.Button(
                model_mgmt,
                text="Cancel Pull",
                command=lambda: self.cancel_pull_var is not None and self.cancel_pull_var.set(True),
                state="disabled",
            )
            self.cancel_pull_btn.grid(row=10, column=1, sticky="e", padx=4)
        except (tk.TclError, AttributeError) as e:
            logger.debug("Pull progress widgets not available: %s", e)
            self.pull_progress = None
            self.pull_progress_label = None
            self.cancel_pull_var = None
            self.cancel_pull_btn = None

        # Brain viewer and storage removed per user request

    def _get_model_to_pull(self, agent):
        # Returns the model name to pull for the given agent.
        # Use the entry field if non-empty; otherwise use the selected item from the list.
        if agent == "a":
            if self.a_model_entry is not None:
                name = self.a_model_entry.get().strip()
                if name:
                    return name
            if self.a_model_list is not None:
                return self._get_selected_model(self.a_model_list)
            return None
        elif agent == "b":
            if self.b_model_entry is not None:
                name = self.b_model_entry.get().strip()
                if name:
                    return name
            if self.b_model_list is not None:
                return self._get_selected_model(self.b_model_list)
            return None
        elif agent == "both":
            # Prefer Agent A entry, then B, then selected from either list
            if self.a_model_entry is not None:
                name = self.a_model_entry.get().strip()
                if name:
                    return name
            if self.b_model_entry is not None:
                name = self.b_model_entry.get().strip()
                if name:
                    return name
            if self.a_model_list is not None:
                sel_a = self._get_selected_model(self.a_model_list)
                if sel_a:
                    return sel_a
            if self.b_model_list is not None:
                return self._get_selected_model(self.b_model_list)
            return None
        return None

    def _show_model_details(self, agent):
        # Always show both model details and the persistent log
        model = None
        if agent == "a":
            if self.a_model_list is not None:
                sel = self.a_model_list.curselection()
                if sel:
                    model = self.a_model_list.get(sel[0])
        elif agent == "b":
            if self.b_model_list is not None:
                sel = self.b_model_list.curselection()
                if sel:
                    model = self.b_model_list.get(sel[0])
        details = ""
        if model:
            info = None
            if hasattr(self, "_models_info") and agent in self._models_info:
                info = self._models_info[agent].get(model)
            if info:
                details = f"Model: {model}\n"
                for k, v in info.items():
                    details += f"{k.capitalize()}: {v}\n"
                details = details.strip()
            else:
                details = f"Model: {model}"
        self._update_model_details_box(details)

    def _update_model_details_box(self, details=None):
        # Guard against uninitialized widget
        if self.model_details_text is None:
            return
        try:
            self.model_details_text.config(state="normal")
        except (AttributeError, tk.TclError):
            return
        self.model_details_text.delete("1.0", "end")
        # Always show model details for current selection
        if details is None:
            # Try to get current selection from A or B
            model = None
            agent = None
            if self.a_model_list is not None and self.a_model_list.curselection():
                agent = "a"
                model = self.a_model_list.get(self.a_model_list.curselection()[0])
            elif self.b_model_list is not None and self.b_model_list.curselection():
                agent = "b"
                model = self.b_model_list.get(self.b_model_list.curselection()[0])
            if model:
                info = None
                if hasattr(self, "_models_info") and agent in self._models_info:
                    info = self._models_info[agent].get(model)
                if info:
                    details = f"Model: {model}\n"
                    for k, v in info.items():
                        details += f"{k.capitalize()}: {v}\n"
                    details = details.strip()
                else:
                    details = f"Model: {model}"
            else:
                details = ""
        if details:
            self.model_details_text.insert("end", details + "\n", "info")
            self.model_details_text.insert("end", "-" * 60 + "\n", "info")
        # Show status/error log (last 20)
        for ts, msg, level in self._model_status_log[-20:]:
            tag = level if level in ("error", "warning", "info") else "info"
            self.model_details_text.insert("end", f"[{ts}] {msg}\n", tag)
        self.model_details_text.see("end")
        # Add a minimal status entry (avoid calling _add_model_status to prevent recursion)
        try:
            ts = datetime.now().strftime("%H:%M:%S")
            self._model_status_log.append((ts, "Updated model details box", "info"))
            # Keep log small
            if len(self._model_status_log) > 50:
                self._model_status_log = self._model_status_log[-50:]
        except Exception as e:
            logger.debug("_update_model_details_box: failed to append status log: %s", e)
        # Return the details box to read-only state
        try:
            self.model_details_text.config(state="disabled")

            # --- API Path Overrides ---
            api_frame = ttk.LabelFrame(self.settings_tab, text="API Path Overrides")
            api_frame.pack(fill="x", padx=6, pady=(12, 6))
            ttk.Label(api_frame, text="Agent A API Path (optional):").grid(
                row=0, column=0, sticky="w", padx=4, pady=4
            )
            self.a_api_path = ttk.Entry(api_frame, width=24)
            self.a_api_path.grid(row=0, column=1, sticky="w", padx=4, pady=4)
            ttk.Label(api_frame, text="Agent B API Path (optional):").grid(
                row=1, column=0, sticky="w", padx=4, pady=4
            )
            self.b_api_path = ttk.Entry(api_frame, width=24)
            self.b_api_path.grid(row=1, column=1, sticky="w", padx=4, pady=4)
            ttk.Label(api_frame, text="Example: /api/chat or /v1/completions", foreground="#555").grid(
                row=2, column=0, columnspan=2, sticky="w", padx=4, pady=(0, 6)
            )
        except (AttributeError, tk.TclError) as e:
            logger.debug("model_details_text.config disable failed: %s", e)

    def _add_model_status(self, msg, level="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        self._model_status_log.append((ts, msg, level))
        # Only keep last 50 messages
        if len(self._model_status_log) > 50:
            self._model_status_log = self._model_status_log[-50:]
        self._update_model_details_box()

    def _copy_model_details(self):
        try:
            if self.model_details_text is None:
                return
            try:
                self.model_details_text.focus_set()
            except (AttributeError, tk.TclError):
                pass
            try:
                self.root.clipboard_clear()
                text = self.model_details_text.get("1.0", "end").strip()
                self.root.clipboard_append(text)
            except (AttributeError, tk.TclError):
                logger.debug("_copy_model_details: clipboard operations failed")
        except Exception as e:
            logger.debug("_copy_model_details outer exception: %s", e)

    def _add_recent_url(self, agent, url):
        try:
            if not url or not isinstance(url, str):
                return
            url = url.strip()
            if not url:
                return
            lst = self._recent_urls.get(agent, []) or []
            if url in lst:
                lst.remove(url)
            lst.insert(0, url)
            lst = lst[:10]
            self._recent_urls[agent] = lst
            try:
                if agent == "a" and hasattr(self, "a_url"):
                    self.a_url["values"] = lst
                if agent == "b" and hasattr(self, "b_url"):
                    self.b_url["values"] = lst
            except (tk.TclError, AttributeError):
                pass
        except (AttributeError, TypeError, ValueError) as e:
            logger.debug("_add_recent_url ignored bad value: %s", e)

    def _manage_urls(self, agent):
        try:
            top = tk.Toplevel(self.root)
            top.title("Manage Recent URLs")
            top.geometry("480x300")
            lbl = ttk.Label(top, text=f"Recent URLs for Agent {agent.upper()}")
            lbl.pack(anchor="w", padx=8, pady=(8, 2))
            lb = tk.Listbox(top)
            lb.pack(fill="both", expand=True, padx=8, pady=4)
            for u in self._recent_urls.get(agent, []) or []:
                lb.insert(tk.END, u)
            btn_frame = ttk.Frame(top)
            btn_frame.pack(fill="x", padx=8, pady=8)

            def remove_selected():
                try:
                    sel = lb.curselection()
                    if not sel:
                        return
                    idx = sel[0]
                    lb.delete(idx)
                    lst = list(lb.get(0, tk.END))
                    self._recent_urls[agent] = lst
                    try:
                        if agent == "a":
                            self.a_url["values"] = lst
                        else:
                            self.b_url["values"] = lst
                    except (tk.TclError, AttributeError) as e:
                        logger.debug("manage_urls: updating combobox values failed: %s", e)
                    try:
                        self.save_config()
                    except (OSError, IOError) as e:
                        logger.debug("manage_urls: save_config failed after removal: %s", e)
                except (IndexError, tk.TclError, AttributeError) as e:
                    logger.debug("manage_urls.remove_selected error: %s", e)

            def close():
                try:
                    top.destroy()
                except (tk.TclError, AttributeError) as e:
                    logger.debug("manage_urls.close failed: %s", e)

            rem_btn = ttk.Button(btn_frame, text="Remove Selected", command=remove_selected)
            rem_btn.pack(side="left")
            close_btn = ttk.Button(btn_frame, text="Close", command=close)
            close_btn.pack(side="right")
        except (tk.TclError, AttributeError, OSError) as e:
            logger.debug("_manage_urls failed: %s", e)

    def _set_model_busy(self, msg):
        try:
            self.model_busy_var.set(msg)
            if self.model_busy_label is not None:
                self.model_busy_label.update_idletasks()
        except (AttributeError, tk.TclError) as e:
            logger.debug("_set_model_busy failed: %s", e)

    def _clear_model_busy(self):
        try:
            self.model_busy_var.set("")
            if self.model_busy_label is not None:
                self.model_busy_label.update_idletasks()
        except (AttributeError, tk.TclError) as e:
            logger.debug("_clear_model_busy failed: %s", e)

    def _save_and_exit(self):
        try:
            self.save_config()
        except (OSError, IOError) as e:
            messagebox.showerror("Save Error", f"Failed to save config: {e}")
        self.root.quit()

    def _get_selected_model(self, listbox):
        try:
            selection = listbox.curselection()
            if selection:
                return listbox.get(selection[0])
        except (IndexError, tk.TclError, AttributeError):
            pass
        return ""

    # Brain subsystem removed: load/wipe helpers deleted

    def _refresh_a_models(self):
        self._set_model_busy("Refreshing Agent A models...")
        self.root.after(
            100,
            lambda: self._fetch_models(
                self.a_url.get().strip(),
                self.a_model,
                self.refresh_a_btn,
                self.a_model_status,
                None,
                agent="a_settings",
            ),
        )

    def _refresh_b_models(self):
        self._set_model_busy("Refreshing Agent B models...")
        self.root.after(
            100,
            lambda: self._fetch_models(
                self.b_url.get().strip(),
                self.b_model,
                self.refresh_b_btn,
                self.b_model_status,
                None,
                agent="b_settings",
            ),
        )

    def _refresh_chat_tab_model_selectors(self):
        """Synchronize the Chat-tab comboboxes with the Settings tab model lists."""
        try:
            a_vals = []
            b_vals = []
            try:
                aml = getattr(self, "a_model_list", None)
                if aml is not None:
                    try:
                        a_vals = list(aml.get(0, tk.END))
                    except tk.TclError as e:
                        logger.debug("_refresh_chat_tab_model_selectors: failed reading a_model_list: %s", e)
                        a_vals = []
                else:
                    a_vals = []
            except tk.TclError as e:
                logger.debug("_refresh_chat_tab_model_selectors: failed reading a_model_list: %s", e)
                a_vals = []
            try:
                bml = getattr(self, "b_model_list", None)
                if bml is not None:
                    try:
                        b_vals = list(bml.get(0, tk.END))
                    except tk.TclError as e:
                        logger.debug("_refresh_chat_tab_model_selectors: failed reading b_model_list: %s", e)
                        b_vals = []
                else:
                    b_vals = []
            except tk.TclError as e:
                logger.debug("_refresh_chat_tab_model_selectors: failed reading b_model_list: %s", e)
                b_vals = []
            # Update the main runtime comboboxes in the Chat tab
            try:
                if hasattr(self, "a_model"):
                    try:
                        self.a_model["values"] = a_vals
                        cur = self.a_model.get()
                        if cur not in a_vals and a_vals:
                            self.a_model.set(a_vals[0])
                    except tk.TclError as e:
                        logger.debug("_refresh_chat_tab_model_selectors: updating a_model values failed: %s", e)
            except (AttributeError, tk.TclError) as e:
                logger.debug("_refresh_chat_tab_model_selectors: a_model section failed: %s", e)
            try:
                if hasattr(self, "b_model"):
                    try:
                        self.b_model["values"] = b_vals
                        cur = self.b_model.get()
                        if cur not in b_vals and b_vals:
                            self.b_model.set(b_vals[0])
                    except tk.TclError as e:
                        logger.debug("_refresh_chat_tab_model_selectors: updating b_model values failed: %s", e)
            except (AttributeError, tk.TclError) as e:
                logger.debug("_refresh_chat_tab_model_selectors: b_model section failed: %s", e)
        except tk.TclError as e:
            logger.debug("_refresh_chat_tab_model_selectors outer error: %s", e)

    # Removed _on_chat_selector_change: bottom selectors were duplicate.
    # The main comboboxes are authoritative.

    def _update_models_text(self, agent, models):
        # Guard against uninitialized widgets
        if agent == "a_settings":
            if self.a_model_list is None:
                return
            self.a_model_list.delete(0, tk.END)
            if models:
                for m in models:
                    self.a_model_list.insert(tk.END, m)
            else:
                self.a_model_list.insert(tk.END, "(No models found or fetch failed)")
            # Auto-select and show details for first model after refresh
            self._auto_select_first_model("a")
        elif agent == "b_settings":
            if self.b_model_list is None:
                return
            self.b_model_list.delete(0, tk.END)
            if models:
                for m in models:
                    self.b_model_list.insert(tk.END, m)
            else:
                self.b_model_list.insert(tk.END, "(No models found or fetch failed)")
            self._auto_select_first_model("b")
        # No-op for 'a' and 'b' agents as a_models_text and b_models_text widgets are not defined
        # Also refresh the Chat-tab model selectors if present
        try:
            if hasattr(self, "_refresh_chat_tab_model_selectors"):
                try:
                    self._refresh_chat_tab_model_selectors()
                except (AttributeError, tk.TclError) as e:
                    logger.debug("_update_models_text: _refresh_chat_tab_model_selectors failed: %s", e)
        except (AttributeError, tk.TclError) as e:
            logger.debug("_update_models_text: refresh call failed: %s", e)

    # Patch _fetch_models to also fetch model details if available
    # (This is a minimal patch, as the main fetch logic is in worker)
    # To support model details, we need to parse details if present in the response
    # We'll store details in self._models_info[agent] as a dict,
    # e.g. {model_name: {details}}
    # This patch assumes the worker function is inside _fetch_models
    # Add after models are parsed:
    #   - If agent in ('a_settings', 'b_settings'), parse details
    #     and store in self._models_info[agent]
    #   - Details: size, modified_at, description, digest, etc. if present
    #   - On error, clear self._models_info[agent]
    #   - On model list update, clear model details display
    #   - On model select, call _show_model_details(agent)
    #   - On fetch/refresh, show busy indicator

    def _poll_connectivity(self):
        # Poll server and model status every 2 seconds
        try:
            self._check_server_status(self.a_url.get().strip(), self.a_model_status)
            self._check_server_status(self.b_url.get().strip(), self.b_model_status)
            self._check_model_status(
                self.a_url.get().strip(),
                self.a_model.get().strip(),
                self.a_model_status,
            )
            self._check_model_status(
                self.b_url.get().strip(),
                self.b_model.get().strip(),
                self.b_model_status,
            )
            # Also update the Chat-tab indicators (if present)
            try:
                if hasattr(self, "a_status_dot"):
                    self._check_server_status(self.a_url.get().strip(), self.a_status_dot)
                    try:
                        self._check_model_status(
                            self.a_url.get().strip(),
                            self.a_model.get().strip(),
                            self.a_status_dot,
                        )
                    except (AttributeError, tk.TclError) as e:
                        logger.debug("_fetch_models: _set_icon_color failed: %s", e)
                if hasattr(self, "b_status_dot"):
                    self._check_server_status(self.b_url.get().strip(), self.b_status_dot)
                    try:
                        self._check_model_status(
                            self.b_url.get().strip(),
                            self.b_model.get().strip(),
                            self.b_status_dot,
                        )
                    except (AttributeError, tk.TclError) as e:
                        logger.debug("_poll_connectivity: failed checking b_status_dot model status: %s", e)
            except (AttributeError, tk.TclError) as e:
                logger.debug("_poll_connectivity: failed updating chat-tab indicators: %s", e)
        except (AttributeError, tk.TclError, urllib.error.URLError, OSError) as e:
            logger.debug("_poll_connectivity outer: exception while polling connectivity: %s", e)
        # Schedule next poll
        self.root.after(2000, self._poll_connectivity)

    def _call_ollama_with_timeout(
        self, client_url, model, messages, runtime_options=None, timeout=20
    ):
        """Call chat_with_ollama in a thread and return its result or a timeout error."""
        result = {}
        def worker():
            try:
                res = chat_with_ollama(client_url, model, messages, runtime_options=runtime_options)
            except Exception as e:
                logger.exception("_call_ollama_with_timeout: chat_with_ollama raised for %s", client_url)
                res = {"content": f"[ERROR calling {client_url}: {e}]"}
            try:
                result["res"] = res
            except (TypeError, AttributeError) as e:
                logger.debug("_call_ollama_with_timeout: failed to set result: %s", e)
                result["res"] = {"content": "[ERROR]"}

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            # Thread still running — return a timeout placeholder.
            # Leave the worker to finish in background.
            logger.warning(
                "_call_ollama_with_timeout: timeout after %ss contacting %s",
                timeout,
                client_url,
            )
            return {"content": f"[ERROR: timeout after {timeout}s contacting {client_url}]"}
        return result.get("res", {"content": "[ERROR: no response]"})

    def load_personas(self, path=DEFAULT_PERSONAS_PATH):
        if not os.path.exists(path):
            # nothing to load
            self.persona_presets = {}
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            out = {}
            for name, v in data.items():
                if isinstance(v, dict):
                    out[name] = (
                        str(v.get("age", "")),
                        v.get("quirk", ""),
                        v.get("prompt", ""),
                    )
            self.persona_presets = out
        except (json.JSONDecodeError, OSError):
            self.persona_presets = {}

    def save_config(self, path=DEFAULT_CONFIG):
        cfg = {
            "a_url": self.a_url.get().strip(),
            "b_url": self.b_url.get().strip(),
            "a_model": self.a_model.get().strip(),
            "b_model": self.b_model.get().strip(),
            "a_name": self.a_name.get().strip(),
            "b_name": self.b_name.get().strip(),
            "a_persona": self.a_persona.get().strip(),
            "b_persona": self.b_persona.get().strip(),
            "a_age": self.a_age.get().strip(),
            "b_age": self.b_age.get().strip(),
            "a_quirk": self.a_quirk.get().strip(),
            "b_quirk": self.b_quirk.get().strip(),
            "topic": self.topic.get().strip(),
            "turns": int(self.turns.get()),
            "delay": float(self.delay.get()),
            "max_chars_a": int(self.max_chars_a.get()),
            "max_chars_b": int(self.max_chars_b.get()),
            "short_turn": bool(self.short_turn_var.get()),
            "log": bool(self.log_var.get()),
            "log_path": self.log_path.get().strip(),
            "close_on_exit": bool(self.close_on_exit_var.get()),
            # Pull model management config removed
            "persona_presets": {
                k: {"age": v[0], "quirk": v[1], "prompt": v[2]}
                for k, v in self.persona_presets.items()
            },
            "a_runtime": {
                "temperature": float(self.a_temp.get()),
                "max_tokens": int(self.a_max_tokens.get()),
                "top_p": float(self.a_top_p.get()),
                "stop": [s.strip() for s in self.a_stop.get().split(",") if s.strip()],
                "stream": bool(self.a_stream.get()),
            },
            "b_runtime": {
                "temperature": float(self.b_temp.get()),
                "max_tokens": int(self.b_max_tokens.get()),
                "top_p": float(self.b_top_p.get()),
                "stop": [s.strip() for s in self.b_stop.get().split(",") if s.strip()],
                "stream": bool(self.b_stream.get()),
            },
            "a_api_path": (self.a_api_path.get().strip() if hasattr(self, "a_api_path") and self.a_api_path is not None else ""),
            "b_api_path": (self.b_api_path.get().strip() if hasattr(self, "b_api_path") and self.b_api_path is not None else ""),
        }
        try:
            # update recent URL lists before saving
            try:
                aurl = cfg.get("a_url", "").strip()
                burl = cfg.get("b_url", "").strip()
                try:
                    self._add_recent_url("a", aurl)
                except (AttributeError, ValueError) as e:
                    logger.debug("save_config: _add_recent_url(a) failed: %s", e)
                try:
                    self._add_recent_url("b", burl)
                except (AttributeError, ValueError) as e:
                    logger.debug("save_config: _add_recent_url(b) failed: %s", e)
                cfg["recent_a_urls"] = list(self._recent_urls.get("a", []))
                cfg["recent_b_urls"] = list(self._recent_urls.get("b", []))
            except (AttributeError, ValueError) as e:
                logger.debug("save_config: recent urls update failed: %s", e)
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2)
            except (OSError, TypeError) as e:
                logger.exception("Failed to write config to %s: %s", path, e)
        except (AttributeError, OSError, TypeError) as e:
            logger.exception("Error saving config: %s", e)

    def load_config(self, path=DEFAULT_CONFIG):
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.debug("load_config: failed to read/parse %s: %s", path, e)
            return

        self._set_widget_value(self.a_url, cfg.get("a_url", self.a_url.get()))
        self._set_widget_value(self.b_url, cfg.get("b_url", self.b_url.get()))
        self._set_widget_value(self.a_model, cfg.get("a_model", self.a_model.get()))
        self._set_widget_value(self.b_model, cfg.get("b_model", self.b_model.get()))
        self._set_widget_value(self.a_persona, cfg.get("a_persona", self.a_persona.get()))
        try:
            self._set_widget_value(self.a_name, cfg.get("a_name", self.a_name.get()))
        except (AttributeError, tk.TclError):
            pass
        self._set_widget_value(self.b_persona, cfg.get("b_persona", self.b_persona.get()))
        # Load API path overrides if present
        try:
            if hasattr(self, "a_api_path") and self.a_api_path is not None:
                self.a_api_path.delete(0, tk.END)
                self.a_api_path.insert(0, cfg.get("a_api_path", ""))
            if hasattr(self, "b_api_path") and self.b_api_path is not None:
                self.b_api_path.delete(0, tk.END)
                self.b_api_path.insert(0, cfg.get("b_api_path", ""))
        except (AttributeError, tk.TclError) as e:
            logger.debug("load_config: api_path set failed: %s", e)
        self._set_widget_value(self.a_age, cfg.get("a_age", self.a_age.get()))
        self._set_widget_value(self.b_age, cfg.get("b_age", self.b_age.get()))
        self._set_widget_value(self.a_quirk, cfg.get("a_quirk", self.a_quirk.get()))
        self._set_widget_value(self.b_quirk, cfg.get("b_quirk", self.b_quirk.get()))
        try:
            self.topic.delete(0, tk.END)
            self.topic.insert(0, cfg.get("topic", self.topic.get()))
        except (tk.TclError, AttributeError):
            pass
        try:
            self.turns.set(int(cfg.get("turns", self.turns.get())))
        except (ValueError, TypeError, tk.TclError, AttributeError):
            pass
        try:
            self.delay.set(float(cfg.get("delay", self.delay.get())))
        except (ValueError, TypeError, tk.TclError, AttributeError):
            pass
        try:
            self.max_chars_a.set(int(cfg.get("max_chars_a", self.max_chars_a.get())))
        except (ValueError, TypeError, tk.TclError, AttributeError) as e:
            logger.debug("load_config: max_chars_a set failed: %s", e)
        try:
            self.max_chars_b.set(int(cfg.get("max_chars_b", self.max_chars_b.get())))
        except (ValueError, TypeError, tk.TclError, AttributeError) as e:
            logger.debug("load_config: max_chars_b set failed: %s", e)
        try:
            self.short_turn_var.set(bool(cfg.get("short_turn", self.short_turn_var.get())))
        except (TypeError, tk.TclError, AttributeError) as e:
            logger.debug("load_config: short_turn_var set failed: %s", e)
        try:
            self.log_var.set(bool(cfg.get("log", self.log_var.get())))
            self.log_path.delete(0, tk.END)
            self.log_path.insert(0, cfg.get("log_path", self.log_path.get()))
        except (TypeError, tk.TclError, AttributeError) as e:
            logger.debug("load_config: log_var/log_path set failed: %s", e)
        try:
            self.close_on_exit_var.set(bool(cfg.get("close_on_exit", self.close_on_exit_var.get())))
        except (TypeError, tk.TclError, AttributeError) as e:
            logger.debug("load_config: close_on_exit_var set failed: %s", e)
        # load persona presets if present
        pp = cfg.get("persona_presets")
        if isinstance(pp, dict):
            try:
                self.persona_presets = {
                    k: (str(v.get("age", "")), v.get("quirk", ""), v.get("prompt", ""))
                    for k, v in pp.items()
                }
                preset_names = list(self.persona_presets.keys())
                self.a_preset["values"] = preset_names
                self.b_preset["values"] = preset_names
            except (AttributeError, TypeError) as e:
                logger.debug("load_config: persona_presets load failed: %s", e)
        # Load persona file selections if present
        try:
            a_pf = cfg.get("a_persona_file", "")
            b_pf = cfg.get("b_persona_file", "")
            if hasattr(self, "a_persona_file_settings") and self.a_persona_file_settings is not None and a_pf:
                try:
                    self.a_persona_file_settings.set(a_pf)
                    p = os.path.join(os.path.dirname(__file__), a_pf)
                    if os.path.exists(p):
                        with open(p, "r", encoding="utf-8") as pf:
                            txt = pf.read().strip()
                        try:
                            self.a_persona.delete(0, tk.END)
                            self.a_persona.insert(0, txt)
                        except (tk.TclError, AttributeError) as e:
                            logger.debug("load_config: setting a_persona text failed: %s", e)
                except (OSError, AttributeError, TypeError):
                    logger.debug("load_config: loading a_persona file failed")
            if hasattr(self, "b_persona_file_settings") and self.b_persona_file_settings is not None and b_pf:
                try:
                    self.b_persona_file_settings.set(b_pf)
                    p = os.path.join(os.path.dirname(__file__), b_pf)
                    if os.path.exists(p):
                        with open(p, "r", encoding="utf-8") as pf:
                            txt = pf.read().strip()
                        try:
                            self.b_persona.delete(0, tk.END)
                            self.b_persona.insert(0, txt)
                        except (tk.TclError, AttributeError) as e:
                            logger.debug("load_config: setting b_persona text failed: %s", e)
                except (OSError, AttributeError, TypeError):
                    logger.debug("load_config: loading b_persona file failed")
        except (OSError, AttributeError, TypeError) as e:
            logger.debug("load_config: persona file selections load failed: %s", e)
        # Load recent URLs if present
        try:
            ra = cfg.get("recent_a_urls", []) or []
            rb = cfg.get("recent_b_urls", []) or []
            self._recent_urls["a"] = [u for u in ra if isinstance(u, str) and u.strip()]
            self._recent_urls["b"] = [u for u in rb if isinstance(u, str) and u.strip()]
            try:
                if hasattr(self, "a_url"):
                    self.a_url["values"] = self._recent_urls["a"]
                    # set the combobox value to saved a_url if present
                    try:
                        self.a_url.set(cfg.get("a_url", self.a_url.get()))
                    except (tk.TclError, AttributeError) as e:
                        logger.debug("load_config: a_url.set failed: %s", e)
            except (AttributeError, tk.TclError):
                logger.debug("load_config: setting a_url values failed")
            try:
                if hasattr(self, "b_url"):
                    self.b_url["values"] = self._recent_urls["b"]
                    try:
                        self.b_url.set(cfg.get("b_url", self.b_url.get()))
                    except (tk.TclError, AttributeError) as e:
                        logger.debug("load_config: b_url.set failed: %s", e)
            except (AttributeError, tk.TclError):
                logger.debug("load_config: setting b_url values failed")
        except (AttributeError, TypeError) as e:
            logger.debug("load_config: recent urls load failed: %s", e)
        # Pull model management config load removed
        try:
            ar = cfg.get("a_runtime", {}) or {}
            try:
                self.a_temp.set(float(ar.get("temperature", self.a_temp.get())))
            except (ValueError, TypeError, AttributeError, tk.TclError) as e:
                logger.debug("load_config: a_temp set failed: %s", e)
            try:
                self.a_max_tokens.set(int(ar.get("max_tokens", self.a_max_tokens.get())))
            except (ValueError, TypeError, AttributeError, tk.TclError) as e:
                logger.debug("load_config: a_max_tokens set failed: %s", e)
            try:
                self.a_top_p.set(float(ar.get("top_p", self.a_top_p.get())))
            except (ValueError, TypeError, AttributeError, tk.TclError) as e:
                logger.debug("load_config: a_top_p set failed: %s", e)
            try:
                self.a_stop.delete(0, tk.END)
                self.a_stop.insert(
                    0,
                    ",".join(ar.get("stop", []) if isinstance(ar.get("stop", []), list) else []),
                )
            except (AttributeError, tk.TclError) as e:
                logger.debug("load_config: a_stop set failed: %s", e)
            try:
                self.a_stream.set(bool(ar.get("stream", self.a_stream.get())))
            except (AttributeError, tk.TclError) as e:
                logger.debug("load_config: a_stream set failed: %s", e)
        except (AttributeError, TypeError):
            pass
        try:
            br = cfg.get("b_runtime", {}) or {}
            try:
                self.b_temp.set(float(br.get("temperature", self.b_temp.get())))
            except (ValueError, TypeError, AttributeError, tk.TclError) as e:
                logger.debug("load_config: b_temp set failed: %s", e)
            try:
                self.b_max_tokens.set(int(br.get("max_tokens", self.b_max_tokens.get())))
            except (ValueError, TypeError, AttributeError, tk.TclError) as e:
                logger.debug("load_config: b_max_tokens set failed: %s", e)
            try:
                self.b_top_p.set(float(br.get("top_p", self.b_top_p.get())))
            except (ValueError, TypeError, AttributeError, tk.TclError) as e:
                logger.debug("load_config: b_top_p set failed: %s", e)
            try:
                self.b_stop.delete(0, tk.END)
                self.b_stop.insert(
                    0,
                    ",".join(br.get("stop", []) if isinstance(br.get("stop", []), list) else []),
                )
            except (AttributeError, tk.TclError) as e:
                logger.debug("load_config: b_stop set failed: %s", e)
            try:
                self.b_stream.set(bool(br.get("stream", self.b_stream.get())))
            except (AttributeError, tk.TclError) as e:
                logger.debug("load_config: b_stream set failed: %s", e)
        except (AttributeError, TypeError, ValueError):
            pass
        try:
            self._set_widget_value(self.b_name, cfg.get("b_name", self.b_name.get()))
        except (AttributeError, tk.TclError) as e:
            logger.debug("load_config: setting b_name failed: %s", e)

    def _poll_queue(self):
        def format_markdown(md):
            # Bold: **text** or __text__
            md = re.sub(r"\*\*(.*?)\*\*|__(.*?)__", lambda m: m.group(1) or m.group(2), md)
            # Italic: *text* or _text_
            md = re.sub(r"\*(.*?)\*|_(.*?)_", lambda m: m.group(1) or m.group(2), md)
            # Inline code: `code`
            md = re.sub(r"`([^`]*)`", r"[code]\1[/code]", md)
            # Code blocks: ```code```
            md = re.sub(r"```([\s\S]*?)```", r"\n[code]\1[/code]\n", md)
            # Lists: - item or * item
            md = re.sub(r"^[\s]*[-\*] (.*)", r"• \1", md, flags=re.MULTILINE)
            # Headers: # Header
            md = re.sub(r"^#+ (.*)", r"\1", md, flags=re.MULTILINE)
            # Blockquotes: > quote
            md = re.sub(r"^> (.*)", r'"\1"', md, flags=re.MULTILINE)
            return md

        try:
            while True:
                kind, text = self.queue.get_nowait()
                fmt = self.formatting_var.get() if hasattr(self, "formatting_var") else "plain"
                if fmt == "plain":
                    formatted = text
                elif fmt == "markdown":
                    formatted = format_markdown(text)
                elif fmt == "raw":
                    formatted = text
                else:
                    formatted = text
                if kind == "a":
                    name = self.a_name.get().strip() if hasattr(self, "a_name") else "Agent_A"
                    self.chat_text.config(state="normal")
                    self.chat_text.insert("end", f"{name}: " + formatted + "\n\n")
                    self.chat_text.see("end")
                    self.chat_text.config(state="disabled")
                elif kind == "b":
                    name = self.b_name.get().strip() if hasattr(self, "b_name") else "Agent_B"
                    self.chat_text.config(state="normal")
                    self.chat_text.insert("end", f"{name}: " + formatted + "\n\n")
                    self.chat_text.see("end")
                    self.chat_text.config(state="disabled")
                elif kind == "status":
                    self.status_var.set(formatted)
                    try:
                        m = re.search(r"Turn\s*(\d+)\s*/\s*(\d+)", formatted)
                        if m:
                            try:
                                self.turn_count_var.set(f"{m.group(1)}/{m.group(2)}")
                            except (AttributeError, tk.TclError):
                                pass
                    except (re.error, TypeError):
                        pass
                elif kind == "endpoint":
                    try:
                        if hasattr(self, "last_endpoint_var") and self.last_endpoint_var is not None:
                            try:
                                self.last_endpoint_var.set(formatted)
                            except (AttributeError, tk.TclError):
                                pass
                    except Exception:
                        pass
                    try:
                        logger.info("Endpoint used: %s", formatted)
                    except Exception:
                        pass
                elif kind == "done":
                    try:
                        if hasattr(self, "start_btn") and self.start_btn is not None:
                            try:
                                self.start_btn.config(state="normal")
                            except (AttributeError, tk.TclError):
                                try:
                                    self.start_btn["state"] = "normal"
                                except Exception as e:
                                    logger.debug("_poll_queue: fallback start_btn state set failed: %s", e)
                    except Exception as e:
                        logger.debug("_poll_queue: restoring start_btn state failed: %s", e)
                    try:
                        if hasattr(self, "stop_btn") and self.stop_btn is not None:
                            try:
                                self.stop_btn.config(state="disabled")
                            except (AttributeError, tk.TclError):
                                try:
                                    self.stop_btn["state"] = "disabled"
                                except Exception as e:
                                    logger.debug("_poll_queue: fallback stop_btn state set failed: %s", e)
                    except Exception as e:
                        logger.debug("_poll_queue: restoring stop_btn state failed: %s", e)
                    self.status_var.set("Finished.")
                    try:
                        self.turn_count_var.set("")
                    except (AttributeError, tk.TclError) as e:
                        logger.debug("_poll_queue: clearing turn_count_var failed: %s", e)
                elif kind == "user":
                    try:
                        self.chat_text.config(state="normal")
                        self.chat_text.insert("end", f"You: {formatted}\n\n")
                        self.chat_text.see("end")
                        self.chat_text.config(state="disabled")
                    except (tk.TclError, AttributeError) as e:
                        logger.debug("_poll_queue: inserting user text failed: %s", e)
        except queue.Empty:
            logger.debug("_poll_queue: queue empty")
        self.root.after(100, self._poll_queue)

    def start(self, greeting=None):
        # Guard against uninitialized widgets
        if not hasattr(self, "start_btn") or self.start_btn is None:
            return
        if not hasattr(self, "stop_btn") or self.stop_btn is None:
            return
        if not hasattr(self, "chat_text") or self.chat_text is None:
            return
        if self.thread and self.thread.is_alive():
            return
        self.chat_text.delete("1.0", "end")
        self.stop_event.clear()
        try:
            self.start_btn.config(state="disabled")
        except (AttributeError, tk.TclError):
            return
        try:
            self.stop_btn.config(state="normal")
        except (AttributeError, tk.TclError):
            pass
        self.status_var.set("Running...")
        try:
            self.turn_count_var.set(f"0/{int(self.turns.get())}")
        except (ValueError, TypeError, AttributeError, tk.TclError):
            try:
                self.turn_count_var.set("")
            except (AttributeError, tk.TclError):
                pass
        # Safely read persona file selections (these attributes may exist but be None)
        a_persona_file = ""
        b_persona_file = ""
        try:
            aps = getattr(self, "a_persona_file_settings", None)
            if aps is not None and hasattr(aps, "get"):
                try:
                    a_persona_file = aps.get().strip() or ""
                except Exception as e:
                    logger.debug("start: reading a_persona_file failed: %s", e)
                    a_persona_file = ""
        except Exception as e:
            logger.debug("start: error accessing a_persona_file_settings: %s", e)
            a_persona_file = ""
        try:
            bps = getattr(self, "b_persona_file_settings", None)
            if bps is not None and hasattr(bps, "get"):
                try:
                    b_persona_file = bps.get().strip() or ""
                except Exception as e:
                    logger.debug("start: reading b_persona_file failed: %s", e)
                    b_persona_file = ""
        except Exception as e:
            logger.debug("start: error accessing b_persona_file_settings: %s", e)
            b_persona_file = ""

        cfg = {
            "a_url": self.a_url.get().strip(),
            "a_name": (self.a_name.get().strip() if hasattr(self, "a_name") else "Agent_A"),
            "a_model": self.a_model.get().strip(),
            "a_persona": self.a_persona.get().strip(),
            "a_persona_file": a_persona_file,
            "a_age": self.a_age.get().strip(),
            "a_quirk": self.a_quirk.get().strip(),
            "b_url": self.b_url.get().strip(),
            "b_model": self.b_model.get().strip(),
            "b_persona": self.b_persona.get().strip(),
            "b_persona_file": b_persona_file,
            "b_age": self.b_age.get().strip(),
            "b_quirk": self.b_quirk.get().strip(),
            "topic": self.topic.get().strip(),
            "turns": int(self.turns.get()),
            "delay": float(self.delay.get()),
            "humanize": bool(self.humanize_var.get()),
            "greeting": (
                greeting or (self.greeting.get().strip() if hasattr(self, "greeting") else "")
            )
            or None,
            "max_chars_a": int(self.max_chars_a.get()),
            "max_chars_b": int(self.max_chars_b.get()),
            "short_turn": bool(self.short_turn_var.get()),
            "log": bool(self.log_var.get()),
            "log_path": self.log_path.get().strip() or None,
            "a_runtime": {
                "temperature": float(self.a_temp.get()),
                "max_tokens": int(self.a_max_tokens.get()),
                "top_p": float(self.a_top_p.get()),
                "stop": [s.strip() for s in self.a_stop.get().split(",") if s.strip()],
                "stream": bool(self.a_stream.get()),
            },
            "b_runtime": {
                "temperature": float(self.b_temp.get()),
                "max_tokens": int(self.b_max_tokens.get()),
                "top_p": float(self.b_top_p.get()),
                "stop": [s.strip() for s in self.b_stop.get().split(",") if s.strip()],
                "stream": bool(self.b_stream.get()),
            },
            "b_name": (self.b_name.get().strip() if hasattr(self, "b_name") else "Agent_B"),
        }
        # create an inbound queue for injected user messages during a running conversation
        self.to_worker_queue = queue.Queue()
        self.thread = threading.Thread(
            target=self._run_conversation,
            args=(cfg, self.stop_event, self.queue, self.to_worker_queue),
            daemon=True,
        )
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.status_var.set("Stopping...")

    def on_close(self):
        try:
            self.stop()
            if self.thread:
                try:
                    self.thread.join(timeout=1.0)
                except RuntimeError:
                    pass
            try:
                self.save_config()
            except (OSError, TypeError, AttributeError):
                pass
        except (AttributeError, RuntimeError):
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        # Exit process only if the user enabled the option
        try:
            if getattr(self, "close_on_exit_var", None) and self.close_on_exit_var.get():
                os._exit(0)
        except (AttributeError, tk.TclError):
            sys.exit(0)

    def _fetch_models(
        self,
        server_url,
        combobox,
        button,
        status_label=None,
        status_icon=None,
        agent=None,
    ):
        # Insert visible debug message in B Listbox at start - guard against uninitialized widgets
        if agent == "b_settings":
            if self.b_model_list is not None:
                try:
                    self.b_model_list.delete(0, tk.END)
                    self.b_model_list.insert(tk.END, "(Refreshing...)")
                except (AttributeError, tk.TclError) as e:
                    logger.debug("_fetch_models: b_model_list update failed: %s", e)
            self._add_model_status("Started refreshing models for agent B", "info")

        def worker():
            try:
                try:
                    if button:
                        if button:
                            self._safe_set_button_state(button, "disabled")
                except (AttributeError, tk.TclError) as e:
                    logger.debug("_fetch_models: disabling button failed: %s", e)
                # show concise status banner in Settings
                try:
                    if agent == "a_settings":
                        self._set_model_busy("Refreshing Agent A models...")
                    elif agent == "b_settings":
                        self._set_model_busy("Refreshing Agent B models...")
                except Exception:
                    pass
                # Prepare attempt tracking for debugging and probes
                attempts = []
                last_exc = None

                if not server_url:
                    self.queue.put(("status", "Server URL empty"))
                    if status_label is not None:
                        def _set_status_gray(sl=status_label):
                            try:
                                if sl is not None:
                                    sl.config(text="●", foreground="gray")
                            except (tk.TclError, AttributeError) as e:
                                logger.debug("_fetch_models: status_label update failed: %s", e)

                        try:
                            self.root.after(0, _set_status_gray)
                        except (tk.TclError, AttributeError) as e:
                            logger.debug("_fetch_models: scheduling status_label update failed: %s", e)
                            # try immediate fallback
                            try:
                                _set_status_gray()
                            except Exception as e:
                                logger.debug("_fetch_models: immediate status_label update fallback failed: %s", e)
                    if agent in ("a_settings", "b_settings"):
                        def _update_models_safe():
                            try:
                                self._update_models_text(agent, [])
                            except (tk.TclError, AttributeError) as e:
                                logger.debug("_fetch_models: _update_models_text failed: %s", e)

                        try:
                            self.root.after(0, _update_models_safe)
                        except (tk.TclError, AttributeError) as e:
                            logger.debug("_fetch_models: scheduling _update_models_text failed: %s", e)
                            try:
                                _update_models_safe()
                            except Exception as e:
                                logger.debug("_fetch_models: immediate _update_models_text fallback failed: %s", e)
                    return
                # Quick TCP probe to detect unreachable hosts/ports early
                try:
                    p = urlparse(server_url)
                    host = p.hostname or server_url
                    port = p.port
                    if port is None:
                        port = 443 if (p.scheme and p.scheme.lower() == "https") else 80
                    attempts.append(f"TCP PROBE {host}:{port}")
                    try:
                        s = socket.create_connection((host, port), timeout=2)
                        s.close()
                    except Exception as e:
                        last_exc = e
                        attempts.append(f"TCP FAIL {host}:{port}: {repr(e)}")
                        dbg_path = "model_fetch_debug.log"
                        try:
                            with open(dbg_path, "a", encoding="utf-8") as df:
                                df.write(f"[{datetime.now().isoformat()}] TCP probe failed for {server_url}: {repr(e)}\n")
                                for a in attempts:
                                    df.write(a + "\n")
                                df.write("\n")
                        except OSError:
                            logger.debug("_fetch_models: failed writing %s", dbg_path, exc_info=True)
                        try:
                            # Update UI with concise message and mark status red
                            self._set_model_busy("Server unreachable (TCP) — check host/port")
                        except Exception:
                            pass
                        if agent:
                            try:
                                self.root.after(0, lambda: self._update_models_text(agent, []))
                            except Exception:
                                try:
                                    self._update_models_text(agent, [])
                                except Exception:
                                    pass
                        if status_label is not None:
                            try:
                                self.root.after(0, lambda: status_label.config(text="●", foreground="red"))
                            except Exception:
                                try:
                                    status_label.config(text="●", foreground="red")
                                except Exception:
                                    pass
                        return
                except Exception as e:
                    logger.debug("_fetch_models: TCP probe step failed: %s", e)
                # Prefer the newer /v1/models endpoint first; increase timeout tolerance
                endpoints = ["/v1/models", "/models", "/api/models"]
                models = []
                last_exc = None
                attempts = []
                for ep in endpoints:
                    url = server_url.rstrip("/") + ep
                    # requests with retries/backoff
                    for attempt in range(3):
                        try:
                            attempts.append(f"GET {url} (attempt {attempt+1})")
                            resp = requests.get(url, timeout=5)
                            resp.raise_for_status()
                            try:
                                data = resp.json()
                            except Exception:
                                txt = resp.text or ""
                                if "\n" in txt:
                                    lines = [line.strip() for line in txt.splitlines() if line.strip()]
                                    models.extend(lines)
                                else:
                                    # non-JSON single-line responses
                                    if txt.strip():
                                        models.append(txt.strip())
                                data = data if 'data' in locals() else None
                            if isinstance(data, list):
                                for item in data:
                                    if isinstance(item, dict):
                                        name = item.get("name") or item.get("model") or item.get("id")
                                        if name:
                                            models.append(name)
                                    else:
                                        models.append(str(item))
                            elif isinstance(data, dict):
                                for key in ("models", "results", "data"):
                                    if key in data and isinstance(data[key], list):
                                        for item in data[key]:
                                            if isinstance(item, dict):
                                                n = (
                                                    item.get("name")
                                                    or item.get("model")
                                                    or item.get("id")
                                                    or item.get("modelId")
                                                )
                                                if n:
                                                    models.append(n)
                                if not models:
                                    for v in data.values():
                                        if isinstance(v, str):
                                            models.append(v)
                            if models:
                                break
                        except requests.RequestException as ie:
                            last_exc = ie
                            attempts.append(f"ERROR {url} attempt {attempt+1}: {repr(ie)}")
                            logger.debug("_fetch_models: request to %s failed: %s", url, ie, exc_info=True)
                            try:
                                time.sleep(0.5 * (2 ** attempt))
                            except Exception:
                                pass
                            continue
                    if models:
                        break

                def _set_icon_color(col: str):
                    try:
                        if status_label is not None:
                            color_map = {"green": "green", "red": "red", "gray": "gray"}
                            try:
                                # capture status_label into the lambda and only call config if it's not None
                                self.root.after(
                                    0,
                                    lambda sl=status_label: sl.config(
                                        text="●", foreground=color_map.get(col, "gray")
                                    ) if sl is not None else None,
                                )
                            except (tk.TclError, AttributeError):
                                try:
                                    if status_label is not None:
                                        status_label.config(text="●", foreground=color_map.get(col, "gray"))
                                except (AttributeError, tk.TclError):
                                    pass
                    except (AttributeError, tk.TclError):
                        pass

                if models:
                    seen = set()
                    unique = []
                    for m in models:
                        if m not in seen:
                            seen.add(m)
                            unique.append(m)
                    if combobox:
                        try:
                            try:
                                try:
                                    self._call_in_main(lambda: combobox.config(values=unique))
                                except (AttributeError, tk.TclError) as e:
                                    try:
                                        combobox.config(values=unique)
                                    except (AttributeError, tk.TclError) as e2:
                                        logger.debug("_fetch_models: combobox.config failed: %s; %s", e, e2)
                                if unique:
                                    try:
                                        self._call_in_main(lambda: combobox.set(unique[0]))
                                    except (AttributeError, tk.TclError) as e:
                                        try:
                                            combobox.set(unique[0])
                                        except (AttributeError, tk.TclError) as e2:
                                            logger.debug("_fetch_models: combobox.set failed: %s; %s", e, e2)
                            except (AttributeError, tk.TclError) as e:
                                logger.debug("_fetch_models: combobox inner update failed: %s", e)
                        except (AttributeError, tk.TclError) as e:
                            logger.debug("_fetch_models: combobox outer update failed: %s", e)
                    try:
                        try:
                            self._call_in_main(
                                lambda: self._add_model_status(
                                    f"Loaded {len(unique)} models from {server_url}", "info"
                                )
                            )
                        except (AttributeError, tk.TclError) as e:
                            try:
                                self._add_model_status(
                                    f"Loaded {len(unique)} models from {server_url}", "info"
                                )
                            except (AttributeError, tk.TclError) as e2:
                                logger.debug("_fetch_models: _add_model_status failed: %s; %s", e, e2)
                    except (AttributeError, tk.TclError) as e:
                        logger.debug("_fetch_models: scheduling _add_model_status failed: %s", e)
                    # Always update the model list in the main GUI combobox as well
                    # Always update the correct Listbox in Settings after fetch
                    if agent == "a_settings":
                        try:
                            self._call_in_main(lambda: self._update_models_text("a_settings", unique))
                        except (tk.TclError, AttributeError):
                            try:
                                self._update_models_text("a_settings", unique)
                            except (tk.TclError, AttributeError) as e:
                                logger.debug("_fetch_models: _update_models_text a_settings failed: %s", e)
                    if agent == "b_settings":
                        try:
                            try:
                                self.root.after(
                                    0,
                                    lambda: self._update_models_text("b_settings", unique),
                                )
                            except (tk.TclError, AttributeError):
                                self._update_models_text("b_settings", unique)
                        except (AttributeError, tk.TclError) as e:
                            logger.debug("_fetch_models: _update_models_text b_settings scheduling failed: %s", e)
                    if status_label is not None:
                        try:
                            _set_icon_color("green")
                        except (AttributeError, tk.TclError) as e:
                            logger.debug("_fetch_models: _set_icon_color failed when marking green: %s", e)
                    try:
                        self._clear_model_busy()
                    except Exception:
                        pass
                else:
                    msg = f"No models found at {server_url}"
                    if last_exc:
                        msg += f": {repr(last_exc)}"
                    if agent:
                        try:
                            self.root.after(0, lambda: self._update_models_text(agent, []))
                        except tk.TclError as e:
                            try:
                                self._update_models_text(agent, [])
                            except tk.TclError as e2:
                                logger.debug("_fetch_models: _update_models_text failed in no-models path: %s; %s", e, e2)
                    dbg_path = "model_fetch_debug.log"
                    try:
                        with open(dbg_path, "a", encoding="utf-8") as df:
                            dbg_line = (
                                f"[{datetime.now().isoformat()}] Fetch models debug for "
                                f"{server_url}\n"
                            )
                            df.write(dbg_line)
                            for a in attempts:
                                df.write(a + "\n")
                            if last_exc:
                                df.write("Last exception: " + repr(last_exc) + "\n")
                            df.write("\n")
                    except OSError:
                        logger.debug("_fetch_models: failed writing %s", dbg_path, exc_info=True)
                    try:
                        try:
                            self._call_in_main(lambda: self._add_model_status(msg + " (see model_fetch_debug.log)", "error"))
                        except (tk.TclError, AttributeError):
                            self._add_model_status(msg + " (see model_fetch_debug.log)", "error")
                    except (AttributeError, tk.TclError) as e:
                        logger.debug("_fetch_models: _add_model_status scheduling failed: %s", e)
                    # Surface concise banner instead of intrusive modal
                    try:
                        self._set_model_busy("Model fetch failed — see model_fetch_debug.log")
                    except Exception:
                        pass
                    if status_label is not None:
                        try:
                            _set_icon_color("red")
                        except (AttributeError, tk.TclError) as e:
                            logger.debug("_fetch_models: _set_icon_color failed when marking red: %s", e)
            except (
                urllib.error.URLError,
                OSError,
                socket.timeout,
                json.JSONDecodeError,
                ValueError,
            ) as e:
                self._add_model_status(f"Model fetch failed: {repr(e)}", "error")
            finally:
                if button:
                    self._safe_set_button_state(button, "normal")
                if agent == "b_settings":
                    try:
                        try:
                            self.root.after(
                                0,
                                lambda: self._add_model_status(
                                    "Finished refreshing models for agent B", "info"
                                ),
                            )
                        except (tk.TclError, AttributeError):
                            self._add_model_status("Finished refreshing models for agent B", "info")
                    except (AttributeError, tk.TclError) as e:
                        logger.debug("_fetch_models: finalizing b_settings status failed: %s", e)

        def run_and_force_update():
            worker()
            # Force update of the combobox UI in the main thread
            if combobox:
                try:
                    try:
                        self.root.after(0, combobox.update_idletasks)
                    except (tk.TclError, AttributeError):
                        combobox.update_idletasks()
                except (AttributeError, tk.TclError):
                    pass

        threading.Thread(target=run_and_force_update, daemon=True).start()

    def _pull_now(self, server_url, model_name):
        pass

    def _pull_all(self, server_url):
        pass

    def _refresh_available_models(self):
        pass

    def _pull_to_urls(self, url_list, model_name):
        # using top-level json and requests
        if not url_list or not model_name:
            messagebox.showerror("Pull Model", "No server URL or model name specified.")
            return
        for server_url in url_list:
            if not server_url:
                continue
            # Reset cancel flag
            try:
                if self.cancel_pull_var is not None:
                    self.cancel_pull_var.set(False)
            except (AttributeError, TypeError):
                pass
            try:
                status_msg = f"Pulling model {model_name} to {server_url}..."
                self._set_model_busy(status_msg)
                self._add_model_status(status_msg, "info")
                url = server_url.rstrip("/") + "/api/pull"

                # Prepare progress UI (use determinate mode and start at 0)
                try:
                    if self.pull_progress is not None:
                        try:
                            p = self.pull_progress

                            def _init_progress(p=p):
                                try:
                                    if p is None:
                                        return
                                    p.config(mode="determinate", maximum=100)
                                    p.config(value=0)
                                    p.update_idletasks()
                                except (tk.TclError, AttributeError):
                                    pass

                            try:
                                self.root.after(0, _init_progress)
                            except (tk.TclError, AttributeError):
                                _init_progress()
                        except (AttributeError, tk.TclError):
                            pass
                    if self.pull_progress_label is not None:
                        try:
                            lbl = self.pull_progress_label
                            try:
                                self.root.after(
                                    0,
                                    lambda l=lbl: l.config(text="Starting...") if l is not None else None,
                                )
                            except (tk.TclError, AttributeError):
                                if lbl is not None:
                                    try:
                                        lbl.config(text="Starting...")
                                    except (AttributeError, tk.TclError):
                                        pass
                        except (AttributeError, tk.TclError):
                            pass
                    if self.cancel_pull_btn is not None:
                        try:
                            self._safe_set_button_state(self.cancel_pull_btn, "normal")
                        except (AttributeError, tk.TclError):
                            pass
                except (AttributeError, tk.TclError):
                    pass

                resp = requests.post(url, json={"name": model_name}, stream=True, timeout=60)
                if resp.status_code not in (200, 201):
                    # Non-success — read small body and show error
                    try:
                        err = resp.json().get("error")
                    except (ValueError, json.JSONDecodeError):
                        err = resp.text
                    fail_msg = f"Failed to pull model to {server_url}: {err}"
                    self._add_model_status(fail_msg, "error")
                    self._safe_messagebox(messagebox.showerror, "Pull Model", fail_msg)
                else:
                    # Stream and update progress when possible
                    cancelled = False
                    try:
                        for raw in resp.iter_lines(decode_unicode=True):
                            if self.cancel_pull_var is not None and self.cancel_pull_var.get():
                                cancelled = True
                                self._add_model_status("Pull cancelled by user", "warning")
                                break
                            if not raw:
                                continue
                            line = raw.strip()
                            parsed = None
                            pct = None
                            try:
                                parsed = json.loads(line)
                            except (json.JSONDecodeError, ValueError):
                                parsed = None
                            msg_text = None
                            if isinstance(parsed, dict):
                                # Common keys: 'progress', 'percent', 'status', 'message',
                                # 'downloaded', 'total'
                                for k in ("progress", "percent", "download_percent"):
                                    if k in parsed:
                                        try:
                                            pct = float(parsed.get(k) or 0.0)
                                        except (ValueError, TypeError):
                                            pct = None
                                        break
                                if pct is None and "downloaded" in parsed and "total" in parsed:
                                    try:
                                        downloaded = float(parsed.get("downloaded") or 0)
                                        total = float(parsed.get("total") or 1)
                                        pct = (downloaded / total) * 100.0
                                    except (ValueError, TypeError, ZeroDivisionError):
                                        pct = None
                                msg_text = (
                                    parsed.get("status")
                                    or parsed.get("message")
                                    or parsed.get("msg")
                                    or None
                                )
                            else:
                                msg_text = line

                            if pct is not None:
                                try:
                                    p = max(0, min(100, int(pct)))

                                    def _set_pct(v=p):
                                        try:
                                            if self.pull_progress is not None:
                                                try:
                                                    self.pull_progress.config(
                                                        mode="determinate", value=v
                                                    )
                                                    self.pull_progress.update_idletasks()
                                                except (tk.TclError, AttributeError):
                                                    try:
                                                        self.pull_progress["value"] = v
                                                    except (tk.TclError, AttributeError):
                                                        pass
                                            if self.pull_progress_label is not None:
                                                self.pull_progress_label.config(text=f"{v}%")
                                        except (AttributeError, tk.TclError):
                                            pass

                                    self.root.after(0, _set_pct)
                                except (ValueError, TypeError):
                                    pass
                            else:
                                # show textual status
                                if msg_text:
                                    try:
                                        lbl = self.pull_progress_label
                                        try:
                                            self.root.after(
                                                0,
                                                lambda l=lbl, t=msg_text: l.config(text=str(t)[:200]) if l is not None else None,
                                            )
                                        except (tk.TclError, AttributeError):
                                            if lbl is not None:
                                                try:
                                                    lbl.config(text=str(msg_text)[:200])
                                                except (tk.TclError, AttributeError):
                                                    pass
                                    except (AttributeError, tk.TclError):
                                        pass
                    except (requests.RequestException, OSError) as stream_exc:
                        self._add_model_status(f"Error during pull stream: {stream_exc}", "error")

                    # Completed or cancelled
                    if cancelled:
                        self._safe_messagebox(
                            messagebox.showinfo, "Pull Model", f"Pull cancelled for {server_url}"
                        )
                    else:
                        success_msg = f'Model "{model_name}" pulled successfully to {server_url}.'
                        self._add_model_status(success_msg, "info")
                        self._safe_messagebox(messagebox.showinfo, "Pull Model", success_msg)

                # Finalize progress UI
                try:
                    if self.pull_progress is not None:
                        try:
                            p = self.pull_progress

                            def _finalize_progress(p=p):
                                try:
                                    if p is None:
                                        return
                                    p.config(mode="determinate", value=100)
                                    p.update_idletasks()
                                except (tk.TclError, AttributeError):
                                    pass

                            try:
                                self.root.after(0, _finalize_progress)
                            except (tk.TclError, AttributeError):
                                _finalize_progress()
                        except (AttributeError, tk.TclError):
                            pass
                    if self.pull_progress_label is not None:
                        try:
                            lbl = self.pull_progress_label

                            def _clear_progress_label(lbl=lbl):
                                try:
                                    if lbl is None:
                                        return
                                    lbl.config(text="")
                                except (tk.TclError, AttributeError):
                                    pass

                            try:
                                self.root.after(0, _clear_progress_label)
                            except (tk.TclError, AttributeError):
                                _clear_progress_label()
                        except (AttributeError, tk.TclError):
                            pass
                    if self.cancel_pull_btn is not None:
                        try:
                            self._safe_set_button_state(self.cancel_pull_btn, "disabled")
                        except (AttributeError, tk.TclError):
                            pass
                except (AttributeError, tk.TclError):
                    pass
            except (requests.RequestException, OSError) as e:
                err_msg = f"Error pulling model to {server_url}: {e}"
                self._add_model_status(err_msg, "error")
                self._safe_messagebox(messagebox.showerror, "Pull Model", err_msg)
            finally:
                self._clear_model_busy()
                # Refresh model list for the relevant agent
                try:
                    if server_url == self.a_url.get().strip():
                        self._refresh_a_models()
                    elif server_url == self.b_url.get().strip():
                        self._refresh_b_models()
                except (AttributeError, tk.TclError):
                    pass

    def _remove_model(self, server_url, model_name):
        # Remove a model from the Ollama server using the correct API endpoint
        # requests imported at module level
        if not server_url or not model_name:
            messagebox.showerror("Remove Model", "No server URL or model name specified.")
            return
        try:
            self._set_model_busy(f"Removing model {model_name}...")
            # Ollama expects DELETE /api/delete with JSON body: {"name": "modelname"}
            url = server_url.rstrip("/") + "/api/delete"
            resp = requests.delete(url, json={"name": model_name}, timeout=10)
            if resp.status_code == 200:
                messagebox.showinfo("Remove Model", f'Model "{model_name}" removed successfully.')
            else:
                try:
                    err = resp.json().get("error")
                except (ValueError, json.JSONDecodeError):
                    err = resp.text
                messagebox.showerror("Remove Model", f"Failed to remove model: {err}")
        except (requests.RequestException, OSError) as e:
            messagebox.showerror("Remove Model", f"Error removing model: {e}")
        finally:
            self._clear_model_busy()
            # Refresh model list for the relevant agent
            if server_url == self.a_url.get().strip():
                self._refresh_a_models()
            elif server_url == self.b_url.get().strip():
                self._refresh_b_models()

    def _apply_preset(self, preset_name, age_cb, quirk_cb, persona_entry):
        if not preset_name:
            return
        v = self.persona_presets.get(preset_name)
        if not v:
            return
        age, quirk, persona_text = v
        try:
            age_cb.set(age)
        except (tk.TclError, AttributeError):
            pass
        try:
            quirk_cb.set(quirk)
        except (tk.TclError, AttributeError):
            try:
                quirk_cb.delete(0, tk.END)
                quirk_cb.insert(0, quirk)
            except (tk.TclError, AttributeError):
                pass
        try:
            persona_entry.delete(0, tk.END)
            persona_entry.insert(0, persona_text)
        except (tk.TclError, AttributeError):
            pass
        try:
            self.queue.put(("status", f"Applied preset: {preset_name}"))
        except queue.Full:
            pass

    def reset_defaults(self):
        try:
            self.a_url.delete(0, tk.END)
            self.a_url.insert(0, "http://localhost:11434")
        except (tk.TclError, AttributeError):
            pass
        try:
            self.b_url.delete(0, tk.END)
            self.b_url.insert(0, "http://192.168.127.121:11434")
        except (tk.TclError, AttributeError):
            pass
        try:
            self.a_model.set("llama2")
        except (tk.TclError, AttributeError):
            pass
        try:
            self.b_model.set("llama2")
        except (tk.TclError, AttributeError):
            pass
        try:
            self.a_persona.delete(0, tk.END)
            self.a_persona.insert(0, "")
        except (tk.TclError, AttributeError):
            pass
        try:
            self.b_persona.delete(0, tk.END)
            self.b_persona.insert(0, "")
        except (tk.TclError, AttributeError):
            pass
        try:
            self.a_age.delete(0, tk.END)
            self.a_age.insert(0, "45")
            self.b_age.delete(0, tk.END)
            self.b_age.insert(0, "28")
        except (tk.TclError, AttributeError):
            pass
        try:
            self.a_quirk.delete(0, tk.END)
            self.a_quirk.insert(0, "polite phrasing")
            self.b_quirk.delete(0, tk.END)
            self.b_quirk.insert(0, "uses slang")
        except (tk.TclError, AttributeError):
            pass
        try:
            try:
                self.a_name.delete(0, tk.END)
                self.a_name.insert(0, "Ava")
            except (tk.TclError, AttributeError):
                pass
            try:
                self.b_name.delete(0, tk.END)
                self.b_name.insert(0, "Orion")
            except (tk.TclError, AttributeError):
                pass
        except (tk.TclError, AttributeError):
            pass
        try:
            self.max_chars_a.set(120)
            self.max_chars_b.set(120)
        except (tk.TclError, AttributeError):
            pass
        try:
            self.short_turn_var.set(True)
        except (tk.TclError, AttributeError):
            pass
        # restore default presets
        self.load_personas()
        try:
            preset_names = list(self.persona_presets.keys())
            self.a_preset["values"] = preset_names
            self.b_preset["values"] = preset_names
            if preset_names:
                self.a_preset.set(preset_names[0])
                self.b_preset.set(preset_names[0])
        except (tk.TclError, AttributeError):
            pass
        # clear persona file selections by default
        try:
            a_pf_setter = getattr(self, "a_persona_file_settings", None)
            if a_pf_setter is not None and hasattr(a_pf_setter, "set"):
                try:
                    a_pf_setter.set("")
                except (tk.TclError, AttributeError):
                    pass
            b_pf_setter = getattr(self, "b_persona_file_settings", None)
            if b_pf_setter is not None and hasattr(b_pf_setter, "set"):
                try:
                    b_pf_setter.set("")
                except (tk.TclError, AttributeError):
                    pass
        except (tk.TclError, AttributeError):
            pass
        self.queue.put(("status", "Defaults restored"))
        try:
            self.save_config()
        except (OSError, IOError):
            pass

    def _run_conversation(self, cfg, stop_event, out_queue, in_queue=None):
        log_file = None
        try:
            topic = cfg["topic"]
            try:
                out_queue.put(("status", f"Using topic: {topic}"))
            except queue.Full:
                pass

            def build_persona(base, age, quirk):
                parts = []
                if base:
                    parts.append(base)
                if age:
                    parts.append(f"Age: {age}")
                if quirk:
                    parts.append(f"Quirk: {quirk}")
                return " | ".join(parts) if parts else ""

            persona_a = build_persona(cfg.get("a_persona"), cfg.get("a_age"), cfg.get("a_quirk"))
            persona_b = build_persona(cfg.get("b_persona"), cfg.get("b_age"), cfg.get("b_quirk"))

            name_a = cfg.get("a_name") or "Agent_A"
            name_b = cfg.get("b_name") or "Agent_B"
            instruction_parts = [
                "Important: In every reply, explicitly reference the discussion topic",
                "and keep responses focused on it.",
                "Begin each response by briefly restating the topic and avoid unrelated tangents.",
                (
                    "Always respond in complete sentences. Do not use sentence fragments or"
                    " single-word replies;"
                ),
                "each response should be a full sentence ending with appropriate punctuation.",
            ]
            instruction = " ".join(instruction_parts)

            sys_a = " ".join(
                [
                    instruction,
                    f"You are {name_a}.",
                    f"Discuss '{topic}' with {name_b}.",
                    persona_a,
                ]
            ).strip()
            sys_b = " ".join(
                [
                    instruction,
                    f"You are {name_b}.",
                    f"Discuss '{topic}' with {name_a}.",
                    persona_b,
                ]
            ).strip()

            messages_a = [{"role": "system", "content": sys_a}]
            messages_b = [{"role": "system", "content": sys_b}]

            # Prefer an explicit greeting passed to start().
            # Otherwise follow the humanize/topic settings
            if cfg.get("greeting"):
                initial_prompt = cfg.get("greeting")
            elif cfg.get("humanize"):
                initial_prompt = "Hello, how are you?"
            else:
                initial_prompt = f"Let's discuss {topic}. I think..."

            out_queue.put(("b", f"(initial) {initial_prompt}"))
            # Add the initial user prompt to both agents so they both answer the question
            messages_b.append({"role": "user", "content": initial_prompt})
            messages_a.append({"role": "user", "content": initial_prompt})
            # initial prompt recorded locally (no persistent brain)

            turns = cfg["turns"]
            delay = cfg["delay"]
            a_url = cfg["a_url"]
            b_url = cfg["b_url"]
            # Apply API path overrides if present in config
            try:
                a_api = cfg.get("a_api_path", "") or ""
                if a_api:
                    if not a_api.startswith("/"):
                        a_api = "/" + a_api
                    a_url = a_url.rstrip("/") + a_api
            except Exception:
                pass
            try:
                b_api = cfg.get("b_api_path", "") or ""
                if b_api:
                    if not b_api.startswith("/"):
                        b_api = "/" + b_api
                    b_url = b_url.rstrip("/") + b_api
            except Exception:
                pass
            a_model = cfg["a_model"]
            b_model = cfg["b_model"]

            log_file = None
            if cfg.get("log") and cfg.get("log_path"):
                try:
                    log_file = open(cfg.get("log_path"), "a", encoding="utf-8")
                except OSError:
                    log_file = None

            def ts():
                return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            def trunc(text: str, agent: str) -> str:
                if not text:
                    return ""
                t = text.strip()
                maxc = cfg.get("max_chars_a") if agent == "a" else cfg.get("max_chars_b")
                # Short-turn: prefer the first full sentence.
                # If the first sentence exists, return it whole
                if cfg.get("short_turn"):
                    m = re.search(r"(.+?[.!?])(\s|$)", t, re.S)
                    if m:
                        s = m.group(1).strip()
                        # If a max char limit exists but would force cutting the
                        # first full sentence, prefer returning the full sentence
                        # to preserve completeness.
                        if maxc and maxc > 0 and len(s) > maxc:
                            return s
                        limit = maxc if maxc and maxc > 0 else 120
                        if len(s) > limit:
                            return s
                        return s
                    else:
                        parts = re.split(r"[,;:\\-]\s*", t, maxsplit=1)
                        s = parts[0].strip()
                        if maxc and maxc > 0 and len(s) > maxc:
                            return s
                        if not s.endswith((".", "!", "?")):
                            s = s.rstrip(" ,;:") + "…"
                        return s

                # Non-short-turn: if we must truncate, cut at the last
                # sentence boundary within the limit
                if maxc and maxc > 0 and len(t) > maxc:
                    snippet = t[:maxc]
                    # look for the last sentence terminator
                    last_pos = max(snippet.rfind("."), snippet.rfind("!"), snippet.rfind("?"))
                    if last_pos != -1 and last_pos > 0:
                        s = snippet[: last_pos + 1].strip()
                        return s
                    # fallback: try to return the first full sentence from the whole text
                    m2 = re.search(r"(.+?[.!?])(\s|$)", t, re.S)
                    if m2:
                        return m2.group(1).strip()
                    # last resort: truncate and append ellipsis
                    s = snippet.strip()
                    if not s.endswith((".", "!", "?")):
                        s = s.rstrip(" ,;:") + "…"
                    return s

                return t

            def dedupe_sentences(text: str) -> str:
                if not text:
                    return ""
                # Split into sentence-like chunks (keep trailing punctuation)
                parts = re.findall(r"[^.!?\n]+[\.!?…]?", text, flags=re.S)
                if not parts:
                    return text.strip()
                out = []
                prev = None
                for p in parts:
                    s = p.strip()
                    if not s:
                        continue
                    # If identical to previous sentence, skip
                    if prev is not None and s == prev:
                        continue
                    out.append(s)
                    prev = s
                return " ".join(out).strip()

            for i in range(turns):
                if stop_event.is_set():
                    break
                out_queue.put(("status", f"Turn {i + 1}/{turns}"))

                # check for any injected user messages and append them to Agent B's message queue
                try:
                    in_q = in_queue if in_queue is not None else None
                    if in_q is not None:
                        while True:
                            um = in_q.get_nowait()
                            if isinstance(um, str) and um.strip():
                                # Broadcast injected user message to both agents so both will answer
                                try:
                                    messages_b.append({"role": "user", "content": um.strip()})
                                except (AttributeError, TypeError):
                                    pass
                                try:
                                    messages_a.append({"role": "user", "content": um.strip()})
                                except (AttributeError, TypeError):
                                    pass
                                try:
                                    out_queue.put(("user", um.strip()))
                                except queue.Full:
                                    pass
                            # continue draining any additional messages
                except queue.Empty:
                    pass

                # pass runtime options for Agent B
                b_runtime = {
                    "temperature": float(cfg.get("b_runtime", {}).get("temperature", 0.7)),
                    "max_tokens": int(cfg.get("b_runtime", {}).get("max_tokens", 512)),
                    "top_p": float(cfg.get("b_runtime", {}).get("top_p", 1.0)),
                    "stop": cfg.get("b_runtime", {}).get("stop") or None,
                    "stream": bool(cfg.get("b_runtime", {}).get("stream", False)),
                }
                resp_b = self._call_ollama_with_timeout(
                    b_url, b_model, messages_b, runtime_options=b_runtime, timeout=20
                )
                content_b = trunc(resp_b.get("content", ""), "b")
                content_b = dedupe_sentences(content_b)
                out_queue.put(("b", content_b))
                # brain logging removed
                if log_file:
                    try:
                        log_file.write(f"[{ts()}] B: {content_b}\n")
                        log_file.flush()
                    except OSError:
                        pass
                messages_b.append({"role": "assistant", "content": content_b})
                messages_a.append({"role": "user", "content": content_b})
                # publish endpoint used for Agent B (if present)
                try:
                    ep = resp_b.get("endpoint") if isinstance(resp_b, dict) else None
                    if ep:
                        try:
                            out_queue.put(("endpoint", f"B: {ep}"))
                        except queue.Full:
                            pass
                except Exception:
                    pass

                if stop_event.is_set():
                    break

                a_runtime = {
                    "temperature": float(cfg.get("a_runtime", {}).get("temperature", 0.7)),
                    "max_tokens": int(cfg.get("a_runtime", {}).get("max_tokens", 512)),
                    "top_p": float(cfg.get("a_runtime", {}).get("top_p", 1.0)),
                    "stop": cfg.get("a_runtime", {}).get("stop") or None,
                    "stream": bool(cfg.get("a_runtime", {}).get("stream", False)),
                }
                resp_a = self._call_ollama_with_timeout(
                    a_url, a_model, messages_a, runtime_options=a_runtime, timeout=20
                )
                content_a = trunc(resp_a.get("content", ""), "a")
                content_a = dedupe_sentences(content_a)
                out_queue.put(("a", content_a))
                # brain logging removed
                if log_file:
                    try:
                        log_file.write(f"[{ts()}] A: {content_a}\n")
                        log_file.flush()
                    except OSError:
                        pass
                messages_a.append({"role": "assistant", "content": content_a})
                messages_b.append({"role": "user", "content": content_a})
                # publish endpoint used for Agent A (if present)
                try:
                    ep2 = resp_a.get("endpoint") if isinstance(resp_a, dict) else None
                    if ep2:
                        try:
                            out_queue.put(("endpoint", f"A: {ep2}"))
                        except queue.Full:
                            pass
                except Exception:
                    pass

                # Only sleep if not stopping
                if stop_event.is_set():
                    break
                time.sleep(delay)

        except Exception as e:
            logger.exception("Worker thread encountered exception: %s", e)
            try:
                tb = traceback.format_exc()
                with open("thread_error.log", "a", encoding="utf-8") as ef:
                    ef.write(tb + "\n")
                try:
                    out_queue.put(("status", f"Error: {e} (see thread_error.log)"))
                except queue.Full:
                    pass
            except OSError as e2:
                logger.debug("thread worker: failed to write thread_error.log: %s", e2)
                try:
                    out_queue.put(("status", f"Error: {e}"))
                except queue.Full:
                    pass
        finally:
            try:
                if log_file:
                    log_file.close()
            except OSError:
                pass
            try:
                out_queue.put(("done", ""))
            except queue.Full:
                pass


def main():
    root = tk.Tk()
    app = OllamaGUI(root)

    try:
        # Load previous config if present; otherwise fall back to defaults
        try:
            app.load_config()
        except (OSError, json.JSONDecodeError, ValueError, AttributeError):
            app.reset_defaults()
    except (AttributeError, tk.TclError, OSError):
        try:
            app.reset_defaults()
        except (AttributeError, tk.TclError, OSError):
            pass
    # Ensure model lists auto-refresh after config is loaded and widgets are ready
    root.after(100, app._refresh_a_models)
    root.after(200, app._refresh_b_models)
    root.mainloop()


if __name__ == "__main__":
    main()
