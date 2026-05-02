import { spawn } from 'node:child_process';
import type { ChildProcess } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import type { LauncherSnapshot, ModelInfo, ModelProfileConfig, RunningModelSnapshot, RuntimeDeploymentState, ServerSettings } from '../shared/types';
import { buildLaunchPlan } from '../shared/commandBuilder';
import { normalizeModelProfileConfig, normalizeServerSettings } from '../shared/defaults';
import { JsonStore } from './JsonStore';
import type { AppPaths } from './AppPaths';

interface LauncherConfig {
  executablePath?: string;
}

export class LauncherService {
  private running?: {
    process: ChildProcess;
    snapshot: RunningModelSnapshot;
    modelId?: string;
    modelName?: string;
    host: string;
    port: number;
    apiKeyConfigured: boolean;
    deployment: RuntimeDeploymentState;
  };
  private executablePath: string;
  private lastError?: string;
  private launching = false;
  private readonly stopping = new WeakSet<ChildProcess>();

  constructor(private readonly paths: AppPaths, private readonly store: JsonStore) {
    this.executablePath = path.join(paths.paths.rootDir, 'llama-server.exe');
  }

  async initialize(): Promise<void> {
    const saved = await this.store.read<LauncherConfig>(this.paths.paths.launcherFile, {});
    this.executablePath = process.env.LLAMA_SERVER_EXE?.trim() || saved.executablePath || this.executablePath;
  }

  async loadExecutablePath(): Promise<string> {
    await this.initialize();
    return this.executablePath;
  }

  async saveExecutablePath(executablePath: string): Promise<void> {
    const normalized = executablePath.trim();
    if (path.basename(normalized).toLowerCase() !== 'llama-server.exe') {
      throw new Error('Executable must be llama-server.exe');
    }
    await fs.access(normalized);
    this.executablePath = normalized;
    await this.store.write(this.paths.paths.launcherFile, { executablePath: normalized });
  }

  get snapshot(): LauncherSnapshot {
    if (!this.running) {
      return {
        running: false,
        executablePath: this.executablePath,
        ...(this.lastError ? { error: this.lastError } : {}),
      };
    }
    return {
      running: true,
      modelId: this.running.modelId,
      modelName: this.running.modelName,
      host: this.running.host,
      port: this.running.port,
      apiKeyConfigured: this.running.apiKeyConfigured,
      executablePath: this.executablePath,
      mode: this.running.deployment.mode,
      deployment: this.running.deployment,
      process: this.running.snapshot,
      ...(this.lastError ? { error: this.lastError } : {}),
    };
  }

  async start(model: ModelInfo | null, serverSettings: Partial<ServerSettings>, modelProfile: Partial<ModelProfileConfig> = {}): Promise<LauncherSnapshot> {
    if (this.running || this.launching) {
      this.lastError = 'Stop the running model before launching another.';
      return this.snapshot;
    }
    this.launching = true;
    let executablePath: string;
    let effectiveServer: ServerSettings;
    let effectiveProfile: ModelProfileConfig;
    let cwd: string;
    try {
      await this.initialize();
      executablePath = this.executablePath;
      effectiveServer = normalizeServerSettings(serverSettings);
      effectiveProfile = normalizeModelProfileConfig({ ...(model?.configSettings ?? {}), ...modelProfile });
      cwd = effectiveServer.DefaultWorkingDirectory.trim() || model?.directory || path.dirname(executablePath);
      if (path.basename(executablePath).toLowerCase() !== 'llama-server.exe') throw new Error('Executable must be llama-server.exe');
      await fs.access(executablePath);
      await fs.access(cwd);
      if (model?.path && !effectiveServer.MultiModel) await fs.access(model.path);
    } catch (error) {
      this.lastError = error instanceof Error ? error.message : 'Unable to access executable, model, or working directory.';
      this.launching = false;
      return this.snapshot;
    }

    let plan;
    let child: ChildProcess;
    try {
      plan = buildLaunchPlan(executablePath, model?.path, effectiveServer, effectiveProfile);
      child = spawn(executablePath, plan.argv, {
        cwd,
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true,
        shell: false,
      });
    } catch (error) {
      this.lastError = error instanceof Error ? error.message : 'Unable to launch llama-server.';
      this.launching = false;
      return this.snapshot;
    }
    const snapshot: RunningModelSnapshot = {
      pid: child.pid ?? 0,
      redactedCommandText: plan.redactedCommandText,
      redactedArgs: plan.redactedArgv,
      cwd,
      startedAt: Date.now(),
      stdoutTail: [],
    };
    const deployment: RuntimeDeploymentState = {
      mode: plan.deployment.mode,
      health: 'unknown',
      deployments: effectiveServer.MultiModel ? [] : [{
        ...(model?.id ? { modelId: model.id } : {}),
        ...(model?.name ? { modelName: model.name } : {}),
        ...(effectiveProfile.Alias ? { alias: effectiveProfile.Alias } : {}),
        endpoint: `http://${effectiveServer.Host}:${effectiveServer.Port}`,
        status: 'starting',
      }],
    };
    this.running = {
      process: child,
      snapshot,
      ...(model?.id ? { modelId: model.id } : {}),
      ...(model?.name ? { modelName: model.name } : {}),
      host: effectiveServer.Host,
      port: effectiveServer.Port,
      apiKeyConfigured: Boolean(effectiveServer.ApiKey.trim()),
      deployment,
    };
    this.launching = false;
    this.lastError = undefined;
    const pushLine = (chunk: Buffer) => {
      const lines = chunk.toString('utf8').split(/\r?\n/).filter(Boolean);
      snapshot.stdoutTail = [...snapshot.stdoutTail, ...lines].slice(-20);
    };
    child.stdout?.on('data', pushLine);
    child.stderr?.on('data', pushLine);
    child.on('error', (error) => {
      this.lastError = error.message;
      snapshot.stdoutTail = [...snapshot.stdoutTail, error.message].slice(-20);
      if (this.running?.process === child) this.running = undefined;
    });
    child.on('exit', (code, signal) => {
      if (this.running?.process === child) this.running = undefined;
      if (!this.stopping.has(child)) {
        if (signal) this.lastError = `llama-server exited after signal ${signal}`;
        else if (code && code !== 0) this.lastError = `llama-server exited with code ${code}`;
      }
      this.stopping.delete(child);
    });
    return this.snapshot;
  }

  async stop(): Promise<LauncherSnapshot> {
    if (!this.running) return this.snapshot;
    const child = this.running.process;
    let didExit = false;
    const exited = new Promise<void>((resolve) => {
      const markExited = () => {
        didExit = true;
        resolve();
      };
      child.once('close', markExited);
      child.once('exit', markExited);
    });
    this.stopping.add(child);
    this.lastError = undefined;
    if (!child.kill()) {
      this.stopping.delete(child);
      this.lastError = 'Unable to stop llama-server process.';
      return this.snapshot;
    }
    await Promise.race([exited, new Promise((resolve) => setTimeout(resolve, 5000))]);
    if (!didExit) {
      this.lastError = 'Timed out while stopping llama-server; process may still be running.';
      return this.snapshot;
    }
    if (this.running?.process === child) this.running = undefined;
    return this.snapshot;
  }

  async ensureExecutableExists(): Promise<boolean> {
    try {
      await fs.access(await this.loadExecutablePath());
      return true;
    } catch {
      return false;
    }
  }

  async getExecutablePath(): Promise<string> {
    await this.initialize();
    return this.executablePath;
  }
}
