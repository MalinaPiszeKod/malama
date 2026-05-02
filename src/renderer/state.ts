import type { BootstrapPayload, ChatSession, CloudflaredTunnelSnapshot, HuggingFaceModelSummary, ModelInfo, ModelCatalog, ModelProfileConfig, MetricSnapshot, PresetDefinition, ServerSettings, ViewName, LauncherSnapshot } from '../shared/types.js';

export interface AppState extends BootstrapPayload {
  view: ViewName;
  selectedModelId?: string;
  selectedSessionId?: string;
  libraryTab: 'description' | 'metadata' | 'estimate';
  hfQuery: string;
  hfTagFilter: string;
  hfPipelineFilter: string;
  hfSort: 'downloads' | 'likes' | 'lastModified' | 'modelId';
  hfBrowserOpen: boolean;
  hfResults: HuggingFaceModelSummary[];
  chatDraft: string;
  launcher: LauncherSnapshot;
  cloudflared: CloudflaredTunnelSnapshot;
  settingsDraft: ServerSettings;
  modelProfiles: Record<string, Partial<ModelProfileConfig>>;
  modelProfileDrafts: Record<string, Partial<ModelProfileConfig>>;
}

export interface AppActions {
  setView(view: ViewName): void;
  setSelectedModel(modelId?: string): void;
  setSelectedSession(sessionId?: string): void;
  setLibraryTab(tab: AppState['libraryTab']): void;
  setHfQuery(query: string): void;
  setHfTagFilter(tag: string): void;
  setHfPipelineFilter(pipeline: string): void;
  setHfSort(sort: AppState['hfSort']): void;
  openHfBrowser(): void;
  closeHfBrowser(): void;
  setChatDraft(message: string): void;
  setSettingDraftField<K extends keyof ServerSettings>(key: K, value: ServerSettings[K]): void;
  setModelProfileField<K extends keyof ModelProfileConfig>(modelId: string, key: K, value: ModelProfileConfig[K]): void;
  setModelProfile(modelId: string, profile: Partial<ModelProfileConfig>): void;
  refresh(): Promise<void>;
  saveSettings(): Promise<void>;
  saveSelectedModelProfile(): Promise<void>;
  resetSettings(): Promise<void>;
  launchSelected(): Promise<void>;
  stopLaunch(): Promise<void>;
  chooseExecutable(): Promise<void>;
  copyServerUrl(): Promise<void>;
  installCloudflared(): Promise<void>;
  startCloudflared(): Promise<void>;
  stopCloudflared(): Promise<void>;
  copyCloudflaredUrl(): Promise<void>;
  searchHf(): Promise<void>;
  sendChat(): Promise<void>;
}

export function createInitialState(payload: BootstrapPayload): AppState {
  return {
    ...payload,
    view: 'deploy',
    selectedModelId: payload.catalog.models[0]?.id,
    selectedSessionId: payload.chatSessions[0]?.id,
    libraryTab: 'description',
    hfQuery: 'gguf',
    hfTagFilter: 'gguf',
    hfPipelineFilter: '',
    hfSort: 'downloads',
    hfBrowserOpen: false,
    hfResults: payload.huggingFace,
    chatDraft: '',
    launcher: payload.launcher,
    cloudflared: payload.cloudflared,
    settingsDraft: payload.settings,
    modelProfiles: payload.modelProfiles,
    modelProfileDrafts: {},
  };
}

export function findSelectedModel(state: AppState): ModelInfo | undefined {
  return state.catalog.models.find((model) => model.id === state.selectedModelId || model.alias === state.selectedModelId);
}

export function findSelectedSession(state: AppState): ChatSession | undefined {
  return state.chatSessions.find((session) => session.id === state.selectedSessionId);
}
