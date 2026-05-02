import { DEFAULT_SERVER_SETTINGS, diffModelProfileConfig, diffServerSettings, normalizeModelProfileConfig, normalizeServerSettings } from '../shared/defaults';
import type { LlamaServerSettings, ModelProfileConfig, ServerSettings } from '../shared/types';
import { JsonStore } from './JsonStore';
import type { AppPaths } from './AppPaths';

interface PersistedAppSettings {
  server?: Partial<ServerSettings>;
  modelProfiles?: Record<string, Partial<ModelProfileConfig>>;
}

function looksLikeNestedSettings(value: unknown): value is PersistedAppSettings {
  return Boolean(value && typeof value === 'object' && ('server' in value || 'modelProfiles' in value));
}

export class SettingsService {
  constructor(private readonly paths: AppPaths, private readonly store: JsonStore) {}

  private async readPersisted(): Promise<PersistedAppSettings> {
    const saved = await this.store.read<Record<string, unknown>>(this.paths.paths.settingsFile, {});
    if (looksLikeNestedSettings(saved)) {
      return {
        server: saved.server as Partial<ServerSettings> | undefined,
        modelProfiles: saved.modelProfiles as Record<string, Partial<ModelProfileConfig>> | undefined,
      };
    }

    // Migration path for the old flat LlamaServerSettings file: server-owned keys
    // stay global, model-owned keys become app-wide defaults only when explicitly
    // present in old settings.
    const legacy = saved as Partial<LlamaServerSettings>;
    return { server: normalizeServerSettings(legacy), modelProfiles: {} };
  }

  private async writePersisted(next: PersistedAppSettings): Promise<void> {
    await this.store.write(this.paths.paths.settingsFile, {
      server: diffServerSettings(normalizeServerSettings(next.server)),
      modelProfiles: next.modelProfiles ?? {},
    });
  }

  async load(): Promise<ServerSettings> {
    const saved = await this.readPersisted();
    return normalizeServerSettings(saved.server);
  }

  async loadOverrides(): Promise<Partial<ServerSettings>> {
    return diffServerSettings(await this.load());
  }

  async loadModelProfiles(): Promise<Record<string, Partial<ModelProfileConfig>>> {
    const saved = await this.readPersisted();
    const profiles: Record<string, Partial<ModelProfileConfig>> = {};
    Object.entries(saved.modelProfiles ?? {}).forEach(([modelId, profile]) => {
      profiles[modelId] = diffModelProfileConfig(normalizeModelProfileConfig(profile));
    });
    return profiles;
  }

  async save(settings: Partial<ServerSettings>): Promise<ServerSettings> {
    const saved = await this.readPersisted();
    const merged = normalizeServerSettings(settings);
    await this.writePersisted({ server: merged, modelProfiles: saved.modelProfiles ?? {} });
    return merged;
  }

  async saveModelProfile(modelId: string, profile: Partial<ModelProfileConfig>): Promise<Record<string, Partial<ModelProfileConfig>>> {
    const saved = await this.readPersisted();
    const profiles = { ...(saved.modelProfiles ?? {}) };
    profiles[modelId] = diffModelProfileConfig(normalizeModelProfileConfig(profile));
    await this.writePersisted({ server: saved.server ?? DEFAULT_SERVER_SETTINGS, modelProfiles: profiles });
    return profiles;
  }

  async reset(): Promise<ServerSettings> {
    const saved = await this.readPersisted();
    await this.writePersisted({ server: {}, modelProfiles: saved.modelProfiles ?? {} });
    return DEFAULT_SERVER_SETTINGS;
  }
}
