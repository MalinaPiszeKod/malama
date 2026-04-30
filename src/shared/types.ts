export type ViewName = 'deploy' | 'library' | 'chat' | 'settings' | 'metrics';

export interface LlamaServerSettings {
  GpuLayers: number;
  NcpuMoe: number;
  CtxSize: number;
  Threads: number;
  BatchSize: number;
  UBatchSize: number;
  Temp: number;
  TopP: number;
  TopK: number;
  MinP: number;
  TypicalP: number;
  RepeatPenalty: number;
  RepeatLastN: number;
  PresencePenalty: number;
  FreqPenalty: number;
  CacheTypeK: string;
  CacheTypeV: string;
  FlashAttn: boolean;
  SplitMode: string;
  TensorSplit: number;
  Mlock: boolean;
  NoMmap: boolean;
  Host: string;
  Port: number;
  Parallel: number;
  ApiKey: string;
  Alias: string;
  MultiModel: boolean;
  ModelsDir: string;
  ModelsMax: number;
  ModelsAutoload: boolean;
  Thinking: boolean;
  PreserveThinking: boolean;
  ReasoningFormat: string;
  ReasoningBudget: string;
  Jinja: boolean;
  Webui: boolean;
  Metrics: boolean;
  ContBatching: boolean;
  DryMultiplier: number;
  DryBase: number;
  DryAllowed: number;
  XtcProb: number;
  XtcThresh: number;
  Seed: number;
}

export interface PresetDefinition {
  Name: string;
  Description: string;
  Created?: string;
  File?: string;
  Settings: Partial<LlamaServerSettings>;
}

export interface ModelRegistryEntry {
  alias: string;
  path: string;
  source: 'registry' | 'config' | 'scan';
}

export interface ModelMetadata {
  description: string;
  systemPrompt: string;
  chatTemplate: string;
  host?: string;
  port?: number;
  configPath?: string;
  transformerLayers?: number;
  outputLayer?: boolean;
  fullOffloadLayers?: number;
  extra: Record<string, string>;
}

export interface DeploymentEstimate {
  modelGb: number;
  kvCacheGb: number;
  totalGb: number;
  notes: string[];
}

export interface ModelInfo {
  id: string;
  alias: string;
  name: string;
  path: string;
  directory: string;
  quant: string;
  sizeGb: number;
  metadata: ModelMetadata;
  configSettings: Partial<LlamaServerSettings>;
  registrySource: ModelRegistryEntry['source'];
  estimate: DeploymentEstimate;
}

export interface TreeNode {
  id: string;
  label: string;
  kind: 'group' | 'model';
  children?: TreeNode[];
  modelId?: string;
}

export interface ModelCatalog {
  tree: TreeNode[];
  models: ModelInfo[];
  registry: ModelRegistryEntry[];
  configFiles: string[];
  localRoots: string[];
}

export interface RunningModelSnapshot {
  pid: number;
  redactedCommandText: string;
  cwd: string;
  startedAt: number;
  stdoutTail: string[];
}

export interface LauncherSnapshot {
  running: boolean;
  modelId?: string;
  modelName?: string;
  host?: string;
  port?: number;
  executablePath?: string;
  process?: RunningModelSnapshot;
  error?: string;
}

export interface SlotSnapshot {
  id: number;
  state: string;
  tokens?: number;
  promptTokens?: number;
  generationTokens?: number;
  speedTps?: number;
}

export interface MetricSnapshot {
  timestamp: string;
  server: {
    reachable: boolean;
    metricsText?: string;
    slots: SlotSnapshot[];
  };
  system: {
    platform: string;
    arch: string;
    cpuCount: number;
    loadAvg: number[];
    totalMemMb: number;
    freeMemMb: number;
    usedMemMb: number;
    uptimeSec: number;
  };
  launcher: LauncherSnapshot;
}

export interface ChatMessage {
  id: string;
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string;
  createdAt: string;
}

export interface ChatSession {
  id: string;
  title: string;
  modelId?: string;
  updatedAt: string;
  messages: ChatMessage[];
}

export interface HuggingFaceModelSummary {
  id: string;
  likes?: number;
  downloads?: number;
  pipelineTag?: string;
  tags: string[];
  siblingCount?: number;
  author?: string;
  lastModified?: string;
}

export interface BootstrapPayload {
  settings: LlamaServerSettings;
  presets: PresetDefinition[];
  catalog: ModelCatalog;
  metrics: MetricSnapshot;
  chatSessions: ChatSession[];
  huggingFace: HuggingFaceModelSummary[];
  launcher: LauncherSnapshot;
}

export interface AppPathsState {
  rootDir: string;
  distDir: string;
  userDataDir: string;
  rendererHtml: string;
  settingsFile: string;
  chatSessionsFile: string;
  launcherFile: string;
  assetsDir: string;
  registryFile: string;
  presetsDir: string;
  modelConfigsDir: string;
}
