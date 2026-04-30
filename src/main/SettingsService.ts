import { DEFAULT_SETTINGS, normalizeSettings } from '../shared/defaults';
import type { LlamaServerSettings } from '../shared/types';
import { JsonStore } from './JsonStore';
import type { AppPaths } from './AppPaths';

export class SettingsService {
  constructor(private readonly paths: AppPaths, private readonly store: JsonStore) {}

  private diffFromDefaults(settings: LlamaServerSettings): Partial<LlamaServerSettings> {
    const overrides: Partial<LlamaServerSettings> = {};
    (Object.keys(DEFAULT_SETTINGS) as (keyof LlamaServerSettings)[]).forEach((key) => {
      if (!Object.is(settings[key], DEFAULT_SETTINGS[key])) {
        (overrides as Record<keyof LlamaServerSettings, LlamaServerSettings[keyof LlamaServerSettings]>)[key] = settings[key];
      }
    });
    return overrides;
  }

  async load(): Promise<LlamaServerSettings> {
    const saved = await this.store.read<Partial<LlamaServerSettings>>(this.paths.paths.settingsFile, {});
    return normalizeSettings(saved);
  }

  async loadOverrides(): Promise<Partial<LlamaServerSettings>> {
    const saved = await this.store.read<Partial<LlamaServerSettings>>(this.paths.paths.settingsFile, {});
    return this.diffFromDefaults(normalizeSettings(saved));
  }

  async save(settings: Partial<LlamaServerSettings>): Promise<LlamaServerSettings> {
    const merged = normalizeSettings(settings);
    await this.store.write(this.paths.paths.settingsFile, this.diffFromDefaults(merged));
    return merged;
  }

  async reset(): Promise<LlamaServerSettings> {
    await this.store.write(this.paths.paths.settingsFile, {});
    return DEFAULT_SETTINGS;
  }
}
