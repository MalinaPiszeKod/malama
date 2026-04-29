from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterator, Mapping, Sequence


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


class ChatAPIError(RuntimeError):
    pass


def build_base_url(host: str, port: int | str) -> str:
    raw_host = host.strip()
    if not raw_host:
        raw_host = "127.0.0.1"
    if "://" not in raw_host:
        raw_host = f"http://{raw_host}"
    parsed = urllib.parse.urlsplit(raw_host)
    scheme = parsed.scheme or "http"
    hostname = parsed.hostname or parsed.path or "127.0.0.1"
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    actual_port = parsed.port if parsed.port is not None else int(port)
    return f"{scheme}://{hostname}:{actual_port}"


def get_model_id(host: str, port: int | str, timeout: float = 10.0) -> str | None:
    url = f"{build_base_url(host, port)}/v1/models"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception:
        return None

    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                model_id = item.get("id")
                if isinstance(model_id, str) and model_id.strip():
                    return model_id.strip()
    return None


def stream_chat_events(
    host: str,
    port: int | str,
    messages: Sequence[ChatMessage],
    model: str,
    *,
    timeout: float = 300.0,
    extra: Mapping[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    url = f"{build_base_url(host, port)}/v1/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": message.role, "content": message.content} for message in messages],
        "stream": True,
    }
    if extra:
        payload.update(dict(extra))

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict) and event.get("error"):
                    error = event["error"]
                    if isinstance(error, dict):
                        message = error.get("message") or error.get("type") or "chat request failed"
                    else:
                        message = str(error)
                    raise ChatAPIError(message)
                if isinstance(event, dict):
                    yield event
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise ChatAPIError(detail or f"HTTP {exc.code}") from None
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        raise ChatAPIError(str(reason) if reason else "chat request failed") from None


def stream_chat_completion(
    host: str,
    port: int | str,
    messages: Sequence[ChatMessage],
    model: str,
    *,
    timeout: float = 300.0,
    extra: Mapping[str, Any] | None = None,
) -> Iterator[str]:
    for event in stream_chat_events(
        host, port, messages, model, timeout=timeout, extra=extra
    ):
        choices = event.get("choices") if isinstance(event, dict) else None
        if not isinstance(choices, list):
            continue
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta") or {}
            if not isinstance(delta, dict):
                continue
            content = delta.get("content")
            if isinstance(content, str) and content:
                yield content
