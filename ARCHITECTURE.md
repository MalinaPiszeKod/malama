# malama Architecture

## Overview

`malama - Malina's Llama Launcher` is an Electron + TypeScript desktop control surface for local `llama-server` / `llama.cpp` workflows.

Electron is the only supported application path. Legacy Python, Tkinter, and PowerShell launchers have been removed.

## Module layout

### Main process

- `src/main/index.ts` boots Electron, creates services, registers IPC, and opens the main window.
- `src/main/createWindow.ts` configures the browser window and preload script.
- `src/main/AppPaths.ts` centralizes project, asset, and user-data paths.
- `src/main/SettingsService.ts` loads, saves, and resets server settings plus per-model profile overrides.
- `src/main/ModelService.ts` loads presets, registry entries, GGUF files, and model config metadata.
- `src/main/LauncherService.ts` owns `llama-server.exe` path persistence plus process start/stop state.
- `src/main/ChatService.ts` calls the OpenAI-compatible local chat API and persists sessions.
- `src/main/MetricsService.ts` collects launcher and host metrics snapshots.
- `src/main/HuggingFaceService.ts` searches Hugging Face model data.
- `src/main/ipc.ts` exposes typed IPC handlers.

### Preload

- `src/preload/index.ts` exposes the safe `window.malama` API through Electron context isolation.

### Shared domain

- `src/shared/types.ts` defines app, model, preset, metrics, chat, and settings types.
- `src/shared/defaults.ts` defines default server settings, model profile defaults, inference defaults, and presets.
- `src/shared/parsers.ts` parses model registry/config formats.
- `src/shared/commandBuilder.ts` centralizes structured `llama-server` argument and request-default generation.
- `src/shared/ipc.ts` defines IPC channel names and API contracts.

### Renderer

- `src/renderer/index.ts` owns renderer state wiring and action dispatch.
- `src/renderer/app.ts` renders the top-level shell and root view routing.
- `src/renderer/components.ts` contains reusable DOM component helpers.
- `src/renderer/views/` contains Deploy, Library, Chat, Settings, and Metrics views.
- `src/renderer/styles/theme.css` contains theme tokens and component primitives.
- `src/renderer/styles/layout.css` contains app layout and responsive view structure.

## Configuration and data

The app preserves existing data assets:

- `resources/images/logo.png`
- `models.registry`
- `model-configs/*.cfg`
- `presets/*.json`
- `docs/`

User runtime state is stored in Electron's user-data directory through `AppPaths`, including:

- `settings.json`
- `launcher.json`
- `chat-sessions.json`

## Configuration ownership

- Settings tab owns `ServerSettings`: executable path, host, port, API key, metrics/logging, process strategy, health/startup behavior, and multi-model repository mode.
- Deploy right panel owns `ModelProfileConfig`: selected-model identity, load/runtime options, prompt/template overrides, inference defaults, sampling, and reasoning defaults.
- `LauncherSnapshot` / `RuntimeDeploymentState` describe live runtime state and are not persisted as user config.

## Command generation

All `llama-server` CLI flags should be added in one place:

- `src/shared/commandBuilder.ts`

To add a new setting:

1. add the field/type in `src/shared/types.ts` under the correct owner (`ServerSettings`, `ModelProfileConfig`, or request defaults)
2. add its default in `src/shared/defaults.ts`
3. map server startup args, model-load args, or request defaults in `src/shared/commandBuilder.ts`
4. expose server-global fields only in `src/renderer/views/settings.ts`; expose selected-model fields only in the Deploy right panel
5. keep IPC payloads typed through `src/shared/ipc.ts`

## UI architecture

Views should stay modular and styling should remain customizable through CSS variables/classes. User-facing UI belongs under `src/renderer/views/`; shared primitives belong in `src/renderer/components.ts`.

## Security notes

- Renderer code talks to the main process only through `window.malama`.
- `contextIsolation` is enabled and `nodeIntegration` is disabled.
- Secrets and full API keys must not be logged.
- UI logs should display redacted command text where applicable.

## Validation

Use:

```powershell
npm run typecheck
npm run build
```

Optional packaging smoke test:

```powershell
npm run package
```
