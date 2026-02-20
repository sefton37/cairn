/**
 * Context Overlay - Detailed view of context usage and source management
 *
 * Shows breakdown of what's consuming context and allows toggling sources.
 */

import { kernelRequest } from './kernel';
import { el, escapeHtml } from './dom';
import type { ContextStatsResult, ContextSource, ContextToggleResult } from './types';

interface ContextOverlay {
  element: HTMLElement;
  show: (conversationId: string | null) => void;
  hide: () => void;
}

export function createContextOverlay(onClose?: () => void): ContextOverlay {
  let currentConversationId: string | null = null;
  let stats: ContextStatsResult | null = null;

  // Create overlay container
  const overlay = el('div');
  overlay.className = 'context-overlay';
  overlay.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.8);
    display: none;
    z-index: 1000;
    justify-content: center;
    align-items: center;
  `;

  // Modal container
  const modal = el('div');
  modal.className = 'context-modal';
  modal.style.cssText = `
    width: 600px;
    max-width: 90vw;
    max-height: 85vh;
    background: #1e1e1e;
    border-radius: 12px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  `;

  // Header
  const header = el('div');
  header.style.cssText = `
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;
    border-bottom: 1px solid #333;
  `;

  const title = el('div');
  title.textContent = 'Context Usage';
  title.style.cssText = 'font-size: 18px; font-weight: 600; color: #fff;';

  const closeBtn = el('button');
  closeBtn.textContent = '✕';
  closeBtn.style.cssText = `
    background: none;
    border: none;
    color: rgba(255,255,255,0.6);
    font-size: 20px;
    cursor: pointer;
    padding: 4px 8px;
  `;
  closeBtn.addEventListener('click', hide);

  header.appendChild(title);
  header.appendChild(closeBtn);

  // Content area
  const content = el('div');
  content.className = 'context-content';
  content.style.cssText = `
    flex: 1;
    overflow: auto;
    padding: 20px;
  `;

  modal.appendChild(header);
  modal.appendChild(content);
  overlay.appendChild(modal);

  // Close on backdrop click
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) hide();
  });

  // Close on Escape
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && overlay.style.display === 'flex') hide();
  });

  function show(conversationId: string | null) {
    currentConversationId = conversationId;
    overlay.style.display = 'flex';
    void loadData();
  }

  function hide() {
    overlay.style.display = 'none';
    onClose?.();
  }

  async function loadData() {
    try {
      stats = await kernelRequest('context/stats', {
        conversation_id: currentConversationId,
        include_breakdown: true,
      }) as ContextStatsResult;
      render();
    } catch (e) {
      content.innerHTML = `<div style="color: #ef4444;">Failed to load context stats: ${escapeHtml(e instanceof Error ? e.message : 'Unknown error')}</div>`;
    }
  }

  function render() {
    if (!stats) return;

    content.innerHTML = '';

    // Summary section
    const summary = el('div');
    summary.style.cssText = `
      background: rgba(0,0,0,0.3);
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 20px;
    `;

    // Overall usage gauge
    const usageColor = stats.warning_level === 'critical' ? '#ef4444' :
                       stats.warning_level === 'warning' ? '#f59e0b' : '#22c55e';

    summary.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
        <div>
          <div style="font-size: 14px; color: rgba(255,255,255,0.7);">Total Context Usage</div>
          <div style="font-size: 32px; font-weight: 600; color: ${usageColor};">${Math.round(stats.usage_percent)}%</div>
        </div>
        <div style="text-align: right;">
          <div style="font-size: 12px; color: rgba(255,255,255,0.5);">
            ${stats.estimated_tokens.toLocaleString()} / ${(stats.context_limit - stats.reserved_tokens).toLocaleString()} tokens
          </div>
          <div style="font-size: 12px; color: rgba(255,255,255,0.5);">
            ${stats.available_tokens.toLocaleString()} available
          </div>
        </div>
      </div>
      <div style="height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden;">
        <div style="height: 100%; width: ${Math.min(100, stats.usage_percent)}%; background: ${usageColor}; border-radius: 4px;"></div>
      </div>
      <div style="margin-top: 8px; font-size: 11px; color: rgba(255,255,255,0.4);">
        Model context limit: ${stats.context_limit.toLocaleString()} tokens (${stats.reserved_tokens.toLocaleString()} reserved for response)
      </div>
    `;
    content.appendChild(summary);

    // Sources section
    const sourcesHeader = el('div');
    sourcesHeader.textContent = 'Context Sources';
    sourcesHeader.style.cssText = `
      font-size: 14px;
      font-weight: 600;
      color: #fff;
      margin-bottom: 12px;
    `;
    content.appendChild(sourcesHeader);

    const sourcesHelp = el('div');
    sourcesHelp.textContent = 'Toggle sources to free up context. Disabled sources will not be included in conversations.';
    sourcesHelp.style.cssText = `
      font-size: 12px;
      color: rgba(255,255,255,0.5);
      margin-bottom: 16px;
    `;
    content.appendChild(sourcesHelp);

    // Source cards
    if (stats.sources && stats.sources.length > 0) {
      const sourceList = el('div');
      sourceList.style.cssText = 'display: flex; flex-direction: column; gap: 12px;';

      for (const source of stats.sources) {
        const card = createSourceCard(source);
        sourceList.appendChild(card);
      }

      content.appendChild(sourceList);
    } else {
      // No sources returned - likely backend hasn't been restarted
      const noSourcesInfo = el('div');
      noSourcesInfo.style.cssText = `
        background: rgba(255,200,100,0.1);
        border: 1px solid rgba(255,200,100,0.3);
        border-radius: 8px;
        padding: 16px;
        text-align: center;
      `;
      noSourcesInfo.innerHTML = `
        <div style="font-size: 24px; margin-bottom: 8px;">⚠️</div>
        <div style="color: #f59e0b; margin-bottom: 8px;">Source breakdown not available</div>
        <div style="font-size: 12px; color: rgba(255,255,255,0.5);">
          Please restart the app to enable detailed context tracking.
        </div>
      `;
      content.appendChild(noSourcesInfo);
    }
  }

  function createSourceCard(source: ContextSource): HTMLElement {
    const card = el('div');
    card.style.cssText = `
      background: rgba(255,255,255,0.03);
      border: 1px solid ${source.enabled ? '#333' : 'rgba(255,255,255,0.1)'};
      border-radius: 8px;
      padding: 14px;
      opacity: ${source.enabled ? '1' : '0.6'};
      transition: all 0.2s;
    `;

    // Get color for this source
    const colors: Record<string, string> = {
      'system_prompt': '#3b82f6',
      'play_context': '#8b5cf6',
      'learned_kb': '#22c55e',
      'system_state': '#f59e0b',
      'messages': '#ec4899',
    };
    const color = colors[source.name] || '#6b7280';

    // Header row with toggle
    const headerRow = el('div');
    headerRow.style.cssText = `
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 10px;
    `;

    const nameSection = el('div');
    nameSection.innerHTML = `
      <div style="font-size: 14px; font-weight: 500; color: #fff;">${escapeHtml(source.display_name)}</div>
      <div style="font-size: 11px; color: rgba(255,255,255,0.5);">${escapeHtml(source.description)}</div>
    `;

    // Toggle switch
    const toggle = el('button');
    const isMessages = source.name === 'messages';
    toggle.style.cssText = `
      width: 44px;
      height: 24px;
      border-radius: 12px;
      border: none;
      background: ${source.enabled ? color : 'rgba(255,255,255,0.2)'};
      cursor: ${isMessages ? 'not-allowed' : 'pointer'};
      position: relative;
      transition: background 0.2s;
      opacity: ${isMessages ? '0.5' : '1'};
    `;

    const toggleKnob = el('div');
    toggleKnob.style.cssText = `
      position: absolute;
      top: 2px;
      left: ${source.enabled ? '22px' : '2px'};
      width: 20px;
      height: 20px;
      border-radius: 50%;
      background: #fff;
      transition: left 0.2s;
    `;
    toggle.appendChild(toggleKnob);

    if (!isMessages) {
      toggle.addEventListener('click', async () => {
        const newEnabled = !source.enabled;
        toggle.style.background = newEnabled ? color : 'rgba(255,255,255,0.2)';
        toggleKnob.style.left = newEnabled ? '22px' : '2px';
        card.style.opacity = newEnabled ? '1' : '0.6';

        try {
          await kernelRequest('context/toggle_source', {
            source_name: source.name,
            enabled: newEnabled,
          }) as ContextToggleResult;
          source.enabled = newEnabled;
          // Reload to get updated stats
          await loadData();
        } catch (e) {
          // Revert on error
          toggle.style.background = source.enabled ? color : 'rgba(255,255,255,0.2)';
          toggleKnob.style.left = source.enabled ? '22px' : '2px';
          card.style.opacity = source.enabled ? '1' : '0.6';
          console.error('Failed to toggle source:', e);
        }
      });
    }
    toggle.title = isMessages ? 'Conversation cannot be disabled' : (source.enabled ? 'Click to disable' : 'Click to enable');

    headerRow.appendChild(nameSection);
    headerRow.appendChild(toggle);
    card.appendChild(headerRow);

    // Usage bar
    const usageRow = el('div');
    usageRow.style.cssText = `
      display: flex;
      align-items: center;
      gap: 12px;
    `;

    const barContainer = el('div');
    barContainer.style.cssText = `
      flex: 1;
      height: 6px;
      background: rgba(255,255,255,0.1);
      border-radius: 3px;
      overflow: hidden;
    `;

    const barFill = el('div');
    barFill.style.cssText = `
      height: 100%;
      width: ${Math.min(100, source.percent)}%;
      background: ${source.enabled ? color : 'rgba(255,255,255,0.3)'};
      border-radius: 3px;
      transition: width 0.3s;
    `;
    barContainer.appendChild(barFill);

    const statsText = el('div');
    statsText.style.cssText = `
      font-size: 12px;
      font-family: monospace;
      color: rgba(255,255,255,0.7);
      min-width: 100px;
      text-align: right;
    `;
    statsText.innerHTML = `
      <span style="color: ${source.enabled ? color : 'rgba(255,255,255,0.4)'};">${source.percent.toFixed(1)}%</span>
      <span style="color: rgba(255,255,255,0.4);">(${source.tokens.toLocaleString()})</span>
    `;

    usageRow.appendChild(barContainer);
    usageRow.appendChild(statsText);
    card.appendChild(usageRow);

    return card;
  }

  return {
    element: overlay,
    show,
    hide,
  };
}
