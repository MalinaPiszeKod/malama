import path from 'node:path';
import type { DeploymentConfig, InferenceDefaults, ModelProfileConfig, ServerSettings } from './types';
import { DEFAULT_INFERENCE_DEFAULTS, DEFAULT_MODEL_PROFILE_CONFIG, DEFAULT_SERVER_SETTINGS, normalizeModelProfileConfig, normalizeServerSettings } from './defaults.js';

export type LaunchArgMap = Record<string, string | number | boolean>;

export interface LaunchPlan {
  deployment: DeploymentConfig;
  args: LaunchArgMap;
  argv: string[];
  redactedArgs: LaunchArgMap;
  redactedArgv: string[];
  redactedCommandText: string;
}

function setValue(args: LaunchArgMap, flag: string, value: string | number | boolean | undefined | null): void {
  if (value === undefined || value === null || value === '') return;
  if (typeof value === 'boolean') {
    if (value) args[flag] = true;
    return;
  }
  args[flag] = value;
}

function setChangedValue<T extends string | number>(args: LaunchArgMap, flag: string, value: T, fallback: T): void {
  if (!Object.is(value, fallback)) setValue(args, flag, value);
}

export function buildServerStartupArgs(settings: Partial<ServerSettings>): LaunchArgMap {
  const s = normalizeServerSettings(settings);
  if (s.ProcessStrategy === 'multiple-managed-processes') {
    throw new Error('Multiple managed llama-server processes are not implemented in this launcher yet. Use the single server process strategy.');
  }
  const args: LaunchArgMap = {};

  setValue(args, 'host', s.Host);
  setValue(args, 'port', s.Port);
  setValue(args, 'api-key', s.ApiKey);
  if (!s.Webui) setValue(args, 'no-webui', true);
  if (s.Metrics) setValue(args, 'metrics', true);
  if (s.ContBatching) setValue(args, 'cont-batching', true);
  setChangedValue(args, 'threads', s.Threads, DEFAULT_SERVER_SETTINGS.Threads);
  setChangedValue(args, 'batch-size', s.BatchSize, DEFAULT_SERVER_SETTINGS.BatchSize);
  setChangedValue(args, 'ubatch-size', s.UBatchSize, DEFAULT_SERVER_SETTINGS.UBatchSize);
  setChangedValue(args, 'parallel', s.Parallel, DEFAULT_SERVER_SETTINGS.Parallel);
  if (s.LogVerbosity.trim()) setValue(args, 'verbosity', s.LogVerbosity.trim());

  if (s.MultiModel) {
    const modelsDir = s.ModelsDir.trim();
    if (!modelsDir) throw new Error('ModelsDir must be set when MultiModel is enabled');
    setValue(args, 'models-dir', modelsDir);
    setChangedValue(args, 'models-max', s.ModelsMax, DEFAULT_SERVER_SETTINGS.ModelsMax);
    setValue(args, s.ModelsAutoload ? 'models-autoload' : 'no-models-autoload', true);
  }

  return args;
}

export function buildModelLoadArgs(modelPath: string | null | undefined, profile: Partial<ModelProfileConfig>, server: Partial<ServerSettings> = {}): LaunchArgMap {
  const s = normalizeModelProfileConfig(profile);
  const serverSettings = normalizeServerSettings(server);
  const args: LaunchArgMap = {};

  if (!serverSettings.MultiModel) {
    if (!modelPath) throw new Error('Select a model or enable MultiModel with ModelsDir');
    setValue(args, 'model', modelPath);
  }

  setValue(args, 'alias', s.Alias.trim());
  setChangedValue(args, 'ctx-size', s.CtxSize, DEFAULT_MODEL_PROFILE_CONFIG.CtxSize);
  setChangedValue(args, 'n-gpu-layers', s.GpuLayers, DEFAULT_MODEL_PROFILE_CONFIG.GpuLayers);
  if (s.NcpuMoe > 0) setValue(args, 'n-cpu-moe', s.NcpuMoe);
  setChangedValue(args, 'cache-type-k', s.CacheTypeK, DEFAULT_MODEL_PROFILE_CONFIG.CacheTypeK);
  setChangedValue(args, 'cache-type-v', s.CacheTypeV, DEFAULT_MODEL_PROFILE_CONFIG.CacheTypeV);
  if (s.FlashAttn && s.FlashAttn !== 'auto') setValue(args, 'flash-attn', s.FlashAttn);
  if (s.SplitMode && s.SplitMode !== 'auto') setValue(args, 'split-mode', s.SplitMode);
  setValue(args, 'tensor-split', s.TensorSplit.trim());
  if (s.MainGpu >= 0) setValue(args, 'main-gpu', s.MainGpu);
  setValue(args, 'device', s.Device.trim());
  if (s.Mlock) setValue(args, 'mlock', true);
  if (s.NoMmap) setValue(args, 'no-mmap', true);
  setValue(args, s.Jinja ? 'jinja' : 'no-jinja', true);
  setValue(args, 'chat-template', s.ChatTemplate.trim());

  return args;
}

