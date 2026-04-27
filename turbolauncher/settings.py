from __future__ import annotations

import re
from typing import Any

NUMERIC_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")
INT_RE = re.compile(r"^[+-]?\d+$")

BUILT_IN_PRESETS = [
    {
        "Name": "Agentic AI",
        "Description": "Thinking ON + preserve, optimized for tool calling and MCP agents",
        "File": "agentic-ai.json",
    },
    {
        "Name": "Coding Precise",
        "Description": "Thinking ON + preserve, lower temp for precise code generation",
        "File": "coding-precise.json",
    },
    {
        "Name": "Fast Chat",
        "Description": "Thinking OFF, faster responses for general conversation",
        "File": "fast-chat.json",
    },
    {
        "Name": "Deep Reasoning",
        "Description": "Thinking ON + preserve, 131K context for complex planning",
        "File": "deep-reasoning.json",
    },
    {
        "Name": "Max Context",
        "Description": "Thinking ON + preserve, full 262K context window",
        "File": "max-context.json",
    },
]

DEFAULT_SETTINGS: dict[str, Any] = {
    "GpuLayers": 30,
    "NcpuMoe": 28,
    "CtxSize": 65536,
    "Threads": 16,
    "BatchSize": 512,
    "UBatchSize": 512,
    "Temp": 1.0,
    "TopP": 0.95,
    "TopK": 20,
    "MinP": 0.0,
    "TypicalP": 1.0,
    "RepeatPenalty": 1.0,
    "RepeatLastN": 64,
    "PresencePenalty": 1.5,
    "FreqPenalty": 0.0,
    "CacheTypeK": "turbo3",
    "CacheTypeV": "turbo3",
    "FlashAttn": True,
    "SplitMode": "auto",
    "TensorSplit": 0,
    "Mlock": False,
    "NoMmap": False,
    "Host": "127.0.0.1",
    "Port": 1234,
    "Parallel": 1,
    "ApiKey": "",
    "Alias": "",
    "Thinking": True,
    "PreserveThinking": True,
    "ReasoningFormat": "auto",
    "ReasoningBudget": "",
    "Jinja": True,
    "Webui": True,
    "Metrics": True,
    "ContBatching": True,
    "DryMultiplier": 0.0,
    "DryBase": 1.0,
    "DryAllowed": 2,
    "XtcProb": 0.0,
    "XtcThresh": 0.5,
    "Seed": -1,
}

