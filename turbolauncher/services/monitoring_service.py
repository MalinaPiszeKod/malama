from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import urllib.request

from ..monitoring import (
    get_cpu_usage,
    get_gpu_info,
    get_ram_usage,
    parse_prometheus_metrics,
    parse_slots_status,
)


@dataclass(frozen=True)
class ServerMetricsSnapshot:
    total_prompt_tokens: int | None = None
    total_decode_tokens: int | None = None
    total_prompt_time: float | None = None
    total_decode_time: float | None = None
    peps: float | None = None
    tps: float | None = None
    kv_usage: float | None = None
    kv_cache_tokens: int | None = None
    ctx_size: int | None = None
    requests: int | None = None
    requests_processing: int | None = None
    requests_deferred: int | None = None

    @classmethod
    def from_payload(cls, payload: str) -> ServerMetricsSnapshot:
        metrics = parse_prometheus_metrics(payload)
        return cls(
            total_prompt_tokens=metrics.get("total_prompt_tokens"),
            total_decode_tokens=metrics.get("total_decode_tokens"),
            total_prompt_time=metrics.get("total_prompt_time"),
            total_decode_time=metrics.get("total_decode_time"),
            peps=metrics.get("peps"),
            tps=metrics.get("tps"),
            kv_usage=metrics.get("kv_usage"),
            kv_cache_tokens=metrics.get("kv_cache_tokens"),
            ctx_size=metrics.get("ctx_size"),
            requests=metrics.get("requests"),
            requests_processing=metrics.get("requests_processing"),
            requests_deferred=metrics.get("requests_deferred"),
        )

    def to_ui_metrics(self) -> dict[str, Any]:
        metrics: dict[str, Any] = {}
        for key in (
            "total_prompt_tokens",
            "total_decode_tokens",
            "total_prompt_time",
            "total_decode_time",
            "peps",
            "tps",
            "kv_usage",
            "kv_cache_tokens",
            "ctx_size",
            "requests",
            "requests_processing",
            "requests_deferred",
        ):
            value = getattr(self, key)
            if value is not None:
                metrics[key] = value
        return metrics


@dataclass(frozen=True)
class SlotStateSnapshot:
    slot_id: Any | None = None
    task_id: Any | None = None
    slot_ctx: Any | None = None
    slot_processing: bool = False
    session_decoded: int = 0
    session_remaining: int = 0
    session_has_next_token: bool = False
    session_progress: float | None = None

    @classmethod
    def from_payload(cls, payload: str) -> SlotStateSnapshot | None:
        metrics = parse_slots_status(payload)
        if not metrics:
            return None
        return cls(
            slot_id=metrics.get("slot_id"),
            task_id=metrics.get("task_id"),
            slot_ctx=metrics.get("slot_ctx"),
            slot_processing=bool(metrics.get("slot_processing")),
            session_decoded=int(metrics.get("session_decoded") or 0),
            session_remaining=int(metrics.get("session_remaining") or 0),
            session_has_next_token=bool(metrics.get("session_has_next_token")),
            session_progress=metrics.get("session_progress"),
        )

    def to_ui_metrics(self) -> dict[str, Any]:
        metrics: dict[str, Any] = {
            "slot_id": self.slot_id,
            "task_id": self.task_id,
            "slot_ctx": self.slot_ctx,
            "slot_processing": self.slot_processing,
            "session_decoded": self.session_decoded,
            "session_remaining": self.session_remaining,
            "session_has_next_token": self.session_has_next_token,
        }
        if self.session_progress is not None:
            metrics["session_progress"] = self.session_progress
        return metrics


