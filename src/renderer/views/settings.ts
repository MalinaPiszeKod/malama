import type { AppActions, AppState } from '../state.js';
import { button, card, el, input, metricTile, select } from '../components.js';

const boolOptions = [
  { value: 'true', label: 'On' },
  { value: 'false', label: 'Off' },
];

const SERVER_FIELD_HELP: Partial<Record<keyof AppState['settingsDraft'], string>> = {
  Host: 'Address llama-server binds to. Use 127.0.0.1 for local-only access; 0.0.0.0 exposes on all interfaces.',
  Port: 'HTTP port for the OpenAI-compatible API and web UI.',
  ApiKey: 'Bearer token passed as --api-key. Required before exposing the server publicly.',
  DefaultWorkingDirectory: 'Working directory used for llama-server process launch. Leave empty to use model directory or executable directory.',
  Threads: 'CPU worker threads for inference. llama-server can auto-tune when left at its default; higher is not always faster.',
  BatchSize: 'Logical prompt-processing batch size. Larger can improve prompt ingestion but increases memory pressure.',
  UBatchSize: 'Physical micro-batch size. Lower this first when VRAM/RAM is tight.',
  Parallel: 'Number of concurrent slots/requests. Higher improves throughput but increases KV cache memory use.',
  Webui: 'Enable llama-server built-in web UI. Disable for API-only operation.',
  Metrics: 'Expose /metrics for monitoring. Useful for this launcher metrics view.',
  ContBatching: 'Continuous batching lets active slots share decode work and usually improves multi-request throughput.',
  LogVerbosity: 'llama-server log verbosity. Common values are empty/default, 0, 1, 2, or higher for more detail.',
  MultiModel: 'Enable llama-server router/repository mode via --models-dir. This is on-demand loading, not preloading all models.',
  ModelsDir: 'Directory scanned by llama-server router mode for GGUF models.',
  ModelsMax: 'Maximum models loaded at once in router mode. 0 means unlimited in current llama-server docs.',
  ModelsAutoload: 'Router mode auto-loads a requested model on demand. It does not load every model at startup.',
  HealthCheckTimeoutMs: 'Timeout for launcher health checks against the server.',
  StartupBehavior: 'Launcher startup policy. Manual means do not launch a model automatically.',
  ProcessStrategy: 'How the launcher manages llama-server processes. Multiple-process mode is not implemented yet.',
};

const SERVER_SUGGESTIONS: Partial<Record<keyof AppState['settingsDraft'], string[]>> = {
  Host: ['127.0.0.1', '0.0.0.0', 'localhost'],
  LogVerbosity: ['', '0', '1', '2', '3'],
  StartupBehavior: ['manual', 'launch-selected-on-open'],
  ProcessStrategy: ['single-server-process', 'multiple-managed-processes'],
};

function valueOf(state: AppState, key: keyof AppState['settingsDraft']): string {
  const value = state.settingsDraft[key];
  return typeof value === 'boolean' ? String(value) : String(value ?? '');
}

function serverTooltip(state: AppState, field: keyof AppState['settingsDraft']): string | undefined {
  const help = SERVER_FIELD_HELP[field];
  if (!help) return undefined;
  return `${help} Default: ${String(state.settings[field])}.`;
}

