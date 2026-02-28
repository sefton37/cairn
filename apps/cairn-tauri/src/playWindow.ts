/**
 * Play Window - Standalone 1080p window for The Play
 *
 * This window replaces the overlay modal with a dedicated window containing:
 * - Act View: Notion-lite knowledgebase with nested markdown pages
 * - Scene View: Kanban board of all Scenes, filterable by Act
 */

import { el } from './dom';
import { kernelRequest } from './kernel';
import { createPlayActView } from './playActView';
import { createPlaySceneView } from './playSceneView';
import type {
  PlayActsListResult,
} from './types';

type PlayWindowView = 'acts' | 'scenes';

interface PlayWindowState {
  currentView: PlayWindowView;
  actsCache: PlayActsListResult['acts'];
  activeActId: string | null;
}

/**
 * Build the standalone Play window UI.
 * This is called when the URL contains ?view=play
 */
export async function buildPlayWindow(): Promise<void> {
  const root = document.getElementById('app');
  if (!root) return;

  root.innerHTML = '';

  const state: PlayWindowState = {
    currentView: 'acts',
    actsCache: [],
    activeActId: null,
  };

  // Main container
  const container = el('div');
  container.className = 'play-window';
  container.style.cssText = `
    height: 100vh;
    display: flex;
    flex-direction: column;
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    color: #e5e7eb;
    font-family: system-ui, -apple-system, sans-serif;
  `;

  // Header with tabs
  const header = el('div');
  header.className = 'play-window-header';
  header.style.cssText = `
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 24px;
    background: rgba(0, 0, 0, 0.3);
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  `;

  // Title
  const title = el('h1');
  title.textContent = 'The Play';
  title.style.cssText = `
    margin: 0;
    font-size: 18px;
    font-weight: 600;
    color: #e5e7eb;
  `;

  // View tabs
  const tabsContainer = el('div');
  tabsContainer.className = 'play-tabs';
  tabsContainer.style.cssText = `
    display: flex;
    gap: 4px;
    padding: 4px;
    background: rgba(0, 0, 0, 0.2);
    border-radius: 8px;
  `;

  const actTab = createTab('Act View', 'acts', state, renderContent);
  const sceneTab = createTab('Scene View', 'scenes', state, renderContent);

  tabsContainer.appendChild(actTab);
  tabsContainer.appendChild(sceneTab);

  header.appendChild(title);
  header.appendChild(tabsContainer);

  // Content area
  const contentArea = el('div');
  contentArea.className = 'play-window-content';
  contentArea.style.cssText = `
    flex: 1;
    display: flex;
    overflow: hidden;
  `;

  container.appendChild(header);
  container.appendChild(contentArea);
  root.appendChild(container);

  // Initialize views
  let actView: ReturnType<typeof createPlayActView> | null = null;
  let sceneView: ReturnType<typeof createPlaySceneView> | null = null;

  // Load initial data
  async function loadData() {
    try {
      const result = await kernelRequest('play/acts/list', {}) as PlayActsListResult;
      state.actsCache = result.acts ?? [];
      state.activeActId = result.active_act_id;
    } catch (e) {
      console.error('Failed to load Play data:', e);
    }
  }

  // Render the current view
  function renderContent() {
    contentArea.innerHTML = '';
    updateTabStyles(actTab, sceneTab, state.currentView);

    if (state.currentView === 'acts') {
      if (!actView) {
        actView = createPlayActView({
          onActsChange: async () => {
            await loadData();
          },
          kernelRequest,
        });
      }
      actView.refresh();
      contentArea.appendChild(actView.element);
    } else {
      if (!sceneView) {
        sceneView = createPlaySceneView({
          onSceneChange: async () => {
            await loadData();
          },
          kernelRequest,
        });
      }
      sceneView.refresh();
      contentArea.appendChild(sceneView.element);
    }
  }

  await loadData();
  renderContent();
}

function createTab(
  label: string,
  view: PlayWindowView,
  state: PlayWindowState,
  onSwitch: () => void
): HTMLButtonElement {
  const tab = el('button') as HTMLButtonElement;
  tab.textContent = label;
  tab.dataset.view = view;
  tab.style.cssText = `
    padding: 8px 16px;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
    transition: all 0.2s;
  `;

  tab.addEventListener('click', () => {
    state.currentView = view;
    onSwitch();
  });

  return tab;
}

function updateTabStyles(
  actTab: HTMLButtonElement,
  sceneTab: HTMLButtonElement,
  currentView: PlayWindowView
) {
  const activeStyle = `
    background: rgba(59, 130, 246, 0.3);
    color: #fff;
  `;
  const inactiveStyle = `
    background: transparent;
    color: rgba(255, 255, 255, 0.5);
  `;

  actTab.style.cssText += currentView === 'acts' ? activeStyle : inactiveStyle;
  sceneTab.style.cssText += currentView === 'scenes' ? activeStyle : inactiveStyle;
}
