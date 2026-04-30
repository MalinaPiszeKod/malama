import os from 'node:os';
import type { LauncherSnapshot, MetricSnapshot, SlotSnapshot } from '../shared/types';

async function fetchText(url: string): Promise<string | undefined> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 2000);
  try {
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) return undefined;
    return await res.text();
  } catch {
    return undefined;
  } finally {
    clearTimeout(timeout);
  }
}

function parseSlots(payload?: string): SlotSnapshot[] {
  if (!payload) return [];
  try {
    const parsed = JSON.parse(payload) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.map((item, index) => {
      const obj = item as Record<string, unknown>;
      return {
        id: Number(obj.id ?? index),
        state: String(obj.state ?? obj.status ?? 'unknown'),
        tokens: typeof obj.tokens === 'number' ? obj.tokens : undefined,
        promptTokens: typeof obj.prompt_tokens === 'number' ? obj.prompt_tokens : undefined,
        generationTokens: typeof obj.generation_tokens === 'number' ? obj.generation_tokens : undefined,
        speedTps: typeof obj.speed_tps === 'number' ? obj.speed_tps : undefined,
      };
    });
  } catch {
    return [];
  }
}

export class MetricsService {
  async collect(launcher: LauncherSnapshot): Promise<MetricSnapshot> {
    const host = launcher.host || '127.0.0.1';
    const port = launcher.port || 1234;
    const base = `http://${host}:${port}`;
    const [metricsText, slotsText] = await Promise.all([
      fetchText(`${base}/metrics`),
      fetchText(`${base}/slots`),
    ]);
    return {
      timestamp: new Date().toISOString(),
      server: {
        reachable: Boolean(metricsText || slotsText),
        metricsText,
        slots: parseSlots(slotsText),
      },
      system: {
        platform: os.platform(),
        arch: os.arch(),
        cpuCount: os.cpus().length,
        loadAvg: os.loadavg(),
        totalMemMb: Math.round(os.totalmem() / 1024 / 1024),
        freeMemMb: Math.round(os.freemem() / 1024 / 1024),
        usedMemMb: Math.round((os.totalmem() - os.freemem()) / 1024 / 1024),
        uptimeSec: Math.round(os.uptime()),
      },
      launcher,
    };
  }
}
