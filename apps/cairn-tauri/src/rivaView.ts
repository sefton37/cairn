/**
 * RIVA View — Agent Orchestrator + Project Manager.
 *
 * Three-pane layout:
 *   Left:   Projects — epics, issues, cycles, research tree
 *   Center: Activity — contracts, audits, CI status, agent sessions
 *   Right:  Chat — conversational interface with RIVA
 */

import { open as openFolderDialog } from '@tauri-apps/plugin-dialog';
import { el, escapeHtml } from './dom';
import { kernelRequest, KernelError } from './kernel';

const PROJECTS_ROOT_KEY = 'riva_projects_root';

// ── Types ──────────────────────────────────────────────────────────────

interface RivaStatus {
  status: string;
  uptime_seconds: number;
  version: string;
}

interface ScannedProject {
  name: string;
  path: string;
  is_git: boolean;
  language?: string;
}

interface PlayAct {
  act_id: string;
  title: string;
  active: boolean;
  color: string | null;
}

interface PmEpic {
  id: string;
  name: string;
  status: string;
  project: string | null;
  priority: string;
  target_quarter: string | null;
  owner: string | null;
  description: string | null;
  success_criteria: string | null;
  notes: string | null;
  act_id: string | null;
  created_at: string;
  updated_at: string;
}

