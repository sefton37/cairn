/**
 * ReOS View — System dashboard + terminal for natural language Linux.
 *
 * Split-screen layout:
 *   Left:  Scrollable system dashboard with live vitals (CPU, RAM, disk, etc.)
 *   Right: Terminal placeholder (PTY integration in Phase 2)
 *
 * The dashboard polls reos/vitals every 5 seconds via JSON-RPC.
 */

import { el } from './dom';

// ── Types ──────────────────────────────────────────────────────────────

interface NetworkInterface {
  name: string;
  state: string;
  mac: string | null;
  addresses: Array<{ family: string; address: string; prefix?: number }>;
  rx_bytes?: number;
  tx_bytes?: number;
  rx_packets?: number;
  tx_packets?: number;
  rx_errors?: number;
  tx_errors?: number;
}

interface ContainerItem {
  id: string;
  image: string;
  status: string;
  name: string;
  runtime: string;
}

interface ContainerInfo {
  runtime: string;
  items: ContainerItem[];
}

interface ReosVitals {
  hostname: string;
  kernel: string;
  distro: string;
  uptime: string;
  cpu_model: string;
  cpu_cores: number;
  cpu_percent: number;
  memory_total_mb: number;
  memory_used_mb: number;
  memory_percent: number;
  disk_total_gb: number;
  disk_used_gb: number;
  disk_percent: number;
  load_avg: [number, number, number];
  gpu_name: string | null;
  gpu_percent: number | null;
  gpu_memory_used_mb: number | null;
  gpu_memory_total_mb: number | null;
  network: NetworkInterface[];
  containers: ContainerInfo | null;
}

interface ReosViewCallbacks {
  kernelRequest: (method: string, params: unknown) => Promise<unknown>;
}

// ── Helpers ────────────────────────────────────────────────────────────