export function renderSettingsView(state: AppState, actions: AppActions): HTMLElement {
  const root = el('div', 'settings-layout');
  const form = el('div', 'panel settings-form');
  form.append(card('llama-server settings'));

  const sections: Array<{ title: string; fields: Array<keyof AppState['settingsDraft']> }> = [
    { title: 'Server endpoint', fields: ['Host', 'Port', 'ApiKey'] },
    { title: 'Server process', fields: ['DefaultWorkingDirectory', 'Threads', 'BatchSize', 'UBatchSize', 'Parallel', 'Webui', 'Metrics', 'ContBatching', 'LogVerbosity'] },
    { title: 'Multi-model repository', fields: ['MultiModel', 'ModelsDir', 'ModelsMax', 'ModelsAutoload'] },
    { title: 'Launcher behavior', fields: ['HealthCheckTimeoutMs', 'StartupBehavior', 'ProcessStrategy'] },
  ];

  const renderField = <K extends keyof AppState['settingsDraft']>(field: K): HTMLElement => {
    const current = state.settingsDraft[field];
    const label = String(field);
    const options = { tooltip: serverTooltip(state, field), suggestions: SERVER_SUGGESTIONS[field] };
    if (typeof current === 'boolean') {
      return select(label, String(current), boolOptions, (value) => actions.setSettingDraftField(field, (value === 'true') as AppState['settingsDraft'][K]), options);
    }
    if (typeof current === 'number') {
      return input(label, String(current), (value) => actions.setSettingDraftField(field, Number(value) as AppState['settingsDraft'][K]), 'number', options);
    }
    if (field === 'ApiKey' || field === 'Host' || field === 'ModelsDir' || field === 'DefaultWorkingDirectory' || field === 'StartupBehavior' || field === 'ProcessStrategy' || field === 'LogVerbosity') {
      return input(label, valueOf(state, field), (value) => actions.setSettingDraftField(field, value as AppState['settingsDraft'][K]), 'text', options);
    }
    return input(label, valueOf(state, field), (value) => actions.setSettingDraftField(field, value as AppState['settingsDraft'][K]), 'text', options);
  };

  sections.forEach((section) => {
    const box = card(section.title, 'settings-group');
    section.fields.forEach((field) => {
      box.append(renderField(field));
    });
    form.append(box);
  });

  const buttons = el('div', 'button-row');
  buttons.append(button('Reset', actions.resetSettings, 'secondary'), button('Save', actions.saveSettings, 'primary'));
  form.append(buttons);

  const right = el('div', 'stack');
  const executable = card('Executable');
  executable.append(
    el('div', 'stack', state.launcher.executablePath || 'llama-server.exe not selected'),
    button('Choose executable', actions.chooseExecutable, 'secondary')
  );
  const cloudflare = card('Cloudflare tunnel');
  const installButton = button(state.cloudflared.installing ? 'Installing…' : 'Install cloudflared helper', actions.installCloudflared, 'secondary');
  installButton.disabled = state.cloudflared.installed || state.cloudflared.installing;
  const startButton = button('Expose server', actions.startCloudflared, 'primary');
  startButton.disabled = !state.launcher.running || !state.launcher.apiKeyConfigured || !state.cloudflared.installed || state.cloudflared.running;
  const stopButton = button('Stop tunnel', actions.stopCloudflared, 'danger');
  stopButton.disabled = !state.cloudflared.running;
  const copyButton = button('Copy URL', actions.copyCloudflaredUrl, 'secondary');
  copyButton.disabled = !state.cloudflared.publicUrl;
  cloudflare.append(
    metricTile('Helper', state.cloudflared.installed ? 'Installed' : 'Not found', state.cloudflared.executablePath || 'Use helper installer'),
    metricTile('Tunnel', state.cloudflared.running ? 'Running' : 'Stopped', state.cloudflared.targetUrl || 'Start an API-key protected server first'),
    metricTile('Public URL', state.cloudflared.publicUrl || '—', state.cloudflared.publicUrl ? 'Ready to copy' : 'Waiting for cloudflared'),
    el('div', 'button-row')
  );
  (cloudflare.querySelector('.button-row') as HTMLElement).append(installButton, startButton, stopButton, copyButton);
  if (state.cloudflared.error) cloudflare.append(el('p', 'muted', state.cloudflared.error));
  if (state.launcher.running && !state.launcher.apiKeyConfigured) cloudflare.append(el('p', 'muted', 'Public tunnels require a llama-server API key. Set ApiKey in Settings, save, and relaunch the model.'));
  if (state.cloudflared.stdoutTail.length) cloudflare.append(el('pre', 'log-block', state.cloudflared.stdoutTail.join('\n')));
  right.append(executable, cloudflare);

  root.append(form, right);
  return root;
}
