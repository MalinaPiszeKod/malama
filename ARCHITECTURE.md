# Malina's Llama Launcher Architecture

## Overview

Malina's Llama Launcher is a local launcher and control surface for `llama-server` / `llama.cpp` compatible backends on Windows-first environments.

The refactored architecture keeps behavior stable while separating pure domain logic, persistence, process management, and UI orchestration.

## Module layout

### UI and composition

- `turbolauncher/app.py`
  - Tkinter window and widgets
  - event handlers
  - schedules polling / threads
  - delegates launcher/config/model/session work to services

### Domain and pure logic

- `turbolauncher/settings.py`
  - defaults
  - coercion
  - validation ranges and enums
- `turbolauncher/command_builder.py`
  - central llama-server flag generation
  - command argument ordering
- `turbolauncher/models.py`
  - `ModelEntry`
  - `.cfg` parsing helpers
  - GGUF quant/file metadata
- `turbolauncher/monitoring.py`
  - Prometheus metrics parsing
  - `/slots` parsing
  - OS resource probes
- `turbolauncher/vram.py`
  - VRAM estimation heuristics
- `turbolauncher/chat.py`
  - OpenAI-compatible `/v1/models` and streaming chat helpers

### Services

- `turbolauncher/services/model_service.py`
  - model registry
  - source folders
  - `.gguf` discovery
  - `.cfg` resolution and metadata merge
- `turbolauncher/services/preset_service.py`
  - preset listing/loading/saving
- `turbolauncher/services/session_service.py`
  - session persistence
- `turbolauncher/services/runtime_service.py`
  - runtime path resolution
- `turbolauncher/services/launcher_service.py`
  - launch request validation
  - bind host / poll host normalization
  - subprocess start / stop
  - redacted command logging

### Infrastructure

- `turbolauncher/infrastructure/json_store.py`
  - shared JSON read/write helpers

### Compatibility facade

- `turbolauncher/core.py`
  - stable `LauncherCore` wrapper around service modules
  - preserves older import and call sites

## Configuration model

### Presets

Presets remain JSON files in `presets/*.json`.

Example:

```json
{
  "Name": "Balanced",
  "Description": "General-purpose interactive preset",
  "Created": "2026-04-29 12:00",
  "Settings": {
    "GpuLayers": 30,
    "CtxSize": 65536,
    "Threads": 16,
    "CacheTypeK": "turbo3",
    "CacheTypeV": "turbo3"
  }
}
```

### Model registry

Model registry format is unchanged:

```ini
# Model registry - alias=config_path
qwen36=model-configs/qwen36.cfg
demo_model=D:\Models\demo.gguf
```

### Model config

Model `.cfg` files remain backward-compatible. They can optionally provide offload metadata and chat metadata.

Example:

```ini
MODEL_PATH=D:\Models\demo.gguf
ALIAS=demo
HOST=127.0.0.1
PORT=1234

TRANSFORMER_LAYERS=40
OUTPUT_LAYER=on
FULL_OFFLOAD_LAYERS=41

CHAT_SYS_PROMPT=You are a helpful assistant.
CHAT_TEMPLATE={{ bos_token }}{{ messages }}
```

Offload metadata precedence:

1. `FULL_OFFLOAD_LAYERS`
2. `TRANSFORMER_LAYERS + OUTPUT_LAYER`
3. unknown / unset

### Runtime state

User runtime state remains separate from presets:

- `%APPDATA%/TurboLauncher/session.json`
- `%APPDATA%/TurboLauncher/chat_state.json`
- `%APPDATA%/TurboLauncher/runtime_path.txt`
- `%APPDATA%/TurboLauncher/model_library.json`

## Command generation

All llama-server flags should be added in exactly one place:

- `turbolauncher/command_builder.py`

To add a new flag:

1. add default and type in `settings.py`
2. add validation if needed in `settings.py`
3. map the option to its CLI flag in `command_builder.py`
4. add regression tests in `tests/test_regressions.py`

## Backend / fork extensibility

The launcher currently preserves a single canonical flag builder for llama.cpp-compatible backends.

To add support for a backend or fork:

1. keep shared options in `settings.py`
2. add backend-specific argument mapping in `command_builder.py`
3. if divergence grows, introduce a small backend selector in a new module such as:
   - `turbolauncher/backends.py`
4. keep unsupported combinations validated early with actionable errors

Do not fork flag generation across the UI.

## Logging and secrets

Secrets such as API keys must never be logged directly.

- `LauncherService.build_launch_command()` produces both:
  - full command text
  - redacted command text

UI logs should use the redacted form.

## Known limitations / technical debt

- `app.py` is still the largest file and remains the main composition root.
- Tkinter widget construction is still co-located with many event handlers.
- monitoring is split between server metrics, `/slots`, and chat-stream progress; external non-launcher requests cannot provide full prompt progress.
- backend/fork-specific behavior is prepared for extension but not yet split into dedicated backend modules.
- legacy PowerShell/WPF assets still exist alongside the Python launcher.

## Testing strategy

Current regression coverage focuses on:

- config defaults and compatibility
- model config parsing and offload metadata
- registry and duplicate handling
- command building
- Windows path quoting / paths with spaces
- API key redaction
- invalid configuration errors
- launcher process stop behavior using mocks
- metrics and slots parsing
- chat SSE and prompt-progress event handling
