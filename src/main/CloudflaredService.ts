import { execFile } from 'node:child_process';
import { spawn } from 'node:child_process';
import type { ChildProcess } from 'node:child_process';
import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import path from 'node:path';
import type { CloudflaredTunnelSnapshot } from '../shared/types';
import type { AppPaths } from './AppPaths';

const TRY_CLOUDFLARE_URL = /https:\/\/[a-zA-Z0-9.-]+\.trycloudflare\.com/g;
const CLOUDFLARED_VERSION = '2026.3.0';
const WINDOWS_AMD64_DOWNLOAD = {
  url: `https://github.com/cloudflare/cloudflared/releases/download/${CLOUDFLARED_VERSION}/cloudflared-windows-amd64.exe`,
  sha256: '59b12880b24af581cf5b1013db601c7d843b9b097e9c78aa5957c7f39f741885',
};

function runWhere(command: string): Promise<string | null> {
  return new Promise((resolve) => {
    execFile('where.exe', [command], { windowsHide: true }, (error, stdout) => {
      if (error) {
        resolve(null);
        return;
      }
      const first = stdout.split(/\r?\n/).map((line) => line.trim()).find(Boolean);
      resolve(first ?? null);
    });
  });
}

function normalizeTunnelHost(host: string): string {
  const trimmed = host.trim().toLowerCase();
  return trimmed === '0.0.0.0' || trimmed === '::' ? '127.0.0.1' : host.trim();
}

export class CloudflaredService {
  private process?: ChildProcess;
  private starting = false;
  private executablePath?: string;
  private installing = false;
  private targetUrl?: string;
  private publicUrl?: string;
  private startedAt?: number;
  private stdoutTail: string[] = [];
  private error?: string;

  constructor(private readonly paths: AppPaths) {}

  get bundledPath(): string {
    return path.join(this.paths.paths.toolsDir, 'cloudflared.exe');
  }

  async getStatus(): Promise<CloudflaredTunnelSnapshot> {
    await this.locateExecutable();
    return this.snapshot;
  }

  get snapshot(): CloudflaredTunnelSnapshot {
    return {
      installed: Boolean(this.executablePath),
      installing: this.installing,
      running: Boolean(this.process),
      ...(this.executablePath ? { executablePath: this.executablePath } : {}),
      ...(this.targetUrl ? { targetUrl: this.targetUrl } : {}),
      ...(this.publicUrl ? { publicUrl: this.publicUrl } : {}),
      ...(this.process?.pid ? { pid: this.process.pid } : {}),
      ...(this.startedAt ? { startedAt: this.startedAt } : {}),
      stdoutTail: this.stdoutTail,
      ...(this.error ? { error: this.error } : {}),
    };
  }

