import type { AppActions, AppState } from '../state.js';
import { badge, button, card, el, select, tabs, tree } from '../components.js';
import { findSelectedModel } from '../state.js';

export function renderLibraryView(state: AppState, actions: AppActions): HTMLElement {
  const root = el('div', 'view-grid library-view');
  const left = el('aside', 'panel');
  left.append(card('Local model tree'), tree(state.catalog.tree, actions.setSelectedModel, state.selectedModelId));

  const model = findSelectedModel(state);
  const center = el('main', 'panel');
  const queryRow = el('div', 'search-row');
  const input = document.createElement('input');
  input.className = 'field-input';
  input.dataset.focusKey = 'input:hugging-face-search';
  input.value = state.hfQuery;
  input.placeholder = 'Search Hugging Face';
  input.addEventListener('input', () => actions.setHfQuery(input.value));
  queryRow.append(input, button('Search', () => actions.searchHf(state.hfQuery), 'primary'));

  const hfList = el('div', 'stack');
  state.hfResults.slice(0, 8).forEach((item) => {
    const entry = card(item.id, 'huggingface-item');
    entry.append(
      el('div', 'muted', item.pipelineTag || 'text-generation'),
      el('div', 'muted', item.tags.slice(0, 4).join(' · ')),
      badge(item.author || 'hf')
    );
    hfList.append(entry);
  });

  const activeTab = state.libraryTab;
  const hfCard = card('Hugging Face browser');
  hfCard.append(queryRow, hfList);
  center.append(
    hfCard,
    tabs([
      { id: 'description', label: 'Description' },
      { id: 'metadata', label: 'Metadata' },
      { id: 'estimate', label: 'Deployment estimate' },
    ], activeTab, (value) => actions.setLibraryTab(value as AppState['libraryTab']))
  );

  const info = card('Model details');
  if (!model) {
    info.append(el('p', 'muted', 'Select a model to inspect details.'));
  } else if (activeTab === 'description') {
    info.append(el('p', '', model.metadata.description || 'No description available.'), badge(model.quant));
  } else if (activeTab === 'metadata') {
    const grid = el('div', 'kv-grid');
    info.append(grid);
    [['Alias', model.alias], ['Path', model.path], ['Directory', model.directory], ['Quant', model.quant], ['Size GB', String(model.sizeGb)]].forEach(([key, value]) => {
      grid.append(el('div', 'kv-item', `${key}: ${value}`));
    });
  } else {
    info.append(
      el('div', 'stack', `${model.estimate.totalGb} GB total`),
      el('p', 'muted', model.estimate.notes.join(' · '))
    );
  }
  center.append(info);

  const right = card('Selected model');
  const deployButton = button('Deploy selected', actions.launchSelected, 'primary');
  deployButton.disabled = !model || state.launcher.running;
  right.append(
    select('View', activeTab, [
      { value: 'description', label: 'Description' },
      { value: 'metadata', label: 'Metadata' },
      { value: 'estimate', label: 'Deployment estimate' },
    ], (value) => actions.setLibraryTab(value as AppState['libraryTab'])),
    deployButton
  );
  right.append(el('div', 'muted', model?.metadata.chatTemplate || 'Select a local model to deploy or inspect.'));

  root.append(left, center, right);
  return root;
}
