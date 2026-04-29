from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections import OrderedDict
from typing import Any, Iterable
import socket
import subprocess
import time

from ..command_builder import args_to_list, build_command_args, command_string


@dataclass(frozen=True)
class LaunchRequest:
    executable_path: Path
    model_path: Path
    settings: dict[str, Any]
    cwd: Path | None = None


@dataclass(frozen=True)
class LaunchCommand:
    executable_path: Path
    args: OrderedDict[str, Any]
    argv: list[str]
    command_text: str
    redacted_command_text: str
    cwd: Path | None = None


@dataclass(frozen=True)
class RunningProcess:
    process: subprocess.Popen[str]
    request: LaunchRequest
    command: LaunchCommand


@dataclass(frozen=True)
class LaunchResult:
    command: LaunchCommand
    running_process: RunningProcess
    started_at: float


class LauncherService:
    def __init__(self, *, secret_flags: Iterable[str] | None = None) -> None:
        self.secret_flags = tuple(secret_flags or ("api-key",))

    @staticmethod
    def normalize_bind_host(host: str | None) -> str:
        value = str(host or "127.0.0.1").strip()
        if value in {"", "*", "[::]"}:
            return "::" if value in {"*", "[::]"} else "127.0.0.1"
        return value

    @staticmethod
    def normalize_poll_host(host: str | None) -> str:
        value = str(host or "127.0.0.1").strip()
        if value in {"0.0.0.0", "::", "[::]", "*", ""}:
            return "127.0.0.1"
        return value

    @classmethod
    def can_bind_port(cls, host: str | None, port: int) -> tuple[bool, str]:
        bind_host = cls.normalize_bind_host(host)
        family = (
            socket.AF_INET6
            if ":" in bind_host and bind_host.count(".") != 3
            else socket.AF_INET
        )
        try:
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((bind_host, int(port)))
            return True, ""
        except OSError as exc:
            return False, str(exc)

    def validate_launch_request(self, request: LaunchRequest) -> None:
        if not request.executable_path.exists() or not request.executable_path.is_file():
            raise FileNotFoundError(f"Executable not found: {request.executable_path}")
        if not request.model_path.exists() or not request.model_path.is_file():
            raise FileNotFoundError(f"Model file not found: {request.model_path}")

    def build_launch_args(self, request: LaunchRequest) -> OrderedDict[str, Any]:
        return build_command_args(request.model_path, request.settings)

    def redact_launch_args(self, args: OrderedDict[str, Any]) -> OrderedDict[str, Any]:
        redacted = OrderedDict(args)
        for key in self.secret_flags:
            if key in redacted and redacted[key] not in {None, ""}:
                redacted[key] = "***"
        return redacted

    def build_launch_command(
        self, request: LaunchRequest, args: OrderedDict[str, Any] | None = None
    ) -> LaunchCommand:
        launch_args = args if args is not None else self.build_launch_args(request)
        argv = [str(request.executable_path), *args_to_list(launch_args)]
        command_text = command_string(request.executable_path, launch_args)
        redacted_text = command_string(
            request.executable_path, self.redact_launch_args(launch_args)
        )
        return LaunchCommand(
            executable_path=request.executable_path,
            args=launch_args,
            argv=argv,
            command_text=command_text,
            redacted_command_text=redacted_text,
            cwd=request.cwd,
        )

    def start_process(
        self, request: LaunchRequest, args: OrderedDict[str, Any] | None = None
    ) -> LaunchResult:
        self.validate_launch_request(request)
        command = self.build_launch_command(request, args=args)
        creationflags = (
            subprocess.CREATE_NO_WINDOW
            if hasattr(subprocess, "CREATE_NO_WINDOW")
            else 0
        )
        cwd = str(command.cwd or request.executable_path.parent)
        process = subprocess.Popen(
            command.argv,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )
        running = RunningProcess(process=process, request=request, command=command)
        return LaunchResult(command=command, running_process=running, started_at=time.time())

    def stop_process(self, running: RunningProcess, timeout: float = 3.0) -> None:
        process = running.process
        try:
            process.terminate()
            process.wait(timeout=timeout)
            return
        except Exception:
            pass
        try:
            process.kill()
            process.wait(timeout=timeout)
        except Exception:
            pass
