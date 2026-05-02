import { clipboard, dialog, ipcMain } from 'electron';
import type { AppPaths } from './AppPaths';
import type { SettingsService } from './SettingsService';
import type { ModelService } from './ModelService';
import type { LauncherService } from './LauncherService';
import type { MetricsService } from './MetricsService';
import type { ChatService } from './ChatService';
import type { HuggingFaceService } from './HuggingFaceService';
import type { CloudflaredService } from './CloudflaredService';
import { IPC_CHANNELS } from '../shared/ipc';
import type { BootstrapResponse } from '../shared/ipc';
import type { ChatSession, HuggingFaceSearchRequest, ModelProfileConfig, ServerSettings } from '../shared/types';

export interface IpcContext {
  paths: AppPaths;
  settings: SettingsService;
  models: ModelService;
  launcher: LauncherService;
  metrics: MetricsService;
  chat: ChatService;
  huggingFace: HuggingFaceService;
  cloudflared: CloudflaredService;
  bootstrap(): Promise<BootstrapResponse>;
}

export function registerIpc(context: IpcContext): void {
  let lastPickedExecutable: string | null = null;
  const objectPayload = <T extends object>(value: unknown, name: string): T => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`${name} must be an object`);
    return value as T;
  };
  const stringPayload = (value: unknown, name: string, maxLength = 4096): string => {
    if (typeof value !== 'string') throw new Error(`${name} must be a string`);
    const trimmed = value.trim();
    if (trimmed.length > maxLength) throw new Error(`${name} is too long`);
    return trimmed;
  };

  ipcMain.handle(IPC_CHANNELS.bootstrap, async () => context.bootstrap());
  ipcMain.handle(IPC_CHANNELS.getSettings, async () => context.settings.load());
  ipcMain.handle(IPC_CHANNELS.saveSettings, async (_event, settings) => context.settings.save(objectPayload<Partial<ServerSettings>>(settings, 'settings')));
  ipcMain.handle(IPC_CHANNELS.resetSettings, async () => context.settings.reset());
  ipcMain.handle(IPC_CHANNELS.saveModelProfile, async (_event, payload: unknown) => {
    const data = objectPayload<{ modelId?: unknown; profile?: unknown }>(payload, 'model profile payload');
    return context.settings.saveModelProfile(stringPayload(data.modelId, 'modelId', 1024), objectPayload<Partial<ModelProfileConfig>>(data.profile, 'profile'));
  });
  ipcMain.handle(IPC_CHANNELS.refreshCatalog, async () => context.models.refreshCatalog());
  ipcMain.handle(IPC_CHANNELS.listPresets, async () => context.models.loadPresets());
  ipcMain.handle(IPC_CHANNELS.launchModel, async (_event, payload: unknown) => {
    const data = objectPayload<{ modelId?: unknown; serverSettings?: unknown; modelProfile?: unknown }>(payload, 'launch payload');
    const modelId = data.modelId === undefined ? undefined : stringPayload(data.modelId, 'modelId', 1024);
    const serverSettings = data.serverSettings === undefined ? await context.settings.load() : objectPayload<Partial<ServerSettings>>(data.serverSettings, 'serverSettings');
    const savedProfiles = await context.settings.loadModelProfiles();
    const modelProfile = {
      ...(modelId ? savedProfiles[modelId] ?? {} : {}),
      ...(data.modelProfile === undefined ? {} : objectPayload<Partial<ModelProfileConfig>>(data.modelProfile, 'modelProfile')),
    };
    return context.launcher.start(await context.models.findModel(modelId), serverSettings, modelProfile);
  });
  ipcMain.handle(IPC_CHANNELS.stopModel, async () => context.launcher.stop());
  ipcMain.handle(IPC_CHANNELS.getLauncher, async () => context.launcher.snapshot);
  ipcMain.handle(IPC_CHANNELS.setExecutablePath, async (_event, filePath: unknown) => {
    const selectedPath = stringPayload(filePath, 'filePath');
    if (selectedPath !== lastPickedExecutable) throw new Error('Executable path must be selected with the native picker first');
    await context.launcher.saveExecutablePath(selectedPath);
  });
  ipcMain.handle(IPC_CHANNELS.getExecutablePath, async () => context.launcher.getExecutablePath());
  ipcMain.handle(IPC_CHANNELS.getMetrics, async () => context.metrics.collect(context.launcher.snapshot));
  ipcMain.handle(IPC_CHANNELS.chatSend, async (_event, payload: unknown) => {
    const data = objectPayload<{ sessionId?: unknown; message?: unknown }>(payload, 'chat payload');
    const sessionId = data.sessionId === undefined ? undefined : stringPayload(data.sessionId, 'sessionId', 256);
    const message = stringPayload(data.message, 'message', 64_000);
    const modelId = context.launcher.snapshot.modelId;
    const modelProfiles = await context.settings.loadModelProfiles();
    return context.chat.sendMessage(sessionId, message, await context.settings.load(), modelId ? modelProfiles[modelId] : undefined, modelId);
  });
  ipcMain.handle(IPC_CHANNELS.getChatSessions, async () => context.chat.loadSessions());
  ipcMain.handle(IPC_CHANNELS.saveChatSession, async (_event, session: unknown) => context.chat.saveSession(objectPayload<ChatSession>(session, 'chat session')));
  ipcMain.handle(IPC_CHANNELS.hfSearch, async (_event, query: unknown) => {
    if (typeof query === 'string') return context.huggingFace.search(stringPayload(query, 'query', 256));
    const payload = objectPayload<{ query?: unknown; tag?: unknown; pipeline?: unknown; sort?: unknown; limit?: unknown }>(query, 'Hugging Face search');
    const request: HuggingFaceSearchRequest = {
      query: payload.query === undefined ? 'gguf' : stringPayload(payload.query, 'query', 256),
      ...(payload.tag === undefined ? {} : { tag: stringPayload(payload.tag, 'tag', 128) }),
      ...(payload.pipeline === undefined ? {} : { pipeline: stringPayload(payload.pipeline, 'pipeline', 128) }),
      ...(payload.sort === undefined ? {} : { sort: stringPayload(payload.sort, 'sort', 32) as HuggingFaceSearchRequest['sort'] }),
      ...(payload.limit === undefined ? {} : { limit: Number(payload.limit) }),
    };
    return context.huggingFace.search(request);
  });
  ipcMain.handle(IPC_CHANNELS.getCloudflared, async () => context.cloudflared.getStatus());
  ipcMain.handle(IPC_CHANNELS.installCloudflared, async () => context.cloudflared.install());
  ipcMain.handle(IPC_CHANNELS.startCloudflared, async () => {
    const launcher = context.launcher.snapshot;
    if (!launcher.running) throw new Error('Start llama-server before exposing it with cloudflared.');
    if (!launcher.apiKeyConfigured) throw new Error('Set an API key and relaunch llama-server before exposing it publicly.');
    return context.cloudflared.start(launcher.host ?? '127.0.0.1', launcher.port ?? 1234);
  });
  ipcMain.handle(IPC_CHANNELS.stopCloudflared, async () => context.cloudflared.stop());
  ipcMain.handle(IPC_CHANNELS.copyText, async (_event, text: unknown) => {
    clipboard.writeText(stringPayload(text, 'text', 4096));
  });
  ipcMain.handle(IPC_CHANNELS.pickExecutable, async (event) => {
    void event;
    const result = await dialog.showOpenDialog({ properties: ['openFile'], filters: [{ name: 'Executable', extensions: ['exe'] }] });
    lastPickedExecutable = result.canceled ? null : result.filePaths[0] ?? null;
    return lastPickedExecutable;
  });
  ipcMain.handle(IPC_CHANNELS.pickDirectory, async (event) => {
    void event;
    const result = await dialog.showOpenDialog({ properties: ['openDirectory'] });
    return result.canceled ? null : result.filePaths[0] ?? null;
  });
}
