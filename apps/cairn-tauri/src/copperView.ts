/**
 * Copper View — LAN Ollama Coordinator dashboard.
 *
 * Single scrollable column showing:
 *   - Header bar with service status badge
 *   - Nodes panel (per-node cards with toggle, priority, remove controls)
 *   - Add Node inline form
 *   - Models panel (table with per-model pull action)
 *   - Active Tasks panel (shown only when pulls are in progress)
 *
 * Polls copper/status + copper/nodes + copper/models every 10 seconds.
 * Slows to 30 seconds when Copper is not available.
 * Polls copper/tasks every 2-3 seconds while any task is running.
 */

import { el } from './dom';

// ── Types ──────────────────────────────────────────────────────────────

interface CopperNodeStatus {
  alive: boolean;
  latency_ms: number;
  models: string[];
  active_requests: number;
  error: string | null;
}

interface CopperStatus {
  copper_available: boolean;
  nodes: Record<string, CopperNodeStatus>;
  total_active: number;
}

interface CopperNodeConfig {
  name: string;
  host: string;
  port: number;
  enabled: boolean;
  priority: number;
}

interface CopperNodes {
  copper_available: boolean;
  nodes: CopperNodeConfig[];
}

interface CopperModelEntry {
  name: string;
  nodes: string[];
}

interface CopperModels {
  copper_available: boolean;
  models: CopperModelEntry[];
}

interface CopperPullResponse {
  copper_available: boolean;
  task_id: string;
}

interface CopperTaskStatus {
  copper_available: boolean;
  task_id: string;
  status: 'running' | 'completed' | 'failed';
  model: string;
  target_node: string | null;
  progress: Record<string, string>;
  result: Record<string, unknown> | null;
  error: string | null;
  task_type?: string; // "pull" | "build"
}

interface CopperModelfile {
  name: string;
  base_model: string;
  parameters: Record<string, number>;
  created_at: string;
  updated_at: string;
}

interface CopperModelfiles {
  copper_available: boolean;
  modelfiles: CopperModelfile[];
}

interface CopperBuildResponse {
  copper_available: boolean;
  task_id: string;
}

interface ExtractResult {
  copper_available: boolean;
  system_prompt: string;
  word_count: number;
  memory_count: number;
  sources: string[];
  truncated: boolean;
}

interface CopperViewCallbacks {
  kernelRequest: (method: string, params: unknown) => Promise<unknown>;
}

// ── Helpers (duplicated from reosView.ts — do not import) ──────────────

