# Configuration

This document describes the configuration files and runtime state used by `malama - Malina's Llama Launcher`.

## Project data files

### Presets

Location:

- `presets/*.json`

Purpose:

- reusable launcher/model profiles

Key fields:

- `Name`
- `Description`
- `Created`
- `Settings`

The `Settings` object maps onto typed options defined in `src/shared/types.ts` and defaulted in `src/shared/defaults.ts`. Server-global settings are stored separately from model profile settings.

### Server settings

Location:

- Electron user-data `settings.json`

Purpose:

- global `llama-server.exe` process settings
- host/port/API key
- logging, metrics, batching, parallelism
- multi-model repository mode
- launcher health/startup behavior

These settings are edited only from the app Settings tab.

### Model profiles

Location:

- Electron user-data `settings.json` under `modelProfiles`
- optional project sidecars in `model-configs/*.cfg`

Purpose:

- selected model identity and alias
- model load/runtime overrides
- inference, sampling, reasoning, and prompt defaults

These settings are edited from the selected-model panel in Deploy.

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

- per-model metadata and profile defaults
- model path indirection
- chat metadata
- model-load/offload metadata

Common keys:

- `MODEL_PATH`
- `ALIAS`
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

## Runtime state

Runtime state is stored in Electron's user-data directory, resolved by `src/main/AppPaths.ts`.

Current files:

- `settings.json`
- `launcher.json`
- `chat-sessions.json`

These are user/runtime state files, not committed project config.

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

## Validation expectations

The launcher should validate early for:

- missing runtime executable
- missing model file
- invalid numeric settings
- invalid enum values
- occupied port
- unsupported flag combinations where known

Relevant implementation areas:

- `src/main/SettingsService.ts`
- `src/main/LauncherService.ts`
- `src/shared/commandBuilder.ts`

## Example model config

```ini
MODEL_PATH=D:\Models\demo.gguf
ALIAS=demo
TRANSFORMER_LAYERS=40
OUTPUT_LAYER=on
FULL_OFFLOAD_LAYERS=41

CTX_SIZE=65536
CACHE_TYPE_K=turbo3
CACHE_TYPE_V=turbo3
FLASH_ATTN=on

CHAT_SYS_PROMPT=You are a concise assistant.
CHAT_TEMPLATE={{ bos_token }}{{ messages }}
```
