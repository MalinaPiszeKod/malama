# Development Guide

## Architectural intent

The codebase uses Electron + TypeScript with a clear split between:

- shared domain types, defaults, parsers, and command generation
- main-process services for IO, process management, persistence, and network calls
- a preload bridge exposing a typed `window.malama` API
- renderer views and components for the desktop UI

Avoid putting command semantics in renderer code. UI controls should update typed settings; `src/shared/commandBuilder.ts` should remain the single place that translates settings into `llama-server` arguments.

## Adding a new `llama-server` flag

Add a new flag in this order:

1. add or update the type in `src/shared/types.ts`
2. add the default in `src/shared/defaults.ts`
3. add range/enum validation in the relevant service if needed
4. map the option in `src/shared/commandBuilder.ts`
5. expose the setting in the relevant renderer view
6. run `npm run typecheck` and `npm run build`

## Services

### `ModelService`

Owns registry loading, preset loading, model config parsing, and GGUF catalog refreshes.

### `LauncherService`

Owns executable path persistence, launch request construction, and process lifecycle state.

### `SettingsService`

Owns loading, saving, and resetting `llama-server` settings.

### `ChatService`

Owns local OpenAI-compatible chat requests and chat session persistence.

### `MetricsService`

Owns periodic metrics snapshots for the Metrics view.

### `HuggingFaceService`

Owns model search calls for the Library view.

## UI guidelines

- Keep root views under `src/renderer/views/`.
- Prefer small, reusable component helpers in `src/renderer/components.ts`.
- Keep visual customization in CSS variables and named classes.
- Do not hard-code colors or spacing in TypeScript unless there is no CSS alternative.

## Logging rules

- Log selected model and resolved non-secret configuration.
- Log redacted command lines only.
- Never log API keys or other secrets.
- Prefer stable lifecycle messages that are easy to search.

## Validation expectations

Run:

```powershell
npm run typecheck
npm run build
```

Use `npm start` for a local Electron smoke test when a desktop session is available.
