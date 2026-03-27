/**
 * Cairn Desktop Application - Personal Attention Minder
 *
 * Main entry point for the Tauri-based desktop UI.
 * Communicates with the Python kernel via JSON-RPC over stdio.
 */
import { open as openDialog } from '@tauri-apps/plugin-dialog';

import './style.css';
import { initTheme } from './themes';

// Modular imports
import {
  kernelRequest,
  KernelError,
  AuthenticationError,
  isAuthenticated,
  validateSession,
  logout,
  getSessionUsername,
  getSessionToken,
} from './kernel';
import { checkSessionOrLogin, showLockOverlay } from './lockScreen';
import { el, escapeHtml, rowHeader, label, textInput, textArea, smallButton } from './dom';
import { createPlayOverlay } from './playOverlay';
import { createSettingsOverlay } from './settingsOverlay';
import { createContextOverlay } from './contextOverlay';
import { createCairnView } from './cairnView';
import { createAgentBar } from './agentBar';
import type { AgentId } from './agentBar';
import { createReosView } from './reosView';
import { createRivaView } from './rivaView';
import { createCopperView } from './copperView';

import { buildPlayWindow } from './playWindow';
import type {
  ChatRespondResult,
  SystemLiveStateResult,
  PlayMeReadResult,
  PlayActsListResult,
  PlayScenesListResult,
  PlayActsCreateResult,
  PlayKbListResult,
  PlayKbReadResult,
  PlayKbWritePreviewResult,
  PlayKbWriteApplyResult,
  ApprovalPendingResult,
  ApprovalRespondResult,
  ApprovalExplainResult,
  ContextStatsResult,
} from './types';