export function buildInferenceDefaultArgs(profile: Partial<InferenceDefaults>): LaunchArgMap {
  const s = normalizeModelProfileConfig(profile);
  const args: LaunchArgMap = {};
  setChangedValue(args, 'temp', s.Temp, DEFAULT_INFERENCE_DEFAULTS.Temp);
  setChangedValue(args, 'top-p', s.TopP, DEFAULT_INFERENCE_DEFAULTS.TopP);
  setChangedValue(args, 'top-k', s.TopK, DEFAULT_INFERENCE_DEFAULTS.TopK);
  setChangedValue(args, 'min-p', s.MinP, DEFAULT_INFERENCE_DEFAULTS.MinP);
  setChangedValue(args, 'typical-p', s.TypicalP, DEFAULT_INFERENCE_DEFAULTS.TypicalP);
  setChangedValue(args, 'repeat-penalty', s.RepeatPenalty, DEFAULT_INFERENCE_DEFAULTS.RepeatPenalty);
  setChangedValue(args, 'repeat-last-n', s.RepeatLastN, DEFAULT_INFERENCE_DEFAULTS.RepeatLastN);
  setChangedValue(args, 'presence-penalty', s.PresencePenalty, DEFAULT_INFERENCE_DEFAULTS.PresencePenalty);
  setChangedValue(args, 'frequency-penalty', s.FreqPenalty, DEFAULT_INFERENCE_DEFAULTS.FreqPenalty);
  if (s.Seed >= 0) setValue(args, 'seed', s.Seed);
  if (!s.Thinking) setValue(args, 'reasoning-format', 'none');
  else if (s.ReasoningFormat && s.ReasoningFormat !== 'auto') setValue(args, 'reasoning-format', s.ReasoningFormat);
  setValue(args, 'reasoning-budget', s.ReasoningBudget.trim());
  if (s.DryMultiplier > 0) {
    setValue(args, 'dry-multiplier', s.DryMultiplier);
    setValue(args, 'dry-base', s.DryBase);
    setValue(args, 'dry-allowed-length', s.DryAllowed);
    setValue(args, 'dry-penalty-last-n', -1);
  }
  if (s.XtcProb > 0) {
    setValue(args, 'xtc-probability', s.XtcProb);
    setValue(args, 'xtc-threshold', s.XtcThresh);
  }
  return args;
}

export function buildRequestDefaults(profile: Partial<ModelProfileConfig>): Record<string, unknown> {
  const s = normalizeModelProfileConfig(profile);
  const defaults: Record<string, unknown> = {
    temperature: s.Temp,
    top_p: s.TopP,
  };
  if (s.TopK !== DEFAULT_INFERENCE_DEFAULTS.TopK) defaults.top_k = s.TopK;
  if (s.MinP !== DEFAULT_INFERENCE_DEFAULTS.MinP) defaults.min_p = s.MinP;
  if (s.TypicalP !== DEFAULT_INFERENCE_DEFAULTS.TypicalP) defaults.typical_p = s.TypicalP;
  if (s.RepeatPenalty !== DEFAULT_INFERENCE_DEFAULTS.RepeatPenalty) defaults.repeat_penalty = s.RepeatPenalty;
  if (s.PresencePenalty !== DEFAULT_INFERENCE_DEFAULTS.PresencePenalty) defaults.presence_penalty = s.PresencePenalty;
  if (s.FreqPenalty !== DEFAULT_INFERENCE_DEFAULTS.FreqPenalty) defaults.frequency_penalty = s.FreqPenalty;
  if (s.MaxTokens >= 0) defaults.max_tokens = s.MaxTokens;
  if (s.Seed >= 0) defaults.seed = s.Seed;
  if (s.StopSequences.trim()) defaults.stop = s.StopSequences.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
  return defaults;
}

export function buildLaunchPlan(exePath: string, modelPath: string | null | undefined, server: Partial<ServerSettings>, profile: Partial<ModelProfileConfig>): LaunchPlan {
  const s = normalizeServerSettings(server);
  const p = normalizeModelProfileConfig(profile);
  const args = {
    ...buildServerStartupArgs(s),
    ...buildModelLoadArgs(modelPath, p, s),
    ...buildInferenceDefaultArgs(p),
  };
  const redactedArgs = redactArgs(args);
  const deployment: DeploymentConfig = s.MultiModel
    ? { mode: 'multi-model-repository', modelsDir: s.ModelsDir.trim() || (modelPath ? path.dirname(modelPath) : undefined), alias: p.Alias || undefined }
    : { mode: 'single-model-process', modelPath: modelPath || undefined, alias: p.Alias || undefined };
  return {
    deployment,
    args,
    argv: argsToList(args),
    redactedArgs,
    redactedArgv: argsToList(redactedArgs),
    redactedCommandText: commandString(exePath, redactedArgs),
  };
}

export function redactArgs(args: LaunchArgMap): LaunchArgMap {
  const redacted = { ...args };
  if ('api-key' in redacted && redacted['api-key']) redacted['api-key'] = '***';
  return redacted;
}

export function argsToList(args: LaunchArgMap): string[] {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(args)) {
    if (typeof value === 'boolean') {
      if (value) parts.push(`--${key}`);
    } else if (value !== undefined && value !== null && value !== '') {
      parts.push(`--${key}`, String(value));
    }
  }
  return parts;
}

export function commandString(exePath: string, args: LaunchArgMap): string {
  return [exePath, ...argsToList(args)].map(quoteArg).join(' ');
}

function quoteArg(part: string): string {
  if (!/[\s"]/.test(part)) return part;
  return `"${part.replace(/"/g, '\\"')}"`;
}
