import fs from 'node:fs/promises';
import path from 'node:path';
import type { ChatMessage, ChatSession, LlamaServerSettings } from '../shared/types';
import type { AppPaths } from './AppPaths';
import { JsonStore } from './JsonStore';

function id(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

export class ChatService {
  constructor(private readonly paths: AppPaths, private readonly store: JsonStore) {}

  async loadSessions(): Promise<ChatSession[]> {
    return this.store.read<ChatSession[]>(this.paths.paths.chatSessionsFile, [this.createDefaultSession()]);
  }

  async saveSession(session: ChatSession): Promise<ChatSession> {
    const sessions = await this.loadSessions();
    const index = sessions.findIndex((item) => item.id === session.id);
    if (index >= 0) sessions[index] = session; else sessions.unshift(session);
    await this.store.write(this.paths.paths.chatSessionsFile, sessions);
    return session;
  }

  async sendMessage(sessionId: string | undefined, message: string, settings: LlamaServerSettings, modelId?: string): Promise<ChatSession> {
    const sessions = await this.loadSessions();
    const session = sessions.find((item) => item.id === sessionId) ?? sessions[0] ?? this.createDefaultSession();
    const now = new Date().toISOString();
    session.messages.push({ id: id('user'), role: 'user', content: message, createdAt: now });
    session.updatedAt = now;
    if (!session.title || session.title === 'New chat') session.title = message.slice(0, 32) || 'Chat';

    const assistant = await this.tryRemoteCompletion(session.messages, settings, modelId).catch(() => 'Remote server unavailable. This is an offline scaffold response. Configure a running llama-server instance to enable live chat.');
    session.messages.push({ id: id('assistant'), role: 'assistant', content: assistant, createdAt: new Date().toISOString() });
    await this.saveSession(session);
    return session;
  }

  private createDefaultSession(): ChatSession {
    const now = new Date().toISOString();
    return { id: id('chat'), title: 'New chat', updatedAt: now, messages: [{ id: id('system'), role: 'system', content: 'You are a helpful assistant.', createdAt: now }] };
  }

  private async tryRemoteCompletion(messages: ChatMessage[], settings: LlamaServerSettings, modelId?: string): Promise<string> {
    const body = {
      model: modelId || settings.Alias || 'local-model',
      messages: messages.map((msg) => ({ role: msg.role, content: msg.content })),
      temperature: settings.Temp,
      top_p: settings.TopP,
      stream: false,
    };
    const url = `http://${settings.Host}:${settings.Port}/v1/chat/completions`;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'content-type': 'application/json', ...(settings.ApiKey ? { authorization: `Bearer ${settings.ApiKey}` } : {}) },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json() as { choices?: Array<{ message?: { content?: string } }> };
      return payload.choices?.[0]?.message?.content || 'No assistant text returned.';
    } finally {
      clearTimeout(timeout);
    }
  }
}
