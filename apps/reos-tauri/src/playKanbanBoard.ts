/**
 * Play Kanban Board - Drag-and-drop Kanban component for Scenes
 *
 * Four columns representing scene stages:
 * - Planning
 * - In Progress
 * - Awaiting Data
 * - Complete
 */

import { el } from './dom';
import type { SceneWithAct, SceneStage } from './types';

// Column definitions
const COLUMNS: { stage: SceneStage; label: string; color: string }[] = [
  { stage: 'planning', label: 'Planning', color: '#9ca3af' },
  { stage: 'in_progress', label: 'In Progress', color: '#3b82f6' },
  { stage: 'awaiting_data', label: 'Awaiting Data', color: '#f59e0b' },
  { stage: 'complete', label: 'Complete', color: '#22c55e' },
];

interface PlayKanbanBoardOptions {
  scenes: SceneWithAct[];
  onStageChange: (sceneId: string, newStage: SceneStage, actId: string) => Promise<void>;
  onSceneClick: (sceneId: string, actId: string) => void;
}

export function createPlayKanbanBoard(options: PlayKanbanBoardOptions): {
  element: HTMLElement;
} {
  const { scenes, onStageChange, onSceneClick } = options;

  // Main container
  const board = el('div');
  board.className = 'kanban-board';
  board.style.cssText = `
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    height: 100%;
    min-height: 400px;
  `;

  // Group scenes by stage
  const scenesByStage: Record<SceneStage, SceneWithAct[]> = {
    planning: [],
    in_progress: [],
    awaiting_data: [],
    complete: [],
  };

  for (const scene of scenes) {
    const stage = (scene.stage as SceneStage) || 'planning';
    if (scenesByStage[stage]) {
      scenesByStage[stage].push(scene);
    } else {
      scenesByStage.planning.push(scene);
    }
  }

  // Create columns
  for (const column of COLUMNS) {
    const columnEl = createColumn(
      column,
      scenesByStage[column.stage],
      onStageChange,
      onSceneClick
    );
    board.appendChild(columnEl);
  }

  return {
    element: board,
  };
}

function createColumn(
  column: { stage: SceneStage; label: string; color: string },
  scenes: SceneWithAct[],
  onStageChange: (sceneId: string, newStage: SceneStage, actId: string) => Promise<void>,
  onSceneClick: (sceneId: string, actId: string) => void
): HTMLElement {
  const columnEl = el('div');
  columnEl.className = `kanban-column kanban-column-${column.stage}`;
  columnEl.dataset.stage = column.stage;
  columnEl.style.cssText = `
    display: flex;
    flex-direction: column;
    background: rgba(0, 0, 0, 0.2);
    border-radius: 12px;
    overflow: hidden;
  `;

  // Column header
  const header = el('div');
  header.className = 'kanban-column-header';
  header.style.cssText = `
    padding: 12px 16px;
    background: ${column.color}22;
    border-bottom: 2px solid ${column.color};
    display: flex;
    align-items: center;
    justify-content: space-between;
  `;

  const headerTitle = el('span');
  headerTitle.textContent = column.label;
  headerTitle.style.cssText = `
    font-size: 13px;
    font-weight: 600;
    color: ${column.color};
  `;

  const headerCount = el('span');
  headerCount.textContent = String(scenes.length);
  headerCount.style.cssText = `
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 10px;
    background: ${column.color}33;
    color: ${column.color};
  `;

  header.appendChild(headerTitle);
  header.appendChild(headerCount);
  columnEl.appendChild(header);

  // Cards container (drop zone)
  const cardsContainer = el('div');
  cardsContainer.className = 'kanban-cards';
  cardsContainer.dataset.stage = column.stage;
  cardsContainer.style.cssText = `
    flex: 1;
    padding: 12px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-height: 100px;
  `;

  // Drag and drop handlers
  cardsContainer.addEventListener('dragover', (e) => {
    e.preventDefault();
    cardsContainer.style.background = 'rgba(59, 130, 246, 0.1)';
    cardsContainer.style.outline = '2px dashed rgba(59, 130, 246, 0.5)';
    cardsContainer.style.outlineOffset = '-4px';
  });

  cardsContainer.addEventListener('dragleave', (e) => {
    // Only reset if leaving the container entirely
    if (!cardsContainer.contains(e.relatedTarget as Node)) {
      cardsContainer.style.background = 'transparent';
      cardsContainer.style.outline = 'none';
    }
  });

  cardsContainer.addEventListener('drop', async (e) => {
    e.preventDefault();
    cardsContainer.style.background = 'transparent';
    cardsContainer.style.outline = 'none';

    const sceneId = e.dataTransfer?.getData('scene_id');
    const actId = e.dataTransfer?.getData('act_id');
    const sourceStage = e.dataTransfer?.getData('source_stage');

    if (sceneId && actId && sourceStage !== column.stage) {
      await onStageChange(sceneId, column.stage, actId);
    }
  });

  // Add scene cards
  for (const scene of scenes) {
    const card = createSceneCard(scene, onSceneClick);
    cardsContainer.appendChild(card);
  }

  // Empty state
  if (scenes.length === 0) {
    const emptyState = el('div');
    emptyState.textContent = 'No scenes';
    emptyState.style.cssText = `
      text-align: center;
      padding: 24px;
      color: rgba(255, 255, 255, 0.3);
      font-size: 12px;
      font-style: italic;
    `;
    cardsContainer.appendChild(emptyState);
  }

  columnEl.appendChild(cardsContainer);

  return columnEl;
}

