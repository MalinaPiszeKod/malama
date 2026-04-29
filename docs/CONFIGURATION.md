# Configuration

This document describes the configuration files and runtime state used by Malina's Llama Launcher.

## File overview

### Presets

Location:

- `presets/*.json`

Purpose:

- reusable launcher settings profiles

Key fields:

- `Name`
- `Description`
- `Created`
- `Settings`

The `Settings` object maps directly onto launcher options defined in `turbolauncher/settings.py`.

### Model registry

Location:

- `models.registry`

Purpose:

- maps aliases to GGUF files or model config files

Format:

```ini
alias=path
```

Examples:

```ini
demo=D:\Models\demo.gguf
qwen36=model-configs/qwen36.cfg
```

### Model configs

Location:

- `model-configs/*.cfg`

Purpose:

- per-model metadata and defaults
- model path indirection
- chat metadata
- generic offload metadata

Common keys:

- `MODEL_PATH`
- `ALIAS`
- `HOST`
- `PORT`
- `THREADS`
- `CTX_SIZE`
- `CACHE_TYPE_K`
- `CACHE_TYPE_V`
- `FLASH_ATTN`
- `CHAT_SYS_PROMPT`
- `CHAT_TEMPLATE`
- `PROMPT_TEMPLATE`
- `TRANSFORMER_LAYERS`
- `OUTPUT_LAYER`
- `FULL_OFFLOAD_LAYERS`

### Runtime state

Location:

- `%APPDATA%\TurboLauncher\session.json`
- `%APPDATA%\TurboLauncher\runtime_path.txt`
- `%APPDATA%\TurboLauncher\model_library.json`
- `%APPDATA%\TurboLauncher\chat_state.json`

Purpose:

- stores current session, runtime path, model source folders, download directory, and chat state

These are user/runtime state files, not committed project config.

## Backward compatibility

The launcher preserves compatibility with existing preset/session/config formats where possible.

### Session compatibility

`session.json` intentionally writes both:

- legacy top-level keys such as `LastPreset` and `LastModel`
- nested `Settings`

This keeps older behavior stable while allowing newer code to consume structured settings.

## Offload metadata

The launcher supports generic model offload metadata in sidecar configs.

### Supported keys

- `TRANSFORMER_LAYERS=<int>`
- `OUTPUT_LAYER=on|off|true|false|1|0`
- `FULL_OFFLOAD_LAYERS=<int>`

### Precedence

1. `FULL_OFFLOAD_LAYERS`
2. `TRANSFORMER_LAYERS + OUTPUT_LAYER`
3. unset / unknown

If `OUTPUT_LAYER` is omitted and `TRANSFORMER_LAYERS` is present, the launcher assumes full offload includes one output layer unless explicitly disabled.

## Source folders

Source folders are stored in `model_library.json` under `source_dirs`.

Default source directories are resolved generically through `turbolauncher/model_sources.py` and are no longer meant to live as machine-specific service internals.

Environment override support can be added or adjusted there without changing discovery logic.

## Validation expectations

The launcher validates early for:

- missing runtime executable
- missing model file
- invalid numeric settings
- invalid enum values
- occupied port
- unsupported flag combinations where known

Validation entry points:

- `turbolauncher/settings.py`
- `turbolauncher/services/launcher_service.py`

## Example model config

```ini
MODEL_PATH=D:\Models\demo.gguf
ALIAS=demo
HOST=127.0.0.1
PORT=1234

TRANSFORMER_LAYERS=40
OUTPUT_LAYER=on
FULL_OFFLOAD_LAYERS=41

THREADS=16
CTX_SIZE=65536
CACHE_TYPE_K=turbo3
CACHE_TYPE_V=turbo3
FLASH_ATTN=on

CHAT_SYS_PROMPT=You are a concise assistant.
CHAT_TEMPLATE={{ bos_token }}{{ messages }}
```
