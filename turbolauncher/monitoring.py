from __future__ import annotations

import ctypes
import os
import re
import shutil
import subprocess
from typing import Any

from .paths import GB


def parse_prometheus_metrics(content: str) -> dict[str, Any]:
    patterns = {
        "requests": (r"llama_server_request_success_total\s+(\d+)", int),
        "total_prompt_tokens": (r"prompt_eval_n_total\s+(\d+)", int),
        "total_decode_tokens": (r"eval_n_total\s+(\d+)", int),
        "total_prompt_time": (r"prompt_eval_seconds_total\s+([\d.]+)", float),
        "total_decode_time": (r"eval_seconds_total\s+([\d.]+)", float),
        "peps": (r"prompt_eval_tokens_per_second\s+([\d.]+)", float),
        "tps": (r"tokens_per_second\s+([\d.]+)", float),
        "kv_usage": (r"kv_cache_usage_count\s+([\d.]+)", float),
        "ctx_size": (r"n_ctx\s+(\d+)", int),
    }
    metrics: dict[str, Any] = {}
    for key, (pattern, converter) in patterns.items():
        match = re.search(pattern, content)
        if match:
            metrics[key] = converter(match.group(1))
    return metrics


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