function buildUi() {
  const query = new URLSearchParams(window.location.search);
  if (query.get('view') === 'me') {
    void buildMeWindow();
    return;
  }
  if (query.get('view') === 'dashboard') {
    void buildDashboardWindow();
    return;
  }
  if (query.get('view') === 'play') {
    void buildPlayWindow();
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

  // ============ View Router ============
  // Tracks which agent view is currently displayed
  let currentAgentView: AgentId = 'cairn';

  // ============ Context Meter + Health (inserted into CAIRN chat header) ============
  const navContextMeter = el('div');
  navContextMeter.className = 'nav-context-meter';
  navContextMeter.title = 'Click to view context details';
  navContextMeter.style.cssText = `
    flex: 1;
    padding: 6px 10px;
    background: rgba(0, 0, 0, 0.2);
    border-radius: 6px;
    cursor: pointer;
    transition: background 0.2s;
  `;

  const contextUsageBar = el('div');
  contextUsageBar.style.cssText = `
    height: 4px;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 2px;
    overflow: hidden;
    margin-bottom: 4px;
  `;

  const contextUsageFill = el('div');
  contextUsageFill.style.cssText = `
    height: 100%;
    width: 0%;
    background: #22c55e;
    border-radius: 2px;
    transition: width 0.3s, background 0.3s;
  `;
  contextUsageBar.appendChild(contextUsageFill);

  const contextUsageLabel = el('div');
  contextUsageLabel.style.cssText = `
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 10px;
    color: rgba(255, 255, 255, 0.6);
  `;
  contextUsageLabel.innerHTML = `
    <span>\u{1F9E0} Context</span>
    <span class="context-usage-value">Loading...</span>
  `;

  navContextMeter.appendChild(contextUsageBar);
  navContextMeter.appendChild(contextUsageLabel);

  // Update context meter periodically
  let lastContextMeterUpdate = 0;
  async function updateNavContextMeter() {
    try {
      const stats = await kernelRequest('context/stats', {
        conversation_id: currentConversationId,
      }) as ContextStatsResult;

      const percent = Math.min(100, stats.usage_percent);
      const color = stats.warning_level === 'critical' ? '#ef4444' :
                    stats.warning_level === 'warning' ? '#f59e0b' : '#22c55e';

      contextUsageFill.style.width = `${percent}%`;
      contextUsageFill.style.background = color;

      const valueEl = contextUsageLabel.querySelector('.context-usage-value');
      if (valueEl) {
        valueEl.textContent = `${Math.round(percent)}% • ${stats.available_tokens.toLocaleString()} left`;
        (valueEl as HTMLElement).style.color = color;
      }
    } catch {
      // Silently fail - context stats may not be available
    }
  }

  // Poll context every 30s
  setInterval(() => {
    const now = Date.now();
    if (now - lastContextMeterUpdate > 30000) {
      lastContextMeterUpdate = now;
      void updateNavContextMeter();
    }
  }, 5000);

  // Initial load
  setTimeout(() => void updateNavContextMeter(), 1000);

  navContextMeter.addEventListener('mouseenter', () => {
    navContextMeter.style.background = 'rgba(0, 0, 0, 0.3)';
  });
  navContextMeter.addEventListener('mouseleave', () => {
    navContextMeter.style.background = 'rgba(0, 0, 0, 0.2)';
  });

  // Note: Click handler to open contextOverlay is added after contextOverlay is created

  // navContextMeter and healthIndicator will be inserted into cairnView after creation
  // Health Pulse indicator (hidden by default, appears when findings exist)
  const healthIndicator = el('div');
  healthIndicator.className = 'health-indicator';
  healthIndicator.style.display = 'none';
  healthIndicator.style.cssText = `
    display: none;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    margin-top: 8px;
    margin-bottom: 4px;
    background: rgba(0, 0, 0, 0.2);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 8px;
    cursor: pointer;
    font-size: 12px;
    color: rgba(255, 255, 255, 0.8);
    transition: background 0.2s;
  `;
  healthIndicator.addEventListener('mouseenter', () => {
    healthIndicator.style.background = 'rgba(0, 0, 0, 0.3)';
  });
  healthIndicator.addEventListener('mouseleave', () => {
    healthIndicator.style.background = 'rgba(0, 0, 0, 0.2)';
  });
  healthIndicator.addEventListener('click', () => {
    void (async () => {
      try {
        const data = (await kernelRequest('health/findings', {})) as {
          findings: Array<{ severity: string; title: string; details: string }>;
          finding_count: number;
          overall_severity: string;
        };
        const findings = data.findings || [];
        if (findings.length === 0) {
          cairnView.addChatMessage('assistant', 'All Clear — No health findings.');
          return;
        }
        const prefix: Record<string, string> = { critical: '[CRITICAL]', warning: '[WARNING]' };
        const lines = [`**Health Check — ${findings.length} finding(s)**\n`];
        for (const f of findings) {
          lines.push(`${prefix[f.severity] || '[WARNING]'} **${f.title}**`);
          if (f.details) lines.push(`  ${f.details}`);
          lines.push('');
        }
        cairnView.addChatMessage('assistant', lines.join('\n').trim());
      } catch (err) {
        cairnView.addChatMessage('assistant', `Error loading health findings: ${err instanceof Error ? err.message : 'Unknown error'}`);
      }
    })();
  });

  const healthDot = el('span');
  healthDot.className = 'health-dot';
  healthDot.style.cssText = `
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  `;

  const healthText = el('span');
  healthText.className = 'health-text';

  healthIndicator.appendChild(healthDot);
  healthIndicator.appendChild(healthText);
  // healthIndicator will be placed alongside navContextMeter in cairnView

  // Health status polling
  async function refreshHealthStatus(): Promise<void> {
    try {
      const status = (await kernelRequest('health/status', {})) as {
        overall_severity: string;
        finding_count: number;
        unacknowledged_count: number;
      };

      if (status.finding_count > 0) {
        healthIndicator.style.display = 'flex';
        healthText.textContent = `${status.finding_count} health finding${status.finding_count === 1 ? '' : 's'}`;

        // Set dot color based on severity
        const colors: Record<string, string> = {
          critical: '#ef4444',
          warning: '#f59e0b',
          healthy: '#22c55e',
        };
        healthDot.style.background = colors[status.overall_severity] || colors.healthy;

        // Pulse animation for critical
        if (status.overall_severity === 'critical') {
          healthDot.style.animation = 'healthPulse 2s ease-in-out infinite';
        } else {
          healthDot.style.animation = 'none';
        }
      } else {
        healthIndicator.style.display = 'none';
      }
    } catch {
      // Silently ignore health polling errors
    }
  }

  // Poll health every 60s, piggyback on activity tracking
  function scheduleHealthPoll(): void {
    const isIdle = Date.now() - lastActivityTime > IDLE_THRESHOLD;
    const interval = isIdle ? 120000 : 60000;  // 2min idle, 1min active
    setTimeout(() => {
      void refreshHealthStatus().then(scheduleHealthPoll);
    }, interval);
  }
  // Initial health check after 5s delay
  setTimeout(() => {
    void refreshHealthStatus().then(scheduleHealthPoll);
  }, 5000);

  // (The Play button is now in the agent bar)

  // ============ CAIRN View (Conversational) ============
  const cairnView = createCairnView({
    onSendMessage: async (message: string) => {
      return handleCairnMessage(message);
    },
    kernelRequest,
    onDismissCard: (item) => {
      // Propose a rule to Cairn in chat
      let description: string;
      if (item.entity_type === 'email') {
        const who = item.sender_name || item.sender_email || 'this sender';
        description = `I dismissed the email "${item.title}" from ${who}. Should I create a rule to always dismiss emails like this?`;
      } else {
        description = `I dismissed "${item.title}" from my attention. Should I create a rule to deprioritize items like this?`;
      }
      // Send as a user message so Cairn can respond with a rule proposal
      void handleCairnMessage(description);
      cairnView.addChatMessage('user', description);
    },
  });

  // Load attention items at startup for "What Needs My Attention" section (next 7 days)
  // Returns a promise so the greeting can wait for this to complete (avoids DB lock contention)
  const attentionLoaded = (async () => {
    try {
      const result = await kernelRequest('cairn/attention', { hours: 168, limit: 50 }) as {
        count: number;
        items: Array<{
          entity_type: string;
          entity_id: string;
          title: string;
          reason: string;
          urgency: string;
          calendar_start?: string;
          calendar_end?: string;
          is_recurring?: boolean;
          recurrence_frequency?: string;
          next_occurrence?: string;
          act_id?: string;
          scene_id?: string;
          act_title?: string;
          act_color?: string;
          user_priority?: number;
          sender_name?: string | null;
          sender_email?: string | null;
          account_email?: string | null;
          email_date?: string | null;
          importance_score?: number | null;
          importance_reason?: string | null;
          email_message_id?: number | null;
          is_read?: boolean | null;
          learned_boost?: number | null;
          boost_reasons?: string[] | null;
        }>;
      };
      if (result.items && result.items.length > 0) {
        cairnView.updateSurfaced(result.items.map(item => ({
          title: item.title,
          reason: item.reason,
          urgency: item.urgency,
          is_recurring: item.is_recurring,
          recurrence_frequency: item.recurrence_frequency,
          next_occurrence: item.next_occurrence,
          entity_type: item.entity_type,
          entity_id: item.entity_id,
          act_id: item.act_id,
          scene_id: item.scene_id,
          act_title: item.act_title,
          act_color: item.act_color,
          user_priority: item.user_priority,
          sender_name: item.sender_name,
          sender_email: item.sender_email,
          account_email: item.account_email,
          email_date: item.email_date,
          importance_score: item.importance_score,
          importance_reason: item.importance_reason,
          email_message_id: item.email_message_id,
          is_read: item.is_read,
          learned_boost: item.learned_boost,
          boost_reasons: item.boost_reasons,
        })));
      }
    } catch (e) {
      console.log('Could not load attention items:', e);
      // Silently fail - the panel will just show "Nothing surfaced yet"
    }
  })();

  // Refresh attention items - called after Play mutations and on polling interval
  async function refreshAttentionItems(): Promise<void> {
    try {
      const result = await kernelRequest('cairn/attention', { hours: 168, limit: 200 }) as {
        count: number;
        items: Array<{
          entity_type: string;
          entity_id: string;
          title: string;
          reason: string;
          urgency: string;
          calendar_start?: string;
          calendar_end?: string;
          is_recurring?: boolean;
          recurrence_frequency?: string;
          next_occurrence?: string;
          act_id?: string;
          scene_id?: string;
          act_title?: string;
          act_color?: string;
          user_priority?: number;
          sender_name?: string | null;
          sender_email?: string | null;
          account_email?: string | null;
          email_date?: string | null;
          importance_score?: number | null;
          importance_reason?: string | null;
          email_message_id?: number | null;
          is_read?: boolean | null;
          learned_boost?: number | null;
          boost_reasons?: string[] | null;
        }>;
      };
      cairnView.updateSurfaced(result.items.map(item => ({
        title: item.title,
        reason: item.reason,
        urgency: item.urgency,
        is_recurring: item.is_recurring,
        recurrence_frequency: item.recurrence_frequency,
        next_occurrence: item.next_occurrence,
        entity_type: item.entity_type,
        entity_id: item.entity_id,
        act_id: item.act_id,
        scene_id: item.scene_id,
        act_title: item.act_title,
        act_color: item.act_color,
        user_priority: item.user_priority,
        sender_name: item.sender_name,
        sender_email: item.sender_email,
        account_email: item.account_email,
        email_date: item.email_date,
        importance_score: item.importance_score,
        importance_reason: item.importance_reason,
        email_message_id: item.email_message_id,
        is_read: item.is_read,
        learned_boost: item.learned_boost,
        boost_reasons: item.boost_reasons,
      })));
    } catch (e) {
      console.log('Could not refresh attention items:', e);
    }
  }

  // Auto-archive conversation on window close
  const autoArchiveOnClose = async (): Promise<void> => {
    if (!currentConversationId) return;

    try {
      // Archive the current conversation silently
      await kernelRequest('conversation/archive', {
        conversation_id: currentConversationId,
        auto_link: true,
        extract_knowledge: true,
      });
      console.log('Auto-archived conversation on close');
    } catch (e) {
      console.error('Failed to auto-archive on close:', e);
    }
  };

  // Auto-archive on close using beforeunload (best-effort, may not complete)
  window.addEventListener('beforeunload', () => {
    if (currentConversationId) {
      void autoArchiveOnClose();
    }
  });

  // Adaptive polling for attention items: 10s when user active, 60s when idle
  let lastActivityTime = Date.now();
  const ACTIVE_POLL_INTERVAL = 10000;  // 10 seconds when active
  const IDLE_POLL_INTERVAL = 60000;    // 60 seconds when idle
  const IDLE_THRESHOLD = 30000;        // Consider idle after 30 seconds of no activity

  function updateActivityTime(): void {
    lastActivityTime = Date.now();
  }

  // Track user activity
  document.addEventListener('mousemove', updateActivityTime);
  document.addEventListener('keydown', updateActivityTime);
  document.addEventListener('click', updateActivityTime);

  // Start adaptive polling
  function scheduleNextPoll(): void {
    const isIdle = Date.now() - lastActivityTime > IDLE_THRESHOLD;
    const interval = isIdle ? IDLE_POLL_INTERVAL : ACTIVE_POLL_INTERVAL;

    setTimeout(() => {
      void refreshAttentionItems().then(scheduleNextPoll);
    }, interval);
  }

  // Start polling after a small delay to avoid duplicate initial fetch
  setTimeout(scheduleNextPoll, ACTIVE_POLL_INTERVAL);

  // Handle CAIRN chat messages (default conversational mode)
  // Uses async chat to enable real-time consciousness streaming
  async function handleCairnMessage(message: string): Promise<void> {
    // Show thinking indicator while waiting for response
    cairnView.showThinking();
    try {
      // Start async chat - returns immediately with chat_id
      // This allows consciousness/poll requests to be handled while chat processes
      const asyncResult = (await kernelRequest('cairn/chat_async', {
        text: message,
        conversation_id: currentConversationId,
      })) as { chat_id: string; status: string };

      const chatId = asyncResult.chat_id;

      // Poll for chat completion
      // The consciousness stream polling runs in parallel (started in cairnView.ts)
      let chatComplete = false;
      while (!chatComplete) {
        // Small delay between status checks
        await new Promise(resolve => setTimeout(resolve, 200));

        const statusResult = (await kernelRequest('cairn/chat_status', {
          chat_id: chatId,
        })) as { status: string; result?: ChatRespondResult; error?: string };

        if (statusResult.status === 'complete' && statusResult.result) {
          chatComplete = true;
          cairnView.hideThinking();
          if (statusResult.result.conversation_id) {
            currentConversationId = statusResult.result.conversation_id;
          }
          // Use addAssistantMessage to include full response data (thinking steps, tool calls)
          cairnView.addAssistantMessage(statusResult.result);

          // Persist consciousness events and show feedback UI (RLHF)
          if (statusResult.result.conversation_id && statusResult.result.user_message_id && statusResult.result.message_id) {
            void cairnView.persistAndShowFeedback(
              statusResult.result.conversation_id,
              statusResult.result.user_message_id,
              statusResult.result.message_id,
            );
          }

          // Refresh attention items after CAIRN chat - scene moves may have changed act assignments
          void refreshAttentionItems();
        } else if (statusResult.status === 'error') {
          chatComplete = true;
          cairnView.hideThinking();
          cairnView.addChatMessage('assistant', `Error: ${statusResult.error || 'Unknown error'}`);
        }
        // If status is "processing", continue polling
      }
    } catch (error) {
      cairnView.hideThinking();
      cairnView.addChatMessage('assistant', `Error: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  }

  // ============ Main View Container ============
  const mainViewContainer = el('div');
  mainViewContainer.className = 'main-view-container';
  mainViewContainer.style.cssText = `
    flex: 1;
    display: flex;
    overflow: hidden;
    height: 100%;
    min-height: 0;
  `;
  // CAIRN view fills the main container
  cairnView.container.style.display = 'flex';

  // Context state for the context meter
  let currentConversationId: string | null = null;

  // Context meter stubs (updated by updateContextMeter, displayed in nav)
  const meterFill = el('div') as HTMLDivElement;
  const meterText = el('span') as HTMLSpanElement;

  // ============ Create Agent Views ============
  const reosView = createReosView({ kernelRequest, getSessionCred: getSessionToken });
  const rivaView = createRivaView();
  const copperView = createCopperView({ kernelRequest });

  // Insert context meter + health indicator into CAIRN's chat header
  cairnView.chatHeader.appendChild(navContextMeter);
  cairnView.chatHeader.appendChild(healthIndicator);

  // ============ The Play (created early, used as a view) ============
  const settingsOverlay = createSettingsOverlay();
  const playOverlay = createPlayOverlay(() => {});
  const playViewContainer = playOverlay.viewElement ?? playOverlay.element;
  playViewContainer.style.display = 'none';
  playViewContainer.style.flex = '1';

  // Add all views to container
  mainViewContainer.appendChild(playViewContainer);
  mainViewContainer.appendChild(cairnView.container);
  mainViewContainer.appendChild(reosView.container);
  mainViewContainer.appendChild(rivaView.container);
  mainViewContainer.appendChild(copperView.container);
  reosView.container.style.display = 'none';
  rivaView.container.style.display = 'none';
  copperView.container.style.display = 'none';

  // View router: swap which view is displayed in mainViewContainer
  const viewMap: Record<AgentId, HTMLElement> = {
    play: playViewContainer,
    cairn: cairnView.container,
    reos: reosView.container,
    riva: rivaView.container,
    copper: copperView.container,
  };

  function switchView(id: AgentId) {
    for (const [viewId, viewEl] of Object.entries(viewMap)) {
      viewEl.style.display = viewId === id ? 'flex' : 'none';
    }
    currentAgentView = id;
    // Trigger Play data load when switching to it
    if (id === 'play') {
      playOverlay.open();
    }
    // ReOS dashboard polling lifecycle — terminal stays alive across view switches
    if (id === 'reos') {
      reosView.startPolling();
      reosView.startTerminal();
    } else {
      reosView.stopPolling();
    }
    // Copper dashboard polling lifecycle
    if (id === 'copper') {
      copperView.startPolling();
    } else {
      copperView.stopPolling();
    }
    // RIVA project manager polling lifecycle
    if (id === 'riva') {
      rivaView.startPolling();
    } else {
      rivaView.stopPolling();
    }
  }

  // ============ Agent Bar ============
  const agentBar = createAgentBar({
    onSwitchAgent: (id) => switchView(id),
    onOpenSettings: () => settingsOverlay.show(),
  });

  // ============ Shell Assembly ============
  // Layout: agentBar (180px) | mainViewContainer (swappable views)
  shell.appendChild(agentBar.element);
  shell.appendChild(mainViewContainer);

  root.appendChild(shell);
  root.appendChild(settingsOverlay.element);

  // Create Context overlay
  const contextOverlay = createContextOverlay();
  root.appendChild(contextOverlay.element);

  // Wire up nav context meter to open the overlay
  navContextMeter.addEventListener('click', () => {
    contextOverlay.show(currentConversationId);
    // Update meter after viewing (user might have toggled sources)
    setTimeout(() => void updateNavContextMeter(), 500);
  });


  let activeActId: string | null = null;
  let actsCache: PlayActsListResult['acts'] = [];
  let selectedSceneId: string | null = null;

  let scenesCache: PlayScenesListResult['scenes'] = [];

  let kbSelectedPath = 'kb.md';
  let kbTextDraft = '';
  let kbPreview: PlayKbWritePreviewResult | null = null;

  // Log JSON to console for debugging
  function showJsonInInspector(title: string, obj: unknown) {
    console.log(`[${title}]`, obj);
  }

  // Helper functions (rowHeader, label, textInput, textArea, smallButton)
  // are now imported from ./dom.ts

  async function refreshKbForSelection() {
    if (!activeActId) return;
    const sceneId = selectedSceneId ?? undefined;

    const filesRes = (await kernelRequest('play/kb/list', {
      act_id: activeActId,
      scene_id: sceneId
    })) as PlayKbListResult;

    const files = filesRes.files ?? [];
    if (files.length > 0 && !files.includes(kbSelectedPath)) {
      kbSelectedPath = files[0];
    }

    try {
      const readRes = (await kernelRequest('play/kb/read', {
        act_id: activeActId,
        scene_id: sceneId,
        path: kbSelectedPath
      })) as PlayKbReadResult;
      kbTextDraft = readRes.text ?? '';
    } catch {
      // If missing, keep draft as-is (acts as a create).
    }
    kbPreview = null;
  }


  async function refreshActs() {
    const res = (await kernelRequest('play/acts/list', {})) as PlayActsListResult;
    activeActId = res.active_act_id ?? null;
    actsCache = res.acts ?? [];
  }

  async function refreshScenes(actId: string) {
    const res = (await kernelRequest('play/scenes/list', { act_id: actId })) as PlayScenesListResult;
    scenesCache = res.scenes ?? [];
    if (selectedSceneId && !scenesCache.some((s) => s.scene_id === selectedSceneId)) {
      selectedSceneId = null;
    }
  }


  // Note: currentConversationId is declared earlier in buildUi

  // Legacy stub for context meter click (not visible in new UI)
  const contextMeter = el('div');
  contextMeter.addEventListener('click', () => {
    contextOverlay.show(currentConversationId);
  });

  // --- Context Meter & Chat Actions ---

  async function updateContextMeter() {
    try {
      const stats = await kernelRequest('context/stats', {
        conversation_id: currentConversationId,
      }) as ContextStatsResult;

      // Update progress bar
      meterFill.style.width = `${Math.min(100, stats.usage_percent)}%`;
      meterText.textContent = `${Math.round(stats.usage_percent)}%`;

      // Color based on warning level
      if (stats.warning_level === 'critical') {
        meterFill.style.background = '#ef4444';
        meterText.style.color = '#ef4444';
      } else if (stats.warning_level === 'warning') {
        meterFill.style.background = '#f59e0b';
        meterText.style.color = '#f59e0b';
      } else {
        meterFill.style.background = '#22c55e';
        meterText.style.color = 'inherit';
      }
    } catch (e) {
      console.error('Failed to update context meter:', e);
    }
  }

  // Update context meter periodically and after messages
  setInterval(() => void updateContextMeter(), 30000);

  // Keyboard shortcuts
  document.addEventListener('keydown', (e) => {
    const chatInput = cairnView.getChatInput();

    // Escape to clear input
    if (e.key === 'Escape' && document.activeElement === chatInput) {
      chatInput.value = '';
      chatInput.blur();
    }
  });

  // Initial load
  void (async () => {
    try {
      await refreshActs();
      if (activeActId) await refreshScenes(activeActId);

      // Wait for attention items to finish loading (avoids DB lock contention)
      await attentionLoaded;

      // No auto-greeting on startup
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

async function buildDashboardWindow() {
  const root = document.getElementById('app');
  if (!root) return;
  root.innerHTML = '';

  const wrap = el('div');
  wrap.style.cssText = `
    padding: 20px;
    height: 100vh;
    box-sizing: border-box;
    overflow: auto;
    font-family: system-ui, sans-serif;
    background: #1a1a1a;
    color: #e5e7eb;
  `;

  const header = el('div');
  header.style.cssText = `
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
  `;

  const title = el('div');
  title.textContent = '💻 System Dashboard';
  title.style.cssText = 'font-weight: 600; font-size: 20px; color: #fff;';

  const refreshBtn = el('button');
  refreshBtn.textContent = '↻ Refresh';
  refreshBtn.style.cssText = `
    padding: 8px 16px;
    font-size: 12px;
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 6px;
    background: rgba(255,255,255,0.1);
    color: #e5e7eb;
    cursor: pointer;
    transition: all 0.2s;
  `;
  refreshBtn.addEventListener('mouseenter', () => {
    refreshBtn.style.background = 'rgba(255,255,255,0.2)';
  });
  refreshBtn.addEventListener('mouseleave', () => {
    refreshBtn.style.background = 'rgba(255,255,255,0.1)';
  });

  header.appendChild(title);
  header.appendChild(refreshBtn);

  // System metrics row (CPU, RAM, Disk, GPU)
  const metricsRow = el('div');
  metricsRow.style.cssText = `
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 24px;
  `;

  // Gauge helper with description and detail value
  function createGauge(label: string, icon: string, description: string): {
    container: HTMLElement;
    value: HTMLElement;
    bar: HTMLElement;
    detail: HTMLElement;
    setHidden: (hidden: boolean) => void;
  } {
    const container = el('div');
    container.style.cssText = `
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 12px;
      padding: 16px;
    `;

    const labelRow = el('div');
    labelRow.style.cssText = 'display: flex; align-items: center; gap: 8px; margin-bottom: 4px;';
    labelRow.innerHTML = `<span style="font-size: 18px;">${icon}</span><span style="font-weight: 500; color: rgba(255,255,255,0.8);">${label}</span>`;

    const desc = el('div');
    desc.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.5); margin-bottom: 10px;';
    desc.textContent = description;

    const value = el('div');
    value.style.cssText = 'font-size: 28px; font-weight: 700; color: #22c55e; margin-bottom: 4px;';
    value.textContent = '--%';

    const detail = el('div');
    detail.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.6); margin-bottom: 8px;';
    detail.textContent = '';

    const barContainer = el('div');
    barContainer.style.cssText = `
      height: 8px;
      background: rgba(255,255,255,0.1);
      border-radius: 4px;
      overflow: hidden;
    `;

    const bar = el('div');
    bar.style.cssText = `
      height: 100%;
      width: 0%;
      background: #22c55e;
      border-radius: 4px;
      transition: width 0.3s, background 0.3s;
    `;
    barContainer.appendChild(bar);

    container.appendChild(labelRow);
    container.appendChild(desc);
    container.appendChild(value);
    container.appendChild(detail);
    container.appendChild(barContainer);

    return {
      container,
      value,
      bar,
      detail,
      setHidden: (hidden: boolean) => {
        container.style.display = hidden ? 'none' : 'block';
      }
    };
  }

  const cpuGauge = createGauge('CPU', '⚡', 'Processing power usage');
  const ramGauge = createGauge('Memory', '💾', 'RAM consumption');
  const diskGauge = createGauge('Disk', '📁', 'Storage space used');
  const gpuGauge = createGauge('GPU', '🎮', 'Graphics processor load');

  metricsRow.appendChild(cpuGauge.container);
  metricsRow.appendChild(ramGauge.container);
  metricsRow.appendChild(diskGauge.container);
  metricsRow.appendChild(gpuGauge.container);

  // Initially hide GPU gauge until we know if one is available
  gpuGauge.setHidden(true);

  // Grid layout for sections
  const grid = el('div');
  grid.style.cssText = `
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 16px;
  `;

  // Section helper
  function createSection(sectionTitle: string, icon: string): { section: HTMLElement; content: HTMLElement } {
    const section = el('div');
    section.style.cssText = `
      background: rgba(255,255,255,0.05);
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.1);
      padding: 16px;
      min-height: 200px;
    `;

    const sectionHeader = el('div');
    sectionHeader.style.cssText = `
      font-weight: 600;
      font-size: 14px;
      margin-bottom: 12px;
      color: rgba(255,255,255,0.9);
      display: flex;
      align-items: center;
      gap: 8px;
    `;
    sectionHeader.innerHTML = `<span>${icon}</span>${sectionTitle}`;

    const content = el('div');
    content.style.cssText = 'font-size: 13px;';

    section.appendChild(sectionHeader);
    section.appendChild(content);

    return { section, content };
  }

  // Create sections
  const servicesSection = createSection('Services', '🔧');
  const containersSection = createSection('Containers', '🐳');
  const portsSection = createSection('Listening Ports', '🔌');
  const trafficSection = createSection('Network Traffic', '📡');

  grid.appendChild(servicesSection.section);
  grid.appendChild(containersSection.section);
  grid.appendChild(portsSection.section);
  grid.appendChild(trafficSection.section);

  wrap.appendChild(header);
  wrap.appendChild(metricsRow);
  wrap.appendChild(grid);
  root.appendChild(wrap);

  // Helper to get color based on percentage
  function getGaugeColor(percent: number): string {
    if (percent >= 90) return '#ef4444';
    if (percent >= 70) return '#f59e0b';
    return '#22c55e';
  }

  // Refresh function
  async function refreshDashboard() {
    servicesSection.content.innerHTML = '<span style="opacity: 0.6">Loading...</span>';
    containersSection.content.innerHTML = '<span style="opacity: 0.6">Loading...</span>';
    portsSection.content.innerHTML = '<span style="opacity: 0.6">Loading...</span>';
    trafficSection.content.innerHTML = '<span style="opacity: 0.6">Loading...</span>';

    try {
      const result = await kernelRequest('system/live_state', {}) as SystemLiveStateResult;

      // Update CPU gauge
      const cpuPercent = result.cpu_percent ?? 0;
      const cpuColor = getGaugeColor(cpuPercent);
      cpuGauge.value.textContent = `${Math.round(cpuPercent)}%`;
      cpuGauge.value.style.color = cpuColor;
      cpuGauge.bar.style.width = `${cpuPercent}%`;
      cpuGauge.bar.style.background = cpuColor;
      const cpuModel = result.cpu_model ?? 'Unknown';
      const cpuCores = result.cpu_cores ?? 0;
      cpuGauge.detail.textContent = `${cpuCores} cores • ${cpuModel.substring(0, 30)}${cpuModel.length > 30 ? '...' : ''}`;

      // Update RAM gauge (memory is nested object with percent field)
      const memoryData = result.memory as { percent?: number; used_mb?: number; total_mb?: number } | undefined;
      const ramPercent = memoryData?.percent ?? 0;
      const ramUsedMb = memoryData?.used_mb ?? 0;
      const ramTotalMb = memoryData?.total_mb ?? 0;
      const ramColor = getGaugeColor(ramPercent);
      ramGauge.value.textContent = `${Math.round(ramPercent)}%`;
      ramGauge.value.style.color = ramColor;
      ramGauge.bar.style.width = `${ramPercent}%`;
      ramGauge.bar.style.background = ramColor;
      const ramUsedGb = (ramUsedMb / 1024).toFixed(1);
      const ramTotalGb = (ramTotalMb / 1024).toFixed(1);
      ramGauge.detail.textContent = `${ramUsedGb} GB / ${ramTotalGb} GB used`;

      // Update Disk gauge (disks is array, use first/root disk)
      const disksData = result.disks as Array<{ percent?: number; used_gb?: number; total_gb?: number; mount?: string }> | undefined;
      const firstDisk = disksData && disksData.length > 0 ? disksData[0] : null;
      const diskPercent = firstDisk?.percent ?? 0;
      const diskUsedGb = firstDisk?.used_gb ?? 0;
      const diskTotalGb = firstDisk?.total_gb ?? 0;
      const diskColor = getGaugeColor(diskPercent);
      diskGauge.value.textContent = `${Math.round(diskPercent)}%`;
      diskGauge.value.style.color = diskColor;
      diskGauge.bar.style.width = `${diskPercent}%`;
      diskGauge.bar.style.background = diskColor;
      diskGauge.detail.textContent = `${diskUsedGb.toFixed(0)} GB / ${diskTotalGb.toFixed(0)} GB used`;

      // Update GPU gauge if available
      const gpuData = result.gpu as { name?: string; percent?: number; memory_used_mb?: number; memory_total_mb?: number } | null;
      if (gpuData) {
        gpuGauge.setHidden(false);
        // Update grid to show 4 columns
        metricsRow.style.gridTemplateColumns = 'repeat(4, 1fr)';
        const gpuPercent = gpuData.percent ?? 0;
        const gpuColor = getGaugeColor(gpuPercent);
        gpuGauge.value.textContent = `${Math.round(gpuPercent)}%`;
        gpuGauge.value.style.color = gpuColor;
        gpuGauge.bar.style.width = `${gpuPercent}%`;
        gpuGauge.bar.style.background = gpuColor;
        const gpuMemUsedGb = ((gpuData.memory_used_mb ?? 0) / 1024).toFixed(1);
        const gpuMemTotalGb = ((gpuData.memory_total_mb ?? 0) / 1024).toFixed(1);
        const gpuName = gpuData.name ?? 'Unknown';
        gpuGauge.detail.textContent = `${gpuMemUsedGb}/${gpuMemTotalGb} GB • ${gpuName.substring(0, 20)}`;
      } else {
        gpuGauge.setHidden(true);
        // Use 3 columns when no GPU
        metricsRow.style.gridTemplateColumns = 'repeat(3, 1fr)';
      }

      // Render services
      const services = result.services ?? [];
      if (services.length === 0) {
        servicesSection.content.innerHTML = '<span style="opacity: 0.5; color: rgba(255,255,255,0.6);">No services found</span>';
      } else {
        servicesSection.content.innerHTML = '';
        for (const svc of services) {
          const row = el('div');
          row.style.cssText = `
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
          `;

          const dot = el('span');
          dot.textContent = '●';
          dot.style.cssText = `
            font-size: 10px;
            color: ${svc.status === 'failed' ? '#ef4444' : svc.active ? '#22c55e' : '#6b7280'};
          `;

          const name = el('span');
          name.textContent = svc.name;
          name.style.cssText = 'flex: 1; color: rgba(255,255,255,0.9);';

          const status = el('span');
          status.textContent = svc.status;
          status.style.cssText = `
            font-size: 10px;
            padding: 2px 8px;
            border-radius: 4px;
            background: ${svc.status === 'failed' ? 'rgba(239,68,68,0.2)' : svc.active ? 'rgba(34,197,94,0.2)' : 'rgba(107,114,128,0.2)'};
            color: ${svc.status === 'failed' ? '#ef4444' : svc.active ? '#22c55e' : '#9ca3af'};
          `;

          row.appendChild(dot);
          row.appendChild(name);
          row.appendChild(status);
          servicesSection.content.appendChild(row);
        }
      }

      // Render containers
      const containers = result.containers ?? [];
      if (containers.length === 0) {
        containersSection.content.innerHTML = '<span style="opacity: 0.5; color: rgba(255,255,255,0.6);">No containers found</span>';
      } else {
        containersSection.content.innerHTML = '';
        for (const ctr of containers) {
          const row = el('div');
          row.style.cssText = `
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
          `;

          const isRunning = ctr.status.toLowerCase().includes('up');
          const dot = el('span');
          dot.textContent = '●';
          dot.style.cssText = `font-size: 10px; color: ${isRunning ? '#22c55e' : '#6b7280'};`;

          const name = el('span');
          name.textContent = ctr.name;
          name.style.cssText = 'flex: 1; color: rgba(255,255,255,0.9);';

          const image = el('span');
          image.textContent = ctr.image.split(':')[0].split('/').pop() ?? ctr.image;
          image.style.cssText = `
            font-size: 11px;
            padding: 2px 6px;
            border-radius: 4px;
            background: rgba(255,255,255,0.1);
            color: rgba(255,255,255,0.6);
          `;

          row.appendChild(dot);
          row.appendChild(name);
          row.appendChild(image);
          containersSection.content.appendChild(row);
        }
      }

      // Render ports
      const ports = result.ports ?? [];
      if (ports.length === 0) {
        portsSection.content.innerHTML = '<span style="opacity: 0.5; color: rgba(255,255,255,0.6);">No listening ports</span>';
      } else {
        portsSection.content.innerHTML = '';
        for (const port of ports) {
          const row = el('div');
          row.style.cssText = `
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
          `;

          const portNum = el('span');
          portNum.textContent = `:${port.port}`;
          portNum.style.cssText = `
            font-family: 'JetBrains Mono', monospace;
            font-weight: 600;
            min-width: 60px;
            color: #60a5fa;
          `;

          const addr = el('span');
          addr.textContent = port.address === '0.0.0.0' || port.address === '*' ? 'all interfaces' : port.address;
          addr.style.cssText = 'flex: 1; color: rgba(255,255,255,0.6);';

          const process = el('span');
          process.textContent = port.process || `PID ${port.pid ?? '?'}`;
          process.style.cssText = `
            font-size: 11px;
            padding: 2px 8px;
            border-radius: 4px;
            background: rgba(59,130,246,0.2);
            color: #93c5fd;
          `;

          row.appendChild(portNum);
          row.appendChild(addr);
          row.appendChild(process);
          portsSection.content.appendChild(row);
        }
      }

      // Render traffic
      const traffic = result.traffic ?? [];
      if (traffic.length === 0) {
        trafficSection.content.innerHTML = '<span style="opacity: 0.5; color: rgba(255,255,255,0.6);">No network interfaces</span>';
      } else {
        trafficSection.content.innerHTML = '';
        for (const iface of traffic) {
          const row = el('div');
          row.style.cssText = `
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 10px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
          `;

          const name = el('span');
          name.textContent = iface.interface;
          name.style.cssText = 'font-weight: 500; min-width: 80px; color: rgba(255,255,255,0.9);';

          const rx = el('span');
          rx.innerHTML = `<span style="color: #22c55e;">↓</span> ${escapeHtml(iface.rx_formatted)}`;
          rx.style.cssText = 'flex: 1; font-family: monospace; font-size: 12px;';

          const tx = el('span');
          tx.innerHTML = `<span style="color: #3b82f6;">↑</span> ${escapeHtml(iface.tx_formatted)}`;
          tx.style.cssText = 'flex: 1; font-family: monospace; font-size: 12px;';

          row.appendChild(name);
          row.appendChild(rx);
          row.appendChild(tx);
          trafficSection.content.appendChild(row);
        }
      }
    } catch (e) {
      const errorMsg = `<span style="color: #ef4444;">Error: ${String(e)}</span>`;
      servicesSection.content.innerHTML = errorMsg;
      containersSection.content.innerHTML = '';
      portsSection.content.innerHTML = '';
      trafficSection.content.innerHTML = '';

      // Reset gauges on error
      cpuGauge.value.textContent = '--%';
      ramGauge.value.textContent = '--%';
      diskGauge.value.textContent = '--%';
    }
  }

  // Initial load and refresh button
  refreshBtn.addEventListener('click', () => void refreshDashboard());
  await refreshDashboard();

  // Auto-refresh every 10 seconds
  setInterval(() => void refreshDashboard(), 10000);
}

/**
 * Initialize the application with authentication.
 *
 * Security:
 * - Checks for existing session on startup
 * - Shows login screen if not authenticated
 * - Sets up session monitoring for auto-lock
 */
async function initializeApp(): Promise<void> {
  // Apply saved theme before anything renders (including lock screen)
  initTheme();

  const root = document.getElementById('app');
  if (!root) return;

  // Skip authentication in development mode for faster iteration
  // @ts-ignore - Vite provides import.meta.env
  const skipAuth = import.meta.env.DEV;

  if (skipAuth) {
    console.log('[DEV] Creating dev session...');
    try {
      // Create a dev session on the Rust side
      const { invoke } = await import('@tauri-apps/api/core');
      const result = await invoke('dev_create_session') as { success: boolean; session_token?: string; username?: string; error?: string };

      if (result.success && result.session_token && result.username) {
        // Store the session in localStorage so kernelRequest can use it
        const { setSession } = await import('./kernel');
        setSession(result.session_token, result.username);
        console.log(`[DEV] Session created for user: ${result.username}`);
        buildUi();
        return;
      } else {
        console.error('[DEV] Failed to create dev session:', result.error);
      }
    } catch (e) {
      console.error('[DEV] Failed to create dev session:', e);
    }
    // Fall through to normal auth if dev session fails
  }

  // Check authentication and show login if needed
  const isValid = await checkSessionOrLogin(root, (_username) => {
    // On successful login, build the authenticated UI
    buildUi();
    setupSessionMonitoring();
  });

  if (isValid) {
    // Session is valid, build UI immediately
    buildUi();
    setupSessionMonitoring();
  }
}

/**
 * Set up session monitoring for auto-lock.
 * Monitors for:
 * - Session expiry (periodic validation)
 * - Window visibility changes (potential system lock)
 */
function setupSessionMonitoring(): void {
  // Check session validity every 5 minutes
  setInterval(async () => {
    if (!isAuthenticated()) return;

    const isValid = await validateSession();
    if (!isValid) {
      // Session expired, show lock overlay
      showLockOverlay(() => {
        // Session restored, continue normally
      });
    }
  }, 5 * 60 * 1000);

  // Monitor visibility changes (user might have locked screen)
  document.addEventListener('visibilitychange', async () => {
    if (document.visibilityState === 'visible' && isAuthenticated()) {
      // Coming back from hidden, validate session
      const isValid = await validateSession();
      if (!isValid) {
        showLockOverlay(() => {
          // Session restored
        });
      }
    }
  });
}

// Initialize app on load
initializeApp().catch((err) => {
  console.error('Failed to initialize app:', err);
  // Show error prominently in the UI
  const errorDiv = document.createElement('div');
  errorDiv.style.cssText = `
    position: fixed; top: 0; left: 0; right: 0;
    background: #ef4444; color: white; padding: 12px;
    text-align: center; font-size: 14px; z-index: 9999;
  `;
  errorDiv.textContent = `Failed to initialize Talking Rock: ${err instanceof Error ? err.message : String(err)}`;
  document.body.appendChild(errorDiv);
});
