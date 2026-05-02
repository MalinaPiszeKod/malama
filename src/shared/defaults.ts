import type { InferenceDefaults, LlamaServerSettings, ModelLoadSettings, ModelProfileConfig, PresetDefinition, ServerSettings } from './types';

export const CACHE_TYPES = ['f32', 'f16', 'bf16', 'q8_0', 'q4_0', 'q4_1', 'iq4_nl', 'q5_0', 'q5_1', 'turbo4', 'turbo3'] as const;
export const SPLIT_MODES = ['auto', 'none', 'layer', 'row'] as const;
export const FLASH_ATTN_MODES = ['auto', 'on', 'off'] as const;
export const REASONING_FORMATS = ['auto', 'none', 'deepseek', 'deepseek-legacy'] as const;
export const STARTUP_BEHAVIORS = ['manual', 'launch-selected-on-open'] as const;
export const PROCESS_STRATEGIES = ['single-server-process', 'multiple-managed-processes'] as const;

export const DEFAULT_SERVER_SETTINGS: ServerSettings = {
  Host: '127.0.0.1',
  Port: 1234,
  ApiKey: '',
  Webui: true,
  Metrics: true,
  ContBatching: true,
  Threads: 16,
  BatchSize: 512,
  UBatchSize: 512,
  Parallel: 1,
  MultiModel: false,
  ModelsDir: '',
  ModelsMax: 4,
  ModelsAutoload: true,
  DefaultWorkingDirectory: '',
  HealthCheckTimeoutMs: 2000,
  StartupBehavior: 'manual',
  ProcessStrategy: 'single-server-process',
  LogVerbosity: '',
};

export const DEFAULT_MODEL_LOAD_SETTINGS: ModelLoadSettings = {
  Alias: '',
  CtxSize: 65536,
  GpuLayers: 30,
  NcpuMoe: 28,
  CacheTypeK: 'f16',
  CacheTypeV: 'f16',
  FlashAttn: 'auto',
  SplitMode: 'auto',
  TensorSplit: '',
  MainGpu: -1,
  Device: '',
  Mlock: false,
  NoMmap: false,
  Jinja: true,
  ChatTemplate: '',
  SystemPrompt: '',
  RopeScaling: '',
  RopeFreqBase: '',
  RopeFreqScale: '',
};

export const DEFAULT_INFERENCE_DEFAULTS: InferenceDefaults = {
  MaxTokens: -1,
  Temp: 1,
  TopP: 0.95,
  TopK: 20,
  MinP: 0,
  TypicalP: 1,
  RepeatPenalty: 1,
  RepeatLastN: 64,
  PresencePenalty: 1.5,
  FreqPenalty: 0,
  Thinking: true,
  PreserveThinking: true,
  ReasoningFormat: 'auto',
  ReasoningBudget: '',
  StopSequences: '',
  DryMultiplier: 0,
  DryBase: 1,
  DryAllowed: 2,
  XtcProb: 0,
  XtcThresh: 0.5,
  Seed: -1,
};

export const DEFAULT_MODEL_PROFILE_CONFIG: ModelProfileConfig = {
  ...DEFAULT_MODEL_LOAD_SETTINGS,
  ...DEFAULT_INFERENCE_DEFAULTS,
};

export const DEFAULT_SETTINGS: LlamaServerSettings = {
  ...DEFAULT_SERVER_SETTINGS,
  ...DEFAULT_MODEL_PROFILE_CONFIG,
};

export const BUILT_IN_PRESETS: PresetDefinition[] = [
  { Name: 'Agentic AI', Description: 'Thinking ON + preserve, optimized for tool calling and MCP agents', File: 'agentic-ai.json', Settings: { Thinking: true, PreserveThinking: true, Temp: 1, TopP: 0.95 } },
  { Name: 'Coding Precise', Description: 'Thinking ON + preserve, lower temp for precise code generation', File: 'coding-precise.json', Settings: { Thinking: true, PreserveThinking: true, Temp: 0.4, TopP: 0.9 } },
  { Name: 'Fast Chat', Description: 'Thinking OFF, faster responses for general conversation', File: 'fast-chat.json', Settings: { Thinking: false, PreserveThinking: false, Temp: 0.7, TopP: 0.8 } },
  { Name: 'Deep Reasoning', Description: 'Thinking ON + preserve, 131K context for complex planning', File: 'deep-reasoning.json', Settings: { Thinking: true, PreserveThinking: true, CtxSize: 131072 } },
  { Name: 'Max Context', Description: 'Thinking ON + preserve, full 262K context window', File: 'max-context.json', Settings: { Thinking: true, PreserveThinking: true, CtxSize: 262144 } },
];

