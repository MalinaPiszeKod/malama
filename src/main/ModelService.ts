import fs from 'node:fs/promises';
import path from 'node:path';
import { BUILT_IN_PRESETS, DEFAULT_SETTINGS } from '../shared/defaults';
import { detectQuant, estimateDeployment, fileSizeGb, parseModelConfig, parsePreset, parseRegistry } from '../shared/parsers';
import type { LlamaServerSettings, ModelCatalog, ModelInfo, ModelRegistryEntry, PresetDefinition, TreeNode } from '../shared/types';
import type { AppPaths } from './AppPaths';

export class ModelService {
  private lastCatalog: ModelCatalog | null = null;

  constructor(private readonly paths: AppPaths) {}

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

  async refreshCatalog(settings: Partial<LlamaServerSettings> = DEFAULT_SETTINGS): Promise<ModelCatalog> {
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
        addCandidate(this.buildModelInfo(modelPath, entry.alias || parsed.alias, 'config', parsed.metadata, settings, parsed.settings));
        continue;
      }
      const meta = configs.get(resolvedPath);
      const modelPath = meta?.modelPath ? path.resolve(path.dirname(resolvedPath), meta.modelPath) : resolvedPath;
      const metadata = meta?.metadata ?? { description: '', systemPrompt: '', chatTemplate: '', extra: {} };
      addCandidate(this.buildModelInfo(modelPath, entry.alias, 'registry', metadata, settings, meta?.settings));
    }

    const scanRoots = [path.join(this.paths.paths.rootDir, 'models'), path.join(this.paths.paths.userDataDir, 'models')];
    for (const root of scanRoots) {
      for await (const modelPath of this.walkFiles(root, 3)) {
        if (path.extname(modelPath).toLowerCase() !== '.gguf') continue;
        const alias = path.basename(modelPath, path.extname(modelPath));
        addCandidate(this.buildModelInfo(modelPath, alias, 'scan', { description: '', systemPrompt: '', chatTemplate: '', extra: {} }, settings));
      }
    }

    const models = [...candidates.values()].sort((a, b) => a.alias.localeCompare(b.alias));
    const tree = this.buildTree(models);
    this.lastCatalog = { tree, models, registry, configFiles, localRoots: scanRoots };
    return this.lastCatalog;
  }

  async findModel(modelId?: string): Promise<ModelInfo | null> {
    if (!modelId) return null;
    const catalog = this.lastCatalog ?? await this.refreshCatalog(DEFAULT_SETTINGS);
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

  private buildModelInfo(modelPath: string, alias: string, source: ModelRegistryEntry['source'], metadata: { description: string; systemPrompt: string; chatTemplate: string; host?: string; port?: number; configPath?: string; transformerLayers?: number; outputLayer?: boolean; fullOffloadLayers?: number; extra: Record<string, string> }, settings: Partial<LlamaServerSettings>, configSettings: Partial<LlamaServerSettings> = {}): ModelInfo {
    const sizeGb = fileSizeGb(modelPath);
    const quant = detectQuant(modelPath);
    const effectiveSettings = { ...configSettings, ...settings };
    const estimate = estimateDeployment(sizeGb, effectiveSettings.CtxSize ?? DEFAULT_SETTINGS.CtxSize, effectiveSettings.GpuLayers ?? DEFAULT_SETTINGS.GpuLayers);
    return {
      id: path.resolve(modelPath),
      alias,
      name: path.basename(modelPath),
      path: modelPath,
      directory: path.dirname(modelPath),
      quant,
      sizeGb,
      metadata,
      configSettings,
      registrySource: source,
      estimate,
    };
  }

  private buildTree(models: ModelInfo[]): TreeNode[] {
    const groups = new Map<string, TreeNode>();
    for (const model of models) {
      const relative = path.relative(this.paths.paths.rootDir, model.directory) || '.';
      const parts = relative.split(path.sep).filter(Boolean);
      let currentPath = '';
      let parent: TreeNode[] | undefined;
      parts.forEach((part) => {
        currentPath = currentPath ? `${currentPath}/${part}` : part;
        if (!groups.has(currentPath)) {
          groups.set(currentPath, { id: currentPath, label: part, kind: 'group', children: [] });
          if (parent) parent.push(groups.get(currentPath)!);
        }
        parent = groups.get(currentPath)!.children;
      });
      const leaf: TreeNode = { id: model.id, label: `${model.alias} · ${model.quant}`, kind: 'model', modelId: model.id };
      if (!parts.length) {
        const rootNode = groups.get('root') ?? { id: 'root', label: 'All models', kind: 'group', children: [] };
        rootNode.children ??= [];
        rootNode.children.push(leaf);
        groups.set('root', rootNode);
      } else {
        const key = parts.join('/');
        const group = groups.get(key)!;
        group.children ??= [];
        group.children.push(leaf);
      }
    }
    return [...groups.values()].filter((node) => node.id === 'root' || node.children?.length);
  }
}
