/**
 * Cairn Desktop Application - Personal Attention Minder
 *
 * Main entry point for the Tauri-based desktop UI.
 * Communicates with the Python kernel via JSON-RPC over stdio.
 */
import { WebviewWindow, getCurrentWebviewWindow } from '@tauri-apps/api/webviewWindow';
import { open as openDialog } from '@tauri-apps/plugin-dialog';

import './style.css';

// Modular imports
import {
  kernelRequest,
  KernelError,
  AuthenticationError,
  isAuthenticated,
  validateSession,
  logout,
  getSessionUsername,
} from './kernel';
import { checkSessionOrLogin, showLockOverlay } from './lockScreen';
import { el, escapeHtml, rowHeader, label, textInput, textArea, smallButton } from './dom';
import { createPlayOverlay } from './playOverlay';
import { createSettingsOverlay } from './settingsOverlay';
import { createContextOverlay } from './contextOverlay';
import { createCairnView } from './cairnView';

import { buildPlayWindow } from './playWindow';
import type {
  ChatRespondResult,
  SystemInfoResult,
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

  const nav = el('div');
  nav.className = 'nav';
  nav.style.width = '280px';
  nav.style.borderRight = '1px solid #ddd';
  nav.style.padding = '12px';
  nav.style.overflow = 'auto';

  const navTitle = el('div');
  navTitle.textContent = 'Talking Rock for Linux';
  navTitle.style.fontWeight = '600';
  navTitle.style.fontSize = '16px';
  navTitle.style.marginBottom = '12px';

  // System Status Section
  const systemSection = el('div');
  systemSection.className = 'system-section';

  const systemHeader = el('div');
  systemHeader.textContent = 'System Status';
  systemHeader.style.fontWeight = '600';
  systemHeader.style.marginBottom = '8px';
  systemHeader.style.fontSize = '13px';
  systemHeader.style.color = '#666';

  const systemStatus = el('div');
  systemStatus.className = 'system-status';
  systemStatus.style.fontSize = '12px';
  systemStatus.style.marginBottom = '12px';
  systemStatus.innerHTML = '<span style="opacity: 0.6">Loading...</span>';

  systemSection.appendChild(systemHeader);
  systemSection.appendChild(systemStatus);

  // Shared nav button style
  const navBtnStyle = (btn: HTMLElement) => {
    btn.style.padding = '10px';
    btn.style.fontSize = '12px';
    btn.style.fontWeight = '500';
    btn.style.border = '1px solid rgba(255, 255, 255, 0.15)';
    btn.style.borderRadius = '8px';
    btn.style.background = 'rgba(255, 255, 255, 0.08)';
    btn.style.color = '#e5e7eb';
    btn.style.cursor = 'pointer';
    btn.style.width = '100%';
    btn.style.textAlign = 'left';
  };

  // System Dashboard Button
  const dashboardBtn = el('button');
  dashboardBtn.textContent = 'Open System Dashboard';
  dashboardBtn.style.marginTop = '12px';
  navBtnStyle(dashboardBtn);

  // The Play Button - opens the Play window
  const playBtn = el('button');
  playBtn.textContent = 'The Play';
  playBtn.title = 'Open The Play - your story, acts, and scenes';
  navBtnStyle(playBtn);
  playBtn.style.marginTop = '12px';

  // Nav content container (top section)
  const navContent = el('div');
  navContent.className = 'nav-content';
  navContent.style.cssText = 'flex: 1;';

  navContent.appendChild(navTitle);

  // ============ Context Usage Indicator (opens Context Overlay) ============
  const navContextMeter = el('div');
  navContextMeter.className = 'nav-context-meter';
  navContextMeter.title = 'Click to view context details';
  navContextMeter.style.cssText = `
    margin-bottom: 12px;
    padding: 10px 12px;
    background: rgba(0, 0, 0, 0.2);
    border-radius: 8px;
    cursor: pointer;
    transition: background 0.2s;
  `;

  const contextUsageBar = el('div');
  contextUsageBar.style.cssText = `
    height: 6px;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 3px;
    overflow: hidden;
    margin-bottom: 6px;
  `;

  const contextUsageFill = el('div');
  contextUsageFill.style.cssText = `
    height: 100%;
    width: 0%;
    background: #22c55e;
    border-radius: 3px;
    transition: width 0.3s, background 0.3s;
  `;
  contextUsageBar.appendChild(contextUsageFill);

  const contextUsageLabel = el('div');
  contextUsageLabel.style.cssText = `
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 11px;
    color: rgba(255, 255, 255, 0.6);
  `;
  contextUsageLabel.innerHTML = `
    <span>🧠 Context</span>
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

  navContent.appendChild(navContextMeter);
  navContent.appendChild(systemSection);

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
  navContent.appendChild(healthIndicator);

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

  navContent.appendChild(dashboardBtn);
  navContent.appendChild(playBtn);

  // Settings button (bottom of nav)
  const settingsBtn = el('button');
  settingsBtn.className = 'settings-btn';
  settingsBtn.innerHTML = '⚙️ Settings';
  settingsBtn.style.cssText = `
    width: 100%;
    padding: 10px 12px;
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 6px;
    color: rgba(255,255,255,0.8);
    cursor: pointer;
    font-size: 13px;
    text-align: left;
    transition: background 0.2s;
    margin-top: 8px;
  `;
  settingsBtn.addEventListener('mouseenter', () => {
    settingsBtn.style.background = 'rgba(255,255,255,0.1)';
  });
  settingsBtn.addEventListener('mouseleave', () => {
    settingsBtn.style.background = 'rgba(255,255,255,0.05)';
  });

  // Make nav flex column
  nav.style.display = 'flex';
  nav.style.flexDirection = 'column';

  nav.appendChild(navContent);
  nav.appendChild(settingsBtn);

  // ============ CAIRN View (Conversational) ============
  const cairnView = createCairnView({
    onSendMessage: async (message: string) => {
      return handleCairnMessage(message);
    },
    kernelRequest,
  });

  // Load attention items at startup for "What Needs My Attention" section (next 7 days)
  void (async () => {
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
  `;
  mainViewContainer.appendChild(cairnView.container);

  // CAIRN view fills the main container
  cairnView.container.style.display = 'flex';

  // Context state for the context meter
  let currentConversationId: string | null = null;

  // Inspector stub elements (used by renderPlayInspector, rendered into overlay context)
  const inspectionTitle = el('div') as HTMLDivElement;
  const inspectionBody = el('div') as HTMLDivElement;

  // Context meter stubs (updated by updateContextMeter, displayed in nav)
  const meterFill = el('div') as HTMLDivElement;
  const meterText = el('span') as HTMLSpanElement;

  // ============ Shell Assembly ============
  // Layout: nav (280px) | mainViewContainer (CAIRN view)
  shell.appendChild(nav);
  shell.appendChild(mainViewContainer);

  root.appendChild(shell);

  // Create Play overlay
  const playOverlay = createPlayOverlay(() => {
    // Callback when overlay closes
    playInspectorActive = false;
  });
  root.appendChild(playOverlay.element);

  // Create Settings overlay
  const settingsOverlay = createSettingsOverlay();
  root.appendChild(settingsOverlay.element);

  // Wire up settings button
  settingsBtn.addEventListener('click', () => {
    settingsOverlay.show();
  });

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

  // Flag to track if "The Play" view is active in the inspection panel
  let playInspectorActive = false;

  // Log JSON to console for debugging
  function showJsonInInspector(title: string, obj: unknown) {
    console.log(`[${title}]`, obj);
  }

  async function openDashboardWindow() {
    console.log('openDashboardWindow called');
    try {
      const existing = await WebviewWindow.getByLabel('dashboard');
      console.log('existing dashboard window:', existing);
      if (existing) {
        await existing.setFocus();
        return;
      }
    } catch (e) {
      console.log('getByLabel error (expected if window does not exist):', e);
      // Best effort: if getByLabel fails, fall through and create a new window.
    }

    try {
      console.log('Creating new dashboard window...');
      const w = new WebviewWindow('dashboard', {
        title: 'System Dashboard — Talking Rock',
        url: '/?view=dashboard',
        width: 1000,
        height: 800
      });
      console.log('WebviewWindow created:', w);

      w.once('tauri://created', () => {
        console.log('Dashboard window created successfully');
      });
      w.once('tauri://error', (e) => {
        console.error('Dashboard window creation error:', e);
      });
    } catch (e) {
      console.error('Failed to create dashboard window:', e);
    }
  }

  async function openPlayWindow() {
    console.log('openPlayWindow called');
    try {
      const existing = await WebviewWindow.getByLabel('play');
      console.log('existing play window:', existing);
      if (existing) {
        await existing.setFocus();
        return;
      }
    } catch (e) {
      console.log('getByLabel error (expected if window does not exist):', e);
      // Best effort: if getByLabel fails, fall through and create a new window.
    }

    try {
      console.log('Creating new play window...');
      const w = new WebviewWindow('play', {
        title: 'The Play — Talking Rock',
        url: '/?view=play',
        width: 1920,
        height: 1080,
      });
      console.log('WebviewWindow created:', w);

      w.once('tauri://created', () => {
        console.log('Play window created successfully');
      });
      w.once('tauri://error', (e) => {
        console.error('Play window creation error:', e);
      });
    } catch (e) {
      console.error('Failed to create play window:', e);
    }
  }

  // Play button opens The Play window (standalone 1080p window)
  playBtn.addEventListener('click', () => void openPlayWindow());
  dashboardBtn.addEventListener('click', () => void openDashboardWindow());

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
    status.textContent = selectedSceneId
      ? `Act → Scene`
      : `Act`;
    inspectionBody.appendChild(status);

    // Act editor + create
    inspectionBody.appendChild(rowHeader('Act'));

    const actTitle = textInput('');
    const actNotes = textArea('', 70);
    const actRepoPath = textInput('');
    actRepoPath.placeholder = '/path/to/project';
    actRepoPath.style.flex = '1';
    const actRepoRow = el('div');
    actRepoRow.style.display = 'flex';
    actRepoRow.style.gap = '8px';
    actRepoRow.style.alignItems = 'center';
    actRepoRow.style.flexWrap = 'wrap';

    // Browse button for folder picker
    const actRepoBrowse = smallButton('Browse...');
    actRepoBrowse.style.background = 'rgba(59, 130, 246, 0.3)';
    actRepoBrowse.style.borderColor = '#3b82f6';
    actRepoBrowse.style.color = '#60a5fa';

    const actRepoOrLabel = el('span');
    actRepoOrLabel.textContent = 'or';
    actRepoOrLabel.style.color = 'rgba(255, 255, 255, 0.4)';
    actRepoOrLabel.style.fontSize = '11px';

    const actRepoAssign = smallButton('Set');
    actRepoRow.appendChild(actRepoBrowse);
    actRepoRow.appendChild(actRepoOrLabel);
    actRepoRow.appendChild(actRepoPath);
    actRepoRow.appendChild(actRepoAssign);
    const actRepoStatus = el('div');
    actRepoStatus.style.fontSize = '11px';
    actRepoStatus.style.marginTop = '4px';
    actRepoStatus.style.color = '#666';
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
    inspectionBody.appendChild(label('Repository Path'));
    inspectionBody.appendChild(actRepoRow);
    inspectionBody.appendChild(actRepoStatus);
    inspectionBody.appendChild(actSave);
    inspectionBody.appendChild(label('Create new act'));
    inspectionBody.appendChild(actCreateRow);

    void (async () => {
      if (!activeAct) return;
      actTitle.value = activeAct.title ?? '';
      actNotes.value = activeAct.notes ?? '';
      actRepoPath.value = activeAct.repo_path ?? '';
      if (activeAct.repo_path) {
        actRepoStatus.textContent = `Current: ${activeAct.repo_path}`;
        actRepoStatus.style.color = '#22c55e';
      } else {
        actRepoStatus.textContent = 'No repository assigned. Code mode requires a repo.';
        actRepoStatus.style.color = '#f59e0b';
      }
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

    // Helper to assign repo path
    const assignActRepo = async (repoPath: string) => {
      if (!activeActId) return;
      if (!repoPath) {
        actRepoStatus.textContent = 'Please select or enter a path';
        actRepoStatus.style.color = '#ef4444';
        return;
      }
      try {
        actRepoStatus.textContent = 'Setting...';
        actRepoStatus.style.color = '#60a5fa';
        const res = await kernelRequest('play/acts/assign_repo', {
          act_id: activeActId,
          repo_path: repoPath,
        }) as { success: boolean; repo_path: string };
        actRepoStatus.textContent = `Set: ${res.repo_path}`;
        actRepoStatus.style.color = '#22c55e';
        actRepoPath.value = res.repo_path;
        await refreshActs();
      } catch (err) {
        actRepoStatus.textContent = `Error: ${String(err)}`;
        actRepoStatus.style.color = '#ef4444';
      }
    };

    // Browse button - opens folder picker
    actRepoBrowse.addEventListener('click', () => {
      void (async () => {
        try {
          const selected = await openDialog({
            directory: true,
            multiple: false,
            title: 'Select Repository Folder',
          });
          if (selected && typeof selected === 'string') {
            actRepoPath.value = selected;  // Update text field immediately
            await assignActRepo(selected);
          }
        } catch (err) {
          actRepoStatus.textContent = `Error: ${String(err)}`;
          actRepoStatus.style.color = '#ef4444';
        }
      })();
    });

    // Manual text entry
    actRepoAssign.addEventListener('click', () => {
      void (async () => {
        await assignActRepo(actRepoPath.value.trim());
      })();
    });

    actCreate.addEventListener('click', () => {
      void (async () => {
        const title = actNewTitle.value.trim();
        if (!title) return;
        const res = (await kernelRequest('play/acts/create', { title })) as PlayActsCreateResult;
        activeActId = res.created_act_id;
        selectedSceneId = null;
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
          void (async () => {
            if (activeActId) {
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

    const renderKb = () => {
      kbSection.innerHTML = '';
      kbSection.appendChild(rowHeader('Mini Knowledgebase'));

      const who = el('div');
      who.style.fontSize = '12px';
      who.style.opacity = '0.8';
      who.style.marginBottom = '6px';
      who.textContent = selectedSceneId
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
            scene_id: selectedSceneId
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
        if (!title || !activeActId) return;
        await kernelRequest('play/scenes/create', { act_id: activeActId, title });
        await refreshScenes(activeActId);
        renderPlayInspector();
      })();
    });

    renderScenesList();
    renderSceneDetails();
    void (async () => {
      await refreshKbForSelection();
      renderKb();
    })();
  }

  async function refreshActs() {
    const res = (await kernelRequest('play/acts/list', {})) as PlayActsListResult;
    activeActId = res.active_act_id ?? null;
    actsCache = res.acts ?? [];

    // Only render The Play inspector if the user has activated it
    if (playInspectorActive) {
      renderPlayInspector();
    }
  }

  async function refreshScenes(actId: string) {
    const res = (await kernelRequest('play/scenes/list', { act_id: actId })) as PlayScenesListResult;
    scenesCache = res.scenes ?? [];
    if (selectedSceneId && !scenesCache.some((s) => s.scene_id === selectedSceneId)) {
      selectedSceneId = null;
    }
    // Only render The Play inspector if the user has activated it
    if (playInspectorActive) {
      renderPlayInspector();
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

  // Load system status
  async function refreshSystemStatus() {
    try {
      const result = await kernelRequest('tools/call', {
        name: 'linux_system_info',
        arguments: {}
      }) as { result: SystemInfoResult };

      const info = result.result ?? result as unknown as SystemInfoResult;

      const memPercent = info.memory_percent ?? 0;
      const diskPercent = info.disk_percent ?? 0;
      const loadAvg = info.load_avg ?? [0, 0, 0];

      systemStatus.innerHTML = `
        <div style="margin-bottom: 6px"><strong>${escapeHtml(info.hostname ?? 'Unknown')}</strong></div>
        <div style="opacity: 0.8; margin-bottom: 4px">${escapeHtml(info.distro ?? 'Linux')}</div>
        <div style="margin-bottom: 4px">Kernel: ${escapeHtml(info.kernel ?? 'N/A')}</div>
        <div style="margin-bottom: 4px">Uptime: ${escapeHtml(info.uptime ?? 'N/A')}</div>
        <div style="margin-bottom: 6px">
          <div style="display: flex; justify-content: space-between;">
            <span>Memory</span>
            <span>${memPercent.toFixed(0)}%</span>
          </div>
          <div style="height: 4px; background: #e5e7eb; border-radius: 2px; overflow: hidden;">
            <div style="height: 100%; width: ${memPercent}%; background: ${memPercent > 80 ? '#ef4444' : memPercent > 60 ? '#f59e0b' : '#22c55e'}"></div>
          </div>
        </div>
        <div style="margin-bottom: 6px">
          <div style="display: flex; justify-content: space-between;">
            <span>Disk (/)</span>
            <span>${diskPercent.toFixed(0)}%</span>
          </div>
          <div style="height: 4px; background: #e5e7eb; border-radius: 2px; overflow: hidden;">
            <div style="height: 100%; width: ${diskPercent}%; background: ${diskPercent > 90 ? '#ef4444' : diskPercent > 75 ? '#f59e0b' : '#22c55e'}"></div>
          </div>
        </div>
        <div style="opacity: 0.8">Load: ${loadAvg[0].toFixed(2)} ${loadAvg[1].toFixed(2)} ${loadAvg[2].toFixed(2)}</div>
      `;
    } catch (e) {
      systemStatus.innerHTML = `<span style="opacity: 0.6">Could not load system info</span>`;
    }
  }

  // Keyboard shortcuts
  document.addEventListener('keydown', (e) => {
    const chatInput = cairnView.getChatInput();

    // Ctrl+K or Cmd+K to focus input
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      chatInput.focus();
      chatInput.select();
    }

    // Ctrl+L to clear chat
    if ((e.ctrlKey || e.metaKey) && e.key === 'l') {
      e.preventDefault();
      cairnView.clearChat();
      cairnView.addChatMessage('assistant', 'Chat cleared. How can I help?');
    }

    // Ctrl+R to refresh system status
    if ((e.ctrlKey || e.metaKey) && e.key === 'r' && !e.shiftKey) {
      e.preventDefault();
      void refreshSystemStatus();
    }

    // Escape to clear input
    if (e.key === 'Escape' && document.activeElement === chatInput) {
      chatInput.value = '';
      chatInput.blur();
    }
  });

  // Initial load
  void (async () => {
    try {
      // Load system status
      await refreshSystemStatus();
      // Refresh every 30 seconds
      setInterval(() => {
        void refreshSystemStatus();
      }, 30000);

      await refreshActs();
      if (activeActId) await refreshScenes(activeActId);

      // Welcome message
      cairnView.addChatMessage('assistant', 'Welcome to Talking Rock! Ask me anything about your system or schedule. Keyboard shortcuts: Ctrl+K to focus, Ctrl+L to clear, Ctrl+R to refresh status.');
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
