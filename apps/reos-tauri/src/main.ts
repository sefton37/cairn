import { invoke } from '@tauri-apps/api/core';
import { WebviewWindow } from '@tauri-apps/api/webviewWindow';
import { z } from 'zod';

import './style.css';
import { KernelError, el, Navigation, Chat, PlayInspector } from './components';

const JsonRpcResponseSchema = z.object({
  jsonrpc: z.literal('2.0'),
  id: z.union([z.string(), z.number(), z.null()]).optional(),
  result: z.unknown().optional(),
  error: z
    .object({
      code: z.number(),
      message: z.string(),
      data: z.unknown().optional()
    })
    .optional()
});

type PlayMeReadResult = {
  markdown: string;
};

async function kernelRequest(method: string, params: unknown): Promise<unknown> {
  const raw = await invoke('kernel_request', { method, params });
  const parsed = JsonRpcResponseSchema.parse(raw);
  if (parsed.error) {
    throw new KernelError(parsed.error.message, parsed.error.code);
  }
  return parsed.result;
}

function buildUi() {
  const query = new URLSearchParams(window.location.search);
  if (query.get('view') === 'me') {
    void buildMeWindow();
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

  // Create components
  const navigation = new Navigation(kernelRequest);
  const chat = new Chat(kernelRequest);
  const playInspector = new PlayInspector(kernelRequest);

  // Create inspection pane container
  const inspection = el('div');
  inspection.className = 'inspection';
  inspection.style.width = '420px';
  inspection.style.borderLeft = '1px solid #ddd';
  inspection.style.margin = '0';
  inspection.style.padding = '0';
  inspection.style.overflow = 'auto';

  // Append components to shell
  shell.appendChild(navigation.render());
  shell.appendChild(chat.render());
  shell.appendChild(inspection);

  root.appendChild(shell);

  // Set up component callbacks
  async function openMeWindow() {
    try {
      const existing = await WebviewWindow.getByLabel('me');
      if (existing) {
        await existing.setFocus();
        return;
      }
    } catch {
      // Best effort: if getByLabel fails, fall through and create a new window
    }

    const w = new WebviewWindow('me', {
      title: 'Me — ReOS',
      url: '/?view=me',
      width: 900,
      height: 700
    });
    void w;
  }

  navigation.setOnMeClick(() => void openMeWindow());
  navigation.setOnActSelected(async () => {
    // Refresh PlayInspector when act changes
    await playInspector.init();
  });

  // Append PlayInspector to inspection pane
  inspection.appendChild(playInspector.render());

  // Initialize components
  void (async () => {
    try {
      await navigation.init();
      await chat.init();
      await playInspector.init();
    } catch (e) {
      console.error('Startup error:', e);
    }
  })();
}

async function buildMeWindow() {
  const root = document.getElementById('app');
  if (!root) return;
  root.innerHTML = '';

  root.style.padding = '20px';
  root.style.fontFamily = 'system-ui, sans-serif';

  const title = el('h2');
  title.textContent = 'Me';
  title.style.marginTop = '0';
  root.appendChild(title);

  const hint = el('div');
  hint.style.fontSize = '13px';
  hint.style.opacity = '0.8';
  hint.style.marginBottom = '12px';
  hint.textContent =
    'This is the top-level KB for The Play. Document your charter, values, and constraints here.';
  root.appendChild(hint);

  const editor = el('textarea');
  editor.style.width = '100%';
  editor.style.minHeight = '600px';
  editor.style.fontSize = '14px';
  editor.style.fontFamily = 'monospace';
  editor.style.padding = '12px';
  editor.style.border = '1px solid #ccc';
  editor.style.borderRadius = '4px';
  root.appendChild(editor);

  try {
    const res = (await kernelRequest('play/me/read', {})) as PlayMeReadResult;
    editor.value = res.markdown ?? '';
  } catch (e) {
    editor.value = `# Error loading Me\n\n${String(e)}`;
  }

  editor.addEventListener('input', () => {
    // Auto-save or manual save could be implemented here
  });
}

// Start the app
document.addEventListener('DOMContentLoaded', () => {
  buildUi();
});
