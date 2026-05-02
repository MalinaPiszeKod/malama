import { contextBridge, ipcRenderer } from 'electron';
import { IPC_CHANNELS } from '../shared/ipc';
import type { MalamaApi } from '../shared/ipc';

const api: MalamaApi = {
  bootstrap: () => ipcRenderer.invoke(IPC_CHANNELS.bootstrap),
  getSettings: () => ipcRenderer.invoke(IPC_CHANNELS.getSettings),
  saveSettings: (settings) => ipcRenderer.invoke(IPC_CHANNELS.saveSettings, settings),
  resetSettings: () => ipcRenderer.invoke(IPC_CHANNELS.resetSettings),
  saveModelProfile: (payload) => ipcRenderer.invoke(IPC_CHANNELS.saveModelProfile, payload),
  refreshCatalog: () => ipcRenderer.invoke(IPC_CHANNELS.refreshCatalog),
  listPresets: () => ipcRenderer.invoke(IPC_CHANNELS.listPresets),
  launchModel: (payload) => ipcRenderer.invoke(IPC_CHANNELS.launchModel, payload),
  stopModel: () => ipcRenderer.invoke(IPC_CHANNELS.stopModel),
  getLauncher: () => ipcRenderer.invoke(IPC_CHANNELS.getLauncher),
  setExecutablePath: (filePath) => ipcRenderer.invoke(IPC_CHANNELS.setExecutablePath, filePath),
  getExecutablePath: () => ipcRenderer.invoke(IPC_CHANNELS.getExecutablePath),
  getMetrics: () => ipcRenderer.invoke(IPC_CHANNELS.getMetrics),
  chatSend: (payload) => ipcRenderer.invoke(IPC_CHANNELS.chatSend, payload),
  getChatSessions: () => ipcRenderer.invoke(IPC_CHANNELS.getChatSessions),
  saveChatSession: (session) => ipcRenderer.invoke(IPC_CHANNELS.saveChatSession, session),
  hfSearch: (query) => ipcRenderer.invoke(IPC_CHANNELS.hfSearch, query),
  getCloudflared: () => ipcRenderer.invoke(IPC_CHANNELS.getCloudflared),
  installCloudflared: () => ipcRenderer.invoke(IPC_CHANNELS.installCloudflared),
  startCloudflared: () => ipcRenderer.invoke(IPC_CHANNELS.startCloudflared),
  stopCloudflared: () => ipcRenderer.invoke(IPC_CHANNELS.stopCloudflared),
  copyText: (text) => ipcRenderer.invoke(IPC_CHANNELS.copyText, text),
  pickExecutable: async () => ipcRenderer.invoke(IPC_CHANNELS.pickExecutable),
  pickDirectory: async () => ipcRenderer.invoke(IPC_CHANNELS.pickDirectory),
};

contextBridge.exposeInMainWorld('malama', api);
