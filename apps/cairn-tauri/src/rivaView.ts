/**
 * RIVA View — Agent Orchestrator split-screen UI.
 *
 * Layout:
 *   Left:  Observatory — agent list, status badges, properties panel
 *   Right: Chat — conversation with RIVA, plan display, audit results
 *
 * Phase 1: structural shell with RIVA service connection status.
 * Panels are populated in later phases as backend endpoints are built.
 */

import { el } from './dom';
import { kernelRequest, KernelError } from './kernel';

// ── Types ──────────────────────────────────────────────────────────────

interface RivaStatus {
  status: string;
  uptime_seconds: number;
  version: string;
}

// ── State ──────────────────────────────────────────────────────────────

let statusPollTimer: number | null = null;

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

function createPaneHeader(title: string, extra?: HTMLElement): HTMLElement {
  const header = el('div');
  header.style.cssText = `
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    flex-shrink: 0;
  `;

  const titleEl = el('div');
  titleEl.textContent = title;
  titleEl.style.cssText = `
    font-size: 14px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.9);
    letter-spacing: 0.02em;
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
    color: rgba(255, 255, 255, 0.3);
    font-size: 13px;
    padding: 20px;
    text-align: center;
  `;
  container.textContent = message;
  return container;
}

// ── Panes ──────────────────────────────────────────────────────────────

function createObservatoryPane(): HTMLElement {
  const pane = el('div');
  pane.className = 'riva-observatory';
  pane.style.cssText = `
    flex: 1;
    display: flex;
    flex-direction: column;
    border-right: 1px solid rgba(255, 255, 255, 0.08);
    min-width: 0;
  `;

  pane.appendChild(createPaneHeader('Observatory'));
  pane.appendChild(createEmptyState('No agents yet.\nAgents will appear here once created.'));

  return pane;
}

function createChatPane(): HTMLElement {
  const pane = el('div');
  pane.className = 'riva-chat';
  pane.style.cssText = `
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
  `;

  pane.appendChild(createPaneHeader('RIVA'));
  pane.appendChild(createEmptyState('Ready.\nPlans, contracts, and audit results will appear here.'));

  return pane;
}

// ── Main ───────────────────────────────────────────────────────────────

export function createRivaView(): { container: HTMLElement; destroy?: () => void } {
  const container = el('div');
  container.className = 'riva-view';
  container.style.cssText = `
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  `;

  // Top bar with title and status
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
  titleRow.style.cssText = `
    display: flex;
    align-items: center;
    gap: 10px;
  `;

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
  subtitle.textContent = 'Agent Orchestrator';
  subtitle.style.cssText = `
    font-size: 12px;
    color: rgba(255, 255, 255, 0.4);
  `;
  titleRow.appendChild(subtitle);
  topBar.appendChild(titleRow);

  const statusBadge = createStatusBadge();
  topBar.appendChild(statusBadge);
  container.appendChild(topBar);

  // Split panes
  const splitContainer = el('div');
  splitContainer.style.cssText = `
    flex: 1;
    display: flex;
    overflow: hidden;
  `;

  splitContainer.appendChild(createObservatoryPane());
  splitContainer.appendChild(createChatPane());
  container.appendChild(splitContainer);

  // Start polling RIVA status
  async function checkStatus(): Promise<void> {
    try {
      const result = await kernelRequest('riva/status', {}) as RivaStatus;
      if (result && result.status === 'running') {
        setStatusBadge(statusBadge, 'connected');
      } else {
        setStatusBadge(statusBadge, 'offline');
      }
    } catch (err) {
      if (err instanceof KernelError && err.code === -32099) {
        setStatusBadge(statusBadge, 'offline');
      } else {
        setStatusBadge(statusBadge, 'offline');
      }
    }
  }

  checkStatus();
  statusPollTimer = window.setInterval(checkStatus, 10000);

  function destroy(): void {
    if (statusPollTimer !== null) {
      clearInterval(statusPollTimer);
      statusPollTimer = null;
    }
  }

  return { container, destroy };
}
