import fs from 'node:fs/promises';
import path from 'node:path';
import { BUILT_IN_PRESETS, DEFAULT_MODEL_PROFILE_CONFIG } from '../shared/defaults';
import { detectQuant, estimateDeployment, fileSizeGb, parseModelConfig, parsePreset, parseRegistry } from '../shared/parsers';
import type { LlamaServerSettings, ModelCatalog, ModelInfo, ModelMetadata, ModelProfileConfig, ModelRegistryEntry, PresetDefinition, TreeNode } from '../shared/types';
import type { AppPaths } from './AppPaths';
import { readGgufMetadata, type GgufMetadata, type GgufValue } from './GgufMetadata';
import type { HuggingFaceService } from './HuggingFaceService';

export class ModelService {
  private lastCatalog: ModelCatalog | null = null;

  constructor(private readonly paths: AppPaths, private readonly huggingFace?: HuggingFaceService) {}

  async loadPresets(): Promise<PresetDefinition[]> {
    const presets: PresetDefinition[] = [...BUILT_IN_PRESETS];
    try {
      const entries = await fs.readdir(this.paths.paths.presetsDir, { withFileTypes: true });
      for (const entry of entries) {
        if (!entry.isFile() || !entry.name.endsWith('.json')) continue;
        const filePath = path.join(this.paths.paths.presetsDir, entry.name);
        const preset = parsePreset(filePath, await fs.readFile(filePath, 'utf8'));
        if (preset) presets.push(preset);
      }
    } catch {
      // ignore missing presets directory
    }
    return presets;
  }

  async refreshCatalog(settings: Partial<ModelProfileConfig> = DEFAULT_MODEL_PROFILE_CONFIG): Promise<ModelCatalog> {
    const registry = await this.readRegistry();
    const configFiles = await this.readConfigFiles();
    const configs = new Map<string, ReturnType<typeof parseModelConfig>>();
    for (const configPath of configFiles) {
      try {
        configs.set(configPath, parseModelConfig(configPath, await fs.readFile(configPath, 'utf8')));
      } catch {
        continue;
      }
    }

    const candidates = new Map<string, ModelInfo>();
    const addCandidate = (model: ModelInfo) => { candidates.set(model.id, model); };

    for (const entry of registry) {
      const resolvedPath = path.resolve(this.paths.paths.rootDir, entry.path);
      const config = configFiles.find((cfg) => path.resolve(cfg) === resolvedPath);
      if (config) {
        const parsed = configs.get(config)!;
        const modelPath = parsed.modelPath ? path.resolve(path.dirname(config), parsed.modelPath) : config;
        addCandidate(await this.buildModelInfo(modelPath, entry.alias || parsed.alias, 'config', parsed.metadata, settings, parsed.settings));
        continue;
      }
      const meta = configs.get(resolvedPath);
      const modelPath = meta?.modelPath ? path.resolve(path.dirname(resolvedPath), meta.modelPath) : resolvedPath;
      const metadata = meta?.metadata ?? emptyMetadata();
      addCandidate(await this.buildModelInfo(modelPath, entry.alias, 'registry', metadata, settings, meta?.settings));
    }

    const scanRoots = [path.join(this.paths.paths.rootDir, 'models'), path.join(this.paths.paths.userDataDir, 'models')];
    for (const root of scanRoots) {
      for await (const modelPath of this.walkFiles(root, 3)) {
        if (path.extname(modelPath).toLowerCase() !== '.gguf') continue;
        const alias = path.basename(modelPath, path.extname(modelPath));
        addCandidate(await this.buildModelInfo(modelPath, alias, 'scan', emptyMetadata(), settings));
      }
    }

    const models = [...candidates.values()].sort((a, b) => a.alias.localeCompare(b.alias));
    const tree = this.buildTree(models, scanRoots);
    this.lastCatalog = { tree, models, registry, configFiles, localRoots: scanRoots };
    return this.lastCatalog;
  }

  async findModel(modelId?: string): Promise<ModelInfo | null> {
    if (!modelId) return null;
    const catalog = this.lastCatalog ?? await this.refreshCatalog(DEFAULT_MODEL_PROFILE_CONFIG);
    return catalog.models.find((model) => model.id === modelId || model.alias === modelId) ?? null;
  }

