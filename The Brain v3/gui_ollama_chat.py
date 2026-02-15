#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui_ollama_chat.py - Tkinter GUI for managing and running two-agent Ollama conversations.
Restores the original feature set: per-agent URLs/models, model discovery, persona presets,
short-turn truncation, threaded conversation loop, and persistent config.
"""


import os
import json
import time
import queue
import threading
import urllib.request
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText
from multi_ollama_chat import chat_with_ollama
import brain


DEFAULT_PERSONAS_PATH = os.path.join(os.path.dirname(__file__), 'personas.json')
DEFAULT_CONFIG = os.path.join(os.path.dirname(__file__), 'gui_config.json')


class Tooltip:
    """Simple tooltip for Tkinter widgets."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind('<Enter>', self.show)
        widget.bind('<Leave>', self.hide)

    def show(self, _=None):
        if self.tipwindow:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 20
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(tw, text=self.text, background='#ffffe0', relief='solid', borderwidth=1)
        lbl.pack()

    def hide(self, _=None):
        if self.tipwindow:
            try:
                self.tipwindow.destroy()
            except Exception:
                pass
            self.tipwindow = None


class OllamaGUI:
    """Main GUI class for Ollama two-agent chat."""
    def _on_send(self):
        self.start()

    def _on_stop(self):
        self.stop()

    def _clear_chat(self):
        self.chat_text.config(state='normal')
        self.chat_text.delete('1.0', 'end')
        self.chat_text.insert('end', 'Welcome to Ollama Two-Agent Chat!\n')
        self.chat_text.config(state='disabled')

    def _check_model_status(self, url, model, status_label):
        pass

    def _check_server_status(self, url, status_label):
        def worker():
            try:
                req = urllib.request.Request(url.rstrip('/') + '/v1/models')
                with urllib.request.urlopen(req, timeout=1) as resp:
                    if resp.status == 200:
                        status_label.config(text='●', foreground='green')
                        return
            except Exception:
                pass
            status_label.config(text='●', foreground='red')
        threading.Thread(target=worker, daemon=True).start()


    def __init__(self, root):
        self.root = root
        root.title('Ollama Two-Agent Chat')
        self.queue = queue.Queue()
        # --- Notebook and Tabs ---
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill='both', expand=True)
        self.chat_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.chat_tab, text='Chat')
        self.settings_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.settings_tab, text='Settings')
        # Continue with rest of initialization
        self.thread = None
        self.stop_event = threading.Event()
        self._poll_queue()
        self._apply_theme('Dark')
        # Immediately poll connectivity after widgets are created
        self.root.after(200, self._poll_connectivity)
        self._models_info = {'a_settings': {}, 'b_settings': {}}
        # model refresh will be scheduled after UI widgets are initialized


    def _auto_select_first_model(self, agent):
        if agent == 'a':
            if self.a_model_list.size() > 0:
                self.a_model_list.selection_clear(0, 'end')
                self.a_model_list.selection_set(0)
                self._show_model_details('a')
        elif agent == 'b':
            if self.b_model_list.size() > 0:
                self.b_model_list.selection_clear(0, 'end')
                self.b_model_list.selection_set(0)
                self._show_model_details('b')
        # Restore model auto-refresh on URL change after widgets are created

        # --- Theme Application ---
    def _apply_theme(self, theme):
        style = ttk.Style()
        # Use default theme (vista/win10/clam)
        try:
            style.theme_use('vista')
        except Exception:
            try:
                style.theme_use('xpnative')
            except Exception:
                style.theme_use('clam')
        style.configure('.', background='SystemButtonFace', foreground='black')
        style.configure('TLabel', background='SystemButtonFace', foreground='black')
        style.configure('TFrame', background='SystemButtonFace')
        style.configure('TNotebook', background='SystemButtonFace')
        style.configure('TNotebook.Tab', background='SystemButtonFace', foreground='black')
        style.configure('TEntry', fieldbackground='white', foreground='black')
        style.configure('TCombobox', fieldbackground='white', foreground='black')
        style.configure('TButton', background='SystemButtonFace', foreground='black')

        # --- Agent Settings ---

        agent_frame = ttk.LabelFrame(self.chat_tab, text='Agent Settings')
        agent_frame.pack(fill='x', padx=16, pady=(12, 4), anchor='n')

        # Agent A controls
        ttk.Label(agent_frame, text='Agent A URL:').grid(row=0, column=0, sticky='w', padx=(0,6), pady=6)
        self.a_url = ttk.Entry(agent_frame, width=36)
        self.a_url.grid(row=0, column=1, sticky='w', pady=6)
        # Persist URLs when user edits them (focus-out or Enter)
        try:
            self.a_url.bind('<FocusOut>', lambda e: self.save_config())
            self.a_url.bind('<Return>', lambda e: self.save_config())
        except Exception:
            pass
        ttk.Label(agent_frame, text='Model:').grid(row=0, column=2, sticky='w', padx=(12,6), pady=6)
        self.a_model = ttk.Combobox(agent_frame, width=24, values=[])
        self.a_model.grid(row=0, column=3, sticky='w', pady=6)
        self.a_model_status = ttk.Label(agent_frame, text='●', foreground='gray')
        self.a_model_status.grid(row=0, column=4, padx=6, pady=6)
        self.a_refresh_btn = ttk.Button(agent_frame, text='↻', width=3, command=lambda: (self.save_config(), self._fetch_models(self.a_url.get().strip(), self.a_model, self.a_refresh_btn, self.a_model_status, None)))
        self.a_refresh_btn.grid(row=0, column=5, padx=6, pady=6)
        ttk.Label(agent_frame, text='Preset:').grid(row=0, column=6, sticky='w', padx=(12,6), pady=6)
        self.a_preset = ttk.Combobox(agent_frame, width=20, values=[])
        self.a_preset.grid(row=0, column=7, sticky='w', pady=6)
        self.a_preset.bind('<<ComboboxSelected>>', lambda e: self._apply_preset(self.a_preset.get(), self.a_age, self.a_quirk, self.a_persona))
        ttk.Label(agent_frame, text='Persona:').grid(row=1, column=0, sticky='w', padx=(0,6), pady=6)
        self.a_persona = ttk.Entry(agent_frame, width=36)
        self.a_persona.grid(row=1, column=1, sticky='w', pady=6)
        ttk.Label(agent_frame, text='Name:').grid(row=1, column=6, sticky='w', padx=(12,6), pady=6)
        self.a_name = ttk.Entry(agent_frame, width=12)
        self.a_name.grid(row=1, column=7, sticky='w', pady=6)
        ttk.Label(agent_frame, text='Age:').grid(row=1, column=2, sticky='w', padx=(12,6), pady=6)
        self.a_age = ttk.Entry(agent_frame, width=12)
        self.a_age.grid(row=1, column=3, sticky='w', pady=6)
        ttk.Label(agent_frame, text='Quirk:').grid(row=1, column=4, sticky='w', padx=(12,6), pady=6)
        # Gather all unique quirks from persona presets and add more
        extra_quirks = [
            'sarcastic', 'mysterious', 'hyper-logical', 'minimalist', 'storyteller',
            'humorous', 'cryptic', 'mentor-like', 'philosophical', 'AI expert',
            'hacker mindset', 'playful', 'visionary', 'skeptical', 'empathetic',
            'teacherly', 'provocative', 'zen', 'repetitive', 'random', 'detailed'
        ]
        try:
            with open(DEFAULT_PERSONAS_PATH, 'r', encoding='utf-8') as f:
                persona_data = json.load(f)
            quirks = set(v.get('quirk','') for v in persona_data.values() if v.get('quirk'))
        except Exception:
            quirks = set()
        quirks.update(extra_quirks)
        quirk_list = sorted(q for q in quirks if q)
        self.a_quirk = ttk.Combobox(agent_frame, width=20, values=quirk_list)
        self.a_quirk.grid(row=1, column=5, sticky='w', pady=6)
        self.a_quirk.set('')

        # Agent B controls
        ttk.Label(agent_frame, text='Agent B URL:').grid(row=2, column=0, sticky='w', padx=(0,6), pady=6)
        self.b_url = ttk.Entry(agent_frame, width=36)
        self.b_url.grid(row=2, column=1, sticky='w', pady=6)
        try:
            self.b_url.bind('<FocusOut>', lambda e: self.save_config())
            self.b_url.bind('<Return>', lambda e: self.save_config())
        except Exception:
            pass
        ttk.Label(agent_frame, text='Model:').grid(row=2, column=2, sticky='w', padx=(12,6), pady=6)
        self.b_model = ttk.Combobox(agent_frame, width=24, values=[])
        self.b_model.grid(row=2, column=3, sticky='w', pady=6)
        self.b_model_status = ttk.Label(agent_frame, text='●', foreground='gray')
        self.b_model_status.grid(row=2, column=4, padx=6, pady=6)
        self.b_refresh_btn = ttk.Button(agent_frame, text='↻', width=3, command=lambda: (self.save_config(), self._fetch_models(self.b_url.get().strip(), self.b_model, self.b_refresh_btn, self.b_model_status, None)))
        self.b_refresh_btn.grid(row=2, column=5, padx=6, pady=6)
        ttk.Label(agent_frame, text='Preset:').grid(row=2, column=6, sticky='w', padx=(12,6), pady=6)
        self.b_preset = ttk.Combobox(agent_frame, width=20, values=[])
        self.b_preset.grid(row=2, column=7, sticky='w', pady=6)
        self.b_preset.bind('<<ComboboxSelected>>', lambda e: self._apply_preset(self.b_preset.get(), self.b_age, self.b_quirk, self.b_persona))
        ttk.Label(agent_frame, text='Persona:').grid(row=3, column=0, sticky='w', padx=(0,6), pady=6)
        self.b_persona = ttk.Entry(agent_frame, width=36)
        self.b_persona.grid(row=3, column=1, sticky='w', pady=6)
        ttk.Label(agent_frame, text='Name:').grid(row=3, column=6, sticky='w', padx=(12,6), pady=6)
        self.b_name = ttk.Entry(agent_frame, width=12)
        self.b_name.grid(row=3, column=7, sticky='w', pady=6)
        ttk.Label(agent_frame, text='Age:').grid(row=3, column=2, sticky='w', padx=(12,6), pady=6)
        self.b_age = ttk.Entry(agent_frame, width=12)
        self.b_age.grid(row=3, column=3, sticky='w', pady=6)
        ttk.Label(agent_frame, text='Quirk:').grid(row=3, column=4, sticky='w', padx=(12,6), pady=6)
        self.b_quirk = ttk.Combobox(agent_frame, width=20, values=quirk_list)
        self.b_quirk.grid(row=3, column=5, sticky='w', pady=6)
        self.b_quirk.set('')


        # --- Separator ---
        ttk.Separator(self.chat_tab, orient='horizontal').pack(fill='x', padx=6, pady=6)

        # --- Runtime Options ---
        runtime_frame = ttk.LabelFrame(self.chat_tab, text='Runtime Options')
        runtime_frame.pack(fill='x', padx=6, pady=(0,6), anchor='n')
        # ... (runtime options code remains unchanged) ...

        # --- Chat Output ---
        chat_frame = ttk.Frame(self.chat_tab)
        chat_frame.pack(fill='both', expand=True, padx=6, pady=6)
        self.chat_text = ScrolledText(chat_frame, wrap='word', height=20, state='normal')
        self.chat_text.pack(fill='both', expand=True)
        self.chat_text.insert('end', 'Welcome to Ollama Two-Agent Chat!\n')
        self.chat_text.config(state='disabled')

        # --- Chat Controls ---
        controls_frame = ttk.Frame(self.chat_tab)
        controls_frame.pack(fill='x', padx=6, pady=(0,6))
        self.user_input = ttk.Entry(controls_frame)
        self.user_input.pack(side='left', fill='x', expand=True, padx=(0,6))
        self.send_btn = ttk.Button(controls_frame, text='Send', command=self._on_send)
        self.send_btn.pack(side='left')
        self.stop_btn = ttk.Button(controls_frame, text='Stop', command=self._on_stop)
        self.stop_btn.pack(side='left', padx=(6,0))
        self.clear_btn = ttk.Button(controls_frame, text='Clear Chat', command=self._clear_chat)
        self.clear_btn.pack(side='left', padx=(6,0))

        # Chat-tab compact connection indicators (Agent A / Agent B)
        models_frame = ttk.Frame(controls_frame)
        models_frame.pack(side='right', padx=(6,0))
        ttk.Label(models_frame, text='A').grid(row=0, column=0, sticky='e')
        self.a_status_dot = ttk.Label(models_frame, text='●', foreground='gray')
        self.a_status_dot.grid(row=0, column=1, padx=(6,8))
        ttk.Label(models_frame, text='B').grid(row=1, column=0, sticky='e')
        self.b_status_dot = ttk.Label(models_frame, text='●', foreground='gray')
        self.b_status_dot.grid(row=1, column=1, padx=(6,8))

        # --- Status Bar with Turn Count ---
        self.status_var = tk.StringVar(value='Ready.')
        self.turn_count_var = tk.StringVar(value='')
        status_frame = ttk.Frame(self.chat_tab)
        status_frame.pack(fill='x', side='bottom', padx=0, pady=(0,0))
        status_label = ttk.Label(status_frame, textvariable=self.status_var, anchor='w', relief='sunken')
        status_label.pack(side='left', fill='x', expand=True)
        turn_label = ttk.Label(status_frame, textvariable=self.turn_count_var, anchor='e', relief='sunken', width=12)
        turn_label.pack(side='right')


    # Model management controls (pull/refresh/remove) moved to Settings tab

        # Runtime controls (temperature, max tokens, top_p, stop, stream)
        runtime_frame = ttk.LabelFrame(self.chat_tab, text='Runtime Options')
        runtime_frame.pack(fill='x', padx=6, pady=(0,6))
        # --- Agent A runtime options with tooltips ---
        a_temp_label = ttk.Label(runtime_frame, text='A Temp:')
        a_temp_label.grid(row=0, column=0, sticky='w')
        self.a_temp = tk.DoubleVar(value=0.7)
        a_temp_spin = ttk.Spinbox(runtime_frame, from_=0.0, to=2.0, increment=0.01, textvariable=self.a_temp, width=6)
        a_temp_spin.grid(row=0, column=1)
        Tooltip(a_temp_label, 'Temperature: Controls randomness. Higher values = more creative, lower = more focused.')
        Tooltip(a_temp_spin, 'Temperature: Controls randomness. Higher values = more creative, lower = more focused.')

        a_max_tokens_label = ttk.Label(runtime_frame, text='A Max Tokens:')
        a_max_tokens_label.grid(row=0, column=2, sticky='w')
        self.a_max_tokens = tk.IntVar(value=512)
        a_max_tokens_spin = ttk.Spinbox(runtime_frame, from_=1, to=4096, textvariable=self.a_max_tokens, width=7)
        a_max_tokens_spin.grid(row=0, column=3)
        Tooltip(a_max_tokens_label, 'Max Tokens: Maximum number of tokens (words/pieces) the model can generate in a response.')
        Tooltip(a_max_tokens_spin, 'Max Tokens: Maximum number of tokens (words/pieces) the model can generate in a response.')

        a_top_p_label = ttk.Label(runtime_frame, text='A Top-p:')
        a_top_p_label.grid(row=0, column=4, sticky='w')
        self.a_top_p = tk.DoubleVar(value=1.0)
        a_top_p_spin = ttk.Spinbox(runtime_frame, from_=0.0, to=1.0, increment=0.01, textvariable=self.a_top_p, width=6)
        a_top_p_spin.grid(row=0, column=5)
        Tooltip(a_top_p_label, 'Top-p: Nucleus sampling. Lower values = more focused, higher = more random.')
        Tooltip(a_top_p_spin, 'Top-p: Nucleus sampling. Lower values = more focused, higher = more random.')

        a_stop_label = ttk.Label(runtime_frame, text='A Stop:')
        a_stop_label.grid(row=0, column=6, sticky='w')
        self.a_stop = ttk.Entry(runtime_frame, width=12)
        self.a_stop.grid(row=0, column=7)
        Tooltip(a_stop_label, 'Stop: Comma-separated list of tokens. Model will stop generating if any are produced.')
        Tooltip(self.a_stop, 'Stop: Comma-separated list of tokens. Model will stop generating if any are produced.')

        self.a_stream = tk.BooleanVar(value=False)
        a_stream_btn = ttk.Checkbutton(runtime_frame, text='A Stream', variable=self.a_stream)
        a_stream_btn.grid(row=0, column=8, padx=4)
        Tooltip(a_stream_btn, 'Stream: If enabled, model output appears as it is generated (faster feedback).')

        # --- Agent B runtime options with tooltips ---
        b_temp_label = ttk.Label(runtime_frame, text='B Temp:')
        b_temp_label.grid(row=1, column=0, sticky='w')
        self.b_temp = tk.DoubleVar(value=0.7)
        b_temp_spin = ttk.Spinbox(runtime_frame, from_=0.0, to=2.0, increment=0.01, textvariable=self.b_temp, width=6)
        b_temp_spin.grid(row=1, column=1)
        Tooltip(b_temp_label, 'Temperature: Controls randomness. Higher values = more creative, lower = more focused.')
        Tooltip(b_temp_spin, 'Temperature: Controls randomness. Higher values = more creative, lower = more focused.')

        b_max_tokens_label = ttk.Label(runtime_frame, text='B Max Tokens:')
        b_max_tokens_label.grid(row=1, column=2, sticky='w')
        self.b_max_tokens = tk.IntVar(value=512)
        b_max_tokens_spin = ttk.Spinbox(runtime_frame, from_=1, to=4096, textvariable=self.b_max_tokens, width=7)
        b_max_tokens_spin.grid(row=1, column=3)
        Tooltip(b_max_tokens_label, 'Max Tokens: Maximum number of tokens (words/pieces) the model can generate in a response.')
        Tooltip(b_max_tokens_spin, 'Max Tokens: Maximum number of tokens (words/pieces) the model can generate in a response.')

        b_top_p_label = ttk.Label(runtime_frame, text='B Top-p:')
        b_top_p_label.grid(row=1, column=4, sticky='w')
        self.b_top_p = tk.DoubleVar(value=1.0)
        b_top_p_spin = ttk.Spinbox(runtime_frame, from_=0.0, to=1.0, increment=0.01, textvariable=self.b_top_p, width=6)
        b_top_p_spin.grid(row=1, column=5)
        Tooltip(b_top_p_label, 'Top-p: Nucleus sampling. Lower values = more focused, higher = more random.')
        Tooltip(b_top_p_spin, 'Top-p: Nucleus sampling. Lower values = more focused, higher = more random.')

        b_stop_label = ttk.Label(runtime_frame, text='B Stop:')
        b_stop_label.grid(row=1, column=6, sticky='w')
        self.b_stop = ttk.Entry(runtime_frame, width=12)
        self.b_stop.grid(row=1, column=7)
        Tooltip(b_stop_label, 'Stop: Comma-separated list of tokens. Model will stop generating if any are produced.')
        Tooltip(self.b_stop, 'Stop: Comma-separated list of tokens. Model will stop generating if any are produced.')

        self.b_stream = tk.BooleanVar(value=False)
        b_stream_btn = ttk.Checkbutton(runtime_frame, text='B Stream', variable=self.b_stream)
        b_stream_btn.grid(row=1, column=8, padx=4)
        Tooltip(b_stream_btn, 'Stream: If enabled, model output appears as it is generated (faster feedback).')

        ctrl_frame = ttk.Frame(self.chat_tab)
        ctrl_frame.pack(fill='x', padx=6, pady=(0,6))
        ttk.Label(ctrl_frame, text='Topic').grid(row=0, column=0, sticky='w')
        self.topic = ttk.Entry(ctrl_frame, width=40)
        self.topic.insert(0, 'the benefits of remote work')
        self.topic.grid(row=0, column=1, sticky='w')
        self.clear_topic_btn = ttk.Button(ctrl_frame, text='Clear Topic', command=lambda: self.topic.delete(0, 'end'))
        self.clear_topic_btn.grid(row=0, column=1, sticky='e', padx=(0, 2))
        ttk.Label(ctrl_frame, text='Turns').grid(row=0, column=2, sticky='w')
        self.turns = tk.IntVar(value=10)
        ttk.Spinbox(ctrl_frame, from_=1, to=1000, textvariable=self.turns, width=5).grid(row=0, column=3)
        ttk.Label(ctrl_frame, text='Delay(s)').grid(row=0, column=4, sticky='w')
        self.delay = tk.DoubleVar(value=1.0)
        ttk.Spinbox(ctrl_frame, from_=0.0, to=60.0, increment=0.1, textvariable=self.delay, width=6).grid(row=0, column=5)
        self.humanize_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl_frame, text='Humanize', variable=self.humanize_var).grid(row=0, column=6, padx=6)
        ttk.Label(ctrl_frame, text='Greeting').grid(row=1, column=0, sticky='w')
        self.greeting = ttk.Entry(ctrl_frame, width=40)
        self.greeting.grid(row=1, column=1, sticky='w')
        ttk.Label(ctrl_frame, text='Max chars A').grid(row=1, column=2, sticky='w')
        self.max_chars_a = tk.IntVar(value=120)
        ttk.Spinbox(ctrl_frame, from_=0, to=10000, textvariable=self.max_chars_a, width=7).grid(row=1, column=3)
        # Place Max chars B on the same line as Max chars A
        ttk.Label(ctrl_frame, text='Max chars B').grid(row=1, column=4, sticky='w')
        self.max_chars_b = tk.IntVar(value=120)
        ttk.Spinbox(ctrl_frame, from_=0, to=10000, textvariable=self.max_chars_b, width=7).grid(row=1, column=5)
        # Move short-turn and log options to the next row to avoid overlap
        self.short_turn_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(ctrl_frame, text='Short-turn', variable=self.short_turn_var).grid(row=2, column=2, padx=6)
        self.log_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl_frame, text='Log to file', variable=self.log_var).grid(row=2, column=3, padx=6)
        self.log_path = ttk.Entry(ctrl_frame, width=30)
        self.log_path.insert(0, '')
        self.log_path.grid(row=2, column=4, sticky='w')
        self.close_on_exit_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(ctrl_frame, text='Close terminal on exit', variable=self.close_on_exit_var).grid(row=2, column=5, padx=6)
        # Place run controls grouped to the right of the same row as max chars
        self.start_btn = ttk.Button(ctrl_frame, text='Start', command=self.start)
        self.start_btn.grid(row=1, column=6, padx=6)
        self.stop_btn = ttk.Button(ctrl_frame, text='Stop', command=self.stop, state='disabled')
        self.stop_btn.grid(row=1, column=7, padx=6)
        self.reset_btn = ttk.Button(ctrl_frame, text='Reset Defaults', command=self.reset_defaults)
        self.reset_btn.grid(row=1, column=8, padx=6)
        # Save & Exit button
        self.save_exit_btn = ttk.Button(ctrl_frame, text='Save && Exit', command=self._save_and_exit)
        self.save_exit_btn.grid(row=2, column=8, padx=6)

        self._model_status_log = []
        self._init_settings_tab()
        # Schedule model refreshes after settings tab is created
        try:
            self.root.after(100, self._refresh_a_models)
            self.root.after(200, self._refresh_b_models)
        except Exception:
            pass
        # Load persona presets and populate preset selectors
        try:
            self.load_personas()
            preset_names = list(self.persona_presets.keys())
            try:
                if hasattr(self, 'a_preset'):
                    self.a_preset['values'] = preset_names
                if hasattr(self, 'b_preset'):
                    self.b_preset['values'] = preset_names
                if preset_names:
                    try: self.a_preset.set(preset_names[0])
                    except Exception: pass
                    try: self.b_preset.set(preset_names[0])
                    except Exception: pass
            except Exception:
                pass
        except Exception:
            pass

    def _init_settings_tab(self):
        # Clear and rebuild the Settings tab model management menu
        for widget in self.settings_tab.winfo_children():
            widget.destroy()
        st = ttk.Frame(self.settings_tab)
        st.pack(fill='both', expand=True, padx=12, pady=12)
        ttk.Label(st, text='Chat Output Formatting:').grid(row=0, column=0, sticky='w', padx=6, pady=4)
        self.formatting_var = tk.StringVar(value='plain')
        formatting_options = [
            ('plain', 'Plain Text: No formatting, just text.'),
            ('markdown', 'Markdown: Supports *bold*, _italic_, code, lists, and more.'),
            ('raw', 'Raw Model Output: Shows exactly what the model returns.'),
        ]
        row = 1
        for val, desc in formatting_options:
            rb = ttk.Radiobutton(st, text=val.capitalize(), variable=self.formatting_var, value=val)
            rb.grid(row=row, column=0, sticky='w', padx=12)
            ttk.Label(st, text=desc, wraplength=400, foreground='#555').grid(row=row, column=1, sticky='w', padx=4)
            row += 1

        model_mgmt = ttk.LabelFrame(self.settings_tab, text='Model Management')
        model_mgmt.pack(fill='x', padx=6, pady=(12,6))

        self.model_busy_var = tk.StringVar(value='')
        self.model_busy_label = ttk.Label(model_mgmt, textvariable=self.model_busy_var, foreground='blue')
        self.model_busy_label.grid(row=0, column=0, columnspan=2, sticky='w', pady=(0,4))

        ttk.Label(model_mgmt, text='Agent A Models:').grid(row=1, column=0, sticky='w')
        self.a_model_list = tk.Listbox(model_mgmt, width=32, height=6)
        self.a_model_list.grid(row=2, column=0, sticky='w', padx=2)
        self.a_model_list.bind('<<ListboxSelect>>', lambda e: self._show_model_details('a'))
        self.a_model_entry = ttk.Entry(model_mgmt, width=30)
        self.a_model_entry.grid(row=3, column=0, sticky='w', padx=2, pady=(2,0))
        self.a_model_entry.insert(0, '')
        self.refresh_a_btn = ttk.Button(model_mgmt, text='Refresh A', command=lambda: (self.save_config(), self._fetch_models(self.a_url.get().strip(), self.a_model, self.refresh_a_btn, self.a_model_status, None, agent='a_settings')))
        self.refresh_a_btn.grid(row=4, column=0, sticky='w', padx=2, pady=2)
        self.pull_a_btn = ttk.Button(model_mgmt, text='Pull → Agent A', command=lambda: self._pull_to_urls([self.a_url.get().strip()], self._get_model_to_pull('a')))
        self.pull_a_btn.grid(row=5, column=0, padx=4, pady=2)
        self.remove_a_btn = ttk.Button(model_mgmt, text='Remove from A', command=lambda: self._remove_model(self.a_url.get().strip(), self._get_selected_model(self.a_model_list)))
        self.remove_a_btn.grid(row=6, column=0, padx=4, pady=2)

        ttk.Label(model_mgmt, text='Agent B Models:').grid(row=1, column=1, sticky='w')
        self.b_model_list = tk.Listbox(model_mgmt, width=32, height=6)
        self.b_model_list.grid(row=2, column=1, sticky='w', padx=2)
        self.b_model_list.bind('<<ListboxSelect>>', lambda e: self._show_model_details('b'))
        self.b_model_entry = ttk.Entry(model_mgmt, width=30)
        self.b_model_entry.grid(row=3, column=1, sticky='w', padx=2, pady=(2,0))
        self.b_model_entry.insert(0, '')
        self.refresh_b_btn = ttk.Button(model_mgmt, text='Refresh B', command=lambda: (self.save_config(), self._fetch_models(self.b_url.get().strip(), self.b_model, self.refresh_b_btn, self.b_model_status, None, agent='b_settings')))
        self.refresh_b_btn.grid(row=4, column=1, sticky='w', padx=2, pady=2)
        self.pull_b_btn = ttk.Button(model_mgmt, text='Pull → Agent B', command=lambda: self._pull_to_urls([self.b_url.get().strip()], self._get_model_to_pull('b')))
        self.pull_b_btn.grid(row=5, column=1, padx=4, pady=2)
        self.remove_b_btn = ttk.Button(model_mgmt, text='Remove from B', command=lambda: self._remove_model(self.b_url.get().strip(), self._get_selected_model(self.b_model_list)))
        self.remove_b_btn.grid(row=6, column=1, padx=4, pady=2)

        self.pull_both_btn = ttk.Button(model_mgmt, text='Pull → Both', command=lambda: self._pull_to_urls([self.a_url.get().strip(), self.b_url.get().strip()], self._get_model_to_pull('both')))
        self.pull_both_btn.grid(row=7, column=0, columnspan=2, padx=4, pady=2)

        self.model_details_text = tk.Text(model_mgmt, height=6, width=70, wrap='word', foreground='#222', background='#f8f8ff', borderwidth=1, relief='solid', cursor='xterm')
        self.model_details_text.grid(row=8, column=0, columnspan=2, sticky='we', pady=(8,2))
        self.model_details_text.config(state='normal')
        self.model_details_text.bind('<1>', lambda e: self.model_details_text.focus_set())
        self.model_details_text.tag_configure('error', foreground='red')
        self.model_details_text.tag_configure('warning', foreground='orange')
        self.model_details_text.tag_configure('info', foreground='#222')
        self.copy_all_btn = ttk.Button(model_mgmt, text='Copy All', command=self._copy_model_details)
        self.copy_all_btn.grid(row=9, column=1, sticky='e', pady=(2,6))

        # --- Brain Viewer / Wipe ---
        brain_frame = ttk.LabelFrame(self.settings_tab, text='Brain')
        brain_frame.pack(fill='both', padx=6, pady=(12,6))
        self.brain_text = ScrolledText(brain_frame, height=10, wrap='word')
        self.brain_text.pack(fill='both', expand=True, padx=4, pady=4)
        btn_frame = ttk.Frame(brain_frame)
        btn_frame.pack(fill='x', padx=4, pady=(0,6))
        self.brain_reload_btn = ttk.Button(btn_frame, text='Reload Brain', command=self._load_brain_view)
        self.brain_reload_btn.pack(side='left')
        self.brain_wipe_btn = ttk.Button(btn_frame, text='Wipe Brain', command=self._wipe_brain)
        self.brain_wipe_btn.pack(side='left', padx=(8,0))
        Tooltip(self.brain_wipe_btn, 'Permanently clear brain.json history (irreversible)')
        # Load initial brain view
        try:
            self._load_brain_view()
        except Exception:
            pass

    def _get_model_to_pull(self, agent):
        # Returns the model name to pull for the given agent: entry field if non-empty, else selected from list
        if agent == 'a':
            name = self.a_model_entry.get().strip()
            if name:
                return name
            return self._get_selected_model(self.a_model_list)
        elif agent == 'b':
            name = self.b_model_entry.get().strip()
            if name:
                return name
            return self._get_selected_model(self.b_model_list)
        elif agent == 'both':
            # Prefer Agent A entry, then B, then selected from either list
            name = self.a_model_entry.get().strip()
            if name:
                return name
            name = self.b_model_entry.get().strip()
            if name:
                return name
            return self._get_selected_model(self.a_model_list) or self._get_selected_model(self.b_model_list)
        return None
    def _show_model_details(self, agent):
        # Always show both model details and the persistent log
        model = None
        if agent == 'a':
            sel = self.a_model_list.curselection()
            if sel:
                model = self.a_model_list.get(sel[0])
        elif agent == 'b':
            sel = self.b_model_list.curselection()
            if sel:
                model = self.b_model_list.get(sel[0])
        details = ''
        if model:
            info = None
            if hasattr(self, '_models_info') and agent in self._models_info:
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
        self.model_details_text.config(state='normal')
        self.model_details_text.delete('1.0', 'end')
        # Always show model details for current selection
        if details is None:
            # Try to get current selection from A or B
            model = None
            agent = None
            if self.a_model_list.curselection():
                agent = 'a'
                model = self.a_model_list.get(self.a_model_list.curselection()[0])
            elif self.b_model_list.curselection():
                agent = 'b'
                model = self.b_model_list.get(self.b_model_list.curselection()[0])
            if model:
                info = None
                if hasattr(self, '_models_info') and agent in self._models_info:
                    info = self._models_info[agent].get(model)
                if info:
                    details = f"Model: {model}\n"
                    for k, v in info.items():
                        details += f"{k.capitalize()}: {v}\n"
                    details = details.strip()
                else:
                    details = f"Model: {model}"
            else:
                details = ''
        if details:
            self.model_details_text.insert('end', details + '\n', 'info')
            self.model_details_text.insert('end', '-'*60 + '\n', 'info')
        # Show status/error log (last 20)
        for ts, msg, level in self._model_status_log[-20:]:
            tag = level if level in ('error','warning','info') else 'info'
            self.model_details_text.insert('end', f'[{ts}] {msg}\n', tag)
        self.model_details_text.see('end')
        self.model_details_text.config(state='normal')

    def _add_model_status(self, msg, level='info'):
        import datetime
        ts = datetime.datetime.now().strftime('%H:%M:%S')
        self._model_status_log.append((ts, msg, level))
        # Only keep last 50 messages
        if len(self._model_status_log) > 50:
            self._model_status_log = self._model_status_log[-50:]
        self._update_model_details_box()

    def _copy_model_details(self):
        self.model_details_text.focus_set()
        self.root.clipboard_clear()
        text = self.model_details_text.get('1.0', 'end').strip()
        self.root.clipboard_append(text)

    def _set_model_busy(self, msg):
        self.model_busy_var.set(msg)
        self.model_busy_label.update_idletasks()

    def _clear_model_busy(self):
        self.model_busy_var.set('')
        self.model_busy_label.update_idletasks()

    def _save_and_exit(self):
        try:
            self.save_config()
        except Exception as e:
            messagebox.showerror('Save Error', f'Failed to save config: {e}')
        self.root.quit()

    def _get_selected_model(self, listbox):
        try:
            selection = listbox.curselection()
            if selection:
                return listbox.get(selection[0])
        except Exception:
            pass
        return ''

    def _load_brain_view(self):
        try:
            b = brain.load_brain()
            pretty = json.dumps(b, indent=2, ensure_ascii=False)
        except Exception as e:
            pretty = f'Error loading brain: {e}'
        try:
            self.brain_text.config(state='normal')
            self.brain_text.delete('1.0', 'end')
            self.brain_text.insert('1.0', pretty)
            self.brain_text.config(state='disabled')
        except Exception:
            pass

    def _wipe_brain(self):
        if not messagebox.askyesno('Wipe Brain', 'Are you sure you want to permanently wipe brain.json?'):
            return
        try:
            empty = {'history': []}
            brain.save_brain(empty)
            self._add_model_status('Brain wiped by user', 'warning')
            self._load_brain_view()
            messagebox.showinfo('Wipe Brain', 'brain.json has been wiped.')
        except Exception as e:
            messagebox.showerror('Wipe Brain', f'Failed to wipe brain.json: {e}')


    def _refresh_a_models(self):
        self._set_model_busy('Refreshing Agent A models...')
        self.root.after(100, lambda: self._fetch_models(self.a_url.get().strip(), self.a_model, self.refresh_a_btn, self.a_model_status, None, agent='a_settings'))

    def _refresh_b_models(self):
        self._set_model_busy('Refreshing Agent B models...')
        self.root.after(100, lambda: self._fetch_models(self.b_url.get().strip(), self.b_model, self.refresh_b_btn, self.b_model_status, None, agent='b_settings'))

    def _refresh_chat_tab_model_selectors(self):
        """Synchronize the Chat-tab comboboxes with the Settings tab model lists."""
        try:
            a_vals = []
            b_vals = []
            try:
                if hasattr(self, 'a_model_list'):
                    a_vals = list(self.a_model_list.get(0, tk.END))
            except Exception:
                a_vals = []
            try:
                if hasattr(self, 'b_model_list'):
                    b_vals = list(self.b_model_list.get(0, tk.END))
            except Exception:
                b_vals = []
            # Update the main runtime comboboxes in the Chat tab
            try:
                if hasattr(self, 'a_model'):
                    try:
                        self.a_model['values'] = a_vals
                        cur = self.a_model.get()
                        if cur not in a_vals and a_vals:
                            self.a_model.set(a_vals[0])
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                if hasattr(self, 'b_model'):
                    try:
                        self.b_model['values'] = b_vals
                        cur = self.b_model.get()
                        if cur not in b_vals and b_vals:
                            self.b_model.set(b_vals[0])
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass

    # Removed _on_chat_selector_change: bottom selectors were duplicate; main comboboxes are authoritative

    def _update_models_text(self, agent, models):
        if agent == 'a_settings':
            self.a_model_list.delete(0, tk.END)
            if models:
                for m in models:
                    self.a_model_list.insert(tk.END, m)
            else:
                self.a_model_list.insert(tk.END, '(No models found or fetch failed)')
            # Auto-select and show details for first model after refresh
            self._auto_select_first_model('a')
        elif agent == 'b_settings':
            self.b_model_list.delete(0, tk.END)
            if models:
                for m in models:
                    self.b_model_list.insert(tk.END, m)
            else:
                self.b_model_list.insert(tk.END, '(No models found or fetch failed)')
            self._auto_select_first_model('b')
        # No-op for 'a' and 'b' agents as a_models_text and b_models_text widgets are not defined
        # Also refresh the Chat-tab model selectors if present
        try:
            if hasattr(self, '_refresh_chat_tab_model_selectors'):
                try:
                    self._refresh_chat_tab_model_selectors()
                except Exception:
                    pass
        except Exception:
            pass
    # Patch _fetch_models to also fetch model details if available
    # (This is a minimal patch, as the main fetch logic is in worker)
    # To support model details, we need to parse details if present in the response
    # We'll store details in self._models_info[agent] as a dict: {model_name: {details}}
    # This patch assumes the worker function is inside _fetch_models
    # Add after models are parsed:
    #   - If agent in ('a_settings', 'b_settings'), parse details and store in self._models_info[agent]
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
            self._check_model_status(self.a_url.get().strip(), self.a_model.get().strip(), self.a_model_status)
            self._check_model_status(self.b_url.get().strip(), self.b_model.get().strip(), self.b_model_status)
            # Also update the Chat-tab indicators (if present)
            try:
                if hasattr(self, 'a_status_dot'):
                    self._check_server_status(self.a_url.get().strip(), self.a_status_dot)
                    try:
                        self._check_model_status(self.a_url.get().strip(), self.a_model.get().strip(), self.a_status_dot)
                    except Exception:
                        pass
                if hasattr(self, 'b_status_dot'):
                    self._check_server_status(self.b_url.get().strip(), self.b_status_dot)
                    try:
                        self._check_model_status(self.b_url.get().strip(), self.b_model.get().strip(), self.b_status_dot)
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass
        # Schedule next poll
        self.root.after(2000, self._poll_connectivity)

    def _call_ollama_with_timeout(self, client_url, model, messages, runtime_options=None, timeout=20):
        """Call chat_with_ollama in a thread and return its result or a timeout error."""
        result = {}
        def worker():
            try:
                res = chat_with_ollama(client_url, model, messages, runtime_options=runtime_options)
            except Exception as e:
                res = {"content": f"[ERROR calling {client_url}: {e}]"}
            try:
                result['res'] = res
            except Exception:
                result['res'] = {"content": "[ERROR]"}

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            # Thread still running — return a timeout placeholder and leave the worker to finish in background
            return {"content": f"[ERROR: timeout after {timeout}s contacting {client_url}]"}
        return result.get('res', {"content": "[ERROR: no response]"})

    def load_personas(self, path=DEFAULT_PERSONAS_PATH):
        if not os.path.exists(path):
            # nothing to load
            self.persona_presets = {}
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            out = {}
            for name, v in data.items():
                if isinstance(v, dict):
                    out[name] = (str(v.get('age', '')), v.get('quirk', ''), v.get('prompt', ''))
            self.persona_presets = out
        except Exception:
            self.persona_presets = {}

    def save_config(self, path=DEFAULT_CONFIG):
        cfg = {
            'a_url': self.a_url.get().strip(),
            'b_url': self.b_url.get().strip(),
            'a_model': self.a_model.get().strip(),
            'b_model': self.b_model.get().strip(),
            'a_name': self.a_name.get().strip(),
            'b_name': self.b_name.get().strip(),
            'a_persona': self.a_persona.get().strip(),
            'b_persona': self.b_persona.get().strip(),
            'a_age': self.a_age.get().strip(),
            'b_age': self.b_age.get().strip(),
            'a_quirk': self.a_quirk.get().strip(),
            'b_quirk': self.b_quirk.get().strip(),
            'topic': self.topic.get().strip(),
            'turns': int(self.turns.get()),
            'delay': float(self.delay.get()),
            'max_chars_a': int(self.max_chars_a.get()),
            'max_chars_b': int(self.max_chars_b.get()),
            'short_turn': bool(self.short_turn_var.get()),
            'log': bool(self.log_var.get()),
            'log_path': self.log_path.get().strip(),
            'close_on_exit': bool(self.close_on_exit_var.get()),
            # Pull model management config removed
            'persona_presets': {k: {'age': v[0], 'quirk': v[1], 'prompt': v[2]} for k, v in self.persona_presets.items()},
            'a_runtime': {
                'temperature': float(self.a_temp.get()),
                'max_tokens': int(self.a_max_tokens.get()),
                'top_p': float(self.a_top_p.get()),
                'stop': [s.strip() for s in self.a_stop.get().split(',') if s.strip()],
                'stream': bool(self.a_stream.get()),
            },
            'b_runtime': {
                'temperature': float(self.b_temp.get()),
                'max_tokens': int(self.b_max_tokens.get()),
                'top_p': float(self.b_top_p.get()),
                'stop': [s.strip() for s in self.b_stop.get().split(',') if s.strip()],
                'stream': bool(self.b_stream.get()),
            },
        }
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass

    def load_config(self, path=DEFAULT_CONFIG):
        if not os.path.exists(path):
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
        except Exception:
            return
            def s(entry, val):
                try:
                    if isinstance(entry, ttk.Entry):
                        entry.delete(0, tk.END); entry.insert(0, val)
                    else:
                        entry.set(val)
                except Exception:
                    pass

            s(self.a_url, cfg.get('a_url', self.a_url.get()))
            s(self.b_url, cfg.get('b_url', self.b_url.get()))
            s(self.a_model, cfg.get('a_model', self.a_model.get()))
            s(self.b_model, cfg.get('b_model', self.b_model.get()))
            s(self.a_persona, cfg.get('a_persona', self.a_persona.get()))
            try:
                s(self.a_name, cfg.get('a_name', self.a_name.get()))
            except Exception:
                pass
            s(self.b_persona, cfg.get('b_persona', self.b_persona.get()))
            s(self.a_age, cfg.get('a_age', self.a_age.get()))
            s(self.b_age, cfg.get('b_age', self.b_age.get()))
            s(self.a_quirk, cfg.get('a_quirk', self.a_quirk.get()))
            s(self.b_quirk, cfg.get('b_quirk', self.b_quirk.get()))
            try:
                self.topic.delete(0, tk.END); self.topic.insert(0, cfg.get('topic', self.topic.get()))
            except Exception:
                pass
            try:
                self.turns.set(int(cfg.get('turns', self.turns.get())))
            except Exception:
                pass
            try:
                self.delay.set(float(cfg.get('delay', self.delay.get())))
            except Exception:
                pass
            try:
                self.max_chars_a.set(int(cfg.get('max_chars_a', self.max_chars_a.get())))
            except Exception:
                pass
            try:
                self.max_chars_b.set(int(cfg.get('max_chars_b', self.max_chars_b.get())))
            except Exception:
                pass
            try:
                self.short_turn_var.set(bool(cfg.get('short_turn', self.short_turn_var.get())))
            except Exception:
                pass
            try:
                self.log_var.set(bool(cfg.get('log', self.log_var.get())))
                self.log_path.delete(0, tk.END); self.log_path.insert(0, cfg.get('log_path', self.log_path.get()))
            except Exception:
                pass
            try:
                self.close_on_exit_var.set(bool(cfg.get('close_on_exit', self.close_on_exit_var.get())))
            except Exception:
                pass
            # load persona presets if present
            pp = cfg.get('persona_presets')
            if isinstance(pp, dict):
                try:
                    self.persona_presets = {k: (str(v.get('age','')), v.get('quirk',''), v.get('prompt','')) for k, v in pp.items()}
                    preset_names = list(self.persona_presets.keys())
                    self.a_preset['values'] = preset_names; self.b_preset['values'] = preset_names
                except Exception:
                    pass
            # Pull model management config load removed
            try:
                ar = cfg.get('a_runtime', {}) or {}
                try: self.a_temp.set(float(ar.get('temperature', self.a_temp.get())))
                except Exception: pass
                try: self.a_max_tokens.set(int(ar.get('max_tokens', self.a_max_tokens.get())))
                except Exception: pass
                try: self.a_top_p.set(float(ar.get('top_p', self.a_top_p.get())))
                except Exception: pass
                try: self.a_stop.delete(0, tk.END); self.a_stop.insert(0, ','.join(ar.get('stop', []) if isinstance(ar.get('stop', []), list) else []))
                except Exception: pass
                try: self.a_stream.set(bool(ar.get('stream', self.a_stream.get())))
                except Exception: pass
            except Exception:
                pass
            try:
                br = cfg.get('b_runtime', {}) or {}
                try: self.b_temp.set(float(br.get('temperature', self.b_temp.get())))
                except Exception: pass
                try: self.b_max_tokens.set(int(br.get('max_tokens', self.b_max_tokens.get())))
                except Exception: pass
                try: self.b_top_p.set(float(br.get('top_p', self.b_top_p.get())))
                except Exception: pass
                try: self.b_stop.delete(0, tk.END); self.b_stop.insert(0, ','.join(br.get('stop', []) if isinstance(br.get('stop', []), list) else []))
                except Exception: pass
                try: self.b_stream.set(bool(br.get('stream', self.b_stream.get())))
                except Exception: pass
            except Exception:
                pass
        try:
            s(self.b_name, cfg.get('b_name', self.b_name.get()))
        except Exception:
            pass
        except Exception:
            pass
        finally:
            pass

    def _poll_queue(self):
        def format_markdown(md):
            import re
            # Bold: **text** or __text__
            md = re.sub(r'\*\*(.*?)\*\*|__(.*?)__', lambda m: m.group(1) or m.group(2), md)
            # Italic: *text* or _text_
            md = re.sub(r'\*(.*?)\*|_(.*?)_', lambda m: m.group(1) or m.group(2), md)
            # Inline code: `code`
            md = re.sub(r'`([^`]*)`', r'[code]\1[/code]', md)
            # Code blocks: ```code```
            md = re.sub(r'```([\s\S]*?)```', r'\n[code]\1[/code]\n', md)
            # Lists: - item or * item
            md = re.sub(r'^[\s]*[-\*] (.*)', r'• \1', md, flags=re.MULTILINE)
            # Headers: # Header
            md = re.sub(r'^#+ (.*)', r'\1', md, flags=re.MULTILINE)
            # Blockquotes: > quote
            md = re.sub(r'^> (.*)', r'"\1"', md, flags=re.MULTILINE)
            return md

        try:
            while True:
                kind, text = self.queue.get_nowait()
                fmt = self.formatting_var.get() if hasattr(self, 'formatting_var') else 'plain'
                if fmt == 'plain':
                    formatted = text
                elif fmt == 'markdown':
                    formatted = format_markdown(text)
                elif fmt == 'raw':
                    formatted = text
                else:
                    formatted = text
                if kind == 'a':
                    name = self.a_name.get().strip() if hasattr(self, 'a_name') else 'Agent_A'
                    self.chat_text.config(state='normal')
                    self.chat_text.insert('end', f"{name}: " + formatted + '\n\n')
                    self.chat_text.see('end')
                    self.chat_text.config(state='disabled')
                elif kind == 'b':
                    name = self.b_name.get().strip() if hasattr(self, 'b_name') else 'Agent_B'
                    self.chat_text.config(state='normal')
                    self.chat_text.insert('end', f"{name}: " + formatted + '\n\n')
                    self.chat_text.see('end')
                    self.chat_text.config(state='disabled')
                elif kind == 'status':
                    self.status_var.set(formatted)
                    try:
                        import re
                        m = re.search(r'Turn\s*(\d+)\s*/\s*(\d+)', formatted)
                        if m:
                            try:
                                self.turn_count_var.set(f"{m.group(1)}/{m.group(2)}")
                            except Exception:
                                pass
                    except Exception:
                        pass
                elif kind == 'done':
                    self.start_btn.config(state='normal'); self.stop_btn.config(state='disabled'); self.status_var.set('Finished.')
                    try:
                        self.turn_count_var.set('')
                    except Exception:
                        pass
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.chat_text.delete('1.0', 'end')
        self.stop_event.clear()
        self.start_btn.config(state='disabled'); self.stop_btn.config(state='normal'); self.status_var.set('Running...')
        try:
            self.turn_count_var.set(f"0/{int(self.turns.get())}")
        except Exception:
            try: self.turn_count_var.set('')
            except Exception: pass
        cfg = {
            'a_url': self.a_url.get().strip(),
            'a_model': self.a_model.get().strip(),
            'a_persona': self.a_persona.get().strip(),
            'a_age': self.a_age.get().strip(),
            'a_quirk': self.a_quirk.get().strip(),
            'b_url': self.b_url.get().strip(),
            'b_model': self.b_model.get().strip(),
            'b_persona': self.b_persona.get().strip(),
            'b_age': self.b_age.get().strip(),
            'b_quirk': self.b_quirk.get().strip(),
            'topic': self.topic.get().strip(),
            'turns': int(self.turns.get()),
            'delay': float(self.delay.get()),
            'humanize': bool(self.humanize_var.get()),
            'greeting': self.greeting.get().strip() or None,
            'max_chars_a': int(self.max_chars_a.get()),
            'max_chars_b': int(self.max_chars_b.get()),
            'short_turn': bool(self.short_turn_var.get()),
            'log': bool(self.log_var.get()),
            'log_path': self.log_path.get().strip() or None,
            'a_runtime': {
                'temperature': float(self.a_temp.get()),
                'max_tokens': int(self.a_max_tokens.get()),
                'top_p': float(self.a_top_p.get()),
                'stop': [s.strip() for s in self.a_stop.get().split(',') if s.strip()],
                'stream': bool(self.a_stream.get()),
            },
            'b_runtime': {
                'temperature': float(self.b_temp.get()),
                'max_tokens': int(self.b_max_tokens.get()),
                'top_p': float(self.b_top_p.get()),
                'stop': [s.strip() for s in self.b_stop.get().split(',') if s.strip()],
                'stream': bool(self.b_stream.get()),
            },
        }
        self.thread = threading.Thread(target=self._run_conversation, args=(cfg, self.stop_event, self.queue), daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set(); self.status_var.set('Stopping...')

    def on_close(self):
        try:
            self.stop()
            if self.thread:
                try:
                    self.thread.join(timeout=1.0)
                except Exception:
                    pass
            try:
                self.save_config()
            except Exception:
                pass
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
        # Exit process only if the user enabled the option
        try:
            if getattr(self, 'close_on_exit_var', None) and self.close_on_exit_var.get():
                import os
                os._exit(0)
        except Exception:
            try:
                import sys
                sys.exit(0)
            except Exception:
                pass

    def _fetch_models(self, server_url, combobox, button, status_label=None, status_icon=None, agent=None):
        # Insert visible debug message in B Listbox at start
        if agent == 'b_settings':
            self.b_model_list.delete(0, tk.END)
            self.b_model_list.insert(tk.END, '(Refreshing...)')
            self._add_model_status('Started refreshing models for agent B', 'info')
        def worker():
            try:
                try:
                    if button:
                        button.config(state='disabled')
                except Exception:
                    pass
                if not server_url:
                    self.queue.put(('status', 'Server URL empty'))
                    if status_label is not None:
                        try: status_label.config(text='●', foreground='gray')
                        except Exception: pass
                    if agent in ('a_settings', 'b_settings'):
                        self._update_models_text(agent, [])
                    return
                endpoints = ['/models', '/v1/models', '/api/models']
                models = []
                last_exc = None
                attempts = []
                for ep in endpoints:
                    try:
                        url = server_url.rstrip('/') + ep
                        attempts.append(f'GET {url}')
                        req = urllib.request.Request(url)
                        with urllib.request.urlopen(req, timeout=1) as resp:
                            raw = resp.read()
                        try:
                            data = json.loads(raw.decode('utf-8', errors='ignore'))
                        except Exception:
                            txt = raw.decode('utf-8', errors='ignore').strip()
                            if '\n' in txt:
                                lines = [l.strip() for l in txt.splitlines() if l.strip()]
                                models.extend(lines); break
                            self.queue.put(('status', f'Got non-JSON response from {url}: {txt[:200]}'))
                            continue
                        if isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict):
                                    name = item.get('name') or item.get('model') or item.get('id')
                                    if name: models.append(name)
                                else:
                                    models.append(str(item))
                        elif isinstance(data, dict):
                            for key in ('models', 'results', 'data'):
                                if key in data and isinstance(data[key], list):
                                    for item in data[key]:
                                        if isinstance(item, dict):
                                            n = item.get('name') or item.get('model') or item.get('id') or item.get('modelId')
                                            if n: models.append(n)
                            if not models:
                                for v in data.values():
                                    if isinstance(v, str): models.append(v)
                        if models: break
                    except Exception as ie:
                        last_exc = ie; attempts.append(f'ERROR {ep}: {repr(ie)}'); continue

                def _set_icon_color(col: str):
                    try:
                        if status_label is not None:
                            color_map = {'green': 'green', 'red': 'red', 'gray': 'gray'}
                            status_label.config(text='●', foreground=color_map.get(col, 'gray'))
                    except Exception:
                        pass

                if models:
                    seen = set(); unique = []
                    for m in models:
                        if m not in seen:
                            seen.add(m); unique.append(m)
                    if combobox:
                        try:
                            combobox['values'] = unique
                            cur = combobox.get()
                            if cur not in unique and unique:
                                combobox.set(unique[0])
                        except Exception:
                            pass
                    self._add_model_status(f'Loaded {len(unique)} models from {server_url}', 'info')
                    # Always update the model list in the main GUI combobox as well
                    # Always update the correct Listbox in Settings after fetch
                    if agent == 'a_settings':
                        self._update_models_text('a_settings', unique)
                    if agent == 'b_settings':
                        self._update_models_text('b_settings', unique)
                    if status_label is not None:
                        try: _set_icon_color('green')
                        except Exception: pass
                else:
                    msg = f'No models found at {server_url}'
                    if last_exc: msg += f': {repr(last_exc)}'
                    if agent:
                        self._update_models_text(agent, [])
                    try:
                        import datetime
                        dbg_path = 'model_fetch_debug.log'
                        with open(dbg_path, 'a', encoding='utf-8') as df:
                            df.write(f'[{datetime.datetime.now().isoformat()}] Fetch models debug for {server_url}\n')
                            for a in attempts: df.write(a + '\n')
                            if last_exc: df.write('Last exception: ' + repr(last_exc) + '\n')
                            df.write('\n')
                    except Exception:
                        pass
                    self._add_model_status(msg + ' (see model_fetch_debug.log)', 'error')
                    try: messagebox.showerror('Model Fetch Failed', msg + '\n\nSee model_fetch_debug.log for details.')
                    except Exception: pass
                    if status_label is not None:
                        try: _set_icon_color('red')
                        except Exception: pass
            except Exception as e:
                self._add_model_status(f'Model fetch failed: {repr(e)}', 'error')
            finally:
                try:
                    if button:
                        button.config(state='normal')
                except Exception: pass
                if agent == 'b_settings':
                    self._add_model_status('Finished refreshing models for agent B', 'info')

        def run_and_force_update():
            worker()
            # Force update of the combobox UI in the main thread
            if combobox:
                try:
                    combobox.update_idletasks()
                except Exception:
                    pass
        threading.Thread(target=run_and_force_update, daemon=True).start()

    def _pull_now(self, server_url, model_name):
        pass

    def _pull_all(self, server_url):
        pass

    def _refresh_available_models(self):
        pass

    def _pull_to_urls(self, url_list, model_name):
        import requests
        if not url_list or not model_name:
            messagebox.showerror('Pull Model', 'No server URL or model name specified.')
            return
        for server_url in url_list:
            if not server_url:
                continue
            try:
                status_msg = f'Pulling model {model_name} to {server_url}...'
                self._set_model_busy(status_msg)
                self._add_model_status(status_msg, 'info')
                url = server_url.rstrip('/') + '/api/pull'
                resp = requests.post(url, json={"name": model_name}, timeout=30)
                if resp.status_code == 200:
                    success_msg = f'Model "{model_name}" pulled successfully to {server_url}.'
                    self._add_model_status(success_msg, 'info')
                    messagebox.showinfo('Pull Model', success_msg)
                else:
                    try:
                        err = resp.json().get('error')
                    except Exception:
                        err = resp.text
                    fail_msg = f'Failed to pull model to {server_url}: {err}'
                    self._add_model_status(fail_msg, 'error')
                    messagebox.showerror('Pull Model', fail_msg)
            except Exception as e:
                err_msg = f'Error pulling model to {server_url}: {e}'
                self._add_model_status(err_msg, 'error')
                messagebox.showerror('Pull Model', err_msg)
            finally:
                self._clear_model_busy()
                # Refresh model list for the relevant agent
                if server_url == self.a_url.get().strip():
                    self._refresh_a_models()
                elif server_url == self.b_url.get().strip():
                    self._refresh_b_models()

    def _remove_model(self, server_url, model_name):
        # Remove a model from the Ollama server using the correct API endpoint
        import requests
        if not server_url or not model_name:
            messagebox.showerror('Remove Model', 'No server URL or model name specified.')
            return
        try:
            self._set_model_busy(f'Removing model {model_name}...')
            # Ollama expects DELETE /api/delete with JSON body: {"name": "modelname"}
            url = server_url.rstrip('/') + '/api/delete'
            resp = requests.delete(url, json={"name": model_name}, timeout=10)
            if resp.status_code == 200:
                messagebox.showinfo('Remove Model', f'Model "{model_name}" removed successfully.')
            else:
                try:
                    err = resp.json().get('error')
                except Exception:
                    err = resp.text
                messagebox.showerror('Remove Model', f'Failed to remove model: {err}')
        except Exception as e:
            messagebox.showerror('Remove Model', f'Error removing model: {e}')
        finally:
            self._clear_model_busy()
            # Refresh model list for the relevant agent
            if server_url == self.a_url.get().strip():
                self._refresh_a_models()
            elif server_url == self.b_url.get().strip():
                self._refresh_b_models()

    def _apply_preset(self, preset_name, age_cb, quirk_cb, persona_entry):
        try:
            if not preset_name: return
            v = self.persona_presets.get(preset_name)
            if not v: return
            age, quirk, persona_text = v
            try: age_cb.set(age)
            except Exception: pass
            try:
                quirk_cb.set(quirk)
            except Exception:
                try:
                    quirk_cb.delete(0, tk.END)
                    quirk_cb.insert(0, quirk)
                except Exception:
                    pass
            try: persona_entry.delete(0, tk.END); persona_entry.insert(0, persona_text)
            except Exception: pass
            try: self.queue.put(('status', f'Applied preset: {preset_name}'))
            except Exception: pass
        except Exception:
            pass

    def reset_defaults(self):
        try:
            self.a_url.delete(0, tk.END); self.a_url.insert(0, 'http://localhost:11434')
        except Exception: pass
        try:
            self.b_url.delete(0, tk.END); self.b_url.insert(0, 'http://192.168.127.121:11434')
        except Exception: pass
        try: self.a_model.set('llama2')
        except Exception: pass
        try: self.b_model.set('llama2')
        except Exception: pass
        try: self.a_persona.delete(0, tk.END); self.a_persona.insert(0, '')
        except Exception: pass
        try: self.b_persona.delete(0, tk.END); self.b_persona.insert(0, '')
        except Exception: pass
        try:
            self.a_age.delete(0, tk.END)
            self.a_age.insert(0, '45')
            self.b_age.delete(0, tk.END)
            self.b_age.insert(0, '28')
        except Exception:
            pass
        try:
            self.a_quirk.delete(0, tk.END)
            self.a_quirk.insert(0, 'polite phrasing')
            self.b_quirk.delete(0, tk.END)
            self.b_quirk.insert(0, 'uses slang')
        except Exception:
            pass
        try:
            try:
                self.a_name.delete(0, tk.END); self.a_name.insert(0, 'Ava')
            except Exception:
                pass
            try:
                self.b_name.delete(0, tk.END); self.b_name.insert(0, 'Orion')
            except Exception:
                pass
        except Exception:
            pass
        try: self.max_chars_a.set(120); self.max_chars_b.set(120)
        except Exception: pass
        try: self.short_turn_var.set(True)
        except Exception: pass
        # restore default presets
        self.load_personas()
        try:
            preset_names = list(self.persona_presets.keys())
            self.a_preset['values'] = preset_names; self.b_preset['values'] = preset_names
            if preset_names: self.a_preset.set(preset_names[0]); self.b_preset.set(preset_names[0])
        except Exception: pass
        self.queue.put(('status', 'Defaults restored'))
        try: self.save_config()
        except Exception: pass

    def _run_conversation(self, cfg, stop_event, queue):
        log_file = None
        try:
            topic = cfg['topic']
            try:
                queue.put(('status', f"Using topic: {topic}"))
            except Exception:
                pass
            def build_persona(base, age, quirk):
                parts = []
                if base: parts.append(base)
                if age: parts.append(f"Age: {age}")
                if quirk: parts.append(f"Quirk: {quirk}")
                return ' | '.join(parts) if parts else ''

            persona_a = build_persona(cfg.get('a_persona'), cfg.get('a_age'), cfg.get('a_quirk'))
            persona_b = build_persona(cfg.get('b_persona'), cfg.get('b_age'), cfg.get('b_quirk'))

            name_a = (self.a_name.get().strip() if hasattr(self, 'a_name') else 'Agent_A')
            name_b = (self.b_name.get().strip() if hasattr(self, 'b_name') else 'Agent_B')
            instruction = (
                "Important: In every reply, explicitly reference the discussion topic and keep responses focused on it. "
                "Begin each response by briefly restating the topic and avoid unrelated tangents."
            )
            sys_a = f"{instruction} You are {name_a}. Discuss '{topic}' with {name_b}. {persona_a}".strip()
            sys_b = f"{instruction} You are {name_b}. Discuss '{topic}' with {name_a}. {persona_b}".strip()

            messages_a = [{'role': 'system', 'content': sys_a}]
            messages_b = [{'role': 'system', 'content': sys_b}]

            if cfg['humanize']:
                initial_prompt = cfg['greeting'] or 'Hello, how are you?'
            else:
                initial_prompt = f"Let's discuss {topic}. I think..."

            queue.put(('b', f"(initial) {initial_prompt}"))
            messages_b.append({'role': 'user', 'content': initial_prompt})
            try:
                name_b = (self.b_name.get().strip() if hasattr(self, 'b_name') else 'Agent_B')
                brain.add_to_brain(name_b, initial_prompt, 'user')
            except Exception:
                pass

            turns = cfg['turns']; delay = cfg['delay']
            a_url = cfg['a_url']; b_url = cfg['b_url']
            a_model = cfg['a_model']; b_model = cfg['b_model']

            log_file = None
            if cfg.get('log') and cfg.get('log_path'):
                try: log_file = open(cfg.get('log_path'), 'a', encoding='utf-8')
                except Exception: log_file = None

            def ts():
                from datetime import datetime
                return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            def trunc(text: str, agent: str) -> str:
                if not text: return ''
                t = text.strip()
                maxc = cfg.get('max_chars_a') if agent == 'a' else cfg.get('max_chars_b')
                if cfg.get('short_turn'):
                    import re
                    m = re.search(r"(.+?[.!?])(\s|$)", t, re.S)
                    if m: s = m.group(1).strip()
                    else:
                        parts = re.split(r'[,;:\\-]\s*', t, maxsplit=1); s = parts[0].strip()
                    limit = maxc if maxc and maxc > 0 else 120
                    if len(s) > limit: s = s[:limit].rstrip();
                    if not s.endswith(('.', '!', '?')): s = s.rstrip(' ,;:') + '…'
                    return s
                if maxc and maxc > 0:
                    s = t[:maxc].strip()
                    if len(t) > maxc and not s.endswith(('.', '!', '?')): s = s.rstrip(' ,;:') + '…'
                    return s
                return t


            for i in range(turns):
                if stop_event.is_set():
                    break
                queue.put(('status', f'Turn {i+1}/{turns}'))

                # pass runtime options for Agent B
                b_runtime = {
                    'temperature': float(cfg.get('b_runtime', {}).get('temperature', 0.7)),
                    'max_tokens': int(cfg.get('b_runtime', {}).get('max_tokens', 512)),
                    'top_p': float(cfg.get('b_runtime', {}).get('top_p', 1.0)),
                    'stop': cfg.get('b_runtime', {}).get('stop') or None,
                    'stream': bool(cfg.get('b_runtime', {}).get('stream', False)),
                }
                resp_b = self._call_ollama_with_timeout(b_url, b_model, messages_b, runtime_options=b_runtime, timeout=20)
                content_b = trunc(resp_b.get('content', ''), 'b')
                queue.put(('b', content_b))
                try:
                    name_b = (self.b_name.get().strip() if hasattr(self, 'b_name') else 'Agent_B')
                    brain.add_to_brain(name_b, content_b, 'assistant')
                except Exception:
                    pass
                if log_file:
                    try:
                        log_file.write(f"[{ts()}] B: {content_b}\n"); log_file.flush()
                    except Exception:
                        pass
                messages_b.append({'role': 'assistant', 'content': content_b})
                messages_a.append({'role': 'user', 'content': content_b})

                if stop_event.is_set():
                    break

                a_runtime = {
                    'temperature': float(cfg.get('a_runtime', {}).get('temperature', 0.7)),
                    'max_tokens': int(cfg.get('a_runtime', {}).get('max_tokens', 512)),
                    'top_p': float(cfg.get('a_runtime', {}).get('top_p', 1.0)),
                    'stop': cfg.get('a_runtime', {}).get('stop') or None,
                    'stream': bool(cfg.get('a_runtime', {}).get('stream', False)),
                }
                resp_a = self._call_ollama_with_timeout(a_url, a_model, messages_a, runtime_options=a_runtime, timeout=20)
                content_a = trunc(resp_a.get('content', ''), 'a')
                queue.put(('a', content_a))
                try:
                    name_a = (self.a_name.get().strip() if hasattr(self, 'a_name') else 'Agent_A')
                    brain.add_to_brain(name_a, content_a, 'assistant')
                except Exception:
                    pass
                if log_file:
                    try:
                        log_file.write(f"[{ts()}] A: {content_a}\n"); log_file.flush()
                    except Exception:
                        pass
                messages_a.append({'role': 'assistant', 'content': content_a})
                messages_b.append({'role': 'user', 'content': content_a})

                # Only sleep if not stopping
                if stop_event.is_set():
                    break
                time.sleep(delay)

        except Exception as e:
            queue.put(('status', f'Error: {e}'))
        finally:
            try:
                if log_file: log_file.close()
            except Exception: pass
            queue.put(('done', ''))


def main():
    root = tk.Tk()
    app = OllamaGUI(root)

    try:
        # Always start with the built-in defaults rather than loading previous config
        app.reset_defaults()
    except Exception:
        pass
    # Ensure model lists auto-refresh after config is loaded and widgets are ready
    root.after(100, app._refresh_a_models)
    root.after(200, app._refresh_b_models)
    root.mainloop()


if __name__ == '__main__':
    main()
