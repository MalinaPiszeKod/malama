import type { AppActions, AppState } from '../state.js';
import { badge, button, card, el, input, select, metricTile, tabs, tree } from '../components.js';
import { findSelectedModel } from '../state.js';
import { DEFAULT_MODEL_PROFILE_CONFIG } from '../../shared/defaults.js';
import { buildEffectiveModelProfile, buildProviderBaseModelProfile, clampModelProfileToLimits, inferModelProfileLimits, inferModelProvider, modelProfileFromPreset } from '../../shared/modelProfiles.js';

type DeployTab = 'modelInfo' | 'deployment' | 'inference';
type SlotSnapshot = AppState['metrics']['server']['slots'][number];
type ModelProfileKey = keyof NonNullable<AppState['modelProfiles'][string]>;

let activeDeployTab: DeployTab = 'modelInfo';
let runningCardExpanded = false;
let cleanupDeployResizeObserver: (() => void) | undefined;
const deployPanelWidths = {
  left: 0,
  right: 0,
};
let deployLastRootFontSize = 0;

const MODEL_FIELD_HELP: Partial<Record<ModelProfileKey, string>> = {
  Alias: 'Served model name sent to llama-server --alias and used by OpenAI-compatible requests.',
  ChatTemplate: 'Override the model chat template. Leave empty to use GGUF tokenizer.chat_template metadata.',
  CtxSize: 'Prompt/KV context size. Slider uses GGUF context length when known; number box can override freely.',
  GpuLayers: 'Number of model layers to offload to GPU. Full offload can include the output layer when supported.',
  NcpuMoe: 'MoE expert/layer CPU offload setting for supported MoE builds. Leave low/zero unless tuning MoE memory.',
  FlashAttn: 'Flash Attention mode. Auto lets llama.cpp decide. On can improve speed and reduce memory traffic on supported GPUs; off can help debug compatibility issues.',
  CacheTypeK: 'KV cache K precision. f16 is safest. q8/q4/q5 use less memory so longer context or more parallel users may fit, but output quality/stability can change slightly.',
  CacheTypeV: 'KV cache V precision. f16 is safest. Quantized values reduce KV cache memory and may help fit large contexts, with possible speed/quality trade-offs.',
  Mlock: 'Pin model memory in RAM. Can reduce paging but may hurt the OS if RAM is tight.',
  NoMmap: 'Disable memory mapping. Usually keep off; mmap lets the OS page model files efficiently.',
  SplitMode: 'Multi-GPU split strategy. layer is llama.cpp default and spreads layers/KV across GPUs. none uses one GPU only. row splits rows and is an advanced tuning mode.',
  TensorSplit: 'Manual multi-GPU tensor split proportions, e.g. 3,2. Leave empty for automatic split.',
  MainGpu: 'Primary GPU index for small tensors/scratch buffers in multi-GPU setups.',
  Device: 'Device selector for llama.cpp builds that expose --device. Leave empty for default device selection.',
  Jinja: 'Use the model chat template engine. This turns OpenAI-style messages into the exact prompt format the model was trained for. Keep on unless using raw prompts or a custom non-template workflow.',
  MaxTokens: 'Request-time max output tokens. -1 means server/model default or unlimited depending endpoint.',
  StopSequences: 'One stop sequence per line for request defaults.',
  Temp: 'Sampling temperature. Higher is more random; lower is more deterministic.',
  TopK: 'Limit sampling to top K tokens. 0 disables in many samplers; 40 is common llama-server default.',
  TopP: 'Nucleus sampling probability mass. 0.9-0.95 is common.',
  MinP: 'Minimum probability cutoff relative to best token. Useful alternative to top-p for modern models.',
  TypicalP: 'Typical sampling cutoff. 1 disables typical sampling.',
  RepeatPenalty: 'Penalty for repeating recent tokens. Values near 1.0 are neutral.',
  RepeatLastN: 'How many recent tokens repeat penalty considers. 64 is common; -1 can mean full context in llama.cpp.',
  PresencePenalty: 'OpenAI-style penalty for tokens already present. Positive values discourage repetition/topic reuse.',
  FreqPenalty: 'OpenAI-style penalty proportional to token frequency.',
  Seed: 'Random seed. -1 means random seed.',
  Thinking: 'Launcher request/default hint for reasoning-capable models. Off maps reasoning format to none where supported.',
  PreserveThinking: 'Keep reasoning/thinking content in outputs when model/template exposes it.',
  ReasoningFormat: 'Controls how hidden/thinking text is returned. auto follows the template. none leaves thoughts in normal content. deepseek modes extract thinking into a reasoning field for compatible models.',
  ReasoningBudget: 'Optional token budget for model reasoning when supported by the server/template.',
  DryMultiplier: 'DRY repetition penalty multiplier. 0 disables DRY sampling.',
  DryBase: 'DRY sampling base. Only used when DRY multiplier is > 0.',
  DryAllowed: 'Allowed repeated length before DRY penalty applies.',
  XtcProb: 'XTC sampler probability. 0 disables XTC.',
  XtcThresh: 'XTC threshold used when XTC probability is > 0.',
};

