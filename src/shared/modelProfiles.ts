import type { ModelInfo, ModelProfileConfig, PresetDefinition } from './types';
import { DEFAULT_MODEL_PROFILE_CONFIG, normalizeModelProfileConfig } from './defaults.js';

const FALLBACK_CONTEXT_LIMIT = 1_048_576;
const FALLBACK_GPU_LAYERS_LIMIT = 999;
const FALLBACK_CPU_MOE_LIMIT = 999;

export interface ModelProfileLimits {
  contextMax: number;
  gpuLayersMax: number;
  cpuMoeMax: number;
  contextFromMetadata: boolean;
  gpuLayersFromMetadata: boolean;
  cpuMoeFromMetadata: boolean;
  gpuLayersIncludeOutputLayer: boolean;
}

function metadataNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value !== 'string') return undefined;
  const numeric = Number(value.replace(/,/g, '').trim());
  return Number.isFinite(numeric) ? numeric : undefined;
}

function modelArchitecture(model: ModelInfo): string {
  return model.metadata.extra['gguf.general.architecture'] || '';
}

function firstMetadataNumberBySuffix(model: ModelInfo, suffix: string): number | undefined {
  return Object.entries(model.metadata.extra)
    .filter(([key]) => key.endsWith(suffix))
    .map(([, value]) => metadataNumber(value))
    .find((value): value is number => value !== undefined);
}

export function inferModelProfileLimits(model: ModelInfo): ModelProfileLimits {
  const arch = modelArchitecture(model);
  const contextMax = (arch ? metadataNumber(model.metadata.extra[`gguf.${arch}.context_length`]) : undefined)
    ?? firstMetadataNumberBySuffix(model, '.context_length');
  const expertCount = (arch ? metadataNumber(model.metadata.extra[`gguf.${arch}.expert_count`]) : undefined)
    ?? firstMetadataNumberBySuffix(model, '.expert_count');
  const transformerLayers = model.metadata.transformerLayers;
  const gpuLayersIncludeOutputLayer = model.metadata.outputLayer !== false && transformerLayers !== undefined;
  const gpuLayersMax = model.metadata.fullOffloadLayers
    ?? (transformerLayers !== undefined ? transformerLayers + (gpuLayersIncludeOutputLayer ? 1 : 0) : undefined);

  return {
    contextMax: Math.max(1, contextMax ?? FALLBACK_CONTEXT_LIMIT),
    gpuLayersMax: Math.max(0, gpuLayersMax ?? FALLBACK_GPU_LAYERS_LIMIT),
    cpuMoeMax: Math.max(0, expertCount ?? FALLBACK_CPU_MOE_LIMIT),
    contextFromMetadata: contextMax !== undefined,
    gpuLayersFromMetadata: gpuLayersMax !== undefined,
    cpuMoeFromMetadata: expertCount !== undefined,
    gpuLayersIncludeOutputLayer,
  };
}

export function inferModelProvider(model: ModelInfo): string {
  const source = [
    model.metadata.repository,
    model.metadata.baseModelRepository,
    model.metadata.baseModelRepositoryUrl,
    model.metadata.family,
    model.name,
    model.alias,
    ...model.metadata.tags,
  ].join(' ').toLowerCase();

  if (source.includes('qwen')) return 'Qwen';
  if (source.includes('llama') || source.includes('meta-llama')) return 'Llama';
  if (source.includes('gemma') || source.includes('google/')) return 'Gemma';
  if (source.includes('phi') || source.includes('microsoft/')) return 'Phi';
  if (source.includes('mistral') || source.includes('mixtral')) return 'Mistral';
  if (source.includes('deepseek')) return 'DeepSeek';
  return 'Generic GGUF';
}