function formatBytes(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${Math.round(mb)} MB`;
}

function formatRawBytes(bytes: number): string {
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

function percentColor(pct: number): string {
  if (pct >= 90) return '#ef4444';  // red
  if (pct >= 70) return '#f59e0b';  // amber
  return '#22c55e';                 // green
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

// ── Dashboard Panel Builder ────────────────────────────────────────────

function makePanel(title: string, icon: string): {
  panel: HTMLElement;
  body: HTMLElement;
} {
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

// ── View Factory ───────────────────────────────────────────────────────

export function createReosView(callbacks: ReosViewCallbacks): {
  container: HTMLElement;
  startPolling: () => void;
  stopPolling: () => void;
} {
  let pollTimer: ReturnType<typeof setTimeout> | null = null;
  let isPolling = false;

  // ── Main Container (split-screen) ──
  const container = el('div');
  container.className = 'reos-view';
  container.style.cssText = `
    flex: 1;
    display: flex;
    height: 100%;
    min-height: 0;
    overflow: hidden;
  `;

  // ── LEFT: System Dashboard ──
  const dashboard = el('div');
  dashboard.className = 'reos-dashboard';
  dashboard.style.cssText = `
    width: 50%;
    min-width: 360px;
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    border-right: 1px solid rgba(255,255,255,0.1);
    background: rgba(0,0,0,0.1);
  `;

  // Dashboard header
  const dashHeader = el('div');
  dashHeader.style.cssText = `
    padding: 16px 20px;
    border-bottom: 1px solid rgba(255,255,255,0.1);
    background: rgba(0,0,0,0.2);
    display: flex;
    align-items: center;
    justify-content: space-between;
  `;

  const dashTitle = el('div');
  dashTitle.style.cssText = 'font-size: 16px; font-weight: 600; color: #fff; display: flex; align-items: center; gap: 8px;';
  dashTitle.textContent = '\u{1F5A5}\uFE0F System Dashboard';

  const dashStatus = el('div');
  dashStatus.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.4);';
  dashStatus.textContent = 'Waiting for kernel...';

  dashHeader.appendChild(dashTitle);
  dashHeader.appendChild(dashStatus);

  // Scrollable dashboard body
  const dashBody = el('div');
  dashBody.style.cssText = `
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  `;

  // ── System Info Panel ──
  const { panel: infoPanel, body: infoBody } = makePanel('System', '\u{2139}\uFE0F');

  // ── CPU Panel ──
  const { panel: cpuPanel, body: cpuBody } = makePanel('Processor', '\u{26A1}');

  // ── Memory Panel ──
  const { panel: memPanel, body: memBody } = makePanel('Memory', '\u{1F4BE}');

  // ── Disk Panel ──
  const { panel: diskPanel, body: diskBody } = makePanel('Disk', '\u{1F4BF}');

  // ── GPU Panel (conditional) ──
  const { panel: gpuPanel, body: gpuBody } = makePanel('GPU', '\u{1F3AE}');
  gpuPanel.style.display = 'none';

  // ── Load Panel ──
  const { panel: loadPanel, body: loadBody } = makePanel('Load Average', '\u{1F4CA}');

  // ── Network Panel ──
  const { panel: netPanel, body: netBody } = makePanel('Network', '\u{1F310}');

  // ── Containers Panel (conditional) ──
  const { panel: containerPanel, body: containerBody } = makePanel('Containers', '\u{1F4E6}');
  containerPanel.style.display = 'none';

  dashBody.appendChild(infoPanel);
  dashBody.appendChild(cpuPanel);
  dashBody.appendChild(memPanel);
  dashBody.appendChild(diskPanel);
  dashBody.appendChild(gpuPanel);
  dashBody.appendChild(loadPanel);
  dashBody.appendChild(netPanel);
  dashBody.appendChild(containerPanel);

  dashboard.appendChild(dashHeader);
  dashboard.appendChild(dashBody);

  // ── RIGHT: Terminal Placeholder ──
  const terminal = el('div');
  terminal.className = 'reos-terminal';
  terminal.style.cssText = `
    flex: 1;
    display: flex;
    flex-direction: column;
    background: #0d1117;
    overflow: hidden;
  `;

  // Terminal header
  const termHeader = el('div');
  termHeader.style.cssText = `
    padding: 12px 20px;
    border-bottom: 1px solid rgba(255,255,255,0.1);
    background: rgba(0,0,0,0.3);
    display: flex;
    align-items: center;
    gap: 8px;
  `;

  const termTitle = el('div');
  termTitle.style.cssText = 'font-size: 14px; font-weight: 600; color: rgba(255,255,255,0.8);';
  termTitle.textContent = '\u{1F4BB} Terminal';

  const termBadge = el('div');
  termBadge.style.cssText = `
    font-size: 10px;
    padding: 2px 8px;
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 10px;
    color: rgba(255,255,255,0.4);
  `;
  termBadge.textContent = 'Phase 2 \u2014 PTY';

  termHeader.appendChild(termTitle);
  termHeader.appendChild(termBadge);

  // Terminal body (placeholder)
  const termBody = el('div');
  termBody.style.cssText = `
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    color: rgba(255,255,255,0.3);
    font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
    font-size: 13px;
    padding: 40px;
    text-align: center;
  `;

  const termPrompt = el('div');
  termPrompt.style.cssText = 'font-size: 32px; opacity: 0.3;';
  termPrompt.textContent = '$_';

  const termDesc = el('div');
  termDesc.style.cssText = 'max-width: 320px; line-height: 1.6;';
  termDesc.textContent = 'Full PTY terminal with natural language Linux commands. Type commands or ask in plain English.';

  termBody.appendChild(termPrompt);
  termBody.appendChild(termDesc);

  terminal.appendChild(termHeader);
  terminal.appendChild(termBody);

  container.appendChild(dashboard);
  container.appendChild(terminal);

  // ── Vitals Update Logic ──

  function updateVitals(v: ReosVitals): void {
    // System info
    infoBody.innerHTML = '';
    infoBody.appendChild(makeStatRow('Hostname', v.hostname));
    infoBody.appendChild(makeStatRow('Distro', v.distro));
    infoBody.appendChild(makeStatRow('Kernel', v.kernel));
    infoBody.appendChild(makeStatRow('Uptime', v.uptime));

    // CPU
    cpuBody.innerHTML = '';
    cpuBody.appendChild(makeStatRow('Model', v.cpu_model.length > 40 ? v.cpu_model.substring(0, 40) + '\u2026' : v.cpu_model));
    cpuBody.appendChild(makeStatRow('Cores', String(v.cpu_cores)));
    cpuBody.appendChild(makeStatRow('Usage', `${v.cpu_percent.toFixed(1)}%`, makeBar(v.cpu_percent)));

    // Memory
    memBody.innerHTML = '';
    memBody.appendChild(makeStatRow(
      'Used',
      `${formatBytes(v.memory_used_mb)} / ${formatBytes(v.memory_total_mb)}`,
      makeBar(v.memory_percent),
    ));
    memBody.appendChild(makeStatRow('Percent', `${v.memory_percent.toFixed(1)}%`));

    // Disk
    diskBody.innerHTML = '';
    diskBody.appendChild(makeStatRow(
      'Root (/)',
      `${v.disk_used_gb.toFixed(1)} / ${v.disk_total_gb.toFixed(1)} GB`,
      makeBar(v.disk_percent),
    ));
    diskBody.appendChild(makeStatRow('Percent', `${v.disk_percent.toFixed(1)}%`));

    // GPU (show only if present)
    if (v.gpu_name) {
      gpuPanel.style.display = '';
      gpuBody.innerHTML = '';
      gpuBody.appendChild(makeStatRow('Model', v.gpu_name));
      if (v.gpu_percent !== null) {
        gpuBody.appendChild(makeStatRow('Usage', `${v.gpu_percent.toFixed(1)}%`, makeBar(v.gpu_percent)));
      }
      if (v.gpu_memory_used_mb !== null && v.gpu_memory_total_mb !== null) {
        const gpuMemPct = v.gpu_memory_total_mb > 0 ? (v.gpu_memory_used_mb / v.gpu_memory_total_mb) * 100 : 0;
        gpuBody.appendChild(makeStatRow(
          'VRAM',
          `${formatBytes(v.gpu_memory_used_mb)} / ${formatBytes(v.gpu_memory_total_mb)}`,
          makeBar(gpuMemPct),
        ));
      }
    } else {
      gpuPanel.style.display = 'none';
    }

    // Load average
    loadBody.innerHTML = '';
    const [l1, l5, l15] = v.load_avg;
    const loadPct = v.cpu_cores > 0 ? Math.min((l1 / v.cpu_cores) * 100, 100) : 0;
    loadBody.appendChild(makeStatRow('1 min', l1.toFixed(2), makeBar(loadPct)));
    loadBody.appendChild(makeStatRow('5 min', l5.toFixed(2)));
    loadBody.appendChild(makeStatRow('15 min', l15.toFixed(2)));

    // Network interfaces
    netBody.innerHTML = '';
    if (v.network && v.network.length > 0) {
      for (const iface of v.network) {
        const stateColor = iface.state === 'UP' ? '#22c55e' : 'rgba(255,255,255,0.3)';
        const ipv4 = iface.addresses.find(a => a.family === 'inet');
        const addrStr = ipv4 ? ipv4.address : 'no address';

        const ifaceHeader = el('div');
        ifaceHeader.style.cssText = `
          display: flex; align-items: center; gap: 8px;
          padding: 4px 0; font-size: 13px;
          ${iface !== v.network[0] ? 'margin-top: 8px; border-top: 1px solid rgba(255,255,255,0.04); padding-top: 8px;' : ''}
        `;
        const dot = el('span');
        dot.style.cssText = `width: 6px; height: 6px; border-radius: 50%; background: ${stateColor}; flex-shrink: 0;`;
        const nameEl = el('span');
        nameEl.style.cssText = 'font-weight: 600; color: rgba(255,255,255,0.8);';
        nameEl.textContent = iface.name;
        const addrEl = el('span');
        addrEl.style.cssText = 'color: rgba(255,255,255,0.5); margin-left: auto; font-variant-numeric: tabular-nums;';
        addrEl.textContent = addrStr;
        ifaceHeader.appendChild(dot);
        ifaceHeader.appendChild(nameEl);
        ifaceHeader.appendChild(addrEl);
        netBody.appendChild(ifaceHeader);

        if (iface.rx_bytes !== undefined && iface.tx_bytes !== undefined) {
          netBody.appendChild(makeStatRow('RX', formatRawBytes(iface.rx_bytes)));
          netBody.appendChild(makeStatRow('TX', formatRawBytes(iface.tx_bytes)));
          if (iface.rx_errors && iface.rx_errors > 0) {
            netBody.appendChild(makeStatRow('RX Errors', String(iface.rx_errors)));
          }
          if (iface.tx_errors && iface.tx_errors > 0) {
            netBody.appendChild(makeStatRow('TX Errors', String(iface.tx_errors)));
          }
        }
      }
    } else {
      const noNet = el('div');
      noNet.style.cssText = 'font-size: 12px; color: rgba(255,255,255,0.3); padding: 4px 0;';
      noNet.textContent = 'No network interfaces detected';
      netBody.appendChild(noNet);
    }

    // Containers
    if (v.containers && v.containers.items.length > 0) {
      containerPanel.style.display = '';
      containerBody.innerHTML = '';

      const runtimeLabel = el('div');
      runtimeLabel.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.4); padding-bottom: 6px; text-transform: uppercase; letter-spacing: 0.05em;';
      runtimeLabel.textContent = `${v.containers.runtime} \u2022 ${v.containers.items.length} container${v.containers.items.length !== 1 ? 's' : ''}`;
      containerBody.appendChild(runtimeLabel);

      for (const ctr of v.containers.items) {
        const isRunning = ctr.status.toLowerCase().startsWith('up');
        const row = el('div');
        row.style.cssText = `
          display: flex; align-items: center; gap: 8px;
          padding: 5px 0; font-size: 13px;
          border-bottom: 1px solid rgba(255,255,255,0.03);
        `;

        const statusDot = el('span');
        statusDot.style.cssText = `
          width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
          background: ${isRunning ? '#22c55e' : '#6b7280'};
        `;
        const nameEl = el('span');
        nameEl.style.cssText = 'font-weight: 500; color: rgba(255,255,255,0.8); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;';
        nameEl.textContent = ctr.name;
        nameEl.title = `${ctr.name} (${ctr.image})`;
        const statusEl = el('span');
        statusEl.style.cssText = `margin-left: auto; flex-shrink: 0; font-size: 11px; color: ${isRunning ? 'rgba(34,197,94,0.7)' : 'rgba(255,255,255,0.3)'};`;
        statusEl.textContent = ctr.status;

        row.appendChild(statusDot);
        row.appendChild(nameEl);
        row.appendChild(statusEl);
        containerBody.appendChild(row);
      }
    } else {
      containerPanel.style.display = 'none';
    }

    // Update status indicator
    dashStatus.textContent = `Live \u2022 ${new Date().toLocaleTimeString()}`;
    dashStatus.style.color = 'rgba(34,197,94,0.7)';
  }

  // ── Polling ──

  async function pollVitals(): Promise<void> {
    try {
      const result = await callbacks.kernelRequest('reos/vitals', {});
      try {
        updateVitals(result as ReosVitals);
      } catch (renderErr) {
        console.error('[ReOS] Dashboard render error:', renderErr, 'Vitals data:', JSON.stringify(result).substring(0, 500));
        dashStatus.textContent = `Render error: ${renderErr instanceof Error ? renderErr.message : String(renderErr)}`;
        dashStatus.style.color = 'rgba(239,68,68,0.7)';
      }
    } catch (err) {
      console.error('[ReOS] Vitals poll error:', err);
      dashStatus.textContent = `Error: ${err instanceof Error ? err.message : String(err)}`;
      dashStatus.style.color = 'rgba(239,68,68,0.7)';
    }
  }

  function scheduleNextPoll(): void {
    if (!isPolling) return;
    pollTimer = setTimeout(async () => {
      await pollVitals();
      scheduleNextPoll();
    }, 5000);
  }

  function startPolling(): void {
    if (isPolling) return;
    isPolling = true;
    dashStatus.textContent = 'Fetching vitals...';
    dashStatus.style.color = 'rgba(255,255,255,0.4)';
    // First poll immediately
    void pollVitals().then(() => scheduleNextPoll());
  }

  function stopPolling(): void {
    isPolling = false;
    if (pollTimer !== null) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
  }

  return { container, startPolling, stopPolling };
}
