import path from 'node:path';
import { BrowserWindow } from 'electron';
import type { AppPaths } from './AppPaths';

export function createMainWindow(paths: AppPaths): BrowserWindow {
  const preloadPath = path.join(paths.paths.rootDir, 'dist', 'preload', 'preload', 'index.js');
  const window = new BrowserWindow({
    width: 1680,
    height: 1040,
    minWidth: 720,
    minHeight: 800,
    backgroundColor: '#0b1020',
    title: "malama - Malina's Llama Launcher",
    webPreferences: {
      preload: preloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });
  window.loadFile(paths.paths.rendererHtml);
  return window;
}
