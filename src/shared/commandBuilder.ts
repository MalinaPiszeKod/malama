import path from 'node:path';
import type { LlamaServerSettings } from './types';
import { normalizeSettings } from './defaults';

export type LaunchArgMap = Record<string, string | number | boolean>;

export function buildCommandArgs(modelPath: string | null | undefined, settings: Partial<LlamaServerSettings>): LaunchArgMap {
  const s = normalizeSettings(settings);
  const args: LaunchArgMap = {};

  if (s.MultiModel) {
    const modelsDir = String(s.ModelsDir || '').trim() || (modelPath ? path.dirname(modelPath) : '');
    if (!modelsDir) throw new Error('ModelsDir must be set when MultiModel is enabled');
    args['models-dir'] = modelsDir;
    args['models-max'] = s.ModelsMax;
    args['models-autoload'] = s.ModelsAutoload;
  } else {
    if (!modelPath) throw new Error('Select a model or enable MultiModel with ModelsDir');
    args.model = modelPath;
  }

  args['n-gpu-layers'] = s.GpuLayers;
  if (s.NcpuMoe > 0) args['n-cpu-moe'] = s.NcpuMoe;
  args['ctx-size'] = s.CtxSize;
  args['batch-size'] = s.BatchSize;
  args['ubatch-size'] = s.UBatchSize;
  args.threads = s.Threads;
  if (s.CacheTypeK) args['cache-type-k'] = s.CacheTypeK;
  if (s.CacheTypeV) args['cache-type-v'] = s.CacheTypeV;
  args['flash-attn'] = s.FlashAttn ? 'on' : 'off';
  if (s.SplitMode && s.SplitMode !== 'auto') args['split-mode'] = s.SplitMode;
  if (s.TensorSplit > 0) args['tensor-split'] = s.TensorSplit;
  if (s.Mlock) args.mlock = true;
  if (s.NoMmap) args['no-mmap'] = true;
  if (s.Jinja) args.jinja = true;
  if (s.Thinking) {
    if (s.ReasoningFormat === 'force' || s.ReasoningFormat === 'none') args['reasoning-format'] = s.ReasoningFormat;
  } else {
    args['reasoning-format'] = 'none';
  }
  if (s.ReasoningBudget) args['reasoning-budget'] = s.ReasoningBudget;
  args.temp = s.Temp;
  args['top-p'] = s.TopP;
  args['top-k'] = s.TopK;
  args['min-p'] = s.MinP;
  args['repeat-penalty'] = s.RepeatPenalty;
  args['repeat-last-n'] = s.RepeatLastN;
  args['presence-penalty'] = s.PresencePenalty;
  args['frequency-penalty'] = s.FreqPenalty;
  if (s.TypicalP !== 1) args['typical-p'] = s.TypicalP;
  if (s.Seed >= 0) args.seed = s.Seed;
  if (s.DryMultiplier > 0) {
    args['dry-multiplier'] = s.DryMultiplier;
    args['dry-base'] = s.DryBase;
    args['dry-allowed-length'] = s.DryAllowed;
    args['dry-penalty-last-n'] = -1;
  }
  if (s.XtcProb > 0) {
    args['xtc-probability'] = s.XtcProb;
    args['xtc-threshold'] = s.XtcThresh;
  }
  args.host = s.Host;
  args.port = s.Port;
  if (s.Parallel > 1) args.parallel = s.Parallel;
  if (s.Alias) args.alias = s.Alias;
  if (s.ApiKey) args['api-key'] = s.ApiKey;
  if (!s.Webui) args['no-webui'] = true;
  if (s.Metrics) args.metrics = true;
  if (s.ContBatching) args['cont-batching'] = true;
  return args;
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
  return [exePath, ...argsToList(args)].map((part) => (/\s/.test(part) ? `"${part}"` : part)).join(' ');
}