interface PmIssue {
  id: string;
  name: string;
  status: string;
  priority: string;
  type: string;
  epic_id: string | null;
  estimate: string | null;
  assignee: string | null;
  forgejo_link: string | null;
  branch: string | null;
  acceptance_criteria: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

interface PmCycle {
  id: string;
  name: string;
  status: string;
  goal: string | null;
}

interface PmResearchEntry {
  id: string;
  name: string;
  type: string | null;
  project: string | null;
  date: string | null;
}

interface PmDashboard {
  epics: Record<string, number>;
  issues: Record<string, number>;
  active_cycle: { name: string; goal: string } | null;
  recent_research: PmResearchEntry[];
}

interface CiPipeline {
  number: number;
  status: string;
  event: string;
  branch: string;
  message: string;
  started_at: string | number | null;
  finished_at: string | number | null;
}

interface CiRepo {
  id: number;
  full_name: string;
  active: boolean;
}

interface RivaAudit {
  audit_id: string;
  contract_id: string;
  overall_verdict: string;
  verdict_explanation: string;
  audited_at: string;
}

interface RivaContractSummary {
  id: string;
  plan_id: string;
  agent_id: string;
  status: string;
  created_at: string;
}

interface ChatMessage {
  role: 'user' | 'riva';
  content: string;
  timestamp: Date;
  plan?: PlanInline | null;
}

interface PlanInline {
  id: string;
  title: string;
  status: string;
  steps: Array<{ step_number: number; title: string; status: string }>;
}

// ── State ──────────────────────────────────────────────────────────────

let statusPollTimer: number | null = null;
let dataPollTimer: number | null = null;
let selectedEpicId: string | null = null;
const chatMessages: ChatMessage[] = [];

// ── Helpers ────────────────────────────────────────────────────────────

function createStatusBadge(): HTMLElement {
  const badge = el('div');
  badge.id = 'riva-status-badge';
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

function setStatusBadge(badge: HTMLElement, state: 'connected' | 'connecting' | 'offline'): void {
  const dot = state === 'connected' ? '\u25CF' : state === 'connecting' ? '\u25CB' : '\u25CF';
  const color = state === 'connected' ? '#4ade80' : state === 'connecting' ? '#fbbf24' : '#ef4444';
  const bg = state === 'connected'
    ? 'rgba(74, 222, 128, 0.1)'
    : state === 'connecting'
      ? 'rgba(251, 191, 36, 0.1)'
      : 'rgba(239, 68, 68, 0.1)';
  const border = state === 'connected'
    ? 'rgba(74, 222, 128, 0.2)'
    : state === 'connecting'
      ? 'rgba(251, 191, 36, 0.2)'
      : 'rgba(239, 68, 68, 0.2)';
  const label = state === 'connected' ? 'Connected' : state === 'connecting' ? 'Connecting...' : 'Offline';

  badge.style.color = color;
  badge.style.background = bg;
  badge.style.border = `1px solid ${border}`;
  badge.textContent = `${dot} ${label}`;
}

function priorityColor(p: string): string {
  switch (p) {
    case 'Critical': return '#ef4444';
    case 'High': return '#f59e0b';
    case 'Medium': return '#60a5fa';
    case 'Low': return '#6b7280';
    default: return '#6b7280';
  }
}

function statusIcon(s: string): string {
  switch (s) {
    case 'Done': case 'Complete': case 'Archived': return '\u2713'; // ✓
    case 'In Progress': case 'Active': return '\u25CB';              // ○
    case 'Blocked': return '\u25A0';                                 // ■
    default: return '\u2022';                                        // •
  }
}

function statusColor(s: string): string {
  switch (s) {
    case 'Done': case 'Complete': case 'fulfilled': case 'passed': return '#4ade80';
    case 'In Progress': case 'Active': case 'running': return '#60a5fa';
    case 'Blocked': case 'failed': case 'violated': return '#ef4444';
    default: return 'rgba(255, 255, 255, 0.4)';
  }
}

function createPaneHeader(title: string, extra?: HTMLElement): HTMLElement {
  const header = el('div');
  header.style.cssText = `
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 14px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    flex-shrink: 0;
  `;

  const titleEl = el('div');
  titleEl.textContent = title;
  titleEl.style.cssText = `
    font-size: 13px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.7);
    letter-spacing: 0.04em;
    text-transform: uppercase;
  `;
  header.appendChild(titleEl);

  if (extra) header.appendChild(extra);
  return header;
}

function createEmptyState(message: string): HTMLElement {
  const container = el('div');
  container.style.cssText = `
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    color: rgba(255, 255, 255, 0.25);
    font-size: 13px;
    padding: 20px;
    text-align: center;
    line-height: 1.6;
  `;
  container.textContent = message;
  return container;
}

// ── Acts Cache ──────────────────────────────────────────────────────

let cachedActs: PlayAct[] = [];

async function fetchActs(): Promise<PlayAct[]> {
  try {
    const result = await kernelRequest('play/acts/list', {}) as {
      acts: PlayAct[];
    };
    // Filter out system acts (your_story, archived_conversations)
    cachedActs = result.acts.filter(a => a.title !== 'Your Story' && a.title !== 'Archived Conversations');
    return cachedActs;
  } catch {
    return cachedActs; // Return stale cache on failure
  }
}

function getActTitle(actId: string | null): string {
  if (!actId) return 'Unlinked';
  const act = cachedActs.find(a => a.act_id === actId);
  return act?.title ?? actId;
}

function getActColor(actId: string | null): string {
  if (!actId) return 'rgba(255,255,255,0.3)';
  const act = cachedActs.find(a => a.act_id === actId);
  return act?.color ?? '#6b7280';
}

// ── Detail Card Builders ────────────────────────────────────────────

function buildFieldRow(label: string, value: string | null, opts?: {
  color?: string;
  editable?: boolean;
  type?: 'text' | 'select' | 'textarea';
  options?: string[];
  onChange?: (val: string) => void;
}): HTMLElement {
  const row = el('div');
  row.style.cssText = `
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 6px 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  `;

  const labelEl = el('div');
  labelEl.textContent = label;
  labelEl.style.cssText = `
    width: 100px;
    flex-shrink: 0;
    font-size: 11px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.4);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding-top: 6px;
  `;
  row.appendChild(labelEl);

  if (opts?.editable && opts.type === 'select' && opts.options) {
    const select = el('select');
    select.style.cssText = `
      flex: 1;
      background: rgba(0, 0, 0, 0.3);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 6px;
      padding: 5px 8px;
      color: rgba(255, 255, 255, 0.85);
      font-size: 13px;
      outline: none;
    `;
    for (const opt of opts.options) {
      const optEl = el('option');
      optEl.value = opt;
      optEl.textContent = opt;
      if (opt === (value ?? '')) optEl.selected = true;
      select.appendChild(optEl);
    }
    select.addEventListener('change', () => opts.onChange?.(select.value));
    row.appendChild(select);
  } else if (opts?.editable && opts.type === 'textarea') {
    const textarea = el('textarea');
    textarea.value = value ?? '';
    textarea.rows = 3;
    textarea.style.cssText = `
      flex: 1;
      background: rgba(0, 0, 0, 0.3);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 6px;
      padding: 5px 8px;
      color: rgba(255, 255, 255, 0.85);
      font-size: 13px;
      font-family: inherit;
      outline: none;
      resize: vertical;
    `;
    textarea.addEventListener('change', () => opts.onChange?.(textarea.value));
    row.appendChild(textarea);
  } else if (opts?.editable) {
    const input = el('input');
    input.type = 'text';
    input.value = value ?? '';
    input.style.cssText = `
      flex: 1;
      background: rgba(0, 0, 0, 0.3);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 6px;
      padding: 5px 8px;
      color: rgba(255, 255, 255, 0.85);
      font-size: 13px;
      outline: none;
    `;
    input.addEventListener('change', () => opts.onChange?.(input.value));
    row.appendChild(input);
  } else {
    const valEl = el('div');
    valEl.textContent = value || '\u2014';
    valEl.style.cssText = `
      flex: 1;
      font-size: 13px;
      color: ${opts?.color ?? 'rgba(255, 255, 255, 0.8)'};
      padding: 5px 0;
    `;
    row.appendChild(valEl);
  }

  return row;
}

function buildActPicker(currentActId: string | null, onChange: (actId: string) => void): HTMLElement {
  const row = el('div');
  row.style.cssText = `
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  `;

  const labelEl = el('div');
  labelEl.textContent = 'Act';
  labelEl.style.cssText = `
    width: 100px;
    flex-shrink: 0;
    font-size: 11px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.4);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  `;
  row.appendChild(labelEl);

  const select = el('select');
  select.style.cssText = `
    flex: 1;
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 6px;
    padding: 5px 8px;
    color: rgba(255, 255, 255, 0.85);
    font-size: 13px;
    outline: none;
  `;

  for (const act of cachedActs) {
    const opt = el('option');
    opt.value = act.act_id;
    opt.textContent = `${act.color ? '\u25CF ' : ''}${act.title}`;
    if (act.act_id === currentActId) opt.selected = true;
    select.appendChild(opt);
  }

  select.addEventListener('change', () => onChange(select.value));
  row.appendChild(select);

  // Color indicator
  const colorDot = el('div');
  colorDot.style.cssText = `
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: ${getActColor(currentActId)};
    flex-shrink: 0;
  `;
  row.appendChild(colorDot);

  select.addEventListener('change', () => {
    colorDot.style.background = getActColor(select.value);
  });

  return row;
}

function buildEpicDetailCard(
  epic: PmEpic,
  onClose: () => void,
  onSave: () => void,
  onIssueClick: (issueId: string) => void,
): HTMLElement {
  const card = el('div');
  card.style.cssText = `
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  `;

  // Header with close button
  const header = el('div');
  header.style.cssText = `
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 14px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    flex-shrink: 0;
  `;

  const headerLeft = el('div');
  headerLeft.style.cssText = 'display: flex; align-items: center; gap: 8px;';

  const actDot = el('div');
  actDot.style.cssText = `
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: ${getActColor(epic.act_id)};
  `;
  headerLeft.appendChild(actDot);

  const titleEl = el('div');
  titleEl.textContent = epic.name;
  titleEl.style.cssText = `
    font-size: 15px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.9);
  `;
  headerLeft.appendChild(titleEl);
  header.appendChild(headerLeft);

  const closeBtn = el('button');
  closeBtn.textContent = '\u2715';
  closeBtn.style.cssText = `
    background: none;
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 6px;
    color: rgba(255, 255, 255, 0.5);
    font-size: 14px;
    width: 28px;
    height: 28px;
    cursor: pointer;
    transition: all 0.15s;
  `;
  closeBtn.addEventListener('mouseenter', () => { closeBtn.style.background = 'rgba(255,255,255,0.08)'; });
  closeBtn.addEventListener('mouseleave', () => { closeBtn.style.background = 'none'; });
  closeBtn.addEventListener('click', onClose);
  header.appendChild(closeBtn);
  card.appendChild(header);

  // Scrollable fields
  const fields = el('div');
  fields.style.cssText = `
    flex: 1;
    overflow-y: auto;
    padding: 10px 14px;
  `;

  // Pending changes
  const changes: Record<string, string> = {};
  const markDirty = (field: string, value: string) => { changes[field] = value; };

  fields.appendChild(buildActPicker(epic.act_id, (v) => markDirty('act_id', v)));
  fields.appendChild(buildFieldRow('Name', epic.name, {
    editable: true, onChange: (v) => markDirty('name', v),
  }));
  fields.appendChild(buildFieldRow('Status', epic.status, {
    editable: true, type: 'select',
    options: ['Backlog', 'Active', 'Blocked', 'Done', 'Archived'],
    onChange: (v) => markDirty('status', v),
  }));
  fields.appendChild(buildFieldRow('Priority', epic.priority, {
    editable: true, type: 'select',
    options: ['Critical', 'High', 'Medium', 'Low'],
    onChange: (v) => markDirty('priority', v),
  }));
  fields.appendChild(buildFieldRow('Project', epic.project, {
    editable: true, onChange: (v) => markDirty('project', v),
  }));
  fields.appendChild(buildFieldRow('Quarter', epic.target_quarter, {
    editable: true, onChange: (v) => markDirty('target_quarter', v),
  }));
  fields.appendChild(buildFieldRow('Owner', epic.owner, {
    editable: true, onChange: (v) => markDirty('owner', v),
  }));
  fields.appendChild(buildFieldRow('Description', epic.description, {
    editable: true, type: 'textarea', onChange: (v) => markDirty('description', v),
  }));
  fields.appendChild(buildFieldRow('Success Criteria', epic.success_criteria, {
    editable: true, type: 'textarea', onChange: (v) => markDirty('success_criteria', v),
  }));

  // Issues sub-section
  const issueHeader = el('div');
  issueHeader.textContent = 'Issues';
  issueHeader.style.cssText = `
    font-size: 11px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.5);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 14px 0 6px;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
    margin-top: 8px;
  `;
  fields.appendChild(issueHeader);

  const issueList = el('div');
  issueList.id = 'epic-detail-issues';
  issueList.style.cssText = 'padding-bottom: 8px;';
  fields.appendChild(issueList);

  // Load issues for this epic
  (async () => {
    try {
      const result = await kernelRequest('riva/pm/issues/list', { epic_id: epic.id }) as { issues: PmIssue[] };
      if (result.issues.length === 0) {
        const empty = el('div');
        empty.textContent = 'No issues yet';
        empty.style.cssText = 'font-size: 12px; color: rgba(255,255,255,0.3); padding: 8px 0;';
        issueList.appendChild(empty);
      } else {
        for (const issue of result.issues) {
          const row = el('div');
          row.style.cssText = `
            display: flex;
            align-items: center;
            gap: 6px;
            padding: 6px 8px;
            border-radius: 5px;
            cursor: pointer;
            transition: background 0.15s;
          `;
          row.addEventListener('mouseenter', () => { row.style.background = 'rgba(255,255,255,0.05)'; });
          row.addEventListener('mouseleave', () => { row.style.background = 'transparent'; });
          row.addEventListener('click', () => onIssueClick(issue.id));

          const icon = el('div');
          icon.textContent = statusIcon(issue.status);
          icon.style.cssText = `color: ${statusColor(issue.status)}; font-size: 11px; width: 14px;`;
          row.appendChild(icon);

          const name = el('div');
          name.textContent = issue.name;
          name.style.cssText = `
            flex: 1; font-size: 12px; color: rgba(255,255,255,0.75);
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
          `;
          row.appendChild(name);

          issueList.appendChild(row);
        }
      }
    } catch { /* issues load is best-effort */ }
  })();

  card.appendChild(fields);

  // Save bar
  const saveBar = el('div');
  saveBar.style.cssText = `
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    padding: 10px 14px;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
    flex-shrink: 0;
  `;

  const saveBtn = el('button');
  saveBtn.textContent = 'Save';
  saveBtn.style.cssText = `
    background: rgba(34, 197, 94, 0.15);
    border: 1px solid rgba(34, 197, 94, 0.4);
    border-radius: 8px;
    padding: 6px 18px;
    color: #22c55e;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s;
  `;
  saveBtn.addEventListener('mouseenter', () => { saveBtn.style.background = 'rgba(34, 197, 94, 0.25)'; });
  saveBtn.addEventListener('mouseleave', () => { saveBtn.style.background = 'rgba(34, 197, 94, 0.15)'; });
  saveBtn.addEventListener('click', async () => {
    if (Object.keys(changes).length === 0) return;
    try {
      await kernelRequest('riva/pm/epics/update', { epic_id: epic.id, ...changes });
      saveBtn.textContent = 'Saved';
      saveBtn.style.color = '#4ade80';
      setTimeout(() => { saveBtn.textContent = 'Save'; saveBtn.style.color = '#22c55e'; }, 1500);
      onSave();
    } catch (err) {
      saveBtn.textContent = 'Error';
      saveBtn.style.color = '#ef4444';
      setTimeout(() => { saveBtn.textContent = 'Save'; saveBtn.style.color = '#22c55e'; }, 2000);
    }
  });
  saveBar.appendChild(saveBtn);
  card.appendChild(saveBar);

  return card;
}

function buildIssueDetailCard(
  issue: PmIssue,
  onClose: () => void,
  onSave: () => void,
): HTMLElement {
  const card = el('div');
  card.style.cssText = `
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  `;

  const header = el('div');
  header.style.cssText = `
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 14px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    flex-shrink: 0;
  `;

  const headerLeft = el('div');
  headerLeft.style.cssText = 'display: flex; align-items: center; gap: 8px;';

  const icon = el('div');
  icon.textContent = statusIcon(issue.status);
  icon.style.cssText = `color: ${statusColor(issue.status)}; font-size: 14px;`;
  headerLeft.appendChild(icon);

  const titleEl = el('div');
  titleEl.textContent = issue.name;
  titleEl.style.cssText = 'font-size: 15px; font-weight: 600; color: rgba(255,255,255,0.9);';
  headerLeft.appendChild(titleEl);
  header.appendChild(headerLeft);

  const closeBtn = el('button');
  closeBtn.textContent = '\u2715';
  closeBtn.style.cssText = `
    background: none; border: 1px solid rgba(255,255,255,0.15);
    border-radius: 6px; color: rgba(255,255,255,0.5);
    font-size: 14px; width: 28px; height: 28px; cursor: pointer;
    transition: all 0.15s;
  `;
  closeBtn.addEventListener('mouseenter', () => { closeBtn.style.background = 'rgba(255,255,255,0.08)'; });
  closeBtn.addEventListener('mouseleave', () => { closeBtn.style.background = 'none'; });
  closeBtn.addEventListener('click', onClose);
  header.appendChild(closeBtn);
  card.appendChild(header);

  const fields = el('div');
  fields.style.cssText = 'flex: 1; overflow-y: auto; padding: 10px 14px;';

  const changes: Record<string, string> = {};
  const markDirty = (field: string, value: string) => { changes[field] = value; };

  fields.appendChild(buildFieldRow('Name', issue.name, {
    editable: true, onChange: (v) => markDirty('name', v),
  }));
  fields.appendChild(buildFieldRow('Status', issue.status, {
    editable: true, type: 'select',
    options: ['Backlog', 'In Progress', 'Blocked', 'Done'],
    onChange: (v) => markDirty('status', v),
  }));
  fields.appendChild(buildFieldRow('Priority', issue.priority, {
    editable: true, type: 'select',
    options: ['Critical', 'High', 'Medium', 'Low'],
    onChange: (v) => markDirty('priority', v),
  }));
  fields.appendChild(buildFieldRow('Type', issue.type, {
    editable: true, type: 'select',
    options: ['Feature', 'Bug', 'Chore', 'Spike'],
    onChange: (v) => markDirty('type', v),
  }));
  fields.appendChild(buildFieldRow('Assignee', issue.assignee, {
    editable: true, onChange: (v) => markDirty('assignee', v),
  }));
  fields.appendChild(buildFieldRow('Estimate', issue.estimate, {
    editable: true, onChange: (v) => markDirty('estimate', v),
  }));
  fields.appendChild(buildFieldRow('Branch', issue.branch, {
    editable: true, onChange: (v) => markDirty('branch', v),
  }));
  fields.appendChild(buildFieldRow('Forgejo', issue.forgejo_link));
  fields.appendChild(buildFieldRow('Acceptance', issue.acceptance_criteria, {
    editable: true, type: 'textarea', onChange: (v) => markDirty('acceptance_criteria', v),
  }));
  fields.appendChild(buildFieldRow('Notes', issue.notes, {
    editable: true, type: 'textarea', onChange: (v) => markDirty('notes', v),
  }));

  card.appendChild(fields);

  const saveBar = el('div');
  saveBar.style.cssText = `
    display: flex; justify-content: flex-end; gap: 8px;
    padding: 10px 14px; border-top: 1px solid rgba(255,255,255,0.08); flex-shrink: 0;
  `;

  const saveBtn = el('button');
  saveBtn.textContent = 'Save';
  saveBtn.style.cssText = `
    background: rgba(34, 197, 94, 0.15); border: 1px solid rgba(34, 197, 94, 0.4);
    border-radius: 8px; padding: 6px 18px; color: #22c55e;
    font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.15s;
  `;
  saveBtn.addEventListener('mouseenter', () => { saveBtn.style.background = 'rgba(34, 197, 94, 0.25)'; });
  saveBtn.addEventListener('mouseleave', () => { saveBtn.style.background = 'rgba(34, 197, 94, 0.15)'; });
  saveBtn.addEventListener('click', async () => {
    if (Object.keys(changes).length === 0) return;
    try {
      await kernelRequest('riva/pm/issues/update', { issue_id: issue.id, ...changes });
      saveBtn.textContent = 'Saved';
      saveBtn.style.color = '#4ade80';
      setTimeout(() => { saveBtn.textContent = 'Save'; saveBtn.style.color = '#22c55e'; }, 1500);
      onSave();
    } catch {
      saveBtn.textContent = 'Error';
      saveBtn.style.color = '#ef4444';
      setTimeout(() => { saveBtn.textContent = 'Save'; saveBtn.style.color = '#22c55e'; }, 2000);
    }
  });
  saveBar.appendChild(saveBtn);
  card.appendChild(saveBar);

  return card;
}

// ── Projects Pane (Left) ────────────────────────────────────────────

function createProjectsPane(
  onSelectEpic: (epicId: string | null) => void,
  onOpenEpic: (epicId: string) => void,
): { pane: HTMLElement; refresh: () => Promise<void> } {
  const pane = el('div');
  pane.className = 'riva-projects';
  pane.style.cssText = `
    width: 240px;
    min-width: 200px;
    display: flex;
    flex-direction: column;
    border-right: 1px solid rgba(255, 255, 255, 0.08);
    overflow: hidden;
  `;

  // Gear icon to set projects root folder
  const gearBtn = el('button');
  gearBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`;
  gearBtn.title = localStorage.getItem(PROJECTS_ROOT_KEY) || 'Set projects folder';
  gearBtn.style.cssText = `
    background: none;
    border: none;
    color: rgba(255, 255, 255, 0.4);
    cursor: pointer;
    padding: 2px;
    display: flex;
    align-items: center;
    transition: color 0.15s;
  `;
  gearBtn.addEventListener('mouseenter', () => { gearBtn.style.color = 'rgba(255, 255, 255, 0.8)'; });
  gearBtn.addEventListener('mouseleave', () => { gearBtn.style.color = 'rgba(255, 255, 255, 0.4)'; });
  gearBtn.addEventListener('click', async () => {
    const selected = await openFolderDialog({
      directory: true,
      multiple: false,
      title: 'Select Projects Root Folder',
      defaultPath: localStorage.getItem(PROJECTS_ROOT_KEY) || undefined,
    });
    if (selected && typeof selected === 'string') {
      localStorage.setItem(PROJECTS_ROOT_KEY, selected);
      gearBtn.title = selected;
      refresh();
    }
  });

  pane.appendChild(createPaneHeader('Projects', gearBtn));

  const listContainer = el('div');
  listContainer.style.cssText = `
    flex: 1;
    overflow-y: auto;
    padding: 8px 0;
  `;
  pane.appendChild(listContainer);

  // Summary bar
  const summaryBar = el('div');
  summaryBar.style.cssText = `
    padding: 10px 14px;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
    font-size: 11px;
    color: rgba(255, 255, 255, 0.4);
    flex-shrink: 0;
  `;
  pane.appendChild(summaryBar);

  let selectedProjectPath: string | null = null;

  async function refresh(): Promise<void> {
    const root = localStorage.getItem(PROJECTS_ROOT_KEY);
    if (!root) {
      listContainer.innerHTML = '';
      listContainer.appendChild(
        createEmptyState('Click the gear icon to set your projects folder')
      );
      summaryBar.textContent = '';
      return;
    }

    try {
      const result = await kernelRequest('riva/projects/scan', { root }) as {
        projects: ScannedProject[];
        root: string;
      };
      renderProjectList(result.projects);
      summaryBar.textContent = `${result.projects.length} projects \u00B7 ${root}`;
    } catch {
      listContainer.innerHTML = '';
      listContainer.appendChild(createEmptyState('Could not scan projects folder'));
      summaryBar.textContent = '';
    }
  }

  function langColor(lang: string | undefined): string {
    switch (lang) {
      case 'Python': return '#3572A5';
      case 'Rust': return '#DEA584';
      case 'Node': return '#f1e05a';
      case 'Go': return '#00ADD8';
      case 'Java': return '#b07219';
      case 'Ruby': return '#701516';
      case 'Elixir': return '#6e4a7e';
      case 'C/C++': return '#555555';
      default: return 'rgba(255, 255, 255, 0.2)';
    }
  }

  function renderProjectList(projects: ScannedProject[]): void {
    listContainer.innerHTML = '';

    if (projects.length === 0) {
      listContainer.appendChild(createEmptyState('No project folders found'));
      return;
    }

    for (const proj of projects) {
      const card = el('div');
      const isSelected = selectedProjectPath === proj.path;
      card.style.cssText = `
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 10px 14px;
        cursor: pointer;
        transition: background 0.15s;
        background: ${isSelected ? 'rgba(59, 130, 246, 0.12)' : 'transparent'};
        border-left: 3px solid ${isSelected ? '#3b82f6' : 'transparent'};
      `;

      card.addEventListener('mouseenter', () => {
        if (!isSelected) card.style.background = 'rgba(255, 255, 255, 0.04)';
      });
      card.addEventListener('mouseleave', () => {
        if (!isSelected) card.style.background = 'transparent';
      });
      card.addEventListener('click', () => {
        selectedProjectPath = proj.path;
        onSelectEpic(null);
        onOpenEpic(proj.path);
        refresh();
      });

      // Language dot
      const dot = el('div');
      dot.style.cssText = `
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: ${langColor(proj.language)};
        flex-shrink: 0;
        border: 1px solid rgba(255, 255, 255, 0.1);
      `;
      dot.title = proj.language || 'Unknown';
      card.appendChild(dot);

      // Name + path info
      const info = el('div');
      info.style.cssText = 'flex: 1; min-width: 0;';

      const nameEl = el('div');
      nameEl.textContent = proj.name;
      nameEl.style.cssText = `
        font-size: 13px;
        color: rgba(255, 255, 255, 0.85);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      `;
      info.appendChild(nameEl);

      const metaEl = el('div');
      const parts: string[] = [];
      if (proj.language) parts.push(proj.language);
      if (proj.is_git) parts.push('git');
      metaEl.textContent = parts.join(' \u00B7 ') || 'folder';
      metaEl.style.cssText = `
        font-size: 11px;
        color: rgba(255, 255, 255, 0.35);
        margin-top: 1px;
      `;
      info.appendChild(metaEl);

      card.appendChild(info);

      // Git badge
      if (proj.is_git) {
        const gitBadge = el('div');
        gitBadge.textContent = '\u2022';
        gitBadge.title = 'Git repository';
        gitBadge.style.cssText = `
          font-size: 18px;
          color: #4ade80;
          flex-shrink: 0;
          line-height: 1;
        `;
        card.appendChild(gitBadge);
      }

      listContainer.appendChild(card);
    }
  }

  return { pane, refresh };
}

// ── Activity Pane (Center) ──────────────────────────────────────────

function createActivityPane(): {
  pane: HTMLElement;
  refresh: (epicId: string | null) => Promise<void>;
  showEpicDetail: (epicId: string) => Promise<void>;
  showIssueDetail: (issueId: string) => Promise<void>;
  closeDetail: () => void;
} {
  const pane = el('div');
  pane.className = 'riva-activity';
  pane.style.cssText = `
    flex: 1;
    display: flex;
    flex-direction: column;
    border-right: 1px solid rgba(255, 255, 255, 0.08);
    min-width: 0;
    overflow: hidden;
  `;

  const headerEl = createPaneHeader('Activity');
  pane.appendChild(headerEl);

  const content = el('div');
  content.style.cssText = `
    flex: 1;
    overflow-y: auto;
    padding: 8px;
  `;
  pane.appendChild(content);

  // Detail card container (hidden by default, replaces content when shown)
  const detailContainer = el('div');
  detailContainer.style.cssText = `
    flex: 1;
    display: none;
    flex-direction: column;
    overflow: hidden;
  `;
  pane.appendChild(detailContainer);

  let detailActive = false;

  function showDetail(cardEl: HTMLElement): void {
    detailContainer.innerHTML = '';
    detailContainer.appendChild(cardEl);
    content.style.display = 'none';
    headerEl.style.display = 'none';
    detailContainer.style.display = 'flex';
    detailActive = true;
  }

  function closeDetail(): void {
    detailContainer.style.display = 'none';
    detailContainer.innerHTML = '';
    content.style.display = 'block';
    headerEl.style.display = 'flex';
    detailActive = false;
  }

  function renderSectionHeader(text: string): HTMLElement {
    const h = el('div');
    h.textContent = text;
    h.style.cssText = `
      font-size: 11px;
      font-weight: 600;
      color: rgba(255, 255, 255, 0.5);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      padding: 12px 8px 4px;
    `;
    return h;
  }

  function renderCiCard(repo: CiRepo, pipeline: CiPipeline | null): HTMLElement {
    const card = el('div');
    card.style.cssText = `
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 10px;
      margin: 2px 0;
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.03);
    `;

    // CI status icon
    const icon = el('div');
    const ciStatus = pipeline?.status ?? 'unknown';
    icon.textContent = ciStatus === 'success' ? '\u2713' : ciStatus === 'failure' ? '\u2717'
      : ciStatus === 'running' ? '\u25CB' : '\u2022';
    icon.style.cssText = `
      color: ${ciStatus === 'success' ? '#4ade80' : ciStatus === 'failure' ? '#ef4444'
        : ciStatus === 'running' ? '#60a5fa' : 'rgba(255,255,255,0.3)'};
      font-size: 13px;
      flex-shrink: 0;
      width: 16px;
      text-align: center;
    `;
    card.appendChild(icon);

    // Repo name + last message
    const info = el('div');
    info.style.cssText = 'flex: 1; min-width: 0;';

    const nameEl = el('div');
    nameEl.textContent = repo.full_name.split('/').pop() ?? repo.full_name;
    nameEl.style.cssText = `
      font-size: 13px;
      color: rgba(255, 255, 255, 0.8);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    `;
    info.appendChild(nameEl);

    if (pipeline) {
      const msgEl = el('div');
      msgEl.textContent = `#${pipeline.number} \u00B7 ${pipeline.message}`;
      msgEl.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.35); margin-top: 1px;';
      info.appendChild(msgEl);
    }

    card.appendChild(info);

    // Status badge
    if (pipeline) {
      const badge = el('div');
      badge.textContent = ciStatus;
      badge.style.cssText = `
        font-size: 10px;
        padding: 2px 6px;
        border-radius: 4px;
        color: ${statusColor(ciStatus)};
        background: ${statusColor(ciStatus)}15;
        flex-shrink: 0;
      `;
      card.appendChild(badge);
    }

    return card;
  }

  function renderContractCard(contract: RivaContractSummary): HTMLElement {
    const card = el('div');
    card.style.cssText = `
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 10px;
      margin: 2px 0;
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.03);
    `;

    const icon = el('div');
    icon.textContent = contract.status === 'fulfilled' ? '\u2713' : contract.status === 'violated' ? '\u2717'
      : contract.status === 'active' ? '\u25CB' : '\u2022';
    icon.style.cssText = `
      color: ${statusColor(contract.status)};
      font-size: 13px;
      flex-shrink: 0;
      width: 16px;
      text-align: center;
    `;
    card.appendChild(icon);

    const info = el('div');
    info.style.cssText = 'flex: 1; min-width: 0;';

    const nameEl = el('div');
    nameEl.textContent = `Contract ${contract.id.slice(0, 16)}`;
    nameEl.style.cssText = `
      font-size: 13px;
      color: rgba(255, 255, 255, 0.8);
      font-family: monospace;
    `;
    info.appendChild(nameEl);

    const metaEl = el('div');
    metaEl.textContent = `agent: ${contract.agent_id} \u00B7 ${contract.status}`;
    metaEl.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.35); margin-top: 1px;';
    info.appendChild(metaEl);

    card.appendChild(info);

    return card;
  }

  async function refresh(epicId: string | null): Promise<void> {
    if (detailActive) return; // Don't refresh behind a detail card
    content.innerHTML = '';

    try {
      // Fetch PM data
      const issueParams: Record<string, string> = {};
      if (epicId) issueParams.epic_id = epicId;
      const [issueResult, researchResult] = await Promise.all([
        kernelRequest('riva/pm/issues/list', issueParams) as Promise<{ issues: PmIssue[] }>,
        kernelRequest('riva/pm/research/list', epicId ? { epic_id: epicId } : {}) as Promise<{ research: PmResearchEntry[] }>,
      ]);

      // Fetch CI data (only when not filtered to a specific epic)
      let ciRepos: CiRepo[] = [];
      const ciStatuses: Map<number, CiPipeline | null> = new Map();
      if (!epicId) {
        try {
          const ciResult = await kernelRequest('riva/devops/ci/repos', {}) as { repos: CiRepo[] };
          ciRepos = ciResult.repos.filter(r => r.active);
          // Fetch latest pipeline for each active repo
          await Promise.all(ciRepos.map(async (repo) => {
            try {
              const status = await kernelRequest('riva/devops/ci/status', { repo_id: repo.id }) as { latest: CiPipeline | null };
              ciStatuses.set(repo.id, status.latest);
            } catch { ciStatuses.set(repo.id, null); }
          }));
        } catch { /* DevOps not configured — skip CI section */ }
      }

      // Fetch RIVA contracts
      let contracts: RivaContractSummary[] = [];
      if (!epicId) {
        try {
          const contractResult = await kernelRequest('riva/contract/list', {}) as { contracts?: RivaContractSummary[] };
          contracts = contractResult.contracts ?? [];
        } catch { /* contracts may not exist yet */ }
      }

      const hasData = issueResult.issues.length > 0 || researchResult.research.length > 0
        || ciRepos.length > 0 || contracts.length > 0;

      if (!hasData) {
        content.appendChild(createEmptyState(
          epicId ? 'No activity for this epic' : 'No activity yet'
        ));
        return;
      }

      // CI section (top — most time-sensitive)
      if (ciRepos.length > 0) {
        content.appendChild(renderSectionHeader('CI Pipelines'));
        for (const repo of ciRepos) {
          content.appendChild(renderCiCard(repo, ciStatuses.get(repo.id) ?? null));
        }
      }

      // Contracts section
      if (contracts.length > 0) {
        content.appendChild(renderSectionHeader('Contracts'));
        for (const contract of contracts.slice(0, 5)) {
          content.appendChild(renderContractCard(contract));
        }
      }

      // Issues section
      if (issueResult.issues.length > 0) {
        content.appendChild(renderSectionHeader('Issues'));
        for (const issue of issueResult.issues) {
          content.appendChild(renderIssueCard(issue));
        }
      }

      // Research section
      if (researchResult.research.length > 0) {
        content.appendChild(renderSectionHeader('Decisions & Research'));
        for (const entry of researchResult.research.slice(0, 10)) {
          content.appendChild(renderResearchCard(entry));
        }
      }
    } catch {
      content.appendChild(createEmptyState('Could not load activity'));
    }
  }

  function renderIssueCard(issue: PmIssue): HTMLElement {
    const card = el('div');
    card.style.cssText = `
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 10px;
      margin: 2px 0;
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.03);
      transition: background 0.15s;
      cursor: pointer;
    `;
    card.addEventListener('mouseenter', () => { card.style.background = 'rgba(255, 255, 255, 0.06)'; });
    card.addEventListener('mouseleave', () => { card.style.background = 'rgba(255, 255, 255, 0.03)'; });
    card.addEventListener('click', () => showIssueDetail(issue.id));

    // Status icon
    const icon = el('div');
    icon.textContent = statusIcon(issue.status);
    icon.style.cssText = `
      color: ${statusColor(issue.status)};
      font-size: 12px;
      flex-shrink: 0;
      width: 16px;
      text-align: center;
    `;
    card.appendChild(icon);

    // Name
    const nameEl = el('div');
    nameEl.textContent = issue.name;
    nameEl.style.cssText = `
      flex: 1;
      font-size: 13px;
      color: rgba(255, 255, 255, 0.8);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    `;
    card.appendChild(nameEl);

    // Type tag
    const tag = el('div');
    tag.textContent = issue.type;
    tag.style.cssText = `
      font-size: 10px;
      padding: 1px 5px;
      border-radius: 3px;
      color: rgba(255, 255, 255, 0.5);
      border: 1px solid rgba(255, 255, 255, 0.1);
      flex-shrink: 0;
    `;
    card.appendChild(tag);

    // Priority dot
    const pDot = el('div');
    pDot.style.cssText = `
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: ${priorityColor(issue.priority)};
      flex-shrink: 0;
    `;
    card.appendChild(pDot);

    return card;
  }

  function renderResearchCard(entry: PmResearchEntry): HTMLElement {
    const card = el('div');
    card.style.cssText = `
      padding: 8px 10px;
      margin: 2px 0;
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.03);
    `;

    const nameEl = el('div');
    nameEl.textContent = entry.name;
    nameEl.style.cssText = `
      font-size: 13px;
      color: rgba(255, 255, 255, 0.75);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    `;
    card.appendChild(nameEl);

    const meta = el('div');
    const parts = [entry.type, entry.date].filter(Boolean);
    meta.textContent = parts.join(' \u00B7 ');
    meta.style.cssText = `
      font-size: 11px;
      color: rgba(255, 255, 255, 0.35);
      margin-top: 2px;
    `;
    card.appendChild(meta);

    return card;
  }

  async function showEpicDetail(epicId: string): Promise<void> {
    try {
      const epic = await kernelRequest('riva/pm/epics/get', { epic_id: epicId }) as PmEpic;
      await fetchActs(); // Ensure acts cache is fresh
      const card = buildEpicDetailCard(
        epic,
        closeDetail,
        () => { closeDetail(); refresh(selectedEpicId); },
        (issueId) => showIssueDetail(issueId),
      );
      showDetail(card);
    } catch { /* best effort */ }
  }

  async function showIssueDetail(issueId: string): Promise<void> {
    try {
      const issue = await kernelRequest('riva/pm/issues/get', { issue_id: issueId }) as PmIssue;
      const card = buildIssueDetailCard(
        issue,
        closeDetail,
        () => { closeDetail(); refresh(selectedEpicId); },
      );
      showDetail(card);
    } catch { /* best effort */ }
  }

  return { pane, refresh, showEpicDetail, showIssueDetail, closeDetail };
}

