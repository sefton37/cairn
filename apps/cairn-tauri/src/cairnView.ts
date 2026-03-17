/**
 * CAIRN View - Conversational interface for the Attention Minder.
 *
 * CAIRN surfaces what needs attention without being coercive:
 * - Priority-driven surfacing
 * - Calendar and time awareness
 * - Knowledge base queries
 * - Gentle nudges, never guilt-trips
 */

import { el, escapeHtml } from './dom';
import type { ChatRespondResult, ExtendedThinkingTrace, ThinkingNode, FacetCheck, Tension, ConsciousnessEvent } from './types';
import { highlight, injectSyntaxHighlightStyles } from './syntaxHighlight';

// Event type to CSS class mapping — mirrors consciousnessPane.ts for per-message rendering
const EVENT_TYPE_CLASSES: Record<string, string> = {
  PHASE_START: 'event-phase',
  PHASE_COMPLETE: 'event-phase',
  INTENT_EXTRACTED: 'event-result',
  INTENT_VERIFIED: 'event-result',
  PATTERN_MATCHED: 'event-result',
  COMPREHENSION_START: 'event-phase',
  COMPREHENSION_RESULT: 'event-result',
  DECOMPOSITION_START: 'event-phase',
  DECOMPOSITION_RESULT: 'event-result',
  REASONING_START: 'event-phase',
  REASONING_ITERATION: 'event-reasoning',
  REASONING_RESULT: 'event-result',
  COHERENCE_START: 'event-phase',
  COHERENCE_RESULT: 'event-result',
  DECISION_START: 'event-phase',
  DECISION_RESULT: 'event-result',
  EXPLORE_PASS: 'event-reasoning',
  IDEATE_PASS: 'event-reasoning',
  SYNTHESIZE_PASS: 'event-reasoning',
  LLM_CALL_START: 'event-llm',
  LLM_CALL_COMPLETE: 'event-llm',
  TOOL_CALL_START: 'event-llm',
  TOOL_CALL_COMPLETE: 'event-llm',
  MEMORY_ASSESSING: 'event-memory',
  MEMORY_CREATED: 'event-memory',
  MEMORY_NO_CHANGE: 'event-memory',
  RESPONSE_READY: 'event-result',
};

// Compact icons for consciousness event types — mirrors consciousnessPane.ts
const EVENT_TYPE_ICONS: Record<string, string> = {
  PHASE_START: '\u25B6',
  PHASE_COMPLETE: '\u2713',
  INTENT_EXTRACTED: '\u25C9',
  INTENT_VERIFIED: '\u2713',
  COMPREHENSION_START: '\u25B6',
  COMPREHENSION_RESULT: '\u2713',
  DECOMPOSITION_START: '\u25B6',
  DECOMPOSITION_RESULT: '\u2713',
  REASONING_START: '\u25B6',
  REASONING_ITERATION: '\u21BB',
  REASONING_RESULT: '\u2713',
  COHERENCE_START: '\u25B6',
  COHERENCE_RESULT: '\u2713',
  DECISION_START: '\u25B6',
  DECISION_RESULT: '\u2713',
  EXPLORE_PASS: '\u25B6',
  IDEATE_PASS: '\u25B6',
  SYNTHESIZE_PASS: '\u25B6',
  TOOL_CALL_START: '\u2699',
  TOOL_CALL_COMPLETE: '\u2713',
  LLM_CALL_START: '\u25CF',
  LLM_CALL_COMPLETE: '\u2713',
  MEMORY_ASSESSING: '\u25CB',
  MEMORY_CREATED: '\u2726',
  MEMORY_NO_CHANGE: '\u2013',
  RESPONSE_READY: '\u2714',
};

interface CairnViewCallbacks {
  onSendMessage: (message: string) => Promise<void>;
  kernelRequest: (method: string, params: unknown) => Promise<unknown>;
  onDismissCard?: (item: { entity_type: string; entity_id: string; title: string; sender_name?: string | null; sender_email?: string | null }) => void;
}

/** Full message data including LLM context for expandable details */
interface MessageData {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  // Assistant-only fields from ChatRespondResult
  thinkingSteps?: string[];
  toolCalls?: Array<{
    name: string;
    arguments: Record<string, unknown>;
    ok: boolean;
    result?: unknown;
    error?: { code: string; message: string; data?: unknown };
  }>;
  messageId?: string;
  messageType?: string;
  // Extended thinking trace for CAIRN deep reasoning
  extendedThinkingTrace?: ExtendedThinkingTrace | null;
  // Snapshot of consciousness events captured when this message was received
  consciousnessEvents?: ConsciousnessEvent[];
}

interface CairnViewState {
  chatMessages: MessageData[];
  surfacedItems: Array<{ title: string; reason: string; urgency: string }>;
}

/**
 * Creates the CAIRN conversational view.
 */
