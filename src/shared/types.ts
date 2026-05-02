export type ViewName = 'deploy' | 'library' | 'chat' | 'settings' | 'metrics';

export interface ServerSettings {
  Host: string;
  Port: number;
  ApiKey: string;
  Webui: boolean;
  Metrics: boolean;
  ContBatching: boolean;
  Threads: number;
  BatchSize: number;
  UBatchSize: number;
  Parallel: number;
  MultiModel: boolean;
  ModelsDir: string;
  ModelsMax: number;
  ModelsAutoload: boolean;
  DefaultWorkingDirectory: string;
  HealthCheckTimeoutMs: number;
  StartupBehavior: 'manual' | 'launch-selected-on-open';
  ProcessStrategy: 'single-server-process' | 'multiple-managed-processes';
  LogVerbosity: string;
}

export interface ModelLoadSettings {
  Alias: string;
  CtxSize: number;
  GpuLayers: number;
  NcpuMoe: number;
  CacheTypeK: string;
  CacheTypeV: string;
  FlashAttn: string;
  SplitMode: string;
  TensorSplit: string;
  MainGpu: number;
  Device: string;
  Mlock: boolean;
  NoMmap: boolean;
  Jinja: boolean;
  ChatTemplate: string;
  SystemPrompt: string;
  RopeScaling: string;
  RopeFreqBase: string;
  RopeFreqScale: string;
}

export interface InferenceDefaults {
  MaxTokens: number;
  Thinking: boolean;
  PreserveThinking: boolean;
  ReasoningFormat: string;
  ReasoningBudget: string;
  StopSequences: string;
  Temp: number;
  TopP: number;
  TopK: number;
  MinP: number;
  TypicalP: number;
  RepeatPenalty: number;
  RepeatLastN: number;
  PresencePenalty: number;
  FreqPenalty: number;
  DryMultiplier: number;
  DryBase: number;
  DryAllowed: number;
  XtcProb: number;
  XtcThresh: number;
  Seed: number;
}

export interface ModelProfileConfig extends ModelLoadSettings, InferenceDefaults {}

export type LlamaServerSettings = ServerSettings & ModelProfileConfig;

export type DeploymentMode = 'single-model-process' | 'multi-model-repository' | 'multiple-managed-processes';

export interface DeploymentConfig {
  mode: DeploymentMode;
  modelPath?: string;
  modelsDir?: string;
  alias?: string;
}

export interface ModelDeploymentState {
  modelId?: string;
  modelName?: string;
  alias?: string;
  endpoint?: string;
  status: 'starting' | 'running' | 'unavailable' | 'error';
  error?: string;
}

export interface RuntimeDeploymentState {
  mode: DeploymentMode;
  deployments: ModelDeploymentState[];
  health: 'unknown' | 'ready' | 'unreachable';
  error?: string;
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
  repository: string;
  baseModelRepository?: string;
  baseModelRepositoryUrl?: string;
  family: string;
  tags: string[];
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
  configSettings: Partial<ModelProfileConfig>;
  registrySource: ModelRegistryEntry['source'];
  estimate: DeploymentEstimate;
}

export interface TreeNode {
  id: string;
  label: string;
  detail?: string;
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
  redactedArgs: string[];
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
  apiKeyConfigured?: boolean;
  executablePath?: string;
  mode?: DeploymentMode;
  deployment?: RuntimeDeploymentState;
  process?: RunningModelSnapshot;
  error?: string;
}

export interface CloudflaredTunnelSnapshot {
  installed: boolean;
  installing: boolean;
  running: boolean;
  executablePath?: string;
  targetUrl?: string;
  publicUrl?: string;
  pid?: number;
  startedAt?: number;
  stdoutTail: string[];
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

export interface HuggingFaceSearchRequest {
  query: string;
  tag?: string;
  pipeline?: string;
  sort?: 'downloads' | 'likes' | 'lastModified' | 'modelId';
  limit?: number;
}

export interface BootstrapPayload {
  settings: ServerSettings;
  modelProfiles: Record<string, Partial<ModelProfileConfig>>;
  presets: PresetDefinition[];
  catalog: ModelCatalog;
  metrics: MetricSnapshot;
  chatSessions: ChatSession[];
  huggingFace: HuggingFaceModelSummary[];
  launcher: LauncherSnapshot;
  cloudflared: CloudflaredTunnelSnapshot;
}

export interface AppPathsState {
  rootDir: string;
  distDir: string;
  userDataDir: string;
  rendererHtml: string;
  settingsFile: string;
  chatSessionsFile: string;
  launcherFile: string;
  toolsDir: string;
  assetsDir: string;
  registryFile: string;
  presetsDir: string;
  modelConfigsDir: string;
}