// ── Chat Pane (Right) ───────────────────────────────────────────────

function createChatPane(): {
  pane: HTMLElement;
  addMessage: (msg: ChatMessage) => void;
} {
  const pane = el('div');
  pane.className = 'riva-chat';
  pane.style.cssText = `
    width: 380px;
    min-width: 300px;
    display: flex;
    flex-direction: column;
    min-width: 0;
    overflow: hidden;
  `;

  pane.appendChild(createPaneHeader('Chat'));

  // Message area
  const messageArea = el('div');
  messageArea.style.cssText = `
    flex: 1;
    overflow-y: auto;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  `;

  // Welcome message
  const welcome = el('div');
  welcome.style.cssText = `
    padding: 12px 16px;
    border-radius: 12px;
    background: rgba(94, 122, 148, 0.15);
    color: rgba(255, 255, 255, 0.8);
    font-size: 13px;
    line-height: 1.5;
  `;
  welcome.textContent = 'RIVA is ready. Ask about your projects, create plans, or manage the backlog.';
  messageArea.appendChild(welcome);
  pane.appendChild(messageArea);

  // Input bar
  const inputBar = el('div');
  inputBar.style.cssText = `
    display: flex;
    gap: 8px;
    padding: 10px 12px;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
    flex-shrink: 0;
    align-items: flex-end;
  `;

  const chatInput = el('textarea');
  chatInput.placeholder = 'Ask RIVA...';
  chatInput.rows = 1;
  chatInput.style.cssText = `
    flex: 1;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 10px;
    padding: 8px 12px;
    background: rgba(0, 0, 0, 0.3);
    color: rgba(255, 255, 255, 0.9);
    outline: none;
    font-family: inherit;
    font-size: 13px;
    resize: none;
    max-height: 120px;
    line-height: 1.4;
  `;

  chatInput.addEventListener('focus', () => {
    chatInput.style.borderColor = 'rgba(59, 130, 246, 0.5)';
  });
  chatInput.addEventListener('blur', () => {
    chatInput.style.borderColor = 'rgba(255, 255, 255, 0.12)';
  });

  // Auto-resize textarea
  chatInput.addEventListener('input', () => {
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
  });

  const sendBtn = el('button');
  sendBtn.textContent = '\u2191'; // ↑
  sendBtn.style.cssText = `
    width: 34px;
    height: 34px;
    border: 1px solid rgba(59, 130, 246, 0.4);
    border-radius: 10px;
    background: rgba(59, 130, 246, 0.2);
    color: #60a5fa;
    font-size: 16px;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.15s;
    flex-shrink: 0;
  `;
  sendBtn.addEventListener('mouseenter', () => {
    sendBtn.style.background = 'rgba(59, 130, 246, 0.35)';
  });
  sendBtn.addEventListener('mouseleave', () => {
    sendBtn.style.background = 'rgba(59, 130, 246, 0.2)';
  });

  // Send logic
  // ── Chat routing: match user message to appropriate data queries ──

  async function routeQuery(text: string): Promise<string> {
    const lower = text.toLowerCase();

    // Dashboard / status / overview
    if (lower.match(/\b(dashboard|status|overview|summary|how.?s it going)\b/)) {
      return await queryDashboard();
    }

    // Backlog queries
    if (lower.match(/\b(backlog|what.?s (left|pending|todo|next))\b/)) {
      return await queryBacklog();
    }

    // CI / build / pipeline
    if (lower.match(/\b(ci|build|pipeline|test|passing|failing|green|red)\b/)) {
      return await queryCi();
    }

    // Specific project query
    const projectMatch = lower.match(/\b(cairn|reos|riva|sieve|lithium|nol|helm|infra)/);
    if (projectMatch) {
      return await queryProject(projectMatch[1]);
    }

    // Epic / issue counts
    if (lower.match(/\b(epic|issue|bug|feature|sprint|cycle)\b/)) {
      return await queryDashboard();
    }

    // Research / decisions
    if (lower.match(/\b(decision|research|spike|architecture|why did)\b/)) {
      return await queryResearch();
    }

    // Roadmap
    if (lower.match(/\b(roadmap|quarter|q[1-4]|plan ahead|strategic)\b/)) {
      return await queryRoadmap();
    }

    // Default: show dashboard
    return await queryDashboard();
  }

  async function queryDashboard(): Promise<string> {
    const dash = await kernelRequest('riva/pm/dashboard', {}) as PmDashboard;
    const total = Object.values(dash.issues).reduce((a, b) => a + b, 0);
    const ip = dash.issues['In Progress'] || 0;
    const done = dash.issues['Done'] || 0;
    const backlog = dash.issues['Backlog'] || 0;
    const epicCount = Object.values(dash.epics).reduce((a, b) => a + b, 0);

    let r = `${epicCount} epics, ${total} issues (${backlog} backlog, ${ip} active, ${done} done)`;
    if (dash.active_cycle) {
      r += `\n\nActive cycle: ${dash.active_cycle.name}`;
      if (dash.active_cycle.goal) r += `\nGoal: ${dash.active_cycle.goal}`;
    }
    if (dash.recent_research.length > 0) {
      r += `\n\nRecent decisions:`;
      for (const res of dash.recent_research.slice(0, 3)) {
        r += `\n\u2022 ${res.name}`;
      }
    }
    return r;
  }

  async function queryBacklog(): Promise<string> {
    const result = await kernelRequest('riva/pm/issues/list', { status: 'Backlog' }) as { issues: PmIssue[] };
    if (result.issues.length === 0) return 'Backlog is empty. Nothing pending.';
    let r = `${result.issues.length} backlog items:\n`;
    for (const issue of result.issues.slice(0, 10)) {
      r += `\n[${issue.priority}] ${issue.name} (${issue.type})`;
    }
    if (result.issues.length > 10) r += `\n... and ${result.issues.length - 10} more`;
    return r;
  }

  async function queryCi(): Promise<string> {
    try {
      const repoResult = await kernelRequest('riva/devops/ci/repos', {}) as { repos: CiRepo[] };
      const activeRepos = repoResult.repos.filter(r => r.active);
      if (activeRepos.length === 0) return 'No active CI repos found.';

      let r = 'CI Status:\n';
      for (const repo of activeRepos) {
        try {
          const status = await kernelRequest('riva/devops/ci/status', { repo_id: repo.id }) as { latest: CiPipeline | null };
          const p = status.latest;
          if (p) {
            const icon = p.status === 'success' ? '\u2713' : p.status === 'failure' ? '\u2717' : '\u25CB';
            r += `\n${icon} ${repo.full_name} \u2014 #${p.number} ${p.status} (${p.message})`;
          } else {
            r += `\n\u2022 ${repo.full_name} \u2014 no builds`;
          }
        } catch {
          r += `\n\u2022 ${repo.full_name} \u2014 status unavailable`;
        }
      }
      return r;
    } catch {
      return 'CI not configured. Set WOODPECKER_URL and WOODPECKER_TOKEN to connect.';
    }
  }

  async function queryProject(project: string): Promise<string> {
    const projUpper = project.charAt(0).toUpperCase() + project.slice(1);
    const epics = await kernelRequest('riva/pm/epics/list', { project: projUpper }) as { epics: PmEpic[] };

    if (epics.epics.length === 0) {
      // Try case-insensitive — some projects use all-caps
      const epicsUpper = await kernelRequest('riva/pm/epics/list', { project: project.toUpperCase() }) as { epics: PmEpic[] };
      if (epicsUpper.epics.length === 0) return `No epics found for project "${project}".`;
      return formatProjectEpics(project.toUpperCase(), epicsUpper.epics);
    }
    return formatProjectEpics(projUpper, epics.epics);
  }

  function formatProjectEpics(project: string, epics: PmEpic[]): string {
    let r = `${project}: ${epics.length} epic${epics.length === 1 ? '' : 's'}\n`;
    for (const e of epics) {
      r += `\n[${e.status}] ${e.name} (${e.priority})`;
    }
    return r;
  }

  async function queryResearch(): Promise<string> {
    const result = await kernelRequest('riva/pm/research/list', {}) as { research: PmResearchEntry[] };
    if (result.research.length === 0) return 'No research entries yet.';
    let r = `${result.research.length} research entries:\n`;
    for (const entry of result.research.slice(0, 8)) {
      const type = entry.type ? ` (${entry.type})` : '';
      r += `\n\u2022 ${entry.name}${type}`;
      if (entry.date) r += ` \u2014 ${entry.date}`;
    }
    return r;
  }

  async function queryRoadmap(): Promise<string> {
    const result = await kernelRequest('riva/pm/roadmap/list', {}) as { roadmap: Array<{ name: string; quarter: string | null; project: string | null; status: string }> };
    if (result.roadmap.length === 0) return 'No roadmap items yet.';
    let r = 'Roadmap:\n';
    for (const item of result.roadmap) {
      r += `\n[${item.quarter ?? '?'}] ${item.name} (${item.project ?? 'General'}) \u2014 ${item.status}`;
    }
    return r;
  }

  // ── Send message ──

  async function sendMessage(): Promise<void> {
    const text = chatInput.value.trim();
    if (!text) return;

    chatInput.value = '';
    chatInput.style.height = 'auto';

    const userMsg: ChatMessage = { role: 'user', content: text, timestamp: new Date() };
    chatMessages.push(userMsg);
    addMessage(userMsg);

    // Show thinking indicator
    const thinkingEl = el('div');
    thinkingEl.style.cssText = `
      padding: 10px 16px;
      border-radius: 12px;
      background: rgba(94, 122, 148, 0.1);
      color: rgba(255, 255, 255, 0.4);
      font-size: 13px;
      font-style: italic;
    `;
    thinkingEl.textContent = 'Thinking...';
    messageArea.appendChild(thinkingEl);
    messageArea.scrollTop = messageArea.scrollHeight;

    try {
      const response = await routeQuery(text);
      messageArea.removeChild(thinkingEl);
      const rivaMsg: ChatMessage = { role: 'riva', content: response, timestamp: new Date() };
      chatMessages.push(rivaMsg);
      addMessage(rivaMsg);
    } catch {
      messageArea.removeChild(thinkingEl);
      const errMsg: ChatMessage = {
        role: 'riva',
        content: 'Could not reach RIVA service. Is it running?',
        timestamp: new Date(),
      };
      chatMessages.push(errMsg);
      addMessage(errMsg);
    }
  }

  sendBtn.addEventListener('click', sendMessage);
  chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  inputBar.appendChild(chatInput);
  inputBar.appendChild(sendBtn);
  pane.appendChild(inputBar);

  function addMessage(msg: ChatMessage): void {
    const bubble = el('div');
    const isUser = msg.role === 'user';

    bubble.style.cssText = `
      padding: 10px 14px;
      border-radius: 12px;
      font-size: 13px;
      line-height: 1.5;
      max-width: 90%;
      white-space: pre-wrap;
      word-break: break-word;
      ${isUser
        ? 'background: rgba(59, 130, 246, 0.85); color: #fff; align-self: flex-end;'
        : 'background: rgba(94, 122, 148, 0.15); color: rgba(255, 255, 255, 0.85); align-self: flex-start;'
      }
    `;
    bubble.textContent = msg.content;
    messageArea.appendChild(bubble);
    messageArea.scrollTop = messageArea.scrollHeight;
  }

  return { pane, addMessage };
}

