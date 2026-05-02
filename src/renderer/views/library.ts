import type { AppActions, AppState } from '../state.js';
import type { HuggingFaceModelSummary, ModelInfo } from '../../shared/types.js';
import { badge, button, card, el, select } from '../components.js';
import { findSelectedModel } from '../state.js';
import { buildEffectiveModelProfile } from '../../shared/modelProfiles.js';

function groupByRepository(models: ModelInfo[]): Array<[string, ModelInfo[]]> {
  const groups = new Map<string, ModelInfo[]>();
  models.forEach((model) => {
    const repo = model.metadata.repository || 'Unlinked local models';
    groups.set(repo, [...(groups.get(repo) ?? []), model]);
  });
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
}

function groupHfByRepository(results: HuggingFaceModelSummary[]): Array<[string, HuggingFaceModelSummary[]]> {
  const groups = new Map<string, HuggingFaceModelSummary[]>();
  results.forEach((model) => {
    groups.set(model.id, [...(groups.get(model.id) ?? []), model]);
  });
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
}

function modelWikiCard(model: ModelInfo, state: AppState, actions: AppActions): HTMLElement {
  const node = card(model.alias, 'wiki-model-card');
  const selectButton = button('Inspect', () => actions.setSelectedModel(model.id), model.id === state.selectedModelId ? 'secondary active' : 'secondary');
  node.append(
    el('p', 'muted', model.metadata.repository || model.metadata.family || 'No repository linked. GGUF metadata will still be used when present.'),
    el('div', 'button-row')
  );
  (node.querySelector('.button-row') as HTMLElement).append(
    badge(model.quant),
    badge(`${model.sizeGb} GB`),
    badge(model.registrySource),
    selectButton
  );
  if (model.metadata.tags.length) node.append(el('p', 'muted', model.metadata.tags.slice(0, 8).join(' · ')));
  return node;
}

function renderSelectedModelWiki(model: ModelInfo | undefined, state: AppState, actions: AppActions): HTMLElement {
  const article = card('Model wiki');
  if (!model) {
    article.append(
      el('p', 'muted', 'Select an existing local model to see usage guidance, deployment expectations, and Hugging Face metadata.'),
      el('p', 'muted', 'Model cards are metadata-first. Embedded GGUF metadata is used for local files, and Hugging Face enriches cards when a model config or GGUF metadata links a repository.')
    );
    return article;
  }

  const deployButton = button('Deploy this model', actions.launchSelected, 'primary');
  deployButton.disabled = state.launcher.running;

  article.append(
    el('h2', 'wiki-title', model.alias),
    el('p', '', model.metadata.description || 'No Hugging Face description is available for this local model yet.'),
    el('div', 'button-row')
  );
  (article.querySelector('.button-row') as HTMLElement).append(
    badge(model.metadata.repository || 'unlinked'),
    badge(model.metadata.family || 'metadata pending'),
    badge(model.quant),
    deployButton
  );

  const basics = card('What this model is');
  basics.append(
    el('p', 'muted', `Local file: ${model.name}`),
    el('p', 'muted', `Size: ${model.sizeGb} GB · Quant: ${model.quant}`),
    el('p', 'muted', model.metadata.repository ? `Repository metadata source: ${model.metadata.repository}` : 'Repository metadata source: not linked. Embedded GGUF metadata is still used when available.')
  );

  const run = card('How to run it');
  const profile = buildEffectiveModelProfile(model, state.modelProfiles[model.id], state.modelProfileDrafts[model.id]);
  run.append(
    el('p', 'muted', `Estimated footprint: ${model.estimate.totalGb} GB total (${model.estimate.modelGb} GB model + ${model.estimate.kvCacheGb} GB KV cache estimate).`),
    el('p', 'muted', `Current context target: ${profile.CtxSize ?? 'default'}. Lower context to reduce KV memory; raise it only if the model and hardware can handle it.`),
    el('p', 'muted', `GPU layers setting: ${profile.GpuLayers ?? 'default'}. If launch fails or swaps, reduce GPU layers or context size.`)
  );

  const hardware = card('Hardware pointers');
  hardware.append(
    el('p', 'muted', 'Small Q4/Q5 models usually work on modest GPUs or CPU. Large Q6/Q8 models need more VRAM and may need partial offload.'),
    el('p', 'muted', 'Watch Metrics after launch: memory pressure, low token/sec, or repeated slot stalls usually means the context/offload settings are too aggressive.'),
    el('p', 'muted', 'For public cloudflared exposure, configure an API key before launching the server.')
  );

  const tags = card('Model tags');
  tags.append(el('p', 'muted', model.metadata.tags.length ? model.metadata.tags.join(' · ') : 'No tags found in GGUF or Hugging Face metadata for this model.'));

  const gguf = renderGgufMetadata(model);
  article.append(basics, run, hardware, tags);
  if (gguf) article.append(gguf);
  return article;
}

