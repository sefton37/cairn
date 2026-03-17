/**
 * ReOS Conversational Shell — DOM-based renderer for multi-turn NL→command sessions.
 *
 * Philosophy: A second mode alongside the PTY terminal, not a replacement.
 * The PTY terminal serves "I know Linux; enhance me when I fail."
 * The conversational shell serves "Help me figure out what to do."
 *
 * Visual design: Dark terminal aesthetic, JetBrains Mono, prompt sigil.
 * Command cards with [Run] / [Edit] / [Skip] buttons.
 * Turn types: clarify, inform, propose, danger, refuse.
 *
 * See docs/plan-conversational-shell.md for the full architecture.
 */

import { el } from './dom';

// ── Types ───────────────────────────────────────────────────────────────

export interface ReosConversationalCallbacks {
  kernelRequest: (method: string, params: unknown) => Promise<unknown>;
  /** Called to get the current hostname for the prompt sigil. */
  getHostname?: () => string | null;
  /** Called to get the current system context (distro, package manager, etc.) for reos/converse. */
  getSystemContext?: () => Record<string, unknown>;
}

interface ConversationTurn {
  role: 'user' | 'assistant' | 'system';
  content: string;
  command?: string;
  turnType?: 'clarify' | 'inform' | 'propose' | 'danger' | 'refuse';
  timestamp: number;
}

interface ConversationState {
  conversationId: string;
  turns: ConversationTurn[];
  pendingOperationId: string | null;
  pendingCommand: string | null;
  inputHistory: string[];
  historyIndex: number;
}

interface ReosConverseResult {
  turn_type: 'clarify' | 'inform' | 'propose' | 'danger' | 'refuse';
  message: string;
  command: string | null;
  explanation: string | null;
  is_risky: boolean;
  risk_reason: string | null;
  operation_id: string;
  classification: Record<string, unknown>;
  latency_ms: number;
}

interface ReosExecuteResult {
  success: boolean;
  exit_code: number | null;
  stdout: string;
  stderr: string;
  duration_ms: number;
  truncated: boolean;
}

// ── Factory ─────────────────────────────────────────────────────────────