// ── Main ───────────────────────────────────────────────────────────────

export function createRivaView(): {
  container: HTMLElement;
  startPolling: () => void;
  stopPolling: () => void;
  destroy: () => void;
} {
  const container = el('div');
  container.className = 'riva-view';
  container.style.cssText = `
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  `;

  // ── Top bar ──
  const topBar = el('div');
  topBar.style.cssText = `
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 16px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    flex-shrink: 0;
  `;

  const titleRow = el('div');
  titleRow.style.cssText = 'display: flex; align-items: center; gap: 10px;';

  const title = el('div');
  title.textContent = 'RIVA';
  title.style.cssText = `
    font-size: 16px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.9);
    letter-spacing: 0.04em;
  `;
  titleRow.appendChild(title);

  const subtitle = el('div');
  subtitle.textContent = 'Project Manager';
  subtitle.style.cssText = 'font-size: 12px; color: rgba(255, 255, 255, 0.4);';
  titleRow.appendChild(subtitle);
  topBar.appendChild(titleRow);

  const statusBadge = createStatusBadge();
  topBar.appendChild(statusBadge);
  container.appendChild(topBar);

  // ── Three-pane split ──
  const splitContainer = el('div');
  splitContainer.style.cssText = `
    flex: 1;
    display: flex;
    overflow: hidden;
  `;

  // Create panes with cross-wiring
  const activityPane = createActivityPane();
  const chatPane = createChatPane();
  const projectsPane = createProjectsPane(
    (epicId) => {
      activityPane.closeDetail();
      activityPane.refresh(epicId);
    },
    (epicId) => {
      activityPane.showEpicDetail(epicId);
    },
  );

  splitContainer.appendChild(projectsPane.pane);
  splitContainer.appendChild(activityPane.pane);
  splitContainer.appendChild(chatPane.pane);
  container.appendChild(splitContainer);

  // ── Polling ──
  async function checkStatus(): Promise<void> {
    try {
      const result = await kernelRequest('riva/status', {}) as RivaStatus;
      if (result && result.status === 'running') {
        setStatusBadge(statusBadge, 'connected');
      } else {
        setStatusBadge(statusBadge, 'offline');
      }
    } catch {
      setStatusBadge(statusBadge, 'offline');
    }
  }

  async function refreshAll(): Promise<void> {
    await Promise.all([
      projectsPane.refresh(),
      activityPane.refresh(selectedEpicId),
    ]);
  }

  function startPolling(): void {
    fetchActs(); // Preload Acts for the Act picker
    checkStatus();
    refreshAll();
    if (statusPollTimer === null) {
      statusPollTimer = window.setInterval(checkStatus, 10000);
    }
    if (dataPollTimer === null) {
      dataPollTimer = window.setInterval(refreshAll, 30000);
    }
  }

  function stopPolling(): void {
    if (statusPollTimer !== null) {
      clearInterval(statusPollTimer);
      statusPollTimer = null;
    }
    if (dataPollTimer !== null) {
      clearInterval(dataPollTimer);
      dataPollTimer = null;
    }
  }

  function destroy(): void {
    stopPolling();
  }

  return { container, startPolling, stopPolling, destroy };
}