function providerDefaults(provider: string): Partial<ModelProfileConfig> {
  switch (provider) {
    case 'Qwen':
      return { Temp: 1, TopP: 0.95, TopK: 20, MinP: 0, Thinking: true, PreserveThinking: true, ReasoningFormat: 'auto', Jinja: true };
    case 'DeepSeek':
      return { Temp: 0.6, TopP: 0.95, TopK: 40, MinP: 0, Thinking: true, PreserveThinking: true, ReasoningFormat: 'auto', Jinja: true };
    case 'Llama':
      return { Temp: 0.7, TopP: 0.9, TopK: 40, MinP: 0.05, Thinking: false, PreserveThinking: false, ReasoningFormat: 'none', Jinja: true };
    case 'Gemma':
      return { Temp: 1, TopP: 0.95, TopK: 64, MinP: 0.01, Thinking: false, PreserveThinking: false, ReasoningFormat: 'none', Jinja: true };
    case 'Phi':
      return { Temp: 0.7, TopP: 0.9, TopK: 50, MinP: 0, Thinking: false, PreserveThinking: false, ReasoningFormat: 'none', Jinja: true };
    case 'Mistral':
      return { Temp: 0.7, TopP: 0.9, TopK: 40, MinP: 0.05, Thinking: false, PreserveThinking: false, ReasoningFormat: 'none', Jinja: true };
    default:
      return { Temp: 0.8, TopP: 0.95, TopK: 40, MinP: 0.05, Thinking: false, PreserveThinking: false, ReasoningFormat: 'auto', Jinja: true };
  }
}

export function buildProviderBaseModelProfile(model: ModelInfo): ModelProfileConfig {
  const limits = inferModelProfileLimits(model);
  const provider = inferModelProvider(model);
  const contextTarget = Math.min(limits.contextMax, limits.contextMax >= 65_536 ? 65_536 : limits.contextMax);
  return normalizeModelProfileConfig({
    ...DEFAULT_MODEL_PROFILE_CONFIG,
    ...providerDefaults(provider),
    CtxSize: contextTarget,
    GpuLayers: Math.min(DEFAULT_MODEL_PROFILE_CONFIG.GpuLayers, limits.gpuLayersMax),
    NcpuMoe: Math.min(DEFAULT_MODEL_PROFILE_CONFIG.NcpuMoe, limits.cpuMoeMax),
    ChatTemplate: model.metadata.chatTemplate || DEFAULT_MODEL_PROFILE_CONFIG.ChatTemplate,
    SystemPrompt: model.metadata.systemPrompt || DEFAULT_MODEL_PROFILE_CONFIG.SystemPrompt,
  });
}

export function modelProfileFromPreset(preset: PresetDefinition): Partial<ModelProfileConfig> {
  const normalized = normalizeModelProfileConfig(preset.Settings);
  const profile: Partial<ModelProfileConfig> = {};
  (Object.keys(DEFAULT_MODEL_PROFILE_CONFIG) as (keyof ModelProfileConfig)[]).forEach((key) => {
    if (key in preset.Settings) {
      (profile as Record<keyof ModelProfileConfig, ModelProfileConfig[keyof ModelProfileConfig]>)[key] = normalized[key];
    }
  });
  return profile;
}

export function buildEffectiveModelProfile(
  model: ModelInfo,
  savedProfile?: Partial<ModelProfileConfig>,
  draftProfile?: Partial<ModelProfileConfig>
): ModelProfileConfig {
  return normalizeModelProfileConfig({
    ...buildProviderBaseModelProfile(model),
    ...(model.configSettings ?? {}),
    ...(savedProfile ?? {}),
    ...(draftProfile ?? {}),
  });
}

export function clampModelProfileToLimits(model: ModelInfo, profile: Partial<ModelProfileConfig>): ModelProfileConfig {
  const limits = inferModelProfileLimits(model);
  const normalized = normalizeModelProfileConfig(profile);
  return {
    ...normalized,
    CtxSize: Math.min(Math.max(1024, normalized.CtxSize), limits.contextMax),
    GpuLayers: Math.min(Math.max(0, normalized.GpuLayers), limits.gpuLayersMax),
    NcpuMoe: Math.min(Math.max(0, normalized.NcpuMoe), limits.cpuMoeMax),
  };
}
