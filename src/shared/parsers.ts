import fs from 'node:fs';
import path from 'node:path';
import type { DeploymentEstimate, LlamaServerSettings, ModelInfo, ModelMetadata, ModelRegistryEntry, PresetDefinition } from './types';
import { DEFAULT_SETTINGS } from './defaults';

export function parseKeyValueText(text: string): Record<string, string> {
  return text.split(/\r?\n/).reduce<Record<string, string>>((acc, rawLine) => {
    const line = rawLine.trim();
    if (!line || line.startsWith('#') || !line.includes('=')) return acc;
    const [key, ...rest] = line.split('=');
    const normalizedKey = (key ?? '').trim();
    if (!normalizedKey) return acc;
    acc[normalizedKey] = rest.join('=').trim();
    return acc;
  }, {});
}

export function parseRegistry(text: string): ModelRegistryEntry[] {
  return text.split(/\r?\n/).flatMap((rawLine) => {
    const line = rawLine.trim();
    if (!line || line.startsWith('#') || !line.includes('=')) return [];
    const [alias, ...rest] = line.split('=');
    const value = rest.join('=').trim();
    const normalizedAlias = (alias ?? '').trim();
    if (!normalizedAlias || !value) return [];
    return [{ alias: normalizedAlias, path: value, source: 'registry' as const }];
  });
}

export function parsePreset(filePath: string, text: string): PresetDefinition | null {
  try {
    const data = JSON.parse(text) as Partial<PresetDefinition>;
    if (!data || typeof data.Name !== 'string' || typeof data.Description !== 'string') return null;
    return {
      Name: data.Name,
      Description: data.Description,
      ...(typeof data.Created === 'string' ? { Created: data.Created } : {}),
      File: path.basename(filePath),
      Settings: typeof data.Settings === 'object' && data.Settings ? (data.Settings as Partial<LlamaServerSettings>) : {},
    };
  } catch {
    return null;
  }
}

