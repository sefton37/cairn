import { invoke } from '@tauri-apps/api/core';
import { WebviewWindow } from '@tauri-apps/api/webviewWindow';
import { z } from 'zod';

import './style.css';

const JsonRpcResponseSchema = z.object({
  jsonrpc: z.literal('2.0'),
  id: z.union([z.string(), z.number(), z.null()]).optional(),
  result: z.unknown().optional(),
  error: z
    .object({
      code: z.number(),
      message: z.string(),
      data: z.unknown().optional()
    })
    .optional()
});

type ChatRespondResult = {
  answer: string;
};

type PlayMeReadResult = {
  markdown: string;
};

type PlayActsListResult = {
  active_act_id: string | null;
  acts: Array<{ act_id: string; title: string; active: boolean; notes: string }>;
};

type PlayScenesListResult = {
  scenes: Array<{
    scene_id: string;
    title: string;
    intent: string;
    status: string;
    time_horizon: string;
    notes: string;
  }>;
};

type PlayBeatsListResult = {
  beats: Array<{ beat_id: string; title: string; status: string; notes: string; link: string | null }>;
};

type PlayActsCreateResult = {
  created_act_id: string;
  acts: Array<{ act_id: string; title: string; active: boolean; notes: string }>;
};

type PlayScenesMutationResult = {
  scenes: PlayScenesListResult['scenes'];
};

type PlayBeatsMutationResult = {
  beats: PlayBeatsListResult['beats'];
};

type PlayKbListResult = {
  files: string[];
};

type PlayKbReadResult = {
  path: string;
  text: string;
};

type PlayKbWritePreviewResult = {
  path: string;
  exists: boolean;
  sha256_current: string;
  expected_sha256_current: string;
  sha256_new: string;
  diff: string;
};

type PlayKbWriteApplyResult = {
  ok: boolean;
  sha256_current: string;
};

// System monitoring types
type SystemSummary = {
  hostname: string;
  os_name: string;
  os_version: string;
  kernel: string;
  uptime: string;
  uptime_seconds: number;
  process_count: number;
  service_count: number;
  running_services: number;
  container_count: number;
  running_containers: number;
  cpu_percent: number;
  memory_percent: number;
  disk_percent: number;
  load_avg: string;
};

type SystemResources = {
  cpu_percent: number;
  cpu_count: number;
  memory_total_mb: number;
  memory_used_mb: number;
  memory_percent: number;
  swap_total_mb: number;
  swap_used_mb: number;
  swap_percent: number;
  disk_total_gb: number;
  disk_used_gb: number;
  disk_percent: number;
  load_avg_1: number;
  load_avg_5: number;
  load_avg_15: number;
};

type SystemOverviewResult = {
  summary: SystemSummary;
  resources: SystemResources;
};

type SystemdService = {
  unit: string;
  load_state: string;
  active_state: string;
  sub_state: string;
  description: string;
};

type SystemServicesResult = {
  services: SystemdService[];
};

type ProcessInfo = {
  pid: number;
  user: string;
  cpu_percent: number;
  mem_percent: number;
  vsz_kb: number;
  rss_kb: number;
  tty: string;
  stat: string;
  started: string;
  time: string;
  command: string;
  friendly_name: string;
};

type SystemProcessesResult = {
  processes: ProcessInfo[];
};

type ContainerInfo = {
  id: string;
  name: string;
  image: string;
  status: string;
  ports: string;
  created: string;
  runtime: string;
};

type SystemContainersResult = {
  containers: ContainerInfo[];
};

// Bash execution types
type BashProposal = {
  proposal_id: string;
  command: string;
  description: string;
  risk_level: 'low' | 'medium' | 'high' | 'critical';
  warnings: string[];
  created_at: string;
  approved: boolean;
  executed: boolean;
};

type BashExecuteResult = {
  proposal_id: string;
  command: string;
  exit_code: number;
  stdout: string;
  stderr: string;
  duration_ms: number;
  success: boolean;
};

type BashSuggestResult = {
  found: boolean;
  template_name?: string;
  command_template?: string;
  description?: string;
  requires_params?: string[];
  optional_params?: Record<string, string>;
  message?: string;
};

class KernelError extends Error {
  code: number;

  constructor(message: string, code: number) {
    super(message);
    this.name = 'KernelError';
    this.code = code;
  }
}


async function kernelRequest(method: string, params: unknown): Promise<unknown> {
  const raw = await invoke('kernel_request', { method, params });
  const parsed = JsonRpcResponseSchema.parse(raw);
  if (parsed.error) {
    throw new KernelError(parsed.error.message, parsed.error.code);
  }
  return parsed.result;
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Record<string, string> = {}) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}