  private async readRegistry(): Promise<ModelRegistryEntry[]> {
    try {
      return parseRegistry(await fs.readFile(this.paths.paths.registryFile, 'utf8')).map((entry) => ({ ...entry, path: entry.path }));
    } catch {
      return [];
    }
  }

  private async readConfigFiles(): Promise<string[]> {
    try {
      const entries = await fs.readdir(this.paths.paths.modelConfigsDir, { withFileTypes: true });
      return entries.filter((entry) => entry.isFile() && entry.name.endsWith('.cfg')).map((entry) => path.join(this.paths.paths.modelConfigsDir, entry.name));
    } catch {
      return [];
    }
  }

  private async *walkFiles(root: string, maxDepth: number, depth = 0): AsyncGenerator<string> {
    if (depth > maxDepth) return;
    try {
      const entries = await fs.readdir(root, { withFileTypes: true });
      for (const entry of entries) {
        const fullPath = path.join(root, entry.name);
        if (entry.isFile()) {
          yield fullPath;
        } else if (entry.isDirectory()) {
          yield* this.walkFiles(fullPath, maxDepth, depth + 1);
        }
      }
    } catch {
      return;
    }
  }

  private async buildModelInfo(modelPath: string, alias: string, source: ModelRegistryEntry['source'], metadata: ModelMetadata, settings: Partial<ModelProfileConfig>, configSettings: Partial<ModelProfileConfig> = {}): Promise<ModelInfo> {
    const sizeGb = fileSizeGb(modelPath);
    const gguf = path.extname(modelPath).toLowerCase() === '.gguf' ? await readGgufMetadata(modelPath) : null;
    const ggufMetadata = gguf ? metadataFromGguf(gguf) : emptyMetadata();
    const mergedMetadata = mergeMetadata(ggufMetadata, metadata);
    const fileNameQuant = detectQuant(modelPath);
    const quant = gguf?.quant ?? fileNameQuant;
    const effectiveSettings = { ...configSettings, ...settings };
    const estimate = estimateDeployment(sizeGb, effectiveSettings.CtxSize ?? DEFAULT_MODEL_PROFILE_CONFIG.CtxSize, effectiveSettings.GpuLayers ?? DEFAULT_MODEL_PROFILE_CONFIG.GpuLayers);
    const hf = metadata.repository ? await this.huggingFace?.getModel(metadata.repository) : null;
    const enrichedMetadata = {
      ...mergedMetadata,
      description: hf?.id ? (mergedMetadata.description || `Hugging Face repository: ${hf.id}`) : mergedMetadata.description,
      repository: hf?.id ?? mergedMetadata.repository,
      family: mergedMetadata.family || hf?.pipelineTag || '',
      tags: [...new Set([...mergedMetadata.tags, ...(hf?.tags ?? [])])],
    };
    return {
      id: path.resolve(modelPath),
      alias,
      name: path.basename(modelPath),
      path: modelPath,
      directory: path.dirname(modelPath),
      quant,
      sizeGb,
      metadata: enrichedMetadata,
      configSettings,
      registrySource: source,
      estimate,
    };
  }

  private buildTree(models: ModelInfo[], localRoots: string[]): TreeNode[] {
    type GroupBuilder = { node: TreeNode; children: Map<string, GroupBuilder>; leaves: TreeNode[] };
    const roots = new Map<string, GroupBuilder>();

    const getGroup = (scope: Map<string, GroupBuilder>, label: string, detail?: string): GroupBuilder => {
      const existing = scope.get(label);
      if (existing) {
        if (!existing.node.detail && detail) existing.node.detail = detail;
        return existing;
      }
      const node: TreeNode = { id: `group:${scope.size}:${label}`, label, detail, kind: 'group', children: [] };
      const created: GroupBuilder = { node, children: new Map(), leaves: [] };
      scope.set(label, created);
      return created;
    };

    for (const model of models) {
      const { segments, detail } = treeSegmentsForModel(model, localRoots);
      let scope = roots;
      let current: GroupBuilder | undefined;
      for (const segment of segments) {
        current = getGroup(scope, segment, detail);
        scope = current.children;
      }
      const leaf: TreeNode = { id: model.id, label: `${model.alias} · ${model.quant}`, detail: model.path, kind: 'model', modelId: model.id };
      if (current) current.leaves.push(leaf);
      else roots.set(model.id, { node: leaf, children: new Map(), leaves: [] });
    }

    const sortNodes = (nodes: TreeNode[]): TreeNode[] => nodes
      .slice()
      .sort((a, b) => {
        if (a.kind !== b.kind) return a.kind === 'group' ? -1 : 1;
        return a.label.localeCompare(b.label);
      })
      .map((node) => node.children ? { ...node, children: sortNodes(node.children) } : node);

    const build = (scope: Map<string, GroupBuilder>): TreeNode[] => sortNodes([
      ...[...scope.values()].map((entry) => {
        const children = build(entry.children);
        const leafNodes = sortNodes(entry.leaves);
        return { ...entry.node, children: [...children, ...leafNodes] };
      }),
    ]);

    return build(roots);
  }

}

