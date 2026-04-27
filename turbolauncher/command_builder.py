from __future__ import annotations

import subprocess
from collections import OrderedDict
from pathlib import Path
from typing import Any

from .settings import normalize_settings, validate_launch_settings


def build_command_args(
    model_path: str | Path, settings: dict[str, Any]
) -> OrderedDict[str, Any]:
    s = normalize_settings(settings, strict=True)
    validate_launch_settings(s)
    args: OrderedDict[str, Any] = OrderedDict()
    args["model"] = str(model_path)
    args["n-gpu-layers"] = s["GpuLayers"]
    if s["NcpuMoe"] > 0:
        args["n-cpu-moe"] = s["NcpuMoe"]
    args["ctx-size"] = s["CtxSize"]
    args["batch-size"] = s["BatchSize"]
    args["ubatch-size"] = s["UBatchSize"]
    args["threads"] = s["Threads"]
    if s["CacheTypeK"]:
        args["cache-type-k"] = s["CacheTypeK"]
    if s["CacheTypeV"]:
        args["cache-type-v"] = s["CacheTypeV"]
    args["flash-attn"] = "on" if s["FlashAttn"] else "off"
    if s["SplitMode"] and s["SplitMode"] != "auto":
        args["split-mode"] = s["SplitMode"]
    if s["TensorSplit"] > 0:
        args["tensor-split"] = s["TensorSplit"]
    if s["Mlock"]:
        args["mlock"] = True
    if s["NoMmap"]:
        args["no-mmap"] = True
    if s["Jinja"]:
        args["jinja"] = True
    if s["Thinking"]:
        if s["ReasoningFormat"] in {"force", "none"}:
            args["reasoning-format"] = s["ReasoningFormat"]
    else:
        args["reasoning-format"] = "none"
    if s["ReasoningBudget"]:
        args["reasoning-budget"] = s["ReasoningBudget"]
    for setting_name, arg_name in [
        ("Temp", "temp"),
        ("TopP", "top-p"),
        ("TopK", "top-k"),
        ("MinP", "min-p"),
        ("RepeatPenalty", "repeat-penalty"),
        ("RepeatLastN", "repeat-last-n"),
        ("PresencePenalty", "presence-penalty"),
        ("FreqPenalty", "frequency-penalty"),
    ]:
        args[arg_name] = s[setting_name]
    if s["TypicalP"] != 1.0:
        args["typical-p"] = s["TypicalP"]
    if s["Seed"] >= 0:
        args["seed"] = s["Seed"]
    if s["DryMultiplier"] > 0:
        args["dry-multiplier"] = s["DryMultiplier"]
        args["dry-base"] = s["DryBase"]
        args["dry-allowed-length"] = s["DryAllowed"]
        args["dry-penalty-last-n"] = -1
    if s["XtcProb"] > 0:
        args["xtc-probability"] = s["XtcProb"]
        args["xtc-threshold"] = s["XtcThresh"]
    args["host"] = s["Host"]
    args["port"] = s["Port"]
    if s["Parallel"] > 1:
        args["parallel"] = s["Parallel"]
    if s["Alias"]:
        args["alias"] = s["Alias"]
    if s["ApiKey"]:
        args["api-key"] = s["ApiKey"]
    if not s["Webui"]:
        args["no-webui"] = True
    if s["Metrics"]:
        args["metrics"] = True
    if s["ContBatching"]:
        args["cont-batching"] = True
    return args


def args_to_list(server_args: OrderedDict[str, Any]) -> list[str]:
    parts: list[str] = []
    for key, value in server_args.items():
        if isinstance(value, bool):
            if value:
                parts.append(f"--{key}")
        elif value is not None and value != "":
            parts.extend([f"--{key}", str(value)])
    return parts


def command_string(exe_path: str | Path, server_args: OrderedDict[str, Any]) -> str:
    return subprocess.list2cmdline([str(exe_path), *args_to_list(server_args)])
