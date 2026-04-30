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

export function input(label: string, value: string, onInput: (value: string) => void, type = 'text'): HTMLElement {
  const wrap = el('label', 'field');
  wrap.append(el('span', 'field-label', label));
  const node = document.createElement('input');
  node.type = type;
  node.className = 'field-input';
  node.dataset.focusKey = `input:${label}`;
  node.value = value;
  node.addEventListener('input', () => onInput(node.value));
  wrap.append(node);
  return wrap;
}

export function textarea(label: string, value: string, onInput: (value: string) => void, rows = 4): HTMLElement {
  const wrap = el('label', 'field');
  wrap.append(el('span', 'field-label', label));
  const node = document.createElement('textarea');
  node.className = 'field-input textarea';
  node.dataset.focusKey = `textarea:${label}`;
  node.rows = rows;
  node.value = value;
  node.addEventListener('input', () => onInput(node.value));
  wrap.append(node);
  return wrap;
}

export function select(label: string, value: string, options: Array<{ value: string; label: string }>, onChange: (value: string) => void): HTMLElement {
  const wrap = el('label', 'field');
  wrap.append(el('span', 'field-label', label));
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
    const row = el('button', `tree-row ${node.kind} ${node.modelId === activeId ? 'active' : ''}`.trim(), `${' '.repeat(depth * 2)}${node.label}`) as HTMLButtonElement;
    row.type = 'button';
    if (node.kind === 'model' && node.modelId) row.addEventListener('click', () => onSelect(node.modelId!));
    if (node.children?.length) {
      const group = el('div', 'tree-group');
      group.append(row);
      node.children.forEach((child) => group.append(renderNode(child, depth + 1)));
      return group;
    }
    return row;
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
