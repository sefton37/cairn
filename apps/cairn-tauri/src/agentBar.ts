/**
 * Agent Bar — vertical sidebar for switching between agent views.
 *
 * Core agents: CAIRN, ReOS, RIVA
 * Below: user-created agents (populated from RIVA, future)
 * Bottom: Settings button
 */

import { el } from './dom';

export type AgentId = 'play' | 'cairn' | 'reos' | 'riva';

interface AgentBarCallbacks {
  onSwitchAgent: (id: AgentId) => void;
  onOpenSettings: () => void;
}

interface AgentEntry {
  id: AgentId;
  label: string;
  icon: string;
  description: string;
}

const CORE_AGENTS: AgentEntry[] = [
  { id: 'play', label: 'The Play', icon: '\u{1F3AD}', description: 'Life organization' },
  { id: 'cairn', label: 'CAIRN', icon: '\u{1F9ED}', description: 'Attention minder' },
  { id: 'reos', label: 'ReOS', icon: '\u{1F5A5}\uFE0F', description: 'System control' },
  { id: 'riva', label: 'RIVA', icon: '\u{1F4CB}', description: 'Agent orchestrator' },
];

export function createAgentBar(callbacks: AgentBarCallbacks) {
  let activeId: AgentId = 'cairn';

  const bar = el('div');
  bar.className = 'agent-bar';
  bar.style.cssText = `
    width: 180px;
    min-width: 180px;
    background: rgba(0, 0, 0, 0.15);
    border-right: 1px solid rgba(255, 255, 255, 0.08);
    display: flex;
    flex-direction: column;
    padding: 12px 8px;
    gap: 4px;
    overflow-y: auto;
  `;

  // Title
  const title = el('div');
  title.textContent = 'Talking Rock';
  title.style.cssText = `
    font-weight: 600;
    font-size: 13px;
    color: rgba(255, 255, 255, 0.9);
    padding: 4px 8px 12px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    margin-bottom: 8px;
  `;
  bar.appendChild(title);

  // Agent items
  const items: Map<AgentId, HTMLElement> = new Map();

  for (const agent of CORE_AGENTS) {
    const item = el('div');
    item.className = 'agent-item';
    item.dataset.agentId = agent.id;
    item.style.cssText = `
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 12px;
      border-radius: 8px;
      cursor: pointer;
      transition: background 0.15s;
      color: rgba(255, 255, 255, 0.7);
    `;

    item.innerHTML = `
      <span style="font-size: 18px; width: 24px; text-align: center;">${agent.icon}</span>
      <div style="flex: 1; min-width: 0;">
        <div style="font-size: 13px; font-weight: 500; color: inherit;">${agent.label}</div>
        <div style="font-size: 10px; color: rgba(255, 255, 255, 0.35); margin-top: 1px;">${agent.description}</div>
      </div>
    `;

    item.addEventListener('mouseenter', () => {
      if (agent.id !== activeId) {
        item.style.background = 'rgba(255, 255, 255, 0.06)';
      }
    });
    item.addEventListener('mouseleave', () => {
      if (agent.id !== activeId) {
        item.style.background = 'transparent';
      }
    });
    item.addEventListener('click', () => {
      if (agent.id !== activeId) {
        setActive(agent.id);
        callbacks.onSwitchAgent(agent.id);
      }
    });

    items.set(agent.id, item);
    bar.appendChild(item);
  }

  // Spacer + divider for future user agents
  const spacer = el('div');
  spacer.style.cssText = `
    flex: 1;
    min-height: 20px;
    border-top: 1px solid rgba(255, 255, 255, 0.05);
    margin-top: 8px;
    padding-top: 8px;
  `;

  const userAgentHint = el('div');
  userAgentHint.style.cssText = `
    font-size: 10px;
    color: rgba(255, 255, 255, 0.2);
    padding: 4px 12px;
  `;
  userAgentHint.textContent = 'User agents coming soon';
  spacer.appendChild(userAgentHint);
  bar.appendChild(spacer);

  // Settings button at bottom
  const settingsBtn = el('button');
  settingsBtn.innerHTML = '\u2699\uFE0F Settings';
  settingsBtn.style.cssText = `
    width: 100%;
    padding: 10px 12px;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 6px;
    color: rgba(255, 255, 255, 0.7);
    cursor: pointer;
    font-size: 12px;
    text-align: left;
    transition: background 0.15s;
  `;
  settingsBtn.addEventListener('mouseenter', () => {
    settingsBtn.style.background = 'rgba(255, 255, 255, 0.1)';
  });
  settingsBtn.addEventListener('mouseleave', () => {
    settingsBtn.style.background = 'rgba(255, 255, 255, 0.05)';
  });
  settingsBtn.addEventListener('click', () => callbacks.onOpenSettings());
  bar.appendChild(settingsBtn);

  function setActive(id: AgentId) {
    activeId = id;
    for (const [agentId, item] of items) {
      if (agentId === id) {
        item.style.background = 'rgba(59, 130, 246, 0.15)';
        item.style.color = 'rgba(255, 255, 255, 0.95)';
      } else {
        item.style.background = 'transparent';
        item.style.color = 'rgba(255, 255, 255, 0.7)';
      }
    }
  }

  // Initial state
  setActive('cairn');

  return {
    element: bar,
    setActive,
  };
}