function renderGgufMetadata(model: ModelInfo): HTMLElement | null {
  const entries = [
    ['Name', model.metadata.extra['gguf.general.name']],
    ['Architecture', model.metadata.extra['gguf.general.architecture']],
    ['Size label', model.metadata.extra['gguf.general.size_label']],
    ['File type', model.metadata.extra['gguf.general.file_type']],
    ['Context length', model.metadata.extra[`gguf.${model.metadata.extra['gguf.general.architecture']}.context_length`]],
    ['Embedding length', model.metadata.extra[`gguf.${model.metadata.extra['gguf.general.architecture']}.embedding_length`]],
    ['Block count', model.metadata.extra[`gguf.${model.metadata.extra['gguf.general.architecture']}.block_count`]],
  ].filter((entry): entry is [string, string] => Boolean(entry[1]));

  if (!entries.length && !model.metadata.chatTemplate) return null;

  const gguf = card('Embedded GGUF metadata');
  entries.forEach(([label, value]) => gguf.append(el('p', 'muted', `${label}: ${value}`)));
  if (model.metadata.chatTemplate) gguf.append(el('p', 'muted', 'Chat template: available from GGUF metadata.'));
  return gguf;
}

function renderHuggingFaceModal(state: AppState, actions: AppActions): HTMLElement | null {
  if (!state.hfBrowserOpen) return null;
  const overlay = el('div', 'modal-backdrop');
  const modal = el('section', 'modal-panel hf-browser-modal');
  const header = el('div', 'modal-header');
  header.append(el('h2', 'wiki-title', 'Hugging Face browser'), button('Close', actions.closeHfBrowser, 'secondary'));

  const filters = el('div', 'hf-filters');
  const query = document.createElement('input');
  query.className = 'field-input';
  query.dataset.focusKey = 'input:hf-modal-query';
  query.placeholder = 'Search repositories, e.g. qwen gguf';
  query.value = state.hfQuery;
  query.addEventListener('input', () => actions.setHfQuery(query.value));

  const tag = document.createElement('input');
  tag.className = 'field-input';
  tag.dataset.focusKey = 'input:hf-modal-tag';
  tag.placeholder = 'Filter by tag, e.g. gguf, text-generation-inference';
  tag.value = state.hfTagFilter;
  tag.addEventListener('input', () => actions.setHfTagFilter(tag.value));

  const pipeline = document.createElement('input');
  pipeline.className = 'field-input';
  pipeline.dataset.focusKey = 'input:hf-modal-pipeline';
  pipeline.placeholder = 'Pipeline, e.g. text-generation';
  pipeline.value = state.hfPipelineFilter;
  pipeline.addEventListener('input', () => actions.setHfPipelineFilter(pipeline.value));

  filters.append(
    query,
    tag,
    pipeline,
    select('Order by', state.hfSort, [
      { value: 'downloads', label: 'Downloads' },
      { value: 'likes', label: 'Likes' },
      { value: 'lastModified', label: 'Last modified' },
      { value: 'modelId', label: 'Repository name' },
    ], (value) => actions.setHfSort(value as AppState['hfSort'])),
    button('Search Hugging Face', actions.searchHf, 'primary')
  );

  const results = el('div', 'hf-repo-tree');
  if (!state.hfResults.length) {
    results.append(el('p', 'muted', 'No repositories loaded. Search Hugging Face or adjust filters/tags.'));
  } else {
    groupHfByRepository(state.hfResults).forEach(([repository, repos]) => {
      const ownerCard = card(repository, 'hf-owner-card');
      repos.forEach((repo) => {
        const row = el('article', 'hf-repo-row');
        row.append(
          el('h4', 'card-title', repo.id),
          el('p', 'muted', `${repo.pipelineTag || 'unknown pipeline'} · ${repo.downloads ?? 0} downloads · ${repo.likes ?? 0} likes`),
          el('p', 'muted', repo.tags.slice(0, 12).join(' · ') || 'No tags returned')
        );
        ownerCard.append(row);
      });
      results.append(ownerCard);
    });
  }

  modal.append(header, filters, results);
  overlay.append(modal);
  overlay.addEventListener('click', (event) => {
    if (event.target === overlay) actions.closeHfBrowser();
  });
  return overlay;
}

export function renderLibraryView(state: AppState, actions: AppActions): HTMLElement {
  const root = el('div', 'library-wiki-view');
  const hero = card('Local model wiki', 'wiki-hero');
  hero.append(
    el('p', '', 'Library is for understanding existing local models first: what repository they come from, how they are likely to run, what settings matter, and what hardware pressure to watch.'),
    el('div', 'button-row')
  );
  (hero.querySelector('.button-row') as HTMLElement).append(
    badge(`${state.catalog.models.length} local models`),
    badge(`${groupByRepository(state.catalog.models).length} repository groups`),
    button('Open Hugging Face browser', actions.openHfBrowser, 'primary')
  );

  const model = findSelectedModel(state);
  const modelList = card('Existing models', 'wiki-index');
  groupByRepository(state.catalog.models).forEach(([repo, models]) => {
    const group = card(repo, 'wiki-repo-group');
    models.forEach((item) => group.append(modelWikiCard(item, state, actions)));
    modelList.append(group);
  });

  const details = renderSelectedModelWiki(model, state, actions);
  const modal = renderHuggingFaceModal(state, actions);
  root.append(hero, el('div', 'wiki-layout'));
  (root.querySelector('.wiki-layout') as HTMLElement).append(modelList, details);
  if (modal) root.append(modal);
  return root;
}
