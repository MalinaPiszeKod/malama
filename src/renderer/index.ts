import type { AppActions } from './state.js';
import { createInitialState, findSelectedModel } from './state.js';
import { renderApp } from './app.js';
import { card, el } from './components.js';
import { buildEffectiveModelProfile } from '../shared/modelProfiles.js';

async function main() {
  const root = document.getElementById('app');
  if (!root) throw new Error('Missing app root');
  root.replaceChildren(renderStartupMessage('Loading local models…', 'Reading settings, GGUF metadata, and launcher state.'));

  const bootstrap = await window.malama.bootstrap();

  let state = createInitialState(bootstrap);
  const isEditing = () => ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName ?? '');
  const rerender = () => {
    const scrollTop = root.querySelector('.content')?.scrollTop ?? 0;
    const scrollPositions = new Map<string, { top: number; left: number }>();
    root.querySelectorAll<HTMLElement>('[data-scroll-key]').forEach((node) => {
      const key = node.dataset.scrollKey;
      if (key) scrollPositions.set(key, { top: node.scrollTop, left: node.scrollLeft });
    });
    const focusKey = (document.activeElement as HTMLElement | null)?.dataset?.focusKey;
    root.replaceChildren(renderApp(state, actions));
    const content = root.querySelector('.content');
    if (content) content.scrollTop = scrollTop;
    root.querySelectorAll<HTMLElement>('[data-scroll-key]').forEach((node) => {
      const key = node.dataset.scrollKey;
      const position = key ? scrollPositions.get(key) : undefined;
      if (position) {
        node.scrollTop = position.top;
        node.scrollLeft = position.left;
      }
    });
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
      hfTagFilter: state.hfTagFilter,
      hfPipelineFilter: state.hfPipelineFilter,
      hfSort: state.hfSort,
      hfBrowserOpen: state.hfBrowserOpen,
      chatDraft: state.chatDraft,
      cloudflared: data.cloudflared,
      settingsDraft: state.settingsDraft,
      modelProfiles: data.modelProfiles,
      modelProfileDrafts: state.modelProfileDrafts,
    };
    rerender();
  };

  const actions: AppActions = {
    setView(view) { state.view = view; rerender(); },
    setSelectedModel(modelId) { state.selectedModelId = modelId; rerender(); },
    setSelectedSession(sessionId) { state.selectedSessionId = sessionId; rerender(); },
    setLibraryTab(tab) { state.libraryTab = tab; rerender(); },
    setHfQuery(query) { state.hfQuery = query; },
    setHfTagFilter(tag) { state.hfTagFilter = tag; },
    setHfPipelineFilter(pipeline) { state.hfPipelineFilter = pipeline; },
    setHfSort(sort) { state.hfSort = sort; rerender(); },
    openHfBrowser() { state.hfBrowserOpen = true; rerender(); },
    closeHfBrowser() { state.hfBrowserOpen = false; rerender(); },
    setChatDraft(message) { state.chatDraft = message; },
    setSettingDraftField(key, value) { state.settingsDraft = { ...state.settingsDraft, [key]: value }; },
    setModelProfileField(modelId, key, value) {
      state.modelProfileDrafts = {
        ...state.modelProfileDrafts,
        [modelId]: { ...(state.modelProfileDrafts[modelId] ?? {}), [key]: value },
      };
    },
    setModelProfile(modelId, profile) {
      state.modelProfileDrafts = { ...state.modelProfileDrafts, [modelId]: profile };
      rerender();
    },
    async refresh() { await refresh(); },
    async saveSettings() { await window.malama.saveSettings(state.settingsDraft); await refresh(); },
    async saveSelectedModelProfile() {
      if (!state.selectedModelId) return;
      const model = findSelectedModel(state);
      if (!model) return;
      const profile = buildEffectiveModelProfile(model, state.modelProfiles[state.selectedModelId], state.modelProfileDrafts[state.selectedModelId]);
      state.modelProfiles = await window.malama.saveModelProfile({ modelId: state.selectedModelId, profile });
      const { [state.selectedModelId]: _saved, ...drafts } = state.modelProfileDrafts;
      void _saved;
      state.modelProfileDrafts = drafts;
      await refresh();
    },
    async resetSettings() { state.settingsDraft = await window.malama.resetSettings(); await refresh(); },
    async launchSelected() {
      const model = findSelectedModel(state);
      const modelProfile = model && state.selectedModelId ? buildEffectiveModelProfile(model, state.modelProfiles[state.selectedModelId], state.modelProfileDrafts[state.selectedModelId]) : {};
      await window.malama.launchModel({ modelId: state.selectedModelId, serverSettings: state.settingsDraft, modelProfile });
      await refresh();
    },
    async stopLaunch() { await window.malama.stopModel(); await refresh(); },
    async chooseExecutable() { const filePath = await window.malama.pickExecutable(); if (filePath) await window.malama.setExecutablePath(filePath); await refresh(); },
    async copyServerUrl() {
      const host = state.launcher.host ?? state.settingsDraft.Host;
      const port = state.launcher.port ?? state.settingsDraft.Port;
      await window.malama.copyText(`http://${host}:${port}`);
    },
    async installCloudflared() { state.cloudflared = await window.malama.installCloudflared(); rerender(); },
    async startCloudflared() { state.cloudflared = await window.malama.startCloudflared(); rerender(); },
    async stopCloudflared() { state.cloudflared = await window.malama.stopCloudflared(); rerender(); },
    async copyCloudflaredUrl() { if (state.cloudflared.publicUrl) await window.malama.copyText(state.cloudflared.publicUrl); },
    async searchHf() { state.hfResults = await window.malama.hfSearch({ query: state.hfQuery, tag: state.hfTagFilter || undefined, pipeline: state.hfPipelineFilter || undefined, sort: state.hfSort, limit: 100 }); rerender(); },
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
    void window.malama.getMetrics().then(async (metrics) => {
      state.metrics = metrics;
      state.launcher = metrics.launcher;
      state.cloudflared = await window.malama.getCloudflared();
      if (!isEditing()) rerender();
    });
  }, 8000);
}

function renderStartupMessage(title: string, detail: string): HTMLElement {
  const shell = el('div', 'app-shell');
  const content = el('section', 'content');
  const message = card(title);
  message.append(el('p', 'muted', detail));
  content.append(message);
  shell.append(content);
  return shell;
}

void main().catch((error) => {
  const root = document.getElementById('app');
  const message = error instanceof Error ? error.message : String(error);
  root?.replaceChildren(renderStartupMessage('Startup failed', message));
  console.error(error);
});
