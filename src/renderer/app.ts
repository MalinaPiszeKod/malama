import type { AppActions, AppState } from './state.js';
import { button, el } from './components.js';
import { renderDeployView } from './views/deploy.js';
import { renderLibraryView } from './views/library.js';
import { renderChatView } from './views/chat.js';
import { renderSettingsView } from './views/settings.js';
import { renderMetricsView } from './views/metrics.js';

export function renderApp(state: AppState, actions: AppActions): HTMLElement {
  const shell = el('div', 'app-shell');
  const topbar = el('header', 'topbar');
  const logoWrap = el('div', 'brand');
  const logo = document.createElement('img');
  logo.className = 'app-logo';
  logo.src = '../resources/images/logo.png';
  logo.alt = 'malama';
  logoWrap.append(logo, el('div', 'brand-text', "malama - Malina's Llama Launcher"));
  const nav = el('nav', 'nav-tabs');
  ([['deploy', 'Deploy'], ['library', 'Library'], ['chat', 'Chat'], ['settings', 'Settings'], ['metrics', 'Metrics']] as const).forEach(([id, label]) => {
    nav.append(button(label, () => actions.setView(id), `nav ${state.view === id ? 'active' : ''}`));
  });
  topbar.append(logoWrap, nav);

  const content = el('section', 'content');
  switch (state.view) {
    case 'deploy': content.append(renderDeployView(state, actions)); break;
    case 'library': content.append(renderLibraryView(state, actions)); break;
    case 'chat': content.append(renderChatView(state, actions)); break;
    case 'settings': content.append(renderSettingsView(state, actions)); break;
    case 'metrics': content.append(renderMetricsView(state, actions)); break;
  }

  shell.append(topbar, content);
  return shell;
}
