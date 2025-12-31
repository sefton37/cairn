/**
 * Shared types and interfaces for UI components
 */

export interface Component {
  render(): HTMLElement;
  destroy?(): void;
}

export interface KernelRequestFn {
  (method: string, params: unknown): Promise<unknown>;
}

export class KernelError extends Error {
  code: number;

  constructor(message: string, code: number) {
    super(message);
    this.name = 'KernelError';
    this.code = code;
  }
}

// Helper function for creating DOM elements
export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: Record<string, string> = {}
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    node.setAttribute(k, v);
  }
  return node;
}

// UI component helpers
export function rowHeader(title: string): HTMLDivElement {
  const h = el('div');
  h.textContent = title;
  h.style.fontWeight = '600';
  h.style.marginTop = '12px';
  h.style.marginBottom = '4px';
  return h;
}

export function label(text: string): HTMLDivElement {
  const lbl = el('div');
  lbl.textContent = text;
  lbl.style.fontSize = '12px';
  lbl.style.marginTop = '8px';
  lbl.style.marginBottom = '2px';
  return lbl;
}

export function textInput(value: string): HTMLInputElement {
  const inp = el('input');
  inp.type = 'text';
  inp.value = value;
  inp.style.width = '100%';
  inp.style.padding = '4px';
  inp.style.fontSize = '13px';
  inp.style.border = '1px solid #ccc';
  inp.style.borderRadius = '3px';
  return inp;
}

export function textArea(value: string, heightPx = 90): HTMLTextAreaElement {
  const area = el('textarea');
  area.value = value;
  area.style.width = '100%';
  area.style.minHeight = `${heightPx}px`;
  area.style.padding = '6px';
  area.style.fontSize = '13px';
  area.style.fontFamily = 'monospace';
  area.style.border = '1px solid #ccc';
  area.style.borderRadius = '3px';
  return area;
}

export function smallButton(text: string): HTMLButtonElement {
  const btn = el('button');
  btn.textContent = text;
  btn.style.fontSize = '12px';
  btn.style.padding = '4px 8px';
  return btn;
}

// Tab system helpers
export interface Tab {
  id: string;
  label: string;
  content: () => HTMLElement;
}

export function createTabs(tabs: Tab[], onTabChange?: (tabId: string) => void): {
  container: HTMLDivElement;
  setActiveTab: (tabId: string) => void;
} {
  const container = el('div');
  container.style.display = 'flex';
  container.style.flexDirection = 'column';
  container.style.height = '100%';

  // Tab bar
  const tabBar = el('div');
  tabBar.style.display = 'flex';
  tabBar.style.borderBottom = '1px solid #ddd';
  tabBar.style.marginBottom = '12px';
  tabBar.style.gap = '4px';

  // Tab content area
  const tabContent = el('div');
  tabContent.style.flex = '1';
  tabContent.style.overflow = 'auto';

  let activeTabId = tabs[0]?.id || '';

  const tabButtons: Map<string, HTMLButtonElement> = new Map();

  function setActiveTab(tabId: string): void {
    activeTabId = tabId;

    // Update button styles
    tabButtons.forEach((btn, id) => {
      if (id === tabId) {
        btn.style.backgroundColor = '#fff';
        btn.style.borderBottom = '2px solid #0066cc';
        btn.style.fontWeight = '600';
      } else {
        btn.style.backgroundColor = 'transparent';
        btn.style.borderBottom = '2px solid transparent';
        btn.style.fontWeight = '400';
      }
    });

    // Render content
    tabContent.innerHTML = '';
    const tab = tabs.find(t => t.id === tabId);
    if (tab) {
      tabContent.appendChild(tab.content());
    }

    if (onTabChange) {
      onTabChange(tabId);
    }
  }

  // Create tab buttons
  tabs.forEach(tab => {
    const btn = el('button');
    btn.textContent = tab.label;
    btn.style.padding = '8px 16px';
    btn.style.fontSize = '13px';
    btn.style.border = 'none';
    btn.style.cursor = 'pointer';
    btn.style.background = 'transparent';
    btn.style.transition = 'all 0.2s';

    btn.addEventListener('click', () => setActiveTab(tab.id));
    btn.addEventListener('mouseenter', () => {
      if (activeTabId !== tab.id) {
        btn.style.backgroundColor = '#f5f5f5';
      }
    });
    btn.addEventListener('mouseleave', () => {
      if (activeTabId !== tab.id) {
        btn.style.backgroundColor = 'transparent';
      }
    });

    tabButtons.set(tab.id, btn);
    tabBar.appendChild(btn);
  });

  container.appendChild(tabBar);
  container.appendChild(tabContent);

  // Set initial active tab
  setActiveTab(activeTabId);

  return { container, setActiveTab };
}
