from __future__ import annotations

import ctypes
import json
import os
import re
import shutil
import subprocess
from typing import Any

from .paths import GB


def parse_prometheus_metrics(content: str) -> dict[str, Any]:
    metrics: dict[str, Any] = {}

    def first_match(patterns: list[str], converter: Any) -> Any:
        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                return converter(match.group(1))
        return None

    aliases: dict[str, tuple[list[str], Any]] = {
        "total_prompt_tokens": (
            [
                r"llamacpp:prompt_tokens_total\s+(\d+)",
                r"prompt_eval_n_total\s+(\d+)",
            ],
            int,
        ),
        "total_decode_tokens": (
            [
                r"llamacpp:tokens_predicted_total\s+(\d+)",
                r"eval_n_total\s+(\d+)",
            ],
            int,
        ),
        "total_prompt_time": (
            [
                r"llamacpp:prompt_seconds_total\s+([\d.]+)",
                r"prompt_eval_seconds_total\s+([\d.]+)",
            ],
            float,
        ),
        "total_decode_time": (
            [
                r"llamacpp:tokens_predicted_seconds_total\s+([\d.]+)",
                r"eval_seconds_total\s+([\d.]+)",
            ],
            float,
        ),
        "peps": (
            [
                r"llamacpp:prompt_tokens_seconds\s+([\d.]+)",
                r"prompt_eval_tokens_per_second\s+([\d.]+)",
            ],
            float,
        ),
        "tps": (
            [
                r"llamacpp:predicted_tokens_seconds\s+([\d.]+)",
                r"tokens_per_second\s+([\d.]+)",
            ],
            float,
        ),
        "kv_usage": (
            [
                r"llamacpp:kv_cache_usage_ratio\s+([\d.]+)",
                r"kv_cache_usage_count\s+([\d.]+)",
            ],
            float,
        ),
        "kv_cache_tokens": (
            [r"llamacpp:kv_cache_tokens\s+(\d+)"],
            int,
        ),
        "ctx_size": (
            [
                r"llamacpp:n_tokens_max\s+(\d+)",
                r"n_ctx\s+(\d+)",
            ],
            int,
        ),
    }

    for key, (patterns, converter) in aliases.items():
        value = first_match(patterns, converter)
        if value is not None:
            metrics[key] = value

    requests_processing = first_match([r"llamacpp:requests_processing\s+(\d+)"], int)
    requests_deferred = first_match([r"llamacpp:requests_deferred\s+(\d+)"], int)
    requests_success_total = first_match([r"llama_server_request_success_total\s+(\d+)"], int)
    if requests_processing is not None or requests_deferred is not None:
        metrics["requests"] = int(requests_processing or 0) + int(requests_deferred or 0)
        metrics["requests_processing"] = int(requests_processing or 0)
        metrics["requests_deferred"] = int(requests_deferred or 0)
    elif requests_success_total is not None:
        metrics["requests"] = requests_success_total

    return metrics


def parse_slots_status(payload: str) -> dict[str, Any]:
    try:
        data = json.loads(payload)
    except Exception:
        return {}
    if isinstance(data, dict):
        for key in ("slots", "data", "items"):
            value = data.get(key)
            if isinstance(value, list):
                data = value
                break
        else:
            return {}
    if not isinstance(data, list):
        return {}

    active_slot: dict[str, Any] | None = None
    for item in data:
        if isinstance(item, dict) and item.get("is_processing"):
            active_slot = item
            break
    if active_slot is None:
        for item in data:
            if isinstance(item, dict):
                active_slot = item
                break
    if active_slot is None:
        return {}

    next_token = active_slot.get("next_token")
    if not isinstance(next_token, dict):
        next_token = {}

    decoded = int(next_token.get("n_decoded") or 0)
    remain = int(next_token.get("n_remain") or 0)
    remain_non_negative = remain if remain >= 0 else 0
    total = decoded + remain_non_negative if decoded + remain_non_negative > 0 else 0
    progress = (decoded / total) if total else None

    result: dict[str, Any] = {
        "slot_id": active_slot.get("id"),
        "task_id": active_slot.get("id_task"),
        "slot_ctx": active_slot.get("n_ctx"),
        "slot_processing": bool(active_slot.get("is_processing")),
        "session_decoded": decoded,
        "session_remaining": remain,
        "session_has_next_token": bool(next_token.get("has_next_token")),
    }
    if progress is not None:
        result["session_progress"] = progress
    return result


def get_ram_usage() -> dict[str, float] | None:
    if os.name != "nt":
        return None

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    total = status.ullTotalPhys / GB
    free = status.ullAvailPhys / GB
    used = total - free
    return {
        "TotalGB": round(total, 1),
        "UsedGB": round(used, 1),
        "FreeGB": round(free, 1),
        "Percent": round(status.dwMemoryLoad, 1),
    }


def get_cpu_usage() -> float | None:
    if os.name != "nt" or not shutil.which("wmic"):
        return None
    flags = (
        subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    )
    try:
        output = subprocess.check_output(
            ["wmic", "cpu", "get", "loadpercentage", "/value"],
            text=True,
            timeout=2,
            creationflags=flags,
            stderr=subprocess.DEVNULL,
        )
        values = [int(m.group(1)) for m in re.finditer(r"LoadPercentage=(\d+)", output)]
        if values:
            return round(sum(values) / len(values), 1)
    except Exception:
        return None
    return None


def get_gpu_info() -> dict[str, Any] | None:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return None
    flags = (
        subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    )
    try:
        output = subprocess.check_output(
            [
                smi,
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=3,
            creationflags=flags,
            stderr=subprocess.DEVNULL,
        ).strip()
        if not output:
            return None
        utils: list[float] = []
        used_total = 0.0
        total_total = 0.0
        for line in output.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                utils.append(float(parts[0]))
                used_total += float(parts[1]) / 1024
                total_total += float(parts[2]) / 1024
        if not utils:
            return None
        return {
            "Utilization": round(sum(utils) / len(utils), 1),
            "UsedVramGB": round(used_total, 1),
            "TotalVramGB": round(total_total, 1),
            "Driver": "NVIDIA",
        }
    except Exception:
        return None
