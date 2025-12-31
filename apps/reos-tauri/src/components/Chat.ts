/**
 * Chat component for the center pane
 */

import { Component, KernelRequestFn, el } from './types';

export class Chat implements Component {
  private container: HTMLDivElement;
  private chatLog: HTMLDivElement;
  private input: HTMLInputElement;
  private sendBtn: HTMLButtonElement;

  constructor(private kernelRequest: KernelRequestFn) {
    this.container = el('div');
    this.container.className = 'center';
    this.container.style.flex = '1';
    this.container.style.display = 'flex';
    this.container.style.flexDirection = 'column';

    this.chatLog = el('div');
    this.chatLog.className = 'chat-log';
    this.chatLog.style.flex = '1';
    this.chatLog.style.padding = '12px';
    this.chatLog.style.overflow = 'auto';

    const inputRow = el('div');
    inputRow.className = 'input-row';
    inputRow.style.display = 'flex';
    inputRow.style.gap = '8px';
    inputRow.style.padding = '12px';
    inputRow.style.borderTop = '1px solid #ddd';

    this.input = el('input');
    this.input.className = 'chat-input';
    this.input.type = 'text';
    this.input.placeholder = 'Type a message…';
    this.input.style.flex = '1';

    this.sendBtn = el('button');
    this.sendBtn.className = 'send-btn';
    this.sendBtn.textContent = 'Send';

    inputRow.appendChild(this.input);
    inputRow.appendChild(this.sendBtn);

    this.container.appendChild(this.chatLog);
    this.container.appendChild(inputRow);

    // Event listeners
    this.sendBtn.addEventListener('click', () => void this.onSend());
    this.input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') void this.onSend();
    });
  }

  async init(): Promise<void> {
    // No async initialization needed for chat
  }

  private append(role: 'user' | 'reos', text: string): void {
    const row = el('div');
    row.className = `chat-row ${role}`;

    const bubble = el('div');
    bubble.className = `chat-bubble ${role}`;
    bubble.textContent = text;

    row.appendChild(bubble);
    this.chatLog.appendChild(row);
    this.chatLog.scrollTop = this.chatLog.scrollHeight;
  }

  private appendThinking(): { row: HTMLDivElement; bubble: HTMLDivElement } {
    const row = el('div') as HTMLDivElement;
    row.className = 'chat-row reos';

    const bubble = el('div') as HTMLDivElement;
    bubble.className = 'chat-bubble reos thinking';

    const dots = el('span') as HTMLSpanElement;
    dots.className = 'typing-dots';
    dots.innerHTML = '<span></span><span></span><span></span>';
    bubble.appendChild(dots);

    row.appendChild(bubble);
    this.chatLog.appendChild(row);
    this.chatLog.scrollTop = this.chatLog.scrollHeight;
    return { row, bubble };
  }

  private async onSend(): Promise<void> {
    const text = this.input.value.trim();
    if (!text) return;

    this.input.value = '';
    this.append('user', text);

    // Immediately show an empty ReOS bubble with a thinking animation
    const pending = this.appendThinking();

    // Ensure the browser paints the new bubbles before we start the kernel RPC
    // Note: `requestAnimationFrame` alone can resume into a microtask that still
    // runs before paint, so we also yield a macrotask
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    await new Promise<void>((resolve) => setTimeout(resolve, 0));

    try {
      const res = await this.kernelRequest('chat/respond', { text }) as {
        answer: string;
      };
      pending.bubble.classList.remove('thinking');
      pending.bubble.textContent = res.answer || '(no answer)';
    } catch (e) {
      pending.bubble.classList.remove('thinking');
      pending.bubble.textContent = `Error: ${String(e)}`;
    }
  }

  render(): HTMLElement {
    return this.container;
  }

  destroy(): void {
    // Cleanup if needed
  }
}