function formatBytes(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${Math.round(mb)} MB`;
}

function percentColor(pct: number): string {
  if (pct >= 90) return '#ef4444';
  if (pct >= 70) return '#f59e0b';
  return '#22c55e';
}

function makeBar(pct: number, width: string = '100%'): HTMLElement {
  const track = el('div');
  track.style.cssText = `
    width: ${width}; height: 6px;
    background: rgba(255,255,255,0.08);
    border-radius: 3px;
    overflow: hidden;
  `;
  const fill = el('div');
  fill.style.cssText = `
    height: 100%;
    width: ${Math.min(pct, 100).toFixed(1)}%;
    background: ${percentColor(pct)};
    border-radius: 3px;
    transition: width 0.4s ease, background 0.4s ease;
  `;
  track.appendChild(fill);
  return track;
}

function makePanel(title: string, icon: string): { panel: HTMLElement; body: HTMLElement } {
  const panel = el('div');
  panel.style.cssText = `
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 8px;
    overflow: hidden;
    flex-shrink: 0;
  `;

  const header = el('div');
  header.style.cssText = `
    padding: 10px 14px;
    font-size: 12px;
    font-weight: 600;
    color: rgba(255,255,255,0.6);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    display: flex;
    align-items: center;
    gap: 6px;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    user-select: none;
  `;
  header.textContent = `${icon} ${title}`;
  panel.appendChild(header);

  const body = el('div');
  body.style.cssText = `padding: 12px 14px;`;
  panel.appendChild(body);

  return { panel, body };
}

function makeStatRow(label: string, value: string, bar?: HTMLElement): HTMLElement {
  const row = el('div');
  row.style.cssText = `
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 4px 0;
    font-size: 13px;
  `;

  const lbl = el('span');
  lbl.style.color = 'rgba(255,255,255,0.5)';
  lbl.textContent = label;
  row.appendChild(lbl);

  if (bar) {
    const mid = el('div');
    mid.style.cssText = 'flex: 1; margin: 0 12px;';
    mid.appendChild(bar);
    row.appendChild(mid);
  }

  const val = el('span');
  val.style.cssText = 'font-weight: 500; color: rgba(255,255,255,0.9); font-variant-numeric: tabular-nums;';
  val.textContent = value;
  row.appendChild(val);

  return row;
}

// ── Status badge helpers (pattern from rivaView.ts) ────────────────────

type BadgeState = 'connected' | 'connecting' | 'offline';

function createStatusBadge(): HTMLElement {
  const badge = el('div');
  badge.style.cssText = `
    font-size: 12px;
    padding: 4px 12px;
    border-radius: 12px;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  `;
  setStatusBadge(badge, 'connecting');
  return badge;
}

function setStatusBadge(badge: HTMLElement, state: BadgeState): void {
  const dot = state === 'connected' ? '\u25CF' : state === 'connecting' ? '\u25CB' : '\u25CF';
  const color =
    state === 'connected' ? '#4ade80' : state === 'connecting' ? '#fbbf24' : '#ef4444';
  const bg =
    state === 'connected'
      ? 'rgba(74, 222, 128, 0.1)'
      : state === 'connecting'
        ? 'rgba(251, 191, 36, 0.1)'
        : 'rgba(239, 68, 68, 0.1)';
  const border =
    state === 'connected'
      ? 'rgba(74, 222, 128, 0.2)'
      : state === 'connecting'
        ? 'rgba(251, 191, 36, 0.2)'
        : 'rgba(239, 68, 68, 0.2)';
  const label =
    state === 'connected' ? 'Connected' : state === 'connecting' ? 'Connecting...' : 'Not Running';

  badge.style.color = color;
  badge.style.background = bg;
  badge.style.border = `1px solid ${border}`;
  badge.textContent = `${dot} ${label}`;
}

// ── Small action button helper ─────────────────────────────────────────

function makeButton(
  text: string,
  variant: 'primary' | 'secondary' | 'danger' | 'ghost' = 'secondary',
): HTMLButtonElement {
  const btn = el('button') as HTMLButtonElement;
  btn.textContent = text;
  const base = `
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    transition: opacity 0.15s ease;
    user-select: none;
    white-space: nowrap;
  `;
  const variants: Record<string, string> = {
    primary: `
      background: rgba(74, 222, 128, 0.15);
      border: 1px solid rgba(74, 222, 128, 0.3);
      color: #4ade80;
    `,
    secondary: `
      background: rgba(255,255,255,0.06);
      border: 1px solid rgba(255,255,255,0.1);
      color: rgba(255,255,255,0.7);
    `,
    danger: `
      background: rgba(239, 68, 68, 0.1);
      border: 1px solid rgba(239, 68, 68, 0.25);
      color: #ef4444;
    `,
    ghost: `
      background: transparent;
      border: 1px solid rgba(255,255,255,0.08);
      color: rgba(255,255,255,0.5);
    `,
  };
  btn.style.cssText = base + (variants[variant] ?? variants['secondary']);
  btn.addEventListener('mouseenter', () => { btn.style.opacity = '0.75'; });
  btn.addEventListener('mouseleave', () => { btn.style.opacity = '1'; });
  return btn;
}

function makeInput(
  type: 'text' | 'number',
  placeholder: string,
  defaultValue?: string,
): HTMLInputElement {
  const inp = el('input') as HTMLInputElement;
  inp.type = type;
  inp.placeholder = placeholder;
  if (defaultValue !== undefined) inp.value = defaultValue;
  inp.style.cssText = `
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 6px;
    color: rgba(255,255,255,0.9);
    font-size: 13px;
    padding: 5px 9px;
    outline: none;
    width: 100%;
    box-sizing: border-box;
  `;
  inp.addEventListener('focus', () => {
    inp.style.borderColor = 'rgba(74, 222, 128, 0.5)';
  });
  inp.addEventListener('blur', () => {
    inp.style.borderColor = 'rgba(255,255,255,0.12)';
  });
  return inp;
}

// ── View Factory ───────────────────────────────────────────────────────

export function createCopperView(callbacks: CopperViewCallbacks): {
  container: HTMLElement;
  startPolling: () => void;
  stopPolling: () => void;
} {
  // ── Timer state ──
  let isPolling = false;
  let mainTimer: ReturnType<typeof setTimeout> | null = null;
  let taskTimer: ReturnType<typeof setTimeout> | null = null;

  // ── Data state ──
  let lastStatus: CopperStatus | null = null;
  let lastNodes: CopperNodeConfig[] = [];
  let lastModels: CopperModelEntry[] = [];
  let lastModelfiles: CopperModelfile[] = [];
  let activeTasks: Map<string, CopperTaskStatus> = new Map();

  // ── DOM state: which nodes are in confirm-remove mode ──
  let pendingRemoveNode: string | null = null;

  // ── Root container ──
  const container = el('div');
  container.className = 'copper-view';
  container.style.cssText = `
    flex: 1;
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    overflow: hidden;
    background: rgba(0,0,0,0.1);
  `;

  // ── Header bar ──
  const headerBar = el('div');
  headerBar.style.cssText = `
    padding: 16px 20px;
    border-bottom: 1px solid rgba(255,255,255,0.1);
    background: rgba(0,0,0,0.2);
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
  `;

  const headerLeft = el('div');
  headerLeft.style.cssText = 'display: flex; flex-direction: column; gap: 2px;';

  const headerTitle = el('div');
  headerTitle.style.cssText = 'font-size: 16px; font-weight: 600; color: #fff;';
  headerTitle.textContent = '\u{1F310} Copper';

  const headerSubtitle = el('div');
  headerSubtitle.style.cssText = 'font-size: 12px; color: rgba(255,255,255,0.4);';
  headerSubtitle.textContent = 'LAN Ollama Coordinator';

  headerLeft.appendChild(headerTitle);
  headerLeft.appendChild(headerSubtitle);

  const headerRight = el('div');
  headerRight.style.cssText = 'display: flex; flex-direction: column; align-items: flex-end; gap: 4px;';

  const statusBadge = createStatusBadge();
  const lastUpdatedEl = el('div');
  lastUpdatedEl.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.3);';
  lastUpdatedEl.textContent = 'Waiting...';

  headerRight.appendChild(statusBadge);
  headerRight.appendChild(lastUpdatedEl);

  headerBar.appendChild(headerLeft);
  headerBar.appendChild(headerRight);
  container.appendChild(headerBar);

  // ── Scrollable body ──
  const scrollBody = el('div');
  scrollBody.style.cssText = `
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  `;
  container.appendChild(scrollBody);

  // ── "Not Running" placeholder ──
  const notRunningEl = el('div');
  notRunningEl.style.cssText = `
    display: none;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    padding: 40px 20px;
    text-align: center;
  `;

  const notRunningMsg = el('div');
  notRunningMsg.style.cssText = 'font-size: 16px; color: rgba(255,255,255,0.6); font-weight: 500;';
  notRunningMsg.textContent = 'Starting Copper\u2026';

  const notRunningHint = el('div');
  notRunningHint.style.cssText = 'font-size: 13px; color: rgba(255,255,255,0.4); margin-top: 4px;';
  notRunningHint.textContent = 'Connecting to the LAN Ollama coordinator';

  const notRunningSpinner = el('div');
  notRunningSpinner.style.cssText = `
    width: 24px;
    height: 24px;
    border: 2px solid rgba(255, 255, 255, 0.1);
    border-top-color: rgba(255, 255, 255, 0.5);
    border-radius: 50%;
    margin-top: 12px;
  `;
  // Animate spinner via JS since inline styles can't do keyframes portably
  let spinAngle = 0;
  const spinInterval = setInterval(() => {
    spinAngle = (spinAngle + 12) % 360;
    notRunningSpinner.style.transform = `rotate(${spinAngle}deg)`;
  }, 30);
  // Clean up spinner when element is removed
  const origStopPolling = { fn: () => { clearInterval(spinInterval); } };

  notRunningEl.appendChild(notRunningMsg);
  notRunningEl.appendChild(notRunningHint);
  notRunningEl.appendChild(notRunningSpinner);
  scrollBody.appendChild(notRunningEl);

  // ── Nodes panel ──
  const { panel: nodesPanel, body: nodesBody } = makePanel('Nodes', '\u{1F5A7}');
  scrollBody.appendChild(nodesPanel);

  // ── Add Node section (button + inline form) ──
  const addNodeSection = el('div');
  addNodeSection.style.cssText = 'display: flex; flex-direction: column; gap: 0;';

  const addNodeBtn = makeButton('+ Add Node', 'ghost');
  addNodeBtn.style.alignSelf = 'flex-start';
  addNodeBtn.style.marginTop = '4px';

  const addNodeForm = el('div');
  addNodeForm.style.cssText = `
    display: none;
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
    padding: 14px;
    margin-top: 6px;
    flex-direction: column;
    gap: 10px;
  `;

  const addFormTitle = el('div');
  addFormTitle.style.cssText = 'font-size: 12px; font-weight: 600; color: rgba(255,255,255,0.6); text-transform: uppercase; letter-spacing: 0.05em;';
  addFormTitle.textContent = 'Add Node';

  const addFormGrid = el('div');
  addFormGrid.style.cssText = 'display: grid; grid-template-columns: 1fr 1fr 100px 80px; gap: 8px; align-items: end;';

  const addNameWrap = el('div');
  addNameWrap.style.cssText = 'display: flex; flex-direction: column; gap: 4px;';
  const addNameLabel = el('div');
  addNameLabel.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.4);';
  addNameLabel.textContent = 'Name';
  const addNameInput = makeInput('text', 'my-node');
  addNameWrap.appendChild(addNameLabel);
  addNameWrap.appendChild(addNameInput);

  const addHostWrap = el('div');
  addHostWrap.style.cssText = 'display: flex; flex-direction: column; gap: 4px;';
  const addHostLabel = el('div');
  addHostLabel.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.4);';
  addHostLabel.textContent = 'Host';
  const addHostInput = makeInput('text', '192.168.1.x');
  addHostWrap.appendChild(addHostLabel);
  addHostWrap.appendChild(addHostInput);

  const addPortWrap = el('div');
  addPortWrap.style.cssText = 'display: flex; flex-direction: column; gap: 4px;';
  const addPortLabel = el('div');
  addPortLabel.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.4);';
  addPortLabel.textContent = 'Port';
  const addPortInput = makeInput('number', '11434', '11434');
  addPortWrap.appendChild(addPortLabel);
  addPortWrap.appendChild(addPortInput);

  const addPriorityWrap = el('div');
  addPriorityWrap.style.cssText = 'display: flex; flex-direction: column; gap: 4px;';
  const addPriorityLabel = el('div');
  addPriorityLabel.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.4);';
  addPriorityLabel.textContent = 'Priority';
  const addPriorityInput = makeInput('number', '0', '0');
  addPriorityWrap.appendChild(addPriorityLabel);
  addPriorityWrap.appendChild(addPriorityInput);

  addFormGrid.appendChild(addNameWrap);
  addFormGrid.appendChild(addHostWrap);
  addFormGrid.appendChild(addPortWrap);
  addFormGrid.appendChild(addPriorityWrap);

  const addFormError = el('div');
  addFormError.style.cssText = 'font-size: 12px; color: #ef4444; display: none;';

  const addFormActions = el('div');
  addFormActions.style.cssText = 'display: flex; gap: 8px;';
  const addFormSubmit = makeButton('Add', 'primary');
  const addFormCancel = makeButton('Cancel', 'ghost');
  addFormActions.appendChild(addFormSubmit);
  addFormActions.appendChild(addFormCancel);

  addNodeForm.appendChild(addFormTitle);
  addNodeForm.appendChild(addFormGrid);
  addNodeForm.appendChild(addFormError);
  addNodeForm.appendChild(addFormActions);

  addNodeSection.appendChild(addNodeBtn);
  addNodeSection.appendChild(addNodeForm);
  scrollBody.appendChild(addNodeSection);

  // ── Models panel ──
  const { panel: modelsPanel, body: modelsBody } = makePanel('Models', '\u{1F9E0}');
  scrollBody.appendChild(modelsPanel);

  // ── Custom Models panel ──
  const { panel: customModelsPanel, body: customModelsBody } = makePanel('Custom Models', '\u2699\uFE0F');
  scrollBody.appendChild(customModelsPanel);

  // ── Tasks panel (hidden until tasks exist) ──
  const { panel: tasksPanel, body: tasksBody } = makePanel('Active Tasks', '\u{23CF}');
  tasksPanel.style.display = 'none';
  scrollBody.appendChild(tasksPanel);

  // ── Custom Models: Create button + inline form ──

  const createModelBtn = makeButton('+ Create Custom Model', 'ghost');
  createModelBtn.style.cssText += ' align-self: flex-start; margin-bottom: 4px;';

  const createModelForm = el('div');
  createModelForm.style.cssText = `
    display: none;
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
    padding: 14px;
    margin-top: 6px;
    flex-direction: column;
    gap: 10px;
  `;

  const createFormTitle = el('div');
  createFormTitle.style.cssText = 'font-size: 12px; font-weight: 600; color: rgba(255,255,255,0.6); text-transform: uppercase; letter-spacing: 0.05em;';
  createFormTitle.textContent = 'Create Custom Model';

  // Name field
  const createNameWrap = el('div');
  createNameWrap.style.cssText = 'display: flex; flex-direction: column; gap: 4px;';
  const createNameLabel = el('div');
  createNameLabel.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.4);';
  createNameLabel.textContent = 'Name (lowercase, alphanumeric, hyphens, underscores)';
  const createNameInput = makeInput('text', 'my-model');
  createNameWrap.appendChild(createNameLabel);
  createNameWrap.appendChild(createNameInput);

  // Base model select
  const createBaseWrap = el('div');
  createBaseWrap.style.cssText = 'display: flex; flex-direction: column; gap: 4px;';
  const createBaseLabel = el('div');
  createBaseLabel.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.4);';
  createBaseLabel.textContent = 'Base Model';
  const createBaseSelect = el('select') as HTMLSelectElement;
  createBaseSelect.style.cssText = `
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 6px;
    color: rgba(255,255,255,0.9);
    font-size: 13px;
    padding: 5px 9px;
    outline: none;
    width: 100%;
    box-sizing: border-box;
  `;
  createBaseSelect.addEventListener('focus', () => {
    createBaseSelect.style.borderColor = 'rgba(74, 222, 128, 0.5)';
  });
  createBaseSelect.addEventListener('blur', () => {
    createBaseSelect.style.borderColor = 'rgba(255,255,255,0.12)';
  });
  createBaseWrap.appendChild(createBaseLabel);
  createBaseWrap.appendChild(createBaseSelect);

  // System prompt textarea
  const createPromptWrap = el('div');
  createPromptWrap.style.cssText = 'display: flex; flex-direction: column; gap: 4px;';
  const createPromptLabel = el('div');
  createPromptLabel.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.4);';
  createPromptLabel.textContent = 'System Prompt';
  const createPromptTextarea = el('textarea') as HTMLTextAreaElement;
  createPromptTextarea.style.cssText = `
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 6px;
    color: rgba(255,255,255,0.9);
    font-size: 13px;
    font-family: monospace;
    padding: 8px 9px;
    outline: none;
    width: 100%;
    box-sizing: border-box;
    min-height: 120px;
    resize: vertical;
  `;
  createPromptTextarea.placeholder = 'You are a helpful assistant...';
  createPromptTextarea.addEventListener('focus', () => {
    createPromptTextarea.style.borderColor = 'rgba(74, 222, 128, 0.5)';
  });
  createPromptTextarea.addEventListener('blur', () => {
    createPromptTextarea.style.borderColor = 'rgba(255,255,255,0.12)';
  });

  const extractBtn = makeButton('Auto-generate from Talking Rock', 'secondary');
  createPromptWrap.appendChild(createPromptLabel);
  createPromptWrap.appendChild(createPromptTextarea);
  createPromptWrap.appendChild(extractBtn);

  const extractInfoEl = el('div');
  extractInfoEl.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.4); display: none;';
  createPromptWrap.appendChild(extractInfoEl);

  // Parameters grid
  const createParamsGrid = el('div');
  createParamsGrid.style.cssText = 'display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px;';

  // Temperature slider
  const createTempWrap = el('div');
  createTempWrap.style.cssText = 'display: flex; flex-direction: column; gap: 6px;';
  const createTempLabelRow = el('div');
  createTempLabelRow.style.cssText = 'display: flex; justify-content: space-between; align-items: center;';
  const createTempLabel = el('div');
  createTempLabel.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.4);';
  createTempLabel.textContent = 'Temperature';
  const createTempValue = el('span');
  createTempValue.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.7); font-variant-numeric: tabular-nums;';
  createTempValue.textContent = '0.7';
  createTempLabelRow.appendChild(createTempLabel);
  createTempLabelRow.appendChild(createTempValue);
  const createTempSlider = el('input') as HTMLInputElement;
  createTempSlider.type = 'range';
  createTempSlider.min = '0.1';
  createTempSlider.max = '1.0';
  createTempSlider.step = '0.1';
  createTempSlider.value = '0.7';
  createTempSlider.style.cssText = 'width: 100%; accent-color: #4ade80;';
  createTempSlider.addEventListener('input', () => {
    createTempValue.textContent = createTempSlider.value;
  });
  createTempWrap.appendChild(createTempLabelRow);
  createTempWrap.appendChild(createTempSlider);

  // Top P slider
  const createTopPWrap = el('div');
  createTopPWrap.style.cssText = 'display: flex; flex-direction: column; gap: 6px;';
  const createTopPLabelRow = el('div');
  createTopPLabelRow.style.cssText = 'display: flex; justify-content: space-between; align-items: center;';
  const createTopPLabel = el('div');
  createTopPLabel.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.4);';
  createTopPLabel.textContent = 'Top P';
  const createTopPValue = el('span');
  createTopPValue.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.7); font-variant-numeric: tabular-nums;';
  createTopPValue.textContent = '0.9';
  createTopPLabelRow.appendChild(createTopPLabel);
  createTopPLabelRow.appendChild(createTopPValue);
  const createTopPSlider = el('input') as HTMLInputElement;
  createTopPSlider.type = 'range';
  createTopPSlider.min = '0.1';
  createTopPSlider.max = '1.0';
  createTopPSlider.step = '0.05';
  createTopPSlider.value = '0.9';
  createTopPSlider.style.cssText = 'width: 100%; accent-color: #4ade80;';
  createTopPSlider.addEventListener('input', () => {
    createTopPValue.textContent = parseFloat(createTopPSlider.value).toFixed(2);
  });
  createTopPWrap.appendChild(createTopPLabelRow);
  createTopPWrap.appendChild(createTopPSlider);

  // Context Length select
  const createCtxWrap = el('div');
  createCtxWrap.style.cssText = 'display: flex; flex-direction: column; gap: 6px;';
  const createCtxLabel = el('div');
  createCtxLabel.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.4);';
  createCtxLabel.textContent = 'Context Length';
  const createCtxSelect = el('select') as HTMLSelectElement;
  createCtxSelect.style.cssText = `
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 6px;
    color: rgba(255,255,255,0.9);
    font-size: 13px;
    padding: 5px 9px;
    outline: none;
    width: 100%;
    box-sizing: border-box;
  `;
  [['2048', '2048'], ['4096', '4096 (default)'], ['8192', '8192']].forEach(([val, label]) => {
    const opt = el('option') as HTMLOptionElement;
    opt.value = val;
    opt.textContent = label;
    if (val === '4096') opt.selected = true;
    createCtxSelect.appendChild(opt);
  });
  createCtxWrap.appendChild(createCtxLabel);
  createCtxWrap.appendChild(createCtxSelect);

  createParamsGrid.appendChild(createTempWrap);
  createParamsGrid.appendChild(createTopPWrap);
  createParamsGrid.appendChild(createCtxWrap);

  const createFormError = el('div');
  createFormError.style.cssText = 'font-size: 12px; color: #ef4444; display: none;';

  const createFormActions = el('div');
  createFormActions.style.cssText = 'display: flex; gap: 8px;';
  const createFormSubmit = makeButton('Create', 'primary');
  const createFormCancel = makeButton('Cancel', 'ghost');
  createFormActions.appendChild(createFormSubmit);
  createFormActions.appendChild(createFormCancel);

  createModelForm.appendChild(createFormTitle);
  createModelForm.appendChild(createNameWrap);
  createModelForm.appendChild(createBaseWrap);
  createModelForm.appendChild(createPromptWrap);
  createModelForm.appendChild(createParamsGrid);
  createModelForm.appendChild(createFormError);
  createModelForm.appendChild(createFormActions);

  // Modelfiles list container (inside customModelsBody)
  const modelfilesListEl = el('div');
  modelfilesListEl.style.cssText = 'display: flex; flex-direction: column; gap: 0;';

  customModelsBody.appendChild(modelfilesListEl);
  customModelsBody.appendChild(createModelBtn);
  customModelsBody.appendChild(createModelForm);

  // ── Add Node form logic ──

  addNodeBtn.addEventListener('click', () => {
    addNodeForm.style.display = 'flex';
    addNodeBtn.style.display = 'none';
    addNameInput.focus();
  });

  addFormCancel.addEventListener('click', () => {
    addNodeForm.style.display = 'none';
    addNodeBtn.style.display = '';
    addFormError.style.display = 'none';
    addNameInput.value = '';
    addHostInput.value = '';
    addPortInput.value = '11434';
    addPriorityInput.value = '0';
  });

  addFormSubmit.addEventListener('click', () => {
    void handleAddNode();
  });

  // Allow Enter key in form fields
  [addNameInput, addHostInput, addPortInput, addPriorityInput].forEach((inp) => {
    inp.addEventListener('keydown', (e: KeyboardEvent) => {
      if (e.key === 'Enter') void handleAddNode();
      if (e.key === 'Escape') addFormCancel.click();
    });
  });

  async function handleAddNode(): Promise<void> {
    const name = addNameInput.value.trim();
    const host = addHostInput.value.trim();
    const port = parseInt(addPortInput.value, 10);
    const priority = parseInt(addPriorityInput.value, 10);

    if (!name || !host) {
      addFormError.textContent = 'Name and host are required.';
      addFormError.style.display = '';
      return;
    }
    if (isNaN(port) || port < 1 || port > 65535) {
      addFormError.textContent = 'Port must be between 1 and 65535.';
      addFormError.style.display = '';
      return;
    }

    addFormError.style.display = 'none';
    addFormSubmit.disabled = true;
    addFormSubmit.textContent = 'Adding...';

    try {
      await callbacks.kernelRequest('copper/nodes/add', {
        name,
        host,
        port,
        priority: isNaN(priority) ? 0 : priority,
      });
      // Reset and close form
      addFormCancel.click();
      // Refresh all data
      await fetchAll();
    } catch (err) {
      addFormError.textContent = `Error: ${err instanceof Error ? err.message : String(err)}`;
      addFormError.style.display = '';
    } finally {
      addFormSubmit.disabled = false;
      addFormSubmit.textContent = 'Add';
    }
  }

  // ── Custom Models form logic ──

  createModelBtn.addEventListener('click', () => {
    // Populate base model dropdown from current lastModels
    createBaseSelect.innerHTML = '';
    if (lastModels.length === 0) {
      const opt = el('option') as HTMLOptionElement;
      opt.value = '';
      opt.textContent = 'No models available';
      createBaseSelect.appendChild(opt);
    } else {
      for (const m of lastModels) {
        const opt = el('option') as HTMLOptionElement;
        opt.value = m.name;
        opt.textContent = m.name;
        createBaseSelect.appendChild(opt);
      }
    }
    createModelForm.style.display = 'flex';
    createModelBtn.style.display = 'none';
    createNameInput.focus();
  });

  createFormCancel.addEventListener('click', () => {
    createModelForm.style.display = 'none';
    createModelBtn.style.display = '';
    createFormError.style.display = 'none';
    extractInfoEl.style.display = 'none';
    createNameInput.value = '';
    createPromptTextarea.value = '';
    createTempSlider.value = '0.7';
    createTempValue.textContent = '0.7';
    createTopPSlider.value = '0.9';
    createTopPValue.textContent = '0.90';
    createCtxSelect.value = '4096';
  });

  createFormSubmit.addEventListener('click', () => {
    void handleCreateModelfile();
  });

  extractBtn.addEventListener('click', () => {
    void handleAutoExtract();
  });

  async function handleCreateModelfile(): Promise<void> {
    const name = createNameInput.value.trim();
    const baseModel = createBaseSelect.value;
    const systemPrompt = createPromptTextarea.value;
    const temperature = parseFloat(createTempSlider.value);
    const topP = parseFloat(createTopPSlider.value);
    const numCtx = parseInt(createCtxSelect.value, 10);

    if (!/^[a-z0-9][a-z0-9_-]*$/.test(name)) {
      createFormError.textContent = 'Name must start with a lowercase letter or digit and contain only lowercase letters, digits, hyphens, and underscores.';
      createFormError.style.display = '';
      return;
    }
    if (!baseModel) {
      createFormError.textContent = 'A base model is required.';
      createFormError.style.display = '';
      return;
    }

    createFormError.style.display = 'none';
    createFormSubmit.disabled = true;
    createFormSubmit.textContent = 'Creating...';

    try {
      await callbacks.kernelRequest('copper/modelfiles/create', {
        name,
        base_model: baseModel,
        system_prompt: systemPrompt,
        parameters: { temperature, top_p: topP, num_ctx: numCtx },
      });
      createFormCancel.click();
      await fetchModelfiles();
      renderCustomModels();
    } catch (err) {
      createFormError.textContent = `Error: ${err instanceof Error ? err.message : String(err)}`;
      createFormError.style.display = '';
    } finally {
      createFormSubmit.disabled = false;
      createFormSubmit.textContent = 'Create';
    }
  }

  async function handleAutoExtract(): Promise<void> {
    extractBtn.disabled = true;
    extractBtn.textContent = 'Extracting...';
    extractInfoEl.style.display = 'none';
    try {
      const result = await callbacks.kernelRequest('copper/modelfiles/extract', {}) as ExtractResult;
      createPromptTextarea.value = result.system_prompt;
      const sourceList = result.sources.join(', ');
      let infoText = `Generated ${result.word_count} words from ${sourceList}`;
      if (result.memory_count > 0) infoText += ` (${result.memory_count} memories)`;
      if (result.truncated) infoText += ' — truncated to fit context limit';
      extractInfoEl.textContent = infoText;
      extractInfoEl.style.display = '';
      extractInfoEl.style.color = result.truncated ? '#fbbf24' : 'rgba(255,255,255,0.4)';
    } catch (err) {
      createFormError.textContent = `Extract error: ${err instanceof Error ? err.message : String(err)}`;
      createFormError.style.display = '';
    } finally {
      extractBtn.disabled = false;
      extractBtn.textContent = 'Auto-generate from Talking Rock';
    }
  }

  async function handleBuildModelfile(name: string): Promise<void> {
    try {
      const resp = await callbacks.kernelRequest('copper/modelfiles/build', { name }) as CopperBuildResponse;
      if (!resp.copper_available) return;
      const initialTask: CopperTaskStatus = {
        copper_available: true,
        task_id: resp.task_id,
        status: 'running',
        model: name,
        target_node: null,
        progress: {},
        result: null,
        error: null,
        task_type: 'build',
      };
      activeTasks.set(resp.task_id, initialTask);
      renderTasks();
      startTaskPolling();
    } catch (err) {
      console.error('[Copper] Build error:', err);
    }
  }

  async function handleDeleteModelfile(name: string): Promise<void> {
    try {
      await callbacks.kernelRequest('copper/modelfiles/delete', { name });
      await fetchModelfiles();
      renderCustomModels();
    } catch (err) {
      console.error('[Copper] Delete modelfile error:', err);
    }
  }

  // ── Render helpers ──────────────────────────────────────────────────

  /** Render the "not running" state and hide all data panels. */
  function showNotRunning(): void {
    notRunningEl.style.display = 'flex';
    nodesPanel.style.display = 'none';
    addNodeSection.style.display = 'none';
    modelsPanel.style.display = 'none';
    customModelsPanel.style.display = 'none';
    tasksPanel.style.display = 'none';
    setStatusBadge(statusBadge, 'offline');
  }

  /** Show data panels and hide the "not running" placeholder. */
  function showData(): void {
    notRunningEl.style.display = 'none';
    nodesPanel.style.display = '';
    addNodeSection.style.display = '';
    modelsPanel.style.display = '';
    customModelsPanel.style.display = '';
    setStatusBadge(statusBadge, 'connected');
  }

  /** Build and render node cards from combined status + config data. */
  function renderNodes(): void {
    nodesBody.innerHTML = '';

    if (lastNodes.length === 0) {
      const empty = el('div');
      empty.style.cssText = 'font-size: 13px; color: rgba(255,255,255,0.3); padding: 8px 0;';
      empty.textContent = 'No nodes configured. Add one below.';
      nodesBody.appendChild(empty);
      return;
    }

    const grid = el('div');
    grid.style.cssText = `
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
    `;

    for (const node of lastNodes) {
      const status = lastStatus?.nodes[node.name] ?? null;
      grid.appendChild(buildNodeCard(node, status));
    }

    nodesBody.appendChild(grid);
  }

  /** Build a single node card element. */
  function buildNodeCard(
    node: CopperNodeConfig,
    status: CopperNodeStatus | null,
  ): HTMLElement {
    const card = el('div');
    card.style.cssText = `
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 8px;
      padding: 12px 14px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      min-width: 220px;
      flex: 1;
      max-width: 340px;
    `;

    // Card header: name + alive dot
    const cardHead = el('div');
    cardHead.style.cssText = 'display: flex; align-items: center; justify-content: space-between; gap: 8px;';

    const nameEl = el('div');
    nameEl.style.cssText = 'font-size: 14px; font-weight: 600; color: rgba(255,255,255,0.9); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;';
    nameEl.textContent = node.name;

    const aliveDot = el('span');
    const alive = status?.alive ?? false;
    aliveDot.style.cssText = `
      width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
      background: ${alive ? '#22c55e' : '#ef4444'};
      box-shadow: ${alive ? '0 0 6px rgba(34,197,94,0.5)' : 'none'};
    `;
    aliveDot.title = alive ? 'Alive' : 'Unreachable';

    cardHead.appendChild(nameEl);
    cardHead.appendChild(aliveDot);
    card.appendChild(cardHead);

    // Host:port
    const hostEl = el('div');
    hostEl.style.cssText = 'font-size: 12px; color: rgba(255,255,255,0.4); font-variant-numeric: tabular-nums;';
    hostEl.textContent = `${node.host}:${node.port}`;
    card.appendChild(hostEl);

    // Stats row: latency / models / active
    const statsRow = el('div');
    statsRow.style.cssText = 'display: flex; gap: 12px; font-size: 12px; color: rgba(255,255,255,0.55);';

    const latencyEl = el('span');
    latencyEl.textContent = status ? `${status.latency_ms}ms` : '—';
    latencyEl.title = 'Latency';

    const modelsCountEl = el('span');
    const modelCount = status?.models.length ?? 0;
    modelsCountEl.textContent = `${modelCount} model${modelCount !== 1 ? 's' : ''}`;

    const activeEl = el('span');
    const activeCount = status?.active_requests ?? 0;
    activeEl.textContent = `${activeCount} active`;
    activeEl.style.color = activeCount > 0 ? '#fbbf24' : 'rgba(255,255,255,0.55)';

    statsRow.appendChild(latencyEl);
    statsRow.appendChild(modelsCountEl);
    statsRow.appendChild(activeEl);
    card.appendChild(statsRow);

    // Error message if present
    if (status?.error) {
      const errEl = el('div');
      errEl.style.cssText = 'font-size: 11px; color: #f87171; padding: 4px 6px; background: rgba(239,68,68,0.08); border-radius: 4px;';
      errEl.textContent = status.error;
      card.appendChild(errEl);
    }

    // Controls row: Enable/Disable toggle + Priority + Remove
    const controls = el('div');
    controls.style.cssText = `
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
      padding-top: 4px;
      border-top: 1px solid rgba(255,255,255,0.05);
      margin-top: 2px;
    `;

    // Enable/Disable toggle
    const toggleBtn = makeButton(node.enabled ? 'Disable' : 'Enable', node.enabled ? 'ghost' : 'primary');
    toggleBtn.addEventListener('click', () => {
      void handleToggleNode(node.name, node.enabled);
    });
    controls.appendChild(toggleBtn);

    // Priority controls
    const priorityWrap = el('div');
    priorityWrap.style.cssText = 'display: flex; align-items: center; gap: 4px; margin-left: auto;';

    const priorityLabel = el('span');
    priorityLabel.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.4);';
    priorityLabel.textContent = 'Priority:';

    const downBtn = makeButton('\u25BE', 'ghost');
    downBtn.style.padding = '2px 6px';
    downBtn.title = 'Lower priority';
    downBtn.addEventListener('click', () => {
      void handleSetPriority(node.name, node.priority - 1);
    });

    const priorityVal = el('span');
    priorityVal.style.cssText = 'font-size: 12px; font-weight: 600; color: rgba(255,255,255,0.7); min-width: 20px; text-align: center; font-variant-numeric: tabular-nums;';
    priorityVal.textContent = String(node.priority);

    const upBtn = makeButton('\u25B4', 'ghost');
    upBtn.style.padding = '2px 6px';
    upBtn.title = 'Raise priority';
    upBtn.addEventListener('click', () => {
      void handleSetPriority(node.name, node.priority + 1);
    });

    priorityWrap.appendChild(priorityLabel);
    priorityWrap.appendChild(downBtn);
    priorityWrap.appendChild(priorityVal);
    priorityWrap.appendChild(upBtn);
    controls.appendChild(priorityWrap);

    // Remove button with inline confirm
    const removeWrap = el('div');
    removeWrap.style.cssText = 'display: flex; align-items: center; gap: 4px;';

    if (pendingRemoveNode === node.name) {
      // Confirmation state
      const confirmLabel = el('span');
      confirmLabel.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.5);';
      confirmLabel.textContent = 'Sure?';

      const confirmYes = makeButton('Yes', 'danger');
      confirmYes.addEventListener('click', () => {
        void handleRemoveNode(node.name);
      });

      const confirmNo = makeButton('No', 'ghost');
      confirmNo.addEventListener('click', () => {
        pendingRemoveNode = null;
        renderNodes();
      });

      removeWrap.appendChild(confirmLabel);
      removeWrap.appendChild(confirmYes);
      removeWrap.appendChild(confirmNo);
    } else {
      const removeBtn = makeButton('\u{1F5D1}', 'ghost');
      removeBtn.title = 'Remove node';
      removeBtn.style.fontSize = '13px';
      removeBtn.addEventListener('click', () => {
        pendingRemoveNode = node.name;
        renderNodes();
      });
      removeWrap.appendChild(removeBtn);
    }

    controls.appendChild(removeWrap);
    card.appendChild(controls);

    return card;
  }

  /** Render the models table. */
  function renderModels(): void {
    modelsBody.innerHTML = '';

    if (lastModels.length === 0) {
      const empty = el('div');
      empty.style.cssText = 'font-size: 13px; color: rgba(255,255,255,0.3); padding: 8px 0;';
      empty.textContent = 'No models found across nodes.';
      modelsBody.appendChild(empty);
      return;
    }

    const table = el('div');
    table.style.cssText = 'display: flex; flex-direction: column; gap: 0;';

    // Header row
    const headerRow = el('div');
    headerRow.style.cssText = `
      display: grid;
      grid-template-columns: 1fr auto auto;
      gap: 12px;
      padding: 4px 8px 8px;
      font-size: 11px;
      color: rgba(255,255,255,0.35);
      text-transform: uppercase;
      letter-spacing: 0.04em;
      border-bottom: 1px solid rgba(255,255,255,0.06);
    `;
    const hModel = el('span'); hModel.textContent = 'Model';
    const hNodes = el('span'); hNodes.textContent = 'Available on';
    const hAction = el('span');
    headerRow.appendChild(hModel);
    headerRow.appendChild(hNodes);
    headerRow.appendChild(hAction);
    table.appendChild(headerRow);

    for (const model of lastModels) {
      const row = buildModelRow(model);
      table.appendChild(row);
    }

    modelsBody.appendChild(table);
  }

  /** Build a single model row. */
  function buildModelRow(model: CopperModelEntry): HTMLElement {
    const row = el('div');
    row.style.cssText = `
      display: grid;
      grid-template-columns: 1fr auto auto;
      gap: 12px;
      padding: 7px 8px;
      align-items: center;
      border-bottom: 1px solid rgba(255,255,255,0.03);
      font-size: 13px;
    `;
    row.addEventListener('mouseenter', () => {
      row.style.background = 'rgba(255,255,255,0.02)';
    });
    row.addEventListener('mouseleave', () => {
      row.style.background = '';
    });

    const nameEl = el('div');
    nameEl.style.cssText = 'color: rgba(255,255,255,0.85); font-weight: 500; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;';
    nameEl.textContent = model.name;

    const nodesEl = el('div');
    nodesEl.style.cssText = 'display: flex; gap: 4px; flex-wrap: wrap; justify-content: flex-end;';
    for (const nodeName of model.nodes) {
      const tag = el('span');
      tag.style.cssText = `
        font-size: 11px;
        padding: 1px 6px;
        border-radius: 4px;
        background: rgba(74, 222, 128, 0.1);
        border: 1px solid rgba(74, 222, 128, 0.2);
        color: rgba(74, 222, 128, 0.8);
      `;
      tag.textContent = nodeName;
      nodesEl.appendChild(tag);
    }
    if (model.nodes.length === 0) {
      const none = el('span');
      none.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.3);';
      none.textContent = 'none';
      nodesEl.appendChild(none);
    }

    // Pull button with node selector dropdown
    const pullWrap = el('div');
    pullWrap.style.cssText = 'position: relative;';

    const pullBtn = makeButton('Pull', 'secondary');
    pullBtn.addEventListener('click', () => {
      // Toggle dropdown
      if (pullDropdown.style.display === 'none' || !pullDropdown.style.display) {
        buildPullDropdown(model.name, pullDropdown);
        pullDropdown.style.display = 'block';
      } else {
        pullDropdown.style.display = 'none';
      }
    });

    const pullDropdown = el('div');
    pullDropdown.style.cssText = `
      display: none;
      position: absolute;
      right: 0;
      top: calc(100% + 4px);
      background: rgba(20,20,28,0.97);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 8px;
      min-width: 160px;
      z-index: 100;
      overflow: hidden;
      box-shadow: 0 8px 24px rgba(0,0,0,0.5);
    `;

    pullWrap.appendChild(pullBtn);
    pullWrap.appendChild(pullDropdown);

    // Close dropdown when clicking elsewhere
    document.addEventListener('click', function closeDropdown(e: MouseEvent) {
      if (!pullWrap.contains(e.target as Node)) {
        pullDropdown.style.display = 'none';
        document.removeEventListener('click', closeDropdown);
      }
    });

    row.appendChild(nameEl);
    row.appendChild(nodesEl);
    row.appendChild(pullWrap);

    return row;
  }

  /** Populate the pull dropdown with node options. */
  function buildPullDropdown(modelName: string, dropdown: HTMLElement): void {
    dropdown.innerHTML = '';

    const allNodes = lastNodes.filter(n => n.enabled);

    const dropHeader = el('div');
    dropHeader.style.cssText = 'padding: 6px 10px; font-size: 11px; color: rgba(255,255,255,0.35); text-transform: uppercase; letter-spacing: 0.04em; border-bottom: 1px solid rgba(255,255,255,0.06);';
    dropHeader.textContent = 'Pull to node';
    dropdown.appendChild(dropHeader);

    if (allNodes.length === 0) {
      const noNodes = el('div');
      noNodes.style.cssText = 'padding: 8px 10px; font-size: 12px; color: rgba(255,255,255,0.3);';
      noNodes.textContent = 'No enabled nodes';
      dropdown.appendChild(noNodes);
      return;
    }

    // "All nodes" option
    const allOption = el('div');
    allOption.style.cssText = `
      padding: 8px 10px;
      font-size: 13px;
      color: rgba(255,255,255,0.8);
      cursor: pointer;
      border-bottom: 1px solid rgba(255,255,255,0.04);
    `;
    allOption.textContent = 'All nodes';
    allOption.addEventListener('mouseenter', () => { allOption.style.background = 'rgba(255,255,255,0.06)'; });
    allOption.addEventListener('mouseleave', () => { allOption.style.background = ''; });
    allOption.addEventListener('click', () => {
      dropdown.style.display = 'none';
      void handlePullModel(modelName, null);
    });
    dropdown.appendChild(allOption);

    for (const node of allNodes) {
      const opt = el('div');
      opt.style.cssText = `
        padding: 8px 10px;
        font-size: 13px;
        color: rgba(255,255,255,0.7);
        cursor: pointer;
      `;
      opt.textContent = node.name;
      opt.addEventListener('mouseenter', () => { opt.style.background = 'rgba(255,255,255,0.06)'; });
      opt.addEventListener('mouseleave', () => { opt.style.background = ''; });
      opt.addEventListener('click', () => {
        dropdown.style.display = 'none';
        void handlePullModel(modelName, node.name);
      });
      dropdown.appendChild(opt);
    }
  }

  /** Render the custom modelfiles list. */
  function renderCustomModels(): void {
    modelfilesListEl.innerHTML = '';

    if (lastModelfiles.length === 0) {
      const empty = el('div');
      empty.style.cssText = 'font-size: 13px; color: rgba(255,255,255,0.3); padding: 8px 0;';
      empty.textContent = 'No custom models yet.';
      modelfilesListEl.appendChild(empty);
      return;
    }

    // Header row
    const headerRow = el('div');
    headerRow.style.cssText = `
      display: grid;
      grid-template-columns: 1fr auto auto auto;
      gap: 12px;
      padding: 4px 8px 8px;
      font-size: 11px;
      color: rgba(255,255,255,0.35);
      text-transform: uppercase;
      letter-spacing: 0.04em;
      border-bottom: 1px solid rgba(255,255,255,0.06);
    `;
    const hName = el('span'); hName.textContent = 'Name';
    const hBase = el('span'); hBase.textContent = 'Base';
    const hUpdated = el('span'); hUpdated.textContent = 'Updated';
    const hActions = el('span');
    headerRow.appendChild(hName);
    headerRow.appendChild(hBase);
    headerRow.appendChild(hUpdated);
    headerRow.appendChild(hActions);
    modelfilesListEl.appendChild(headerRow);

    for (const mf of lastModelfiles) {
      const row = el('div');
      row.style.cssText = `
        display: grid;
        grid-template-columns: 1fr auto auto auto;
        gap: 12px;
        padding: 7px 8px;
        align-items: center;
        border-bottom: 1px solid rgba(255,255,255,0.03);
        font-size: 13px;
      `;
      row.addEventListener('mouseenter', () => { row.style.background = 'rgba(255,255,255,0.02)'; });
      row.addEventListener('mouseleave', () => { row.style.background = ''; });

      const nameEl = el('div');
      nameEl.style.cssText = 'color: rgba(255,255,255,0.85); font-weight: 600; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;';
      nameEl.textContent = mf.name;

      const baseEl = el('div');
      baseEl.style.cssText = 'font-size: 12px; color: rgba(255,255,255,0.5); white-space: nowrap;';
      baseEl.textContent = mf.base_model;

      const updatedEl = el('div');
      updatedEl.style.cssText = 'font-size: 12px; color: rgba(255,255,255,0.35); white-space: nowrap; font-variant-numeric: tabular-nums;';
      try {
        updatedEl.textContent = new Date(mf.updated_at).toLocaleString();
      } catch {
        updatedEl.textContent = mf.updated_at;
      }

      const actionsEl = el('div');
      actionsEl.style.cssText = 'display: flex; gap: 6px;';

      const buildBtn = makeButton('Build', 'secondary');
      buildBtn.addEventListener('click', () => {
        void handleBuildModelfile(mf.name);
      });

      const deleteBtn = makeButton('\u{1F5D1}', 'danger');
      deleteBtn.style.fontSize = '13px';
      deleteBtn.title = 'Delete modelfile';
      deleteBtn.addEventListener('click', () => {
        if (window.confirm(`Delete custom model "${mf.name}"?`)) {
          void handleDeleteModelfile(mf.name);
        }
      });

      actionsEl.appendChild(buildBtn);
      actionsEl.appendChild(deleteBtn);

      row.appendChild(nameEl);
      row.appendChild(baseEl);
      row.appendChild(updatedEl);
      row.appendChild(actionsEl);
      modelfilesListEl.appendChild(row);
    }
  }

  /** Render the active tasks panel. */
  function renderTasks(): void {
    if (activeTasks.size === 0) {
      tasksPanel.style.display = 'none';
      return;
    }

    tasksPanel.style.display = '';
    tasksBody.innerHTML = '';

    for (const [taskId, task] of activeTasks) {
      tasksBody.appendChild(buildTaskCard(taskId, task));
    }
  }

  /** Build a task card for an in-progress or recently completed pull. */
  function buildTaskCard(taskId: string, task: CopperTaskStatus): HTMLElement {
    const card = el('div');
    card.style.cssText = `
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.07);
      border-radius: 6px;
      padding: 10px 12px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      margin-bottom: 8px;
    `;

    // Task header
    const taskHead = el('div');
    taskHead.style.cssText = 'display: flex; align-items: center; justify-content: space-between; gap: 8px;';

    const taskModel = el('div');
    taskModel.style.cssText = 'font-size: 13px; font-weight: 600; color: rgba(255,255,255,0.85);';
    taskModel.textContent = task.model;

    const taskTarget = el('div');
    taskTarget.style.cssText = 'font-size: 12px; color: rgba(255,255,255,0.4);';
    taskTarget.textContent = task.target_node ? `\u2192 ${task.target_node}` : '\u2192 all nodes';

    const taskStatusEl = el('div');
    taskStatusEl.style.cssText = `
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 10px;
      font-weight: 500;
    `;
    if (task.status === 'running') {
      taskStatusEl.style.background = 'rgba(251,191,36,0.1)';
      taskStatusEl.style.border = '1px solid rgba(251,191,36,0.25)';
      taskStatusEl.style.color = '#fbbf24';
      taskStatusEl.textContent = task.task_type === 'build' ? 'Building...' : 'Pulling...';
    } else if (task.status === 'completed') {
      taskStatusEl.style.background = 'rgba(74,222,128,0.1)';
      taskStatusEl.style.border = '1px solid rgba(74,222,128,0.25)';
      taskStatusEl.style.color = '#4ade80';
      taskStatusEl.textContent = 'Done';
    } else {
      taskStatusEl.style.background = 'rgba(239,68,68,0.1)';
      taskStatusEl.style.border = '1px solid rgba(239,68,68,0.25)';
      taskStatusEl.style.color = '#ef4444';
      taskStatusEl.textContent = 'Failed';
    }

    taskHead.appendChild(taskModel);
    taskHead.appendChild(taskTarget);
    taskHead.appendChild(taskStatusEl);
    card.appendChild(taskHead);

    // Per-node progress
    if (Object.keys(task.progress).length > 0) {
      const progressWrap = el('div');
      progressWrap.style.cssText = 'display: flex; flex-direction: column; gap: 3px;';

      for (const [nodeName, nodeStatus] of Object.entries(task.progress)) {
        const progRow = el('div');
        progRow.style.cssText = 'display: flex; align-items: center; gap: 8px; font-size: 12px;';

        const progNode = el('span');
        progNode.style.cssText = 'color: rgba(255,255,255,0.5); min-width: 100px;';
        progNode.textContent = nodeName;

        const progStatus = el('span');
        const lowerStatus = nodeStatus.toLowerCase();
        let statusColor = 'rgba(255,255,255,0.6)';
        if (lowerStatus === 'ok' || lowerStatus === 'completed') statusColor = '#4ade80';
        else if (lowerStatus === 'error' || lowerStatus === 'failed') statusColor = '#ef4444';
        else if (lowerStatus === 'pulling') statusColor = '#fbbf24';
        else if (lowerStatus === 'skipped') statusColor = 'rgba(255,255,255,0.3)';
        progStatus.style.color = statusColor;
        progStatus.textContent = nodeStatus;

        progRow.appendChild(progNode);
        progRow.appendChild(progStatus);
        progressWrap.appendChild(progRow);
      }

      card.appendChild(progressWrap);
    }

    // Error message
    if (task.error) {
      const errEl = el('div');
      errEl.style.cssText = 'font-size: 12px; color: #f87171; padding: 4px 6px; background: rgba(239,68,68,0.08); border-radius: 4px;';
      errEl.textContent = task.error;
      card.appendChild(errEl);
    }

    // Task ID (dimmed, for debugging)
    const taskIdEl = el('div');
    taskIdEl.style.cssText = 'font-size: 10px; color: rgba(255,255,255,0.2); font-variant-numeric: tabular-nums;';
    taskIdEl.textContent = `ID: ${taskId}`;
    card.appendChild(taskIdEl);

    return card;
  }

  // ── Backend action handlers ─────────────────────────────────────────

  async function handleToggleNode(name: string, currentlyEnabled: boolean): Promise<void> {
    try {
      if (currentlyEnabled) {
        await callbacks.kernelRequest('copper/nodes/disable', { name });
      } else {
        await callbacks.kernelRequest('copper/nodes/enable', { name });
      }
      await fetchAll();
    } catch (err) {
      console.error('[Copper] Toggle node error:', err);
    }
  }

  async function handleSetPriority(name: string, priority: number): Promise<void> {
    try {
      await callbacks.kernelRequest('copper/nodes/priority', { name, priority });
      await fetchAll();
    } catch (err) {
      console.error('[Copper] Set priority error:', err);
    }
  }

  async function handleRemoveNode(name: string): Promise<void> {
    pendingRemoveNode = null;
    try {
      await callbacks.kernelRequest('copper/nodes/remove', { name });
      await fetchAll();
    } catch (err) {
      console.error('[Copper] Remove node error:', err);
      renderNodes(); // Re-render to clear confirm state
    }
  }

  async function handlePullModel(modelName: string, targetNode: string | null): Promise<void> {
    try {
      const resp = await callbacks.kernelRequest('copper/pull', {
        model: modelName,
        node: targetNode,
      }) as CopperPullResponse;

      if (!resp.copper_available) {
        showNotRunning();
        return;
      }

      // Register task and start task polling
      const initialTask: CopperTaskStatus = {
        copper_available: true,
        task_id: resp.task_id,
        status: 'running',
        model: modelName,
        target_node: targetNode,
        progress: {},
        result: null,
        error: null,
      };
      activeTasks.set(resp.task_id, initialTask);
      renderTasks();
      startTaskPolling();
    } catch (err) {
      console.error('[Copper] Pull model error:', err);
    }
  }

  // ── Fetch logic ─────────────────────────────────────────────────────

  async function fetchStatus(): Promise<boolean> {
    try {
      const result = await callbacks.kernelRequest('copper/status', {}) as CopperStatus;
      if (!result.copper_available) {
        lastStatus = null;
        showNotRunning();
        return false;
      }
      lastStatus = result;
      return true;
    } catch (err) {
      console.error('[Copper] Status fetch error:', err);
      lastStatus = null;
      showNotRunning();
      return false;
    }
  }

  async function fetchNodes(): Promise<void> {
    try {
      const result = await callbacks.kernelRequest('copper/nodes', {}) as CopperNodes;
      if (!result.copper_available) return;
      lastNodes = result.nodes;
    } catch (err) {
      console.error('[Copper] Nodes fetch error:', err);
    }
  }

  async function fetchModels(): Promise<void> {
    try {
      const result = await callbacks.kernelRequest('copper/models', {}) as CopperModels;
      if (!result.copper_available) return;
      lastModels = result.models;
    } catch (err) {
      console.error('[Copper] Models fetch error:', err);
    }
  }

  async function fetchModelfiles(): Promise<void> {
    try {
      const result = await callbacks.kernelRequest('copper/modelfiles', {}) as CopperModelfiles;
      if (!result.copper_available) return;
      lastModelfiles = result.modelfiles;
    } catch (err) {
      console.error('[Copper] Modelfiles fetch error:', err);
    }
  }

  /** Fetch all endpoints and re-render. */
  async function fetchAll(): Promise<void> {
    const available = await fetchStatus();
    if (!available) return;

    await Promise.all([fetchNodes(), fetchModels(), fetchModelfiles()]);
    showData();
    renderNodes();
    renderModels();
    renderCustomModels();
    lastUpdatedEl.textContent = `Updated ${new Date().toLocaleTimeString()}`;
  }

  /** Poll task statuses. Stops automatically when no tasks remain running. */
  async function pollTasks(): Promise<void> {
    const runningIds = [...activeTasks.keys()].filter(
      (id) => activeTasks.get(id)?.status === 'running',
    );

    if (runningIds.length === 0) {
      stopTaskPolling();
      return;
    }

    const updates = await Promise.allSettled(
      runningIds.map((id) =>
        callbacks.kernelRequest(`copper/tasks/${id}`, {}) as Promise<CopperTaskStatus>,
      ),
    );

    let anyChanged = false;
    const completedIds: string[] = [];

    for (let i = 0; i < runningIds.length; i++) {
      const taskId = runningIds[i];
      const update = updates[i];
      if (update.status === 'fulfilled') {
        const taskResult = update.value;
        if (!taskResult.copper_available) continue;
        activeTasks.set(taskId, taskResult);
        anyChanged = true;
        if (taskResult.status !== 'running') {
          completedIds.push(taskId);
        }
      }
    }

    if (anyChanged) {
      renderTasks();
    }

    // Schedule removal of completed/failed tasks after a brief display period
    for (const id of completedIds) {
      setTimeout(() => {
        activeTasks.delete(id);
        renderTasks();
        // Refresh models list after a successful pull
        void fetchModels().then(() => renderModels());
      }, 4000);
    }

    // Check again if still running tasks remain
    const stillRunning = [...activeTasks.values()].some((t) => t.status === 'running');
    if (!stillRunning) {
      stopTaskPolling();
    }
  }

  // ── Polling scheduling ──────────────────────────────────────────────

  function scheduleMainPoll(availableAtLastCheck: boolean): void {
    if (!isPolling) return;
    const interval = availableAtLastCheck ? 10_000 : 30_000;
    mainTimer = setTimeout(async () => {
      const available = await fetchStatus();
      if (available) {
        await Promise.all([fetchNodes(), fetchModels(), fetchModelfiles()]);
        showData();
        renderNodes();
        renderModels();
        renderCustomModels();
        lastUpdatedEl.textContent = `Updated ${new Date().toLocaleTimeString()}`;
      }
      scheduleMainPoll(available);
    }, interval);
  }

  function startTaskPolling(): void {
    if (taskTimer !== null) return; // already running
    taskTimer = setTimeout(function pollLoop() {
      void pollTasks().then(() => {
        const stillRunning = [...activeTasks.values()].some((t) => t.status === 'running');
        if (stillRunning && isPolling) {
          taskTimer = setTimeout(pollLoop, 2500);
        } else {
          taskTimer = null;
        }
      });
    }, 2500);
  }

  function stopTaskPolling(): void {
    if (taskTimer !== null) {
      clearTimeout(taskTimer);
      taskTimer = null;
    }
  }

  function startPolling(): void {
    if (isPolling) return;
    isPolling = true;
    setStatusBadge(statusBadge, 'connecting');
    lastUpdatedEl.textContent = 'Fetching...';

    // Immediately fetch everything, then start recurring poll
    void fetchAll().then(() => {
      const available = lastStatus !== null;
      scheduleMainPoll(available);
    });
  }

  function stopPolling(): void {
    isPolling = false;
    if (mainTimer !== null) {
      clearTimeout(mainTimer);
      mainTimer = null;
    }
    stopTaskPolling();
  }

  return { container, startPolling, stopPolling };
}
