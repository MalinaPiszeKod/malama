import type { AppActions } from './state.js';
import { createInitialState } from './state.js';
import { renderApp } from './app.js';

async function main() {
  const bootstrap = await window.malama.bootstrap();
  const root = document.getElementById('app');
  if (!root) throw new Error('Missing app root');

  let state = createInitialState(bootstrap);
  const isEditing = () => ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName ?? '');
  const rerender = () => {
    const scrollTop = root.querySelector('.content')?.scrollTop ?? 0;
    const focusKey = (document.activeElement as HTMLElement | null)?.dataset?.focusKey;
    root.replaceChildren(renderApp(state, actions));
    const content = root.querySelector('.content');
    if (content) content.scrollTop = scrollTop;
    if (focusKey) {
      const target = root.querySelector<HTMLElement>(`[data-focus-key="${CSS.escape(focusKey)}"]`);
      target?.focus();
    }
  };

  const refresh = async () => {
    const data = await window.malama.bootstrap();
    state = {
      ...state,
      ...data,
      hfResults: state.hfResults,
      view: state.view,
      selectedModelId: state.selectedModelId,
      selectedSessionId: state.selectedSessionId,
      libraryTab: state.libraryTab,
      hfQuery: state.hfQuery,
      chatDraft: state.chatDraft,
      settingsDraft: state.settingsDraft,
    };
    rerender();
  };

  const actions: AppActions = {
    setView(view) { state.view = view; rerender(); },
    setSelectedModel(modelId) { state.selectedModelId = modelId; rerender(); },
    setSelectedSession(sessionId) { state.selectedSessionId = sessionId; rerender(); },
    setLibraryTab(tab) { state.libraryTab = tab; rerender(); },
    setHfQuery(query) { state.hfQuery = query; },
    setChatDraft(message) { state.chatDraft = message; },
    setSettingDraftField(key, value) { state.settingsDraft = { ...state.settingsDraft, [key]: value }; },
    async refresh() { await refresh(); },
    async saveSettings() { await window.malama.saveSettings(state.settingsDraft); await refresh(); },
    async resetSettings() { state.settingsDraft = await window.malama.resetSettings(); await refresh(); },
    async launchSelected() { await window.malama.launchModel({ modelId: state.selectedModelId }); await refresh(); },
    async stopLaunch() { await window.malama.stopModel(); await refresh(); },
    async chooseExecutable() { const filePath = await window.malama.pickExecutable(); if (filePath) await window.malama.setExecutablePath(filePath); await refresh(); },
    async searchHf(query) { state.hfResults = await window.malama.hfSearch(query); rerender(); },
    async sendChat() {
      const message = state.chatDraft.trim();
      if (!message) return;
      const session = await window.malama.chatSend({ sessionId: state.selectedSessionId, message });
      state.chatDraft = '';
      state.selectedSessionId = session.id;
      state.chatSessions = await window.malama.getChatSessions();
      rerender();
    },
  };

  rerender();
  setInterval(() => {
    void window.malama.getMetrics().then((metrics) => {
      state.metrics = metrics;
      state.launcher = metrics.launcher;
      if (!isEditing()) rerender();
    });
  }, 8000);
}

void main();
