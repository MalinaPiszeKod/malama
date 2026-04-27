#!/usr/bin/env python3
"""Compatibility entrypoint for the modular TurboLauncher package."""

from __future__ import annotations

from turbolauncher.cli import main, run_headless_tests
from turbolauncher.command_builder import (
    args_to_list,
    build_command_args,
    command_string,
)
from turbolauncher.core import LauncherCore
from turbolauncher.settings import (
    coerce_setting,
    normalize_settings,
    validate_launch_settings,
)

__all__ = [
    "LauncherCore",
    "TurboLauncherApp",
    "args_to_list",
    "build_command_args",
    "coerce_setting",
    "command_string",
    "main",
    "normalize_settings",
    "run_headless_tests",
    "validate_launch_settings",
]


def __getattr__(name: str):
    if name == "TurboLauncherApp":
        from turbolauncher.app import TurboLauncherApp

        return TurboLauncherApp
    raise AttributeError(name)


if __name__ == "__main__":
    raise SystemExit(main())
