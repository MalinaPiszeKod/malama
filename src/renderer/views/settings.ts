import type { AppActions, AppState } from '../state.js';
import { button, card, el, input, select } from '../components.js';

const boolOptions = [
  { value: 'true', label: 'On' },
  { value: 'false', label: 'Off' },
];

function valueOf(state: AppState, key: keyof AppState['settingsDraft']): string {
  const value = state.settingsDraft[key];
  return typeof value === 'boolean' ? String(value) : String(value ?? '');
}

export function renderSettingsView(state: AppState, actions: AppActions): HTMLElement {
  const root = el('div', 'settings-layout');
  const form = el('div', 'panel settings-form');
  form.append(card('llama-server settings'));

  const sections: Array<{ title: string; fields: Array<keyof AppState['settingsDraft']> }> = [
    { title: 'Runtime', fields: ['Host', 'Port', 'Threads', 'Parallel', 'GpuLayers', 'NcpuMoe', 'CtxSize', 'BatchSize', 'UBatchSize'] },
    { title: 'Sampling', fields: ['Temp', 'TopP', 'TopK', 'MinP', 'TypicalP', 'RepeatPenalty', 'RepeatLastN', 'PresencePenalty', 'FreqPenalty'] },
    { title: 'Cache / Offload', fields: ['CacheTypeK', 'CacheTypeV', 'FlashAttn', 'SplitMode', 'TensorSplit', 'Mlock', 'NoMmap'] },
    { title: 'Deployment', fields: ['MultiModel', 'ModelsDir', 'ModelsMax', 'ModelsAutoload'] },
    { title: 'Chat / Server', fields: ['ApiKey', 'Alias', 'Thinking', 'PreserveThinking', 'ReasoningFormat', 'ReasoningBudget', 'Jinja', 'Webui', 'Metrics', 'ContBatching'] },
    { title: 'Advanced', fields: ['DryMultiplier', 'DryBase', 'DryAllowed', 'XtcProb', 'XtcThresh', 'Seed'] },
  ];

  const renderField = <K extends keyof AppState['settingsDraft']>(field: K): HTMLElement => {
    const current = state.settingsDraft[field];
    const label = String(field);
    if (typeof current === 'boolean') {
      return select(label, String(current), boolOptions, (value) => actions.setSettingDraftField(field, (value === 'true') as AppState['settingsDraft'][K]));
    }
    if (typeof current === 'number') {
      return input(label, String(current), (value) => actions.setSettingDraftField(field, Number(value) as AppState['settingsDraft'][K]), 'number');
    }
    if (field === 'ReasoningBudget' || field === 'ApiKey' || field === 'Alias' || field === 'Host' || field === 'CacheTypeK' || field === 'CacheTypeV' || field === 'SplitMode' || field === 'ReasoningFormat' || field === 'ModelsDir') {
      return input(label, valueOf(state, field), (value) => actions.setSettingDraftField(field, value as AppState['settingsDraft'][K]));
    }
    return input(label, valueOf(state, field), (value) => actions.setSettingDraftField(field, value as AppState['settingsDraft'][K]), 'text');
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

  const right = card('Executable');
  right.append(
    el('div', 'stack', state.launcher.executablePath || 'llama-server.exe not selected'),
    button('Choose executable', actions.chooseExecutable, 'secondary')
  );

  root.append(form, right);
  return root;
}