const MODEL_SUGGESTIONS: Partial<Record<ModelProfileKey, string[]>> = {
  CacheTypeK: ['f16', 'q8_0', 'q4_0', 'q4_1', 'q5_0', 'q5_1', 'bf16', 'f32'],
  CacheTypeV: ['f16', 'q8_0', 'q4_0', 'q4_1', 'q5_0', 'q5_1', 'bf16', 'f32'],
  FlashAttn: ['auto', 'on', 'off'],
  SplitMode: ['auto', 'none', 'layer', 'row'],
  TensorSplit: ['', '1,1', '3,2', '2,1'],
  Device: ['', 'CUDA0', 'CUDA1'],
  ReasoningFormat: ['auto', 'none', 'deepseek', 'deepseek-legacy'],
};

function modelFieldTooltip(key: ModelProfileKey): string | undefined {
  const help = MODEL_FIELD_HELP[key];
  if (!help) return undefined;
  return `${help} Default: ${String(DEFAULT_MODEL_PROFILE_CONFIG[key])}.`;
}

function rootFontSize(): number {
  const rootFontSize = Number.parseFloat(getComputedStyle(document.documentElement).fontSize);
  return Number.isFinite(rootFontSize) ? rootFontSize : 16;
}

function remToCssPixels(value: number): number {
  return rootFontSize() * value;
}

function deployResizeHandleWidth(): number { return remToCssPixels(0.625); }
function deployCenterMinWidth(): number { return remToCssPixels(24); }
function deployPanelMinWidth(): number { return remToCssPixels(16); }

function ensureDeployWidthDefaults(): void {
  if (!deployPanelWidths.left) deployPanelWidths.left = remToCssPixels(19);
  if (!deployPanelWidths.right) deployPanelWidths.right = remToCssPixels(23);
  deployLastRootFontSize = deployLastRootFontSize || rootFontSize();
}

function syncDeployWidthsToRootFont(): void {
  const nextRootFontSize = rootFontSize();
  if (!deployLastRootFontSize) {
    deployLastRootFontSize = nextRootFontSize;
    return;
  }
  if (Math.abs(nextRootFontSize - deployLastRootFontSize) < 0.01) return;
  const scale = nextRootFontSize / deployLastRootFontSize;
  deployPanelWidths.left *= scale;
  deployPanelWidths.right *= scale;
  deployLastRootFontSize = nextRootFontSize;
}

function formatNumber(value: number): string {
  return Number.isFinite(value) ? value.toFixed(1) : '0.0';
}

function formatText(value: unknown): string {
  if (value === undefined || value === null) return '—';
  if (typeof value === 'string') return value.trim() ? value : '—';
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : '—';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (Array.isArray(value)) return value.length ? value.map((entry) => formatText(entry)).join(', ') : '—';
  return String(value);
}

