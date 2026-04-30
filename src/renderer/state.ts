import type { BootstrapPayload, ChatSession, HuggingFaceModelSummary, LlamaServerSettings, ModelInfo, ModelCatalog, MetricSnapshot, PresetDefinition, ViewName, LauncherSnapshot } from '../shared/types.js';

export interface AppState extends BootstrapPayload {
  view: ViewName;
  selectedModelId?: string;
  selectedSessionId?: string;
  libraryTab: 'description' | 'metadata' | 'estimate';
  hfQuery: string;
  hfResults: HuggingFaceModelSummary[];
  chatDraft: string;
  launcher: LauncherSnapshot;
  settingsDraft: LlamaServerSettings;
}

export interface AppActions {
  setView(view: ViewName): void;
  setSelectedModel(modelId?: string): void;
  setSelectedSession(sessionId?: string): void;
  setLibraryTab(tab: AppState['libraryTab']): void;
  setHfQuery(query: string): void;
  setChatDraft(message: string): void;
  setSettingDraftField<K extends keyof LlamaServerSettings>(key: K, value: LlamaServerSettings[K]): void;
  refresh(): Promise<void>;
  saveSettings(): Promise<void>;
  resetSettings(): Promise<void>;
  launchSelected(): Promise<void>;
  stopLaunch(): Promise<void>;
  chooseExecutable(): Promise<void>;
  searchHf(query: string): Promise<void>;
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
    hfResults: payload.huggingFace,
    chatDraft: '',
    launcher: payload.launcher,
    settingsDraft: payload.settings,
  };
}

export function findSelectedModel(state: AppState): ModelInfo | undefined {
  return state.catalog.models.find((model) => model.id === state.selectedModelId || model.alias === state.selectedModelId);
}

export function findSelectedSession(state: AppState): ChatSession | undefined {
  return state.chatSessions.find((session) => session.id === state.selectedSessionId);
}