export const RECOMMENDED_MODELS = [
  { Id: 'Qwen/Qwen2.5-1.5B-Instruct-GGUF', Name: 'Qwen2.5-1.5B-Instruct', Size: '~1GB (Q4_K_M)', BestFor: 'Testing, quick prototyping', PreferredQuant: 'Q4_K_M' },
  { Id: 'Qwen/Qwen2.5-3B-Instruct-GGUF', Name: 'Qwen2.5-3B-Instruct', Size: '~2GB (Q4_K_M)', BestFor: 'General chat, fast responses', PreferredQuant: 'Q4_K_M' },
  { Id: 'Qwen/Qwen2.5-7B-Instruct-GGUF', Name: 'Qwen2.5-7B-Instruct', Size: '~4.8GB (Q4_K_M)', BestFor: 'Balanced performance', PreferredQuant: 'Q4_K_M' },
  { Id: 'microsoft/Phi-3.5-mini-instruct-GGUF', Name: 'Phi-3.5-mini-4K', Size: '~2.2GB (Q4_K_M)', BestFor: 'Efficient reasoning, coding', PreferredQuant: 'Q4_K_M' },
  { Id: 'google/gemma-3-1b-it-GGUF', Name: 'Gemma-3-1B-IT', Size: '~0.7GB (Q4_K_M)', BestFor: 'Ultra-fast inference, testing', PreferredQuant: 'Q4_K_M' },
  { Id: 'meta-llama/Llama-3.2-3B-Instruct-GGUF', Name: 'Llama-3.2-3B-Instruct', Size: '~2GB (Q4_K_M)', BestFor: 'General purpose, coding', PreferredQuant: 'Q4_K_M' },
] as const;

const numericPattern = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/;
const intPattern = /^[+-]?\d+$/;

export function asBool(value: unknown): boolean {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value !== 0;
  return String(value).trim().toLowerCase() === 'true'
    || String(value).trim().toLowerCase() === 'yes'
    || String(value).trim().toLowerCase() === 'on'
    || String(value).trim().toLowerCase() === 'enabled'
    || String(value).trim() === '1';
}

export function coerceSetting<K extends keyof LlamaServerSettings>(key: K, value: unknown, strict = false): LlamaServerSettings[K] {
  const fallback = DEFAULT_SETTINGS[key];
  const target = typeof fallback;
  try {
    if (target === 'boolean') return asBool(value) as LlamaServerSettings[K];
    if (target === 'number') {
      if (typeof value === 'number') return value as LlamaServerSettings[K];
      if (typeof value === 'boolean') return Number(value) as LlamaServerSettings[K];
      const raw = String(value ?? '').trim();
      const text = strict ? raw : raw.replace(/[^0-9.+-]/g, '');
      if (!text || text === '+' || text === '-' || text === '.' || !(strict ? intPattern : numericPattern).test(text)) {
        throw new Error('invalid number');
      }
      return (key === 'Seed' || Number.isInteger(fallback) ? parseInt(text, 10) : parseFloat(text)) as LlamaServerSettings[K];
    }
    if (key === 'FlashAttn') {
      const text = String(value ?? '').trim().toLowerCase();
      if (['true', 'yes', '1', 'enabled'].includes(text)) return 'on' as LlamaServerSettings[K];
      if (['false', 'no', '0', 'disabled'].includes(text)) return 'off' as LlamaServerSettings[K];
      return (text || fallback) as LlamaServerSettings[K];
    }
    return String(value ?? '').trim() as LlamaServerSettings[K];
  } catch {
    if (strict) throw new Error(`${String(key)} must be a ${target}`);
    return fallback;
  }
}

export function normalizeSettings(input?: Partial<LlamaServerSettings> | null, strict = false): LlamaServerSettings {
  const merged = { ...DEFAULT_SETTINGS, ...(input ?? {}) };
  const result: any = {};
  (Object.keys(DEFAULT_SETTINGS) as (keyof LlamaServerSettings)[]).forEach((key) => {
    result[key] = coerceSetting(key, merged[key], strict);
  });
  validateLlamaServerSettings(result as LlamaServerSettings);
  return result as LlamaServerSettings;
}

