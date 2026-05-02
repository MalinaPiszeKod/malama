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
  logo.alt = 'Malina logo';
  logoWrap.append(logo, el('div', 'brand-text', "Malina's Llama Launcher"));
  const nav = el('nav', 'nav-tabs');
  ([['deploy', 'Deploy'], ['library', 'Library'], ['chat', 'Chat'], ['settings', 'Settings'], ['metrics', 'Metrics']] as const).forEach(([id, label]) => {
    nav.append(button(label, () => actions.setView(id), `nav ${state.view === id ? 'active' : ''}`));
  });
  const serverHost = state.launcher.host ?? state.settingsDraft.Host;
  const serverPort = state.launcher.port ?? state.settingsDraft.Port;
  const serverUrl = `http://${serverHost}:${serverPort}`;
  const serverControls = el('div', 'topbar-server');
  serverControls.append(
    el('div', `topbar-server-meta ${state.launcher.running ? 'running' : 'stopped'}`, state.launcher.running ? 'Server running' : 'Server stopped'),
    el('div', 'topbar-server-url', serverUrl),
    el('div', 'button-row topbar-buttons')
  );
  const buttonRow = serverControls.querySelector('.button-row') as HTMLElement;
  buttonRow.append(
    button('Launch', actions.launchSelected, 'primary'),
    button('Stop', actions.stopLaunch, 'danger'),
    button('Copy URL', actions.copyServerUrl, 'secondary')
  );
  (buttonRow.children[0] as HTMLButtonElement).disabled = (!state.selectedModelId && !state.settingsDraft.MultiModel) || state.launcher.running;
  (buttonRow.children[1] as HTMLButtonElement).disabled = !state.launcher.running;
  (buttonRow.children[2] as HTMLButtonElement).disabled = !serverUrl;
  topbar.append(logoWrap, nav, serverControls);

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