@dataclass(frozen=True)
class ResourceUsageSnapshot:
    cpu_percent: float | None = None
    ram_total_gb: float | None = None
    ram_used_gb: float | None = None
    ram_free_gb: float | None = None
    ram_percent: float | None = None
    gpu_utilization: float | None = None
    gpu_used_vram_gb: float | None = None
    gpu_total_vram_gb: float | None = None
    gpu_driver: str | None = None

    def to_ui_metrics(self) -> dict[str, str]:
        metrics: dict[str, str] = {}
        if self.cpu_percent is not None:
            metrics["cpu"] = f"{self.cpu_percent:.0f}%"
        if (
            self.ram_used_gb is not None
            and self.ram_total_gb is not None
            and self.ram_percent is not None
        ):
            metrics["ram"] = (
                f"{self.ram_used_gb:.1f} / {self.ram_total_gb:.1f} GB ({self.ram_percent:.0f}%)"
            )
        if self.gpu_utilization is not None:
            metrics["gpu"] = f"{self.gpu_utilization:.0f}%"
        if self.gpu_used_vram_gb is not None and self.gpu_total_vram_gb is not None:
            metrics["gpu_vram"] = (
                f"{self.gpu_used_vram_gb:.1f} / {self.gpu_total_vram_gb:.1f} GB"
            )
        return metrics


@dataclass(frozen=True)
class MonitoringSnapshot:
    server_metrics: ServerMetricsSnapshot | None = None
    slot_state: SlotStateSnapshot | None = None
    ui_metrics: dict[str, Any] | None = None


class MonitoringService:
    def __init__(self, *, metrics_timeout: float = 2.0, slots_timeout: float = 2.0) -> None:
        self.metrics_timeout = metrics_timeout
        self.slots_timeout = slots_timeout

    @staticmethod
    def _fetch_text(url: str, timeout: float) -> str:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")

    def fetch_server_metrics(self, host: str, port: int) -> ServerMetricsSnapshot | None:
        try:
            payload = self._fetch_text(f"http://{host}:{port}/metrics", self.metrics_timeout)
        except Exception:
            return None
        return ServerMetricsSnapshot.from_payload(payload)

    def fetch_slot_state(self, host: str, port: int) -> SlotStateSnapshot | None:
        try:
            payload = self._fetch_text(f"http://{host}:{port}/slots", self.slots_timeout)
        except Exception:
            return None
        return SlotStateSnapshot.from_payload(payload)

    def fetch_local_resource_usage(self) -> ResourceUsageSnapshot | None:
        cpu = get_cpu_usage()
        ram = get_ram_usage()
        gpu = get_gpu_info()
        if cpu is None and ram is None and gpu is None:
            return None
        return ResourceUsageSnapshot(
            cpu_percent=cpu,
            ram_total_gb=ram.get("TotalGB") if ram else None,
            ram_used_gb=ram.get("UsedGB") if ram else None,
            ram_free_gb=ram.get("FreeGB") if ram else None,
            ram_percent=ram.get("Percent") if ram else None,
            gpu_utilization=gpu.get("Utilization") if gpu else None,
            gpu_used_vram_gb=gpu.get("UsedVramGB") if gpu else None,
            gpu_total_vram_gb=gpu.get("TotalVramGB") if gpu else None,
            gpu_driver=gpu.get("Driver") if gpu else None,
        )

    @staticmethod
    def merge_server_and_slot_metrics(
        server_metrics: ServerMetricsSnapshot | None,
        slot_state: SlotStateSnapshot | None,
    ) -> MonitoringSnapshot:
        ui_metrics: dict[str, Any] = {}
        if server_metrics:
            ui_metrics.update(server_metrics.to_ui_metrics())
        if slot_state:
            ui_metrics.update(slot_state.to_ui_metrics())
        return MonitoringSnapshot(
            server_metrics=server_metrics,
            slot_state=slot_state,
            ui_metrics=ui_metrics,
        )

    def collect_monitoring_snapshot(self, host: str, port: int) -> MonitoringSnapshot:
        server_metrics = self.fetch_server_metrics(host, port)
        slot_state = self.fetch_slot_state(host, port)
        return self.merge_server_and_slot_metrics(server_metrics, slot_state)
