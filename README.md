# malama - Malina's Llama Launcher

Electron + TypeScript desktop app for managing `llama-server` / `llama.cpp` workflows on Windows.

## Views
- Deploy
- Library
- Chat
- Settings
- Metrics

## Included assets
- `resources/images/logo.png`
- `model-configs/`
- `presets/`
- `models.registry`
- `docs/`

## Requirements
- Node.js 20+
- npm
- `llama-server.exe` on disk

## Quick start
```powershell
npm install
npm run build
npm start
```

If the server executable is elsewhere, use the app's executable picker in Deploy or Settings.

## Scripts
- `npm run typecheck`
- `npm run build`
- `npm start`
- `npm run package`

## Notes
- No Python/Tkinter or PowerShell launcher path remains.
- The app uses typed IPC and vanilla TypeScript renderer components.
