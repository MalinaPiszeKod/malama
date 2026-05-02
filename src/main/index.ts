import { app, BrowserWindow } from 'electron';
import { AppPaths } from './AppPaths';
import { JsonStore } from './JsonStore';
import { SettingsService } from './SettingsService';
import { ModelService } from './ModelService';
import { LauncherService } from './LauncherService';
import { MetricsService } from './MetricsService';
import { ChatService } from './ChatService';
import { HuggingFaceService } from './HuggingFaceService';
import { CloudflaredService } from './CloudflaredService';
import { registerIpc } from './ipc';
import { createMainWindow } from './createWindow';
import { DEFAULT_SERVER_SETTINGS } from '../shared/defaults';

async function bootstrap() {
  app.setName("malama - Malina's Llama Launcher");
  await app.whenReady();

  const paths = new AppPaths(app);
  const store = new JsonStore();
  const settings = new SettingsService(paths, store);
  const launcher = new LauncherService(paths, store);
  const metrics = new MetricsService();
  const chat = new ChatService(paths, store);
  const huggingFace = new HuggingFaceService();
  const models = new ModelService(paths, huggingFace);
  const cloudflared = new CloudflaredService(paths);
  let cloudflaredStoppedForQuit = false;

  registerIpc({
    paths,
    settings,
    models,
    launcher,
    metrics,
    chat,
    huggingFace,
    cloudflared,
    async bootstrap() {
      const currentSettings = await settings.load();
      const modelProfiles = await settings.loadModelProfiles();
      const catalog = await models.refreshCatalog();
      const launcherState = launcher.snapshot;
      return {
        settings: currentSettings || DEFAULT_SERVER_SETTINGS,
        modelProfiles,
        presets: await models.loadPresets(),
        catalog,
        metrics: await metrics.collect(launcherState),
        chatSessions: await chat.loadSessions(),
        huggingFace: await huggingFace.search('gguf'),
        launcher: launcherState,
        cloudflared: await cloudflared.getStatus(),
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

  app.on('before-quit', (event) => {
    if (cloudflaredStoppedForQuit || !cloudflared.snapshot.running) return;
    event.preventDefault();
    void cloudflared.stop().then((status) => {
      if (status.running) {
        console.error(status.error || 'Cloudflared tunnel is still running; canceling quit to avoid orphaning a public tunnel.');
        return;
      }
      cloudflaredStoppedForQuit = true;
      app.quit();
    });
  });
}

bootstrap().catch((error) => {
  console.error(error);
  app.exit(1);
});