SETTING_TYPES: dict[str, type] = {
    "GpuLayers": int,
    "NcpuMoe": int,
    "CtxSize": int,
    "Threads": int,
    "BatchSize": int,
    "UBatchSize": int,
    "Temp": float,
    "TopP": float,
    "TopK": int,
    "MinP": float,
    "TypicalP": float,
    "RepeatPenalty": float,
    "RepeatLastN": int,
    "PresencePenalty": float,
    "FreqPenalty": float,
    "CacheTypeK": str,
    "CacheTypeV": str,
    "FlashAttn": bool,
    "SplitMode": str,
    "TensorSplit": float,
    "Mlock": bool,
    "NoMmap": bool,
    "Host": str,
    "Port": int,
    "Parallel": int,
    "ApiKey": str,
    "Alias": str,
    "Thinking": bool,
    "PreserveThinking": bool,
    "ReasoningFormat": str,
    "ReasoningBudget": str,
    "Jinja": bool,
    "Webui": bool,
    "Metrics": bool,
    "ContBatching": bool,
    "DryMultiplier": float,
    "DryBase": float,
    "DryAllowed": int,
    "XtcProb": float,
    "XtcThresh": float,
    "Seed": int,
}
CACHE_TYPES = ["f16", "q8_0", "q4_0", "turbo4", "turbo3"]
SPLIT_MODES = ["auto", "none", "layer", "row"]
REASONING_FORMATS = ["auto", "none", "force"]
RECOMMENDED_MODELS = [
    {
        "Id": "lmstudio-community/Qwen2.5-1.5B-Instruct-GGUF",
        "Name": "Qwen2.5-1.5B-Instruct",
        "Size": "~1GB (Q4_K_M)",
        "BestFor": "Testing, quick prototyping",
        "PreferredQuant": "Q4_K_M",
    },
    {
        "Id": "lmstudio-community/Qwen2.5-3B-Instruct-GGUF",
        "Name": "Qwen2.5-3B-Instruct",
        "Size": "~2GB (Q4_K_M)",
        "BestFor": "General chat, fast responses",
        "PreferredQuant": "Q4_K_M",
    },
    {
        "Id": "lmstudio-community/Qwen2.5-7B-Instruct-GGUF",
        "Name": "Qwen2.5-7B-Instruct",
        "Size": "~4.8GB (Q4_K_M)",
        "BestFor": "Balanced performance",
        "PreferredQuant": "Q4_K_M",
    },
    {
        "Id": "lmstudio-community/Phi-3.5-mini-instruct-GGUF",
        "Name": "Phi-3.5-mini-4K",
        "Size": "~2.2GB (Q4_K_M)",
        "BestFor": "Efficient reasoning, coding",
        "PreferredQuant": "Q4_K_M",
    },
    {
        "Id": "lmstudio-community/gemma-3-1b-it-GGUF",
        "Name": "Gemma-3-1B-IT",
        "Size": "~0.7GB (Q4_K_M)",
        "BestFor": "Ultra-fast inference, testing",
        "PreferredQuant": "Q4_K_M",
    },
    {
        "Id": "lmstudio-community/Meta-Llama-3.2-3B-Instruct-GGUF",
        "Name": "Llama-3.2-3B-Instruct",
        "Size": "~2GB (Q4_K_M)",
        "BestFor": "General purpose, coding",
        "PreferredQuant": "Q4_K_M",
    },
]


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def coerce_setting(key: str, value: Any, *, strict: bool = False) -> Any:
    target = SETTING_TYPES.get(key, str)
    default = DEFAULT_SETTINGS.get(key, "")
    try:
        if target is bool:
            return as_bool(value)
        if target is int:
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, int):
                return value
            if isinstance(value, float):
                if strict and not value.is_integer():
                    raise ValueError
                return int(value)
            raw = str(value).strip()
            if strict:
                if not INT_RE.fullmatch(raw):
                    raise ValueError
                return int(raw)
            text = re.sub(r"[^0-9.+-]", "", raw)
            if text in {"", "+", "-", "."} or not NUMERIC_RE.fullmatch(text):
                raise ValueError
            return int(float(text))
        if target is float:
            if isinstance(value, bool):
                return float(value)
            raw = str(value).strip()
            text = raw if strict else re.sub(r"[^0-9.+-]", "", raw)
            if text in {"", "+", "-", "."} or not NUMERIC_RE.fullmatch(text):
                raise ValueError
            return float(text)
        return str(value).strip()
    except Exception as exc:
        if strict:
            raise ValueError(f"{key} must be a {target.__name__}") from exc
        return default


def normalize_settings(
    settings: dict[str, Any] | None, *, strict: bool = False
) -> dict[str, Any]:
    merged = dict(DEFAULT_SETTINGS)
    if settings:
        merged.update(settings)
    return {
        key: coerce_setting(key, merged.get(key), strict=strict)
        for key in DEFAULT_SETTINGS
    }


def validate_launch_settings(settings: dict[str, Any]) -> None:
    ranges = {
        "GpuLayers": (0, 999),
        "NcpuMoe": (0, 999),
        "CtxSize": (1, 1_048_576),
        "Threads": (1, 512),
        "BatchSize": (1, 1_048_576),
        "UBatchSize": (1, 1_048_576),
        "Temp": (0, 5),
        "TopP": (0, 1),
        "TopK": (0, 100_000),
        "MinP": (0, 1),
        "TypicalP": (0, 1),
        "RepeatPenalty": (0, 10),
        "RepeatLastN": (-1, 1_048_576),
        "PresencePenalty": (-10, 10),
        "FreqPenalty": (-10, 10),
        "TensorSplit": (0, 10_000),
        "Port": (1, 65_535),
        "Parallel": (1, 256),
        "DryMultiplier": (0, 10),
        "DryBase": (0, 10),
        "DryAllowed": (0, 10_000),
        "XtcProb": (0, 1),
        "XtcThresh": (0, 1),
        "Seed": (-1, 2_147_483_647),
    }
    for key, (low, high) in ranges.items():
        value = settings[key]
        if value < low or value > high:
            raise ValueError(f"{key} must be between {low:g} and {high:g}")
    if not settings["Host"]:
        raise ValueError("Host must not be empty")
    if settings["CacheTypeK"] not in CACHE_TYPES:
        raise ValueError(f"CacheTypeK must be one of: {', '.join(CACHE_TYPES)}")
    if settings["CacheTypeV"] not in CACHE_TYPES:
        raise ValueError(f"CacheTypeV must be one of: {', '.join(CACHE_TYPES)}")
    if settings["SplitMode"] not in SPLIT_MODES:
        raise ValueError(f"SplitMode must be one of: {', '.join(SPLIT_MODES)}")
    if settings["ReasoningFormat"] not in REASONING_FORMATS:
        raise ValueError(
            f"ReasoningFormat must be one of: {', '.join(REASONING_FORMATS)}"
        )