function emptyMetadata(): ModelMetadata {
  return { description: '', repository: '', family: '', tags: [], systemPrompt: '', chatTemplate: '', extra: {} };
}

function metadataFromGguf(gguf: GgufMetadata): ModelMetadata {
  const values = gguf.values;
  const architecture = stringFromValue(values['general.architecture']);
  const baseModelRepositoryUrl = baseModelRepoUrlFromGguf(values);
  const baseModelRepository = repositoryLabelFromUrl(baseModelRepositoryUrl);
  const metadata: ModelMetadata = {
    description: firstString(values, ['general.description', 'general.comment']),
    repository: repositoryFromGguf(values),
    ...(baseModelRepository ? { baseModelRepository } : {}),
    ...(baseModelRepositoryUrl ? { baseModelRepositoryUrl } : {}),
    family: [architecture, firstString(values, ['general.size_label'])].filter(Boolean).join(' ').trim(),
    tags: tagsFromGguf(values),
    systemPrompt: firstString(values, ['general.system_prompt', 'tokenizer.chat_system_prompt']),
    chatTemplate: firstString(values, ['tokenizer.chat_template']),
    ...(numberFromValue(values[`${architecture}.block_count`]) ? { transformerLayers: numberFromValue(values[`${architecture}.block_count`]) } : {}),
    extra: ggufExtra(values),
  };
  return metadata;
}

function mergeMetadata(base: ModelMetadata, override: ModelMetadata): ModelMetadata {
  return {
    ...base,
    ...definedMetadataOptions(override),
    description: override.description || base.description,
    repository: override.repository || base.repository,
    family: override.family || base.family,
    tags: override.tags.length ? override.tags : base.tags,
    systemPrompt: override.systemPrompt || base.systemPrompt,
    chatTemplate: override.chatTemplate || base.chatTemplate,
    extra: { ...base.extra, ...override.extra },
  };
}

function definedMetadataOptions(metadata: ModelMetadata): Partial<ModelMetadata> {
  const options: Partial<ModelMetadata> = {};
  if (metadata.baseModelRepository) options.baseModelRepository = metadata.baseModelRepository;
  if (metadata.baseModelRepositoryUrl) options.baseModelRepositoryUrl = metadata.baseModelRepositoryUrl;
  if (metadata.host) options.host = metadata.host;
  if (metadata.port !== undefined) options.port = metadata.port;
  if (metadata.configPath) options.configPath = metadata.configPath;
  if (metadata.transformerLayers !== undefined) options.transformerLayers = metadata.transformerLayers;
  if (metadata.outputLayer !== undefined) options.outputLayer = metadata.outputLayer;
  if (metadata.fullOffloadLayers !== undefined) options.fullOffloadLayers = metadata.fullOffloadLayers;
  return options;
}

function ggufExtra(values: Record<string, GgufValue>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(values)
      .filter(([key]) => !key.startsWith('tokenizer.ggml.'))
      .map(([key, value]) => [`gguf.${key}`, stringifyGgufValue(value)])
  );
}

function firstString(values: Record<string, GgufValue>, keys: string[]): string {
  for (const key of keys) {
    const value = stringFromValue(values[key]);
    if (value) return value;
  }
  return '';
}

