# Malina's Llama Launcher

Malina's Llama Launcher is a Windows-first desktop launcher for running and managing `llama-server` / `llama.cpp` compatible local LLM deployments.

It is designed for serious local inference workflows: selecting GGUF models, applying presets, tuning runtime/offload settings, launching an OpenAI-compatible endpoint, inspecting the exact generated command, monitoring runtime metrics, and chatting with the active server.

## Highlights

- Tkinter desktop UI with a dark, developer-tool oriented layout
- GGUF model discovery from source folders and a registry file
- Stable preset system with backward-compatible JSON format
- Support for model sidecar config files (`model-configs/*.cfg`)
- Centralized llama-server command generation
- Redacted command logging for secrets such as API keys
- Runtime validation for model path, executable path, ports, and numeric settings
- OpenAI-compatible chat tab with streaming responses
- Metrics from `/metrics`, `/slots`, and local CPU/RAM/GPU probes
- Generic offload metadata support for full GPU offload accounting

## Repository layout

```text
turbolauncher/
  app.py                  # Tkinter app / composition root
  core.py                 # compatibility facade
  settings.py             # defaults, coercion, validation
  command_builder.py      # central llama-server flag mapping
  command_backends.py     # lightweight backend/fork extension rules
  models.py               # model metadata and cfg parsing
  monitoring.py           # metrics and slot parsers + resource probes
  chat.py                 # OpenAI-compatible chat streaming helpers
  vram.py                 # VRAM estimation heuristics
  model_sources.py        # generic default model source rules
  infrastructure/
    json_store.py         # shared JSON persistence helpers
  services/
    launcher_service.py   # process lifecycle + command redaction
    model_service.py      # registry / discovery / model resolution
    preset_service.py     # preset persistence
    runtime_service.py    # runtime path resolution
    session_service.py    # session persistence

presets/                  # shipped preset JSON files
model-configs/            # example / user model cfg files
tests/                    # regression tests
resources/images/         # launcher assets
```

## Requirements

- Windows 10/11 recommended
- Python 3.11+
- A `llama-server.exe` compatible runtime
- Local GGUF model files

Optional:

- `nvidia-smi` for GPU utilization/VRAM telemetry
- Hugging Face access if using model downloads

## Quick start

### 1. Clone and launch

```powershell
git clone <repo-url>
cd TurboLauncher
py -3 TurboLauncher.py
```

### 2. Configure runtime

Use the **Runtime** button to point the launcher at `llama-server.exe`.

### 3. Add or discover models

The launcher will discover `.gguf` models from configured source folders and the registry.

You can also add explicit models through:

- `models.registry`
- `model-configs/*.cfg`
- the UI model library / add-model flow

### 4. Pick a model and preset

Typical flow:

1. choose model
2. choose preset
3. review context / offload / cache settings
4. inspect the generated command
5. click **Start**

## Configuration files

### Presets

Presets live in `presets/*.json`.

Example:

```json
{
  "Name": "Balanced",
  "Description": "General purpose local inference preset",
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

The model registry format is line-based and intentionally simple:

```ini
# Model registry - alias=config_path
qwen36=model-configs/qwen36.cfg
demo=D:\Models\demo.gguf
```

### Model config files

Model config files remain backward-compatible and can carry model metadata, launcher defaults, and chat settings.

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

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for details.

## Command generation

The launcher always builds commands from typed settings and shows the generated command in the UI.

Important properties:

- no ad hoc shell string concatenation
- Windows path quoting is handled centrally
- secrets are redacted in logged command output
- unsupported or invalid values fail early with actionable errors

## Backends and forks

The project currently targets `llama.cpp` compatible servers, including forked builds that mostly preserve flag compatibility.

Backend/fork-specific mutations live in:

- `turbolauncher/command_backends.py`

This keeps fork-specific behavior explicit and contained without introducing a heavy plugin framework.

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for extension guidance.

## Testing

Run the regression suite:

```powershell
py -3 -m unittest tests.test_regressions -v
```

Run headless validation:

```powershell
py -3 TurboLauncher.py --headless
```

Current automated coverage includes:

- config defaults and compatibility
- model registry and sidecar config parsing
- duplicate model handling
- command generation and quoting
- API key redaction
- invalid configuration errors
- launcher process stop behavior via mocks
- metrics and slot parsing
- chat stream and prompt-progress event parsing

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md)
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)

## Known limitations

- The Tkinter app is still the main composition root.
- Some runtime metrics are server-global while others are per-session.
- Full prompt-prefill progress is only available for requests initiated by the launcher when the backend emits it.
- Backend extension is intentionally lightweight rather than a full plugin system.

## License / status

This repository is intended as a serious local developer utility. If you publish it publicly, add a license file that matches your intended usage and distribution terms.
