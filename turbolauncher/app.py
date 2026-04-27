#!/usr/bin/env python3
"""TurboLauncher - Tkinter GUI for launching llama-server.

This Python launcher mirrors the existing TurboLauncher data formats:
presets/*.json, models.registry, model-configs/*.cfg, and the session files in
%APPDATA%\TurboLauncher.
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
import webbrowser
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from .command_builder import args_to_list, build_command_args, command_string
from .core import LauncherCore, sanitize_alias
from .models import ModelEntry, detect_quant
from .monitoring import (
    get_cpu_usage,
    get_gpu_info,
    get_ram_usage,
    parse_prometheus_metrics as _parse_prometheus_metrics,
)
from .paths import (
    APP_DIR,
    APP_NAME,
    APPDATA_ROOT,
    GB,
    HF_CACHE_DIR,
    LOG_FILE,
    MODEL_CONFIGS_DIR,
    PRESETS_DIR,
    REGISTRY_FILE,
    RUNTIME_PATH_FILE,
    SESSION_DIR,
    SESSION_FILE,
    ensure_dirs,
)
from .settings import (
    BUILT_IN_PRESETS,
    CACHE_TYPES,
    DEFAULT_SETTINGS,
    REASONING_FORMATS,
    RECOMMENDED_MODELS,
    SETTING_TYPES,
    SPLIT_MODES,
    coerce_setting,
    normalize_settings,
    validate_launch_settings,
)
from .vram import calculate_total_vram, get_kv_cache_size_gb, get_model_size_gb


def parse_prometheus_metrics(content: str) -> dict[str, Any]:
    return _parse_prometheus_metrics(content)


class TurboLauncherApp(tk.Tk):
    COLORS = {
        "bg": "#0f172a",
        "panel": "#111827",
        "panel2": "#1f2937",
        "surface": "#020617",
        "text": "#e5e7eb",
        "muted": "#9ca3af",
        "accent": "#38bdf8",
        "green": "#34d399",
        "orange": "#fb923c",
        "red": "#f87171",
    }

    BODY_FONT = ("Aptos", 10)
    TITLE_FONT = ("Aptos Display", 21)
    SECTION_FONT = ("Aptos", 11)

    def __init__(self, runtime_path: str | None = None) -> None:
        super().__init__()
        self.core = LauncherCore(runtime_path)
        self.models: list[ModelEntry] = []
        self.presets: list[dict[str, Any]] = []
        self.selected_model: ModelEntry | None = None
        self._last_synced_alias = ""
        self.current_preset = "Agentic AI"
        self.download_dir = self.core.get_download_dir()
        self.source_dirs = [Path(p) for p in self.core.get_model_source_dirs()]
        self.available_vram = 16.0
        self.total_layers = 40
        self.process: subprocess.Popen[str] | None = None
        self.server_start_time: float | None = None
        self.running_host: str | None = None
        self.running_port: int | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()
        self._loading = False
        self._save_after_id: str | None = None
        self.setting_widgets: dict[str, Any] = {}
        self.model_context_vars: dict[str, tk.StringVar] = {}
        self.model_context_notes: tk.StringVar | None = None
        self.launch_model_var: tk.StringVar | None = None

        self.title("TurboLauncher")
        self.geometry("1280x860")
        self.minsize(1040, 720)
        self.configure(bg=self.COLORS["bg"])

        self.vars: dict[str, tk.Variable] = {}
        self.metric_vars: dict[str, tk.StringVar] = {}
        self._configure_style()
        self._create_variables()
        self._build_ui()
        self._wire_events()
        self._initialize_data()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self._drain_log_queue)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        c = self.COLORS
        style.configure("TFrame", background=c["bg"])
        style.configure("Panel.TFrame", background=c["panel"])
        style.configure("Surface.TFrame", background=c["surface"])
        style.configure(
            "TLabel", background=c["bg"], foreground=c["text"], font=self.BODY_FONT
        )
        style.configure("Muted.TLabel", background=c["bg"], foreground=c["muted"])
        style.configure("Panel.TLabel", background=c["panel"], foreground=c["text"])
        style.configure(
            "Title.TLabel",
            background=c["bg"],
            foreground=c["text"],
            font=self.TITLE_FONT,
        )
        style.configure(
            "Section.TLabel",
            background=c["panel"],
            foreground=c["accent"],
            font=self.SECTION_FONT,
        )
        style.configure(
            "Accent.TButton",
            background=c["accent"],
            foreground="#001018",
            font=("Segoe UI Semibold", 10),
            padding=8,
        )
        style.configure(
            "Danger.TButton", background="#7f1d1d", foreground=c["text"], padding=8
        )
        style.configure(
            "TButton", background=c["panel2"], foreground=c["text"], padding=6
        )
        style.map("TButton", background=[("active", "#334155")])
        style.configure(
            "TEntry",
            fieldbackground="#0b1220",
            foreground=c["text"],
            insertcolor=c["text"],
            bordercolor="#334155",
        )
        style.configure(
            "TCombobox",
            fieldbackground="#0b1220",
            foreground=c["text"],
            arrowcolor=c["text"],
            bordercolor="#334155",
        )
        style.configure("TNotebook", background=c["bg"], borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=c["panel2"],
            foreground=c["muted"],
            padding=(14, 8),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", c["panel"])],
            foreground=[("selected", c["text"])],
        )
        style.configure("TCheckbutton", background=c["bg"], foreground=c["text"])
        style.configure(
            "Panel.TCheckbutton", background=c["panel"], foreground=c["text"]
        )
        style.configure("Card.TFrame", background=c["panel"], relief="flat")
        style.configure("CardInner.TFrame", background=c["panel2"])
        style.configure("Card.TLabel", background=c["panel"], foreground=c["text"])
        style.configure(
            "CardMuted.TLabel", background=c["panel"], foreground=c["muted"]
        )

    def _create_variables(self) -> None:
        for key, default in DEFAULT_SETTINGS.items():
            if isinstance(default, bool):
                self.vars[key] = tk.BooleanVar(value=default)
            elif key == "GpuLayers":
                self.vars[key] = tk.DoubleVar(value=float(default))
            else:
                self.vars[key] = tk.StringVar(value=str(default))

        for key in [
            "status",
            "model",
            "model_size",
            "preset",
            "vram",
            "vram_detail",
            "tps",
            "context",
            "uptime",
            "peps",
            "decode_time",
            "prompt_time",
            "kv_cache",
            "requests",
            "tokens",
            "cpu",
            "ram",
            "gpu",
            "gpu_vram",
        ]:
            self.metric_vars[key] = tk.StringVar(value="--")
        self.metric_vars["status"].set("Stopped")
        self.metric_vars["model"].set("No model selected")
        self.metric_vars["preset"].set("Agentic AI")
        self.metric_vars["tps"].set("0 tok/s")

    def _build_ui(self) -> None:
        root = ttk.Frame(self, style="TFrame")
        root.pack(fill="both", expand=True, padx=12, pady=12)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        self._build_sidebar(root)
        self._build_content(root)

    def _build_sidebar(self, parent: ttk.Frame) -> None:
        sidebar = ttk.Frame(parent, style="Panel.TFrame", width=292)
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        sidebar.grid_propagate(False)
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(2, weight=0)
        sidebar.rowconfigure(4, weight=1)
        sidebar.rowconfigure(6, weight=0)

        hero = ttk.Frame(sidebar, style="Panel.TFrame")
        hero.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 12))
        hero.columnconfigure(0, weight=1)
        ttk.Label(
            hero, text="TurboLauncher", style="Panel.TLabel", font=self.TITLE_FONT
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            hero,
            text="A cleaner control surface for llama-server",
            style="CardMuted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        status_card = ttk.Frame(sidebar, style="Card.TFrame")
        status_card.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 12))
        status_card.columnconfigure(0, weight=1)
        ttk.Label(status_card, text="SESSION", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 4)
        )
        ttk.Label(
            status_card,
            textvariable=self.metric_vars["status"],
            style="Card.TLabel",
            font=("Aptos Semibold", 13),
        ).grid(row=1, column=0, sticky="w", padx=12)
        ttk.Label(
            status_card,
            textvariable=self.metric_vars["model"],
            style="CardMuted.TLabel",
            wraplength=240,
        ).grid(row=2, column=0, sticky="w", padx=12, pady=(0, 10))

        quick = ttk.Frame(sidebar, style="Card.TFrame")
        quick.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 12))
        quick.columnconfigure(0, weight=1)
        ttk.Label(quick, text="QUICK ACTIONS", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 8)
        )
        button_row1 = ttk.Frame(quick, style="Card.TFrame")
        button_row1.grid(row=1, column=0, sticky="ew", padx=10)
        button_row1.columnconfigure((0, 1), weight=1)
        ttk.Button(
            button_row1, text="Start", style="Accent.TButton", command=self.start_server
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=(0, 6))
        ttk.Button(
            button_row1, text="Stop", style="Danger.TButton", command=self.stop_server
        ).grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=(0, 6))
        button_row2 = ttk.Frame(quick, style="Card.TFrame")
        button_row2.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        button_row2.columnconfigure((0, 1), weight=1)
        ttk.Button(button_row2, text="Models", command=self.focus_models_tab).grid(
            row=0, column=0, sticky="ew", padx=(0, 4)
        )
        ttk.Button(button_row2, text="Download", command=self.go_to_download_tab).grid(
            row=0, column=1, sticky="ew", padx=(4, 0)
        )
        button_row3 = ttk.Frame(quick, style="Card.TFrame")
        button_row3.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        button_row3.columnconfigure((0, 1), weight=1)
        ttk.Button(button_row3, text="Add model", command=self.add_model_dialog).grid(
            row=0, column=0, sticky="ew", padx=(0, 4)
        )
        ttk.Button(button_row3, text="Runtime", command=self.settings_dialog).grid(
            row=0, column=1, sticky="ew", padx=(4, 0)
        )
        ttk.Button(quick, text="Save session", command=self.save_current_session).grid(
            row=4, column=0, sticky="ew", padx=10, pady=(0, 10)
        )

        preset_frame = ttk.Frame(sidebar, style="Card.TFrame")
        preset_frame.grid(row=4, column=0, sticky="nsew", padx=14)
        preset_frame.rowconfigure(1, weight=1)
        preset_frame.columnconfigure(0, weight=1)
        ttk.Label(preset_frame, text="PRESETS", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 6)
        )
        self.preset_list = tk.Listbox(
            preset_frame,
            bg="#0b1220",
            fg=self.COLORS["text"],
            selectbackground="#0ea5e9",
            selectforeground="#001018",
            activestyle="none",
            highlightthickness=1,
            highlightbackground="#334155",
            relief="flat",
            font=self.BODY_FONT,
        )
        self.preset_list.grid(row=1, column=0, sticky="nsew", padx=10)
        preset_scroll = ttk.Scrollbar(
            preset_frame, orient="vertical", command=self.preset_list.yview
        )
        preset_scroll.grid(row=1, column=1, sticky="ns", padx=(0, 10))
        self.preset_list.configure(yscrollcommand=preset_scroll.set)

        preset_buttons = ttk.Frame(sidebar, style="Panel.TFrame")
        preset_buttons.grid(row=6, column=0, sticky="ew", padx=14, pady=(12, 14))
        preset_buttons.columnconfigure(0, weight=1)
        preset_buttons.columnconfigure(1, weight=1)
        ttk.Button(
            preset_buttons, text="Save Preset", command=self.save_preset_dialog
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(preset_buttons, text="Reload", command=self.refresh_presets).grid(
            row=0, column=1, sticky="ew", padx=(4, 0)
        )

    def _build_content(self, parent: ttk.Frame) -> None:
        content = ttk.Frame(parent, style="TFrame")
        content.grid(row=0, column=1, sticky="nsew")
        content.rowconfigure(2, weight=1)
        content.columnconfigure(0, weight=1)

        header = ttk.Frame(content, style="TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Launch Console", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        status_frame = ttk.Frame(header, style="TFrame")
        status_frame.grid(row=0, column=1, sticky="e")
        self.status_dot = ttk.Label(
            status_frame,
            text="●",
            foreground=self.COLORS["muted"],
            font=("Segoe UI", 18),
        )
        self.status_dot.grid(row=0, column=0, padx=(0, 6))
        ttk.Label(
            status_frame,
            textvariable=self.metric_vars["status"],
            font=("Segoe UI Semibold", 11),
        ).grid(row=0, column=1)

        summary = ttk.Frame(content, style="Panel.TFrame")
        summary.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        for idx in range(4):
            summary.columnconfigure(idx, weight=1)
        self._summary_label(summary, "Model", self.metric_vars["model"], 0)
        self._summary_label(summary, "Preset", self.metric_vars["preset"], 1)
        self._summary_label(summary, "Throughput", self.metric_vars["tps"], 2)
        self._summary_label(summary, "VRAM", self.metric_vars["vram"], 3)

        work = ttk.Frame(content, style="TFrame")
        work.grid(row=2, column=0, sticky="nsew")
        work.rowconfigure(0, weight=1)
        work.rowconfigure(1, weight=1)
        work.columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(work)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        self.launch_tab = self._new_tab("Launch")
        self.sampling_tab = self._new_tab("Sampling")
        self.server_tab = self._new_tab("Server")
        self.reasoning_tab = self._new_tab("Reasoning")
        self.monitoring_tab = self._new_tab("Monitoring")
        self.models_tab = self._new_tab("Models")
        self.models_notebook = ttk.Notebook(self.models_tab)
        self.models_notebook.pack(fill="both", expand=True)
        self.models_library_tab = ttk.Frame(self.models_notebook, style="TFrame")
        self.models_download_tab = ttk.Frame(self.models_notebook, style="TFrame")
        self.models_sources_tab = ttk.Frame(self.models_notebook, style="TFrame")
        self.models_notebook.add(self.models_library_tab, text="Library")
        self.models_notebook.add(self.models_download_tab, text="Download")
        self.models_notebook.add(self.models_sources_tab, text="Source Folders")
        self._build_launch_tab()
        self._build_sampling_tab()
        self._build_server_tab()
        self._build_reasoning_tab()
        self._build_monitoring_tab()
        self._build_models_tabs()

        terminal_frame = ttk.Frame(work, style="Panel.TFrame")
        terminal_frame.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        terminal_frame.rowconfigure(1, weight=1)
        terminal_frame.columnconfigure(0, weight=1)
        action_bar = ttk.Frame(terminal_frame, style="Panel.TFrame")
        action_bar.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        action_bar.columnconfigure(5, weight=1)
        ttk.Button(
            action_bar, text="START", style="Accent.TButton", command=self.start_server
        ).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(
            action_bar, text="STOP", style="Danger.TButton", command=self.stop_server
        ).grid(row=0, column=1, padx=6)
        ttk.Button(action_bar, text="Export Command", command=self.export_command).grid(
            row=0, column=2, padx=6
        )
        ttk.Button(action_bar, text="Runtime", command=self.settings_dialog).grid(
            row=0, column=3, padx=6
        )
        ttk.Button(
            action_bar, text="Clear", command=lambda: self.terminal.delete("1.0", "end")
        ).grid(row=0, column=4, padx=6)

        self.terminal = tk.Text(
            terminal_frame,
            bg="#020617",
            fg="#d1d5db",
            insertbackground="#d1d5db",
            relief="flat",
            height=11,
            wrap="word",
            font=("Consolas", 10),
        )
        self.terminal.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        term_scroll = ttk.Scrollbar(
            terminal_frame, orient="vertical", command=self.terminal.yview
        )
        term_scroll.grid(row=1, column=1, sticky="ns", pady=(0, 10))
        self.terminal.configure(yscrollcommand=term_scroll.set)

    def _summary_label(
        self, parent: ttk.Frame, title: str, var: tk.StringVar, col: int
    ) -> None:
        frame = ttk.Frame(parent, style="Panel.TFrame")
        frame.grid(row=0, column=col, sticky="ew", padx=12, pady=10)
        ttk.Label(
            frame,
            text=title.upper(),
            style="Panel.TLabel",
            foreground=self.COLORS["muted"],
            font=("Segoe UI", 8),
        ).pack(anchor="w")
        ttk.Label(
            frame,
            textvariable=var,
            style="Panel.TLabel",
            font=("Segoe UI Semibold", 11),
        ).pack(anchor="w")

    def _new_tab(self, title: str) -> ttk.Frame:
        frame = ttk.Frame(self.notebook, style="TFrame")
        frame.columnconfigure(0, weight=1)
        self.notebook.add(frame, text=title)
        return frame

    def _grid_container(self, parent: ttk.Frame) -> ttk.Frame:
        frame = ttk.Frame(parent, style="TFrame")
        frame.grid(row=0, column=0, sticky="new", padx=18, pady=18)
        for col in range(4):
            frame.columnconfigure(col, weight=1)
        return frame

    def _card(self, parent: ttk.Frame, *, padding: int = 14) -> ttk.Frame:
        frame = ttk.Frame(parent, style="Card.TFrame")
        frame.columnconfigure(0, weight=1)
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        inner = ttk.Frame(frame, style="Card.TFrame")
        inner.grid(row=0, column=0, sticky="nsew", padx=padding, pady=padding)
        inner.columnconfigure(0, weight=1)
        return inner

    def _section_title(self, parent: ttk.Frame, title: str, subtitle: str = "") -> None:
        header = ttk.Frame(parent, style="Card.TFrame")
        header.grid_columnconfigure(0, weight=1)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(header, text=title.upper(), style="Section.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        if subtitle:
            ttk.Label(
                header, text=subtitle, style="CardMuted.TLabel", wraplength=520
            ).grid(row=1, column=0, sticky="w", pady=(3, 0))

    def _entry(
        self,
        parent: ttk.Frame,
        row: int,
        col: int,
        label: str,
        key: str,
        width: int = 14,
    ) -> None:
        ttk.Label(parent, text=label).grid(
            row=row, column=col, sticky="w", padx=8, pady=(8, 2)
        )
        entry = ttk.Entry(parent, textvariable=self.vars[key], width=width)
        entry.grid(row=row + 1, column=col, sticky="ew", padx=8, pady=(0, 8))
        entry.bind("<FocusOut>", self.on_setting_changed)
        entry.bind("<Return>", self.on_setting_changed)
        self.setting_widgets[key] = entry

    def _combo(
        self,
        parent: ttk.Frame,
        row: int,
        col: int,
        label: str,
        key: str,
        values: list[str],
        state: str = "readonly",
    ) -> None:
        ttk.Label(parent, text=label).grid(
            row=row, column=col, sticky="w", padx=8, pady=(8, 2)
        )
        combo = ttk.Combobox(
            parent, textvariable=self.vars[key], values=values, state=state
        )
        combo.grid(row=row + 1, column=col, sticky="ew", padx=8, pady=(0, 8))
        combo.bind("<<ComboboxSelected>>", self.on_setting_changed)
        self.setting_widgets[key] = combo

    def _check(
        self, parent: ttk.Frame, row: int, col: int, label: str, key: str
    ) -> None:
        check = ttk.Checkbutton(
            parent, text=label, variable=self.vars[key], command=self.on_setting_changed
        )
        check.grid(row=row, column=col, sticky="w", padx=8, pady=8)
        self.setting_widgets[key] = check

    def _build_launch_tab(self) -> None:
        tab = self.launch_tab
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)

        hero = ttk.Frame(tab, style="TFrame")
        hero.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 0))
        hero.columnconfigure(0, weight=1)
        hero.rowconfigure(0, weight=0)
        hero.rowconfigure(1, weight=1)

        model_card = ttk.Frame(hero, style="Card.TFrame")
        model_card.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        model_card.columnconfigure(0, weight=1)
        model_inner = ttk.Frame(model_card, style="Card.TFrame")
        model_inner.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)
        model_inner.columnconfigure(1, weight=1)

        self._section_title(
            model_inner,
            "Selected model",
            "Model selection lives in the Models workspace; this card keeps the active model and launch context in view.",
        )
        picker_row = ttk.Frame(model_inner, style="Card.TFrame")
        picker_row.grid(row=1, column=0, sticky="ew", columnspan=2, pady=(0, 10))
        picker_row.columnconfigure(1, weight=1)
        ttk.Label(picker_row, text="Model", style="CardMuted.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )
        self.launch_model_var = tk.StringVar(value="")
        self.launch_model_picker = ttk.Combobox(
            picker_row,
            textvariable=self.launch_model_var,
            state="readonly",
            values=[],
        )
        self.launch_model_picker.grid(row=0, column=1, sticky="ew")
        self.launch_model_picker.bind(
            "<<ComboboxSelected>>", self._on_launch_model_selected
        )
        ttk.Button(picker_row, text="Library", command=self.focus_models_tab).grid(
            row=0, column=2, sticky="e", padx=(8, 0)
        )
        details = ttk.Frame(model_inner, style="Card.TFrame")
        details.grid(row=2, column=0, sticky="ew", columnspan=2)
        details.columnconfigure(1, weight=1)

        self.model_context_vars = {
            "Name": tk.StringVar(value="No model selected"),
            "Alias": tk.StringVar(value="--"),
            "Path": tk.StringVar(value="--"),
            "Size": tk.StringVar(value="--"),
            "Quant": tk.StringVar(value="--"),
            "Source": tk.StringVar(value="--"),
            "Suggestion": tk.StringVar(value="Pick a model in Models → Library."),
        }
        labels = ["Name", "Alias", "Path", "Size", "Quant", "Source"]
        for row, label in enumerate(labels):
            ttk.Label(details, text=f"{label}:", style="CardMuted.TLabel").grid(
                row=row, column=0, sticky="nw", padx=(0, 10), pady=4
            )
            ttk.Label(
                details,
                textvariable=self.model_context_vars[label],
                style="Card.TLabel",
                wraplength=700,
            ).grid(row=row, column=1, sticky="nw", pady=4)

        self.model_context_notes = self.model_context_vars["Suggestion"]
        ttk.Label(
            model_inner,
            textvariable=self.model_context_notes,
            style="CardMuted.TLabel",
            wraplength=860,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))

        actions = ttk.Frame(model_inner, style="Card.TFrame")
        actions.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        for idx in range(4):
            actions.columnconfigure(idx, weight=1)
        ttk.Button(
            actions, text="Open folder", command=self.open_selected_model_folder
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(
            actions, text="Copy path", command=self.copy_selected_model_path
        ).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(actions, text="Go to Models", command=self.focus_models_tab).grid(
            row=0, column=2, sticky="ew", padx=6
        )
        ttk.Button(actions, text="Export command", command=self.export_command).grid(
            row=0, column=3, sticky="ew", padx=(6, 0)
        )

        tuning_card = ttk.Frame(hero, style="Card.TFrame")
        tuning_card.grid(row=1, column=0, sticky="nsew")
        tuning_card.columnconfigure(0, weight=1)
        tuning_inner = ttk.Frame(tuning_card, style="Card.TFrame")
        tuning_inner.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)
        tuning_inner.columnconfigure((0, 1, 2, 3), weight=1)
        self._section_title(
            tuning_inner,
            "Model runtime",
            "Tune the settings that most directly affect model placement, memory, and launch shape.",
        )

        ttk.Label(tuning_inner, text="GPU Layers", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", padx=8, pady=(2, 2)
        )
        self.gpu_layers_label = ttk.Label(
            tuning_inner,
            text="30",
            foreground=self.COLORS["accent"],
            background=self.COLORS["panel"],
            font=("Aptos Semibold", 11),
        )
        self.gpu_layers_label.grid(row=1, column=1, sticky="w", pady=(2, 2))
        scale = ttk.Scale(
            tuning_inner,
            from_=0,
            to=40,
            variable=self.vars["GpuLayers"],
            command=self._gpu_layers_changed,
        )
        scale.grid(row=2, column=0, columnspan=4, sticky="ew", padx=8, pady=(0, 12))
        scale.bind("<ButtonRelease-1>", self.on_setting_changed)

        self._entry(tuning_inner, 3, 0, "CPU MoE Layers", "NcpuMoe")
        self._combo(
            tuning_inner,
            3,
            1,
            "Context Size",
            "CtxSize",
            ["4096", "8192", "16384", "32768", "65536", "131072"],
            state="normal",
        )
        self._combo(tuning_inner, 3, 2, "Cache K", "CacheTypeK", CACHE_TYPES)
        self._combo(tuning_inner, 3, 3, "Cache V", "CacheTypeV", CACHE_TYPES)
        self._combo(tuning_inner, 5, 0, "Split Mode", "SplitMode", SPLIT_MODES)
        self._entry(tuning_inner, 5, 1, "Tensor Split", "TensorSplit")
        self._check(tuning_inner, 5, 2, "Flash Attention", "FlashAttn")
        self._entry(tuning_inner, 5, 3, "Alias", "Alias", width=18)

        self._entry(tuning_inner, 7, 0, "Threads", "Threads")
        self._entry(tuning_inner, 7, 1, "Batch Size", "BatchSize")
        self._entry(tuning_inner, 7, 2, "UBatch Size", "UBatchSize")
        self._check(tuning_inner, 7, 3, "Lock memory", "Mlock")
        self._check(tuning_inner, 8, 3, "Disable mmap", "NoMmap")

        vram_frame = ttk.Frame(tuning_inner, style="Card.TFrame")
        vram_frame.grid(
            row=9, column=0, columnspan=4, sticky="ew", padx=8, pady=(10, 0)
        )
        vram_frame.columnconfigure(0, weight=1)
        ttk.Label(vram_frame, text="Estimated VRAM", style="Card.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            vram_frame,
            textvariable=self.metric_vars["vram_detail"],
            style="CardMuted.TLabel",
        ).grid(row=0, column=1, sticky="e")
        self.vram_bar = ttk.Progressbar(vram_frame, maximum=16.0, value=0)
        self.vram_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 2))

    def _build_sampling_tab(self) -> None:
        tab = self.sampling_tab
        frame = self._grid_container(tab)
        fields = [
            ("Temperature", "Temp"),
            ("Top P", "TopP"),
            ("Top K", "TopK"),
            ("Min P", "MinP"),
            ("Typical P", "TypicalP"),
            ("Repeat Penalty", "RepeatPenalty"),
            ("Repeat Last N", "RepeatLastN"),
            ("Presence Penalty", "PresencePenalty"),
            ("Frequency Penalty", "FreqPenalty"),
            ("DRY Multiplier", "DryMultiplier"),
            ("DRY Base", "DryBase"),
            ("DRY Allowed", "DryAllowed"),
            ("XTC Probability", "XtcProb"),
            ("XTC Threshold", "XtcThresh"),
            ("Seed", "Seed"),
        ]
        for idx, (label, key) in enumerate(fields):
            row = (idx // 4) * 2
            col = idx % 4
            self._entry(frame, row, col, label, key)

    def _build_server_tab(self) -> None:
        tab = self.server_tab
        frame = self._grid_container(tab)
        self._entry(frame, 0, 0, "Host", "Host")
        self._entry(frame, 0, 1, "Port", "Port")
        self._entry(frame, 0, 2, "Parallel Slots", "Parallel")
        self._entry(frame, 0, 3, "API Key", "ApiKey", width=28)
        self._check(frame, 4, 0, "Jinja templates", "Jinja")
        self._check(frame, 4, 1, "Web UI", "Webui")
        self._check(frame, 4, 2, "Metrics endpoint", "Metrics")
        self._check(frame, 4, 3, "Continuous batching", "ContBatching")
        ttk.Label(
            frame,
            text="Server-level flags stay here; model-specific placement and memory controls are grouped in Launch.",
            foreground=self.COLORS["muted"],
        ).grid(row=6, column=0, columnspan=4, sticky="w", padx=8, pady=(10, 0))

    def _build_reasoning_tab(self) -> None:
        tab = self.reasoning_tab
        frame = self._grid_container(tab)
        self._check(frame, 0, 0, "Thinking", "Thinking")
        self._check(frame, 0, 1, "Preserve thinking (preset only)", "PreserveThinking")
        self._combo(
            frame, 1, 0, "Reasoning Format", "ReasoningFormat", REASONING_FORMATS
        )
        self._entry(frame, 1, 1, "Reasoning Budget", "ReasoningBudget")
        ttk.Label(
            frame,
            text="When Thinking is off, the launcher passes --reasoning-format none.",
            foreground=self.COLORS["muted"],
        ).grid(row=3, column=0, columnspan=4, sticky="w", padx=8, pady=(12, 0))

    def _build_monitoring_tab(self) -> None:
        tab = self.monitoring_tab
        frame = self._grid_container(tab)
        items = [
            ("Status", "status"),
            ("Uptime", "uptime"),
            ("Tokens/sec", "tps"),
            ("Prompt eval/sec", "peps"),
            ("Decode ms/token", "decode_time"),
            ("Prompt ms/token", "prompt_time"),
            ("Context", "context"),
            ("KV Cache", "kv_cache"),
            ("Total Tokens", "tokens"),
            ("Requests", "requests"),
            ("CPU", "cpu"),
            ("RAM", "ram"),
            ("GPU", "gpu"),
            ("GPU VRAM", "gpu_vram"),
        ]
        for idx, (label, key) in enumerate(items):
            row = idx // 2
            col = (idx % 2) * 2
            ttk.Label(frame, text=label, foreground=self.COLORS["muted"]).grid(
                row=row, column=col, sticky="w", padx=8, pady=7
            )
            ttk.Label(
                frame,
                textvariable=self.metric_vars[key],
                font=("Segoe UI Semibold", 10),
            ).grid(row=row, column=col + 1, sticky="w", padx=8, pady=7)

    def _wire_events(self) -> None:
        self.preset_list.bind("<<ListboxSelect>>", self.on_preset_selected)
        if hasattr(self, "models_library_list"):
            self.models_library_list.bind(
                "<<ListboxSelect>>", self._on_library_selected
            )

    def go_to_download_tab(self) -> None:
        self.notebook.select(self.models_tab)
        self.models_notebook.select(self.models_download_tab)

    def focus_models_tab(self) -> None:
        self.notebook.select(self.models_tab)
        self.models_notebook.select(self.models_library_tab)

    def _initialize_data(self) -> None:
        self._loading = True
        self.refresh_models(log_result=True)
        self.refresh_presets(select_first=False)

        session = self.core.load_session() or {}
        preset_name = (
            session.get("LastPreset") or session.get("PresetName") or "Agentic AI"
        )
        if not self.apply_preset(preset_name, persist=False):
            self.apply_preset("Agentic AI", persist=False)

        session_settings = {}
        if isinstance(session.get("Settings"), dict):
            session_settings.update(session["Settings"])
        session_settings.update(
            {k: v for k, v in session.items() if k in DEFAULT_SETTINGS}
        )
        if session_settings:
            self.apply_settings(session_settings, persist=False)

        model_path = session.get("LastModel") or session.get("ModelPath")
        if model_path and not self.select_model_by_path(model_path, persist=False):
            self.select_first_model(persist=False)
        elif not model_path:
            self.select_first_model(persist=False)

        self._loading = False
        self.update_vram_estimate()
        self.log("TurboLauncher Python initialized")
        self.log(f"Launcher dir: {APP_DIR}")
        self.log(
            "Ready. Pick a model in Models → Library, tune Launch, then click START."
        )
        if not self.core.resolve_runtime_executable():
            self.log("Tip: use Runtime to choose llama-server.exe.")

    def refresh_models(self, log_result: bool = True) -> None:
        current_path = str(self.selected_model.path) if self.selected_model else ""
        self.models, report = self.core.load_models_with_report()
        if hasattr(self, "models_library_list"):
            self.models_library_list.delete(0, "end")
        for model in self.models:
            if hasattr(self, "models_library_list"):
                self.models_library_list.insert("end", model.display_name)
        self._refresh_launch_model_picker()
        restored = False
        if current_path:
            restored = self.select_model_by_path(current_path, persist=False)
        if not restored:
            if self.models:
                self.select_first_model(persist=False)
            else:
                self.clear_selected_model(persist=False)
        if log_result:
            for line in report:
                self.log(line)
            self.log(f"Loaded {len(self.models)} model(s).")

    def refresh_presets(self, select_first: bool = True) -> None:
        self.presets = self.core.list_presets()
        self.preset_list.delete(0, "end")
        for preset in self.presets:
            marker = "P" if preset.get("IsBuiltIn") else "U"
            self.preset_list.insert("end", f"[{marker}] {preset['Name']}")
        if select_first and self.presets:
            self.preset_list.selection_set(0)

    def on_model_selected(self, _event: tk.Event | None = None) -> None:
        self._on_library_selected(_event)

    def _refresh_launch_model_picker(self) -> None:
        if not hasattr(self, "launch_model_picker"):
            return
        values = [model.display_name for model in self.models]
        self.launch_model_picker.configure(values=values)
        if not values and self.launch_model_var is not None:
            self.launch_model_var.set("")

    def _on_launch_model_selected(self, _event: tk.Event | None = None) -> None:
        if not hasattr(self, "launch_model_picker"):
            return
        index = self.launch_model_picker.current()
        if 0 <= index < len(self.models):
            self.set_selected_model(self.models[index])

    def clear_selected_model(self, *, persist: bool = True) -> None:
        self.selected_model = None
        self.metric_vars["model"].set("No model selected")
        self.metric_vars["model_size"].set("--")
        if self.launch_model_var is not None:
            self.launch_model_var.set("")
        self.update_model_details(None)
        self._update_model_context(None)
        if hasattr(self, "models_library_list"):
            self.models_library_list.selection_clear(0, "end")
        self.update_vram_estimate()
        if persist:
            self.save_session_debounced()

    def set_selected_model(self, model: ModelEntry, *, persist: bool = True) -> None:
        self.selected_model = model
        self.metric_vars["model"].set(model.name)
        self.metric_vars["model_size"].set(f"{model.size_gb:g} GB")
        current_alias = str(self.vars["Alias"].get()).strip()
        if not current_alias or current_alias == self._last_synced_alias:
            self.vars["Alias"].set(model.alias)
            self._last_synced_alias = model.alias
        self.update_model_details(model)
        self._update_model_context(model)
        self._sync_library_selection()
        self.update_vram_estimate()
        if persist:
            self.save_session_debounced()

    def select_model_by_path(
        self, model_path: str | Path, *, persist: bool = True
    ) -> bool:
        target = str(Path(model_path)).lower()
        for idx, model in enumerate(self.models):
            if str(model.path).lower() == target:
                if hasattr(self, "models_library_list"):
                    self.models_library_list.selection_clear(0, "end")
                    self.models_library_list.selection_set(idx)
                    self.models_library_list.see(idx)
                self.set_selected_model(model, persist=persist)
                return True
        return False

    def select_first_model(self, *, persist: bool = True) -> None:
        if self.models:
            self.set_selected_model(self.models[0], persist=persist)
        else:
            self.clear_selected_model(persist=persist)

    def on_preset_selected(self, _event: tk.Event | None = None) -> None:
        selection = self.preset_list.curselection()
        if not selection:
            return
        index = int(selection[0])
        if 0 <= index < len(self.presets):
            self.apply_preset(self.presets[index]["Name"])

    def apply_preset(self, name: str, *, persist: bool = True) -> bool:
        preset = self.core.load_preset(name)
        if not preset:
            return False
        settings = preset.get("Settings") or {}
        self.apply_settings(settings, persist=False)
        self.current_preset = preset.get("Name") or name
        self.metric_vars["preset"].set(self.current_preset)
        for idx, item in enumerate(self.presets):
            if item["Name"] == self.current_preset:
                self.preset_list.selection_clear(0, "end")
                self.preset_list.selection_set(idx)
                self.preset_list.see(idx)
                break
        self.update_vram_estimate()
        if persist:
            self.save_session_debounced()
            self.log(f"Applied preset: {self.current_preset}")
        return True

    def apply_settings(self, settings: dict[str, Any], *, persist: bool = True) -> None:
        for key, raw_value in settings.items():
            if key not in self.vars:
                continue

            value = coerce_setting(key, raw_value)
            var = self.vars[key]
            if isinstance(var, tk.BooleanVar):
                var.set(bool(value))
            elif isinstance(var, tk.DoubleVar):
                var.set(float(value))
            else:
                var.set(str(value))
        self._gpu_layers_changed(str(self.vars["GpuLayers"].get()))
        self.update_vram_estimate()
        if persist:
            self.save_session_debounced()

    def collect_settings(self, *, strict: bool = False) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for key, var in self.vars.items():
            values[key] = var.get()
        return normalize_settings(values, strict=strict)

    def on_setting_changed(self, _event: tk.Event | None = None) -> None:
        if self._loading:
            return
        self.update_vram_estimate()
        self.save_session_debounced()

    def _gpu_layers_changed(self, value: str) -> None:
        try:
            layers = int(float(value))
        except ValueError:
            layers = 0
        self.gpu_layers_label.configure(text=str(layers))
        if not self._loading:
            self.update_vram_estimate()

    def update_vram_estimate(self) -> None:
        settings = self.collect_settings(strict=False)
        model_path = self.selected_model.path if self.selected_model else None
        quant = (
            self.selected_model.quant
            if self.selected_model
            else detect_quant(str(model_path or ""))
        )
        result = calculate_total_vram(
            model_path,
            quant,
            settings["CtxSize"],
            settings["GpuLayers"],
            settings["CacheTypeK"],
            settings["CacheTypeV"],
            self.available_vram,
            settings["NcpuMoe"],
            self.total_layers,
        )
        total = result["TotalVRAMGB"]
        remaining = result["RemainingGB"]
        self.metric_vars["vram"].set(f"{total:.2f} GB")
        self.metric_vars["vram_detail"].set(
            f"{total:.2f} / {self.available_vram:.1f} GB · {remaining:+.2f} GB"
        )
        self.vram_bar.configure(
            maximum=max(self.available_vram, total, 1.0),
            value=max(0, min(total, self.available_vram)),
        )
        if self.selected_model and self.model_context_vars:
            self._update_model_context(self.selected_model)

    def _context_presets_for_model(self, model: ModelEntry | None) -> list[str]:
        current = str(self.vars["CtxSize"].get())
        if not model:
            values = ["4096", "8192", "16384", "32768", "65536", "131072"]
        else:
            size = model.size_gb or 0.0
            if size <= 1.5:
                values = ["4096", "8192", "16384", "32768"]
            elif size <= 4:
                values = ["8192", "16384", "32768", "65536"]
            elif size <= 12:
                values = ["16384", "32768", "65536", "131072"]
            else:
                values = ["32768", "65536", "131072", "262144"]
        if current and current not in values:
            values.insert(0, current)
        return values

    def _estimated_model_tier(self, model: ModelEntry | None) -> str:
        if not model:
            return ""
        quant = model.quant
        if quant == "Unknown":
            return "Quant not detected from filename"
        return f"Detected {quant} quant"

    def _update_model_context(self, model: ModelEntry | None = None) -> None:
        model = model or self.selected_model
        ctx_values = self._context_presets_for_model(model)
        ctx_widget = self.setting_widgets.get("CtxSize")
        if isinstance(ctx_widget, ttk.Combobox):
            ctx_widget.configure(values=ctx_values)

        if not self.model_context_vars:
            return

        if not model:
            self.model_context_vars["Name"].set("No model selected")
            self.model_context_vars["Alias"].set("--")
            self.model_context_vars["Path"].set("--")
            self.model_context_vars["Size"].set("--")
            self.model_context_vars["Quant"].set("--")
            self.model_context_vars["Source"].set("--")
            self.model_context_vars["Suggestion"].set(
                "Pick a model in Models → Library to see file details, quant hints, and launch guidance."
            )
            return

        quant = model.quant
        settings = self.collect_settings(strict=False)
        self.model_context_vars["Name"].set(model.name)
        self.model_context_vars["Alias"].set(model.alias)
        self.model_context_vars["Path"].set(str(model.path))
        self.model_context_vars["Size"].set(f"{model.size_gb:g} GB")
        self.model_context_vars["Quant"].set(quant)
        self.model_context_vars["Source"].set(model.directory)

        suggested_ctx = ", ".join(ctx_values[:3])
        size_note = self._estimated_model_tier(model)
        vram_preview = calculate_total_vram(
            model.path,
            quant,
            int(settings["CtxSize"]),
            int(settings["GpuLayers"]),
            str(settings["CacheTypeK"]),
            str(settings["CacheTypeV"]),
            self.available_vram,
            int(settings["NcpuMoe"]),
            self.total_layers,
        )
        self.model_context_vars["Suggestion"].set(
            f"{size_note}. Suggested contexts: {suggested_ctx}. Current launch estimate: {vram_preview['TotalVRAMGB']:.2f} GB total, {vram_preview['RemainingGB']:+.2f} GB headroom."
        )

    def _sync_library_selection(self) -> None:
        if not self.selected_model or not hasattr(self, "models_library_list"):
            return
        for idx, model in enumerate(self.models):
            if model.path == self.selected_model.path:
                self.models_library_list.selection_clear(0, "end")
                self.models_library_list.selection_set(idx)
                self.models_library_list.see(idx)
                if self.launch_model_var is not None:
                    self.launch_model_var.set(model.display_name)
                break

    @staticmethod
    def can_bind_port(host: str, port: int) -> tuple[bool, str]:
        bind_host = str(host or "127.0.0.1").strip()
        if bind_host in {"*", "[::]"}:
            bind_host = "::"
        elif not bind_host:
            bind_host = "127.0.0.1"
        family = socket.AF_INET6 if ":" in bind_host and bind_host.count(".") != 3 else socket.AF_INET
        try:
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((bind_host, int(port)))
            return True, ""
        except OSError as exc:
            return False, str(exc)

    def save_session_debounced(self) -> None:
        if self._loading:
            return
        if self._save_after_id:
            self.after_cancel(self._save_after_id)
        self._save_after_id = self.after(350, self.save_current_session)

    def save_current_session(self) -> None:
        self._save_after_id = None
        try:
            model_path = str(self.selected_model.path) if self.selected_model else ""
            self.core.save_session(
                self.current_preset, model_path, self.collect_settings(strict=False)
            )
        except Exception as exc:
            self.log(f"[WARN] Failed to save session: {exc}")

    def add_model_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="Select GGUF model",
            filetypes=[("GGUF Models", "*.gguf"), ("All files", "*.*")],
        )
        if not path:
            return
        alias = simpledialog.askstring(
            "Model alias",
            "Alias:",
            initialvalue=sanitize_alias(Path(path).stem, 30),
            parent=self,
        )
        if not alias:
            return
        self.core.add_model_to_registry(alias, path)
        self.refresh_models(log_result=False)
        self.select_model_by_path(path)
        self.log(f"Added model: {Path(path).name}")

    def save_preset_dialog(self) -> None:
        name = simpledialog.askstring(
            "Save preset", "Preset name:", initialvalue="my-preset", parent=self
        )
        if not name:
            return
        description = (
            simpledialog.askstring(
                "Save preset", "Description (optional):", initialvalue="", parent=self
            )
            or ""
        )
        settings = self.collect_settings(strict=False)
        path = self.core.save_preset(name, description, settings)
        self.refresh_presets(select_first=False)
        self.apply_preset(name, persist=False)
        self.save_current_session()
        self.log(f"Preset saved: {path.name}")

    def settings_dialog(self) -> None:
        current = self.core.read_runtime_path()
        initial_dir = str(Path(current).parent) if current else str(APP_DIR)
        path = filedialog.askopenfilename(
            title="Select llama-server.exe",
            initialdir=initial_dir,
            filetypes=[
                ("llama-server", "llama-server.exe"),
                ("Executables", "*.exe"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        self.core.set_runtime_path(path)
        self.log(f"Runtime path set: {path}")

    def export_command(self) -> None:
        if not self.selected_model:
            messagebox.showwarning(
                "Export command", "Select a model first.", parent=self
            )
            return
        exe = self.core.resolve_runtime_executable() or Path("llama-server.exe")
        try:
            args = build_command_args(
                self.selected_model.path, self.collect_settings(strict=True)
            )
        except ValueError as exc:
            messagebox.showerror("Invalid setting", str(exc), parent=self)
            return
        cmd = command_string(exe, args)
        self.clipboard_clear()
        self.clipboard_append(cmd)
        self.log("Command copied to clipboard.")
        self.log(cmd)

    def start_server(self) -> None:
        if self.process and self.process.poll() is None:
            self.log("[WARN] Server is already running.")
            return
        if not self.selected_model:
            messagebox.showwarning("Start server", "Select a model first.", parent=self)
            return
        if not self.selected_model.path.exists():
            self.log(f"[ERROR] Model file not found: {self.selected_model.path}")
            return
        exe = self.core.resolve_runtime_executable()
        if not exe:
            self.log("[ERROR] llama-server.exe not found.")
            self.log(
                "        Checked configured runtime path, parent directory, and launcher directory."
            )
            self.log("        Use Runtime to set the executable path.")
            return
        try:
            settings = self.collect_settings(strict=True)
            server_args = build_command_args(self.selected_model.path, settings)
        except ValueError as exc:
            messagebox.showerror("Invalid setting", str(exc), parent=self)
            return
        can_bind, bind_error = self.can_bind_port(settings["Host"], settings["Port"])
        if not can_bind:
            self.log(
                f"[ERROR] Port {settings['Port']} is unavailable on {settings['Host']}: {bind_error}"
            )
            messagebox.showerror(
                "Port unavailable",
                f"Cannot bind {settings['Host']}:{settings['Port']}\n\n{bind_error}\n\nChoose a different port in the Server tab and try again.",
                parent=self,
            )
            return

        cmd_list = [str(exe), *args_to_list(server_args)]
        cmd_string = command_string(exe, server_args)
        self.log("")
        self.log("Starting llama-server...")
        self.log(f"Model: {self.selected_model.path}")
        self.log(
            f"GPU Layers: {settings['GpuLayers']} | Context: {settings['CtxSize']}"
        )
        self.log(f"KV Cache: {settings['CacheTypeK']} / {settings['CacheTypeV']}")
        preserve_note = "ON (preset only)" if settings["PreserveThinking"] else "OFF"
        self.log(
            f"Thinking: {'ON' if settings['Thinking'] else 'OFF'} | Preserve: {preserve_note}"
        )
        self.log(f"Port: {settings['Port']} | Host: {settings['Host']}")
        self.log(f"Executable: {exe}")
        self.log(f"Command: {cmd_string}")
        self.log("")

        flags = (
            subprocess.CREATE_NO_WINDOW
            if hasattr(subprocess, "CREATE_NO_WINDOW")
            else 0
        )
        try:
            self.process = subprocess.Popen(
                cmd_list,
                cwd=str(exe.parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=flags,
            )
        except Exception as exc:
            self.process = None
            self.set_status("Failed", "red")
            self.log(f"[ERROR] Failed to start llama-server: {exc}")
            return

        self.server_start_time = time.time()
        self.running_host = settings["Host"]
        self.running_port = settings["Port"]
        self.set_status("Running", "green")
        self.log(f"[INFO] llama-server process started. PID: {self.process.pid}")
        threading.Thread(target=self._read_process_output, daemon=True).start()
        self.after(500, self.check_process)
        self.after(2000, self.poll_metrics)
        self.after(1000, self.poll_resources)
        self.save_current_session()

    def stop_server(self) -> None:
        self.log("")
        self.log("Stopping server...")
        proc = self.process
        if not proc or proc.poll() is not None:
            self.set_status("Stopped", "muted")
            self.log("Server stopped.")
            return
        host = self.local_poll_host(
            self.running_host
            or self.collect_settings(strict=False).get("Host", "127.0.0.1")
        )
        port = self.running_port or self.collect_settings(strict=False).get(
            "Port", 1234
        )
        try:
            request = urllib.request.Request(
                f"http://{host}:{port}/health", method="POST"
            )
            urllib.request.urlopen(request, timeout=2).close()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=3)
            except Exception:
                pass
        self.process = None
        self.server_start_time = None
        self.running_host = None
        self.running_port = None
        self.set_status("Stopped", "muted")
        self.metric_vars["uptime"].set("--")
        self.log("Server stopped.")

    def _read_process_output(self) -> None:
        proc = self.process
        if not proc or not proc.stdout:
            return
        try:
            for line in proc.stdout:
                if line:
                    self.log_queue.put(
                        f"{datetime.now().strftime('%H:%M:%S')}  {line.rstrip()}\n"
                    )
        except Exception as exc:
            self.log_queue.put(
                f"{datetime.now().strftime('%H:%M:%S')}  [WARN] Output reader stopped: {exc}\n"
            )

    def check_process(self) -> None:
        proc = self.process
        if not proc:
            return
        code = proc.poll()
        if code is None:
            if self.server_start_time:
                elapsed = int(time.time() - self.server_start_time)
                self.metric_vars["uptime"].set(
                    f"{elapsed // 3600}h {(elapsed % 3600) // 60}m {elapsed % 60}s"
                    if elapsed >= 3600
                    else f"{elapsed // 60}m {elapsed % 60}s"
                )
            self.after(500, self.check_process)
            return
        self.log(f"[INFO] llama-server exited with code {code}")
        self.process = None
        self.server_start_time = None
        self.running_host = None
        self.running_port = None
        self.set_status(f"Exited ({code})", "muted")
        self.metric_vars["uptime"].set("--")

    def poll_metrics(self) -> None:
        if not self.process or self.process.poll() is not None:
            return
        host = self.local_poll_host(
            self.running_host
            or self.collect_settings(strict=False).get("Host", "127.0.0.1")
        )
        port = self.running_port or self.collect_settings(strict=False).get(
            "Port", 1234
        )
        try:
            with urllib.request.urlopen(
                f"http://{host}:{port}/metrics", timeout=2
            ) as response:
                content = response.read().decode("utf-8", errors="replace")
            metrics = parse_prometheus_metrics(content)
            self.update_metrics(metrics)
        except Exception:
            pass
        self.after(2000, self.poll_metrics)

    def poll_resources(self) -> None:
        if not self.process or self.process.poll() is not None:
            return
        cpu = get_cpu_usage()
        if cpu is not None:
            self.metric_vars["cpu"].set(f"{cpu:.0f}%")
        ram = get_ram_usage()
        if ram:
            self.metric_vars["ram"].set(
                f"{ram['UsedGB']} / {ram['TotalGB']} GB ({ram['Percent']:.0f}%)"
            )
        gpu = get_gpu_info()
        if gpu:
            self.metric_vars["gpu"].set(f"{gpu['Utilization']:.0f}%")
            self.metric_vars["gpu_vram"].set(
                f"{gpu['UsedVramGB']} / {gpu['TotalVramGB']} GB"
            )
            if gpu.get("TotalVramGB"):
                self.available_vram = float(gpu["TotalVramGB"])
                self.update_vram_estimate()
        self.after(3000, self.poll_resources)

    def update_metrics(self, metrics: dict[str, Any]) -> None:
        if "tps" in metrics:
            self.metric_vars["tps"].set(f"{metrics['tps']:.1f} tok/s")
        if "peps" in metrics:
            self.metric_vars["peps"].set(f"{metrics['peps']:.1f}")
        if (
            "total_decode_time" in metrics
            and "total_decode_tokens" in metrics
            and metrics["total_decode_tokens"]
        ):
            ms = (metrics["total_decode_time"] / metrics["total_decode_tokens"]) * 1000
            self.metric_vars["decode_time"].set(f"{ms:.1f}")
        if (
            "total_prompt_time" in metrics
            and "total_prompt_tokens" in metrics
            and metrics["total_prompt_tokens"]
        ):
            ms = (metrics["total_prompt_time"] / metrics["total_prompt_tokens"]) * 1000
            self.metric_vars["prompt_time"].set(f"{ms:.1f}")
        if "ctx_size" in metrics:
            self.metric_vars["context"].set(f"/ {metrics['ctx_size']} tokens")
        if "kv_usage" in metrics:
            self.metric_vars["kv_cache"].set(f"{metrics['kv_usage']:.1f}")
        if "total_decode_tokens" in metrics:
            self.metric_vars["tokens"].set(f"{metrics['total_decode_tokens']:,}")
        if "requests" in metrics:
            self.metric_vars["requests"].set(str(metrics["requests"]))

    def set_status(self, text: str, color_key: str) -> None:
        self.metric_vars["status"].set(text)
        color = self.COLORS.get(color_key, self.COLORS["muted"])
        self.status_dot.configure(foreground=color)

    @staticmethod
    def local_poll_host(host: str) -> str:
        host = str(host or "127.0.0.1").strip()
        if host in {"0.0.0.0", "::", "[::]", "*"}:
            return "127.0.0.1"
        return host

    def log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"{timestamp}  {message}\n" if message else "\n"
        self.log_queue.put(line)
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with LOG_FILE.open("a", encoding="utf-8") as f:
                f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {message}\n")
        except OSError:
            pass

    def _drain_log_queue(self) -> None:
        try:
            while True:
                line = self.log_queue.get_nowait()
                self.terminal.insert("end", line)
                self.terminal.see("end")
        except queue.Empty:
            pass
        self.after(100, self._drain_log_queue)

    def show_hf_dialog(self) -> None:
        self.go_to_download_tab()

    def _selected_hf_model(self, listbox: tk.Listbox) -> dict[str, str] | None:
        selection = listbox.curselection()
        if not selection:
            return None
        return RECOMMENDED_MODELS[int(selection[0])]

    def _open_hf_selected(self, listbox: tk.Listbox) -> None:
        model = self._selected_hf_model(listbox)
        if model:
            webbrowser.open(f"https://huggingface.co/{model['Id']}")

    def _download_hf_selected(
        self, listbox: tk.Listbox, status_label: ttk.Label
    ) -> None:
        model = self._selected_hf_model(listbox)
        if not model:
            messagebox.showwarning(
                "Download model", "Select a model first.", parent=self
            )
            return

        destination_root = Path(
            self.download_dir_var.get() or str(HF_CACHE_DIR)
        ).expanduser()
        self.core.set_download_dir(destination_root)
        status_label.configure(
            text=f"Downloading metadata for {model['Name']} to {destination_root}..."
        )
        self.log(
            f"Download requested: model_id={model['Id']} destination_root={destination_root}"
        )
        threading.Thread(
            target=self._download_hf_worker,
            args=(model, status_label, destination_root),
            daemon=True,
        ).start()

    def _build_models_tabs(self) -> None:
        self._build_models_library_tab()
        self._build_models_download_tab()
        self._build_models_sources_tab()

    def _build_models_library_tab(self) -> None:
        frame = self.models_library_tab
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=0)
        frame.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(frame, style="TFrame")
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=8)
        ttk.Label(toolbar, text="Library", style="Section.TLabel").grid(
            row=0, column=0, padx=(0, 12)
        )
        ttk.Button(toolbar, text="Refresh", command=self.refresh_models).grid(
            row=0, column=1, padx=(0, 6)
        )
        ttk.Button(toolbar, text="Download", command=self.go_to_download_tab).grid(
            row=0, column=2, padx=6
        )
        ttk.Button(
            toolbar, text="Open folder", command=self.open_selected_model_folder
        ).grid(row=0, column=3, padx=6)
        ttk.Button(
            toolbar, text="Copy path", command=self.copy_selected_model_path
        ).grid(row=0, column=4, padx=6)

        self.models_library_list = tk.Listbox(
            frame,
            bg="#0b1220",
            fg=self.COLORS["text"],
            selectbackground="#0ea5e9",
            selectforeground="#001018",
            activestyle="none",
            highlightthickness=1,
            highlightbackground="#334155",
            relief="flat",
            font=self.BODY_FONT,
        )
        self.models_library_list.grid(row=1, column=0, sticky="nsew", padx=12)
        self.models_library_list.bind("<<ListboxSelect>>", self._on_library_selected)
        library_scroll = ttk.Scrollbar(
            frame, orient="vertical", command=self.models_library_list.yview
        )
        library_scroll.grid(row=1, column=1, sticky="ns", padx=(0, 12), pady=0)
        self.models_library_list.configure(yscrollcommand=library_scroll.set)

        details = ttk.Frame(frame, style="Panel.TFrame")
        details.grid(row=1, column=2, sticky="nsew", padx=(0, 12), pady=0)
        details.columnconfigure(1, weight=1)
        self.model_detail_vars = {
            "Name": tk.StringVar(value="No model selected"),
            "Alias": tk.StringVar(value="--"),
            "Path": tk.StringVar(value="--"),
            "Size": tk.StringVar(value="--"),
            "Quant": tk.StringVar(value="--"),
            "Source": tk.StringVar(value="--"),
        }
        for row, (label, var) in enumerate(self.model_detail_vars.items()):
            ttk.Label(details, text=f"{label}:", style="Panel.TLabel").grid(
                row=row, column=0, sticky="nw", padx=10, pady=6
            )
            ttk.Label(
                details,
                textvariable=var,
                style="Panel.TLabel",
                wraplength=420,
                foreground=self.COLORS["muted"],
            ).grid(row=row, column=1, sticky="nw", padx=10, pady=6)
        ttk.Label(
            details,
            text="Pick a model here to populate the Launch workspace.",
            style="Panel.TLabel",
            foreground=self.COLORS["muted"],
            wraplength=420,
        ).grid(
            row=len(self.model_detail_vars),
            column=0,
            columnspan=2,
            sticky="w",
            padx=10,
            pady=(8, 10),
        )

    def _build_models_download_tab(self) -> None:
        frame = self.models_download_tab
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=0)
        frame.rowconfigure(0, weight=1)
        self.download_models_list = tk.Listbox(
            frame,
            height=8,
            bg="#0b1220",
            fg=self.COLORS["text"],
            selectbackground="#0ea5e9",
            selectforeground="#001018",
        )
        self.download_models_list.grid(row=0, column=0, sticky="nsew", padx=12, pady=8)
        download_scroll = ttk.Scrollbar(
            frame, orient="vertical", command=self.download_models_list.yview
        )
        download_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 12), pady=8)
        self.download_models_list.configure(yscrollcommand=download_scroll.set)
        for model in RECOMMENDED_MODELS:
            self.download_models_list.insert(
                "end",
                f"{model['Name']}  ·  {model['Size']}  ·  {model['BestFor']}  ·  preferred {model.get('PreferredQuant', 'Q4_K_M')}",
            )
        ttk.Label(
            frame,
            text="Downloads the recommended GGUF quant for the selected model and logs every step.",
            foreground=self.COLORS["muted"],
        ).grid(row=1, column=0, sticky="w", padx=12)
        self.download_status = ttk.Label(
            frame, text="", foreground=self.COLORS["muted"]
        )
        self.download_status.grid(row=3, column=0, sticky="w", padx=12)
        self.download_dir_var = tk.StringVar(value=str(self.download_dir))
        row = ttk.Frame(frame)
        row.grid(row=2, column=0, sticky="ew", padx=12, pady=(8, 0))
        row.columnconfigure(1, weight=1)
        ttk.Label(row, text="Download destination:").grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        ttk.Entry(row, textvariable=self.download_dir_var).grid(
            row=0, column=1, sticky="ew"
        )
        ttk.Button(row, text="Browse", command=self.browse_download_dir).grid(
            row=0, column=2, padx=4
        )
        ttk.Button(row, text="Reset default", command=self.reset_download_dir).grid(
            row=0, column=3, padx=4
        )
        ttk.Button(
            frame,
            text="Download selected",
            command=lambda: self._download_hf_selected(
                self.download_models_list, self.download_status
            ),
        ).grid(row=4, column=0, sticky="w", padx=12, pady=8)

    def _build_models_sources_tab(self) -> None:
        frame = self.models_sources_tab
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=0)
        frame.rowconfigure(0, weight=1)
        self.sources_list = tk.Listbox(
            frame,
            bg="#0b1220",
            fg=self.COLORS["text"],
            selectbackground="#0ea5e9",
            selectforeground="#001018",
        )
        self.sources_list.grid(row=0, column=0, sticky="nsew", padx=12, pady=8)
        sources_scroll = ttk.Scrollbar(
            frame, orient="vertical", command=self.sources_list.yview
        )
        sources_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 12), pady=8)
        self.sources_list.configure(yscrollcommand=sources_scroll.set)
        for p in self.source_dirs:
            self.sources_list.insert("end", str(p))
        btn = ttk.Frame(frame)
        btn.grid(row=1, column=0, sticky="ew", padx=12)
        ttk.Button(btn, text="Add", command=self.add_source_dir).grid(row=0, column=0)
        ttk.Button(btn, text="Remove", command=self.remove_source_dir).grid(
            row=0, column=1
        )
        ttk.Button(btn, text="Move Up", command=lambda: self.move_source_dir(-1)).grid(
            row=0, column=2
        )
        ttk.Button(btn, text="Move Down", command=lambda: self.move_source_dir(1)).grid(
            row=0, column=3
        )
        ttk.Button(btn, text="Rescan", command=self.refresh_models).grid(
            row=0, column=4
        )

    def _on_library_selected(self, _event: tk.Event | None = None) -> None:
        selection = self.models_library_list.curselection()
        if selection:
            idx = int(selection[0])
            self.set_selected_model(self.models[idx])

    def update_model_details(self, model: ModelEntry | None = None) -> None:
        if not hasattr(self, "model_detail_vars"):
            return
        model = model or self.selected_model
        if not model:
            self.model_detail_vars["Name"].set("No model selected")
            self.model_detail_vars["Alias"].set("--")
            self.model_detail_vars["Path"].set("--")
            self.model_detail_vars["Size"].set("--")
            self.model_detail_vars["Quant"].set("--")
            self.model_detail_vars["Source"].set("--")
            return
        self.model_detail_vars["Name"].set(model.name)
        self.model_detail_vars["Alias"].set(model.alias)
        self.model_detail_vars["Path"].set(str(model.path))
        self.model_detail_vars["Size"].set(f"{model.size_gb:g} GB")
        self.model_detail_vars["Quant"].set(model.quant)
        self.model_detail_vars["Source"].set(model.directory)

    def open_selected_model_folder(self) -> None:
        if not self.selected_model:
            messagebox.showwarning("Open folder", "Select a model first.", parent=self)
            return
        folder = self.selected_model.path.parent
        self.log(f"Opening model folder: {folder}")
        if os.name == "nt":
            os.startfile(folder)  # type: ignore[attr-defined]
        else:
            webbrowser.open(folder.as_uri())

    def copy_selected_model_path(self) -> None:
        if not self.selected_model:
            messagebox.showwarning("Copy path", "Select a model first.", parent=self)
            return
        path = str(self.selected_model.path)
        self.clipboard_clear()
        self.clipboard_append(path)
        self.log(f"Copied model path to clipboard: {path}")

    def browse_download_dir(self) -> None:
        path = filedialog.askdirectory(
            initialdir=self.download_dir_var.get() or str(HF_CACHE_DIR), parent=self
        )
        if path:
            self.download_dir_var.set(path)
            self.download_dir = Path(path)
            self.core.set_download_dir(path)
            self.log(f"Download directory set: {path}")

    def reset_download_dir(self) -> None:
        path = self.core.get_default_download_dir()
        self.download_dir_var.set(str(path))
        self.download_dir = path
        self.core.set_download_dir(path)
        self.log(f"Download directory reset to default: {path}")

    def add_source_dir(self) -> None:
        path = filedialog.askdirectory(parent=self)
        if path:
            self.sources_list.insert("end", path)
            self.core.save_model_source_dirs(
                [self.sources_list.get(i) for i in range(self.sources_list.size())]
            )
            self.log(f"Added model source folder: {path}")

    def remove_source_dir(self) -> None:
        sel = self.sources_list.curselection()
        if not sel:
            return
        removed = self.sources_list.get(sel[0])
        self.sources_list.delete(sel[0])
        self.core.save_model_source_dirs(
            [self.sources_list.get(i) for i in range(self.sources_list.size())]
        )
        self.log(f"Removed model source folder: {removed}")

    def move_source_dir(self, offset: int) -> None:
        sel = self.sources_list.curselection()
        if not sel:
            return
        i = sel[0]
        j = max(0, min(self.sources_list.size() - 1, i + offset))
        if i == j:
            return
        value = self.sources_list.get(i)
        self.sources_list.delete(i)
        self.sources_list.insert(j, value)
        self.sources_list.selection_set(j)
        self.core.save_model_source_dirs(
            [self.sources_list.get(i) for i in range(self.sources_list.size())]
        )
        self.log(f"Moved model source folder: {value} -> position {j + 1}")

    def _download_hf_worker(
        self, model: dict[str, str], status_label: ttk.Label, destination_root: Path
    ) -> None:
        try:
            api_url = f"https://huggingface.co/api/models/{model['Id']}"
            self.log(
                f"Fetching Hugging Face metadata: model_id={model['Id']} api={api_url}"
            )
            with urllib.request.urlopen(api_url, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
            ggufs = [
                s
                for s in data.get("siblings", [])
                if str(s.get("rfilename", "")).lower().endswith(".gguf")
            ]
            if not ggufs:
                raise RuntimeError("No GGUF files found")

            preferred_quant = str(model.get("PreferredQuant") or "Q4_K_M").lower()

            def gguf_rank(entry: dict[str, Any]) -> tuple[int, int]:
                filename = str(entry.get("rfilename", "")).lower()
                size = int(entry.get("size") or 0)
                quant_rank = 0 if preferred_quant in filename else 1
                fallback_rank = (
                    0 if any(q in filename for q in ("q4", "q3", "iq4")) else 1
                )
                return (quant_rank, fallback_rank, size)

            ggufs.sort(key=gguf_rank)
            selected_file = ggufs[0]
            filename = selected_file["rfilename"]
            file_size = selected_file.get("size")
            dest_dir = destination_root / model["Id"].replace("/", "__")
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path = dest_dir / Path(filename).name
            url = f"https://huggingface.co/{model['Id']}/resolve/main/{filename}"
            alias = sanitize_alias(model["Name"], 30)
            self.after(
                0,
                lambda: status_label.configure(
                    text=f"Downloading {Path(filename).name}..."
                ),
            )
            self.log(
                f"Selected GGUF file: model_id={model['Id']} preferred_quant={preferred_quant} filename={filename} size_bytes={file_size or 'unknown'}"
            )
            self.log(
                f"Download start: url={url} destination_dir={dest_dir} final_path={dest_path} registry_alias={alias}"
            )
            if dest_path.exists():
                self.log(f"Download skipped; file already exists: {dest_path}")
            else:
                urllib.request.urlretrieve(url, dest_path)
                self.log(f"Downloaded file written to: {dest_path}")
            self.core.add_model_to_registry(alias, dest_path)
            self.after(0, self.refresh_models)
            self.after(0, lambda: self.select_model_by_path(dest_path))
            self.after(
                0, lambda: status_label.configure(text=f"Downloaded: {dest_path}")
            )
            self.log(
                f"Download complete: model_id={model['Id']} final_path={dest_path} registry_alias={alias}"
            )
        except Exception as exc:
            message = str(exc)
            self.after(
                0, lambda: status_label.configure(text=f"Download failed: {message}")
            )
            self.log(
                f"[ERROR] Download failed: model_id={model.get('Id')} error={message}"
            )

    def on_close(self) -> None:
        try:
            self.save_current_session()
        except Exception:
            pass
        if self.process and self.process.poll() is None:
            if messagebox.askyesno(
                "Quit", "llama-server is running. Stop it and quit?", parent=self
            ):
                self.stop_server()
            else:
                return
        self.destroy()