function toLabel(value: string): string {
  return value
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/_/g, ' ')
    .replace(/\./g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function renderField(label: string, value: string): HTMLElement {
  const item = el('div', 'deploy-kv-item');
  const valueNode = el('div', 'deploy-kv-value', value);
  valueNode.title = value;
  item.append(el('div', 'deploy-kv-label', label), valueNode);
  return item;
}

function renderFieldGrid(rows: Array<[string, string]>, emptyText = 'No values available.'): HTMLElement {
  const grid = el('div', 'deploy-kv-grid');
  if (!rows.length) {
    grid.append(el('div', 'muted', emptyText));
    return grid;
  }
  rows.forEach(([label, value]) => grid.append(renderField(label, value)));
  return grid;
}

function renderGroup(title: string, body: HTMLElement): HTMLElement {
  const group = el('section', 'deploy-group');
  group.append(el('h4', '', title), body);
  return group;
}

function selectedProfile(state: AppState, model: NonNullable<ReturnType<typeof findSelectedModel>>): NonNullable<AppState['modelProfiles'][string]> {
  return buildEffectiveModelProfile(model, state.modelProfiles[model.id], state.modelProfileDrafts[model.id]);
}

function setModelSetting<K extends keyof NonNullable<AppState['modelProfiles'][string]>>(actions: AppActions, modelId: string, key: K, value: NonNullable<AppState['modelProfiles'][string]>[K]): void {
  actions.setModelProfileField(modelId, key as never, value as never);
}

function toNumber(value: unknown, fallback = 0): number {
  const numeric = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function toBoolean(value: unknown): boolean {
  return value === true || value === 'true';
}


function renderReadOnlyTextArea(label: string, value: string, rows = 6): HTMLElement {
  const wrap = el('label', 'field');
  wrap.append(el('span', 'field-label', label));
  const node = document.createElement('textarea');
  node.className = 'field-input textarea deploy-readonly';
  node.readOnly = true;
  node.rows = rows;
  node.value = value || '—';
  wrap.append(node);
  return wrap;
}

function renderModelTextField<K extends keyof NonNullable<AppState['modelProfiles'][string]>>(
  state: AppState,
  actions: AppActions,
  model: NonNullable<ReturnType<typeof findSelectedModel>>,
  key: K,
  label: string
): HTMLElement {
  const profile = selectedProfile(state, model);
  return input(label, String(profile[key] ?? ''), (value) => setModelSetting(actions, model.id, key, value as NonNullable<AppState['modelProfiles'][string]>[K]), 'text', {
    tooltip: modelFieldTooltip(key as ModelProfileKey),
    suggestions: MODEL_SUGGESTIONS[key as ModelProfileKey],
  });
}

function renderModelChoiceOverrideField<K extends keyof NonNullable<AppState['modelProfiles'][string]>>(
  state: AppState,
  actions: AppActions,
  model: NonNullable<ReturnType<typeof findSelectedModel>>,
  key: K,
  label: string,
  values: string[]
): HTMLElement {
  const profile = selectedProfile(state, model);
  const current = String(profile[key] ?? '');
  return input(label, current, (value) => {
    setModelSetting(actions, model.id, key, value as NonNullable<AppState['modelProfiles'][string]>[K]);
  }, 'text', {
    tooltip: modelFieldTooltip(key as ModelProfileKey),
    suggestions: values,
  });
}

function renderModelNumberField<K extends keyof NonNullable<AppState['modelProfiles'][string]>>(
  state: AppState,
  actions: AppActions,
  model: NonNullable<ReturnType<typeof findSelectedModel>>,
  key: K,
  label: string
): HTMLElement {
  const profile = selectedProfile(state, model);
  return input(label, String(toNumber(profile[key], 0)), (value) => {
    const numeric = Number(value);
    if (Number.isFinite(numeric)) setModelSetting(actions, model.id, key, numeric as NonNullable<AppState['modelProfiles'][string]>[K]);
  }, 'number', { tooltip: modelFieldTooltip(key as ModelProfileKey) });
}

function renderModelToggleField<K extends keyof NonNullable<AppState['modelProfiles'][string]>>(
  state: AppState,
  actions: AppActions,
  model: NonNullable<ReturnType<typeof findSelectedModel>>,
  key: K,
  label: string,
  description = ''
): HTMLElement {
  const profile = selectedProfile(state, model);
  const wrap = select(label, String(toBoolean(profile[key])), [
    { value: 'true', label: 'On' },
    { value: 'false', label: 'Off' },
  ], (value) => setModelSetting(actions, model.id, key, (value === 'true') as NonNullable<AppState['modelProfiles'][string]>[K]), { tooltip: modelFieldTooltip(key as ModelProfileKey) });
  if (description) wrap.append(el('div', 'deploy-field-note', description));
  return wrap;
}

function renderModelSliderField<K extends keyof NonNullable<AppState['modelProfiles'][string]>>(
  state: AppState,
  actions: AppActions,
  model: NonNullable<ReturnType<typeof findSelectedModel>>,
  key: K,
  label: string,
  min: number,
  max: number,
  step: number,
  suffix = ''
): HTMLElement {
  const profile = selectedProfile(state, model);
  const current = toNumber(profile[key], min);
  const sliderValue = Math.min(max, Math.max(min, current));
  const wrap = el('label', 'field deploy-slider-field');
  const tooltip = modelFieldTooltip(key as ModelProfileKey);
  if (tooltip) wrap.title = tooltip;
  const head = el('div', 'deploy-slider-head');
  const valueLabel = el('span', 'deploy-slider-value', `${current}${suffix}`);
  const labelNode = el('span', 'field-label', label);
  if (tooltip) {
    labelNode.title = tooltip;
    labelNode.append(el('span', 'field-help', ' ?'));
  }
  head.append(labelNode, valueLabel);
  const controls = el('div', 'deploy-slider-controls');
  const range = document.createElement('input');
  range.type = 'range'; range.min = String(min); range.max = String(max); range.step = String(step); range.value = String(sliderValue); range.className = 'deploy-slider';
  range.dataset.focusKey = `range:${model.id}:${String(key)}`;
  const number = document.createElement('input');
  number.type = 'number'; number.step = String(step); number.value = String(current); number.className = 'field-input deploy-number';
  number.dataset.focusKey = `number:${model.id}:${String(key)}`;
  const syncFromSlider = (next: number) => {
    if (!Number.isFinite(next)) return;
    const clamped = Math.min(max, Math.max(min, next));
    range.value = String(clamped); number.value = String(clamped); valueLabel.textContent = `${clamped}${suffix}`;
    setModelSetting(actions, model.id, key, clamped as NonNullable<AppState['modelProfiles'][string]>[K]);
  };
  const syncFromNumber = (next: number) => {
    if (!Number.isFinite(next)) return;
    const sliderClamped = Math.min(max, Math.max(min, next));
    range.value = String(sliderClamped);
    valueLabel.textContent = `${next}${suffix}`;
    setModelSetting(actions, model.id, key, next as NonNullable<AppState['modelProfiles'][string]>[K]);
  };
  range.addEventListener('input', () => syncFromSlider(Number(range.value)));
  number.addEventListener('input', () => syncFromNumber(Number(number.value)));
  controls.append(range, number);
  wrap.append(head, controls);
  return wrap;
}

function renderGroupCard(title: string, detail: string, children: HTMLElement[]): HTMLElement {
  const group = card(title, 'deploy-form-group');
  if (detail) group.append(el('p', 'muted', detail));
  children.forEach((child) => group.append(child));
  return group;
}

function renderModelPresetChoice(state: AppState, actions: AppActions, model: NonNullable<ReturnType<typeof findSelectedModel>>): HTMLElement {
  const provider = inferModelProvider(model);
  const options = [
    { value: 'custom', label: 'Custom / current' },
    { value: 'provider-base', label: `${provider} optimum` },
    ...state.presets.map((preset) => ({ value: `preset:${preset.File || preset.Name}`, label: preset.Name })),
  ];
  return select('Preset', 'custom', options, (value) => {
    if (value === 'provider-base') {
      actions.setModelProfile(model.id, clampModelProfileToLimits(model, { ...buildProviderBaseModelProfile(model), ...(model.configSettings ?? {}) }));
      return;
    }
    if (value.startsWith('preset:')) {
      const id = value.slice('preset:'.length);
      const preset = state.presets.find((entry) => (entry.File || entry.Name) === id);
      if (!preset) return;
      actions.setModelProfile(model.id, clampModelProfileToLimits(model, { ...selectedProfile(state, model), ...modelProfileFromPreset(preset) }));
    }
  }, { tooltip: 'Apply a provider/model baseline or saved JSON preset to this model draft. You can still override every field afterward.' });
}

function isActiveSlot(slot: SlotSnapshot): boolean {
  const state = slot.state.toLowerCase();
  return !['idle', 'waiting', 'queued', 'empty', 'free', 'off'].some((value) => state.includes(value));
}

function findRunningSlot(state: AppState): SlotSnapshot | undefined {
  return state.metrics.server.slots.find((slot) => isActiveSlot(slot)) || state.metrics.server.slots[0];
}

function formatTokens(value?: number): string {
  return typeof value === 'number' && Number.isFinite(value) ? String(value) : '—';
}

function formatTps(value?: number): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(1)} tps` : '—';
}

function deriveSlotStatus(slot?: SlotSnapshot): { title: string; detail: string } {
  if (!slot) return { title: 'waiting for metrics', detail: '—' };

  const state = slot.state.toLowerCase();
  const tps = formatTps(slot.speedTps);
  const promptTotal = typeof slot.tokens === 'number' ? slot.tokens : undefined;
  const promptDone = typeof slot.promptTokens === 'number' ? slot.promptTokens : undefined;
  const genTotal = typeof slot.tokens === 'number' ? slot.tokens : undefined;
  const genDone = typeof slot.generationTokens === 'number' ? slot.generationTokens : undefined;

  if (state.includes('prompt') || state.includes('eval')) {
    const percent = promptTotal && promptDone !== undefined ? `${Math.max(0, Math.min(100, Math.round((promptDone / promptTotal) * 100)))}%` : '—';
    return { title: 'evaluating prompt', detail: [percent, tps].filter((item) => item !== '—').join(' · ') || '—' };
  }

  if (state.includes('gen') || state.includes('decode') || state.includes('generation')) {
    const tokenCount = genTotal ?? genDone;
    return { title: 'generating', detail: [formatTokens(tokenCount), tps].filter((item) => item !== '—').join(' · ') || '—' };
  }

  if (state.includes('idle')) return { title: 'idle', detail: '—' };

  return { title: slot.state, detail: tps !== '—' ? tps : '—' };
}

function renderEvaluationStatus(slot?: SlotSnapshot): string {
  if (!slot) return 'waiting for metrics';
  const state = slot.state.toLowerCase();
  const promptTotal = typeof slot.tokens === 'number' ? slot.tokens : undefined;
  const promptDone = typeof slot.promptTokens === 'number' ? slot.promptTokens : undefined;
  const percent = promptTotal && promptDone !== undefined ? `${Math.max(0, Math.min(100, Math.round((promptDone / promptTotal) * 100)))}%` : '—';
  const tps = formatTps(slot.speedTps);
  if (state.includes('prompt') || state.includes('eval')) return `${percent} · ${tps}`;
  return promptDone !== undefined ? `${percent} · ${tps}` : '—';
}

function renderGenerationStatus(slot?: SlotSnapshot): string {
  if (!slot) return 'waiting for metrics';
  const state = slot.state.toLowerCase();
  const generated = typeof slot.generationTokens === 'number' ? slot.generationTokens : undefined;
  const fallbackTokens = typeof slot.tokens === 'number' ? slot.tokens : undefined;
  const tokens = generated ?? (state.includes('gen') || state.includes('decode') || state.includes('generation') ? fallbackTokens : undefined);
  const tokenText = tokens !== undefined ? `${tokens} tokens` : '—';
  const tps = formatTps(slot.speedTps);
  return tokens !== undefined || state.includes('gen') || state.includes('decode') || state.includes('generation') ? `${tokenText} · ${tps}` : '—';
}

function renderStatusRows(slot?: SlotSnapshot): Array<[string, string]> {
  return [
    ['State', slot?.state || 'waiting for metrics'],
    ['Evaluating prompt', renderEvaluationStatus(slot)],
    ['Generating', renderGenerationStatus(slot)],
  ];
}

function renderRunningDeploymentCard(state: AppState, actions: AppActions, model: ReturnType<typeof findSelectedModel>): HTMLElement {
  const slot = findRunningSlot(state);
  const title = state.launcher.modelName || model?.name || 'Running deployment';
  const cardNode = el('article', `deploy-deployment-card ${runningCardExpanded ? 'expanded' : 'collapsed'}`.trim());
  const header = el('div', 'deploy-deployment-header');
  const titleBlock = el('div', 'deploy-deployment-title');
  titleBlock.append(
    el('div', 'deploy-deployment-name', title),
    el('div', 'deploy-deployment-meta', model ? `${model.alias} · ${model.quant} · ${formatNumber(model.sizeGb)} GB` : 'No model metadata available.'),
  );
  const status = deriveSlotStatus(slot);
  const toggle = el('button', 'button secondary deploy-expand-toggle', runningCardExpanded ? 'Collapse' : 'Expand') as HTMLButtonElement;
  toggle.type = 'button';
  toggle.addEventListener('click', () => {
    runningCardExpanded = !runningCardExpanded;
    actions.setSelectedModel(state.selectedModelId);
  });
  header.append(titleBlock, badge(state.launcher.running ? 'Live' : 'Offline', state.launcher.running ? 'secondary' : ''), toggle);

  const collapsed = el('div', 'deploy-deployment-collapsed');
  collapsed.append(
    renderFieldGrid([
      ['Model', title],
      ['Quant', model?.quant || '—'],
      ['Size', model ? `${formatNumber(model.sizeGb)} GB` : '—'],
      ['Status', status.title],
      ['Runtime', status.detail],
    ]),
  );

  const expanded = el('div', 'deploy-deployment-expanded');
  expanded.append(
    renderGroup('General', renderFieldGrid([
      ['Name', model?.name || title],
      ['Model ID', state.launcher.modelId || model?.id || '—'],
      ['Alias', model?.alias || '—'],
      ['Quant', model?.quant || '—'],
      ['Size', model ? `${formatNumber(model.sizeGb)} GB` : '—'],
      ['Source', model?.registrySource || '—'],
    ])),
    renderGroup('Status', renderFieldGrid(renderStatusRows(slot))),
  );

  cardNode.append(header, runningCardExpanded ? expanded : collapsed);
  return cardNode;
}

function ggufEntries(model: NonNullable<ReturnType<typeof findSelectedModel>>): Array<[string, string]> {
  return Object.entries(model.metadata.extra)
    .filter(([key]) => key.startsWith('gguf.'))
    .map(([key, value]) => [key.replace(/^gguf\./, ''), value] as [string, string])
    .sort(([a], [b]) => a.localeCompare(b));
}

function groupedGgufRows(model: NonNullable<ReturnType<typeof findSelectedModel>>, matcher: (key: string) => boolean): Array<[string, string]> {
  return ggufEntries(model)
    .filter(([key]) => matcher(key))
    .map(([key, value]) => [toLabel(key.split('.').slice(1).join('.') || key), value] as [string, string]);
}

function renderModelInfoTab(model: NonNullable<ReturnType<typeof findSelectedModel>>): HTMLElement {
  const info = el('div', 'deploy-tab-content');
  info.dataset.scrollKey = `deploy-right-tab:${model.id}:modelInfo`;
  info.append(
    renderGroupCard('File', 'Local file and registration details.', [renderFieldGrid([
      ['Name', model.name],
      ['Alias', model.alias],
      ['Quant', model.quant],
      ['Size', `${formatNumber(model.sizeGb)} GB`],
      ['Path', model.path],
      ['Directory', model.directory],
      ['Registry source', model.registrySource],
    ])]),
    renderGroupCard('Metadata', 'Human-readable model metadata.', [renderFieldGrid([
      ['Description', formatText(model.metadata.description)],
      ['Repository', formatText(model.metadata.repository)],
      ['Base model repository', formatText(model.metadata.baseModelRepository)],
      ['Base model repo URL', formatText(model.metadata.baseModelRepositoryUrl)],
      ['Family', formatText(model.metadata.family)],
      ['Tags', model.metadata.tags.length ? model.metadata.tags.join(', ') : '—'],
      ['Config path', formatText(model.metadata.configPath)],
      ['Transformer layers', formatText(model.metadata.transformerLayers)],
      ['Full offload layers', formatText(model.metadata.fullOffloadLayers)],
      ['Output layer', formatText(model.metadata.outputLayer)],
    ])]),
  );

  const generalRows = groupedGgufRows(model, (key) => key.startsWith('general.'));
  const architecture = model.metadata.extra['gguf.general.architecture'];
  const architectureRows = groupedGgufRows(
    model,
    (key) => Boolean(architecture && key.startsWith(`${architecture}.`) && !key.includes('.attention.') && !key.includes('.rope.') && !key.includes('.expert') && !key.includes('.ssm.'))
  );
  const attentionRows = groupedGgufRows(model, (key) => key.includes('.attention.'));
  const ropeRows = groupedGgufRows(model, (key) => key.includes('.rope.'));
  const expertRows = groupedGgufRows(model, (key) => key.includes('.expert'));
  const ssmRows = groupedGgufRows(model, (key) => key.includes('.ssm.'));
  const tokenizerRows = groupedGgufRows(model, (key) => key.startsWith('tokenizer.') && !key.includes('tokens') && !key.includes('merges'));

  info.append(
    renderGroupCard('GGUF', 'Parsed structure from the model file.', [
      renderGroupCard('General', '', [renderFieldGrid(generalRows, 'No general GGUF parameters found.')]),
      renderGroupCard(architecture ? `${architecture} architecture` : 'Architecture', '', [renderFieldGrid(architectureRows, 'No architecture parameters found.')]),
      renderGroupCard('Attention', '', [renderFieldGrid(attentionRows, 'No attention parameters found.')]),
      renderGroupCard('RoPE', '', [renderFieldGrid(ropeRows, 'No RoPE parameters found.')]),
      renderGroupCard('Experts / MoE', '', [renderFieldGrid(expertRows, 'No expert parameters found.')]),
      renderGroupCard('State-space / hybrid', '', [renderFieldGrid(ssmRows, 'No state-space parameters found.')]),
      renderGroupCard('Tokenizer', '', [renderFieldGrid(tokenizerRows, 'No tokenizer parameters found.')]),
    ])
  );
  return info;
}

function renderDeploymentTab(state: AppState, actions: AppActions, model: NonNullable<ReturnType<typeof findSelectedModel>>): HTMLElement {
  const deployment = el('div', 'deploy-tab-content');
  deployment.dataset.scrollKey = `deploy-right-tab:${model.id}:${activeDeployTab}`;
  const profile = selectedProfile(state, model);
  const ctxCurrent = toNumber(profile.CtxSize, DEFAULT_MODEL_PROFILE_CONFIG.CtxSize);
  const gpuCurrent = toNumber(profile.GpuLayers, DEFAULT_MODEL_PROFILE_CONFIG.GpuLayers);
  const cpuMoeCurrent = toNumber(profile.NcpuMoe, DEFAULT_MODEL_PROFILE_CONFIG.NcpuMoe);
  const inferredLimits = inferModelProfileLimits(model);
  const ctxLimit = Math.max(ctxCurrent, inferredLimits.contextMax);
  const gpuLimit = Math.max(gpuCurrent, inferredLimits.gpuLayersMax);
  const cpuMoeLimit = Math.max(cpuMoeCurrent, inferredLimits.cpuMoeMax);
  const limitSource = inferredLimits.contextFromMetadata ? 'GGUF metadata' : 'permissive fallback (GGUF context length unavailable)';
  const statusText = state.launcher.running
    ? (state.launcher.modelId === model.id || state.launcher.deployment?.mode === 'multi-model-repository' ? `Model deployed${selectedProfile(state, model).Alias ? ` as alias ${selectedProfile(state, model).Alias}` : ''}` : 'Server ready')
    : 'Deployment unavailable: server stopped';
  deployment.append(
    renderGroupCard('Deployment status', 'Read-only server/deployment state.', [el('div', 'deploy-intro', statusText)]),
    renderGroupCard('Model identity', 'Per-model served name and template overrides.', [
      renderModelPresetChoice(state, actions, model),
      renderModelTextField(state, actions, model, 'Alias', 'Served alias'),
      renderModelTextField(state, actions, model, 'ChatTemplate', 'Chat template'),
    ]),
    renderGroupCard('Context & offload', 'Model loading options used for the next deployment.', [
      renderModelSliderField(state, actions, model, 'CtxSize', 'Context size', 1, ctxLimit, 1, ' tokens'),
      renderModelSliderField(state, actions, model, 'GpuLayers', 'GPU layers', 0, gpuLimit, 1),
      renderModelSliderField(state, actions, model, 'NcpuMoe', 'CPU MoE layers', 0, cpuMoeLimit, 1),
      el('div', 'deploy-field-note', `Slider limits: context ${ctxLimit} (${limitSource}), GPU offload ${gpuLimit} layer${gpuLimit === 1 ? '' : 's'}${inferredLimits.gpuLayersIncludeOutputLayer ? ' including output layer' : ''}. Numeric inputs remain free overrides.`),
    ]),
    renderGroupCard('Advanced model options', 'Memory, cache, GPU, and template settings.', [
      renderModelChoiceOverrideField(state, actions, model, 'FlashAttn', 'Flash attention', MODEL_SUGGESTIONS.FlashAttn!),
      renderModelChoiceOverrideField(state, actions, model, 'CacheTypeK', 'Cache type K', MODEL_SUGGESTIONS.CacheTypeK!),
      renderModelChoiceOverrideField(state, actions, model, 'CacheTypeV', 'Cache type V', MODEL_SUGGESTIONS.CacheTypeV!),
      renderModelToggleField(state, actions, model, 'Mlock', 'Mlock'),
      renderModelToggleField(state, actions, model, 'NoMmap', 'No mmap'),
      renderModelChoiceOverrideField(state, actions, model, 'SplitMode', 'Split mode', MODEL_SUGGESTIONS.SplitMode!),
      renderModelTextField(state, actions, model, 'TensorSplit', 'Tensor split'),
      renderModelNumberField(state, actions, model, 'MainGpu', 'Main GPU'),
      renderModelChoiceOverrideField(state, actions, model, 'Device', 'Device', MODEL_SUGGESTIONS.Device!),
      renderModelToggleField(state, actions, model, 'Jinja', 'Jinja templates'),
      button('Save model profile', actions.saveSelectedModelProfile, 'secondary'),
    ]),
  );
  return deployment;
}

function renderInferenceTab(state: AppState, actions: AppActions, model: NonNullable<ReturnType<typeof findSelectedModel>>): HTMLElement {
  const inference = el('div', 'deploy-tab-content');
  inference.dataset.scrollKey = `deploy-right-tab:${model.id}:inference`;
  inference.append(
    renderGroupCard('Prompt', 'Model-provided context only; editable inference prompt is not persisted here.', [
      renderReadOnlyTextArea('System prompt', model.metadata.systemPrompt, 8),
    ]),
    renderGroupCard('Sampling', 'Tune decoding behavior.', [
      renderModelNumberField(state, actions, model, 'MaxTokens', 'Max tokens'),
      renderModelSliderField(state, actions, model, 'Temp', 'Temperature', 0, 2, 0.01),
      renderModelSliderField(state, actions, model, 'TopK', 'Top K', 0, 200, 1),
      renderModelSliderField(state, actions, model, 'TopP', 'Top P', 0, 1, 0.01),
      renderModelSliderField(state, actions, model, 'MinP', 'Min P', 0, 1, 0.01),
      renderModelSliderField(state, actions, model, 'TypicalP', 'Typical P', 0, 1, 0.01),
      renderModelSliderField(state, actions, model, 'RepeatPenalty', 'Repeat penalty', 1, 2.5, 0.01),
      renderModelSliderField(state, actions, model, 'RepeatLastN', 'Repeat last N', 0, 4096, 1),
      renderModelSliderField(state, actions, model, 'PresencePenalty', 'Presence penalty', -2, 2, 0.01),
      renderModelSliderField(state, actions, model, 'FreqPenalty', 'Frequency penalty', -2, 2, 0.01),
      renderModelNumberField(state, actions, model, 'Seed', 'Seed'),
      renderModelTextField(state, actions, model, 'StopSequences', 'Stop sequences'),
    ]),
    renderGroupCard('Reasoning', 'Reasoning and output shaping.', [
      renderModelToggleField(state, actions, model, 'Thinking', 'Thinking'),
      renderModelToggleField(state, actions, model, 'PreserveThinking', 'Preserve thinking'),
      renderModelChoiceOverrideField(state, actions, model, 'ReasoningFormat', 'Reasoning format', MODEL_SUGGESTIONS.ReasoningFormat!),
      renderModelTextField(state, actions, model, 'ReasoningBudget', 'Reasoning budget'),
      renderModelSliderField(state, actions, model, 'DryMultiplier', 'Dry multiplier', 0, 4, 0.01),
      renderModelSliderField(state, actions, model, 'DryBase', 'Dry base', 0, 4, 0.01),
      renderModelSliderField(state, actions, model, 'DryAllowed', 'Dry allowed', 0, 8, 0.01),
      renderModelSliderField(state, actions, model, 'XtcProb', 'XTC probability', 0, 1, 0.01),
      renderModelSliderField(state, actions, model, 'XtcThresh', 'XTC threshold', 0, 1, 0.01),
      button('Save model profile', actions.saveSelectedModelProfile, 'secondary'),
    ]),
  );
  return inference;
}

function renderModelTab(state: AppState, actions: AppActions, model: NonNullable<ReturnType<typeof findSelectedModel>>, tab: DeployTab): HTMLElement {
  if (tab === 'deployment') return renderDeploymentTab(state, actions, model);
  if (tab === 'inference') return renderInferenceTab(state, actions, model);
  return renderModelInfoTab(model);
}

function applyDeployWidths(root: HTMLElement): void {
  root.style.setProperty('--deploy-left-width', `${deployPanelWidths.left}px`);
  root.style.setProperty('--deploy-right-width', `${deployPanelWidths.right}px`);
  root.style.setProperty('--deploy-resizer-width', `${deployResizeHandleWidth()}px`);
}

function observeDeployResize(root: HTMLElement): void {
  cleanupDeployResizeObserver?.();
  let frame = 0;
  let observer: ResizeObserver | undefined;
  const update = () => {
    if (frame) return;
    frame = window.requestAnimationFrame(() => {
      frame = 0;
      if (!root.isConnected) {
        observer?.disconnect();
        window.removeEventListener('resize', update);
        return;
      }
      syncDeployWidthsToRootFont();
      clampDeployWidths(root.getBoundingClientRect().width || window.innerWidth);
      applyDeployWidths(root);
    });
  };

  window.addEventListener('resize', update);
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(update);
    observer.observe(root);
  }
  cleanupDeployResizeObserver = () => {
    observer?.disconnect();
    window.removeEventListener('resize', update);
    if (frame) window.cancelAnimationFrame(frame);
    frame = 0;
  };
}

function clampDeployWidths(totalWidth: number): void {
  const handleWidth = deployResizeHandleWidth();
  const centerMin = deployCenterMinWidth();
  const panelMin = deployPanelMinWidth();
  const available = Math.max(0, totalWidth - (handleWidth * 2) - centerMin);
  deployPanelWidths.left = Math.min(Math.max(deployPanelWidths.left, panelMin), Math.max(panelMin, available - panelMin));
  deployPanelWidths.right = Math.min(Math.max(deployPanelWidths.right, panelMin), Math.max(panelMin, available - deployPanelWidths.left));
}

function attachResizeHandle(
  handle: HTMLElement,
  root: HTMLElement,
  kind: 'left' | 'right'
): void {
  handle.addEventListener('pointerdown', (event) => {
    if (event.button !== 0) return;
    event.preventDefault();
    handle.setPointerCapture(event.pointerId);
    const startRect = root.getBoundingClientRect();
    const startLeft = deployPanelWidths.left;
    const startRight = deployPanelWidths.right;
    const handleWidth = deployResizeHandleWidth();
    const centerMin = deployCenterMinWidth();
    const panelMin = deployPanelMinWidth();
    const onMove = (moveEvent: PointerEvent) => {
      const x = moveEvent.clientX - startRect.left;
      const total = startRect.width;
      if (kind === 'left') {
        const maxLeft = Math.max(panelMin, total - startRight - centerMin - (handleWidth * 2));
        deployPanelWidths.left = Math.min(Math.max(x, panelMin), maxLeft);
      } else {
        const maxRight = Math.max(panelMin, total - startLeft - centerMin - (handleWidth * 2));
        deployPanelWidths.right = Math.min(Math.max(total - x, panelMin), maxRight);
      }
      applyDeployWidths(root);
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onUp);
      document.body.classList.remove('deploy-resizing');
    };
    document.body.classList.add('deploy-resizing');
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp, { once: true });
    window.addEventListener('pointercancel', onUp, { once: true });
  });
}

function enhanceTree(root: HTMLElement): void {
  root.querySelectorAll<HTMLButtonElement>('.tree-row.model').forEach((node) => {
    const modelId = node.dataset.modelId;
    if (!modelId) return;
    node.draggable = true;
    node.addEventListener('dragstart', (event) => {
      event.dataTransfer?.setData('text/plain', modelId);
      event.dataTransfer?.setData('application/x-turbo-model-id', modelId);
      if (event.dataTransfer) event.dataTransfer.effectAllowed = 'copy';
      node.classList.add('dragging');
    });
    node.addEventListener('dragend', () => node.classList.remove('dragging'));
  });
}

export function renderDeployView(state: AppState, actions: AppActions): HTMLElement {
  const root = el('div', 'view-grid deploy-view');
  ensureDeployWidthDefaults();
  syncDeployWidthsToRootFont();
  clampDeployWidths(window.innerWidth);
  applyDeployWidths(root);
  observeDeployResize(root);
  const model = findSelectedModel(state);
  const left = el('aside', 'panel deploy-panel deploy-browser');
  const leftCard = card('Models');
  leftCard.append(el('p', 'muted', 'Drag to launch or click to inspect.'));
  const browser = tree(state.catalog.tree, actions.setSelectedModel, state.selectedModelId);
  browser.classList.add('deploy-tree-wrap');
  browser.dataset.scrollKey = 'deploy-model-tree';
  leftCard.append(browser);
  left.append(leftCard);
  enhanceTree(left);

  const leftHandle = el('div', 'deploy-handle', '');
  leftHandle.setAttribute('aria-hidden', 'true');
  leftHandle.title = 'Resize panels';

  const center = el('main', 'panel deploy-panel deploy-launcher');
  const dropZone = el('section', 'drop-zone');
  dropZone.addEventListener('dragover', (event) => {
    event.preventDefault();
    dropZone.classList.add('dragover');
  });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
  dropZone.addEventListener('drop', (event) => {
    event.preventDefault();
    dropZone.classList.remove('dragover');
    const modelId = event.dataTransfer?.getData('application/x-turbo-model-id') || event.dataTransfer?.getData('text/plain');
    if (!modelId) return;
    actions.setSelectedModel(modelId);
    void actions.launchSelected();
  });
  if (state.launcher.running) {
    dropZone.append(renderRunningDeploymentCard(state, actions, model), el('p', 'deploy-drop-detail', 'Drop another browser model here to redeploy it.'));
  } else {
    const empty = el('div', 'deploy-drop-empty');
    empty.append(
      el('div', 'deploy-drop-copy', 'Drop a model here to launch'),
      el('p', 'deploy-drop-detail', 'Choose a model from the browser, then drag it into this panel or use Launch in the top bar.'),
      badge('Drag from Models', 'secondary'),
    );
    if (model) {
      const selectedSummary = el('div', 'deploy-drop-selected');
      const selectedMeta = `${model.alias} · ${model.quant} · ${formatNumber(model.sizeGb)} GB`;
      const path = el('div', 'deploy-drop-selected-meta', model.path);
      path.title = model.path;
      selectedSummary.append(
        el('div', 'deploy-drop-selected-label', 'Selected model'),
        el('div', 'deploy-drop-selected-name', model.name),
        el('div', 'deploy-drop-selected-meta', selectedMeta),
        path,
      );
      empty.append(selectedSummary);
    } else {
      empty.append(el('p', 'deploy-drop-detail', 'No model selected.'));
    }
    dropZone.append(empty);
  }
  center.append(dropZone);

  const rightHandle = el('div', 'deploy-handle', '');
  rightHandle.setAttribute('aria-hidden', 'true');
  rightHandle.title = 'Resize panels';

  const right = el('aside', 'panel deploy-panel deploy-details');
  right.dataset.scrollKey = `deploy-right-panel:${state.selectedModelId ?? 'none'}`;
  const selected = card('Selected model');
  if (!model) {
    selected.append(el('p', 'muted', 'Choose a model from the browser tree to inspect its parameters.'));
  } else {
    const selectedBadges = el('div', 'deploy-badges', '');
    const selectedTabs = tabs([
      { id: 'modelInfo', label: 'Info' },
      { id: 'deployment', label: 'Load' },
      { id: 'inference', label: 'Inference' },
    ], activeDeployTab, (tab) => {
      activeDeployTab = tab as DeployTab;
      actions.setSelectedModel(state.selectedModelId);
    });
    selectedBadges.append(badge(model.registrySource, 'secondary'), badge(model.quant, 'secondary'));
    selected.append(
      selectedBadges,
      selectedTabs,
      renderModelTab(state, actions, model, activeDeployTab)
    );
  }
  right.append(selected);

  attachResizeHandle(leftHandle, root, 'left');
  attachResizeHandle(rightHandle, root, 'right');

  root.append(left, leftHandle, center, rightHandle, right);
  return root;
}