export function normalizeServerSettings(input?: Partial<ServerSettings> | Partial<LlamaServerSettings> | null, strict = false): ServerSettings {
  const merged = { ...DEFAULT_SERVER_SETTINGS, ...(input ?? {}) };
  const result: any = {};
  (Object.keys(DEFAULT_SERVER_SETTINGS) as (keyof ServerSettings)[]).forEach((key) => {
    result[key] = coerceSetting(key as keyof LlamaServerSettings, merged[key], strict);
  });
  validateServerSettings(result as ServerSettings);
  return result as ServerSettings;
}

export function normalizeModelProfileConfig(input?: Partial<ModelProfileConfig> | Partial<LlamaServerSettings> | null, strict = false): ModelProfileConfig {
  const merged = { ...DEFAULT_MODEL_PROFILE_CONFIG, ...(input ?? {}) };
  const result: any = {};
  (Object.keys(DEFAULT_MODEL_PROFILE_CONFIG) as (keyof ModelProfileConfig)[]).forEach((key) => {
    result[key] = coerceSetting(key as keyof LlamaServerSettings, merged[key], strict);
  });
  validateModelProfileConfig(result as ModelProfileConfig);
  return result as ModelProfileConfig;
}

export function validateLlamaServerSettings(settings: LlamaServerSettings): void {
  const ranges = {
    GpuLayers: [0, 999],
    NcpuMoe: [0, 999],
    CtxSize: [1, 1_048_576],
    Threads: [1, 512],
    BatchSize: [1, 1_048_576],
    UBatchSize: [1, 1_048_576],
    Temp: [0, 5],
    TopP: [0, 1],
    TopK: [0, 100_000],
    MinP: [0, 1],
    TypicalP: [0, 1],
    RepeatPenalty: [0, 10],
    RepeatLastN: [-1, 1_048_576],
    PresencePenalty: [-10, 10],
    FreqPenalty: [-10, 10],
    Port: [1, 65_535],
    Parallel: [1, 256],
    ModelsMax: [0, 1024],
    HealthCheckTimeoutMs: [100, 120_000],
    MainGpu: [-1, 1024],
    MaxTokens: [-1, 1_048_576],
    DryMultiplier: [0, 10],
    DryBase: [0, 10],
    DryAllowed: [0, 10_000],
    XtcProb: [0, 1],
    XtcThresh: [0, 1],
    Seed: [-1, 2_147_483_647],
  } as const;

  (Object.entries(ranges) as [keyof typeof ranges, readonly [number, number]][]).forEach(([key, [low, high]]) => {
    const value = settings[key] as number;
    if (value < low || value > high) {
      throw new Error(`${String(key)} must be between ${low} and ${high}`);
    }
  });

  if (!settings.Host.trim()) throw new Error('Host must not be empty');
  // Free-form values are allowed for llama.cpp forks/newer builds. UI datalists
  // provide known values, but validation should not block explicit overrides.
  if (!STARTUP_BEHAVIORS.includes(settings.StartupBehavior as never)) throw new Error(`StartupBehavior must be one of: ${STARTUP_BEHAVIORS.join(', ')}`);
  if (!PROCESS_STRATEGIES.includes(settings.ProcessStrategy as never)) throw new Error(`ProcessStrategy must be one of: ${PROCESS_STRATEGIES.join(', ')}`);
}

export function validateServerSettings(settings: ServerSettings): void {
  validateLlamaServerSettings({ ...DEFAULT_MODEL_PROFILE_CONFIG, ...settings });
}

export function validateModelProfileConfig(settings: ModelProfileConfig): void {
  validateLlamaServerSettings({ ...DEFAULT_SERVER_SETTINGS, ...settings });
}

export function diffServerSettings(settings: ServerSettings): Partial<ServerSettings> {
  const overrides: Partial<ServerSettings> = {};
  (Object.keys(DEFAULT_SERVER_SETTINGS) as (keyof ServerSettings)[]).forEach((key) => {
    if (!Object.is(settings[key], DEFAULT_SERVER_SETTINGS[key])) {
      (overrides as Record<keyof ServerSettings, ServerSettings[keyof ServerSettings]>)[key] = settings[key];
    }
  });
  return overrides;
}

export function diffModelProfileConfig(settings: ModelProfileConfig): Partial<ModelProfileConfig> {
  const overrides: Partial<ModelProfileConfig> = {};
  (Object.keys(DEFAULT_MODEL_PROFILE_CONFIG) as (keyof ModelProfileConfig)[]).forEach((key) => {
    if (!Object.is(settings[key], DEFAULT_MODEL_PROFILE_CONFIG[key])) {
      (overrides as Record<keyof ModelProfileConfig, ModelProfileConfig[keyof ModelProfileConfig]>)[key] = settings[key];
    }
  });
  return overrides;
}
