import type { AppActions, AppState } from '../state.js';
import { badge, button, card, el } from '../components.js';
import { findSelectedSession } from '../state.js';

export function renderChatView(state: AppState, actions: AppActions): HTMLElement {
  const root = el('div', 'chat-layout');
  const sidebar = el('aside', 'panel chat-sidebar');
  sidebar.append(card('History'));
  state.chatSessions.forEach((session) => {
    sidebar.append(button(session.title, () => actions.setSelectedSession(session.id), session.id === state.selectedSessionId ? 'active' : 'secondary'));
  });

  const session = findSelectedSession(state) || state.chatSessions[0];
  const main = el('section', 'panel chat-main');
  const messages = el('div', 'chat-messages');
  const sessionMessages = session?.messages || [];
  if (!sessionMessages.length) {
    messages.append(el('div', 'muted', session ? 'No messages yet. Send the first one.' : 'No chat session selected.'));
  } else {
    sessionMessages.forEach((msg) => {
      const bubble = el('article', `chat-message ${msg.role}`);
      bubble.append(el('div', 'chat-role', msg.role), el('div', 'chat-content', msg.content));
      messages.append(bubble);
    });
  }

  const composer = card('Composer');
  const editor = document.createElement('textarea');
  editor.className = 'field-input textarea';
  editor.dataset.focusKey = 'textarea:chat-composer';
  editor.rows = 4;
  editor.placeholder = 'Ask something...';
  editor.value = state.chatDraft;
  const footer = el('div', 'chat-footer');
  const send = button('Send', async () => { await actions.sendChat(); }, 'primary');
  send.disabled = state.chatDraft.trim().length === 0;
  editor.addEventListener('input', () => {
    actions.setChatDraft(editor.value);
    send.disabled = editor.value.trim().length === 0;
  });
  editor.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      if (editor.value.trim().length) void actions.sendChat();
    }
  });
  footer.append(
    badge(`Model: ${state.launcher.modelName || 'idle'}`),
    badge(`Tokens: ${session?.messages.length || 0}`),
    badge(`Endpoint: ${state.settings.Host}:${state.settings.Port}`)
  );
  composer.append(editor, send);

  main.append(messages, composer, footer);
  root.append(sidebar, main);
  return root;
}