export function createConversationalShell(callbacks: ReosConversationalCallbacks): {
  container: HTMLElement;
  activate: () => void;
  deactivate: () => void;
} {
  // ── Conversation state ──
  const state: ConversationState = {
    conversationId: crypto.randomUUID(),
    turns: [],
    pendingOperationId: null,
    pendingCommand: null,
    inputHistory: [],
    historyIndex: -1,
  };

  let isWaiting = false;
  // Track whether the latest rendered element is an actionable proposal card.
  let latestCardIsProposal = false;
  let latestRunBtn: HTMLElement | null = null;
  let latestSkipBtn: HTMLElement | null = null;

  // ── Root container ──
  const container = el('div');
  container.className = 'reos-conv-shell';
  container.style.cssText = `
    flex: 1;
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    background: rgba(0,0,0,0.9);
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px;
    color: rgba(255,255,255,0.85);
    overflow: hidden;
    position: relative;
  `;

  // ── Header bar ──
  const header = el('div');
  header.style.cssText = `
    padding: 10px 20px;
    border-bottom: 1px solid rgba(255,255,255,0.1);
    background: rgba(0,0,0,0.4);
    display: flex;
    align-items: center;
    gap: 12px;
    flex-shrink: 0;
  `;

  const headerTitle = el('div');
  headerTitle.style.cssText = 'font-size: 13px; font-weight: 600; color: rgba(255,255,255,0.7);';
  headerTitle.textContent = '\u{1F4AC} Conversational Shell';

  const newConvBtn = el('button');
  newConvBtn.textContent = '\u21BA New';
  newConvBtn.style.cssText = `
    margin-left: auto;
    padding: 3px 10px;
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 4px;
    color: rgba(255,255,255,0.5);
    font-size: 11px;
    font-family: inherit;
    cursor: pointer;
  `;

  // Debug toggle — shows intent classification below each turn when enabled.
  let debugEnabled = localStorage.getItem('reos-conv-debug') === '1';
  const debugBtn = el('button');
  debugBtn.textContent = '[debug]';
  debugBtn.title = 'Toggle intent classification display';
  debugBtn.style.cssText = `
    padding: 3px 8px;
    background: transparent;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 4px;
    color: ${debugEnabled ? 'rgba(88,166,255,0.7)' : 'rgba(255,255,255,0.25)'};
    font-size: 10px;
    font-family: inherit;
    cursor: pointer;
  `;
  debugBtn.addEventListener('click', () => {
    debugEnabled = !debugEnabled;
    localStorage.setItem('reos-conv-debug', debugEnabled ? '1' : '0');
    debugBtn.style.color = debugEnabled ? 'rgba(88,166,255,0.7)' : 'rgba(255,255,255,0.25)';
    // Show/hide all existing debug lines
    scrollBuffer.querySelectorAll('.reos-debug-line').forEach((el) => {
      (el as HTMLElement).style.display = debugEnabled ? '' : 'none';
    });
  });

  header.appendChild(headerTitle);
  header.appendChild(debugBtn);
  header.appendChild(newConvBtn);

  // ── Scroll buffer ──
  const scrollBuffer = el('div');
  scrollBuffer.className = 'reos-conv-buffer';
  scrollBuffer.style.cssText = `
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 16px 20px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  `;

  // ── Input row ──
  const inputRow = el('div');
  inputRow.style.cssText = `
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 20px;
    border-top: 1px solid rgba(255,255,255,0.08);
    background: rgba(0,0,0,0.3);
    flex-shrink: 0;
  `;

  const promptSigil = el('span');
  promptSigil.style.cssText = `
    font-size: 13px;
    color: rgba(88,166,255,0.9);
    white-space: nowrap;
    flex-shrink: 0;
    user-select: none;
  `;
  // Will be updated with hostname when available.
  promptSigil.textContent = 'reos@\u2026:~$';

  const inputEl = el('input') as HTMLInputElement;
  inputEl.type = 'text';
  inputEl.placeholder = 'Describe what you want to do\u2026';
  inputEl.style.cssText = `
    flex: 1;
    background: transparent;
    border: none;
    outline: none;
    color: rgba(255,255,255,0.9);
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px;
    caret-color: #58a6ff;
  `;

  inputRow.appendChild(promptSigil);
  inputRow.appendChild(inputEl);

  // Assemble container
  container.appendChild(header);
  container.appendChild(scrollBuffer);
  container.appendChild(inputRow);

  // ── Helpers ──────────────────────────────────────────────────────────

  /** Fire-and-forget telemetry. Never throws, never blocks. */
  function recordEvent(eventType: string, payload: Record<string, unknown>): void {
    callbacks.kernelRequest('reos/telemetry/event', {
      session_id: state.conversationId,
      trace_id: state.conversationId,
      ts: Date.now(),
      event_type: eventType,
      payload,
    }).catch(() => {/* fire-and-forget */});
  }

  /** Show brief "Copied!" feedback on a button for 1.5 s then revert. */
  function showCopiedFeedback(btn: HTMLElement, original: string): void {
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = original; }, 1500);
  }

  function scrollToBottom(): void {
    requestAnimationFrame(() => {
      scrollBuffer.scrollTop = scrollBuffer.scrollHeight;
    });
  }

  function setInputDisabled(disabled: boolean): void {
    inputEl.disabled = disabled;
    inputEl.style.opacity = disabled ? '0.4' : '1';
  }

  function updatePromptSigil(): void {
    const hostname = callbacks.getHostname?.() ?? 'localhost';
    promptSigil.textContent = `reos@${hostname}:~$`;
  }

  // ── Turn renderers ───────────────────────────────────────────────────

  /** Render a user-typed turn: "> <text>" */
  function appendUserTurn(text: string): void {
    const row = el('div');
    row.style.cssText = `
      display: flex;
      gap: 8px;
      padding: 4px 0;
    `;

    const prefix = el('span');
    prefix.style.cssText = 'color: rgba(255,255,255,0.3); flex-shrink: 0; user-select: none;';
    prefix.textContent = '>';

    const content = el('span');
    content.style.cssText = 'color: rgba(255,255,255,0.9); word-break: break-word;';
    content.textContent = text;

    row.appendChild(prefix);
    row.appendChild(content);
    scrollBuffer.appendChild(row);
    latestCardIsProposal = false;
    scrollToBottom();
  }

  /** Render an inform or clarify turn: plain text, dimmed. */
  function appendInfoTurn(
    text: string,
    isClarify: boolean,
    classification?: Record<string, unknown>,
    turnIndex?: number,
  ): void {
    const wrapper = el('div');
    wrapper.style.cssText = 'display: flex; flex-direction: column; gap: 3px;';

    const row = el('div');
    row.style.cssText = `
      padding: 4px 0;
      color: rgba(255,255,255,0.7);
      line-height: 1.6;
      word-break: break-word;
      display: flex;
      align-items: flex-start;
      gap: 6px;
    `;

    const textSpan = el('span');
    textSpan.style.cssText = 'flex: 1;';

    if (isClarify) {
      const indicator = el('span');
      indicator.style.cssText = `
        flex-shrink: 0;
        color: rgba(88,166,255,0.8);
        font-weight: 600;
      `;
      indicator.textContent = '?';
      textSpan.appendChild(indicator);
      textSpan.appendChild(document.createTextNode(' '));
    }

    textSpan.appendChild(document.createTextNode(text));
    row.appendChild(textSpan);

    // Thumbs up/down feedback buttons
    const thumbs = el('div');
    thumbs.style.cssText = `
      display: flex;
      gap: 4px;
      flex-shrink: 0;
      align-self: center;
      opacity: 0.4;
    `;
    thumbs.addEventListener('mouseenter', () => { thumbs.style.opacity = '0.75'; });
    thumbs.addEventListener('mouseleave', () => { thumbs.style.opacity = '0.4'; });

    let feedbackGiven = false;
    function makeThumb(emoji: string, feedback: 'positive' | 'negative'): HTMLElement {
      const btn = el('button');
      btn.textContent = emoji;
      btn.style.cssText = `
        background: transparent;
        border: none;
        cursor: pointer;
        font-size: 13px;
        padding: 0 2px;
        font-family: inherit;
        color: inherit;
      `;
      btn.addEventListener('click', () => {
        if (feedbackGiven) return;
        feedbackGiven = true;
        // Highlight selected thumb
        btn.style.opacity = '1';
        btn.style.filter = 'brightness(1.5)';
        // Dim the other
        thumbs.querySelectorAll('button').forEach((b) => {
          if (b !== btn) (b as HTMLElement).style.opacity = '0.2';
        });
        recordEvent('turn_feedback', {
          turn_index: turnIndex ?? -1,
          feedback,
        });
      });
      return btn;
    }

    thumbs.appendChild(makeThumb('\u{1F44D}', 'positive'));
    thumbs.appendChild(makeThumb('\u{1F44E}', 'negative'));
    row.appendChild(thumbs);

    wrapper.appendChild(row);

    // Debug line: intent classification
    if (classification) {
      const debugLine = el('div');
      debugLine.className = 'reos-debug-line';
      debugLine.style.cssText = `
        font-size: 10px;
        color: rgba(255,255,255,0.2);
        padding: 0 4px;
        display: ${debugEnabled ? '' : 'none'};
      `;
      const intent = String(classification['intent'] ?? '—');
      const confident = String(classification['confident'] ?? '—');
      debugLine.textContent = `intent: ${intent} | confident: ${confident}`;
      wrapper.appendChild(debugLine);
    }

    scrollBuffer.appendChild(wrapper);
    latestCardIsProposal = false;
    scrollToBottom();
  }

  /** Render a refuse turn: red block, explanation text, no buttons. */
  function appendRefuseTurn(text: string): void {
    const block = el('div');
    block.style.cssText = `
      background: rgba(239,68,68,0.08);
      border: 1px solid rgba(239,68,68,0.3);
      border-radius: 6px;
      padding: 10px 14px;
      color: rgba(239,68,68,0.9);
      line-height: 1.5;
      word-break: break-word;
    `;

    const icon = el('span');
    icon.style.cssText = 'margin-right: 6px;';
    icon.textContent = '\u26D4';

    block.appendChild(icon);
    block.appendChild(document.createTextNode(text));

    scrollBuffer.appendChild(block);
    latestCardIsProposal = false;
    scrollToBottom();
  }

  /** Render a thinking indicator while waiting for RPC. */
  function appendThinkingIndicator(): HTMLElement {
    const row = el('div');
    row.style.cssText = `
      padding: 4px 0;
      color: rgba(88,166,255,0.5);
      font-style: italic;
      font-size: 13px;
    `;
    row.textContent = 'thinking\u2026';
    scrollBuffer.appendChild(row);
    scrollToBottom();
    return row;
  }

  /**
   * Render an output block below a command card after execution.
   * Returns the block element.
   */
  function appendOutputBlock(
    command: string,
    result: ReosExecuteResult,
  ): HTMLElement {
    const block = el('div');
    block.style.cssText = `
      margin-top: 6px;
      background: rgba(0,0,0,0.35);
      border: 1px solid rgba(255,255,255,0.06);
      border-radius: 6px;
      overflow: hidden;
    `;

    // Header row: exit-code dot + command
    const blockHeader = el('div');
    blockHeader.style.cssText = `
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 7px 12px;
      border-bottom: 1px solid rgba(255,255,255,0.05);
      background: rgba(255,255,255,0.02);
    `;

    const exitDot = el('span');
    const dotColor = result.exit_code === 0 ? '#22c55e' : '#ef4444';
    exitDot.style.cssText = `
      width: 8px; height: 8px;
      border-radius: 50%;
      background: ${dotColor};
      flex-shrink: 0;
    `;

    const cmdLabel = el('span');
    cmdLabel.style.cssText = `
      font-size: 12px;
      color: rgba(255,255,255,0.5);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    `;
    cmdLabel.textContent = `$ ${command}`;
    cmdLabel.title = command;

    const exitLabel = el('span');
    exitLabel.style.cssText = `
      margin-left: auto;
      font-size: 11px;
      color: ${result.exit_code === 0 ? 'rgba(34,197,94,0.6)' : 'rgba(239,68,68,0.6)'};
      flex-shrink: 0;
    `;
    exitLabel.textContent = result.exit_code !== null ? `exit ${result.exit_code}` : 'exit ?';

    // Copy output button
    const copyOutputBtn = el('button');
    copyOutputBtn.textContent = 'Copy output';
    copyOutputBtn.style.cssText = `
      margin-left: 6px;
      background: transparent;
      border: none;
      cursor: pointer;
      font-size: 10px;
      color: rgba(255,255,255,0.35);
      font-family: inherit;
      padding: 0 2px;
      opacity: 0.5;
      flex-shrink: 0;
    `;
    copyOutputBtn.style.setProperty('transition', 'opacity 0.15s');
    copyOutputBtn.addEventListener('mouseenter', () => { copyOutputBtn.style.opacity = '0.8'; });
    copyOutputBtn.addEventListener('mouseleave', () => { copyOutputBtn.style.opacity = '0.5'; });
    copyOutputBtn.addEventListener('click', () => {
      const outputText = [result.stdout, result.stderr].filter(Boolean).join('\n').trimEnd();
      navigator.clipboard.writeText(outputText).catch(() => {/* best-effort */});
      showCopiedFeedback(copyOutputBtn, 'Copy output');
    });

    blockHeader.appendChild(exitDot);
    blockHeader.appendChild(cmdLabel);
    blockHeader.appendChild(exitLabel);
    blockHeader.appendChild(copyOutputBtn);
    block.appendChild(blockHeader);

    // Output content
    const combinedOutput = [result.stdout, result.stderr].filter(Boolean).join('\n').trimEnd();
    if (combinedOutput) {
      const pre = el('pre') as HTMLElement;
      pre.style.cssText = `
        margin: 0;
        padding: 10px 12px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 12px;
        color: rgba(255,255,255,0.75);
        white-space: pre-wrap;
        word-break: break-all;
        max-height: 300px;
        overflow-y: auto;
        line-height: 1.5;
      `;
      pre.textContent = combinedOutput;
      block.appendChild(pre);
    } else {
      const empty = el('div');
      empty.style.cssText = 'padding: 8px 12px; font-size: 12px; color: rgba(255,255,255,0.3);';
      empty.textContent = '(no output)';
      block.appendChild(empty);
    }

    if (result.truncated) {
      const notice = el('div');
      notice.style.cssText = `
        padding: 4px 12px;
        font-size: 11px;
        color: rgba(255,193,7,0.7);
        border-top: 1px solid rgba(255,255,255,0.04);
      `;
      notice.textContent = '\u26A0 Output truncated (too large to display fully).';
      block.appendChild(notice);
    }

    scrollBuffer.appendChild(block);
    scrollToBottom();
    return block;
  }

  /**
   * Render a propose or danger command card.
   * Returns the card element so callers can attach output blocks after execution.
   */
  function appendCommandCard(
    result: ReosConverseResult,
    onRun: (command: string, btn: HTMLElement) => void,
    onSkip: (operationId: string, card: HTMLElement) => void,
    onRunEdited?: (editedCommand: string, originalCommand: string, btn: HTMLElement) => void,
  ): HTMLElement {
    const isDanger = result.turn_type === 'danger';

    const card = el('div');
    card.className = `reos-card ${result.turn_type}`;
    card.style.cssText = `
      background: ${isDanger ? 'rgba(239,68,68,0.08)' : 'rgba(255,255,255,0.03)'};
      border: 1px solid ${isDanger ? 'rgba(239,68,68,0.35)' : 'rgba(255,255,255,0.09)'};
      border-radius: 8px;
      padding: 12px 14px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    `;

    // Danger header
    if (isDanger) {
      const dangerHeader = el('div');
      dangerHeader.style.cssText = 'color: rgba(239,68,68,0.9); font-size: 13px; font-weight: 600; display: flex; gap: 6px; align-items: center;';
      dangerHeader.textContent = '\u26A0 Potentially dangerous operation';
      card.appendChild(dangerHeader);
    }

    // Message (above command)
    if (result.message) {
      const msg = el('div');
      msg.style.cssText = `
        font-size: 13px;
        color: rgba(255,255,255,0.7);
        line-height: 1.5;
        word-break: break-word;
      `;
      msg.textContent = result.message;
      card.appendChild(msg);
    }

    // Risk reason
    if (isDanger && result.risk_reason) {
      const riskNote = el('div');
      riskNote.style.cssText = `
        font-size: 12px;
        color: rgba(239,68,68,0.8);
        padding: 4px 8px;
        background: rgba(239,68,68,0.06);
        border-radius: 4px;
        line-height: 1.4;
      `;
      riskNote.textContent = `Risk: ${result.risk_reason}`;
      card.appendChild(riskNote);
    }

    // Command block with copy button
    const command = result.command ?? '';
    const commandRow = el('div');
    commandRow.style.cssText = 'position: relative;';

    const commandBlock = el('div');
    commandBlock.className = 'card-command';
    commandBlock.style.cssText = `
      font-family: 'JetBrains Mono', monospace;
      font-size: 13px;
      color: rgba(255,255,255,0.9);
      background: rgba(0,0,0,0.3);
      border: 1px solid rgba(255,255,255,0.06);
      border-radius: 4px;
      padding: 8px 10px;
      padding-right: 60px;
      word-break: break-all;
      white-space: pre-wrap;
    `;
    commandBlock.textContent = command;

    const copyCommandBtn = el('button');
    copyCommandBtn.textContent = 'Copy';
    copyCommandBtn.style.cssText = `
      position: absolute;
      top: 6px;
      right: 6px;
      background: transparent;
      border: none;
      cursor: pointer;
      font-size: 10px;
      color: rgba(255,255,255,0.4);
      font-family: inherit;
      padding: 2px 4px;
      opacity: 0.5;
    `;
    copyCommandBtn.style.setProperty('transition', 'opacity 0.15s');
    copyCommandBtn.addEventListener('mouseenter', () => { copyCommandBtn.style.opacity = '0.8'; });
    copyCommandBtn.addEventListener('mouseleave', () => { copyCommandBtn.style.opacity = '0.5'; });
    copyCommandBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      navigator.clipboard.writeText(command).catch(() => {/* best-effort */});
      showCopiedFeedback(copyCommandBtn, 'Copy');
    });

    commandRow.appendChild(commandBlock);
    commandRow.appendChild(copyCommandBtn);
    card.appendChild(commandRow);

    // Explanation
    if (result.explanation) {
      const explDiv = el('div');
      explDiv.className = 'card-explanation';
      explDiv.style.cssText = `
        font-size: 12px;
        color: rgba(255,255,255,0.45);
        line-height: 1.4;
        word-break: break-word;
      `;
      explDiv.textContent = result.explanation;
      card.appendChild(explDiv);
    }

    // Action buttons
    const actions = el('div');
    actions.className = 'card-actions';
    actions.style.cssText = 'display: flex; gap: 8px; align-items: center; flex-wrap: wrap;';

    // Run / danger run button
    const runBtn = el('button');
    runBtn.className = 'card-btn run';
    runBtn.textContent = isDanger ? '\u26A0 I understand, run anyway' : 'Run';
    runBtn.style.cssText = `
      padding: 4px 12px;
      background: ${isDanger ? 'rgba(239,68,68,0.15)' : 'rgba(34,197,94,0.12)'};
      border: 1px solid ${isDanger ? 'rgba(239,68,68,0.4)' : 'rgba(34,197,94,0.35)'};
      border-radius: 4px;
      color: ${isDanger ? 'rgba(239,68,68,0.9)' : 'rgba(34,197,94,0.9)'};
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      cursor: pointer;
    `;

    // Edit button (non-danger only)
    const editBtn = el('button');
    editBtn.className = 'card-btn edit';
    editBtn.textContent = 'Edit';
    editBtn.style.cssText = `
      padding: 4px 12px;
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.15);
      border-radius: 4px;
      color: rgba(255,255,255,0.6);
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      cursor: pointer;
    `;

    // Skip button
    const skipBtn = el('button');
    skipBtn.className = 'card-btn skip';
    skipBtn.textContent = 'Skip';
    skipBtn.style.cssText = `
      padding: 4px 12px;
      background: transparent;
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 4px;
      color: rgba(255,255,255,0.35);
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      cursor: pointer;
    `;

    actions.appendChild(runBtn);
    if (!isDanger) actions.appendChild(editBtn);
    actions.appendChild(skipBtn);
    card.appendChild(actions);

    // Debug line: intent classification
    if (result.classification) {
      const debugLine = el('div');
      debugLine.className = 'reos-debug-line';
      debugLine.style.cssText = `
        font-size: 10px;
        color: rgba(255,255,255,0.2);
        padding: 2px 0 0;
        display: ${debugEnabled ? '' : 'none'};
      `;
      const intent = String(result.classification['intent'] ?? '—');
      const confident = String(result.classification['confident'] ?? '—');
      debugLine.textContent = `intent: ${intent} | confident: ${confident}`;
      card.appendChild(debugLine);
    }

    // ── Edit button behavior ──
    let editMode = false;
    let editInput: HTMLInputElement | null = null;

    editBtn.addEventListener('click', () => {
      if (editMode) return;
      editMode = true;

      // Replace command block with an input
      editInput = el('input') as HTMLInputElement;
      editInput.type = 'text';
      editInput.value = command;
      editInput.style.cssText = `
        font-family: 'JetBrains Mono', monospace;
        font-size: 13px;
        color: rgba(255,255,255,0.9);
        background: rgba(0,0,0,0.4);
        border: 1px solid rgba(88,166,255,0.4);
        border-radius: 4px;
        padding: 8px 10px;
        width: 100%;
        box-sizing: border-box;
        outline: none;
        caret-color: #58a6ff;
      `;
      commandBlock.replaceWith(editInput);
      editInput.focus();
      editInput.select();

      // Change Edit → "Run edited"
      editBtn.textContent = 'Run edited';
      editBtn.style.background = 'rgba(34,197,94,0.12)';
      editBtn.style.border = '1px solid rgba(34,197,94,0.35)';
      editBtn.style.color = 'rgba(34,197,94,0.9)';

      editBtn.onclick = () => {
        if (editInput) {
          const edited = editInput.value.trim();
          if (edited) {
            if (edited !== command && onRunEdited) {
              onRunEdited(edited, command, runBtn);
            } else {
              onRun(edited, runBtn);
            }
          }
        }
      };

      // Also allow Enter in the edit field to submit
      editInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          const edited = editInput?.value.trim() ?? '';
          if (edited) {
            if (edited !== command && onRunEdited) {
              onRunEdited(edited, command, runBtn);
            } else {
              onRun(edited, runBtn);
            }
          }
        }
      });
    });

    // ── Run button behavior ──
    runBtn.addEventListener('click', () => {
      const cmd = editMode && editInput ? editInput.value.trim() : command;
      if (cmd) onRun(cmd, runBtn);
    });

    // ── Skip button behavior ──
    skipBtn.addEventListener('click', () => {
      onSkip(result.operation_id, card);
    });

    scrollBuffer.appendChild(card);

    // Track latest proposal for keyboard shortcuts
    latestCardIsProposal = true;
    latestRunBtn = runBtn;
    latestSkipBtn = skipBtn;

    scrollToBottom();
    return card;
  }

  // ── Execution handler ────────────────────────────────────────────────

  function executeCommand(
    command: string,
    operationId: string,
    runBtn: HTMLElement,
    card: HTMLElement,
  ): void {
    // Disable buttons on the card during execution
    card.querySelectorAll('button').forEach((btn) => {
      (btn as HTMLButtonElement).disabled = true;
      (btn as HTMLButtonElement).style.opacity = '0.5';
    });

    const execLabel = el('div');
    execLabel.style.cssText = `
      font-size: 12px;
      color: rgba(88,166,255,0.6);
      font-style: italic;
    `;
    execLabel.textContent = 'executing\u2026';
    card.appendChild(execLabel);

    // Mark this card as no longer actionable (keyboard shortcut should not fire again)
    latestCardIsProposal = false;

    void callbacks.kernelRequest('reos/execute', {
      operation_id: operationId,
      command,
      conversation_id: state.conversationId,
    }).then((raw) => {
      const result = raw as ReosExecuteResult;
      execLabel.remove();
      appendOutputBlock(command, result);

      // Telemetry: command executed
      recordEvent('command_executed', {
        exit_code: result.exit_code,
        duration_ms: result.duration_ms,
        operation_id: operationId,
      });

      // Add execution result to turn history for context
      state.turns.push({
        role: 'system',
        content: `Executed: ${command}\nExit code: ${result.exit_code}\nOutput: ${(result.stdout + result.stderr).substring(0, 500)}`,
        timestamp: Date.now(),
      });
    }).catch((err: unknown) => {
      execLabel.remove();
      const errBlock = el('div');
      errBlock.style.cssText = `
        margin-top: 6px;
        padding: 8px 12px;
        background: rgba(239,68,68,0.08);
        border: 1px solid rgba(239,68,68,0.25);
        border-radius: 6px;
        font-size: 12px;
        color: rgba(239,68,68,0.8);
      `;
      errBlock.textContent = `Execution error: ${err instanceof Error ? err.message : String(err)}`;
      card.appendChild(errBlock);
    }).finally(() => {
      setInputDisabled(false);
      inputEl.focus();
    });
  }

  // ── Submit handler ───────────────────────────────────────────────────

  function submitInput(text: string): void {
    if (!text.trim() || isWaiting) return;

    const trimmed = text.trim();

    // Add to history
    state.inputHistory.unshift(trimmed);
    if (state.inputHistory.length > 100) state.inputHistory.pop();
    state.historyIndex = -1;

    // Render user turn
    appendUserTurn(trimmed);

    // Add to turn history
    state.turns.push({
      role: 'user',
      content: trimmed,
      timestamp: Date.now(),
    });

    // Clear and disable input
    inputEl.value = '';
    setInputDisabled(true);
    isWaiting = true;

    // Telemetry: user submitted a turn
    const submitTs = Date.now();
    recordEvent('turn_submitted', { text: trimmed });

    const thinkingEl = appendThinkingIndicator();

    // Build turn_history for RPC (last 8 turns)
    const turnHistory = state.turns.slice(-8).map((t) => ({
      role: t.role,
      content: t.content,
    }));

    // Resolve system context from vitals
    const systemContext = callbacks.getSystemContext ? callbacks.getSystemContext() : {};

    void callbacks.kernelRequest('reos/converse', {
      natural_language: trimmed,
      conversation_id: state.conversationId,
      turn_history: turnHistory,
      system_context: systemContext,
    }).then((raw) => {
      thinkingEl.remove();
      const result = raw as ReosConverseResult;
      const turnIndex = state.turns.length;

      // Record assistant turn
      state.turns.push({
        role: 'assistant',
        content: result.message,
        command: result.command ?? undefined,
        turnType: result.turn_type,
        timestamp: Date.now(),
      });

      // Store pending operation info
      state.pendingOperationId = result.operation_id ?? null;
      state.pendingCommand = result.command ?? null;

      // Telemetry: response rendered
      recordEvent('turn_rendered', {
        turn_type: result.turn_type,
        latency_ms: Date.now() - submitTs,
      });

      // Render the appropriate turn type
      switch (result.turn_type) {
        case 'clarify':
          appendInfoTurn(result.message, true, result.classification, turnIndex);
          setInputDisabled(false);
          inputEl.focus();
          break;

        case 'inform':
          appendInfoTurn(result.message, false, result.classification, turnIndex);
          setInputDisabled(false);
          inputEl.focus();
          break;

        case 'propose':
        case 'danger':
          appendCommandCard(
            result,
            (command, btn) => {
              // Run callback (unedited)
              recordEvent('command_approved', { command, operation_id: result.operation_id });
              executeCommand(
                command,
                result.operation_id,
                btn,
                btn.closest('.reos-card') as HTMLElement,
              );
            },
            (operationId, card) => {
              // Skip callback — call abort RPC and dim the card
              recordEvent('command_rejected', { operation_id: operationId });
              void callbacks.kernelRequest('reos/converse/abort', {
                operation_id: operationId,
              }).catch(() => {/* silent */});

              // Dim the card
              card.style.opacity = '0.35';
              card.style.pointerEvents = 'none';

              // Clear pending state
              state.pendingOperationId = null;
              state.pendingCommand = null;
              latestCardIsProposal = false;

              setInputDisabled(false);
              inputEl.focus();
            },
            (editedCommand, originalCommand, btn) => {
              // Edited run callback — fire correction telemetry then execute
              recordEvent('command_corrected', {
                original: originalCommand,
                edited: editedCommand,
                operation_id: result.operation_id,
              });
              recordEvent('command_approved', { command: editedCommand, operation_id: result.operation_id });
              executeCommand(
                editedCommand,
                result.operation_id,
                btn,
                btn.closest('.reos-card') as HTMLElement,
              );
            },
          );
          // Input stays disabled — user must click Run/Edit/Skip to continue
          // UNLESS they press n which will Skip
          break;

        case 'refuse':
          appendRefuseTurn(result.message);
          setInputDisabled(false);
          inputEl.focus();
          break;

        default:
          appendInfoTurn(result.message, false, result.classification, turnIndex);
          setInputDisabled(false);
          inputEl.focus();
          break;
      }
    }).catch((err: unknown) => {
      thinkingEl.remove();
      const errMsg = el('div');
      errMsg.style.cssText = `
        padding: 4px 0;
        color: rgba(239,68,68,0.8);
        font-size: 13px;
      `;
      errMsg.textContent = `Error: ${err instanceof Error ? err.message : String(err)}`;
      scrollBuffer.appendChild(errMsg);
      scrollToBottom();
      setInputDisabled(false);
      inputEl.focus();
    }).finally(() => {
      isWaiting = false;
    });
  }

  // ── Input event handlers ─────────────────────────────────────────────

  inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      submitInput(inputEl.value);
      return;
    }

    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (state.inputHistory.length === 0) return;
      state.historyIndex = Math.min(state.historyIndex + 1, state.inputHistory.length - 1);
      inputEl.value = state.inputHistory[state.historyIndex] ?? '';
      // Move cursor to end
      requestAnimationFrame(() => {
        inputEl.selectionStart = inputEl.selectionEnd = inputEl.value.length;
      });
      return;
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (state.historyIndex <= 0) {
        state.historyIndex = -1;
        inputEl.value = '';
        return;
      }
      state.historyIndex--;
      inputEl.value = state.inputHistory[state.historyIndex] ?? '';
      requestAnimationFrame(() => {
        inputEl.selectionStart = inputEl.selectionEnd = inputEl.value.length;
      });
      return;
    }

    // y / n keyboard shortcuts when a proposal card is the latest element
    if (latestCardIsProposal && !isWaiting && inputEl.value === '') {
      if (e.key === 'y' || e.key === 'Y') {
        e.preventDefault();
        latestRunBtn?.click();
        return;
      }
      if (e.key === 'n' || e.key === 'N') {
        e.preventDefault();
        latestSkipBtn?.click();
        return;
      }
    }
  });

  // ── New conversation button ──────────────────────────────────────────

  newConvBtn.addEventListener('click', () => {
    // Reset conversation state
    state.conversationId = crypto.randomUUID();
    state.turns = [];
    state.pendingOperationId = null;
    state.pendingCommand = null;
    state.inputHistory = [];
    state.historyIndex = -1;

    // Clear scroll buffer
    scrollBuffer.innerHTML = '';
    latestCardIsProposal = false;
    latestRunBtn = null;
    latestSkipBtn = null;

    // Reset input
    inputEl.value = '';
    setInputDisabled(false);
    isWaiting = false;

    inputEl.focus();
  });

  // ── Activate / Deactivate ────────────────────────────────────────────

  function activate(): void {
    updatePromptSigil();
    inputEl.focus();
  }

  function deactivate(): void {
    // Nothing to stop. Input state is preserved across tab switches.
  }

  return { container, activate, deactivate };
}
