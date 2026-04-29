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

from .chat import ChatAPIError, ChatMessage, get_model_id, stream_chat_events
from .command_builder import args_to_list, build_command_args, command_string
from .core import LauncherCore, sanitize_alias
from .models import ModelEntry, detect_quant
from .monitoring import parse_prometheus_metrics as _parse_prometheus_metrics
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
from .services.launcher_service import LaunchRequest, LauncherService, RunningProcess
from .services.monitoring_service import MonitoringService
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


APP_TITLE = "Malina's Llama Launcher"


def parse_prometheus_metrics(content: str) -> dict[str, Any]:
    return _parse_prometheus_metrics(content)


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent: tk.Misc, *, style: str = "TFrame") -> None:
        super().__init__(parent, style=style)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(
            self,
            bg=TurboLauncherApp.COLORS["bg"],
            highlightthickness=0,
            borderwidth=0,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.content = ttk.Frame(self.canvas, style=style)
        self.content.columnconfigure(0, weight=1)
        self._window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind(
            "<Configure>",
            lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(self._window, width=e.width),
        )
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)
        self.content.bind("<Enter>", self._bind_mousewheel)
        self.content.bind("<Leave>", self._unbind_mousewheel)

    def _bind_mousewheel(self, _event: tk.Event) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event: tk.Event) -> None:
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event: tk.Event) -> str:
        if hasattr(event, "delta") and event.delta:
            step = -1 * int(event.delta / 120) if event.delta else 0
        else:
            num = getattr(event, "num", 0)
            step = -1 if num == 4 else (1 if num == 5 else 0)
        if step:
            self.canvas.yview_scroll(step, "units")
        return "break"


