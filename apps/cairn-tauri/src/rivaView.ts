/**
 * RIVA View — placeholder for the agent orchestrator.
 *
 * Will eventually contain: project management, agent lifecycle
 * (create/edit/delete), documentation management, and agent configuration.
 */

import { el } from './dom';

export function createRivaView(): { container: HTMLElement } {
  const container = el('div');
  container.className = 'riva-view';
  container.style.cssText = `
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 16px;
    color: rgba(255, 255, 255, 0.7);
    padding: 40px;
  `;

  const icon = el('div');
  icon.textContent = '\u{1F4CB}';
  icon.style.fontSize = '48px';
  container.appendChild(icon);

  const title = el('div');
  title.textContent = 'RIVA — Agent Orchestrator';
  title.style.cssText = `
    font-size: 20px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.9);
  `;
  container.appendChild(title);

  const desc = el('div');
  desc.textContent = 'Manage projects, agents, and documentation.';
  desc.style.cssText = `
    font-size: 14px;
    color: rgba(255, 255, 255, 0.5);
    text-align: center;
    max-width: 400px;
  `;
  container.appendChild(desc);

  const badge = el('div');
  badge.textContent = 'Coming soon — Phase 1';
  badge.style.cssText = `
    font-size: 12px;
    padding: 6px 16px;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 20px;
    color: rgba(255, 255, 255, 0.4);
    margin-top: 8px;
  `;
  container.appendChild(badge);

  return { container };
}
