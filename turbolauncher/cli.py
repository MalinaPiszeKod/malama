from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from .command_builder import build_command_args, command_string
from .core import LauncherCore
from .paths import LOG_FILE, ensure_dirs
from .settings import DEFAULT_SETTINGS, normalize_settings


def run_headless_tests(runtime_path: str | None = None) -> int:
    core = LauncherCore(runtime_path)
    failures: list[str] = []

    presets = core.list_presets()
    if not any(p["Name"] == "Agentic AI" for p in presets):
        failures.append("Agentic AI preset is missing")

    preset = core.load_preset("Agentic AI")
    if not preset or "Settings" not in preset:
        failures.append("Agentic AI preset could not be loaded")

    settings = normalize_settings(
        (preset or {}).get("Settings") if preset else DEFAULT_SETTINGS,
        strict=True,
    )
    models = core.load_models()
    if not models:
        failures.append("No real GGUF models were discovered")
        model_path = Path(r"C:\models\example.gguf")
    else:
        model_path = models[0].path
    args = build_command_args(model_path, settings)

    required_args = [
        "model",
        "n-gpu-layers",
        "ctx-size",
        "batch-size",
        "ubatch-size",
        "threads",
        "host",
        "port",
    ]
    for arg in required_args:
        if arg not in args:
            failures.append(f"Missing command arg: --{arg}")

    if args.get("reasoning-format") == "none" and settings.get("Thinking"):
        failures.append("Thinking preset unexpectedly disables reasoning")
    if settings["NcpuMoe"] > 0 and "n-cpu-moe" not in args:
        failures.append("CPU MoE layer count flag missing")
    if settings["NcpuMoe"] > 0 and "cpu-moe" in args:
        failures.append("Redundant CPU MoE full-offload flag present")

    cmd = command_string(core.resolve_runtime_executable() or "llama-server.exe", args)
    if "--model" not in cmd:
        failures.append("Command string does not contain --model")

    if failures:
        print("Headless validation FAILED")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("Headless validation PASSED")
    print(f"  presets: {len(presets)}")
    print(f"  models: {len(models)}")
    print(f"  command: {cmd}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TurboLauncher Python GUI")
    parser.add_argument("runtime", nargs="?", help="Optional path to llama-server.exe")
    parser.add_argument(
        "--runtime-path",
        dest="runtime_path",
        help="Path to llama-server.exe",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run validation without opening the GUI",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    runtime_path = args.runtime_path or args.runtime
    if args.headless:
        return run_headless_tests(runtime_path)

    try:
        from .app import TurboLauncherApp

        app = TurboLauncherApp(runtime_path)
        app.mainloop()
        return 0
    except Exception:
        ensure_dirs()
        details = traceback.format_exc()
        try:
            LOG_FILE.write_text(details, encoding="utf-8")
        except OSError:
            pass
        try:
            from tkinter import messagebox

            messagebox.showerror("TurboLauncher failed", details)
        except Exception:
            print(details, file=sys.stderr)
        return 1