function createSceneCard(
  scene: SceneWithAct,
  onSceneClick: (sceneId: string, actId: string) => void
): HTMLElement {
  const card = el('div');
  card.className = 'kanban-card';
  card.draggable = true;
  card.dataset.sceneId = scene.scene_id;
  card.dataset.actId = scene.act_id;

  const actColor = scene.act_color || '#8b5cf6';

  card.style.cssText = `
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-left: 3px solid ${actColor};
    border-radius: 8px;
    padding: 12px;
    cursor: grab;
    transition: all 0.15s;
  `;

  // Drag handlers
  card.addEventListener('dragstart', (e) => {
    card.style.opacity = '0.5';
    card.style.cursor = 'grabbing';
    e.dataTransfer?.setData('scene_id', scene.scene_id);
    e.dataTransfer?.setData('act_id', scene.act_id);
    e.dataTransfer?.setData('source_stage', scene.stage);
  });

  card.addEventListener('dragend', () => {
    card.style.opacity = '1';
    card.style.cursor = 'grab';
  });

  // Click handler
  card.addEventListener('click', () => {
    onSceneClick(scene.scene_id, scene.act_id);
  });

  // Hover effect
  card.addEventListener('mouseenter', () => {
    card.style.background = 'rgba(255, 255, 255, 0.08)';
    card.style.borderColor = 'rgba(255, 255, 255, 0.2)';
  });

  card.addEventListener('mouseleave', () => {
    card.style.background = 'rgba(255, 255, 255, 0.05)';
    card.style.borderColor = 'rgba(255, 255, 255, 0.1)';
  });

  // Act badge
  const actBadge = el('div');
  actBadge.textContent = scene.act_title;
  actBadge.style.cssText = `
    font-size: 10px;
    padding: 2px 8px;
    border-radius: 10px;
    background: ${actColor}33;
    color: ${actColor};
    display: inline-block;
    margin-bottom: 8px;
    font-weight: 500;
  `;
  card.appendChild(actBadge);

  // Title
  const title = el('div');
  title.textContent = scene.title;
  title.style.cssText = `
    font-size: 13px;
    color: #e5e7eb;
    font-weight: 500;
    line-height: 1.4;
    margin-bottom: 4px;
  `;
  card.appendChild(title);

  // Notes preview (if any)
  if (scene.notes && scene.notes.trim()) {
    const notesPreview = el('div');
    notesPreview.textContent = scene.notes.slice(0, 60) + (scene.notes.length > 60 ? '...' : '');
    notesPreview.style.cssText = `
      font-size: 11px;
      color: rgba(255, 255, 255, 0.5);
      line-height: 1.4;
      overflow: hidden;
      text-overflow: ellipsis;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
    `;
    card.appendChild(notesPreview);
  }

  // Link indicator
  if (scene.link) {
    const linkIndicator = el('div');
    linkIndicator.innerHTML = '🔗';
    linkIndicator.title = scene.link;
    linkIndicator.style.cssText = `
      font-size: 10px;
      margin-top: 6px;
      opacity: 0.6;
    `;
    card.appendChild(linkIndicator);
  }

  // Calendar indicator
  if (scene.calendar_event_id || scene.thunderbird_event_id) {
    const calendarIndicator = el('div');
    calendarIndicator.innerHTML = '📅';
    calendarIndicator.title = 'Linked to calendar event';
    calendarIndicator.style.cssText = `
      font-size: 10px;
      margin-top: 6px;
      opacity: 0.6;
    `;
    card.appendChild(calendarIndicator);
  }

  return card;
}
