import type { HuggingFaceModelSummary } from '../shared/types';
import { RECOMMENDED_MODELS } from '../shared/defaults';

export class HuggingFaceService {
  async search(query: string): Promise<HuggingFaceModelSummary[]> {
    const q = query.trim();
    try {
      const url = `https://huggingface.co/api/models?search=${encodeURIComponent(q)}&limit=20`;
      const response = await fetch(url, { headers: { accept: 'application/json' } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json() as Array<Record<string, unknown>>;
      return data.map((item) => ({
        id: String(item.id ?? ''),
        likes: typeof item.likes === 'number' ? item.likes : undefined,
        downloads: typeof item.downloads === 'number' ? item.downloads : undefined,
        pipelineTag: typeof item.pipeline_tag === 'string' ? item.pipeline_tag : undefined,
        tags: Array.isArray(item.tags) ? item.tags.map(String) : [],
        siblingCount: typeof item.siblingCount === 'number' ? item.siblingCount : undefined,
        author: typeof item.author === 'string' ? item.author : undefined,
        lastModified: typeof item.lastModified === 'string' ? item.lastModified : undefined,
      }));
    } catch {
      return RECOMMENDED_MODELS
        .filter((item) => !q || `${item.Name} ${item.Id} ${item.BestFor}`.toLowerCase().includes(q.toLowerCase()))
        .map((item) => ({
          id: item.Id,
          likes: undefined,
          downloads: undefined,
          pipelineTag: 'text-generation',
          tags: ['gguf', 'recommended'],
          siblingCount: 0,
          author: 'curated',
          lastModified: undefined,
        }));
    }
  }
}
