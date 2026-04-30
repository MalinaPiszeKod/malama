import path from 'node:path';
import type { App } from 'electron';
import type { AppPathsState } from '../shared/types';

export class AppPaths {
  private readonly state: AppPathsState;

  constructor(private readonly app: App) {
    const rootDir = app.getAppPath();
    const userDataDir = app.getPath('userData');
    this.state = {
      rootDir,
      distDir: path.join(rootDir, 'dist'),
      userDataDir,
      rendererHtml: path.join(rootDir, 'dist', 'renderer', 'index.html'),
      settingsFile: path.join(userDataDir, 'settings.json'),
      chatSessionsFile: path.join(userDataDir, 'chat-sessions.json'),
      launcherFile: path.join(userDataDir, 'launcher.json'),
      assetsDir: path.join(rootDir, 'resources'),
      registryFile: path.join(rootDir, 'models.registry'),
      presetsDir: path.join(rootDir, 'presets'),
      modelConfigsDir: path.join(rootDir, 'model-configs'),
    };
  }

  get paths(): AppPathsState {
    return this.state;
  }
}