class TurboLauncherApp(tk.Tk):
    COLORS = {
        "bg": "#0b1020",
        "panel": "#111827",
        "panel2": "#162033",
        "surface": "#0f172a",
        "surface2": "#0b1220",
        "text": "#e5e7eb",
        "muted": "#9ca3af",
        "accent": "#60a5fa",
        "accent2": "#38bdf8",
        "green": "#34d399",
        "orange": "#fb923c",
        "red": "#f87171",
        "line": "#243041",
    }

    BODY_FONT = ("Segoe UI", 10)
    TITLE_FONT = ("Bahnschrift SemiBold", 18)
    SECTION_FONT = ("Segoe UI Semibold", 10)

    def __init__(self, runtime_path: str | None = None) -> None:
        super().__init__()
        self.core = LauncherCore(runtime_path)
        self.launcher_service = LauncherService()
        self.monitoring_service = MonitoringService()
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
        self.running_process: RunningProcess | None = None
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
        self.chat_state_file = SESSION_DIR / "chat_state.json"
        self.chat_state: dict[str, Any] = {"models": {}}
        self.chat_history: list[ChatMessage] = []
        self.chat_settings_visible = False
        self.chat_request_in_flight = False
        self.chat_status_var = tk.StringVar(value="Idle")
        self.chat_model_id_var = tk.StringVar(value="--")
        self.chat_endpoint_var = tk.StringVar(value="--")
        self.chat_template_note_var = tk.StringVar(
            value="Template changes apply on next server start."
        )
        self.command_preview_text: tk.Text | None = None
        self.warning_text: tk.Text | None = None
        self.logo_image: tk.PhotoImage | None = None
        self.header_logo_image: tk.PhotoImage | None = None
        self.gpu_layers_scale: ttk.Scale | None = None
        self.full_offload_button: ttk.Button | None = None
        self.gpu_offload_help_var = tk.StringVar(value="GPU layer count passed to llama.cpp.")

        self.title(APP_TITLE)
        self.geometry("1280x860")
        self.minsize(1180, 720)
        self.configure(bg=self.COLORS["bg"])

        self.vars: dict[str, tk.Variable] = {}
        self.metric_vars: dict[str, tk.StringVar] = {}
        self._configure_style()
        self._create_variables()
        self._build_ui()
        self.set_status("Stopped", "muted")
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
        style.configure("TopBar.TFrame", background=c["surface"])
        style.configure("Panel.TFrame", background=c["panel"])
        style.configure("Surface.TFrame", background=c["surface2"])
        style.configure(
            "TLabel", background=c["bg"], foreground=c["text"], font=self.BODY_FONT
        )
        style.configure("Muted.TLabel", background=c["bg"], foreground=c["muted"])
        style.configure("TopBar.TLabel", background=c["surface"], foreground=c["text"])
        style.configure("Panel.TLabel", background=c["panel"], foreground=c["text"])
        style.configure(
            "Title.TLabel",
            background=c["bg"],
            foreground=c["text"],
            font=self.TITLE_FONT,
        )
        style.configure(
            "TopTitle.TLabel",
            background=c["surface"],
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
            "Pill.TLabel",
            background=c["surface2"],
            foreground=c["text"],
            font=("Segoe UI Semibold", 9),
            padding=(10, 4),
        )
        style.configure(
            "Status.TLabel",
            background=c["surface"],
            foreground=c["text"],
            font=("Segoe UI Semibold", 15),
        )
        style.configure(
            "StatusCard.TLabel",
            background=c["panel"],
            foreground=c["text"],
            font=("Segoe UI Semibold", 15),
        )
        style.configure(
            "Accent.TButton",
            background=c["accent"],
            foreground="#08111f",
            font=("Segoe UI Semibold", 10),
            padding=(12, 8),
        )
        style.configure(
            "Danger.TButton",
            background="#7f1d1d",
            foreground=c["text"],
            padding=(12, 8),
        )
        style.configure(
            "TButton",
            background=c["panel2"],
            foreground=c["text"],
            padding=(10, 7),
        )
        style.map(
            "TButton",
            background=[("active", c["surface2"]), ("pressed", c["surface"])],
            foreground=[("disabled", c["muted"])],
        )
        style.map(
            "Accent.TButton",
            background=[("active", c["accent2"]), ("pressed", c["accent"])],
            foreground=[("disabled", "#0f172a")],
        )
        style.configure(
            "TEntry",
            fieldbackground=c["surface2"],
            foreground=c["text"],
            insertcolor=c["text"],
            bordercolor=c["line"],
            relief="flat",
        )
        style.configure(
            "TCombobox",
            fieldbackground=c["surface2"],
            foreground=c["text"],
            arrowcolor=c["text"],
            bordercolor=c["line"],
            lightcolor=c["line"],
            darkcolor=c["line"],
            padding=4,
        )
        style.map(
            "TCombobox",
            fieldbackground=[
                ("readonly", c["surface2"]),
                ("active", c["surface2"]),
                ("focus", c["surface2"]),
            ],
            foreground=[("readonly", c["text"]), ("disabled", c["muted"])],
            selectbackground=[("readonly", c["accent"])],
            selectforeground=[("readonly", "#08111f")],
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
            background=[("selected", c["panel"]), ("active", c["surface2"])],
            foreground=[("selected", c["text"]), ("active", c["text"])],
        )
        style.configure(
            "TCheckbutton", background=c["bg"], foreground=c["text"], padding=2
        )
        style.configure(
            "Panel.TCheckbutton", background=c["panel"], foreground=c["text"]
        )
        style.configure("Card.TFrame", background=c["panel"], relief="flat")
        style.configure("CardInner.TFrame", background=c["panel2"])
        style.configure("Card.TLabel", background=c["panel"], foreground=c["text"])
        style.configure(
            "CardMuted.TLabel", background=c["panel"], foreground=c["muted"]
        )
        style.configure("Transparent.TFrame", background=c["surface"], relief="flat")
        self.option_add("*TCombobox*Listbox.background", c["surface2"])
        self.option_add("*TCombobox*Listbox.foreground", c["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", c["accent"])
        self.option_add("*TCombobox*Listbox.selectForeground", "#08111f")
        self.option_add("*TCombobox*Listbox.font", self.BODY_FONT)

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
            "requests_active",
            "requests_queued",
            "tokens",
            "prompt_tokens",
            "session_slot",
            "session_progress",
            "prompt_progress",
            "prompt_processed",
            "session_decoded",
            "session_remaining",
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
        root.rowconfigure(1, weight=1)
        root.columnconfigure(0, weight=1)

        self._build_top_bar(root)

        body = ttk.Frame(root, style="TFrame")
        body.grid(row=1, column=0, sticky="nsew", pady=(12, 10))
        body.columnconfigure(0, weight=0)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left = ScrollableFrame(body, style="Panel.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.configure(width=520)
        left.content.columnconfigure(0, weight=1)
        self._build_left_panel(left.content)

        right = ttk.Frame(body, style="TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)
        self._build_right_panel(right)

        self._build_bottom_panel(root)

    def _load_logo_image(self) -> None:
        logo_path = Path(__file__).resolve().parent.parent / "resources" / "images" / "logo.png"
        try:
            if logo_path.exists():
                self.logo_image = tk.PhotoImage(file=str(logo_path))
                self.header_logo_image = self.logo_image
                width = max(1, self.logo_image.width())
                height = max(1, self.logo_image.height())
                max_header_size = 32
                shrink = max(1, max((width + max_header_size - 1) // max_header_size, (height + max_header_size - 1) // max_header_size))
                if shrink > 1:
                    self.header_logo_image = self.logo_image.subsample(shrink, shrink)
                try:
                    self.iconphoto(True, self.logo_image)
                except tk.TclError:
                    pass
        except Exception:
            self.logo_image = None
            self.header_logo_image = None

    def _build_top_bar(self, parent: ttk.Frame) -> None:
        bar = ttk.Frame(parent, style="TopBar.TFrame", height=72)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_propagate(False)
        bar.columnconfigure(1, weight=1)
        bar.columnconfigure(2, weight=0)
        bar.columnconfigure(3, weight=0)

        self._load_logo_image()
        brand = ttk.Frame(bar, style="TopBar.TFrame")
        brand.grid(row=0, column=0, sticky="w", padx=(6, 16), pady=10)
        if self.header_logo_image is not None:
            ttk.Label(brand, image=self.header_logo_image, style="TopBar.TLabel").grid(
                row=0, column=0, rowspan=2, sticky="w", padx=(0, 10)
            )
        ttk.Label(brand, text=APP_TITLE, style="TopTitle.TLabel").grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(
            brand,
            text="Local llama-server launcher for models, presets, runtime, and live monitoring.",
            style="TopBar.TLabel",
        ).grid(row=1, column=1, sticky="w", pady=(2, 0))

        center = ttk.Frame(bar, style="TopBar.TFrame")
        center.grid(row=0, column=1, sticky="ew", padx=8)
        center.columnconfigure(0, weight=1)
        profile = ttk.Frame(center, style="TopBar.TFrame")
        profile.grid(row=0, column=0, sticky="w")
        ttk.Label(profile, text="Active profile", style="TopBar.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(profile, textvariable=self.metric_vars["preset"], style="Pill.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))

        self.status_dot = ttk.Label(bar, text="●", foreground=self.COLORS["muted"], background=self.COLORS["surface"], font=("Segoe UI", 18))
        self.status_dot.grid(row=0, column=2, padx=(0, 8))
        self.status_value_label = ttk.Label(bar, textvariable=self.metric_vars["status"], style="Status.TLabel")
        self.status_value_label.grid(row=0, column=3, padx=(0, 14))
        ttk.Button(bar, text="Start", style="Accent.TButton", command=self.start_server).grid(
            row=0, column=4, padx=(0, 8)
        )
        ttk.Button(bar, text="Stop", style="Danger.TButton", command=self.stop_server).grid(
            row=0, column=5, padx=(0, 8)
        )
        ttk.Button(bar, text="Runtime", command=self.settings_dialog).grid(
            row=0, column=6, padx=(0, 6)
        )

    def _build_left_panel(self, parent: ttk.Frame) -> None:
        self._build_model_card(parent)
        self._build_preset_card(parent)
        self._build_runtime_card(parent)

        self.notebook = ttk.Notebook(parent)
        self.notebook.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        self.launch_tab = self._new_tab("Overview")
        self.sampling_tab = self._new_tab("Sampling")
        self.server_tab = self._new_tab("Server")
        self.reasoning_tab = self._new_tab("Reasoning")
        self.monitoring_tab = self._new_tab("Monitoring")
        self.chat_tab = self._new_tab("Chat")
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
        self._build_chat_tab()
        self._build_models_tabs()

    def _build_model_card(self, parent: ttk.Frame) -> None:
        card = ttk.Frame(parent, style="Card.TFrame")
        card.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 12))
        card.columnconfigure(0, weight=1)
        inner = ttk.Frame(card, style="Card.TFrame")
        inner.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)
        inner.columnconfigure(0, minsize=92)
        inner.columnconfigure(1, weight=1)
        inner.columnconfigure(1, minsize=220)
        inner.columnconfigure(2, minsize=88)
        self._section_title(inner, "Model", "Pick the active GGUF model and keep its file details in view.")
        ttk.Label(inner, text="Active model", style="CardMuted.TLabel").grid(
            row=1, column=0, sticky="w", pady=(2, 2)
        )
        self.launch_model_var = tk.StringVar(value="")
        self.launch_model_picker = ttk.Combobox(
            inner,
            textvariable=self.launch_model_var,
            state="readonly",
            values=[],
            width=30,
        )
        self.launch_model_picker.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(2, 2))
        self.launch_model_picker.bind("<<ComboboxSelected>>", self._on_launch_model_selected)
        ttk.Button(inner, text="Library", command=self.focus_models_tab).grid(row=1, column=2, sticky="e", padx=(8, 0))

        self.model_context_vars = {
            "Name": tk.StringVar(value="No model selected"),
            "Alias": tk.StringVar(value="--"),
            "Path": tk.StringVar(value="--"),
            "Size": tk.StringVar(value="--"),
            "Quant": tk.StringVar(value="--"),
            "Source": tk.StringVar(value="--"),
            "Suggestion": tk.StringVar(value="Pick a model in Models → Library to fill the overview and command preview."),
        }
        details = ttk.Frame(inner, style="Card.TFrame")
        details.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        details.columnconfigure(1, weight=1)
        for row, label in enumerate(["Name", "Alias", "Path", "Size", "Quant", "Source"]):
            ttk.Label(details, text=f"{label}:", style="CardMuted.TLabel").grid(row=row, column=0, sticky="nw", padx=(0, 10), pady=3)
            ttk.Label(details, textvariable=self.model_context_vars[label], style="Card.TLabel", wraplength=360).grid(row=row, column=1, sticky="nw", pady=3)
        ttk.Label(inner, textvariable=self.model_context_vars["Suggestion"], style="CardMuted.TLabel", wraplength=360).grid(row=3, column=0, columnspan=3, sticky="w", pady=(10, 0))

    def _build_preset_card(self, parent: ttk.Frame) -> None:
        card = ttk.Frame(parent, style="Card.TFrame")
        card.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 12))
        card.columnconfigure(0, weight=1)
        ttk.Label(card, text="PRESETS", style="Section.TLabel").grid(row=0, column=0, sticky="w", padx=14, pady=(12, 8))
        self.preset_list = tk.Listbox(
            card,
            height=6,
            bg=self.COLORS["surface2"],
            fg=self.COLORS["text"],
            selectbackground=self.COLORS["accent"],
            selectforeground="#08111f",
            activestyle="none",
            highlightthickness=1,
            highlightbackground=self.COLORS["line"],
            highlightcolor=self.COLORS["accent"],
            relief="flat",
            borderwidth=0,
            font=self.BODY_FONT,
            exportselection=False,
        )
        self.preset_list.grid(row=1, column=0, sticky="ew", padx=14)
        preset_scroll = ttk.Scrollbar(card, orient="vertical", command=self.preset_list.yview)
        preset_scroll.grid(row=1, column=1, sticky="ns", padx=(0, 14))
        self.preset_list.configure(yscrollcommand=preset_scroll.set)
        preset_buttons = ttk.Frame(card, style="Card.TFrame")
        preset_buttons.grid(row=2, column=0, sticky="ew", padx=14, pady=12)
        preset_buttons.columnconfigure(0, weight=1)
        preset_buttons.columnconfigure(1, weight=1)
        ttk.Button(preset_buttons, text="Save", command=self.save_preset_dialog).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(preset_buttons, text="Reload", command=self.refresh_presets).grid(row=0, column=1, sticky="ew", padx=(4, 0))

    def _build_runtime_card(self, parent: ttk.Frame) -> None:
        card = ttk.Frame(parent, style="Card.TFrame")
        card.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 12))
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)
        card.columnconfigure(2, weight=1)
        ttk.Label(card, text="RUNTIME", style="Section.TLabel").grid(row=0, column=0, sticky="w", padx=14, pady=(12, 6))
        inner = ttk.Frame(card, style="Card.TFrame")
        inner.grid(row=1, column=0, columnspan=3, sticky="ew", padx=14, pady=(0, 10))
        inner.columnconfigure(0, weight=1)
        inner.columnconfigure(1, weight=1)
        ttk.Label(inner, text="GPU offload layers", style="CardMuted.TLabel").grid(row=0, column=0, sticky="w")
        self.gpu_layers_label = ttk.Label(inner, text="30", foreground=self.COLORS["accent"], background=self.COLORS["panel"], font=("Segoe UI Semibold", 11))
        self.gpu_layers_label.grid(row=0, column=1, sticky="e")
        self.gpu_layers_scale = ttk.Scale(inner, from_=0, to=40, variable=self.vars["GpuLayers"], command=self._gpu_layers_changed)
        self.gpu_layers_scale.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 10))
        self.gpu_layers_scale.bind("<ButtonRelease-1>", self.on_setting_changed)
        helper = ttk.Frame(card, style="Card.TFrame")
        helper.grid(row=2, column=0, columnspan=3, sticky="ew", padx=14, pady=(0, 8))
        helper.columnconfigure(0, weight=1)
        ttk.Label(helper, textvariable=self.gpu_offload_help_var, style="CardMuted.TLabel", wraplength=430).grid(row=0, column=0, sticky="w")
        self.full_offload_button = ttk.Button(helper, text="Full offload", command=self.set_full_offload_layers)
        self.full_offload_button.grid(row=0, column=1, sticky="e", padx=(10, 0))
        row = ttk.Frame(card, style="Card.TFrame")
        row.grid(row=3, column=0, columnspan=3, sticky="ew", padx=14, pady=(0, 12))
        for idx in range(4):
            row.columnconfigure(idx, weight=1)
        self._entry(row, 0, 0, "Host", "Host", width=12)
        self._entry(row, 0, 1, "Port", "Port", width=10)
        self._combo(row, 0, 2, "Context", "CtxSize", ["4096", "8192", "16384", "32768", "65536", "131072"], state="normal")
        self._combo(row, 0, 3, "Cache K", "CacheTypeK", CACHE_TYPES)
        self._combo(row, 2, 0, "Cache V", "CacheTypeV", CACHE_TYPES)
        self._combo(row, 2, 1, "Split Mode", "SplitMode", SPLIT_MODES)
        self._entry(row, 2, 2, "Alias", "Alias", width=14)
        self._check(row, 2, 3, "Flash Attn", "FlashAttn")

    def _build_right_panel(self, parent: ttk.Frame) -> None:
        self._build_status_card(parent)
        self._build_endpoint_card(parent)
        self._build_command_card(parent)

    def _build_status_card(self, parent: ttk.Frame) -> None:
        card = ttk.Frame(parent, style="Card.TFrame")
        card.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        card.columnconfigure(0, weight=1)
        inner = ttk.Frame(card, style="Card.TFrame")
        inner.grid(row=0, column=0, sticky="ew", padx=16, pady=16)
        inner.columnconfigure(0, weight=1)
        ttk.Label(inner, text="Current status", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(inner, textvariable=self.metric_vars["status"], style="StatusCard.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 6))
        ttk.Label(inner, textvariable=self.metric_vars["model"], style="CardMuted.TLabel", wraplength=420).grid(row=2, column=0, sticky="w")
        buttons = ttk.Frame(inner, style="Card.TFrame")
        buttons.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        buttons.columnconfigure(2, weight=1)
        ttk.Button(buttons, text="Start", style="Accent.TButton", command=self.start_server).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(buttons, text="Stop", style="Danger.TButton", command=self.stop_server).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(buttons, text="Models", command=self.focus_models_tab).grid(row=0, column=2, sticky="ew", padx=(6, 0))

    def _build_endpoint_card(self, parent: ttk.Frame) -> None:
        card = ttk.Frame(parent, style="Card.TFrame")
        card.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        card.columnconfigure(1, weight=1)
        self._section_title(card, "Endpoint + resources", "Server address, estimate, and health at a glance.")
        body = ttk.Frame(card, style="Card.TFrame")
        body.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))
        body.columnconfigure(1, weight=1)
        ttk.Label(body, text="Endpoint", style="CardMuted.TLabel").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Label(body, textvariable=self.chat_endpoint_var, style="Card.TLabel").grid(row=0, column=1, sticky="w", pady=3)
        ttk.Label(body, text="Uptime", style="CardMuted.TLabel").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Label(body, textvariable=self.metric_vars["uptime"], style="Card.TLabel").grid(row=1, column=1, sticky="w", pady=3)
        ttk.Label(body, text="VRAM estimate", style="CardMuted.TLabel").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Label(body, textvariable=self.metric_vars["vram_detail"], style="Card.TLabel").grid(row=2, column=1, sticky="w", pady=3)
        self.vram_bar = ttk.Progressbar(body, maximum=16.0, value=0)
        self.vram_bar.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 10))
        metrics = ttk.Frame(body, style="Card.TFrame")
        metrics.grid(row=4, column=0, columnspan=2, sticky="ew")
        for idx in range(4):
            metrics.columnconfigure(idx, weight=1)
        self._summary_label(metrics, "TPS", self.metric_vars["tps"], 0)
        self._summary_label(metrics, "CPU", self.metric_vars["cpu"], 1)
        self._summary_label(metrics, "RAM", self.metric_vars["ram"], 2)
        self._summary_label(metrics, "GPU", self.metric_vars["gpu"], 3)

    def _build_command_card(self, parent: ttk.Frame) -> None:
        card = ttk.Frame(parent, style="Card.TFrame")
        card.grid(row=2, column=0, sticky="nsew")
        card.rowconfigure(1, weight=1)
        card.columnconfigure(0, weight=1)
        header = ttk.Frame(card, style="Card.TFrame")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Generated command", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(header, text="Copy command", command=self.export_command).grid(row=0, column=1, sticky="e")
        self.command_preview_text = tk.Text(
            card,
            bg=self.COLORS["surface2"],
            fg=self.COLORS["text"],
            insertbackground=self.COLORS["text"],
            relief="flat",
            height=7,
            wrap="none",
            font=("Consolas", 9),
            borderwidth=0,
        )
        self.command_preview_text.grid(row=1, column=0, sticky="nsew", padx=16)
        self.command_preview_text.configure(state="disabled")
        cmd_scroll = ttk.Scrollbar(card, orient="horizontal", command=self.command_preview_text.xview)
        cmd_scroll.grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 14))
        self.command_preview_text.configure(xscrollcommand=cmd_scroll.set)

    def _build_bottom_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent, style="Panel.TFrame")
        panel.grid(row=2, column=0, sticky="ew")
        panel.rowconfigure(0, weight=1)
        panel.columnconfigure(0, weight=1)
        self.bottom_notebook = ttk.Notebook(panel)
        self.bottom_notebook.grid(row=0, column=0, sticky="nsew", padx=0, pady=(0, 0))

        logs_tab = ttk.Frame(self.bottom_notebook, style="Panel.TFrame")
        metrics_tab = ttk.Frame(self.bottom_notebook, style="Panel.TFrame")
        warnings_tab = ttk.Frame(self.bottom_notebook, style="Panel.TFrame")
        self.bottom_notebook.add(logs_tab, text="Logs")
        self.bottom_notebook.add(metrics_tab, text="Metrics")
        self.bottom_notebook.add(warnings_tab, text="Warnings")

        logs_tab.rowconfigure(1, weight=1)
        logs_tab.columnconfigure(0, weight=1)
        actions = ttk.Frame(logs_tab, style="Panel.TFrame")
        actions.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))
        actions.columnconfigure(3, weight=1)
        ttk.Button(actions, text="Copy command", command=self.export_command).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(actions, text="Runtime", command=self.settings_dialog).grid(row=0, column=1, padx=6)
        ttk.Button(actions, text="Clear logs", command=lambda: self.terminal.delete("1.0", "end")).grid(row=0, column=2, padx=6)

        self.terminal = tk.Text(
            logs_tab,
            bg=self.COLORS["surface2"],
            fg=self.COLORS["text"],
            insertbackground=self.COLORS["text"],
            relief="flat",
            height=10,
            wrap="word",
            font=("Consolas", 10),
            borderwidth=0,
        )
        self.terminal.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        term_scroll = ttk.Scrollbar(logs_tab, orient="vertical", command=self.terminal.yview)
        term_scroll.grid(row=1, column=1, sticky="ns", pady=(0, 12))
        self.terminal.configure(yscrollcommand=term_scroll.set)

        metrics_scroll = ScrollableFrame(metrics_tab, style="Panel.TFrame")
        metrics_scroll.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        metrics_body = metrics_scroll.content
        metrics_body.columnconfigure(0, weight=1)
        metrics_body.columnconfigure(1, weight=1)
        metrics_body.columnconfigure(2, weight=1)
        metrics_body.columnconfigure(3, weight=1)
        for idx, (label, key) in enumerate([
            ("Status", "status"),
            ("Uptime", "uptime"),
            ("Tokens/sec", "tps"),
            ("Prompt eval/sec", "peps"),
            ("Decode ms/token", "decode_time"),
            ("Prompt ms/token", "prompt_time"),
            ("Context", "context"),
            ("KV Cache", "kv_cache"),
            ("Prompt Tokens", "prompt_tokens"),
            ("Generated Tokens", "tokens"),
            ("Active Requests", "requests_active"),
            ("Queued Requests", "requests_queued"),
            ("Active Slot", "session_slot"),
            ("Session Progress", "session_progress"),
            ("Prompt Progress", "prompt_progress"),
            ("Prompt Processed", "prompt_processed"),
            ("Session Decoded", "session_decoded"),
            ("Session Remaining", "session_remaining"),
        ]):
            row = idx // 2
            col = (idx % 2) * 2
            ttk.Label(metrics_body, text=label, style="Panel.TLabel", foreground=self.COLORS["muted"]).grid(row=row, column=col, sticky="w", padx=12, pady=7)
            ttk.Label(metrics_body, textvariable=self.metric_vars[key], style="Panel.TLabel", font=("Segoe UI Semibold", 10)).grid(row=row, column=col + 1, sticky="w", padx=12, pady=7)

        self.warning_text = tk.Text(
            warnings_tab,
            bg=self.COLORS["surface2"],
            fg=self.COLORS["text"],
            insertbackground=self.COLORS["text"],
            relief="flat",
            height=5,
            wrap="word",
            font=self.BODY_FONT,
            borderwidth=0,
            state="disabled",
        )
        self.warning_text.pack(fill="both", expand=True, padx=12, pady=12)
        self._update_warning_notes()

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
        scroll = ScrollableFrame(parent, style="TFrame")
        scroll.grid(row=0, column=0, sticky="nsew")
        frame = ttk.Frame(scroll.content, style="TFrame")
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

        frame = ttk.Frame(tab, style="TFrame")
        frame.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        frame.columnconfigure(0, weight=1)
        self._section_title(
            frame,
            "Overview",
            "A compact launch dashboard with model context, launch guidance, and shortcuts for the active profile.",
        )

        info = ttk.Frame(frame, style="Card.TFrame")
        info.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        info.columnconfigure(1, weight=1)
        for row, (label, key) in enumerate([("Model", "model"), ("Preset", "preset"), ("Status", "status"), ("VRAM", "vram")]):
            ttk.Label(info, text=label, style="CardMuted.TLabel").grid(row=row, column=0, sticky="w", padx=14, pady=6)
            ttk.Label(info, textvariable=self.metric_vars[key], style="Card.TLabel").grid(row=row, column=1, sticky="w", padx=14, pady=6)

        guidance = ttk.Frame(frame, style="Card.TFrame")
        guidance.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        guidance.columnconfigure(0, weight=1)
        self._section_title(guidance, "Launch guidance", "Use the left panel to pick the model and core runtime shape; advanced tabs stay tucked away below.")
        ttk.Label(guidance, textvariable=self.model_context_vars["Suggestion"], style="CardMuted.TLabel", wraplength=860).grid(row=1, column=0, sticky="w", padx=14, pady=(0, 14))

        actions = ttk.Frame(frame, style="Card.TFrame")
        actions.grid(row=3, column=0, sticky="ew")
        for idx in range(4):
            actions.columnconfigure(idx, weight=1)
        ttk.Button(actions, text="Open folder", command=self.open_selected_model_folder).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(actions, text="Copy path", command=self.copy_selected_model_path).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(actions, text="Go to Models", command=self.focus_models_tab).grid(row=0, column=2, sticky="ew", padx=6)
        ttk.Button(actions, text="Copy command", command=self.export_command).grid(row=0, column=3, sticky="ew", padx=(6, 0))

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
            text="Server-level flags stay here; model-specific placement and memory controls are grouped in Overview.",
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
            ("Prompt Tokens", "prompt_tokens"),
            ("Requests", "requests"),
            ("Active Requests", "requests_active"),
            ("Queued Requests", "requests_queued"),
            ("Active Slot", "session_slot"),
            ("Session Progress", "session_progress"),
            ("Prompt Progress", "prompt_progress"),
            ("Prompt Processed", "prompt_processed"),
            ("Session Decoded", "session_decoded"),
            ("Session Remaining", "session_remaining"),
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

    def _build_chat_tab(self) -> None:
        tab = self.chat_tab
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        tab.rowconfigure(2, weight=0)

        top_card = ttk.Frame(tab, style="Card.TFrame")
        top_card.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 10))
        top_inner = ttk.Frame(top_card, style="Card.TFrame")
        top_inner.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)
        top_inner.columnconfigure(1, weight=1)
        self._section_title(
            top_inner,
            "Chat",
            "Stream replies from the active llama-server using the current host, port, and selected model.",
        )

        controls = ttk.Frame(top_inner, style="Card.TFrame")
        controls.grid(row=1, column=0, columnspan=2, sticky="ew")
        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(3, weight=1)
        ttk.Label(controls, text="Model", style="CardMuted.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        self.chat_model_label = ttk.Label(
            controls, textvariable=self.metric_vars["model"], style="Card.TLabel"
        )
        self.chat_model_label.grid(row=0, column=1, sticky="w")
        ttk.Label(controls, text="Endpoint", style="CardMuted.TLabel").grid(
            row=0, column=2, sticky="w", padx=(16, 8)
        )
        ttk.Label(
            controls, textvariable=self.chat_endpoint_var, style="Card.TLabel"
        ).grid(row=0, column=3, sticky="w")

        actions = ttk.Frame(top_inner, style="Card.TFrame")
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        actions.columnconfigure(5, weight=1)
        self.chat_settings_toggle = ttk.Button(
            actions, text="Show Settings", command=self.toggle_chat_settings
        )
        self.chat_settings_toggle.grid(row=0, column=0, padx=(0, 6))
        ttk.Button(actions, text="Use Model Defaults", command=self.reset_chat_overrides).grid(
            row=0, column=1, padx=6
        )
        ttk.Button(actions, text="Clear Chat", command=self.clear_chat_history).grid(
            row=0, column=2, padx=6
        )
        ttk.Label(
            actions, textvariable=self.chat_status_var, style="CardMuted.TLabel"
        ).grid(row=0, column=6, sticky="e")

        self.chat_settings_panel = ttk.Frame(top_inner, style="CardInner.TFrame")
        self.chat_settings_panel.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.chat_settings_panel.columnconfigure(0, weight=1)
        self.chat_settings_panel.columnconfigure(1, weight=1)
        ttk.Label(
            self.chat_settings_panel, text="Loaded model id", style="CardMuted.TLabel"
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 2))
        ttk.Label(
            self.chat_settings_panel, textvariable=self.chat_model_id_var, style="Card.TLabel"
        ).grid(row=1, column=0, sticky="w", padx=10, pady=(0, 10))
        ttk.Label(
            self.chat_settings_panel, text="Prompt template", style="CardMuted.TLabel"
        ).grid(row=0, column=1, sticky="w", padx=10, pady=(10, 2))
        ttk.Label(
            self.chat_settings_panel,
            textvariable=self.chat_template_note_var,
            style="CardMuted.TLabel",
            wraplength=420,
        ).grid(row=1, column=1, sticky="w", padx=10, pady=(0, 10))

        ttk.Label(
            self.chat_settings_panel, text="System prompt", style="CardMuted.TLabel"
        ).grid(row=2, column=0, sticky="w", padx=10, pady=(0, 4))
        self.chat_system_prompt = tk.Text(
            self.chat_settings_panel,
            bg="#0b1220",
            fg=self.COLORS["text"],
            insertbackground=self.COLORS["text"],
            relief="flat",
            height=6,
            wrap="word",
            font=self.BODY_FONT,
        )
        self.chat_system_prompt.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 10))

        ttk.Label(
            self.chat_settings_panel, text="Prompt template", style="CardMuted.TLabel"
        ).grid(row=2, column=1, sticky="w", padx=10, pady=(0, 4))
        self.chat_template_text = tk.Text(
            self.chat_settings_panel,
            bg="#0b1220",
            fg=self.COLORS["text"],
            insertbackground=self.COLORS["text"],
            relief="flat",
            height=6,
            wrap="word",
            font=("Consolas", 10),
        )
        self.chat_template_text.grid(row=3, column=1, sticky="nsew", padx=10, pady=(0, 10))

        self.chat_settings_panel.grid_remove()

        history_card = ttk.Frame(tab, style="Panel.TFrame")
        history_card.grid(row=1, column=0, sticky="nsew", padx=8)
        history_card.rowconfigure(0, weight=1)
        history_card.columnconfigure(0, weight=1)
        self.chat_history_text = tk.Text(
            history_card,
            bg="#020617",
            fg="#d1d5db",
            insertbackground="#d1d5db",
            relief="flat",
            wrap="word",
            state="disabled",
            font=("Segoe UI", 10),
        )
        self.chat_history_text.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.chat_history_text.tag_configure("user_header", foreground=self.COLORS["accent"])
        self.chat_history_text.tag_configure("assistant_header", foreground=self.COLORS["green"])
        self.chat_history_text.tag_configure("system_header", foreground=self.COLORS["orange"])
        self.chat_history_text.tag_configure("body", foreground=self.COLORS["text"])
        chat_scroll = ttk.Scrollbar(
            history_card, orient="vertical", command=self.chat_history_text.yview
        )
        chat_scroll.grid(row=0, column=1, sticky="ns", pady=10)
        self.chat_history_text.configure(yscrollcommand=chat_scroll.set)

        input_card = ttk.Frame(tab, style="Card.TFrame")
        input_card.grid(row=2, column=0, sticky="ew", padx=8, pady=(10, 8))
        input_card.columnconfigure(0, weight=1)
        ttk.Label(input_card, text="Message", style="CardMuted.TLabel").grid(
            row=0, column=0, sticky="w", padx=14, pady=(12, 4)
        )
        self.chat_input = tk.Text(
            input_card,
            bg="#0b1220",
            fg=self.COLORS["text"],
            insertbackground=self.COLORS["text"],
            relief="flat",
            height=4,
            wrap="word",
            font=self.BODY_FONT,
        )
        self.chat_input.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
        self.chat_input.bind("<Return>", self._chat_input_return)
        self.chat_input.bind("<Shift-Return>", self._chat_input_shift_return)
        buttons = ttk.Frame(input_card, style="Card.TFrame")
        buttons.grid(row=1, column=1, sticky="ns", padx=(0, 14), pady=(0, 10))
        self.chat_send_button = ttk.Button(
            buttons, text="Send", style="Accent.TButton", command=self.send_chat_message
        )
        self.chat_send_button.grid(row=0, column=0, sticky="ew")

    def _wire_events(self) -> None:
        self.preset_list.bind("<<ListboxSelect>>", self.on_preset_selected)
        if hasattr(self, "models_library_list"):
            self.models_library_list.bind(
                "<<ListboxSelect>>", self._on_library_selected
            )
        if hasattr(self, "chat_system_prompt"):
            self.chat_system_prompt.bind("<FocusOut>", self._on_chat_settings_changed)
        if hasattr(self, "chat_template_text"):
            self.chat_template_text.bind("<FocusOut>", self._on_chat_settings_changed)

    def toggle_chat_settings(self) -> None:
        self.chat_settings_visible = not self.chat_settings_visible
        if self.chat_settings_visible:
            self.chat_settings_panel.grid()
            self.chat_settings_toggle.configure(text="Hide Settings")
        else:
            self.chat_settings_panel.grid_remove()
            self.chat_settings_toggle.configure(text="Show Settings")

    def _chat_storage_key(self, model: ModelEntry | None = None) -> str:
        model = model or self.selected_model
        if not model:
            return "default"
        return sanitize_alias(model.alias or model.name, 80)

    def _load_chat_state(self) -> None:
        try:
            with self.chat_state_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self.chat_state = data
        except Exception:
            self.chat_state = {"models": {}}
        if "models" not in self.chat_state or not isinstance(
            self.chat_state.get("models"), dict
        ):
            self.chat_state = {"models": {}}

    def _save_chat_state(self) -> None:
        if self._loading:
            return
        try:
            self.chat_state_file.parent.mkdir(parents=True, exist_ok=True)
            with self.chat_state_file.open("w", encoding="utf-8") as f:
                json.dump(self.chat_state, f, indent=2)
        except OSError as exc:
            self.log(f"[WARN] Failed to save chat state: {exc}")

    @staticmethod
    def _text_widget_value(widget: tk.Text) -> str:
        return widget.get("1.0", "end").rstrip()

    @staticmethod
    def _set_text_widget_value(widget: tk.Text, value: str) -> None:
        widget.delete("1.0", "end")
        if value:
            widget.insert("1.0", value)

    def _current_system_prompt(self) -> str:
        if hasattr(self, "chat_system_prompt"):
            return self._text_widget_value(self.chat_system_prompt)
        return self.selected_model.sys_prompt if self.selected_model else ""

    def _current_chat_template(self) -> str:
        if hasattr(self, "chat_template_text"):
            return self._text_widget_value(self.chat_template_text)
        return self.selected_model.chat_template if self.selected_model else ""

    def _store_chat_model_state(self) -> None:
        if not self.selected_model:
            return
        key = self._chat_storage_key(self.selected_model)
        models_state = self.chat_state.setdefault("models", {})
        models_state[key] = {
            "system_prompt": self._current_system_prompt(),
            "chat_template": self._current_chat_template(),
            "history": [
                {"role": message.role, "content": message.content}
                for message in self.chat_history
                if message.content.strip()
            ],
        }
        self._save_chat_state()

    def _load_chat_for_selected_model(self) -> None:
        if not hasattr(self, "chat_history_text"):
            return
        model = self.selected_model
        system_prompt = model.sys_prompt if model else ""
        chat_template = model.chat_template if model else ""
        history: list[ChatMessage] = []
        if model:
            state = self.chat_state.get("models", {}).get(self._chat_storage_key(model), {})
            if isinstance(state, dict):
                system_prompt = str(state.get("system_prompt", system_prompt or ""))
                chat_template = str(state.get("chat_template", chat_template or ""))
                raw_history = state.get("history", [])
                if isinstance(raw_history, list):
                    for item in raw_history:
                        if isinstance(item, dict):
                            role = str(item.get("role", "assistant"))
                            content = str(item.get("content", ""))
                            if content:
                                history.append(ChatMessage(role=role, content=content))
        self.chat_history = history
        if hasattr(self, "chat_system_prompt"):
            self._set_text_widget_value(self.chat_system_prompt, system_prompt)
        if hasattr(self, "chat_template_text"):
            self._set_text_widget_value(self.chat_template_text, chat_template)
        if model and model.chat_template:
            self.chat_template_note_var.set(
                "Template changes apply on next server start and are added to the launch command."
            )
        else:
            self.chat_template_note_var.set(
                "Template changes apply on next server start."
            )
        self.chat_model_id_var.set(model.alias if model else "--")
        self._update_chat_endpoint_preview()
        self._render_chat_history()

    def _render_chat_history(self) -> None:
        if not hasattr(self, "chat_history_text"):
            return
        text = self.chat_history_text
        text.configure(state="normal")
        text.delete("1.0", "end")
        for message in self.chat_history:
            header_tag = {
                "user": "user_header",
                "assistant": "assistant_header",
                "system": "system_header",
            }.get(message.role, "assistant_header")
            label = {
                "user": "You",
                "assistant": "Assistant",
                "system": "System",
            }.get(message.role, message.role.title())
            text.insert("end", f"[{label}] ", header_tag)
            text.insert("end", f"{message.content}\n\n", "body")
        text.configure(state="disabled")
        text.see("end")

    def _append_chat_message_view(self, role: str, content: str) -> None:
        self.chat_history.append(ChatMessage(role=role, content=content))
        self._render_chat_history()

    def _replace_last_chat_message(self, role: str, content: str) -> None:
        if self.chat_history and self.chat_history[-1].role == role:
            self.chat_history[-1] = ChatMessage(role=role, content=content)
        else:
            self.chat_history.append(ChatMessage(role=role, content=content))
        self._render_chat_history()

    def _update_chat_endpoint_preview(self) -> None:
        settings = self.collect_settings(strict=False)
        self.chat_endpoint_var.set(f"{settings['Host']}:{settings['Port']}")

    def _write_chat_template_file(self) -> Path | None:
        template = self._current_chat_template().strip()
        if not template:
            return None
        model_key = self._chat_storage_key()
        out_dir = SESSION_DIR / "chat-templates"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{model_key}.jinja"
        path.write_text(template, encoding="utf-8")
        return path

    def _augment_server_args_with_chat(self, server_args: OrderedDict[str, Any]) -> OrderedDict[str, Any]:
        args = OrderedDict(server_args)
        template_path = self._write_chat_template_file()
        if template_path:
            args["chat-template-file"] = str(template_path)
        return args

    def _on_chat_settings_changed(self, _event: tk.Event | None = None) -> None:
        if self._loading:
            return
        self._store_chat_model_state()

    def reset_chat_overrides(self) -> None:
        if not self.selected_model:
            return
        self._set_text_widget_value(self.chat_system_prompt, self.selected_model.sys_prompt)
        self._set_text_widget_value(self.chat_template_text, self.selected_model.chat_template)
        self._store_chat_model_state()

    def clear_chat_history(self) -> None:
        if self.chat_request_in_flight:
            return
        self.chat_history = []
        self._render_chat_history()
        self._store_chat_model_state()

    def _chat_input_return(self, _event: tk.Event) -> str:
        self.send_chat_message()
        return "break"

    def _chat_input_shift_return(self, event: tk.Event) -> str:
        event.widget.insert("insert", "\n")
        return "break"

    def send_chat_message(self) -> None:
        if self.chat_request_in_flight:
            return
        if not self.selected_model:
            messagebox.showwarning("Chat", "Select a model first.", parent=self)
            return
        prompt = self._text_widget_value(self.chat_input)
        if not prompt.strip():
            return
        settings = self.collect_settings(strict=False)
        host = str(settings["Host"])
        port = int(settings["Port"])
        self.chat_request_in_flight = True
        self.chat_status_var.set("Streaming...")
        self.metric_vars["prompt_progress"].set("--")
        self.metric_vars["prompt_processed"].set("--")
        self.chat_send_button.configure(state="disabled")
        self._append_chat_message_view("user", prompt.strip())
        self._set_text_widget_value(self.chat_input, "")
        self._append_chat_message_view("assistant", "")
        self._store_chat_model_state()
        threading.Thread(
            target=self._chat_stream_worker,
            args=(host, port, prompt.strip(), float(settings["Temp"])),
            daemon=True,
        ).start()

    def _chat_stream_worker(self, host: str, port: int, prompt: str, temperature: float) -> None:
        model_id = get_model_id(host, port) or (self.selected_model.alias if self.selected_model else "model")
        messages = [message for message in self.chat_history[:-1] if message.content.strip()]
        system_prompt = self._current_system_prompt().strip()
        if system_prompt:
            messages = [ChatMessage(role="system", content=system_prompt), *messages]
        assistant_parts: list[str] = []
        try:
            self.after(0, lambda: self.chat_model_id_var.set(model_id))
            for event in stream_chat_events(
                host,
                port,
                messages,
                model=model_id,
                extra={"temperature": temperature, "return_progress": True},
            ):
                prompt_progress = event.get("prompt_progress") if isinstance(event, dict) else None
                if isinstance(prompt_progress, dict):
                    processed = int(prompt_progress.get("processed") or 0)
                    total = int(prompt_progress.get("total") or 0)
                    if total > 0:
                        self.after(0, lambda p=processed, t=total: self.metric_vars["prompt_progress"].set(f"{(p / t) * 100:.0f}%"))
                    self.after(0, lambda p=processed: self.metric_vars["prompt_processed"].set(f"{p:,}"))

                choices = event.get("choices") if isinstance(event, dict) else None
                if not isinstance(choices, list):
                    continue
                for choice in choices:
                    if not isinstance(choice, dict):
                        continue
                    delta = choice.get("delta") or {}
                    if not isinstance(delta, dict):
                        continue
                    content_chunk = delta.get("content")
                    if isinstance(content_chunk, str) and content_chunk:
                        assistant_parts.append(content_chunk)
                        content = "".join(assistant_parts)
                        self.after(0, lambda text=content: self._replace_last_chat_message("assistant", text))
        except ChatAPIError as exc:
            message = str(exc)
            self.after(0, lambda: self._replace_last_chat_message("assistant", f"[ERROR] {message}"))
            self.after(0, lambda: self.chat_status_var.set("Error"))
        else:
            self.after(0, lambda: self.chat_status_var.set("Idle"))
        finally:
            self.after(0, self._finish_chat_request)

    def _finish_chat_request(self) -> None:
        self.chat_request_in_flight = False
        self.chat_send_button.configure(state="normal")
        if self.chat_status_var.get() == "Streaming...":
            self.chat_status_var.set("Idle")
        self._store_chat_model_state()

    def go_to_download_tab(self) -> None:
        self.notebook.select(self.models_tab)
        self.models_notebook.select(self.models_download_tab)

    def focus_models_tab(self) -> None:
        self.notebook.select(self.models_tab)
        self.models_notebook.select(self.models_library_tab)

    def _initialize_data(self) -> None:
        self._loading = True
        self._load_chat_state()
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
        self._update_chat_endpoint_preview()
        self._update_command_preview()
        self._update_warning_notes()
        self.log(f"{APP_TITLE} initialized")
        self.log(f"Launcher dir: {APP_DIR}")
        self.log("Ready. Pick a model, choose a preset, tune runtime, then click START.")
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
        if self.selected_model:
            self._store_chat_model_state()
        self.selected_model = None
        self.metric_vars["model"].set("No model selected")
        self.metric_vars["model_size"].set("--")
        if self.launch_model_var is not None:
            self.launch_model_var.set("")
        self.update_model_details(None)
        self._update_model_context(None)
        self._load_chat_for_selected_model()
        if hasattr(self, "models_library_list"):
            self.models_library_list.selection_clear(0, "end")
        self.update_vram_estimate()
        self._update_command_preview()
        self._update_warning_notes()
        if persist:
            self.save_session_debounced()

    def set_selected_model(self, model: ModelEntry, *, persist: bool = True) -> None:
        if self.selected_model and self.selected_model.path != model.path:
            self._store_chat_model_state()
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
        self._load_chat_for_selected_model()
        self.update_vram_estimate()
        self._update_command_preview()
        self._update_warning_notes()
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
        self._update_command_preview()
        self._update_warning_notes()
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
        self._update_chat_endpoint_preview()
        self._update_command_preview()
        self._update_warning_notes()
        self.save_session_debounced()

    def _gpu_layers_changed(self, value: str) -> None:
        try:
            layers = int(float(value))
        except ValueError:
            layers = 0
        self.gpu_layers_label.configure(text=str(layers))
        if not self._loading:
            self.update_vram_estimate()

    def _model_transformer_layers(self, model: ModelEntry | None = None) -> int:
        model = model or self.selected_model
        if model and model.transformer_layers:
            return max(1, int(model.transformer_layers))
        return 40

    def _model_full_offload_layers(self, model: ModelEntry | None = None) -> int | None:
        model = model or self.selected_model
        if model and model.full_offload_layers:
            return max(0, int(model.full_offload_layers))
        return None

    def _update_gpu_offload_controls(self, model: ModelEntry | None = None) -> None:
        model = model or self.selected_model
        full_count = self._model_full_offload_layers(model)
        current = int(float(self.vars["GpuLayers"].get() or 0))
        if self.gpu_layers_scale is not None:
            max_layers = max(full_count or 40, current, 40)
            self.gpu_layers_scale.configure(to=max_layers)
        if self.full_offload_button is not None:
            if full_count is not None:
                self.full_offload_button.configure(state="normal", text=f"Full offload ({full_count})")
            else:
                self.full_offload_button.configure(state="disabled", text="Full offload")
        if full_count is not None:
            self.gpu_offload_help_var.set(
                f"Layer count passed to llama.cpp. Full offload for this model is {full_count}."
            )
        else:
            self.gpu_offload_help_var.set(
                "Layer count passed to llama.cpp. Full offload includes output layers when model metadata provides it."
            )

    def set_full_offload_layers(self) -> None:
        full_count = self._model_full_offload_layers()
        if full_count is None:
            return
        self.vars["GpuLayers"].set(float(full_count))
        self._gpu_layers_changed(str(full_count))
        self.on_setting_changed()

    def update_vram_estimate(self) -> None:
        settings = self.collect_settings(strict=False)
        if not self.selected_model:
            self.metric_vars["vram"].set("--")
            self.metric_vars["vram_detail"].set("Select a model to estimate VRAM.")
            self.vram_bar.configure(maximum=1.0, value=0)
            if self.model_context_vars:
                self._update_model_context(None)
            if hasattr(self, "warning_text"):
                self._update_warning_notes()
            return

        model_path = self.selected_model.path
        self.total_layers = self._model_transformer_layers(self.selected_model)
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
        if hasattr(self, "warning_text"):
            self._update_warning_notes()

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
        self._update_gpu_offload_controls(model)
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
                "Pick a model in Models → Library to see file details, quant hints, and the live command preview."
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
        offload_note = ""
        if model.full_offload_layers is not None:
            offload_note = f" Full offload count: {model.full_offload_layers}."
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
            f"{size_note}.{offload_note} Suggested contexts: {suggested_ctx}. Current launch estimate: {vram_preview['TotalVRAMGB']:.2f} GB total, {vram_preview['RemainingGB']:+.2f} GB headroom."
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
        return LauncherService.can_bind_port(host, port)

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
            self._store_chat_model_state()
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
        self._update_warning_notes()
        self._update_command_preview()

    def export_command(self) -> None:
        cmd = self._format_launch_command()
        self.clipboard_clear()
        self.clipboard_append(cmd)
        self.log("Command copied to clipboard.")
        if self.selected_model:
            try:
                request = LaunchRequest(
                    executable_path=self.core.resolve_runtime_executable()
                    or Path("llama-server.exe"),
                    model_path=self.selected_model.path,
                    settings=self.collect_settings(strict=True),
                )
                args = build_command_args(self.selected_model.path, self.collect_settings(strict=True))
                args = self._augment_server_args_with_chat(args)
                redacted = self.launcher_service.build_launch_command(request, args).redacted_command_text
                self.log(redacted)
                return
            except Exception:
                pass
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
            server_args = self._augment_server_args_with_chat(server_args)
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
        request = LaunchRequest(
            executable_path=exe,
            model_path=self.selected_model.path,
            settings=settings,
            cwd=exe.parent,
        )
        command = self.launcher_service.build_launch_command(request, server_args)
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
        self.log(f"Command: {command.redacted_command_text}")
        self.log("")

        try:
            result = self.launcher_service.start_process(request, server_args)
            self.running_process = result.running_process
            self.process = result.running_process.process
        except Exception as exc:
            self.running_process = None
            self.process = None
            self.set_status("Failed", "red")
            self.log(f"[ERROR] Failed to start llama-server: {exc}")
            return

        self.server_start_time = result.started_at
        self.running_host = settings["Host"]
        self.running_port = settings["Port"]
        self.set_status("Running", "green")
        self.log(f"[INFO] llama-server process started. PID: {self.process.pid}")
        threading.Thread(target=self._read_process_output, daemon=True).start()
        self.after(500, self.check_process)
        self.after(2000, self.poll_metrics)
        self.after(1000, self.poll_resources)
        self.save_current_session()
        self._update_warning_notes()

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
        if self.running_process is not None:
            self.launcher_service.stop_process(self.running_process)
        else:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                    proc.wait(timeout=3)
                except Exception:
                    pass
        self.running_process = None
        self.process = None
        self.server_start_time = None
        self.running_host = None
        self.running_port = None
        self.set_status("Stopped", "muted")
        self.metric_vars["uptime"].set("--")
        for key in [
            "context",
            "kv_cache",
            "requests",
            "requests_active",
            "requests_queued",
            "session_slot",
            "session_progress",
            "prompt_progress",
            "prompt_processed",
            "session_decoded",
            "session_remaining",
        ]:
            self.metric_vars[key].set("--")
        self.log("Server stopped.")
        self._update_warning_notes()

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
        for key in [
            "context",
            "kv_cache",
            "requests",
            "requests_active",
            "requests_queued",
            "session_slot",
            "session_progress",
            "prompt_progress",
            "prompt_processed",
            "session_decoded",
            "session_remaining",
        ]:
            self.metric_vars[key].set("--")

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
            snapshot = self.monitoring_service.collect_monitoring_snapshot(host, int(port))
            if snapshot.ui_metrics:
                self.update_metrics(snapshot.ui_metrics)
            self.update_slot_metrics(
                snapshot.slot_state.to_ui_metrics() if snapshot.slot_state else {}
            )
        except Exception:
            pass
        self.after(2000, self.poll_metrics)

    def poll_resources(self) -> None:
        if not self.process or self.process.poll() is not None:
            return
        resource_usage = self.monitoring_service.fetch_local_resource_usage()
        if resource_usage:
            resource_metrics = resource_usage.to_ui_metrics()
            if "cpu" in resource_metrics:
                self.metric_vars["cpu"].set(resource_metrics["cpu"])
            if "ram" in resource_metrics:
                self.metric_vars["ram"].set(resource_metrics["ram"])
            if "gpu" in resource_metrics:
                self.metric_vars["gpu"].set(resource_metrics["gpu"])
            if "gpu_vram" in resource_metrics:
                self.metric_vars["gpu_vram"].set(resource_metrics["gpu_vram"])
            if resource_usage.gpu_total_vram_gb:
                self.available_vram = float(resource_usage.gpu_total_vram_gb)
                self.update_vram_estimate()
        self.after(3000, self.poll_resources)

    def update_metrics(self, metrics: dict[str, Any]) -> None:
        if "tps" in metrics:
            self.metric_vars["tps"].set(f"{metrics['tps']:.1f} tok/s")
        if "peps" in metrics:
            self.metric_vars["peps"].set(f"{metrics['peps']:.1f} tok/s")
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
        ctx_capacity = metrics.get("slot_ctx") or self.collect_settings(strict=False).get(
            "CtxSize", 0
        )
        if "kv_cache_tokens" in metrics:
            self.metric_vars["context"].set(
                f"{int(metrics['kv_cache_tokens']):,} / {int(ctx_capacity):,} tokens"
            )
        elif "ctx_size" in metrics:
            self.metric_vars["context"].set(
                f"{int(metrics['ctx_size']):,} / {int(ctx_capacity):,} peak"
            )
        if "kv_usage" in metrics:
            self.metric_vars["kv_cache"].set(f"{metrics['kv_usage'] * 100:.0f}%")
        if "total_decode_tokens" in metrics:
            self.metric_vars["tokens"].set(f"{metrics['total_decode_tokens']:,}")
        if "total_prompt_tokens" in metrics:
            self.metric_vars["prompt_tokens"].set(f"{metrics['total_prompt_tokens']:,}")
        if "requests" in metrics:
            self.metric_vars["requests"].set(str(metrics["requests"]))
        if "requests_processing" in metrics:
            self.metric_vars["requests_active"].set(str(metrics["requests_processing"]))
        if "requests_deferred" in metrics:
            self.metric_vars["requests_queued"].set(str(metrics["requests_deferred"]))
        if "total_prompt_tokens" in metrics and self.metric_vars["prompt_processed"].get() == "--":
            self.metric_vars["prompt_processed"].set(f"{metrics['total_prompt_tokens']:,}")

    def update_slot_metrics(self, slot_metrics: dict[str, Any]) -> None:
        if not slot_metrics:
            self.metric_vars["session_slot"].set("--")
            self.metric_vars["session_progress"].set("--")
            self.metric_vars["session_decoded"].set("--")
            self.metric_vars["session_remaining"].set("--")
            return
        slot_id = slot_metrics.get("slot_id")
        task_id = slot_metrics.get("task_id")
        processing = slot_metrics.get("slot_processing")
        if slot_id is not None:
            label = f"slot {slot_id}"
            if task_id is not None:
                label += f" · task {task_id}"
            if processing:
                label += " · active"
            self.metric_vars["session_slot"].set(label)
        if slot_metrics.get("slot_ctx"):
            current = self.metric_vars["context"].get()
            if "/" not in current or current.endswith("peak"):
                self.metric_vars["context"].set(f"-- / {int(slot_metrics['slot_ctx']):,} tokens")
        if "session_progress" in slot_metrics:
            self.metric_vars["session_progress"].set(
                f"{slot_metrics['session_progress'] * 100:.0f}%"
            )
        elif slot_metrics.get("slot_processing"):
            self.metric_vars["session_progress"].set("running")
        else:
            self.metric_vars["session_progress"].set("--")
        if "session_decoded" in slot_metrics:
            self.metric_vars["session_decoded"].set(
                f"{int(slot_metrics['session_decoded']):,}"
            )
        if "session_remaining" in slot_metrics:
            self.metric_vars["session_remaining"].set(
                f"{int(slot_metrics['session_remaining']):,}"
            )

    def set_status(self, text: str, color_key: str) -> None:
        self.metric_vars["status"].set(text)
        color = self.COLORS.get(color_key, self.COLORS["muted"])
        self.status_dot.configure(foreground=color)
        if hasattr(self, "status_value_label"):
            self.status_value_label.configure(foreground=color)

    def _format_launch_command(self) -> str:
        if not self.selected_model:
            return "Select a model to generate the launch command."
        exe = self.core.resolve_runtime_executable() or Path("llama-server.exe")
        try:
            args = build_command_args(self.selected_model.path, self.collect_settings(strict=True))
            args = self._augment_server_args_with_chat(args)
        except Exception:
            try:
                args = build_command_args(self.selected_model.path, self.collect_settings(strict=False))
                args = self._augment_server_args_with_chat(args)
            except Exception as exc:
                return f"Command preview unavailable: {exc}"
        return command_string(exe, args)

    def _update_command_preview(self) -> None:
        if not self.command_preview_text:
            return
        command = self._format_launch_command()
        self.command_preview_text.configure(state="normal")
        self.command_preview_text.delete("1.0", "end")
        self.command_preview_text.insert("1.0", command)
        self.command_preview_text.configure(state="disabled")

    def _update_warning_notes(self) -> None:
        if not self.warning_text:
            return
        notes: list[str] = []
        if not self.selected_model:
            notes.append("No model selected yet. Pick one to unlock launching and live endpoint monitoring.")
        if not self.core.resolve_runtime_executable():
            notes.append("llama-server.exe is not configured. Use Runtime to set the executable path.")
        if self.selected_model and self.metric_vars["vram"].get() not in {"--", "", None}:
            try:
                total = float(self.metric_vars["vram"].get().split()[0])
                if total > self.available_vram:
                    notes.append(f"Estimated VRAM exceeds detected capacity by {total - self.available_vram:.2f} GB.")
            except Exception:
                pass
        if self.selected_model:
            full_count = self._model_full_offload_layers(self.selected_model)
            try:
                current_layers = int(float(self.vars["GpuLayers"].get() or 0))
            except Exception:
                current_layers = 0
            if full_count is not None:
                if current_layers < full_count:
                    notes.append(
                        f"Partial GPU offload selected ({current_layers}/{full_count}). Some layers or output tensors may remain on CPU."
                    )
                else:
                    notes.append(f"Full GPU offload selected ({full_count}/{full_count}).")
        notes.append("Chat settings are stored per model and remain hidden until you open the Chat tab.")
        notes.append("The generated command updates live as you change model, preset, and runtime settings.")
        self.warning_text.configure(state="normal")
        self.warning_text.delete("1.0", "end")
        self.warning_text.insert("1.0", "\n\n".join(f"• {note}" for note in notes))
        self.warning_text.configure(state="disabled")

    @staticmethod
    def local_poll_host(host: str) -> str:
        return LauncherService.normalize_poll_host(host)

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
            bg=self.COLORS["surface2"],
            fg=self.COLORS["text"],
            selectbackground=self.COLORS["accent"],
            selectforeground="#08111f",
            activestyle="none",
            highlightthickness=1,
            highlightbackground=self.COLORS["line"],
            relief="flat",
            font=self.BODY_FONT,
            exportselection=False,
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
            text="Pick a model here to populate the Overview and command preview.",
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
            bg=self.COLORS["surface2"],
            fg=self.COLORS["text"],
            selectbackground=self.COLORS["accent"],
            selectforeground="#08111f",
            activestyle="none",
            highlightthickness=1,
            highlightbackground=self.COLORS["line"],
            relief="flat",
            borderwidth=0,
            font=self.BODY_FONT,
            exportselection=False,
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
            bg=self.COLORS["surface2"],
            fg=self.COLORS["text"],
            selectbackground=self.COLORS["accent"],
            selectforeground="#08111f",
            activestyle="none",
            highlightthickness=1,
            highlightbackground=self.COLORS["line"],
            relief="flat",
            borderwidth=0,
            font=self.BODY_FONT,
            exportselection=False,
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
