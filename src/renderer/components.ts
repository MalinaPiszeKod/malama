import type { TreeNode } from '../shared/types.js';

export function el<K extends keyof HTMLElementTagNameMap>(tag: K, className?: string, text?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function badge(text: string, className = ''): HTMLSpanElement {
  return el('span', `badge ${className}`.trim(), text);
}

export function card(title: string, className = ''): HTMLElement {
  const node = el('section', `card ${className}`.trim());
  const h = el('h3', 'card-title', title);
  node.append(h);
  return node;
}

export function button(label: string, onClick: () => void, className = ''): HTMLButtonElement {
  const node = el('button', `button ${className}`.trim(), label) as HTMLButtonElement;
  node.type = 'button';
  node.dataset.focusKey = `button:${className}:${label}`;
  node.addEventListener('click', onClick);
  return node;
}

export function metricTile(label: string, value: string, detail?: string): HTMLElement {
  const node = el('div', 'metric-tile');
  node.append(el('div', 'metric-label', label), el('div', 'metric-value', value));
  if (detail) node.append(el('div', 'metric-detail', detail));
  return node;
}

export interface FieldOptions {
  tooltip?: string;
  suggestions?: string[];
}

function appendFieldLabel(wrap: HTMLElement, label: string, tooltip?: string): void {
  const labelNode = el('span', 'field-label', label);
  if (tooltip) {
    labelNode.title = tooltip;
    labelNode.append(el('span', 'field-help', ' ?'));
  }
  wrap.append(labelNode);
  if (tooltip) wrap.title = tooltip;
}

function attachDatalist(node: HTMLInputElement, label: string, suggestions?: string[]): void {
  if (!suggestions?.length) return;
  const listId = `list-${label.replace(/[^a-z0-9_-]+/gi, '-')}`;
  const list = document.createElement('datalist');
  list.id = listId;
  suggestions.forEach((value) => {
    const option = document.createElement('option');
    option.value = value;
    list.append(option);
  });
  node.setAttribute('list', listId);
  node.after(list);
}

export function input(label: string, value: string, onInput: (value: string) => void, type = 'text', options: FieldOptions = {}): HTMLElement {
  const wrap = el('label', 'field');
  appendFieldLabel(wrap, label, options.tooltip);
  const node = document.createElement('input');
  node.type = type;
  node.className = 'field-input';
  node.dataset.focusKey = `input:${label}`;
  node.value = value;
  node.addEventListener('input', () => onInput(node.value));
  wrap.append(node);
  attachDatalist(node, label, options.suggestions);
  return wrap;
}

export function textarea(label: string, value: string, onInput: (value: string) => void, rows = 4, options: FieldOptions = {}): HTMLElement {
  const wrap = el('label', 'field');
  appendFieldLabel(wrap, label, options.tooltip);
  const node = document.createElement('textarea');
  node.className = 'field-input textarea';
  node.dataset.focusKey = `textarea:${label}`;
  node.rows = rows;
  node.value = value;
  node.addEventListener('input', () => onInput(node.value));
  wrap.append(node);
  return wrap;
}

export function select(label: string, value: string, options: Array<{ value: string; label: string }>, onChange: (value: string) => void, fieldOptions: FieldOptions = {}): HTMLElement {
  const wrap = el('label', 'field');
  appendFieldLabel(wrap, label, fieldOptions.tooltip);
  const node = document.createElement('select');
  node.className = 'field-input';
  node.dataset.focusKey = `select:${label}`;
  options.forEach((option) => {
    const opt = document.createElement('option');
    opt.value = option.value;
    opt.textContent = option.label;
    if (option.value === value) opt.selected = true;
    node.append(opt);
  });
  node.addEventListener('change', () => onChange(node.value));
  wrap.append(node);
  return wrap;
}

export function tree(root: TreeNode[], onSelect: (id: string) => void, activeId?: string): HTMLElement {
  const wrap = el('div', 'tree');
  const renderNode = (node: TreeNode, depth: number): HTMLElement => {
    const icon = node.kind === 'group' ? '▾' : '◦';
    const rowClass = `tree-row ${node.kind} ${node.modelId === activeId ? 'active' : ''}`.trim();
    const content = el('div', 'tree-node-content');
    content.append(el('div', 'tree-node-icon', icon), el('div', 'tree-node-text'));
    const text = content.querySelector('.tree-node-text') as HTMLElement;
    text.append(el('div', 'tree-row-title tree-node-title', node.label));
    if (node.detail) text.append(el('div', 'tree-row-detail tree-node-detail', node.detail));

    if (node.kind === 'model') {
      const row = el('button', rowClass) as HTMLButtonElement;
      row.type = 'button';
      if (node.modelId) row.dataset.modelId = node.modelId;
      row.draggable = false;
      row.append(content);
      if (node.modelId) row.addEventListener('click', () => onSelect(node.modelId!));
      return row;
    }

    const branch = el('div', 'tree-branch');
    const groupRow = el('div', rowClass);
    groupRow.append(content);
    branch.append(groupRow);
    if (node.children?.length) {
      const children = el('div', 'tree-children');
      node.children.forEach((child) => children.append(renderNode(child, depth + 1)));
      branch.append(children);
    }
    return branch;
  };
  root.forEach((node) => wrap.append(renderNode(node, 0)));
  return wrap;
}

export function tabs(items: Array<{ id: string; label: string }>, activeId: string, onChange: (id: string) => void): HTMLElement {
  const wrap = el('div', 'tabs');
  items.forEach((item) => {
    const btn = button(item.label, () => onChange(item.id), `tab ${item.id === activeId ? 'active' : ''}`);
    wrap.append(btn);
  });
  return wrap;
}