export function parseModelConfig(filePath: string, text: string): { alias: string; modelPath: string; metadata: ModelMetadata; settings: Partial<LlamaServerSettings> } {
  const kv = parseKeyValueText(text);
  const settings: any = {};
  const metadata: ModelMetadata = {
    description: '',
    systemPrompt: kv.CHAT_SYS_PROMPT ?? '',
    chatTemplate: kv.CHAT_TEMPLATE ?? '',
    ...(kv.HOST ? { host: kv.HOST } : {}),
    ...(kv.PORT ? { port: Number.parseInt(kv.PORT, 10) } : {}),
    configPath: filePath,
    ...(kv.TRANSFORMER_LAYERS ? { transformerLayers: Number.parseInt(kv.TRANSFORMER_LAYERS, 10) } : {}),
    ...(kv.OUTPUT_LAYER ? { outputLayer: ['on', 'true', '1'].includes(kv.OUTPUT_LAYER.toLowerCase()) } : {}),
    ...(kv.FULL_OFFLOAD_LAYERS ? { fullOffloadLayers: Number.parseInt(kv.FULL_OFFLOAD_LAYERS, 10) } : {}),
    extra: {},
  };

  const mapping: Record<string, keyof LlamaServerSettings> = {
    N_GPU_LAYERS: 'GpuLayers',
    GPU_LAYERS: 'GpuLayers',
    THREADS: 'Threads',
    CPU_MOE: 'NcpuMoe',
    N_CPU_MOE: 'NcpuMoe',
    BATCH_SIZE: 'BatchSize',
    UBATCH_SIZE: 'UBatchSize',
    CTX_SIZE: 'CtxSize',
    TEMPERATURE: 'Temp',
    TEMP: 'Temp',
    TOP_P: 'TopP',
    TOP_K: 'TopK',
    MIN_P: 'MinP',
    TYPICAL_P: 'TypicalP',
    REPEAT_PENALTY: 'RepeatPenalty',
    REPEAT_LAST_N: 'RepeatLastN',
    PRESENCE_PENALTY: 'PresencePenalty',
    FREQUENCY_PENALTY: 'FreqPenalty',
    FREQ_PENALTY: 'FreqPenalty',
    CACHE_TYPE_K: 'CacheTypeK',
    CACHE_TYPE_V: 'CacheTypeV',
    FLASH_ATTN: 'FlashAttn',
    SPLIT_MODE: 'SplitMode',
    TENSOR_SPLIT: 'TensorSplit',
    HOST: 'Host',
    PORT: 'Port',
    PARALLEL: 'Parallel',
    THINKING: 'Thinking',
    PRESERVE_THINKING: 'PreserveThinking',
    REASONING_FORMAT: 'ReasoningFormat',
    REASONING_BUDGET: 'ReasoningBudget',
    JINJA: 'Jinja',
    WEBUI: 'Webui',
    METRICS: 'Metrics',
    CONT_BATCHING: 'ContBatching',
    DRY_MULTIPLIER: 'DryMultiplier',
    DRY_BASE: 'DryBase',
    DRY_ALLOWED: 'DryAllowed',
    XTC_PROB: 'XtcProb',
    XTC_THRESH: 'XtcThresh',
    SEED: 'Seed',
    API_KEY: 'ApiKey',
    ALIAS: 'Alias',
    MODELS_DIR: 'ModelsDir',
    MODELS_MAX: 'ModelsMax',
    MODELS_AUTOLOAD: 'ModelsAutoload',
    MULTI_MODEL: 'MultiModel',
    MLOCK: 'Mlock',
    NO_MMAP: 'NoMmap',
  };

  Object.entries(kv).forEach(([key, value]) => {
    if (key === 'MODEL_PATH') {
      return;
    }
    if (key === 'ALIAS') {
      settings.Alias = value;
      return;
    }
    if (key === 'NO_WEBUI') {
      settings.Webui = !['on', 'true', '1', 'yes'].includes(value.toLowerCase());
      return;
    }
    if (key === 'CPU_MOE') {
      if (!['on', 'true', '1', 'yes'].includes(value.toLowerCase())) settings.NcpuMoe = 0;
      return;
    }
    if (key in mapping) {
      const mapped = mapping[key as keyof typeof mapping];
      if (mapped && typeof DEFAULT_SETTINGS[mapped] === 'boolean') {
        settings[mapped] = ['on', 'true', '1', 'yes'].includes(value.toLowerCase());
      } else if (mapped && typeof DEFAULT_SETTINGS[mapped] === 'number') {
        settings[mapped] = Number.isFinite(Number(value)) ? Number(value) : DEFAULT_SETTINGS[mapped];
      } else if (mapped) {
        settings[mapped] = value;
      }
    } else {
      metadata.extra[key] = value;
    }
  });

  return {
    alias: kv.ALIAS || path.basename(filePath, path.extname(filePath)),
    modelPath: kv.MODEL_PATH || '',
    metadata,
    settings,
  };
}

export function detectQuant(pathOrName: string): string {
  const name = path.basename(pathOrName).toUpperCase();
  if (name.includes('Q6_K')) return 'Q6_K';
  if (name.includes('Q8_0')) return 'Q8_0';
  if (name.includes('Q5_K')) return 'Q5_K_M';
  if (name.includes('Q4_K')) return 'Q4_K_M';
  if (name.includes('UD-Q3_XXS')) return 'UD-Q3_XXS';
  return 'Unknown';
}

export function fileSizeGb(filePath: string): number {
  try {
    return Math.round((fs.statSync(filePath).size / 1024 / 1024 / 1024) * 10) / 10;
  } catch {
    return 0;
  }
}

export function estimateDeployment(sizeGb: number, ctxSize: number, gpuLayers: number): DeploymentEstimate {
  const kvCacheGb = Math.max(0.25, Math.min(32, (ctxSize / 16384) * 0.6));
  const modelGb = Math.max(0, sizeGb);
  const totalGb = Math.round((modelGb + kvCacheGb + Math.max(0, gpuLayers) * 0.02) * 10) / 10;
  const notes = [
    gpuLayers > 0 ? `${gpuLayers} GPU layers` : 'CPU-only',
    ctxSize > 65536 ? 'large context footprint' : 'standard context footprint',
  ];
  return { modelGb, kvCacheGb: Math.round(kvCacheGb * 10) / 10, totalGb, notes };
}
