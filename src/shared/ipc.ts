import type { BrowserWindow } from 'electron';
import type { BootstrapPayload, ChatSession, CloudflaredTunnelSnapshot, HuggingFaceModelSummary, HuggingFaceSearchRequest, LauncherSnapshot, MetricSnapshot, ModelCatalog, ModelProfileConfig, PresetDefinition, ServerSettings } from './types';

export const IPC_CHANNELS = {
  bootstrap: 'malama:bootstrap',
  getSettings: 'malama:settings:get',
  saveSettings: 'malama:settings:save',
  resetSettings: 'malama:settings:reset',
  saveModelProfile: 'malama:modelProfiles:save',
  refreshCatalog: 'malama:models:refresh',
  listPresets: 'malama:presets:list',
  launchModel: 'malama:launcher:start',
  stopModel: 'malama:launcher:stop',
  getLauncher: 'malama:launcher:get',
  setExecutablePath: 'malama:launcher:setExecutablePath',
  getExecutablePath: 'malama:launcher:getExecutablePath',
  getMetrics: 'malama:metrics:get',
  chatSend: 'malama:chat:send',
  getChatSessions: 'malama:chat:list',
  saveChatSession: 'malama:chat:save',
  hfSearch: 'malama:hf:search',
  getCloudflared: 'malama:cloudflared:get',
  installCloudflared: 'malama:cloudflared:install',
  startCloudflared: 'malama:cloudflared:start',
  stopCloudflared: 'malama:cloudflared:stop',
  copyText: 'malama:clipboard:copyText',
  pickExecutable: 'malama:dialogs:pickExecutable',
  pickDirectory: 'malama:dialogs:pickDirectory',
} as const;

export interface BootstrapResponse extends BootstrapPayload {}

export interface MalamaApi {
  bootstrap(): Promise<BootstrapResponse>;
  getSettings(): Promise<ServerSettings>;
  saveSettings(settings: Partial<ServerSettings>): Promise<ServerSettings>;
  resetSettings(): Promise<ServerSettings>;
  saveModelProfile(payload: { modelId: string; profile: Partial<ModelProfileConfig> }): Promise<Record<string, Partial<ModelProfileConfig>>>;
  refreshCatalog(): Promise<ModelCatalog>;
  listPresets(): Promise<PresetDefinition[]>;
  launchModel(payload: { modelId?: string; serverSettings?: Partial<ServerSettings>; modelProfile?: Partial<ModelProfileConfig> }): Promise<LauncherSnapshot>;
  stopModel(): Promise<LauncherSnapshot>;
  getLauncher(): Promise<LauncherSnapshot>;
  setExecutablePath(path: string): Promise<void>;
  getExecutablePath(): Promise<string>;
  getMetrics(): Promise<MetricSnapshot>;
  chatSend(payload: { sessionId?: string; message: string }): Promise<ChatSession>;
  getChatSessions(): Promise<ChatSession[]>;
  saveChatSession(session: ChatSession): Promise<ChatSession>;
  hfSearch(query: string | HuggingFaceSearchRequest): Promise<HuggingFaceModelSummary[]>;
  getCloudflared(): Promise<CloudflaredTunnelSnapshot>;
  installCloudflared(): Promise<CloudflaredTunnelSnapshot>;
  startCloudflared(): Promise<CloudflaredTunnelSnapshot>;
  stopCloudflared(): Promise<CloudflaredTunnelSnapshot>;
  copyText(text: string): Promise<void>;
  pickExecutable(): Promise<string | null>;
  pickDirectory(): Promise<string | null>;
}

export interface MalamaWindow extends Window {
  malama: MalamaApi;
}

declare global {
  interface Window {
    malama: MalamaApi;
  }
}

export interface IpcServices {
  bootstrap(): Promise<BootstrapResponse>;
  getSettings(): Promise<ServerSettings>;
  saveSettings(settings: Partial<ServerSettings>): Promise<ServerSettings>;
  resetSettings(): Promise<ServerSettings>;
  saveModelProfile(payload: { modelId: string; profile: Partial<ModelProfileConfig> }): Promise<Record<string, Partial<ModelProfileConfig>>>;
  refreshCatalog(): Promise<ModelCatalog>;
  listPresets(): Promise<PresetDefinition[]>;
  launchModel(payload: { modelId?: string; serverSettings?: Partial<ServerSettings>; modelProfile?: Partial<ModelProfileConfig> }): Promise<LauncherSnapshot>;
  stopModel(): Promise<LauncherSnapshot>;
  getLauncher(): Promise<LauncherSnapshot>;
  setExecutablePath(path: string): Promise<void>;
  getExecutablePath(): Promise<string>;
  getMetrics(): Promise<MetricSnapshot>;
  chatSend(payload: { sessionId?: string; message: string }): Promise<ChatSession>;
  getChatSessions(): Promise<ChatSession[]>;
  saveChatSession(session: ChatSession): Promise<ChatSession>;
  hfSearch(query: string | HuggingFaceSearchRequest): Promise<HuggingFaceModelSummary[]>;
  getCloudflared(): Promise<CloudflaredTunnelSnapshot>;
  installCloudflared(): Promise<CloudflaredTunnelSnapshot>;
  startCloudflared(): Promise<CloudflaredTunnelSnapshot>;
  stopCloudflared(): Promise<CloudflaredTunnelSnapshot>;
  copyText(text: string): Promise<void>;
  pickExecutable(parent: BrowserWindow): Promise<string | null>;
  pickDirectory(parent: BrowserWindow): Promise<string | null>;
}