export function createCairnView(
  callbacks: CairnViewCallbacks
): {
  container: HTMLElement;
  chatHeader: HTMLElement;
  addChatMessage: (role: 'user' | 'assistant', content: string) => void;
  addAssistantMessage: (result: ChatRespondResult) => void;
  showThinking: () => void;
  hideThinking: () => void;
  clearChat: () => void;
  getChatInput: () => HTMLInputElement;
  updateSurfaced: (items: Array<{ title: string; reason: string; urgency: string; is_recurring?: boolean; recurrence_frequency?: string; act_color?: string; user_priority?: number }>) => void;
  persistAndShowFeedback: (conversationId: string, userMessageId: string, responseMessageId: string) => Promise<void>;
} {
  const state: CairnViewState = {
    chatMessages: [],
    surfacedItems: [],
  };

  // Fingerprint of current surfaced items to avoid unnecessary re-renders
  let surfacedFingerprint = '';

  // RLHF Feedback state
  let awaitingFeedback = false;
  let currentChainBlockId: string | null = null;
  let currentUserMessageId: string | null = null;
  let currentResponseMessageId: string | null = null;
  let feedbackRowElement: HTMLElement | null = null;

  // Inject syntax highlighting styles
  injectSyntaxHighlightStyles();

  // Main container
  const container = el('div');
  container.className = 'cairn-view';
  container.style.cssText = `
    display: flex;
    flex: 1;
    height: 100%;
    overflow: hidden;
  `;

  // ============ LEFT: Surfaced Items Panel ============
  const surfacedPanel = el('div');
  surfacedPanel.className = 'surfaced-panel';
  surfacedPanel.style.cssText = `
    width: 800px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    border-right: 1px solid rgba(255,255,255,0.1);
    background: rgba(0,0,0,0.1);
  `;

  // Surfaced header
  const surfacedHeader = el('div');
  surfacedHeader.style.cssText = `
    padding: 16px 20px;
    border-bottom: 1px solid rgba(255,255,255,0.1);
    background: rgba(0,0,0,0.2);
  `;

  const surfacedTitle = el('div');
  surfacedTitle.style.cssText = `
    font-size: 16px;
    font-weight: 600;
    color: #fff;
    display: flex;
    align-items: center;
    gap: 8px;
  `;
  surfacedTitle.innerHTML = '🪨 What Needs Attention';

  const surfacedSubtitle = el('div');
  surfacedSubtitle.style.cssText = `
    font-size: 12px;
    color: rgba(255,255,255,0.5);
    margin-top: 4px;
  `;
  surfacedSubtitle.textContent = 'Drag to reorder, right-click to dismiss \u2014 Cairn learns your preferences';

  surfacedHeader.appendChild(surfacedTitle);
  surfacedHeader.appendChild(surfacedSubtitle);

  // Two-column container for calendar/tasks and email
  const surfacedColumns = el('div');
  surfacedColumns.className = 'surfaced-columns';
  surfacedColumns.style.cssText = `
    flex: 1;
    display: flex;
    flex-direction: row;
    overflow: hidden;
  `;

  // Left column: Calendar & Tasks
  const calendarColumn = el('div');
  calendarColumn.className = 'surfaced-column';
  calendarColumn.style.cssText = `
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    border-right: 1px solid rgba(255,255,255,0.1);
  `;

  const calendarColumnHeader = el('div');
  calendarColumnHeader.className = 'surfaced-column-header';
  calendarColumnHeader.style.cssText = `
    padding: 10px 12px;
    font-size: 12px;
    font-weight: 600;
    color: rgba(255,255,255,0.6);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    background: rgba(0,0,0,0.1);
  `;
  calendarColumnHeader.textContent = 'Calendar & Tasks';

  const calendarList = el('div');
  calendarList.className = 'surfaced-list';
  calendarList.style.cssText = `
    flex: 1;
    overflow-y: auto;
    padding: 12px;
  `;

  calendarColumn.appendChild(calendarColumnHeader);
  calendarColumn.appendChild(calendarList);

  // Right column: Email
  const emailColumn = el('div');
  emailColumn.className = 'surfaced-column';
  emailColumn.style.cssText = `
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  `;

  const emailColumnHeader = el('div');
  emailColumnHeader.className = 'surfaced-column-header';
  emailColumnHeader.style.cssText = `
    padding: 10px 12px;
    font-size: 12px;
    font-weight: 600;
    color: rgba(255,255,255,0.6);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    background: rgba(0,0,0,0.1);
  `;
  emailColumnHeader.textContent = 'Email';

  const emailList = el('div');
  emailList.className = 'surfaced-list';
  emailList.style.cssText = `
    flex: 1;
    overflow-y: auto;
    padding: 12px;
  `;

  emailColumn.appendChild(emailColumnHeader);
  emailColumn.appendChild(emailList);

  surfacedColumns.appendChild(calendarColumn);
  surfacedColumns.appendChild(emailColumn);

  surfacedPanel.appendChild(surfacedHeader);
  surfacedPanel.appendChild(surfacedColumns);

  // ============ RIGHT: Chat Panel ============
  const chatPanel = el('div');
  chatPanel.className = 'chat-panel';
  chatPanel.style.cssText = `
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  `;

  // Chat header
  const chatHeader = el('div');
  chatHeader.style.cssText = `
    padding: 16px 20px;
    border-bottom: 1px solid rgba(255,255,255,0.1);
    background: rgba(0,0,0,0.2);
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
  `;

  const chatTitleArea = el('div');

  const chatTitle = el('div');
  chatTitle.style.cssText = `
    font-size: 16px;
    font-weight: 600;
    color: #fff;
  `;
  chatTitle.textContent = 'CAIRN';

  const chatSubtitle = el('div');
  chatSubtitle.style.cssText = `
    font-size: 12px;
    color: rgba(255,255,255,0.5);
    margin-top: 4px;
  `;
  chatSubtitle.textContent = 'Your attention minder';

  chatTitleArea.appendChild(chatTitle);
  chatTitleArea.appendChild(chatSubtitle);

  chatHeader.appendChild(chatTitleArea);

  // Chat messages area
  const chatMessages = el('div');
  chatMessages.className = 'chat-messages';
  chatMessages.style.cssText = `
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  `;

  // Welcome message
  const welcomeMsg = el('div');
  welcomeMsg.style.cssText = `
    background: rgba(var(--theme-primary-rgb, 212, 168, 86), 0.1);
    border: 1px solid rgba(var(--theme-primary-rgb, 212, 168, 86), 0.2);
    border-radius: 12px;
    padding: 16px;
    color: var(--text-primary, rgba(255,255,255,0.9));
  `;
  welcomeMsg.innerHTML = `
    <div style="font-weight: 600; margin-bottom: 8px;">CAIRN</div>
    <div style="font-size: 13px; line-height: 1.5; color: var(--text-secondary, rgba(255,255,255,0.7));">
      Your attention minder. Ask me anything, or type <kbd style="background: var(--bg-elevated, rgba(255,255,255,0.1)); padding: 2px 6px; border-radius: 4px; font-size: 12px;">/</kbd> to see what I can do.
    </div>
  `;
  chatMessages.appendChild(welcomeMsg);

  // Thunderbird integration prompt (shown if not connected and not declined)
  const thunderbirdPrompt = el('div');
  thunderbirdPrompt.style.cssText = `
    background: rgba(var(--theme-primary-rgb, 212, 168, 86), 0.1);
    border: 1px solid rgba(var(--theme-primary-rgb, 212, 168, 86), 0.3);
    border-radius: 12px;
    padding: 16px;
    color: var(--text-primary, rgba(255,255,255,0.9));
    display: none;
  `;
  chatMessages.appendChild(thunderbirdPrompt);

  // Interface for Thunderbird check result
  interface ThunderbirdCheckResult {
    installed: boolean;
    install_suggestion: string | null;
    profiles: Array<{ name: string; accounts: Array<{ email: string }> }>;
    integration_state: 'not_configured' | 'active' | 'declined';
    active_profiles: string[];
  }

  // Update Thunderbird prompt content based on state
  function updateThunderbirdPrompt(status: ThunderbirdCheckResult) {
    // Don't show if declined or active
    if (status.integration_state === 'declined' || status.integration_state === 'active') {
      thunderbirdPrompt.style.display = 'none';
      return;
    }

    const profileCount = status.profiles.length;
    const accountCount = status.profiles.reduce((sum, p) => sum + p.accounts.length, 0);

    if (!status.installed) {
      // Not installed - show install guide
      thunderbirdPrompt.style.background = 'rgba(245, 158, 11, 0.1)';
      thunderbirdPrompt.style.borderColor = 'rgba(245, 158, 11, 0.3)';
      thunderbirdPrompt.innerHTML = `
        <div style="display: flex; align-items: flex-start; gap: 12px;">
          <span style="font-size: 24px;">📅</span>
          <div style="flex: 1;">
            <div style="font-weight: 600; margin-bottom: 6px; color: #f59e0b;">Connect Your Calendar & Contacts</div>
            <div style="font-size: 13px; line-height: 1.5; color: rgba(255,255,255,0.7); margin-bottom: 12px;">
              Thunderbird isn't installed yet. I can help you track appointments and know who you're working with.
            </div>
            <div style="font-size: 12px; color: rgba(255,255,255,0.5); margin-bottom: 12px; font-family: monospace; background: rgba(0,0,0,0.2); padding: 8px; border-radius: 4px;">
              ${escapeHtml(status.install_suggestion || 'Install Thunderbird from your package manager')}
            </div>
            <div style="display: flex; gap: 8px; flex-wrap: wrap;">
              <button class="tb-dismiss" style="padding: 8px 16px; background: rgba(255,255,255,0.1); border: none; border-radius: 6px; color: rgba(255,255,255,0.7); cursor: pointer; font-size: 12px;">Not now</button>
              <button class="tb-never" style="padding: 8px 16px; background: none; border: none; color: rgba(255,255,255,0.4); cursor: pointer; font-size: 12px;">Never ask again</button>
            </div>
          </div>
        </div>
      `;
    } else {
      // Installed but not configured
      thunderbirdPrompt.style.background = 'rgba(59, 130, 246, 0.1)';
      thunderbirdPrompt.style.borderColor = 'rgba(59, 130, 246, 0.3)';
      thunderbirdPrompt.innerHTML = `
        <div style="display: flex; align-items: flex-start; gap: 12px;">
          <span style="font-size: 24px;">📅</span>
          <div style="flex: 1;">
            <div style="font-weight: 600; margin-bottom: 6px; color: #3b82f6;">Connect Your Calendar & Contacts</div>
            <div style="font-size: 13px; line-height: 1.5; color: rgba(255,255,255,0.7); margin-bottom: 12px;">
              ${profileCount > 0
                ? `Found ${profileCount} profile${profileCount > 1 ? 's' : ''} with ${accountCount} account${accountCount > 1 ? 's' : ''}. Connect to enable time-aware surfacing.`
                : 'Connect Thunderbird to help me track your calendar and contacts.'}
            </div>
            <div style="display: flex; gap: 8px; flex-wrap: wrap;">
              <button class="tb-connect" style="padding: 8px 16px; background: #3b82f6; border: none; border-radius: 6px; color: #fff; cursor: pointer; font-size: 12px; font-weight: 500;">Connect${profileCount > 0 ? ' All' : ''}</button>
              <button class="tb-dismiss" style="padding: 8px 16px; background: rgba(255,255,255,0.1); border: none; border-radius: 6px; color: rgba(255,255,255,0.7); cursor: pointer; font-size: 12px;">Not now</button>
              <button class="tb-never" style="padding: 8px 16px; background: none; border: none; color: rgba(255,255,255,0.4); cursor: pointer; font-size: 12px;">Never ask again</button>
            </div>
          </div>
        </div>
      `;
    }

    // Add event listeners
    const connectBtn = thunderbirdPrompt.querySelector('.tb-connect');
    const dismissBtn = thunderbirdPrompt.querySelector('.tb-dismiss');
    const neverBtn = thunderbirdPrompt.querySelector('.tb-never');

    if (connectBtn) {
      connectBtn.addEventListener('click', async () => {
        try {
          const profileNames = status.profiles.map(p => p.name);
          await callbacks.kernelRequest('thunderbird/configure', {
            active_profiles: profileNames,
            all_active: true,
          });
          thunderbirdPrompt.style.display = 'none';
        } catch (e) {
          console.error('Failed to connect Thunderbird:', e);
        }
      });
    }

    if (dismissBtn) {
      dismissBtn.addEventListener('click', () => {
        thunderbirdPrompt.style.display = 'none';
      });
    }

    if (neverBtn) {
      neverBtn.addEventListener('click', async () => {
        try {
          await callbacks.kernelRequest('thunderbird/decline', {});
          thunderbirdPrompt.style.display = 'none';
        } catch (e) {
          console.error('Failed to decline Thunderbird:', e);
        }
      });
    }

    thunderbirdPrompt.style.display = 'block';
  }

  // Check Thunderbird status on load
  void (async () => {
    try {
      const status = await callbacks.kernelRequest('thunderbird/check', {}) as ThunderbirdCheckResult;
      updateThunderbirdPrompt(status);
    } catch (e) {
      // Fall back to old status check
      try {
        const oldStatus = await callbacks.kernelRequest('cairn/thunderbird/status', {}) as { available: boolean };
        if (!oldStatus.available) {
          // Show simple prompt for backwards compatibility
          thunderbirdPrompt.innerHTML = `
            <div style="display: flex; align-items: flex-start; gap: 12px;">
              <span style="font-size: 24px;">📧</span>
              <div style="flex: 1;">
                <div style="font-weight: 600; margin-bottom: 6px; color: #f59e0b;">Connect Thunderbird?</div>
                <div style="font-size: 13px; line-height: 1.5; color: rgba(255,255,255,0.7);">
                  CAIRN can integrate with Thunderbird to help manage your calendar events and contacts.
                </div>
              </div>
            </div>
          `;
          thunderbirdPrompt.style.display = 'block';
        }
      } catch {
        console.log('Thunderbird status check failed:', e);
      }
    }
  })();

  // Thinking indicator (animated dots)
  const thinkingIndicator = el('div');
  thinkingIndicator.className = 'thinking-indicator';
  thinkingIndicator.style.cssText = `
    display: none;
    align-self: flex-start;
    background: rgba(255,255,255,0.1);
    border-radius: 12px;
    padding: 12px 16px;
    margin-top: 8px;
  `;
  thinkingIndicator.innerHTML = `
    <div style="display: flex; align-items: center; gap: 8px;">
      <div class="thinking-dots" style="display: flex; gap: 4px;">
        <span class="dot" style="width: 8px; height: 8px; border-radius: 50%; background: rgba(255,255,255,0.6); animation: pulse 1.4s ease-in-out infinite;"></span>
        <span class="dot" style="width: 8px; height: 8px; border-radius: 50%; background: rgba(255,255,255,0.6); animation: pulse 1.4s ease-in-out 0.2s infinite;"></span>
        <span class="dot" style="width: 8px; height: 8px; border-radius: 50%; background: rgba(255,255,255,0.6); animation: pulse 1.4s ease-in-out 0.4s infinite;"></span>
      </div>
      <span style="color: rgba(255,255,255,0.5); font-size: 13px;">Thinking...</span>
    </div>
  `;
  // Add CSS animation via style tag
  const styleTag = document.createElement('style');
  styleTag.textContent = `
    @keyframes pulse {
      0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
      40% { opacity: 1; transform: scale(1); }
    }
  `;
  document.head.appendChild(styleTag);
  chatMessages.appendChild(thinkingIndicator);

  // Chat input area
  const inputArea = el('div');
  inputArea.style.cssText = `
    padding: 16px;
    border-top: 1px solid rgba(255,255,255,0.1);
    background: rgba(0,0,0,0.1);
  `;

  const inputRow = el('div');
  inputRow.style.cssText = `
    display: flex;
    gap: 8px;
  `;

  // Command palette — surfaces Cairn capabilities when user types "/"
  const COMMANDS = [
    { cmd: 'What needs my attention right now?', label: 'attention', desc: 'What needs attention', icon: '\u{1F50E}' },
    { cmd: 'Show my calendar for today', label: 'calendar', desc: 'Today\'s calendar', icon: '\u{1F4C5}' },
    { cmd: 'What\'s coming up in the next few hours?', label: 'upcoming', desc: 'Upcoming events', icon: '\u23F0' },
    { cmd: 'Show my todos', label: 'todos', desc: 'Task list', icon: '\u2705' },
    { cmd: 'What should I focus on next?', label: 'focus', desc: 'Next priority', icon: '\u{1F3AF}' },
    { cmd: 'Show my Acts', label: 'acts', desc: 'Life areas (The Play)', icon: '\u{1F3AD}' },
    { cmd: 'How are you doing?', label: 'health', desc: 'System health check', icon: '\u{1F4CA}' },
    { cmd: 'Search my contacts for ', label: 'contacts', desc: 'Search contacts', icon: '\u{1F464}' },
    { cmd: 'Search my knowledge base for ', label: 'search', desc: 'Search knowledge', icon: '\u{1F4D6}' },
  ];

  const cmdPalette = el('div');
  cmdPalette.style.cssText = `
    display: none;
    position: absolute;
    bottom: 100%;
    left: 0;
    right: 0;
    margin-bottom: 4px;
    background: #1e1e2e;
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 8px;
    max-height: 300px;
    overflow-y: auto;
    z-index: 100;
    box-shadow: 0 -4px 16px rgba(0,0,0,0.4);
  `;

  let cmdSelectedIdx = 0;
  let cmdFiltered: typeof COMMANDS = [];

  function renderCmdPalette(filter: string) {
    const q = filter.toLowerCase();
    cmdFiltered = q
      ? COMMANDS.filter(c => c.label.includes(q) || c.desc.toLowerCase().includes(q))
      : [...COMMANDS];
    if (cmdFiltered.length === 0) {
      cmdPalette.style.display = 'none';
      return;
    }
    cmdSelectedIdx = Math.min(cmdSelectedIdx, cmdFiltered.length - 1);
    cmdPalette.innerHTML = cmdFiltered.map((c, i) => `
      <div class="cmd-item${i === cmdSelectedIdx ? ' cmd-selected' : ''}" data-idx="${i}" style="
        padding: 8px 12px;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 13px;
        color: rgba(255,255,255,0.85);
        background: ${i === cmdSelectedIdx ? 'rgba(59,130,246,0.2)' : 'transparent'};
      ">
        <span style="font-size: 16px; width: 24px; text-align: center;">${c.icon}</span>
        <span style="flex:1">${escapeHtml(c.desc)}</span>
        <span style="color: rgba(255,255,255,0.35); font-size: 11px;">/${escapeHtml(c.label)}</span>
      </div>
    `).join('');
    cmdPalette.style.display = 'block';

    cmdPalette.querySelectorAll('.cmd-item').forEach((item) => {
      item.addEventListener('mousedown', (e) => {
        e.preventDefault();
        const idx = parseInt((item as HTMLElement).dataset.idx || '0');
        selectCommand(idx);
      });
    });
  }

  function selectCommand(idx: number) {
    const c = cmdFiltered[idx];
    if (!c) return;
    closeCmdPalette();
    chatInput.value = c.cmd;
    chatInput.focus();
    // Place cursor at end (useful for commands that expect a query suffix)
    chatInput.setSelectionRange(c.cmd.length, c.cmd.length);
  }

  function closeCmdPalette() {
    cmdPalette.style.display = 'none';
    cmdSelectedIdx = 0;
  }

  const chatInput = el('input') as HTMLInputElement;
  chatInput.type = 'text';
  chatInput.placeholder = 'Ask CAIRN anything... (/ for commands)';
  chatInput.style.cssText = `
    flex: 1;
    padding: 12px 16px;
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 8px;
    color: #fff;
    font-size: 14px;
    outline: none;
  `;

  const sendBtn = el('button');
  sendBtn.textContent = 'Send';
  sendBtn.style.cssText = `
    padding: 12px 20px;
    background: #3b82f6;
    border: none;
    border-radius: 8px;
    color: #fff;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.2s;
  `;

  const handleSend = async () => {
    // Block sending if awaiting feedback
    if (awaitingFeedback) {
      // Show a brief message in the chat
      const warningEl = el('div');
      warningEl.style.cssText = `
        align-self: center;
        background: rgba(245, 158, 11, 0.15);
        border: 1px solid rgba(245, 158, 11, 0.3);
        border-radius: 8px;
        padding: 8px 16px;
        color: #fbbf24;
        font-size: 13px;
        margin: 8px 0;
      `;
      warningEl.textContent = 'Please provide feedback on the previous response first';
      chatMessages.insertBefore(warningEl, thinkingIndicator);
      chatMessages.scrollTop = chatMessages.scrollHeight;
      // Remove after 3 seconds
      setTimeout(() => warningEl.remove(), 3000);
      return;
    }

    const message = chatInput.value.trim();
    if (!message) return;

    chatInput.value = '';
    addChatMessage('user', message);

    // Start consciousness streaming before sending
    void startConsciousnessPolling();

    await callbacks.onSendMessage(message);
  };

  chatInput.addEventListener('keydown', (e) => {
    // Command palette navigation
    if (cmdPalette.style.display !== 'none') {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        cmdSelectedIdx = Math.min(cmdSelectedIdx + 1, cmdFiltered.length - 1);
        renderCmdPalette(chatInput.value.slice(1));
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        cmdSelectedIdx = Math.max(cmdSelectedIdx - 1, 0);
        renderCmdPalette(chatInput.value.slice(1));
        return;
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        selectCommand(cmdSelectedIdx);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        closeCmdPalette();
        chatInput.value = '';
        return;
      }
    } else if (e.key === 'Enter') {
      handleSend();
    }
  });

  chatInput.addEventListener('input', () => {
    const val = chatInput.value;
    if (val.startsWith('/') && val.indexOf(' ') === -1) {
      renderCmdPalette(val.slice(1));
    } else {
      closeCmdPalette();
    }
  });

  sendBtn.addEventListener('click', handleSend);

  // inputRow needs relative positioning for the palette to anchor
  inputRow.style.position = 'relative';
  inputRow.appendChild(cmdPalette);
  inputRow.appendChild(chatInput);
  inputRow.appendChild(sendBtn);
  inputArea.appendChild(inputRow);

  chatPanel.appendChild(chatHeader);
  chatPanel.appendChild(chatMessages);
  chatPanel.appendChild(inputArea);

  // Add event type border styles used in both the old consciousness pane and the
  // new per-message details panel consciousness section.
  const consciousnessEventStyles = document.createElement('style');
  consciousnessEventStyles.textContent = `
    .event-phase   { border-left: 3px solid #3b82f6; }
    .event-result  { border-left: 3px solid #22c55e; }
    .event-llm     { border-left: 3px solid #a78bfa; }
    .event-reasoning { border-left: 3px solid #f59e0b; }
    .event-memory  { border-left: 3px solid #ec4899; }
  `;
  document.head.appendChild(consciousnessEventStyles);

  // Consciousness polling state
  let consciousnessPolling = false;
  let consciousnessEvents: ConsciousnessEvent[] = [];
  let consciousnessIndex = 0;

  async function startConsciousnessPolling() {
    consciousnessPolling = true;
    consciousnessEvents = [];
    consciousnessIndex = 0;

    // Note: consciousness/start is called by cairn/chat_async, no need to call it here
    // This avoids race conditions where we might clear events after they start being emitted

    // Poll for events — accumulated into consciousnessEvents[] for per-message snapshot
    const pollInterval = setInterval(async () => {
      if (!consciousnessPolling) {
        clearInterval(pollInterval);
        return;
      }

      try {
        const result = await callbacks.kernelRequest('consciousness/poll', {
          since_index: consciousnessIndex,
        }) as { events: ConsciousnessEvent[]; next_index: number };

        if (result.events && result.events.length > 0) {
          consciousnessEvents.push(...result.events);
          consciousnessIndex = result.next_index;
        }
      } catch (e) {
        console.warn('Consciousness poll failed:', e);
      }
    }, 200); // Poll every 200ms
  }

  function stopConsciousnessPolling() {
    // Events accumulated in consciousnessEvents[] will be snapshotted by addAssistantMessage
    consciousnessPolling = false;
  }

  // Assemble container
  container.appendChild(surfacedPanel);
  container.appendChild(chatPanel);

  // ============ Functions ============

  /**
   * Render a single consciousness event as an HTML string for the details panel.
   * Mirrors the rendering logic from consciousnessPane.ts but as a static string.
   */
  function renderConsciousnessEventHtml(
    event: ConsciousnessEvent,
    index: number,
    expandedSet?: Set<number>,
  ): string {
    const typeClass = EVENT_TYPE_CLASSES[event.type] || 'event-phase';
    const icon = EVENT_TYPE_ICONS[event.type] || '\u2022';
    const isExpanded = expandedSet ? expandedSet.has(index) : false;
    const hasContent = event.content && event.content.length > 0;

    let contentHtml = '';
    if (hasContent && isExpanded) {
      const escapedContent = event.content
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\n/g, '<br>');
      contentHtml = `<div style="padding: 6px 8px 6px 22px; background: rgba(0,0,0,0.15); font-size: 11px; font-family: monospace; color: rgba(255,255,255,0.6); line-height: 1.4; white-space: pre-wrap; word-break: break-word;">${escapedContent}</div>`;
    }

    return `
      <div class="consciousness-event ${typeClass}" data-index="${index}" style="margin-bottom: 2px; border-radius: 4px; overflow: hidden;">
        <div style="display: flex; align-items: center; gap: 6px; padding: 4px 8px; background: rgba(255,255,255,0.03); cursor: pointer;">
          <span style="font-size: 11px; flex-shrink: 0; opacity: 0.6;">${icon}</span>
          <span style="flex: 1; font-size: 12px; font-weight: 500; color: rgba(255,255,255,0.85); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(event.title)}</span>
          ${hasContent ? `<button class="consciousness-expand-btn" style="background: none; border: none; color: rgba(255,255,255,0.3); font-size: 11px; cursor: pointer; padding: 1px 4px; flex-shrink: 0;">${isExpanded ? '\u2212' : '+'}</button>` : ''}
        </div>
        ${contentHtml}
      </div>
    `;
  }

  function renderChatMessage(data: MessageData): HTMLElement {
    const { role, content, thinkingSteps, toolCalls, extendedThinkingTrace, consciousnessEvents: msgConsciousnessEvents } = data;
    const hasDetails = role === 'assistant' && (
      (thinkingSteps && thinkingSteps.length > 0) ||
      (toolCalls && toolCalls.length > 0) ||
      (msgConsciousnessEvents && msgConsciousnessEvents.length > 0)
    );
    const hasExtendedThinking = role === 'assistant' && extendedThinkingTrace != null;

    const msgWrapper = el('div');
    msgWrapper.style.cssText = `
      max-width: 85%;
      ${role === 'user' ? 'align-self: flex-end; margin-left: auto;' : 'align-self: flex-start;'}
    `;

    // Extended Thinking panel (above the message when present)
    if (hasExtendedThinking && extendedThinkingTrace) {
      const thinkingPanel = renderExtendedThinkingPanel(extendedThinkingTrace);
      msgWrapper.appendChild(thinkingPanel);
    }

    // Main message bubble
    const msgEl = el('div');
    msgEl.style.cssText = `
      padding: 12px 16px;
      border-radius: 12px;
      font-size: 14px;
      line-height: 1.5;
      ${role === 'user'
        ? 'background: #3b82f6; color: #fff;'
        : 'background: rgba(255,255,255,0.1); color: rgba(255,255,255,0.9);'
      }
    `;
    // Render content with markdown and code block support
    msgEl.innerHTML = renderContentWithCodeBlocks(content);
    msgWrapper.appendChild(msgEl);

    // Expandable details for assistant messages
    if (hasDetails) {
      const detailsToggle = el('button');
      detailsToggle.textContent = 'Show details';
      detailsToggle.style.cssText = `
        background: none;
        border: none;
        color: rgba(255,255,255,0.4);
        font-size: 11px;
        padding: 4px 0;
        cursor: pointer;
        margin-top: 4px;
      `;

      const detailsPanel = el('div');
      detailsPanel.style.cssText = `
        display: none;
        margin-top: 8px;
        padding: 12px;
        background: rgba(0,0,0,0.3);
        border-radius: 8px;
        font-size: 12px;
        max-height: 400px;
        overflow-y: auto;
      `;

      // Build details content
      let detailsHTML = '';

      if (thinkingSteps && thinkingSteps.length > 0) {
        detailsHTML += `
          <div style="margin-bottom: 12px;">
            <div style="color: #60a5fa; font-weight: 600; margin-bottom: 6px;">Thinking Steps</div>
            <div style="color: rgba(255,255,255,0.7); white-space: pre-wrap; font-family: monospace; font-size: 11px;">
              ${thinkingSteps.map((step, i) => `${i + 1}. ${escapeHtml(step)}`).join('\n')}
            </div>
          </div>
        `;
      }

      if (toolCalls && toolCalls.length > 0) {
        detailsHTML += `
          <div>
            <div style="color: #60a5fa; font-weight: 600; margin-bottom: 6px;">Tool Calls</div>
            ${toolCalls.map(tc => `
              <div style="margin-bottom: 8px; padding: 8px; background: rgba(255,255,255,0.05); border-radius: 4px;">
                <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px;">
                  <span style="color: #f59e0b; font-weight: 500;">${escapeHtml(tc.name)}</span>
                  <span style="font-size: 10px; padding: 2px 6px; border-radius: 4px; ${tc.ok ? 'background: rgba(34,197,94,0.2); color: #22c55e;' : 'background: rgba(239,68,68,0.2); color: #ef4444;'}">${tc.ok ? 'OK' : 'ERROR'}</span>
                </div>
                <div style="color: rgba(255,255,255,0.5); font-family: monospace; font-size: 10px; word-break: break-all;">
                  Args: ${escapeHtml(JSON.stringify(tc.arguments, null, 2).substring(0, 200))}${JSON.stringify(tc.arguments).length > 200 ? '...' : ''}
                </div>
                ${tc.error ? `<div style="color: #ef4444; margin-top: 4px;">Error: ${escapeHtml(tc.error.message)}</div>` : ''}
              </div>
            `).join('')}
          </div>
        `;
      }

      // Consciousness Stream section — rendered last so thinking/tool sections are visible first
      if (msgConsciousnessEvents && msgConsciousnessEvents.length > 0) {
        detailsHTML += `
          <div style="margin-top: 12px;">
            <div style="color: #a78bfa; font-weight: 600; margin-bottom: 6px;">
              Consciousness Stream (${msgConsciousnessEvents.length} events)
            </div>
            <div class="details-consciousness-events" style="max-height: 200px; overflow-y: auto;">
              ${msgConsciousnessEvents.map((evt, i) => renderConsciousnessEventHtml(evt, i)).join('')}
            </div>
          </div>
        `;
      }

      detailsPanel.innerHTML = detailsHTML;

      // Attach expand/collapse handlers for consciousness events inside the details panel
      const consciousnessContainer = detailsPanel.querySelector('.details-consciousness-events');
      if (consciousnessContainer) {
        const expandedSet = new Set<number>();
        consciousnessContainer.addEventListener('click', (e: Event) => {
          const btn = (e.target as HTMLElement).closest('.consciousness-expand-btn');
          if (!btn) return;
          const eventEl = btn.closest('.consciousness-event');
          if (!eventEl) return;
          const idx = parseInt(eventEl.getAttribute('data-index') || '0', 10);
          if (expandedSet.has(idx)) {
            expandedSet.delete(idx);
          } else {
            expandedSet.add(idx);
          }
          // Re-render events with updated expanded state
          if (msgConsciousnessEvents) {
            (consciousnessContainer as HTMLElement).innerHTML = msgConsciousnessEvents
              .map((evt, i) => renderConsciousnessEventHtml(evt, i, expandedSet))
              .join('');
          }
        });
      }

      let expanded = false;
      detailsToggle.addEventListener('click', () => {
        expanded = !expanded;
        detailsPanel.style.display = expanded ? 'block' : 'none';
        detailsToggle.textContent = expanded ? 'Hide details' : 'Show details';
      });

      msgWrapper.appendChild(detailsToggle);
      msgWrapper.appendChild(detailsPanel);
    }

    return msgWrapper;
  }

  /** Render the Extended Thinking collapsible panel */
  function renderExtendedThinkingPanel(trace: ExtendedThinkingTrace): HTMLElement {
    const panel = el('div');
    panel.className = 'extended-thinking-panel';
    panel.style.cssText = `
      margin-bottom: 12px;
      border: 1px solid rgba(147, 51, 234, 0.3);
      border-radius: 12px;
      background: rgba(147, 51, 234, 0.05);
      overflow: hidden;
    `;

    // Summary counts for collapsed view
    const understoodCount = trace.understood?.length || 0;
    const ambiguousCount = trace.ambiguous?.length || 0;
    const assumptionCount = trace.assumptions?.length || 0;
    const tensionCount = trace.tensions?.length || 0;
    const confidencePercent = Math.round((trace.final_confidence || 0) * 100);

    // Header (always visible)
    const header = el('div');
    header.style.cssText = `
      padding: 12px 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      cursor: pointer;
      background: rgba(147, 51, 234, 0.1);
    `;
    header.innerHTML = `
      <div style="display: flex; align-items: center; gap: 8px;">
        <span style="font-size: 16px;">🧠</span>
        <span style="font-weight: 600; color: #a78bfa;">CAIRN's Thinking</span>
        <span style="font-size: 11px; padding: 2px 8px; border-radius: 10px; background: rgba(147, 51, 234, 0.2); color: #c4b5fd;">
          ${confidencePercent}% confident
        </span>
      </div>
      <div style="display: flex; align-items: center; gap: 12px;">
        <div style="display: flex; gap: 8px; font-size: 11px; color: rgba(255,255,255,0.5);">
          ${understoodCount > 0 ? `<span title="Understood">✓ ${understoodCount}</span>` : ''}
          ${ambiguousCount > 0 ? `<span title="Ambiguous" style="color: #fbbf24;">? ${ambiguousCount}</span>` : ''}
          ${assumptionCount > 0 ? `<span title="Assumptions" style="color: #60a5fa;">⚠ ${assumptionCount}</span>` : ''}
          ${tensionCount > 0 ? `<span title="Tensions" style="color: #f87171;">⚡ ${tensionCount}</span>` : ''}
        </div>
        <span class="expand-icon" style="color: rgba(255,255,255,0.4); transition: transform 0.2s;">▼</span>
      </div>
    `;

    // Content (collapsible)
    const content = el('div');
    content.className = 'thinking-content';
    content.style.cssText = `
      display: none;
      padding: 16px;
      border-top: 1px solid rgba(147, 51, 234, 0.2);
      max-height: 400px;
      overflow-y: auto;
    `;

    // Build content sections
    let contentHTML = '';

    // Phase 1: What was understood
    if (understoodCount > 0) {
      contentHTML += `
        <div style="margin-bottom: 16px;">
          <div style="display: flex; align-items: center; gap: 6px; color: #22c55e; font-weight: 600; margin-bottom: 8px;">
            <span>✓</span>
            <span>Understood</span>
          </div>
          <ul style="margin: 0; padding-left: 20px; color: rgba(255,255,255,0.8); font-size: 13px; line-height: 1.6;">
            ${trace.understood.map(node => `<li>${escapeHtml(node.content)} <span style="color: rgba(255,255,255,0.4); font-size: 11px;">(${Math.round(node.confidence * 100)}%)</span></li>`).join('')}
          </ul>
        </div>
      `;
    }

    // Ambiguous items
    if (ambiguousCount > 0) {
      contentHTML += `
        <div style="margin-bottom: 16px;">
          <div style="display: flex; align-items: center; gap: 6px; color: #fbbf24; font-weight: 600; margin-bottom: 8px;">
            <span>?</span>
            <span>Ambiguous</span>
          </div>
          <ul style="margin: 0; padding-left: 20px; color: rgba(255,255,255,0.8); font-size: 13px; line-height: 1.6;">
            ${trace.ambiguous.map(node => `<li>${escapeHtml(node.content)}</li>`).join('')}
          </ul>
        </div>
      `;
    }

    // Phase 2: Assumptions made
    if (assumptionCount > 0) {
      contentHTML += `
        <div style="margin-bottom: 16px;">
          <div style="display: flex; align-items: center; gap: 6px; color: #60a5fa; font-weight: 600; margin-bottom: 8px;">
            <span>⚠</span>
            <span>Assumptions I made</span>
          </div>
          <ul style="margin: 0; padding-left: 20px; color: rgba(255,255,255,0.8); font-size: 13px; line-height: 1.6;">
            ${trace.assumptions.map(node => `<li>${escapeHtml(node.content)} <span style="color: rgba(255,255,255,0.4); font-size: 11px;">(${Math.round(node.confidence * 100)}%)</span></li>`).join('')}
          </ul>
        </div>
      `;
    }

    // Questions for user
    if (trace.questions_for_user && trace.questions_for_user.length > 0) {
      contentHTML += `
        <div style="margin-bottom: 16px;">
          <div style="display: flex; align-items: center; gap: 6px; color: #c084fc; font-weight: 600; margin-bottom: 8px;">
            <span>❓</span>
            <span>Questions for you</span>
          </div>
          <ul style="margin: 0; padding-left: 20px; color: rgba(255,255,255,0.8); font-size: 13px; line-height: 1.6;">
            ${trace.questions_for_user.map(q => `<li>${escapeHtml(q)}</li>`).join('')}
          </ul>
        </div>
      `;
    }

    // Phase 3: Identity checks
    if (trace.identity_facets_checked && trace.identity_facets_checked.length > 0) {
      contentHTML += `
        <div style="margin-bottom: 16px;">
          <div style="display: flex; align-items: center; gap: 6px; color: #a78bfa; font-weight: 600; margin-bottom: 8px;">
            <span>🔍</span>
            <span>Checked against your identity</span>
          </div>
          <div style="display: flex; flex-direction: column; gap: 8px;">
            ${trace.identity_facets_checked.map(fc => {
              const alignmentColor = fc.alignment > 0.3 ? '#22c55e' : fc.alignment < -0.3 ? '#ef4444' : '#fbbf24';
              const alignmentText = fc.alignment > 0.3 ? 'aligns' : fc.alignment < -0.3 ? 'conflicts' : 'neutral';
              return `
                <div style="padding: 8px 12px; background: rgba(255,255,255,0.05); border-radius: 6px; font-size: 13px;">
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="color: #fff;">"${escapeHtml(fc.facet_name)}"</span>
                    <span style="color: ${alignmentColor};">— ${alignmentText} (${fc.alignment.toFixed(1)})</span>
                  </div>
                  <div style="color: rgba(255,255,255,0.5); font-size: 11px; margin-top: 4px;">
                    From: ${escapeHtml(fc.facet_source)}
                  </div>
                </div>
              `;
            }).join('')}
          </div>
        </div>
      `;
    }

    // Tensions detected
    if (tensionCount > 0) {
      contentHTML += `
        <div style="margin-bottom: 16px;">
          <div style="display: flex; align-items: center; gap: 6px; color: #f87171; font-weight: 600; margin-bottom: 8px;">
            <span>⚡</span>
            <span>Tensions detected</span>
          </div>
          <div style="display: flex; flex-direction: column; gap: 8px;">
            ${trace.tensions.map(t => {
              const severityColor = t.severity === 'high' ? '#ef4444' : t.severity === 'medium' ? '#f97316' : '#fbbf24';
              return `
                <div style="padding: 12px; background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.2); border-radius: 8px;">
                  <div style="font-size: 13px; color: #fff; margin-bottom: 6px;">
                    ${escapeHtml(t.description)}
                  </div>
                  <div style="font-size: 11px; color: rgba(255,255,255,0.6); margin-bottom: 6px;">
                    Your "<span style="color: #a78bfa;">${escapeHtml(t.identity_facet)}</span>" vs
                    "<span style="color: #60a5fa;">${escapeHtml(t.prompt_aspect)}</span>"
                  </div>
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 10px; padding: 2px 6px; border-radius: 4px; background: ${severityColor}20; color: ${severityColor}; text-transform: uppercase;">
                      ${t.severity}
                    </span>
                    <span style="font-size: 11px; color: rgba(255,255,255,0.5);">
                      ${escapeHtml(t.recommendation)}
                    </span>
                  </div>
                </div>
              `;
            }).join('')}
          </div>
        </div>
      `;
    }

    // Decision summary
    const decisionIcon = trace.decision === 'respond' ? '✅' : trace.decision === 'ask' ? '❓' : '⏸️';
    const decisionText = trace.decision === 'respond' ? 'Proceeding with response' :
                         trace.decision === 'ask' ? 'Need to ask you first' : 'Deferring for later';
    contentHTML += `
      <div style="padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.1);">
        <div style="display: flex; align-items: center; gap: 8px; font-size: 12px;">
          <span>${decisionIcon}</span>
          <span style="color: rgba(255,255,255,0.6);">Decision: <span style="color: #fff;">${decisionText}</span></span>
        </div>
      </div>
    `;

    content.innerHTML = contentHTML;

    // Toggle behavior
    let expanded = false;
    const expandIcon = header.querySelector('.expand-icon') as HTMLElement;

    header.addEventListener('click', () => {
      expanded = !expanded;
      content.style.display = expanded ? 'block' : 'none';
      if (expandIcon) {
        expandIcon.style.transform = expanded ? 'rotate(180deg)' : 'rotate(0deg)';
      }
    });

    panel.appendChild(header);
    panel.appendChild(content);

    return panel;
  }

  /**
   * Render a plain-text segment with basic markdown support.
   * Escapes HTML, applies inline and block-level markdown transforms,
   * then converts remaining newlines to <br>.
   *
   * Supported:
   *   **text**       → <strong>text</strong>
   *   ### heading    → bold heading (h3-ish)
   *   ## heading     → bold heading (h2-ish)
   *   - item / * item → indented bullet
   *   1. item        → indented numbered item
   */
  function renderMarkdownSegment(text: string): string {
    // SAFETY: HTML escaping MUST happen first — the regex transforms below
    // inject safe HTML tags and assume all user content is already escaped.
    let escaped = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');

    // Inline: **bold**
    escaped = escaped.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // Block-level: process line by line
    const lines = escaped.split('\n');
    const rendered = lines.map((line) => {
      if (/^### (.+)$/.test(line)) {
        return `<strong style="font-size: 15px;">${line.replace(/^### /, '')}</strong>`;
      }
      if (/^## (.+)$/.test(line)) {
        return `<strong style="font-size: 16px;">${line.replace(/^## /, '')}</strong>`;
      }
      if (/^[*-] (.+)$/.test(line)) {
        return `&nbsp;&nbsp;&bull;&nbsp;${line.replace(/^[*-] /, '')}`;
      }
      if (/^\d+\. (.+)$/.test(line)) {
        const num = line.match(/^(\d+)\. /)![1];
        return `&nbsp;&nbsp;${num}.&nbsp;${line.replace(/^\d+\. /, '')}`;
      }
      return line;
    });

    return rendered.join('<br>');
  }

  /**
   * Parse content and render code blocks with syntax highlighting,
   * plus basic markdown in all non-code segments.
   * Handles markdown-style ``` code blocks.
   */
  function renderContentWithCodeBlocks(content: string): string {
    // Match code blocks: ```language\ncode\n```
    const codeBlockRegex = /```(\w*)\n([\s\S]*?)```/g;
    let result = '';
    let lastIndex = 0;

    for (const match of content.matchAll(codeBlockRegex)) {
      const [fullMatch, language, code] = match;
      const index = match.index!;

      // Add text before the code block with markdown rendering
      if (index > lastIndex) {
        result += renderMarkdownSegment(content.slice(lastIndex, index));
      }

      // Add the highlighted code block
      const lang = language || 'text';
      const safeLang = escapeHtml(lang);
      const highlightedCode = highlight(code.trimEnd(), lang);
      result += `
        <div style="
          margin: 8px 0;
          background: rgba(0,0,0,0.4);
          border-radius: 8px;
          overflow: hidden;
        ">
          <div style="
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 6px 12px;
            background: rgba(0,0,0,0.3);
            font-size: 11px;
            color: rgba(255,255,255,0.5);
          ">
            <span>${safeLang}</span>
          </div>
          <pre style="
            margin: 0;
            padding: 12px;
            font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
            font-size: 12px;
            line-height: 1.5;
            overflow-x: auto;
            white-space: pre-wrap;
            word-break: break-word;
          "><code>${highlightedCode}</code></pre>
        </div>
      `;

      lastIndex = index + fullMatch.length;
    }

    // Add any remaining text after the last code block
    if (lastIndex < content.length) {
      result += renderMarkdownSegment(content.slice(lastIndex));
    }

    return result;
  }

  function addChatMessage(role: 'user' | 'assistant', content: string): void {
    const data: MessageData = { role, content, timestamp: new Date() };
    state.chatMessages.push(data);
    const msgEl = renderChatMessage(data);
    // Insert before thinking indicator
    chatMessages.insertBefore(msgEl, thinkingIndicator);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function addAssistantMessage(result: ChatRespondResult): void {
    // If this response requires user approval, render the approval widget instead
    if (result.pending_approval_id) {
      const widget = renderApprovalWidget(result.pending_approval_id, result.answer);
      chatMessages.insertBefore(widget, thinkingIndicator);
      chatMessages.scrollTop = chatMessages.scrollHeight;
      return;
    }

    // Snapshot consciousness events accumulated during this response. The defensive copy
    // is required because startConsciousnessPolling resets the array on the next message,
    // which would clear events from all previously rendered messages without a copy.
    // This relies on hideThinking() (which stops polling) being called before
    // addAssistantMessage() — currently guaranteed by main.ts lines 565/570.
    const data: MessageData = {
      role: 'assistant',
      content: result.answer,
      timestamp: new Date(),
      thinkingSteps: result.thinking_steps,
      toolCalls: result.tool_calls,
      messageId: result.message_id,
      messageType: result.message_type,
      extendedThinkingTrace: result.extended_thinking_trace,
      consciousnessEvents: consciousnessEvents.length > 0
        ? [...consciousnessEvents]  // defensive copy — see comment above
        : undefined,
    };
    state.chatMessages.push(data);
    const msgEl = renderChatMessage(data);
    // Insert before thinking indicator
    chatMessages.insertBefore(msgEl, thinkingIndicator);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function renderApprovalWidget(approvalId: string, explanation: string): HTMLElement {
    const container = el('div');
    container.className = 'approval-widget';
    container.style.cssText = `
      background: rgba(234, 179, 8, 0.08);
      border: 1px solid rgba(234, 179, 8, 0.3);
      border-radius: 12px;
      padding: 16px;
      margin: 8px 0;
    `;

    // Explanation text
    const textEl = el('div');
    textEl.style.cssText = `
      color: rgba(255, 255, 255, 0.9);
      font-size: 14px;
      line-height: 1.5;
      margin-bottom: 12px;
      white-space: pre-wrap;
    `;
    textEl.textContent = explanation;

    // Button row
    const btnRow = el('div');
    btnRow.style.cssText = `
      display: flex;
      align-items: center;
      gap: 12px;
    `;

    const approveBtn = el('button');
    approveBtn.className = 'approval-btn approve';
    approveBtn.style.cssText = `
      background: rgba(34, 197, 94, 0.15);
      border: 1px solid rgba(34, 197, 94, 0.4);
      border-radius: 8px;
      padding: 8px 20px;
      color: #22c55e;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
    `;
    approveBtn.textContent = 'Approve';
    approveBtn.addEventListener('mouseenter', () => {
      approveBtn.style.background = 'rgba(34, 197, 94, 0.25)';
    });
    approveBtn.addEventListener('mouseleave', () => {
      approveBtn.style.background = 'rgba(34, 197, 94, 0.15)';
    });

    const rejectBtn = el('button');
    rejectBtn.className = 'approval-btn reject';
    rejectBtn.style.cssText = `
      background: rgba(239, 68, 68, 0.15);
      border: 1px solid rgba(239, 68, 68, 0.4);
      border-radius: 8px;
      padding: 8px 20px;
      color: #ef4444;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
    `;
    rejectBtn.textContent = "Don't Approve";
    rejectBtn.addEventListener('mouseenter', () => {
      rejectBtn.style.background = 'rgba(239, 68, 68, 0.25)';
    });
    rejectBtn.addEventListener('mouseleave', () => {
      rejectBtn.style.background = 'rgba(239, 68, 68, 0.15)';
    });

    async function handleApproval(action: 'approve' | 'reject') {
      // Disable buttons during in-flight request
      approveBtn.disabled = true;
      rejectBtn.disabled = true;
      approveBtn.style.opacity = '0.5';
      rejectBtn.style.opacity = '0.5';
      approveBtn.style.cursor = 'default';
      rejectBtn.style.cursor = 'default';

      try {
        const result = await callbacks.kernelRequest('approval/respond', {
          approval_id: approvalId,
          action,
        }) as { status: string; result?: { answer?: string } };

        // Replace widget content with outcome
        if (action === 'approve' && result.result?.answer) {
          // Show the execution result as a normal assistant message
          textEl.textContent = result.result.answer;
          container.style.borderColor = 'rgba(34, 197, 94, 0.3)';
          container.style.background = 'rgba(34, 197, 94, 0.05)';
          btnRow.remove();
        } else if (action === 'reject') {
          textEl.textContent = 'Cancelled.';
          textEl.style.color = 'rgba(255, 255, 255, 0.5)';
          container.style.borderColor = 'rgba(239, 68, 68, 0.2)';
          container.style.background = 'rgba(239, 68, 68, 0.03)';
          btnRow.remove();
        } else {
          textEl.textContent = 'Approved, but no result was returned.';
          btnRow.remove();
        }
      } catch (err) {
        textEl.textContent = `Error: ${err instanceof Error ? err.message : 'Unknown error'}`;
        container.style.borderColor = 'rgba(239, 68, 68, 0.3)';
        btnRow.remove();
      }

      chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    approveBtn.addEventListener('click', () => handleApproval('approve'));
    rejectBtn.addEventListener('click', () => handleApproval('reject'));

    btnRow.appendChild(approveBtn);
    btnRow.appendChild(rejectBtn);
    container.appendChild(textEl);
    container.appendChild(btnRow);

    return container;
  }

  function showThinking(): void {
    thinkingIndicator.style.display = 'flex';
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function hideThinking(): void {
    thinkingIndicator.style.display = 'none';
    // Stop consciousness polling when response is received
    stopConsciousnessPolling();
  }

  /** Create and show the feedback row UI */
  function showFeedbackRow(): void {
    // Remove any existing feedback row
    if (feedbackRowElement) {
      feedbackRowElement.remove();
    }

    feedbackRowElement = el('div');
    feedbackRowElement.className = 'feedback-row';
    feedbackRowElement.style.cssText = `
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 16px;
      padding: 12px 16px;
      background: rgba(147, 51, 234, 0.1);
      border: 1px solid rgba(147, 51, 234, 0.3);
      border-radius: 12px;
      margin: 8px 0;
    `;

    const label = el('span');
    label.style.cssText = `
      color: rgba(255,255,255,0.8);
      font-size: 13px;
    `;
    label.textContent = 'Was this helpful?';

    const thumbsUp = el('button');
    thumbsUp.className = 'feedback-btn feedback-up';
    thumbsUp.style.cssText = `
      background: rgba(34, 197, 94, 0.15);
      border: 1px solid rgba(34, 197, 94, 0.3);
      border-radius: 8px;
      padding: 8px 16px;
      color: #22c55e;
      font-size: 18px;
      cursor: pointer;
      transition: all 0.2s;
      display: flex;
      align-items: center;
      gap: 6px;
    `;
    thumbsUp.innerHTML = '<span>👍</span><span style="font-size: 12px;">Yes</span>';
    thumbsUp.addEventListener('mouseenter', () => {
      thumbsUp.style.background = 'rgba(34, 197, 94, 0.25)';
    });
    thumbsUp.addEventListener('mouseleave', () => {
      thumbsUp.style.background = 'rgba(34, 197, 94, 0.15)';
    });
    thumbsUp.addEventListener('click', () => submitFeedback(5));

    const thumbsDown = el('button');
    thumbsDown.className = 'feedback-btn feedback-down';
    thumbsDown.style.cssText = `
      background: rgba(239, 68, 68, 0.15);
      border: 1px solid rgba(239, 68, 68, 0.3);
      border-radius: 8px;
      padding: 8px 16px;
      color: #ef4444;
      font-size: 18px;
      cursor: pointer;
      transition: all 0.2s;
      display: flex;
      align-items: center;
      gap: 6px;
    `;
    thumbsDown.innerHTML = '<span>👎</span><span style="font-size: 12px;">No</span>';
    thumbsDown.addEventListener('mouseenter', () => {
      thumbsDown.style.background = 'rgba(239, 68, 68, 0.25)';
    });
    thumbsDown.addEventListener('mouseleave', () => {
      thumbsDown.style.background = 'rgba(239, 68, 68, 0.15)';
    });
    thumbsDown.addEventListener('click', () => submitFeedback(1));

    feedbackRowElement.appendChild(label);
    feedbackRowElement.appendChild(thumbsUp);
    feedbackRowElement.appendChild(thumbsDown);

    // Insert before thinking indicator
    chatMessages.insertBefore(feedbackRowElement, thinkingIndicator);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    // Disable the input visually
    chatInput.style.opacity = '0.5';
    chatInput.placeholder = 'Please provide feedback first...';
    sendBtn.style.opacity = '0.5';
    sendBtn.style.pointerEvents = 'none';
  }

  /** Submit feedback for the current reasoning chain */
  async function submitFeedback(rating: number): Promise<void> {
    if (!currentChainBlockId) {
      console.warn('No chain block ID for feedback');
      return;
    }

    try {
      await callbacks.kernelRequest('reasoning/feedback', {
        chain_block_id: currentChainBlockId,
        rating,
      });

      // Update feedback row to show submitted state
      if (feedbackRowElement) {
        const isPositive = rating === 5;
        feedbackRowElement.innerHTML = `
          <span style="color: ${isPositive ? '#22c55e' : '#ef4444'}; font-size: 14px;">
            ${isPositive ? '👍' : '👎'} Thanks for your feedback!
          </span>
        `;
        feedbackRowElement.style.background = isPositive
          ? 'rgba(34, 197, 94, 0.1)'
          : 'rgba(239, 68, 68, 0.1)';
        feedbackRowElement.style.borderColor = isPositive
          ? 'rgba(34, 197, 94, 0.3)'
          : 'rgba(239, 68, 68, 0.3)';

        // Fade out after 2 seconds
        setTimeout(() => {
          if (feedbackRowElement) {
            feedbackRowElement.style.transition = 'opacity 0.5s';
            feedbackRowElement.style.opacity = '0';
            setTimeout(() => feedbackRowElement?.remove(), 500);
          }
        }, 2000);
      }

      // Re-enable input
      awaitingFeedback = false;
      currentChainBlockId = null;
      chatInput.style.opacity = '1';
      chatInput.placeholder = 'Ask CAIRN anything...';
      sendBtn.style.opacity = '1';
      sendBtn.style.pointerEvents = 'auto';

    } catch (e) {
      console.error('Failed to submit feedback:', e);
    }
  }

  /** Persist consciousness events and show feedback UI */
  async function persistAndShowFeedback(
    conversationId: string,
    userMessageId: string,
    responseMessageId: string,
  ): Promise<void> {
    try {
      // Persist the reasoning chain
      const result = await callbacks.kernelRequest('consciousness/persist', {
        conversation_id: conversationId,
        user_message_id: userMessageId,
        response_message_id: responseMessageId,
      }) as { chain_block_id: string | null; event_count: number; error?: string };

      if (result.error || !result.chain_block_id) {
        console.warn('Failed to persist consciousness:', result.error);
        return;
      }

      // Store state for feedback
      currentChainBlockId = result.chain_block_id;
      currentUserMessageId = userMessageId;
      currentResponseMessageId = responseMessageId;
      awaitingFeedback = true;

      // Show the feedback row
      showFeedbackRow();

    } catch (e) {
      console.error('Failed to persist consciousness:', e);
    }
  }

  function clearChat(): void {
    state.chatMessages = [];
    chatMessages.innerHTML = '';
    chatMessages.appendChild(welcomeMsg);
  }

  function getChatInput(): HTMLInputElement {
    return chatInput;
  }

  function updateSurfaced(items: Array<{
    title: string;
    reason: string;
    urgency: string;
    is_recurring?: boolean;
    recurrence_frequency?: string;
    next_occurrence?: string;
    entity_type?: string;
    entity_id?: string;
    act_id?: string;
    scene_id?: string;
    act_title?: string;
    act_color?: string;
    user_priority?: number;
    // Email-specific fields
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
  }>): void {
    // Compute fingerprint to detect changes and avoid unnecessary re-renders
    const newFingerprint = JSON.stringify(items.map(i => ({
      id: i.entity_id,
      t: i.title,
      u: i.urgency,
      a: i.act_id,
      c: i.act_color,
      p: i.user_priority,
    })));

    if (newFingerprint === surfacedFingerprint) {
      return;  // No changes, skip DOM update
    }

    surfacedFingerprint = newFingerprint;
    state.surfacedItems = items;

    // Split items by entity type into two columns
    const calendarItems = items.filter(i => i.entity_type !== 'email');
    const emailItems = items.filter(i => i.entity_type === 'email');

    calendarList.innerHTML = '';
    emailList.innerHTML = '';

    // Helper: render an empty-state message into a list element
    function renderEmptyState(listEl: HTMLElement, message: string) {
      const emptyMsg = el('div');
      emptyMsg.style.cssText = `
        text-align: center;
        padding: 20px;
        color: rgba(255,255,255,0.4);
        font-size: 13px;
      `;
      emptyMsg.textContent = message;
      listEl.appendChild(emptyMsg);
    }

    // Helper: build a card element for a surfaced item
    function buildItemEl(item: typeof items[0], index: number): HTMLElement {
      const itemEl = el('div');
      itemEl.setAttribute('data-index', String(index));
      itemEl.setAttribute('data-entity-id', item.entity_id || '');
      itemEl.draggable = true;
      itemEl.style.cssText = `
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 8px;
        cursor: grab;
        transition: background 0.2s, opacity 0.2s;
      `;

      const urgencyColor = item.urgency === 'critical' ? '#ef4444'
        : item.urgency === 'high' ? '#f97316'
        : item.urgency === 'medium' ? '#eab308'
        : '#22c55e';

      const urgencyLabel = item.urgency === 'critical' ? 'Critical'
        : item.urgency === 'high' ? 'High'
        : item.urgency === 'medium' ? 'Medium'
        : 'Low';

      // Build a detailed tooltip explaining this specific item's urgency
      let urgencyTooltip = `${urgencyLabel} urgency`;

      if (item.entity_type === 'email') {
        // Email: show score + reason breakdown
        const parts: string[] = [];
        if (item.importance_score != null) {
          parts.push(`Score: ${(item.importance_score as number).toFixed(2)}`);
        }
        if (item.importance_reason) {
          parts.push(`Why: ${item.importance_reason}`);
        }
        parts.push('');
        parts.push('Score guide:');
        parts.push('  Red = critical (rare)');
        parts.push('  Orange = high (score ≥ 0.8)');
        parts.push('  Yellow = medium (score ≥ 0.5)');
        parts.push('  Green = low (score < 0.5)');
        parts.push('');
        parts.push('Scoring factors: known contact, relevance to active work, sender engagement history');
        urgencyTooltip += '\n' + parts.join('\n');
      } else {
        // Calendar/scene: use the reason field which already has specifics
        urgencyTooltip += ` — ${item.reason}`;
        urgencyTooltip += '\n\nColor guide:';
        urgencyTooltip += '\n  Red = critical (overdue or happening now)';
        urgencyTooltip += '\n  Orange = high (due soon or starting shortly)';
        urgencyTooltip += '\n  Yellow = medium (upcoming)';
        urgencyTooltip += '\n  Green = low (no immediate deadline)';
      }

      if (item.learned_boost && item.boost_reasons?.length) {
        urgencyTooltip += `\n\nLearned priority: ${item.boost_reasons.join(', ')}`;
      }

      // Recurring icon (just the icon, no date)
      const recurringIcon = item.is_recurring
        ? `<span title="Recurring ${item.recurrence_frequency?.toLowerCase() || ''}" style="font-size: 11px; margin-left: 4px;">🔄</span>`
        : '';

      // Act label with dynamic color
      const actColor = item.act_color || '#9333ea';
      const actLabel = item.act_title
        ? `<span style="font-size: 10px; margin-left: 6px; padding: 2px 6px; background: ${actColor}33; color: ${actColor}; border-radius: 4px;">Act: ${escapeHtml(item.act_title)}</span>`
        : '';

      if (item.entity_type === 'email') {
        const senderDisplay = item.sender_name
          ? escapeHtml(item.sender_name)
          : item.sender_email
            ? escapeHtml(item.sender_email)
            : 'Unknown Sender';

        const emailDateDisplay = item.email_date
          ? (() => {
              try {
                return new Date(item.email_date).toLocaleDateString(undefined, {
                  month: 'short', day: 'numeric', year: 'numeric',
                });
              } catch {
                return escapeHtml(item.email_date);
              }
            })()
          : '';

        const importanceDisplay = (item.importance_score !== null && item.importance_score !== undefined)
          ? `<span class="email-score-display" title="${item.importance_reason ? escapeHtml(item.importance_reason) : 'Importance score'}" style="font-size: 10px; color: rgba(255,255,255,0.35); margin-left: 6px;">score: ${(item.importance_score as number).toFixed(2)}</span>`
          : '';

        itemEl.innerHTML = `
          <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
            <span title="${urgencyTooltip}" style="width: 8px; height: 8px; border-radius: 50%; background: ${urgencyColor}; cursor: help;"></span>
            <span style="font-size: 13px;">📧</span>
            <span style="font-weight: 500; color: #fff; font-size: 13px;">${escapeHtml(item.title)}</span>
          </div>
          <div style="display: flex; align-items: center; gap: 6px; padding-left: 16px; margin-bottom: 4px; flex-wrap: wrap;">
            <span style="font-size: 10px; padding: 2px 6px; background: rgba(59,130,246,0.2); color: #60a5fa; border-radius: 4px;">${senderDisplay}</span>
            ${item.account_email ? `<span style="font-size: 10px; padding: 2px 6px; background: rgba(168,85,247,0.15); color: #c084fc; border-radius: 4px;">${escapeHtml(item.account_email)}</span>` : ''}
            ${emailDateDisplay ? `<span style="font-size: 11px; color: rgba(255,255,255,0.4);">${emailDateDisplay}</span>` : ''}
            ${importanceDisplay}
          </div>
          <div style="font-size: 12px; color: rgba(255,255,255,0.5); padding-left: 16px;">
            ${escapeHtml(item.reason)}
          </div>
        `;
      } else {
        itemEl.innerHTML = `
          <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
            <span title="${urgencyTooltip}" style="width: 8px; height: 8px; border-radius: 50%; background: ${urgencyColor}; cursor: help;"></span>
            <span style="font-weight: 500; color: #fff; font-size: 13px;">${escapeHtml(item.title)}</span>
            ${recurringIcon}
            ${actLabel}
          </div>
          <div style="font-size: 12px; color: rgba(255,255,255,0.5); padding-left: 16px;">
            ${escapeHtml(item.reason)}
          </div>
        `;
      }

      // Hover highlight
      itemEl.addEventListener('mouseenter', () => {
        itemEl.style.background = 'rgba(255,255,255,0.08)';
      });
      itemEl.addEventListener('mouseleave', () => {
        itemEl.style.background = 'rgba(255,255,255,0.05)';
      });

      // Right-click context menu: Dismiss (learns a rule)
      itemEl.addEventListener('contextmenu', (e: MouseEvent) => {
        e.preventDefault();

        // Remove any existing context menu
        document.querySelectorAll('.attention-context-menu').forEach(m => m.remove());

        const menu = el('div');
        menu.className = 'attention-context-menu';
        menu.style.cssText = `
          position: fixed;
          left: ${e.clientX}px;
          top: ${e.clientY}px;
          background: #1e1e2e;
          border: 1px solid rgba(255,255,255,0.15);
          border-radius: 6px;
          padding: 4px 0;
          z-index: 9999;
          box-shadow: 0 4px 12px rgba(0,0,0,0.4);
          min-width: 160px;
        `;

        const dismissOption = el('div');
        dismissOption.textContent = 'Dismiss';
        dismissOption.style.cssText = `
          padding: 8px 16px;
          font-size: 13px;
          color: rgba(255,255,255,0.8);
          cursor: pointer;
          transition: background 0.1s;
        `;
        dismissOption.addEventListener('mouseenter', () => {
          dismissOption.style.background = 'rgba(255,255,255,0.1)';
        });
        dismissOption.addEventListener('mouseleave', () => {
          dismissOption.style.background = 'transparent';
        });
        dismissOption.addEventListener('click', () => {
          menu.remove();

          // Animate removal
          itemEl.style.opacity = '0';
          itemEl.style.transition = 'opacity 0.3s';
          setTimeout(() => itemEl.remove(), 300);

          // Dismiss via RPC (email or scene)
          if (item.entity_type === 'email' && item.email_message_id != null) {
            callbacks.kernelRequest('cairn/email/dismiss', {
              email_message_id: item.email_message_id,
            }).catch((err: unknown) => console.error('Dismiss email failed:', err));
          }

          // Trigger rule learning flow in chat
          if (callbacks.onDismissCard && item.entity_id) {
            callbacks.onDismissCard({
              entity_type: item.entity_type || 'scene',
              entity_id: item.entity_id,
              title: item.title,
              sender_name: item.sender_name,
              sender_email: item.sender_email,
            });
          }
        });

        menu.appendChild(dismissOption);
        document.body.appendChild(menu);

        // Close menu on click outside
        const closeMenu = () => {
          menu.remove();
          document.removeEventListener('click', closeMenu);
        };
        setTimeout(() => document.addEventListener('click', closeMenu), 0);
      });

      // Click to navigate to Scene in The Play
      if (item.entity_type === 'scene' && item.act_id) {
        itemEl.addEventListener('click', () => {
          const event = new CustomEvent('openPlayScene', {
            detail: { actId: item.act_id, sceneId: item.entity_id },
          });
          window.dispatchEvent(event);
        });
      }

      // Email actions: open, upvote, downvote
      if (item.entity_type === 'email' && item.email_message_id != null) {
        // Dim read emails
        if (item.is_read) {
          itemEl.style.opacity = '0.65';
        }

        itemEl.style.cursor = 'pointer';

        // Click body to open
        itemEl.addEventListener('click', (e) => {
          // Don't open if clicking an action button
          if ((e.target as HTMLElement).closest('.email-actions')) return;
          callbacks.kernelRequest('cairn/email/open', {
            email_message_id: item.email_message_id,
          }).catch((err: unknown) => {
            console.error('Failed to open email:', err);
          });
        });

        // Action buttons row
        const actionsRow = el('div');
        actionsRow.className = 'email-actions';
        actionsRow.style.cssText = `
          display: flex;
          gap: 6px;
          padding: 4px 0 0 16px;
        `;

        const upvoteBtn = el('button');
        upvoteBtn.textContent = '▲';
        upvoteBtn.title = 'Increase score — surface emails like this higher';
        upvoteBtn.style.cssText = `
          font-size: 11px;
          padding: 2px 8px;
          background: rgba(16, 185, 129, 0.1);
          border: 1px solid rgba(16, 185, 129, 0.3);
          border-radius: 4px;
          color: rgba(16, 185, 129, 0.8);
          cursor: pointer;
        `;
        upvoteBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          callbacks.kernelRequest('cairn/email/upvote', {
            email_message_id: item.email_message_id,
          }).then((res: unknown) => {
            const result = res as { new_score?: number };
            if (result.new_score !== undefined) {
              const scoreEl = itemEl.querySelector('.email-score-display');
              if (scoreEl) scoreEl.textContent = `score: ${result.new_score.toFixed(2)}`;
            }
            itemEl.style.borderLeft = '3px solid rgba(16, 185, 129, 0.6)';
            setTimeout(() => { itemEl.style.borderLeft = ''; }, 1500);
          }).catch((err: unknown) => {
            console.error('Failed to upvote email:', err);
          });
        });

        const downvoteBtn = el('button');
        downvoteBtn.textContent = '▼';
        downvoteBtn.title = 'Lower score — surface emails like this lower';
        downvoteBtn.style.cssText = `
          font-size: 11px;
          padding: 2px 8px;
          background: rgba(239, 68, 68, 0.1);
          border: 1px solid rgba(239, 68, 68, 0.3);
          border-radius: 4px;
          color: rgba(239, 68, 68, 0.8);
          cursor: pointer;
        `;
        downvoteBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          callbacks.kernelRequest('cairn/email/downvote', {
            email_message_id: item.email_message_id,
          }).then((res: unknown) => {
            const result = res as { new_score?: number };
            if (result.new_score !== undefined) {
              const scoreEl = itemEl.querySelector('.email-score-display');
              if (scoreEl) scoreEl.textContent = `score: ${result.new_score.toFixed(2)}`;
            }
            itemEl.style.borderLeft = '3px solid rgba(239, 68, 68, 0.6)';
            setTimeout(() => { itemEl.style.borderLeft = ''; }, 1500);
          }).catch((err: unknown) => {
            console.error('Failed to downvote email:', err);
          });
        });

        actionsRow.appendChild(upvoteBtn);
        actionsRow.appendChild(downvoteBtn);
        itemEl.appendChild(actionsRow);
      }

      return itemEl;
    }

    /**
     * Create drag-and-drop handlers scoped to a single column.
     * On drop, merges both columns' current DOM order and fires the reorder RPC.
     * columnItems: the items rendered in this column (calendar or email)
     * listEl: the column's list DOM element
     * getOtherColumnItems: function returning the other column's current ordered items from its DOM
     */
    function makeColumnDragHandlers(
      columnItems: typeof items,
      listEl: HTMLElement,
      getOtherColumnItems: () => typeof items,
    ) {
      let dragSourceIndex: number | null = null;

      columnItems.forEach((item, index) => {
        const itemEl = listEl.querySelector(`[data-index="${index}"]`) as HTMLElement | null;
        if (!itemEl) return;

        itemEl.addEventListener('dragstart', (e: DragEvent) => {
          dragSourceIndex = index;
          itemEl.style.opacity = '0.4';
          e.dataTransfer!.effectAllowed = 'move';
          e.dataTransfer!.setData('text/plain', String(index));
        });

        itemEl.addEventListener('dragover', (e: DragEvent) => {
          e.preventDefault();
          e.dataTransfer!.dropEffect = 'move';
          const rect = itemEl.getBoundingClientRect();
          const midY = rect.top + rect.height / 2;
          if (e.clientY < midY) {
            itemEl.style.borderTop = '2px solid #3b82f6';
            itemEl.style.borderBottom = '1px solid rgba(255,255,255,0.1)';
          } else {
            itemEl.style.borderBottom = '2px solid #3b82f6';
            itemEl.style.borderTop = '1px solid rgba(255,255,255,0.1)';
          }
        });

        itemEl.addEventListener('dragleave', () => {
          itemEl.style.borderTop = '1px solid rgba(255,255,255,0.1)';
          itemEl.style.borderBottom = '1px solid rgba(255,255,255,0.1)';
        });

        itemEl.addEventListener('drop', (e: DragEvent) => {
          e.preventDefault();
          itemEl.style.borderTop = '1px solid rgba(255,255,255,0.1)';
          itemEl.style.borderBottom = '1px solid rgba(255,255,255,0.1)';

          if (dragSourceIndex === null || dragSourceIndex === index) return;

          const rect = itemEl.getBoundingClientRect();
          const midY = rect.top + rect.height / 2;
          let targetIndex = e.clientY < midY ? index : index + 1;
          if (dragSourceIndex < targetIndex) targetIndex--;

          if (targetIndex === dragSourceIndex) return;

          // Reorder within this column
          const reorderedColumn = [...columnItems];
          const [moved] = reorderedColumn.splice(dragSourceIndex, 1);
          reorderedColumn.splice(targetIndex, 0, moved);

          // Merge: calendar column items first, email column items second.
          // Cross-column ordering is not supported — the RPC accepts a mixed list.
          const otherItems = getOtherColumnItems();
          const mergedItems = listEl === calendarList
            ? [...reorderedColumn, ...otherItems]
            : [...otherItems, ...reorderedColumn];

          // Optimistic re-render
          surfacedFingerprint = '';
          updateSurfaced(mergedItems);

          // Fire RPC to persist + analyze
          const orderedIds = mergedItems
            .map(i => i.entity_id)
            .filter((id): id is string => !!id);
          const orderedEntities = mergedItems
            .filter(i => i.entity_id)
            .map(i => [i.entity_type || 'scene', i.entity_id]);
          const originalItems = items;
          showThinking();
          callbacks.kernelRequest('cairn/attention/reorder', {
            ordered_scene_ids: orderedIds,
            ordered_entities: orderedEntities,
          }).then((result: unknown) => {
            hideThinking();
            const r = result as { priorities_updated: number; analysis_text?: string };
            if (r.analysis_text && r.analysis_text.trim()) {
              addChatMessage('assistant', r.analysis_text);
            }
          }).catch((err: unknown) => {
            hideThinking();
            console.error('Failed to persist attention reorder:', err);
            surfacedFingerprint = '';
            updateSurfaced(originalItems);
          });
        });

        itemEl.addEventListener('dragend', () => {
          itemEl.style.opacity = '1';
          dragSourceIndex = null;
          // Clean up border indicators in this column
          listEl.querySelectorAll('[data-index]').forEach((card) => {
            (card as HTMLElement).style.borderTop = '1px solid rgba(255,255,255,0.1)';
            (card as HTMLElement).style.borderBottom = '1px solid rgba(255,255,255,0.1)';
          });
        });
      });
    }

    // Render calendar/task items into left column
    if (calendarItems.length === 0) {
      renderEmptyState(calendarList, 'No calendar items or tasks');
    } else {
      calendarItems.forEach((item, index) => {
        calendarList.appendChild(buildItemEl(item, index));
      });
    }

    // Render email items into right column
    if (emailItems.length === 0) {
      renderEmptyState(emailList, 'No email');
    } else {
      emailItems.forEach((item, index) => {
        emailList.appendChild(buildItemEl(item, index));
      });
    }

    // Attach drag-and-drop handlers per column.
    // Each column reads the other column's current DOM order when merging for the RPC.
    function getCalendarItemsFromDom(): typeof items {
      return Array.from(calendarList.querySelectorAll('[data-entity-id]')).map(el => {
        const entityId = el.getAttribute('data-entity-id') || '';
        return calendarItems.find(i => i.entity_id === entityId) || calendarItems[0];
      }).filter(Boolean);
    }

    function getEmailItemsFromDom(): typeof items {
      return Array.from(emailList.querySelectorAll('[data-entity-id]')).map(el => {
        const entityId = el.getAttribute('data-entity-id') || '';
        return emailItems.find(i => i.entity_id === entityId) || emailItems[0];
      }).filter(Boolean);
    }

    makeColumnDragHandlers(calendarItems, calendarList, getEmailItemsFromDom);
    makeColumnDragHandlers(emailItems, emailList, getCalendarItemsFromDom);
  }

  return {
    container,
    chatHeader,
    addChatMessage,
    addAssistantMessage,
    showThinking,
    hideThinking,
    clearChat,
    getChatInput,
    updateSurfaced,
    persistAndShowFeedback,
  };
}