function repositoryFromGguf(values: Record<string, GgufValue>): string {
  const explicit = firstString(values, ['general.repository', 'general.repo_id', 'huggingface.repo_id']);
  if (explicit) return explicit;

  const url = firstString(values, ['general.source.url', 'general.url', 'general.repo_url']);
  const match = url.match(/(?:huggingface\.co|hf\.co)\/([^/\s]+\/[^/\s?#]+)/i);
  return match?.[1] ?? '';
}

function baseModelRepoUrlFromGguf(values: Record<string, GgufValue>): string {
  const direct = firstString(values, ['general.base_model.repo_url', 'general.base_model.url']);
  if (direct) return direct;

  const match = Object.entries(values)
    .filter(([key]) => /^general\.base_model(?:\.\d+)?\.(?:repo_url|url)$/i.test(key))
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([, value]) => stringFromValue(value).trim())
    .find(Boolean);
  return match ?? '';
}

function repositoryLabelFromUrl(url: string): string {
  const trimmed = url.trim();
  if (!trimmed) return '';
  const hf = trimmed.match(/(?:huggingface\.co|hf\.co)\/([^/\s]+\/[^/\s?#]+)/i);
  if (hf?.[1]) return hf[1];
  try {
    const parsed = new URL(trimmed);
    return parsed.pathname.replace(/^\/+/, '').replace(/\/+$/, '') || parsed.hostname;
  } catch {
    return trimmed;
  }
}

function treeSegmentsForModel(model: ModelInfo, localRoots: string[]): { segments: string[]; detail?: string } {
  const repoValue = model.metadata.baseModelRepositoryUrl || model.metadata.baseModelRepository || model.metadata.repository;
  if (repoValue) {
    const repo = repositorySegmentsFromValue(repoValue);
    if (repo.segments.length) return repo;
  }

  const local = localModelSegments(model, localRoots);
  return { segments: local.length ? local : ['Unlinked local models'], detail: model.directory };
}

function localModelSegments(model: ModelInfo, localRoots: string[]): string[] {
  const directory = path.resolve(model.directory);
  const root = localRoots.map((rootPath) => path.resolve(rootPath)).find((rootPath) => directory.toLowerCase().startsWith(rootPath.toLowerCase()));
  if (!root) return ['Local models', path.basename(model.directory) || 'Files'];
  const relative = path.relative(root, directory);
  const parts = relative.split(path.sep).filter(Boolean);
  return ['Local models', path.basename(root), ...parts].filter(Boolean);
}

function repositorySegmentsFromValue(value: string): { segments: string[]; detail?: string } {
  const trimmed = value.trim();
  if (!trimmed) return { segments: [] };
  try {
    const parsed = new URL(trimmed);
    const pathname = parsed.pathname.replace(/^\/+/, '').replace(/\/+$/, '');
    const parts = pathname.split('/').filter(Boolean);
    return { segments: [parsed.hostname, ...parts], detail: trimmed };
  } catch {
    const clean = trimmed.replace(/^https?:\/\//i, '');
    const parts = clean.split('/').filter(Boolean);
    if (parts.length >= 2) return { segments: parts, detail: trimmed };
    return { segments: [trimmed], detail: trimmed };
  }
}


function tagsFromGguf(values: Record<string, GgufValue>): string[] {
  const tags = [values['general.tags'], values['general.languages'], values['general.language']]
    .flatMap((value) => stringsFromValue(value))
    .map((tag) => tag.trim())
    .filter(Boolean);
  return [...new Set(tags)];
}

function stringsFromValue(value: GgufValue | undefined): string[] {
  if (typeof value === 'string') return value.split(/[;,]/).map((part) => part.trim()).filter(Boolean);
  if (Array.isArray(value)) return value.flatMap((item) => typeof item === 'string' ? item : []);
  return [];
}

function stringFromValue(value: GgufValue | undefined): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') return String(value);
  return '';
}

function numberFromValue(value: GgufValue | undefined): number | undefined {
  if (typeof value === 'number') return value;
  if (typeof value === 'bigint' && value <= BigInt(Number.MAX_SAFE_INTEGER)) return Number(value);
  return undefined;
}

function stringifyGgufValue(value: GgufValue): string {
  if (typeof value === 'bigint') return value.toString();
  if (Array.isArray(value)) return value.map((item) => typeof item === 'bigint' ? item.toString() : String(item)).join(', ');
  return String(value);
}