  async install(): Promise<CloudflaredTunnelSnapshot> {
    if (this.installing) return this.snapshot;
    this.installing = true;
    this.error = undefined;
    try {
      await fs.mkdir(this.paths.paths.toolsDir, { recursive: true });
      if (process.arch !== 'x64') throw new Error('Automatic cloudflared helper install currently supports Windows x64 only. Install cloudflared manually and add it to PATH.');
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 120_000);
      try {
        const response = await fetch(WINDOWS_AMD64_DOWNLOAD.url, { signal: controller.signal });
        if (!response.ok) throw new Error(`cloudflared download failed: HTTP ${response.status}`);
        const payload = Buffer.from(await response.arrayBuffer());
        const digest = crypto.createHash('sha256').update(payload).digest('hex');
        if (digest !== WINDOWS_AMD64_DOWNLOAD.sha256) throw new Error('cloudflared checksum verification failed.');
        await fs.writeFile(this.bundledPath, payload);
      } finally {
        clearTimeout(timeout);
      }
      this.executablePath = this.bundledPath;
    } catch (error) {
      this.error = error instanceof Error ? error.message : 'Unable to install cloudflared.';
    } finally {
      this.installing = false;
    }
    return this.snapshot;
  }

  async start(host: string, port: number): Promise<CloudflaredTunnelSnapshot> {
    if (this.process || this.starting) return this.snapshot;
    this.starting = true;
    this.error = undefined;
    const executable = await this.locateExecutable();
    if (!executable) {
      this.error = 'cloudflared was not found. Install the helper first.';
      this.starting = false;
      return this.snapshot;
    }

    const safePort = Number(port);
    if (!Number.isInteger(safePort) || safePort < 1 || safePort > 65_535) {
      this.error = 'Invalid server port for tunnel.';
      this.starting = false;
      return this.snapshot;
    }

    this.targetUrl = `http://${normalizeTunnelHost(host)}:${safePort}`;
    this.publicUrl = undefined;
    this.stdoutTail = [];
    this.startedAt = Date.now();

    let child: ChildProcess;
    try {
      child = spawn(executable, ['tunnel', '--no-autoupdate', '--url', this.targetUrl], {
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true,
        shell: false,
      });
    } catch (error) {
      this.error = error instanceof Error ? error.message : 'Unable to start cloudflared.';
      this.starting = false;
      return this.snapshot;
    }
    this.process = child;
    this.starting = false;

    const pushLine = (chunk: Buffer) => {
      const text = chunk.toString('utf8');
      const match = text.match(TRY_CLOUDFLARE_URL);
      if (match?.[0]) this.publicUrl = match[0];
      const lines = text.split(/\r?\n/).filter(Boolean);
      this.stdoutTail = [...this.stdoutTail, ...lines].slice(-30);
    };

    child.stdout?.on('data', pushLine);
    child.stderr?.on('data', pushLine);
    child.on('error', (error) => {
      this.error = error.message;
      if (this.process === child) this.process = undefined;
      this.starting = false;
    });
    child.on('exit', (code, signal) => {
      if (this.process === child) this.process = undefined;
      if (!this.error && code && code !== 0) this.error = `cloudflared exited with code ${code}`;
      if (!this.error && signal) this.error = `cloudflared exited after signal ${signal}`;
    });

    await this.waitForPublicUrl(15_000);
    return this.snapshot;
  }

  async stop(): Promise<CloudflaredTunnelSnapshot> {
    if (!this.process) return this.snapshot;
    const child = this.process;
    let didExit = false;
    const exited = new Promise<void>((resolve) => {
      const markExited = () => {
        didExit = true;
        resolve();
      };
      child.once('close', markExited);
      child.once('exit', markExited);
    });
    if (!child.kill()) {
      this.error = 'Unable to stop cloudflared.';
      return this.snapshot;
    }
    await Promise.race([exited, new Promise((resolve) => setTimeout(resolve, 5000))]);
    if (!didExit) {
      this.error = 'Timed out while stopping cloudflared; process may still be running.';
      return this.snapshot;
    }
    if (this.process === child) this.process = undefined;
    this.error = undefined;
    return this.snapshot;
  }

  private async waitForPublicUrl(timeoutMs: number): Promise<void> {
    const start = Date.now();
    while (!this.publicUrl && this.process && Date.now() - start < timeoutMs) {
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
  }

  private async locateExecutable(): Promise<string | null> {
    if (this.executablePath) return this.executablePath;
    const envPath = process.env.CLOUDFLARED_EXE?.trim();
    if (envPath && await this.exists(envPath)) {
      this.executablePath = envPath;
      return envPath;
    }
    if (await this.exists(this.bundledPath)) {
      this.executablePath = this.bundledPath;
      return this.bundledPath;
    }
    const fromPath = await runWhere('cloudflared.exe') ?? await runWhere('cloudflared');
    if (fromPath && await this.exists(fromPath)) {
      this.executablePath = fromPath;
      return fromPath;
    }
    this.executablePath = undefined;
    return null;
  }

  private async exists(filePath: string): Promise<boolean> {
    try {
      await fs.access(filePath);
      return true;
    } catch {
      return false;
    }
  }
}
