import type { AppActions, AppState } from '../state.js';
import { badge, button, card, el, metricTile, tree } from '../components.js';
import { findSelectedModel } from '../state.js';

function settingsGroup(title: string, pairs: Array<[string, string | number | boolean]>): HTMLElement {
  const section = card(title, 'settings-group');
  const grid = el('div', 'kv-grid');
  pairs.forEach(([label, value]) => {
    grid.append(el('div', 'kv-item', `${label}: ${String(value)}`));
  });
  section.append(grid);
  return section;
}

export function renderDeployView(state: AppState, actions: AppActions): HTMLElement {
  const root = el('div', 'view-grid deploy-view');
  const left = el('aside', 'panel');
  left.append(card('Model tree'), tree(state.catalog.tree, actions.setSelectedModel, state.selectedModelId));

  const model = findSelectedModel(state);
  const center = el('main', 'panel');
  const launcher = card('Running model');
  const startButton = button('Start', actions.launchSelected, 'primary');
  startButton.disabled = !model || state.launcher.running;
  const stopButton = button('Stop', actions.stopLaunch, 'danger');
  stopButton.disabled = !state.launcher.running;
  launcher.append(
    el('div', 'stack', state.launcher.running ? 'Model server running' : 'No active launch'),
    metricTile('Executable', state.launcher.executablePath || 'Not selected'),
    metricTile('Endpoint', `${state.launcher.host ?? state.settings.Host}:${state.launcher.port ?? state.settings.Port}`, state.launcher.running ? 'Listening' : 'Ready'),
    el('div', 'button-row')
  );
  (launcher.querySelector('.button-row') as HTMLElement).append(
    button('Choose executable', actions.chooseExecutable, 'secondary'),
    startButton,
    stopButton
  );
  if (state.launcher.error) launcher.append(el('p', 'muted', state.launcher.error));
  if (state.launcher.process?.stdoutTail.length) {
    const log = el('pre', 'log-block', state.launcher.process.stdoutTail.join('\n'));
    launcher.append(log);
  }

  const selected = card('Selected model');
  selected.append(
    metricTile('Alias', model?.alias || '—'),
    metricTile('Name', model?.name || '—'),
    metricTile('Quant', model?.quant || '—'),
    metricTile('Size', model ? `${model.sizeGb} GB` : '—'),
    metricTile('Estimate', model ? `${model.estimate.totalGb} GB total` : '—')
  );
  if (model) {
    selected.append(el('p', 'muted', model.metadata.description || 'No metadata available.'));
    selected.append(badge(model.registrySource));
  } else {
    selected.append(el('p', 'muted', 'No model selected. Choose a model from the tree before launching.'));
  }
  center.append(launcher, selected);

  const right = el('aside', 'panel');
  right.append(
    settingsGroup('Runtime', [['Host', state.settings.Host], ['Port', state.settings.Port], ['Threads', state.settings.Threads], ['Ctx', state.settings.CtxSize]]),
    settingsGroup('Sampling', [['Temp', state.settings.Temp], ['Top P', state.settings.TopP], ['Top K', state.settings.TopK], ['Repeat Penalty', state.settings.RepeatPenalty]]),
    settingsGroup('Server', [['Web UI', state.settings.Webui], ['Metrics', state.settings.Metrics], ['Cont batching', state.settings.ContBatching], ['Thinking', state.settings.Thinking]])
  );

  root.append(left, center, right);
  return root;
}
