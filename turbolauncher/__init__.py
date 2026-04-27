"""TurboLauncher package."""

from .core import LauncherCore

__all__ = ["LauncherCore", "TurboLauncherApp"]


def __getattr__(name: str):
    if name == "TurboLauncherApp":
        from .app import TurboLauncherApp

        return TurboLauncherApp
    raise AttributeError(name)
