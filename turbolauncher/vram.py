from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import detect_quant, file_size_gb
from .paths import GB


def get_model_size_gb(gguf_path: str | Path | None, quant_type: str) -> float:
    if gguf_path:
        path = Path(gguf_path)
        if path.exists():
            return round(path.stat().st_size / GB, 2)
    return {
        "Q6_K": 33.0,
        "Q8_0": 66.0,
        "Q4_K_M": 21.0,
        "Q4_K_S": 16.0,
        "Q5_K_M": 25.0,
        "UD-Q3_XXS": 13.2,
        "Unknown": 33.0,
    }.get(quant_type, 33.0)


def get_kv_cache_size_gb(
    ctx_size: int,
    gpu_layers: int,
    total_layers: int,
    cache_type_k: str,
    cache_type_v: str,
    hidden_dim: int = 2048,
) -> float:
    del cache_type_v
    attention_layers = 10
    deltanet_layers = 30
    comp_k = {"f16": 1.0, "q8_0": 2.0, "q4_0": 4.0, "turbo4": 3.8, "turbo3": 4.9}.get(
        cache_type_k, 1.0
    )
    delta_net_kv_bytes = 8
    attention_kv_bytes = hidden_dim * 2 * 2
    if total_layers <= 0:
        total_layers = 40
    gpu_layers = max(0, gpu_layers)
    gpu_attention_layers = round(attention_layers * (gpu_layers / total_layers))
    gpu_deltanet_layers = max(
        0, min(deltanet_layers, gpu_layers - gpu_attention_layers)
    )
    kv_bytes = (gpu_attention_layers * attention_kv_bytes / comp_k) * ctx_size + (
        gpu_deltanet_layers * delta_net_kv_bytes / comp_k
    ) * ctx_size
    return round(kv_bytes / GB, 2)


def calculate_total_vram(
    gguf_path: str | Path | None,
    quant_type: str,
    ctx_size: int,
    gpu_layers: int,
    cache_type_k: str,
    cache_type_v: str,
    available_vram: float = 16.0,
    ncpu_moe: int = 0,
    total_layers: int = 40,
) -> dict[str, Any]:
    model_size = get_model_size_gb(gguf_path, quant_type)
    kv_cache_size = get_kv_cache_size_gb(
        ctx_size, gpu_layers, total_layers, cache_type_k, cache_type_v
    )
    layer_ratio = gpu_layers / total_layers if total_layers else 0
    gpu_model_size = model_size * layer_ratio
    if ncpu_moe > 0:
        moe_ratio = ncpu_moe / total_layers if total_layers else 0
        moe_savings = model_size * moe_ratio * 0.6
        gpu_model_size = max(gpu_model_size - moe_savings, model_size * 0.3)
    overhead = 1.5
    total_vram = gpu_model_size + kv_cache_size + overhead
    remaining = available_vram - total_vram
    warning = (
        "ERROR: Exceeds VRAM. Model may swap to system RAM."
        if remaining < 0
        else ("Warning: less than 2 GB headroom." if remaining < 2 else "OK")
    )
    return {
        "ModelSizeGB": model_size,
        "GpuModelSizeGB": round(gpu_model_size, 2),
        "KvCacheSizeGB": kv_cache_size,
        "OverheadGB": overhead,
        "TotalVRAMGB": round(total_vram, 2),
        "RemainingGB": round(remaining, 2),
        "AvailableVRAM": available_vram,
        "IsOverLimit": remaining < 0,
        "Warning": warning,
    }
