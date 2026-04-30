import { app, BrowserWindow } from 'electron';
import { AppPaths } from './AppPaths';
import { JsonStore } from './JsonStore';
import { SettingsService } from './SettingsService';
import { ModelService } from './ModelService';
import { LauncherService } from './LauncherService';
import { MetricsService } from './MetricsService';
import { ChatService } from './ChatService';
import { HuggingFaceService } from './HuggingFaceService';
import { registerIpc } from './ipc';
import { createMainWindow } from './createWindow';
import { DEFAULT_SETTINGS } from '../shared/defaults';

async function bootstrap() {
  app.setName("malama - Malina's Llama Launcher");
  await app.whenReady();

  const paths = new AppPaths(app);
  const store = new JsonStore();
  const settings = new SettingsService(paths, store);
  const models = new ModelService(paths);
  const launcher = new LauncherService(paths, store);
  const metrics = new MetricsService();
  const chat = new ChatService(paths, store);
  const huggingFace = new HuggingFaceService();

  registerIpc({
    paths,
    settings,
    models,
    launcher,
    metrics,
    chat,
    huggingFace,
    async bootstrap() {
      const currentSettings = await settings.load();
      const catalog = await models.refreshCatalog(await settings.loadOverrides());
      const launcherState = launcher.snapshot;
      return {
        settings: currentSettings || DEFAULT_SETTINGS,
        presets: await models.loadPresets(),
        catalog,
        metrics: await metrics.collect(launcherState),
        chatSessions: await chat.loadSessions(),
        huggingFace: await huggingFace.search('gguf'),
        launcher: launcherState,
      };
    },
  });

  await launcher.initialize();

  createMainWindow(paths);

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createMainWindow(paths);
  });

  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
  });
}

bootstrap().catch((error) => {
  console.error(error);
  app.exit(1);
});
