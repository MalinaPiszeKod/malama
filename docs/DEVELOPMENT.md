# Development Guide

## Architectural intent

The codebase aims for pragmatic separation of concerns:

- pure setting/command/parse logic stays in small modules
- side effects live in focused services
- Tkinter remains the composition root, not the place where command semantics are invented

Avoid adding framework-style abstractions unless there is a real extension need.

## Adding a new llama-server flag

Add a new flag in this order:

1. add the default in `turbolauncher/settings.py`
2. add the type in `SETTING_TYPES`
3. add range/enum validation if needed
4. map the option in `turbolauncher/command_builder.py`
5. add or update regression tests in `tests/test_regressions.py`

Keep command generation centralized. Do not build flags in the UI.

## Adding backend / fork support

Backend/fork-specific command changes belong in:

- `turbolauncher/command_backends.py`

Guidelines:

- preserve shared llama.cpp-compatible behavior in `command_builder.py`
- keep backend-specific mutations small and explicit
- validate unsupported combinations early
- avoid introducing a plugin framework unless there are multiple truly divergent backends

Typical extension pattern:

1. add a backend identifier or rule hook
2. apply backend-specific argument mutations in one obvious place
3. add tests for that backend-specific behavior

## Services

### `ModelService`

Owns:

- registry loading/saving
- model source directory persistence
- GGUF scanning
- sidecar cfg resolution

### `PresetService`

Owns:

- preset listing/loading/saving

### `SessionService`

Owns:

- session persistence

### `RuntimeService`

Owns:

- runtime executable path persistence/resolution

### `LauncherService`

Owns:

- launch request validation
- bind host normalization
- redacted command generation
- subprocess start/stop behavior

### Monitoring service

If extending runtime telemetry, keep network/resource polling out of the Tkinter code and prefer typed snapshots passed back to the UI.

## Logging rules

- Log selected model and resolved non-secret configuration
- Log redacted command lines only
- Never log API keys or other secrets
- Prefer stable, grep-friendly lifecycle messages

## Testing expectations

Add or preserve tests for:

- config defaults
- command generation
- path quoting on Windows
- secret redaction
- model registry loading
- duplicate model handling
- invalid config errors
- process lifecycle with mocks
- backward compatibility with existing file formats

Run:

```powershell
py -3 -m unittest tests.test_regressions -v
py -3 TurboLauncher.py --headless
```

## Remaining technical debt

- `app.py` is still the composition root and remains large
- some UI construction and event handling still live in the same module
- metrics combine multiple data sources with different scopes
- backend extension is lightweight, not a full multi-backend framework

These are deliberate trade-offs for behavior stability and incremental refactoring.
