import type { AppActions, AppState } from '../state.js';
import { card, el, metricTile } from '../components.js';

export function renderMetricsView(state: AppState, _actions: AppActions): HTMLElement {
  const root = el('div', 'metrics-layout');
  root.append(
    metricTile('Server', state.metrics.server.reachable ? 'reachable' : 'offline', state.metrics.timestamp),
    metricTile('CPU', `${state.metrics.system.cpuCount} cores`, `${state.metrics.system.loadAvg.map((n) => n.toFixed(2)).join(' / ')}`),
    metricTile('Memory', `${state.metrics.system.usedMemMb} / ${state.metrics.system.totalMemMb} MB`, `${state.metrics.system.freeMemMb} MB free`),
    metricTile('Launcher', state.launcher.running ? 'running' : 'stopped', state.launcher.modelName || 'idle')
  );

  const slots = card('Slots');
  state.metrics.server.slots.forEach((slot) => {
    slots.append(el('div', 'kv-item', `Slot ${slot.id}: ${slot.state} ${slot.speedTps ? `· ${slot.speedTps} tps` : ''}`));
  });
  if (!state.metrics.server.slots.length) slots.append(el('div', 'muted', 'No slot data available.'));

  const raw = card('Raw metrics');
  raw.append(el('pre', 'log-block', state.metrics.server.metricsText || 'No /metrics response yet.'));

  root.append(slots, raw);
  return root;
}
