# malama - Malina's Llama Launcher

`malama` is a Windows-first Electron desktop launcher for local `llama-server` / `llama.cpp` workflows. It is meant to be the control surface for running local GGUF models, inspecting your model library, chatting with the active server, monitoring runtime health, and optionally exposing an API-key-protected local server through a temporary Cloudflare tunnel.

## What it does

- Starts and stops `llama-server.exe` with typed, validated settings.
- Reads local model metadata from `models.registry` and `model-configs/*.cfg`.
- Shows a model library with local models and Hugging Face search results.
- Provides a ChatGPT-like local chat view against the running OpenAI-compatible endpoint.
- Displays runtime metrics, server reachability, slots, logs, and host resource data.
- Can install a pinned, checksum-verified `cloudflared` helper and create a quick tunnel.
- Lets you copy the generated public tunnel URL from the Deploy view.

Electron + TypeScript is the only supported application path. The previous Python/Tkinter and PowerShell launchers were removed.

## Requirements

- Windows 10/11
- Node.js 20+
- npm
- A local `llama-server.exe`
- At least one GGUF model or a model config pointing at one

Optional:

- Internet access for Hugging Face search and cloudflared helper download.
- An API key configured in Settings if you want to expose the server through cloudflared.

## Project layout

- `src/main/` - Electron main-process services, IPC handlers, process management, persistence.
- `src/preload/` - safe `window.malama` bridge exposed to renderer code.
- `src/renderer/` - vanilla TypeScript UI views, components, and CSS.
- `src/shared/` - shared types, defaults, parsers, IPC contracts, command builder.
- `resources/images/logo.png` - application logo.
- `model-configs/` - per-model config files.
- `presets/` - reusable launcher presets.
- `models.registry` - alias-to-model/config registry.
- `docs/` - architecture and configuration notes.

## Run from source

Install dependencies:

```powershell
npm install
```

Build TypeScript and copy renderer/static assets:

```powershell
npm run build
```

Start the Electron app:

```powershell
npm start
```

If `llama-server.exe` is not next to the app, open Settings and use **Choose executable**.

## Build checks

Run the TypeScript project references without emitting files:

```powershell
npm run typecheck
```

Run a full app build:

```powershell
npm run build
```

The build output is written to `dist/`.

## Make a Windows executable

Package the Electron app:

```powershell
npm run package
```

Outputs are written to `release/`:

- `release/win-unpacked/malama - Malina's Llama Launcher.exe` - runnable unpacked app.
- Installer artifacts are produced by Electron Builder when the local Windows environment permits its signing/tool extraction workflow.

If packaging fails with a Windows symbolic-link privilege error while extracting Electron Builder tools, enable Windows Developer Mode or run the packaging shell as Administrator. The unpacked `.exe` may still be available in `release/win-unpacked/`.

## Using the app

1. Open the app.
2. Go to **Settings** and review global `llama-server` options.
3. Set `ApiKey` if you plan to expose the server publicly.
4. Go to **Deploy**.
5. Tune selected-model load/inference defaults in the right panel if needed.
6. Select a local model from the model tree.
7. Click **Start**.
8. Use **Chat** to talk to the running endpoint.
9. Use **Metrics** to monitor server and host state.

## Expose with cloudflared

The Deploy view includes a **Cloudflared tunnel** panel.

1. Start `llama-server` with an API key configured.
2. If cloudflared is missing, click **Install cloudflared helper**.
3. Click **Expose server**.
4. Wait for the `https://*.trycloudflare.com` URL.
5. Click **Copy URL**.
6. Click **Stop tunnel** when done.

For safety, malama blocks cloudflared exposure unless the active `llama-server` launch has an API key configured. The helper download is pinned and SHA-256 verified before use.

## Coding guide

When changing launcher behavior:

1. Add or update shared types in `src/shared/types.ts`.
2. Add defaults and validation in `src/shared/defaults.ts`.
3. Map command-line flags in `src/shared/commandBuilder.ts`.
4. Add main-process behavior in `src/main/*Service.ts`.
5. Expose safe IPC in `src/shared/ipc.ts`, `src/preload/index.ts`, and `src/main/ipc.ts`.
6. Add UI in `src/renderer/views/` and reusable pieces in `src/renderer/components.ts`.
7. Keep styling customizable through `src/renderer/styles/theme.css` and `layout.css`.
8. Run `npm run typecheck` and `npm run build`.

Renderer code should not access Node APIs directly. Use the typed `window.malama` preload API and validate data again in the main process at IPC boundaries.

## Useful scripts

- `npm run clean` - remove `dist/` and `release/`.
- `npm run typecheck` - TypeScript validation without output.
- `npm run build` - compile and copy static assets.
- `npm start` - build and launch Electron.
- `npm run dev` - same as start for now.
- `npm run package` - build distributable Windows artifacts.
