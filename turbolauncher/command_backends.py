from __future__ import annotations

from collections import OrderedDict
from typing import Any, Callable

CommandArgs = OrderedDict[str, Any]
BackendRule = Callable[[CommandArgs, dict[str, Any]], None]


# Add fork-specific command mutations here.
BACKEND_COMMAND_RULES: dict[str, tuple[BackendRule, ...]] = {
    "default": (),
}


def apply_backend_command_rules(
    args: CommandArgs,
    settings: dict[str, Any],
    *,
    backend: str = "default",
) -> None:
    for rule in BACKEND_COMMAND_RULES.get(backend, BACKEND_COMMAND_RULES["default"]):
        rule(args, settings)