function buildUi() {
  const query = new URLSearchParams(window.location.search);
  if (query.get('view') === 'me') {
    void buildMeWindow();
    return;
  }
  if (query.get('view') === 'command-dashboard') {
    void buildCommandDashboardWindow();
    return;
  }

  const root = document.getElementById('app');
  if (!root) return;

  root.innerHTML = '';

  const shell = el('div');
  shell.className = 'shell';
  shell.style.display = 'flex';
  shell.style.height = '100vh';
  shell.style.fontFamily = 'system-ui, sans-serif';

  const nav = el('div');
  nav.className = 'nav';
  nav.style.width = '240px';
  nav.style.borderRight = '1px solid #ddd';
  nav.style.padding = '12px';
  nav.style.overflow = 'auto';

  const navTitle = el('div');
  navTitle.textContent = 'ReOS';
  navTitle.style.fontWeight = '600';
  navTitle.style.marginBottom = '10px';

  const meHeader = el('div');
  meHeader.textContent = 'Me (The Play)';
  meHeader.style.marginTop = '12px';
  meHeader.style.fontWeight = '600';

  const meBtn = el('button');
  meBtn.textContent = 'Me';

  const actsHeader = el('div');
  actsHeader.textContent = 'Acts';
  actsHeader.style.marginTop = '12px';
  actsHeader.style.fontWeight = '600';

  const actsList = el('div');
  actsList.style.display = 'flex';
  actsList.style.flexDirection = 'column';
  actsList.style.gap = '6px';

  const systemHeader = el('div');
  systemHeader.textContent = 'System';
  systemHeader.style.marginTop = '12px';
  systemHeader.style.fontWeight = '600';

  const cmdDashBtn = el('button');
  cmdDashBtn.textContent = 'Command Dashboard';

  nav.appendChild(navTitle);
  nav.appendChild(systemHeader);
  nav.appendChild(cmdDashBtn);
  nav.appendChild(meHeader);
  nav.appendChild(meBtn);
  nav.appendChild(actsHeader);
  nav.appendChild(actsList);

  const center = el('div');
  center.className = 'center';
  center.style.flex = '1';
  center.style.display = 'flex';
  center.style.flexDirection = 'column';

  const chatLog = el('div');
  chatLog.className = 'chat-log';
  chatLog.style.flex = '1';
  chatLog.style.padding = '12px';
  chatLog.style.overflow = 'auto';

  const inputRow = el('div');
  inputRow.className = 'input-row';
  inputRow.style.display = 'flex';
  inputRow.style.gap = '8px';
  inputRow.style.padding = '12px';
  inputRow.style.borderTop = '1px solid #ddd';

  const input = el('input');
  input.className = 'chat-input';
  input.type = 'text';
  input.placeholder = 'Type a message…';
  input.style.flex = '1';

  const send = el('button');
  send.className = 'send-btn';
  send.textContent = 'Send';

  inputRow.appendChild(input);
  inputRow.appendChild(send);

  const inspection = el('div');
  inspection.className = 'inspection';
  inspection.style.width = '420px';
  inspection.style.borderLeft = '1px solid #ddd';
  inspection.style.margin = '0';
  inspection.style.padding = '12px';
  inspection.style.overflow = 'auto';

  const inspectionTitle = el('div');
  inspectionTitle.style.fontWeight = '600';
  inspectionTitle.style.marginBottom = '8px';
  inspectionTitle.textContent = 'Inspection';

  const inspectionBody = el('div');

  inspection.appendChild(inspectionTitle);
  inspection.appendChild(inspectionBody);

  center.appendChild(chatLog);
  center.appendChild(inputRow);

  shell.appendChild(nav);
  shell.appendChild(center);
  shell.appendChild(inspection);

  root.appendChild(shell);

  function append(role: 'user' | 'reos', text: string) {
    const row = el('div');
    row.className = `chat-row ${role}`;

    const bubble = el('div');
    bubble.className = `chat-bubble ${role}`;
    bubble.textContent = text;

    row.appendChild(bubble);
    chatLog.appendChild(row);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  function appendThinking(): { row: HTMLDivElement; bubble: HTMLDivElement } {
    const row = el('div') as HTMLDivElement;
    row.className = 'chat-row reos';

    const bubble = el('div') as HTMLDivElement;
    bubble.className = 'chat-bubble reos thinking';

    const dots = el('span') as HTMLSpanElement;
    dots.className = 'typing-dots';
    dots.innerHTML = '<span></span><span></span><span></span>';
    bubble.appendChild(dots);

    row.appendChild(bubble);
    chatLog.appendChild(row);
    chatLog.scrollTop = chatLog.scrollHeight;
    return { row, bubble };
  }

  function appendCommandProposal(proposal: BashProposal): void {
    const row = el('div');
    row.className = 'chat-row reos';

    const bubble = el('div');
    bubble.className = 'chat-bubble reos';
    bubble.style.background = 'linear-gradient(135deg, #1e293b 0%, #334155 100%)';
    bubble.style.color = '#f1f5f9';
    bubble.style.padding = '16px';
    bubble.style.borderRadius = '12px';
    bubble.style.maxWidth = '500px';

    // Header with risk badge
    const header = el('div');
    header.style.display = 'flex';
    header.style.justifyContent = 'space-between';
    header.style.alignItems = 'center';
    header.style.marginBottom = '12px';

    const title = el('span');
    title.textContent = 'Command Proposal';
    title.style.fontWeight = '600';
    title.style.fontSize = '14px';

    const riskBadge = el('span');
    riskBadge.textContent = proposal.risk_level.toUpperCase();
    riskBadge.style.padding = '2px 8px';
    riskBadge.style.borderRadius = '9999px';
    riskBadge.style.fontSize = '10px';
    riskBadge.style.fontWeight = '600';
    const riskColors: Record<string, { bg: string; text: string }> = {
      low: { bg: '#dcfce7', text: '#166534' },
      medium: { bg: '#fef3c7', text: '#92400e' },
      high: { bg: '#fee2e2', text: '#991b1b' },
      critical: { bg: '#7f1d1d', text: '#fecaca' }
    };
    const colors = riskColors[proposal.risk_level] || riskColors.medium;
    riskBadge.style.background = colors.bg;
    riskBadge.style.color = colors.text;

    header.appendChild(title);
    header.appendChild(riskBadge);
    bubble.appendChild(header);

    // Description
    const desc = el('div');
    desc.textContent = proposal.description;
    desc.style.fontSize = '13px';
    desc.style.marginBottom = '12px';
    desc.style.color = '#cbd5e1';
    bubble.appendChild(desc);

    // Command box
    const cmdBox = el('div');
    cmdBox.style.background = '#0f172a';
    cmdBox.style.padding = '12px';
    cmdBox.style.borderRadius = '8px';
    cmdBox.style.marginBottom = '12px';
    cmdBox.style.fontFamily = 'ui-monospace, monospace';
    cmdBox.style.fontSize = '12px';
    cmdBox.style.whiteSpace = 'pre-wrap';
    cmdBox.style.wordBreak = 'break-all';
    cmdBox.textContent = proposal.command;
    bubble.appendChild(cmdBox);

    // Warnings
    if (proposal.warnings.length > 0) {
      const warningsBox = el('div');
      warningsBox.style.background = '#451a03';
      warningsBox.style.padding = '10px';
      warningsBox.style.borderRadius = '8px';
      warningsBox.style.marginBottom = '12px';
      warningsBox.style.fontSize = '12px';

      const warnTitle = el('div');
      warnTitle.textContent = 'Warnings:';
      warnTitle.style.fontWeight = '600';
      warnTitle.style.color = '#fbbf24';
      warnTitle.style.marginBottom = '4px';
      warningsBox.appendChild(warnTitle);

      for (const w of proposal.warnings) {
        const warnItem = el('div');
        warnItem.textContent = `• ${w}`;
        warnItem.style.color = '#fed7aa';
        warningsBox.appendChild(warnItem);
      }
      bubble.appendChild(warningsBox);
    }

    // Action buttons
    const actions = el('div');
    actions.style.display = 'flex';
    actions.style.gap = '8px';

    const approveBtn = el('button');
    approveBtn.textContent = 'Approve & Run';
    approveBtn.style.flex = '1';
    approveBtn.style.padding = '10px 16px';
    approveBtn.style.borderRadius = '8px';
    approveBtn.style.border = 'none';
    approveBtn.style.background = '#22c55e';
    approveBtn.style.color = 'white';
    approveBtn.style.fontWeight = '600';
    approveBtn.style.cursor = 'pointer';
    approveBtn.style.fontSize = '13px';

    const rejectBtn = el('button');
    rejectBtn.textContent = 'Reject';
    rejectBtn.style.padding = '10px 16px';
    rejectBtn.style.borderRadius = '8px';
    rejectBtn.style.border = '1px solid #475569';
    rejectBtn.style.background = 'transparent';
    rejectBtn.style.color = '#94a3b8';
    rejectBtn.style.cursor = 'pointer';
    rejectBtn.style.fontSize = '13px';

    actions.appendChild(approveBtn);
    actions.appendChild(rejectBtn);
    bubble.appendChild(actions);

    // Result container (hidden initially)
    const resultContainer = el('div');
    resultContainer.style.display = 'none';
    resultContainer.style.marginTop = '12px';
    bubble.appendChild(resultContainer);

    // Handle approve
    approveBtn.addEventListener('click', () => {
      approveBtn.disabled = true;
      rejectBtn.disabled = true;
      approveBtn.textContent = 'Running...';
      approveBtn.style.background = '#64748b';

      void (async () => {
        try {
          // Approve the proposal
          await kernelRequest('bash/approve', { proposal_id: proposal.proposal_id });

          // Execute it
          const result = (await kernelRequest('bash/execute', {
            proposal_id: proposal.proposal_id,
            timeout: 60
          })) as BashExecuteResult;

          // Show result
          actions.style.display = 'none';
          resultContainer.style.display = 'block';

          const resultHeader = el('div');
          resultHeader.style.display = 'flex';
          resultHeader.style.justifyContent = 'space-between';
          resultHeader.style.alignItems = 'center';
          resultHeader.style.marginBottom = '8px';

          const resultTitle = el('span');
          resultTitle.textContent = result.success ? 'Success' : 'Failed';
          resultTitle.style.fontWeight = '600';
          resultTitle.style.color = result.success ? '#22c55e' : '#ef4444';

          const exitCode = el('span');
          exitCode.textContent = `Exit code: ${result.exit_code}`;
          exitCode.style.fontSize = '11px';
          exitCode.style.color = '#94a3b8';

          resultHeader.appendChild(resultTitle);
          resultHeader.appendChild(exitCode);
          resultContainer.appendChild(resultHeader);

          if (result.stdout) {
            const stdoutLabel = el('div');
            stdoutLabel.textContent = 'Output:';
            stdoutLabel.style.fontSize = '11px';
            stdoutLabel.style.color = '#94a3b8';
            stdoutLabel.style.marginBottom = '4px';
            resultContainer.appendChild(stdoutLabel);

            const stdout = el('pre');
            stdout.textContent = result.stdout;
            stdout.style.background = '#0f172a';
            stdout.style.padding = '10px';
            stdout.style.borderRadius = '6px';
            stdout.style.fontSize = '11px';
            stdout.style.margin = '0 0 8px 0';
            stdout.style.whiteSpace = 'pre-wrap';
            stdout.style.maxHeight = '200px';
            stdout.style.overflow = 'auto';
            resultContainer.appendChild(stdout);
          }

          if (result.stderr) {
            const stderrLabel = el('div');
            stderrLabel.textContent = 'Errors:';
            stderrLabel.style.fontSize = '11px';
            stderrLabel.style.color = '#f87171';
            stderrLabel.style.marginBottom = '4px';
            resultContainer.appendChild(stderrLabel);

            const stderr = el('pre');
            stderr.textContent = result.stderr;
            stderr.style.background = '#450a0a';
            stderr.style.padding = '10px';
            stderr.style.borderRadius = '6px';
            stderr.style.fontSize = '11px';
            stderr.style.margin = '0';
            stderr.style.whiteSpace = 'pre-wrap';
            stderr.style.color = '#fca5a5';
            resultContainer.appendChild(stderr);
          }

          const duration = el('div');
          duration.textContent = `Completed in ${result.duration_ms}ms`;
          duration.style.fontSize = '10px';
          duration.style.color = '#64748b';
          duration.style.marginTop = '8px';
          resultContainer.appendChild(duration);

        } catch (e) {
          actions.style.display = 'none';
          resultContainer.style.display = 'block';
          resultContainer.innerHTML = '';

          const errorBox = el('div');
          errorBox.style.background = '#450a0a';
          errorBox.style.padding = '12px';
          errorBox.style.borderRadius = '8px';
          errorBox.style.color = '#fca5a5';
          errorBox.textContent = `Error: ${String(e)}`;
          resultContainer.appendChild(errorBox);
        }
      })();
    });

    // Handle reject
    rejectBtn.addEventListener('click', () => {
      actions.style.display = 'none';
      resultContainer.style.display = 'block';

      const rejected = el('div');
      rejected.textContent = 'Command rejected';
      rejected.style.color = '#94a3b8';
      rejected.style.fontStyle = 'italic';
      resultContainer.appendChild(rejected);
    });

    row.appendChild(bubble);
    chatLog.appendChild(row);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  function appendCommandResult(result: BashExecuteResult): void {
    const row = el('div');
    row.className = 'chat-row reos';

    const bubble = el('div');
    bubble.className = 'chat-bubble reos';
    bubble.style.background = result.success ? '#14532d' : '#450a0a';
    bubble.style.color = '#f1f5f9';
    bubble.style.padding = '12px';
    bubble.style.borderRadius = '12px';
    bubble.style.maxWidth = '500px';

    const header = el('div');
    header.style.marginBottom = '8px';
    header.style.fontWeight = '600';
    header.textContent = result.success ? 'Command Succeeded' : 'Command Failed';
    bubble.appendChild(header);

    if (result.stdout) {
      const stdout = el('pre');
      stdout.textContent = result.stdout;
      stdout.style.background = 'rgba(0,0,0,0.3)';
      stdout.style.padding = '8px';
      stdout.style.borderRadius = '6px';
      stdout.style.fontSize = '11px';
      stdout.style.margin = '0';
      stdout.style.whiteSpace = 'pre-wrap';
      stdout.style.maxHeight = '200px';
      stdout.style.overflow = 'auto';
      bubble.appendChild(stdout);
    }

    row.appendChild(bubble);
    chatLog.appendChild(row);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  let activeActId: string | null = null;
  let actsCache: PlayActsListResult['acts'] = [];
  let selectedSceneId: string | null = null;
  let selectedBeatId: string | null = null;

  let scenesCache: PlayScenesListResult['scenes'] = [];
  let beatsCache: PlayBeatsListResult['beats'] = [];

  let kbSelectedPath = 'kb.md';
  let kbTextDraft = '';
  let kbPreview: PlayKbWritePreviewResult | null = null;

  function showJsonInInspector(title: string, obj: unknown) {
    inspectionTitle.textContent = title;
    inspectionBody.innerHTML = '';
    const pre = el('pre');
    pre.style.margin = '0';
    pre.textContent = JSON.stringify(obj ?? null, null, 2);
    inspectionBody.appendChild(pre);
  }

  async function openMeWindow() {
    try {
      const existing = await WebviewWindow.getByLabel('me');
      if (existing) {
        await existing.setFocus();
        return;
      }
    } catch {
      // Best effort: if getByLabel fails, fall through and create a new window.
    }

    const w = new WebviewWindow('me', {
      title: 'Me — ReOS',
      url: '/?view=me',
      width: 900,
      height: 700
    });
    void w;
  }

  async function openCommandDashboardWindow() {
    try {
      const existing = await WebviewWindow.getByLabel('command-dashboard');
      if (existing) {
        await existing.setFocus();
        return;
      }
    } catch {
      // Best effort: if getByLabel fails, fall through and create a new window.
    }

    const w = new WebviewWindow('command-dashboard', {
      title: 'Command Dashboard — ReOS',
      url: '/?view=command-dashboard',
      width: 1200,
      height: 800
    });
    void w;
  }

  cmdDashBtn.addEventListener('click', () => void openCommandDashboardWindow());
  meBtn.addEventListener('click', () => void openMeWindow());

  function rowHeader(title: string) {
    const h = el('div');
    h.textContent = title;
    h.style.fontWeight = '600';
    h.style.margin = '10px 0 6px';
    return h;
  }

  function label(text: string) {
    const l = el('div');
    l.textContent = text;
    l.style.fontSize = '12px';
    l.style.opacity = '0.8';
    l.style.marginBottom = '4px';
    return l;
  }

  function textInput(value: string) {
    const i = el('input') as HTMLInputElement;
    i.type = 'text';
    i.value = value;
    i.style.width = '100%';
    i.style.boxSizing = 'border-box';
    i.style.padding = '8px 10px';
    i.style.border = '1px solid rgba(209, 213, 219, 0.7)';
    i.style.borderRadius = '10px';
    i.style.background = 'rgba(255, 255, 255, 0.55)';
    return i;
  }

  function textArea(value: string, heightPx = 90) {
    const t = el('textarea') as HTMLTextAreaElement;
    t.value = value;
    t.style.width = '100%';
    t.style.boxSizing = 'border-box';
    t.style.padding = '8px 10px';
    t.style.border = '1px solid rgba(209, 213, 219, 0.7)';
    t.style.borderRadius = '10px';
    t.style.background = 'rgba(255, 255, 255, 0.55)';
    t.style.minHeight = `${heightPx}px`;
    t.style.resize = 'vertical';
    return t;
  }

  function smallButton(text: string) {
    const b = el('button') as HTMLButtonElement;
    b.textContent = text;
    b.style.padding = '8px 10px';
    b.style.border = '1px solid rgba(209, 213, 219, 0.65)';
    b.style.borderRadius = '10px';
    b.style.background = 'rgba(255, 255, 255, 0.35)';
    return b;
  }

  async function refreshBeats(actId: string, sceneId: string) {
    const res = (await kernelRequest('play/beats/list', { act_id: actId, scene_id: sceneId })) as PlayBeatsListResult;
    beatsCache = res.beats ?? [];
  }

  async function refreshKbForSelection() {
    if (!activeActId) return;
    const sceneId = selectedSceneId ?? undefined;
    const beatId = selectedBeatId ?? undefined;

    const filesRes = (await kernelRequest('play/kb/list', {
      act_id: activeActId,
      scene_id: sceneId,
      beat_id: beatId
    })) as PlayKbListResult;

    const files = filesRes.files ?? [];
    if (files.length > 0 && !files.includes(kbSelectedPath)) {
      kbSelectedPath = files[0];
    }

    try {
      const readRes = (await kernelRequest('play/kb/read', {
        act_id: activeActId,
        scene_id: sceneId,
        beat_id: beatId,
        path: kbSelectedPath
      })) as PlayKbReadResult;
      kbTextDraft = readRes.text ?? '';
    } catch {
      // If missing, keep draft as-is (acts as a create).
    }
    kbPreview = null;
  }

  function renderPlayInspector() {
    inspectionTitle.textContent = 'The Play';
    inspectionBody.innerHTML = '';

    if (!activeActId) {
      const empty = el('div');
      empty.textContent = 'Create an Act to begin.';
      empty.style.opacity = '0.8';
      inspectionBody.appendChild(empty);

      inspectionBody.appendChild(rowHeader('Act'));
      const actCreateRow = el('div');
      actCreateRow.style.display = 'flex';
      actCreateRow.style.gap = '8px';
      const actNewTitle = textInput('');
      actNewTitle.placeholder = 'New act title';
      const actCreate = smallButton('Create');
      actCreateRow.appendChild(actNewTitle);
      actCreateRow.appendChild(actCreate);
      inspectionBody.appendChild(actCreateRow);

      actCreate.addEventListener('click', () => {
        void (async () => {
          const title = actNewTitle.value.trim();
          if (!title) return;
          const res = (await kernelRequest('play/acts/create', { title })) as PlayActsCreateResult;
          activeActId = res.created_act_id;
          selectedSceneId = null;
          selectedBeatId = null;
          await refreshActs();
          if (activeActId) await refreshScenes(activeActId);
        })();
      });
      return;
    }

    const activeAct = actsCache.find((a) => a.act_id === activeActId) ?? null;

    const status = el('div');
    status.style.fontSize = '12px';
    status.style.opacity = '0.85';
    status.style.marginBottom = '8px';
    status.textContent = selectedBeatId
      ? `Act → Scene → Beat`
      : selectedSceneId
        ? `Act → Scene`
        : `Act`;
    inspectionBody.appendChild(status);

    // Act editor + create
    inspectionBody.appendChild(rowHeader('Act'));

    const actTitle = textInput('');
    const actNotes = textArea('', 70);
    const actSave = smallButton('Save Act');
    const actCreateRow = el('div');
    actCreateRow.style.display = 'flex';
    actCreateRow.style.gap = '8px';
    const actNewTitle = textInput('');
    actNewTitle.placeholder = 'New act title';
    const actCreate = smallButton('Create');
    actCreateRow.appendChild(actNewTitle);
    actCreateRow.appendChild(actCreate);

    inspectionBody.appendChild(label('Title'));
    inspectionBody.appendChild(actTitle);
    inspectionBody.appendChild(label('Notes'));
    inspectionBody.appendChild(actNotes);
    inspectionBody.appendChild(actSave);
    inspectionBody.appendChild(label('Create new act'));
    inspectionBody.appendChild(actCreateRow);

    void (async () => {
      if (!activeAct) return;
      actTitle.value = activeAct.title ?? '';
      actNotes.value = activeAct.notes ?? '';
    })();

    actSave.addEventListener('click', () => {
      void (async () => {
        if (!activeActId) return;
        await kernelRequest('play/acts/update', {
          act_id: activeActId,
          title: actTitle.value,
          notes: actNotes.value
        });
        await refreshActs();
      })();
    });

    actCreate.addEventListener('click', () => {
      void (async () => {
        const title = actNewTitle.value.trim();
        if (!title) return;
        const res = (await kernelRequest('play/acts/create', { title })) as PlayActsCreateResult;
        activeActId = res.created_act_id;
        selectedSceneId = null;
        selectedBeatId = null;
        await refreshActs();
        if (activeActId) await refreshScenes(activeActId);
      })();
    });

    // Scenes section
    inspectionBody.appendChild(rowHeader('Scenes'));

    const sceneCreateTitle = textInput('');
    sceneCreateTitle.placeholder = 'New scene title';
    const sceneCreateBtn = smallButton('Create');
    const sceneCreateRow = el('div');
    sceneCreateRow.style.display = 'flex';
    sceneCreateRow.style.gap = '8px';
    sceneCreateRow.appendChild(sceneCreateTitle);
    sceneCreateRow.appendChild(sceneCreateBtn);
    inspectionBody.appendChild(sceneCreateRow);

    const scenesList = el('div');
    scenesList.style.display = 'flex';
    scenesList.style.flexDirection = 'column';
    scenesList.style.gap = '6px';
    scenesList.style.marginTop = '8px';
    inspectionBody.appendChild(scenesList);

    const sceneDetails = el('div');
    inspectionBody.appendChild(sceneDetails);

    const beatsDetails = el('div');
    inspectionBody.appendChild(beatsDetails);

    const kbSection = el('div');
    inspectionBody.appendChild(kbSection);

    const renderScenesList = () => {
      scenesList.innerHTML = '';
      if (scenesCache.length === 0) {
        const empty = el('div');
        empty.textContent = '(no scenes yet)';
        empty.style.opacity = '0.7';
        scenesList.appendChild(empty);
        return;
      }
      for (const s of scenesCache) {
        const btn = smallButton(selectedSceneId === s.scene_id ? `• ${s.title}` : s.title);
        btn.style.textAlign = 'left';
        btn.addEventListener('click', () => {
          selectedSceneId = s.scene_id;
          selectedBeatId = null;
          void (async () => {
            if (activeActId) {
              await refreshBeats(activeActId, s.scene_id);
              await refreshKbForSelection();
            }
            renderPlayInspector();
          })();
        });
        scenesList.appendChild(btn);
      }
    };

    const renderSceneDetails = () => {
      sceneDetails.innerHTML = '';
      if (!selectedSceneId) return;
      const s = scenesCache.find((x) => x.scene_id === selectedSceneId);
      if (!s) return;

      sceneDetails.appendChild(rowHeader('Scene Details'));
      const tTitle = textInput(s.title ?? '');
      const tIntent = textInput(s.intent ?? '');
      const tStatus = textInput(s.status ?? '');
      const tH = textInput(s.time_horizon ?? '');
      const tNotes = textArea(s.notes ?? '', 80);
      const save = smallButton('Save Scene');

      sceneDetails.appendChild(label('Title'));
      sceneDetails.appendChild(tTitle);
      sceneDetails.appendChild(label('Intent'));
      sceneDetails.appendChild(tIntent);
      sceneDetails.appendChild(label('Status'));
      sceneDetails.appendChild(tStatus);
      sceneDetails.appendChild(label('Time horizon'));
      sceneDetails.appendChild(tH);
      sceneDetails.appendChild(label('Notes'));
      sceneDetails.appendChild(tNotes);
      sceneDetails.appendChild(save);

      save.addEventListener('click', () => {
        void (async () => {
          if (!activeActId || !selectedSceneId) return;
          await kernelRequest('play/scenes/update', {
            act_id: activeActId,
            scene_id: selectedSceneId,
            title: tTitle.value,
            intent: tIntent.value,
            status: tStatus.value,
            time_horizon: tH.value,
            notes: tNotes.value
          });
          await refreshScenes(activeActId);
          renderPlayInspector();
        })();
      });
    };

    const renderBeats = () => {
      beatsDetails.innerHTML = '';
      if (!activeActId || !selectedSceneId) return;

      beatsDetails.appendChild(rowHeader('Beats'));

      const createRow = el('div');
      createRow.style.display = 'flex';
      createRow.style.gap = '8px';
      const newTitle = textInput('');
      newTitle.placeholder = 'New beat title';
      const newStatus = textInput('');
      newStatus.placeholder = 'status';
      const createBtn = smallButton('Create');
      createRow.appendChild(newTitle);
      createRow.appendChild(newStatus);
      createRow.appendChild(createBtn);
      beatsDetails.appendChild(createRow);

      const list = el('div');
      list.style.display = 'flex';
      list.style.flexDirection = 'column';
      list.style.gap = '6px';
      list.style.marginTop = '8px';
      beatsDetails.appendChild(list);

      const detail = el('div');
      beatsDetails.appendChild(detail);

      const renderList = () => {
        list.innerHTML = '';
        if (beatsCache.length === 0) {
          const empty = el('div');
          empty.textContent = '(no beats yet)';
          empty.style.opacity = '0.7';
          list.appendChild(empty);
          return;
        }
        for (const b of beatsCache) {
          const btn = smallButton(selectedBeatId === b.beat_id ? `• ${b.title}` : b.title);
          btn.style.textAlign = 'left';
          btn.addEventListener('click', () => {
            selectedBeatId = b.beat_id;
            void (async () => {
              await refreshKbForSelection();
              renderPlayInspector();
            })();
          });
          list.appendChild(btn);
        }
      };

      const renderDetail = () => {
        detail.innerHTML = '';
        if (!selectedBeatId) return;
        const b = beatsCache.find((x) => x.beat_id === selectedBeatId);
        if (!b) return;

        detail.appendChild(rowHeader('Beat Details'));
        const tTitle = textInput(b.title ?? '');
        const tStatus = textInput(b.status ?? '');
        const tLink = textInput(b.link ?? '');
        const tNotes = textArea(b.notes ?? '', 80);
        const save = smallButton('Save Beat');

        detail.appendChild(label('Title'));
        detail.appendChild(tTitle);
        detail.appendChild(label('Status'));
        detail.appendChild(tStatus);
        detail.appendChild(label('Link'));
        detail.appendChild(tLink);
        detail.appendChild(label('Notes'));
        detail.appendChild(tNotes);
        detail.appendChild(save);

        save.addEventListener('click', () => {
          void (async () => {
            if (!activeActId || !selectedSceneId || !selectedBeatId) return;
            await kernelRequest('play/beats/update', {
              act_id: activeActId,
              scene_id: selectedSceneId,
              beat_id: selectedBeatId,
              title: tTitle.value,
              status: tStatus.value,
              link: tLink.value || null,
              notes: tNotes.value
            });
            await refreshBeats(activeActId, selectedSceneId);
            renderPlayInspector();
          })();
        });
      };

      createBtn.addEventListener('click', () => {
        void (async () => {
          const title = newTitle.value.trim();
          if (!title) return;
          await kernelRequest('play/beats/create', {
            act_id: activeActId,
            scene_id: selectedSceneId,
            title,
            status: newStatus.value
          });
          await refreshBeats(activeActId, selectedSceneId);
          renderPlayInspector();
        })();
      });

      renderList();
      renderDetail();
    };

    const renderKb = () => {
      kbSection.innerHTML = '';
      kbSection.appendChild(rowHeader('Mini Knowledgebase'));

      const who = el('div');
      who.style.fontSize = '12px';
      who.style.opacity = '0.8';
      who.style.marginBottom = '6px';
      who.textContent = selectedBeatId
        ? `Beat KB`
        : selectedSceneId
          ? `Scene KB`
          : `Act KB`;
      kbSection.appendChild(who);

      const fileRow = el('div');
      fileRow.style.display = 'flex';
      fileRow.style.gap = '8px';
      const pathInput = textInput(kbSelectedPath);
      const loadBtn = smallButton('Load');
      fileRow.appendChild(pathInput);
      fileRow.appendChild(loadBtn);
      kbSection.appendChild(fileRow);

      const listWrap = el('div');
      listWrap.style.display = 'flex';
      listWrap.style.flexWrap = 'wrap';
      listWrap.style.gap = '6px';
      listWrap.style.margin = '8px 0';
      kbSection.appendChild(listWrap);

      const editor = textArea(kbTextDraft, 180);
      kbSection.appendChild(editor);

      const btnRow = el('div');
      btnRow.style.display = 'flex';
      btnRow.style.gap = '8px';
      btnRow.style.marginTop = '8px';
      const previewBtn = smallButton('Preview');
      const applyBtn = smallButton('Apply');
      btnRow.appendChild(previewBtn);
      btnRow.appendChild(applyBtn);
      kbSection.appendChild(btnRow);

      const diffPre = el('pre');
      diffPre.style.whiteSpace = 'pre-wrap';
      diffPre.style.fontSize = '12px';
      diffPre.style.marginTop = '8px';
      diffPre.style.padding = '8px 10px';
      diffPre.style.borderRadius = '10px';
      diffPre.style.border = '1px solid rgba(209, 213, 219, 0.65)';
      diffPre.style.background = 'rgba(255, 255, 255, 0.35)';
      diffPre.textContent = kbPreview ? kbPreview.diff : '';
      kbSection.appendChild(diffPre);

      const errorLine = el('div');
      errorLine.style.fontSize = '12px';
      errorLine.style.marginTop = '6px';
      errorLine.style.opacity = '0.85';
      kbSection.appendChild(errorLine);

      editor.addEventListener('input', () => {
        kbTextDraft = editor.value;
      });

      pathInput.addEventListener('input', () => {
        kbSelectedPath = pathInput.value;
      });

      loadBtn.addEventListener('click', () => {
        void (async () => {
          errorLine.textContent = '';
          kbSelectedPath = pathInput.value || 'kb.md';
          await refreshKbForSelection();
          renderPlayInspector();
        })();
      });

      previewBtn.addEventListener('click', () => {
        void (async () => {
          errorLine.textContent = '';
          if (!activeActId) return;
          try {
            const res = (await kernelRequest('play/kb/write_preview', {
              act_id: activeActId,
              scene_id: selectedSceneId,
              beat_id: selectedBeatId,
              path: kbSelectedPath,
              text: editor.value
            })) as PlayKbWritePreviewResult;
            kbPreview = res;
            diffPre.textContent = res.diff ?? '';
          } catch (e) {
            errorLine.textContent = `Preview error: ${String(e)}`;
          }
        })();
      });

      applyBtn.addEventListener('click', () => {
        void (async () => {
          errorLine.textContent = '';
          if (!activeActId) return;
          if (!kbPreview) {
            errorLine.textContent = 'Preview first.';
            return;
          }
          try {
            const res = (await kernelRequest('play/kb/write_apply', {
              act_id: activeActId,
              scene_id: selectedSceneId,
              beat_id: selectedBeatId,
              path: kbSelectedPath,
              text: editor.value,
              expected_sha256_current: kbPreview.expected_sha256_current
            })) as PlayKbWriteApplyResult;
            void res;
            await refreshKbForSelection();
            renderPlayInspector();
          } catch (e) {
            if (e instanceof KernelError && e.code === -32009) {
              errorLine.textContent = 'Conflict: file changed since preview. Re-preview to continue.';
            } else {
              errorLine.textContent = `Apply error: ${String(e)}`;
            }
          }
        })();
      });

      // Render file pills if we already have them cached.
      void (async () => {
        try {
          if (!activeActId) return;
          const filesRes = (await kernelRequest('play/kb/list', {
            act_id: activeActId,
            scene_id: selectedSceneId,
            beat_id: selectedBeatId
          })) as PlayKbListResult;
          const files = filesRes.files ?? [];
          listWrap.innerHTML = '';
          for (const f of files) {
            const pill = smallButton(f);
            pill.addEventListener('click', () => {
              kbSelectedPath = f;
              void (async () => {
                await refreshKbForSelection();
                renderPlayInspector();
              })();
            });
            listWrap.appendChild(pill);
          }
        } catch {
          // ignore
        }
      })();
    };

    sceneCreateBtn.addEventListener('click', () => {
      void (async () => {
        const title = sceneCreateTitle.value.trim();
        if (!title) return;
        await kernelRequest('play/scenes/create', { act_id: activeActId, title });
        await refreshScenes(activeActId);
        renderPlayInspector();
      })();
    });

    renderScenesList();
    renderSceneDetails();
    renderBeats();
    void (async () => {
      await refreshKbForSelection();
      renderKb();
    })();
  }

  async function refreshActs() {
    const res = (await kernelRequest('play/acts/list', {})) as PlayActsListResult;
    activeActId = res.active_act_id ?? null;
    actsCache = res.acts ?? [];

    actsList.innerHTML = '';
    for (const a of actsCache) {
      const btn = el('button');
      btn.textContent = a.act_id === activeActId ? `• ${a.title}` : a.title;
      btn.addEventListener('click', async () => {
        const setRes = (await kernelRequest('play/acts/set_active', { act_id: a.act_id })) as PlayActsListResult;
        activeActId = setRes.active_act_id ?? null;
        selectedSceneId = null;
        selectedBeatId = null;
        await refreshActs();
        if (activeActId) await refreshScenes(activeActId);
      });
      actsList.appendChild(btn);
    }

    if (actsCache.length === 0) {
      const empty = el('div');
      empty.textContent = '(no acts yet)';
      empty.style.opacity = '0.7';
      actsList.appendChild(empty);
    }

    renderPlayInspector();
  }

  async function refreshScenes(actId: string) {
    const res = (await kernelRequest('play/scenes/list', { act_id: actId })) as PlayScenesListResult;
    scenesCache = res.scenes ?? [];
    if (selectedSceneId && !scenesCache.some((s) => s.scene_id === selectedSceneId)) {
      selectedSceneId = null;
      selectedBeatId = null;
    }
    if (activeActId) {
      if (selectedSceneId) {
        await refreshBeats(activeActId, selectedSceneId);
      } else {
        beatsCache = [];
      }
    }
    renderPlayInspector();
  }


  // Patterns that suggest user wants to run a system command
  const systemCommandPatterns = [
    /\b(what('?s| is) my) ip/i,
    /\b(show|get|find|check|list|display|tell me)\b.*\b(ip|port|process|service|disk|memory|cpu|file|folder|log|container)/i,
    /\b(kill|stop|start|restart|disable|enable)\b.*\b(process|service|daemon)/i,
    /\b(open|listening|running)\b.*\b(port|process|service)/i,
    /\bhow (much|many)\b.*\b(memory|ram|disk|space|storage|cpu)/i,
    /\b(disk|memory|cpu|ram)\s*(usage|space|info)/i,
    /\buptime\b/i,
    /\b(system|machine) info/i,
    /\bwho am i\b/i,
    /\bcurrent user\b/i,
    /\b(find|search|locate|grep)\b.*(file|text|string|pattern)/i,
    /\bdocker\b.*(container|image|ps|log)/i,
    /\bsystemd?\b.*(service|status|unit)/i,
    /\brun\s+['"`]?[a-z]/i,  // "run ls", "run 'ls -la'"
    /^!.+/,  // starts with ! like a shell command
  ];

  function looksLikeSystemCommand(text: string): boolean {
    return systemCommandPatterns.some(pattern => pattern.test(text));
  }

  async function onSend() {
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    append('user', text);

    // Immediately show an empty ReOS bubble with a thinking animation.
    const pending = appendThinking();

    // Ensure the browser paints the new bubbles before we start the kernel RPC.
    // Note: `requestAnimationFrame` alone can resume into a microtask that still
    // runs before paint, so we also yield a macrotask.
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    await new Promise<void>((resolve) => setTimeout(resolve, 0));

    try {
      // Check if this looks like a system command request
      if (looksLikeSystemCommand(text)) {
        // Try to suggest a command
        const suggestion = (await kernelRequest('bash/suggest', { intent: text })) as BashSuggestResult;

        if (suggestion.found && suggestion.command_template) {
          // Check if we need parameters
          const needsParams = (suggestion.requires_params ?? []).length > 0;

          if (needsParams) {
            // Ask for parameters through chat
            pending.bubble.classList.remove('thinking');
            pending.bubble.textContent = `I found a matching command template: ${suggestion.description}\n\nCommand: ${suggestion.command_template}\n\nThis command needs the following parameters: ${suggestion.requires_params?.join(', ')}\n\nPlease provide the values or type the full command you want to run.`;
          } else {
            // Propose the command directly
            const proposal = (await kernelRequest('bash/propose', {
              command: suggestion.command_template,
              description: suggestion.description || 'Execute system command'
            })) as BashProposal;

            // Remove thinking bubble and show proposal
            pending.row.remove();
            appendCommandProposal(proposal);
          }
        } else {
          // Check if user typed a direct command with ! prefix
          if (text.startsWith('!')) {
            const command = text.slice(1).trim();
            const proposal = (await kernelRequest('bash/propose', {
              command,
              description: 'User-specified command'
            })) as BashProposal;

            pending.row.remove();
            appendCommandProposal(proposal);
          } else {
            // Fall back to chat for suggestions
            const res = (await kernelRequest('chat/respond', { text })) as ChatRespondResult;
            pending.bubble.classList.remove('thinking');
            pending.bubble.textContent = res.answer ?? '(no answer)';
          }
        }
      } else {
        // Normal chat response
        const res = (await kernelRequest('chat/respond', { text })) as ChatRespondResult;
        pending.bubble.classList.remove('thinking');
        pending.bubble.textContent = res.answer ?? '(no answer)';
      }
    } catch (e) {
      pending.bubble.classList.remove('thinking');
      pending.bubble.textContent = `Error: ${String(e)}`;
    }
  }

  send.addEventListener('click', () => void onSend());
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') void onSend();
  });

  // Initial load
  void (async () => {
    try {
      await refreshActs();
      if (activeActId) await refreshScenes(activeActId);
    } catch (e) {
      showJsonInInspector('Startup error', { error: String(e) });
    }
  })();
}

async function buildMeWindow() {
  const root = document.getElementById('app');
  if (!root) return;
  root.innerHTML = '';

  const wrap = el('div');
  wrap.style.padding = '12px';
  wrap.style.height = '100vh';
  wrap.style.boxSizing = 'border-box';
  wrap.style.overflow = 'auto';

  const title = el('div');
  title.textContent = 'Me (The Play)';
  title.style.fontWeight = '600';
  title.style.marginBottom = '10px';

  const body = el('pre');
  body.style.margin = '0';
  body.style.whiteSpace = 'pre-wrap';

  wrap.appendChild(title);
  wrap.appendChild(body);
  root.appendChild(wrap);

  try {
    const res = (await kernelRequest('play/me/read', {})) as PlayMeReadResult;
    body.textContent = res.markdown ?? '';
  } catch (e) {
    body.textContent = `Error: ${String(e)}`;
  }
}

async function buildCommandDashboardWindow() {
  const root = document.getElementById('app');
  if (!root) return;
  root.innerHTML = '';

  // Utility functions for the dashboard
  function createCard(title: string): { card: HTMLDivElement; body: HTMLDivElement } {
    const card = el('div') as HTMLDivElement;
    card.style.background = 'rgba(255, 255, 255, 0.7)';
    card.style.borderRadius = '12px';
    card.style.padding = '16px';
    card.style.boxShadow = '0 1px 3px rgba(0,0,0,0.08)';

    const header = el('div');
    header.textContent = title;
    header.style.fontWeight = '600';
    header.style.fontSize = '14px';
    header.style.marginBottom = '12px';
    header.style.color = '#374151';

    const body = el('div') as HTMLDivElement;
    card.appendChild(header);
    card.appendChild(body);

    return { card, body };
  }

  function createProgressBar(percent: number, color: string = '#3b82f6'): HTMLDivElement {
    const wrap = el('div') as HTMLDivElement;
    wrap.style.height = '8px';
    wrap.style.background = '#e5e7eb';
    wrap.style.borderRadius = '4px';
    wrap.style.overflow = 'hidden';

    const bar = el('div') as HTMLDivElement;
    bar.style.height = '100%';
    bar.style.width = `${Math.min(100, percent)}%`;
    bar.style.background = percent > 90 ? '#ef4444' : percent > 70 ? '#f59e0b' : color;
    bar.style.borderRadius = '4px';
    bar.style.transition = 'width 0.3s ease';

    wrap.appendChild(bar);
    return wrap;
  }

  function createStatRow(label: string, value: string, subValue?: string): HTMLDivElement {
    const row = el('div') as HTMLDivElement;
    row.style.display = 'flex';
    row.style.justifyContent = 'space-between';
    row.style.alignItems = 'center';
    row.style.padding = '4px 0';

    const labelEl = el('span');
    labelEl.textContent = label;
    labelEl.style.color = '#6b7280';
    labelEl.style.fontSize = '13px';

    const valueWrap = el('div');
    valueWrap.style.textAlign = 'right';

    const valueEl = el('span');
    valueEl.textContent = value;
    valueEl.style.fontWeight = '500';
    valueEl.style.fontSize = '13px';

    valueWrap.appendChild(valueEl);

    if (subValue) {
      const subEl = el('div');
      subEl.textContent = subValue;
      subEl.style.fontSize = '11px';
      subEl.style.color = '#9ca3af';
      valueWrap.appendChild(subEl);
    }

    row.appendChild(labelEl);
    row.appendChild(valueWrap);
    return row;
  }

  function createStatusBadge(status: string, isActive: boolean): HTMLSpanElement {
    const badge = el('span') as HTMLSpanElement;
    badge.textContent = status;
    badge.style.padding = '2px 8px';
    badge.style.borderRadius = '9999px';
    badge.style.fontSize = '11px';
    badge.style.fontWeight = '500';
    if (isActive) {
      badge.style.background = '#dcfce7';
      badge.style.color = '#166534';
    } else {
      badge.style.background = '#fef2f2';
      badge.style.color = '#991b1b';
    }
    return badge;
  }

  // Main container
  const container = el('div');
  container.style.padding = '20px';
  container.style.height = '100vh';
  container.style.boxSizing = 'border-box';
  container.style.overflow = 'auto';
  container.style.background = 'linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%)';
  container.style.fontFamily = 'system-ui, -apple-system, sans-serif';

  // Header
  const header = el('div');
  header.style.display = 'flex';
  header.style.justifyContent = 'space-between';
  header.style.alignItems = 'center';
  header.style.marginBottom = '20px';

  const titleEl = el('h1');
  titleEl.textContent = 'Command Dashboard';
  titleEl.style.margin = '0';
  titleEl.style.fontSize = '24px';
  titleEl.style.fontWeight = '600';
  titleEl.style.color = '#1f2937';

  const refreshBtn = el('button');
  refreshBtn.textContent = 'Refresh';
  refreshBtn.style.padding = '8px 16px';
  refreshBtn.style.borderRadius = '8px';
  refreshBtn.style.border = '1px solid #d1d5db';
  refreshBtn.style.background = 'white';
  refreshBtn.style.cursor = 'pointer';
  refreshBtn.style.fontSize = '13px';

  header.appendChild(titleEl);
  header.appendChild(refreshBtn);
  container.appendChild(header);

  // Grid layout for dashboard
  const grid = el('div');
  grid.style.display = 'grid';
  grid.style.gridTemplateColumns = 'repeat(auto-fit, minmax(350px, 1fr))';
  grid.style.gap = '16px';
  container.appendChild(grid);

  // System Summary Card
  const { card: summaryCard, body: summaryBody } = createCard('System Overview');
  grid.appendChild(summaryCard);

  // Resources Card
  const { card: resourcesCard, body: resourcesBody } = createCard('Resource Utilization');
  grid.appendChild(resourcesCard);

  // Services Card (full width)
  const { card: servicesCard, body: servicesBody } = createCard('Systemd Services');
  servicesCard.style.gridColumn = '1 / -1';

  const servicesControls = el('div');
  servicesControls.style.display = 'flex';
  servicesControls.style.gap = '8px';
  servicesControls.style.marginBottom = '12px';

  const serviceFilter = el('select') as HTMLSelectElement;
  serviceFilter.innerHTML = `
    <option value="all">All Services</option>
    <option value="active">Active Only</option>
    <option value="failed">Failed Only</option>
    <option value="inactive">Inactive Only</option>
  `;
  serviceFilter.style.padding = '6px 10px';
  serviceFilter.style.borderRadius = '6px';
  serviceFilter.style.border = '1px solid #d1d5db';
  serviceFilter.style.fontSize = '12px';

  const serviceSearch = el('input') as HTMLInputElement;
  serviceSearch.type = 'text';
  serviceSearch.placeholder = 'Search services...';
  serviceSearch.style.padding = '6px 10px';
  serviceSearch.style.borderRadius = '6px';
  serviceSearch.style.border = '1px solid #d1d5db';
  serviceSearch.style.fontSize = '12px';
  serviceSearch.style.flex = '1';

  servicesControls.appendChild(serviceFilter);
  servicesControls.appendChild(serviceSearch);
  servicesBody.appendChild(servicesControls);

  const servicesTable = el('div');
  servicesTable.style.maxHeight = '300px';
  servicesTable.style.overflow = 'auto';
  servicesBody.appendChild(servicesTable);

  grid.appendChild(servicesCard);

  // Processes Card
  const { card: processesCard, body: processesBody } = createCard('Running Processes');
  processesCard.style.gridColumn = '1 / -1';

  const processesTable = el('div');
  processesTable.style.maxHeight = '300px';
  processesTable.style.overflow = 'auto';
  processesBody.appendChild(processesTable);

  grid.appendChild(processesCard);

  // Containers Card
  const { card: containersCard, body: containersBody } = createCard('Containers');
  containersCard.style.gridColumn = '1 / -1';

  const containersTable = el('div');
  containersBody.appendChild(containersTable);

  grid.appendChild(containersCard);

  root.appendChild(container);

  // Data storage
  let servicesData: SystemdService[] = [];

  // Render functions
  function renderSummary(summary: SystemSummary) {
    summaryBody.innerHTML = '';

    const hostRow = el('div');
    hostRow.style.marginBottom = '16px';
    hostRow.style.padding = '12px';
    hostRow.style.background = '#f3f4f6';
    hostRow.style.borderRadius = '8px';

    const hostname = el('div');
    hostname.textContent = summary.hostname;
    hostname.style.fontSize = '18px';
    hostname.style.fontWeight = '600';
    hostname.style.color = '#1f2937';

    const osInfo = el('div');
    osInfo.textContent = `${summary.os_name}`;
    osInfo.style.fontSize = '12px';
    osInfo.style.color = '#6b7280';
    osInfo.style.marginTop = '4px';

    const kernelInfo = el('div');
    kernelInfo.textContent = `Kernel: ${summary.kernel}`;
    kernelInfo.style.fontSize = '12px';
    kernelInfo.style.color = '#6b7280';

    hostRow.appendChild(hostname);
    hostRow.appendChild(osInfo);
    hostRow.appendChild(kernelInfo);
    summaryBody.appendChild(hostRow);

    summaryBody.appendChild(createStatRow('Uptime', summary.uptime));
    summaryBody.appendChild(createStatRow('Load Average', summary.load_avg));
    summaryBody.appendChild(createStatRow('Processes', String(summary.process_count)));
    summaryBody.appendChild(createStatRow('Services', `${summary.running_services} / ${summary.service_count} active`));
    summaryBody.appendChild(createStatRow('Containers', `${summary.running_containers} / ${summary.container_count} running`));
  }

  function renderResources(resources: SystemResources) {
    resourcesBody.innerHTML = '';

    // CPU
    const cpuSection = el('div');
    cpuSection.style.marginBottom = '16px';

    const cpuHeader = el('div');
    cpuHeader.style.display = 'flex';
    cpuHeader.style.justifyContent = 'space-between';
    cpuHeader.style.marginBottom = '6px';

    const cpuLabel = el('span');
    cpuLabel.textContent = `CPU (${resources.cpu_count} cores)`;
    cpuLabel.style.fontSize = '13px';
    cpuLabel.style.color = '#374151';

    const cpuValue = el('span');
    cpuValue.textContent = `${resources.cpu_percent}%`;
    cpuValue.style.fontSize = '13px';
    cpuValue.style.fontWeight = '600';

    cpuHeader.appendChild(cpuLabel);
    cpuHeader.appendChild(cpuValue);
    cpuSection.appendChild(cpuHeader);
    cpuSection.appendChild(createProgressBar(resources.cpu_percent, '#3b82f6'));

    const loadInfo = el('div');
    loadInfo.textContent = `Load: ${resources.load_avg_1.toFixed(2)}, ${resources.load_avg_5.toFixed(2)}, ${resources.load_avg_15.toFixed(2)}`;
    loadInfo.style.fontSize = '11px';
    loadInfo.style.color = '#9ca3af';
    loadInfo.style.marginTop = '4px';
    cpuSection.appendChild(loadInfo);

    resourcesBody.appendChild(cpuSection);

    // Memory
    const memSection = el('div');
    memSection.style.marginBottom = '16px';

    const memHeader = el('div');
    memHeader.style.display = 'flex';
    memHeader.style.justifyContent = 'space-between';
    memHeader.style.marginBottom = '6px';

    const memLabel = el('span');
    memLabel.textContent = 'Memory';
    memLabel.style.fontSize = '13px';
    memLabel.style.color = '#374151';

    const memValue = el('span');
    memValue.textContent = `${resources.memory_used_mb} / ${resources.memory_total_mb} MB (${resources.memory_percent}%)`;
    memValue.style.fontSize = '13px';
    memValue.style.fontWeight = '600';

    memHeader.appendChild(memLabel);
    memHeader.appendChild(memValue);
    memSection.appendChild(memHeader);
    memSection.appendChild(createProgressBar(resources.memory_percent, '#8b5cf6'));

    resourcesBody.appendChild(memSection);

    // Swap
    if (resources.swap_total_mb > 0) {
      const swapSection = el('div');
      swapSection.style.marginBottom = '16px';

      const swapHeader = el('div');
      swapHeader.style.display = 'flex';
      swapHeader.style.justifyContent = 'space-between';
      swapHeader.style.marginBottom = '6px';

      const swapLabel = el('span');
      swapLabel.textContent = 'Swap';
      swapLabel.style.fontSize = '13px';
      swapLabel.style.color = '#374151';

      const swapValue = el('span');
      swapValue.textContent = `${resources.swap_used_mb} / ${resources.swap_total_mb} MB (${resources.swap_percent}%)`;
      swapValue.style.fontSize = '13px';
      swapValue.style.fontWeight = '600';

      swapHeader.appendChild(swapLabel);
      swapHeader.appendChild(swapValue);
      swapSection.appendChild(swapHeader);
      swapSection.appendChild(createProgressBar(resources.swap_percent, '#f59e0b'));

      resourcesBody.appendChild(swapSection);
    }

    // Disk
    const diskSection = el('div');

    const diskHeader = el('div');
    diskHeader.style.display = 'flex';
    diskHeader.style.justifyContent = 'space-between';
    diskHeader.style.marginBottom = '6px';

    const diskLabel = el('span');
    diskLabel.textContent = 'Disk (/)';
    diskLabel.style.fontSize = '13px';
    diskLabel.style.color = '#374151';

    const diskValue = el('span');
    diskValue.textContent = `${resources.disk_used_gb} / ${resources.disk_total_gb} GB (${resources.disk_percent}%)`;
    diskValue.style.fontSize = '13px';
    diskValue.style.fontWeight = '600';

    diskHeader.appendChild(diskLabel);
    diskHeader.appendChild(diskValue);
    diskSection.appendChild(diskHeader);
    diskSection.appendChild(createProgressBar(resources.disk_percent, '#10b981'));

    resourcesBody.appendChild(diskSection);
  }

  function renderServices(filter: string, search: string) {
    servicesTable.innerHTML = '';

    let filtered = servicesData;

    if (filter === 'active') {
      filtered = filtered.filter(s => s.active_state === 'active');
    } else if (filter === 'failed') {
      filtered = filtered.filter(s => s.active_state === 'failed');
    } else if (filter === 'inactive') {
      filtered = filtered.filter(s => s.active_state === 'inactive');
    }

    if (search) {
      const lowerSearch = search.toLowerCase();
      filtered = filtered.filter(s =>
        s.unit.toLowerCase().includes(lowerSearch) ||
        s.description.toLowerCase().includes(lowerSearch)
      );
    }

    if (filtered.length === 0) {
      const empty = el('div');
      empty.textContent = 'No services match the filter';
      empty.style.padding = '20px';
      empty.style.textAlign = 'center';
      empty.style.color = '#9ca3af';
      servicesTable.appendChild(empty);
      return;
    }

    // Table header
    const headerRow = el('div');
    headerRow.style.display = 'grid';
    headerRow.style.gridTemplateColumns = '2fr 1fr 3fr';
    headerRow.style.gap = '12px';
    headerRow.style.padding = '8px 12px';
    headerRow.style.borderBottom = '1px solid #e5e7eb';
    headerRow.style.fontWeight = '600';
    headerRow.style.fontSize = '12px';
    headerRow.style.color = '#6b7280';
    headerRow.style.position = 'sticky';
    headerRow.style.top = '0';
    headerRow.style.background = 'rgba(255,255,255,0.95)';

    const colService = el('span');
    colService.textContent = 'Service';
    const colStatus = el('span');
    colStatus.textContent = 'Status';
    const colDesc = el('span');
    colDesc.textContent = 'Description';

    headerRow.appendChild(colService);
    headerRow.appendChild(colStatus);
    headerRow.appendChild(colDesc);
    servicesTable.appendChild(headerRow);

    for (const service of filtered) {
      const row = el('div');
      row.style.display = 'grid';
      row.style.gridTemplateColumns = '2fr 1fr 3fr';
      row.style.gap = '12px';
      row.style.padding = '8px 12px';
      row.style.borderBottom = '1px solid #f3f4f6';
      row.style.fontSize = '12px';
      row.style.alignItems = 'center';

      const unitName = el('span');
      unitName.textContent = service.unit.replace('.service', '');
      unitName.style.fontFamily = 'monospace';
      unitName.style.color = '#374151';

      const statusCell = el('span');
      statusCell.appendChild(createStatusBadge(
        service.sub_state,
        service.active_state === 'active'
      ));

      const desc = el('span');
      desc.textContent = service.description;
      desc.style.color = '#6b7280';
      desc.style.overflow = 'hidden';
      desc.style.textOverflow = 'ellipsis';
      desc.style.whiteSpace = 'nowrap';

      row.appendChild(unitName);
      row.appendChild(statusCell);
      row.appendChild(desc);
      servicesTable.appendChild(row);
    }
  }

  function renderProcesses(processes: ProcessInfo[]) {
    processesTable.innerHTML = '';

    if (processes.length === 0) {
      const empty = el('div');
      empty.textContent = 'No processes found';
      empty.style.padding = '20px';
      empty.style.textAlign = 'center';
      empty.style.color = '#9ca3af';
      processesTable.appendChild(empty);
      return;
    }

    // Table header
    const headerRow = el('div');
    headerRow.style.display = 'grid';
    headerRow.style.gridTemplateColumns = '60px 80px 60px 60px 2fr 2fr';
    headerRow.style.gap = '12px';
    headerRow.style.padding = '8px 12px';
    headerRow.style.borderBottom = '1px solid #e5e7eb';
    headerRow.style.fontWeight = '600';
    headerRow.style.fontSize = '12px';
    headerRow.style.color = '#6b7280';
    headerRow.style.position = 'sticky';
    headerRow.style.top = '0';
    headerRow.style.background = 'rgba(255,255,255,0.95)';

    ['PID', 'User', 'CPU %', 'Mem %', 'What is this?', 'Command'].forEach(text => {
      const col = el('span');
      col.textContent = text;
      headerRow.appendChild(col);
    });
    processesTable.appendChild(headerRow);

    for (const proc of processes) {
      const row = el('div');
      row.style.display = 'grid';
      row.style.gridTemplateColumns = '60px 80px 60px 60px 2fr 2fr';
      row.style.gap = '12px';
      row.style.padding = '8px 12px';
      row.style.borderBottom = '1px solid #f3f4f6';
      row.style.fontSize = '12px';
      row.style.alignItems = 'center';

      const pid = el('span');
      pid.textContent = String(proc.pid);
      pid.style.fontFamily = 'monospace';

      const user = el('span');
      user.textContent = proc.user;
      user.style.color = '#6b7280';

      const cpu = el('span');
      cpu.textContent = `${proc.cpu_percent.toFixed(1)}`;
      cpu.style.color = proc.cpu_percent > 50 ? '#ef4444' : proc.cpu_percent > 20 ? '#f59e0b' : '#374151';
      cpu.style.fontWeight = proc.cpu_percent > 20 ? '600' : 'normal';

      const mem = el('span');
      mem.textContent = `${proc.mem_percent.toFixed(1)}`;
      mem.style.color = proc.mem_percent > 50 ? '#ef4444' : proc.mem_percent > 20 ? '#f59e0b' : '#374151';
      mem.style.fontWeight = proc.mem_percent > 20 ? '600' : 'normal';

      const friendly = el('span');
      friendly.textContent = proc.friendly_name;
      friendly.style.color = '#3b82f6';
      friendly.style.fontWeight = '500';

      const cmd = el('span');
      cmd.textContent = proc.command.length > 60 ? proc.command.slice(0, 60) + '...' : proc.command;
      cmd.style.fontFamily = 'monospace';
      cmd.style.fontSize = '11px';
      cmd.style.color = '#6b7280';
      cmd.style.overflow = 'hidden';
      cmd.style.textOverflow = 'ellipsis';
      cmd.style.whiteSpace = 'nowrap';
      cmd.title = proc.command;

      row.appendChild(pid);
      row.appendChild(user);
      row.appendChild(cpu);
      row.appendChild(mem);
      row.appendChild(friendly);
      row.appendChild(cmd);
      processesTable.appendChild(row);
    }
  }

  function renderContainers(containers: ContainerInfo[]) {
    containersTable.innerHTML = '';

    if (containers.length === 0) {
      const empty = el('div');
      empty.textContent = 'No containers found (Docker/Podman not available or no containers)';
      empty.style.padding = '20px';
      empty.style.textAlign = 'center';
      empty.style.color = '#9ca3af';
      containersTable.appendChild(empty);
      return;
    }

    // Table header
    const headerRow = el('div');
    headerRow.style.display = 'grid';
    headerRow.style.gridTemplateColumns = '100px 150px 200px 120px 150px 80px';
    headerRow.style.gap = '12px';
    headerRow.style.padding = '8px 12px';
    headerRow.style.borderBottom = '1px solid #e5e7eb';
    headerRow.style.fontWeight = '600';
    headerRow.style.fontSize = '12px';
    headerRow.style.color = '#6b7280';

    ['Container ID', 'Name', 'Image', 'Status', 'Ports', 'Runtime'].forEach(text => {
      const col = el('span');
      col.textContent = text;
      headerRow.appendChild(col);
    });
    containersTable.appendChild(headerRow);

    for (const container of containers) {
      const row = el('div');
      row.style.display = 'grid';
      row.style.gridTemplateColumns = '100px 150px 200px 120px 150px 80px';
      row.style.gap = '12px';
      row.style.padding = '8px 12px';
      row.style.borderBottom = '1px solid #f3f4f6';
      row.style.fontSize = '12px';
      row.style.alignItems = 'center';

      const id = el('span');
      id.textContent = container.id;
      id.style.fontFamily = 'monospace';
      id.style.color = '#6b7280';

      const name = el('span');
      name.textContent = container.name;
      name.style.fontWeight = '500';
      name.style.color = '#374151';

      const image = el('span');
      image.textContent = container.image.length > 30 ? container.image.slice(0, 30) + '...' : container.image;
      image.style.fontFamily = 'monospace';
      image.style.fontSize = '11px';
      image.style.color = '#6b7280';
      image.title = container.image;

      const status = el('span');
      const isUp = container.status.toLowerCase().includes('up');
      status.appendChild(createStatusBadge(
        container.status.split(' ')[0],
        isUp
      ));

      const ports = el('span');
      ports.textContent = container.ports || '-';
      ports.style.fontSize = '11px';
      ports.style.color = '#6b7280';

      const runtime = el('span');
      runtime.textContent = container.runtime;
      runtime.style.color = container.runtime === 'docker' ? '#2563eb' : '#7c3aed';
      runtime.style.fontWeight = '500';

      row.appendChild(id);
      row.appendChild(name);
      row.appendChild(image);
      row.appendChild(status);
      row.appendChild(ports);
      row.appendChild(runtime);
      containersTable.appendChild(row);
    }
  }

  // Fetch and render data
  async function loadData() {
    try {
      // Load overview (summary + resources)
      const overview = (await kernelRequest('system/overview', {})) as SystemOverviewResult;
      renderSummary(overview.summary);
      renderResources(overview.resources);

      // Load services
      const servicesResult = (await kernelRequest('system/services', {})) as SystemServicesResult;
      servicesData = servicesResult.services;
      renderServices(serviceFilter.value, serviceSearch.value);

      // Load processes
      const processesResult = (await kernelRequest('system/processes', { limit: 50 })) as SystemProcessesResult;
      renderProcesses(processesResult.processes);

      // Load containers
      const containersResult = (await kernelRequest('system/containers', {})) as SystemContainersResult;
      renderContainers(containersResult.containers);

    } catch (e) {
      summaryBody.innerHTML = `<div style="color: #ef4444;">Error loading data: ${String(e)}</div>`;
    }
  }

  // Event handlers
  serviceFilter.addEventListener('change', () => {
    renderServices(serviceFilter.value, serviceSearch.value);
  });

  serviceSearch.addEventListener('input', () => {
    renderServices(serviceFilter.value, serviceSearch.value);
  });

  refreshBtn.addEventListener('click', () => {
    refreshBtn.textContent = 'Refreshing...';
    refreshBtn.disabled = true;
    void loadData().finally(() => {
      refreshBtn.textContent = 'Refresh';
      refreshBtn.disabled = false;
    });
  });

  // Initial load
  void loadData();
}

buildUi();
