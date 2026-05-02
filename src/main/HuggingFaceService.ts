import type { HuggingFaceModelSummary, HuggingFaceSearchRequest } from '../shared/types';

function toSummary(item: Record<string, unknown>): HuggingFaceModelSummary {
  return {
    id: String(item.id ?? item.modelId ?? ''),
    likes: typeof item.likes === 'number' ? item.likes : undefined,
    downloads: typeof item.downloads === 'number' ? item.downloads : undefined,
    pipelineTag: typeof item.pipeline_tag === 'string' ? item.pipeline_tag : undefined,
    tags: Array.isArray(item.tags) ? item.tags.map(String) : [],
    siblingCount: typeof item.siblingCount === 'number' ? item.siblingCount : undefined,
    author: typeof item.author === 'string' ? item.author : undefined,
    lastModified: typeof item.lastModified === 'string' ? item.lastModified : undefined,
  };
}

async function fetchJson(url: string, timeoutMs = 10_000): Promise<unknown> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { headers: { accept: 'application/json' }, signal: controller.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  } finally {
    clearTimeout(timeout);
  }
}

export class HuggingFaceService {
  async getModel(modelId: string): Promise<HuggingFaceModelSummary | null> {
    const id = modelId.trim();
    if (!id || !id.includes('/')) return null;
    try {
      const encodedId = id.split('/').map(encodeURIComponent).join('/');
      const data = await fetchJson(`https://huggingface.co/api/models/${encodedId}`) as Record<string, unknown>;
      return toSummary(data);
    } catch {
      return null;
    }
  }

  async search(request: string | HuggingFaceSearchRequest): Promise<HuggingFaceModelSummary[]> {
    const options = typeof request === 'string' ? { query: request } : request;
    const q = options.query.trim();
    const limit = Math.max(10, Math.min(100, options.limit ?? 50));
    try {
      const params = new URLSearchParams({ search: q || 'gguf', limit: String(limit), full: 'false' });
      if (options.tag) params.append('filter', options.tag);
      if (options.pipeline) params.append('pipeline_tag', options.pipeline);
      if (options.sort) {
        params.append('sort', options.sort);
        params.append('direction', '-1');
      }
      const url = `https://huggingface.co/api/models?${params.toString()}`;
      const data = await fetchJson(url) as Array<Record<string, unknown>>;
      return data.map(toSummary).filter((item) => item.id);
    } catch {
      return [];
    }
  }
}
