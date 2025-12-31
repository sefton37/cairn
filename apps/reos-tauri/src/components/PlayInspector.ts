/**
 * Play Inspector component with tabbed interface
 *
 * Clean, elegant multi-tab view for Acts → Scenes → Beats → Todos
 * Each level has tabs for: Charter, Notes, Children (list), KB
 *
 * Designed to complement chat-first workflow - UI for viewing/light editing,
 * chat for complex operations.
 */

import {
  Component,
  KernelRequestFn,
  KernelError,
  el,
  label,
  textInput,
  textArea,
  smallButton,
  createTabs,
  Tab,
} from './types';

interface ActData {
  act_id: string;
  title: string;
  active: boolean;
  notes: string;
  charter: string;
}

interface SceneData {
  scene_id: string;
  title: string;
  intent: string;
  status: string;
  time_horizon: string;
  notes: string;
  charter: string;
}

interface BeatData {
  beat_id: string;
  title: string;
  status: string;
  notes: string;
  link: string | null;
  charter: string;
}

interface TodoData {
  todo_id: string;
  title: string;
  status: string;
  notes: string;
  completed: boolean;
}

interface KbFile {
  path: string;
  size: number;
}

interface KbWritePreviewResult {
  path: string;
  exists: boolean;
  sha256_current: string;
  expected_sha256_current: string;
  sha256_new: string;
  diff: string;
}

export class PlayInspector implements Component {
  private container: HTMLDivElement;
  private breadcrumbEl: HTMLDivElement;
  private contentEl: HTMLDivElement;

  // State
  private acts: ActData[] = [];
  private activeActId: string | null = null;

  private scenes: SceneData[] = [];
  private selectedSceneId: string | null = null;

  private beats: BeatData[] = [];
  private selectedBeatId: string | null = null;

  private todos: TodoData[] = [];

  // KB state
  private kbFiles: string[] = [];
  private kbPath = 'kb.md';
  private kbText = '';
  private kbPreview: KbWritePreviewResult | null = null;

  constructor(private kernelRequest: KernelRequestFn) {
    this.container = el('div');
    this.container.className = 'play-inspector';
    this.container.style.display = 'flex';
    this.container.style.flexDirection = 'column';
    this.container.style.height = '100%';
    this.container.style.padding = '12px';
    this.container.style.overflow = 'hidden';

    // Breadcrumb navigation
    this.breadcrumbEl = el('div');
    this.breadcrumbEl.style.marginBottom = '12px';
    this.breadcrumbEl.style.fontSize = '13px';
    this.breadcrumbEl.style.color = '#666';

    // Content area
    this.contentEl = el('div');
    this.contentEl.style.flex = '1';
    this.contentEl.style.overflow = 'hidden';
    this.contentEl.style.display = 'flex';
    this.contentEl.style.flexDirection = 'column';

    this.container.appendChild(this.breadcrumbEl);
    this.container.appendChild(this.contentEl);
  }

  render(): HTMLElement {
    return this.container;
  }

  async init(): Promise<void> {
    await this.loadActs();
    this.renderBreadcrumb();
    await this.renderContent();
  }

  private async loadActs(): Promise<void> {
    try {
      const res = (await this.kernelRequest('play/acts/list', {})) as {
        acts: ActData[];
        active_act_id: string | null;
      };
      this.acts = res.acts || [];
      this.activeActId = res.active_act_id;
    } catch (err) {
      console.error('Failed to load acts:', err);
      this.acts = [];
    }
  }

  private async loadScenes(): Promise<void> {
    if (!this.activeActId) {
      this.scenes = [];
      return;
    }
    try {
      const res = (await this.kernelRequest('play/scenes/list', {
        act_id: this.activeActId,
      })) as { scenes: SceneData[] };
      this.scenes = res.scenes || [];
    } catch (err) {
      console.error('Failed to load scenes:', err);
      this.scenes = [];
    }
  }

  private async loadBeats(): Promise<void> {
    if (!this.activeActId || !this.selectedSceneId) {
      this.beats = [];
      return;
    }
    try {
      const res = (await this.kernelRequest('play/beats/list', {
        act_id: this.activeActId,
        scene_id: this.selectedSceneId,
      })) as { beats: BeatData[] };
      this.beats = res.beats || [];
    } catch (err) {
      console.error('Failed to load beats:', err);
      this.beats = [];
    }
  }

  private async loadTodos(): Promise<void> {
    if (!this.activeActId || !this.selectedSceneId || !this.selectedBeatId) {
      this.todos = [];
      return;
    }
    try {
      const res = (await this.kernelRequest('play/todos/list', {
        act_id: this.activeActId,
        scene_id: this.selectedSceneId,
        beat_id: this.selectedBeatId,
      })) as { todos: TodoData[] };
      this.todos = res.todos || [];
    } catch (err) {
      console.error('Failed to load todos:', err);
      this.todos = [];
    }
  }

  private async loadKbFiles(): Promise<void> {
    if (!this.activeActId) {
      this.kbFiles = [];
      return;
    }
    try {
      const res = (await this.kernelRequest('play/kb/list', {
        act_id: this.activeActId,
        scene_id: this.selectedSceneId,
        beat_id: this.selectedBeatId,
      })) as { files: KbFile[] };
      this.kbFiles = (res.files || []).map(f => f.path);
    } catch (err) {
      console.error('Failed to load KB files:', err);
      this.kbFiles = [];
    }
  }

  private renderBreadcrumb(): void {
    this.breadcrumbEl.innerHTML = '';

    const parts: HTMLElement[] = [];

    // "The Play" always shown
    const playLink = el('span');
    playLink.textContent = 'The Play';
    playLink.style.cursor = 'pointer';
    playLink.style.textDecoration = 'underline';
    playLink.addEventListener('click', () => {
      this.selectedSceneId = null;
      this.selectedBeatId = null;
      void this.renderContent();
    });
    parts.push(playLink);

    // Act (if active)
    if (this.activeActId) {
      const act = this.acts.find(a => a.act_id === this.activeActId);
      if (act) {
        parts.push(el('span'));
        parts[parts.length - 1].textContent = ' → ';

        const actLink = el('span');
        actLink.textContent = act.title;
        actLink.style.cursor = 'pointer';
        actLink.style.textDecoration = 'underline';
        actLink.addEventListener('click', () => {
          this.selectedSceneId = null;
          this.selectedBeatId = null;
          void this.renderContent();
        });
        parts.push(actLink);
      }
    }

    // Scene (if selected)
    if (this.selectedSceneId) {
      const scene = this.scenes.find(s => s.scene_id === this.selectedSceneId);
      if (scene) {
        parts.push(el('span'));
        parts[parts.length - 1].textContent = ' → ';

        const sceneLink = el('span');
        sceneLink.textContent = scene.title;
        sceneLink.style.cursor = 'pointer';
        sceneLink.style.textDecoration = 'underline';
        sceneLink.addEventListener('click', () => {
          this.selectedBeatId = null;
          void this.renderContent();
        });
        parts.push(sceneLink);
      }
    }

    // Beat (if selected)
    if (this.selectedBeatId) {
      const beat = this.beats.find(b => b.beat_id === this.selectedBeatId);
      if (beat) {
        parts.push(el('span'));
        parts[parts.length - 1].textContent = ' → ';

        const beatSpan = el('span');
        beatSpan.textContent = beat.title;
        beatSpan.style.fontWeight = '600';
        parts.push(beatSpan);
      }
    }

    parts.forEach(p => this.breadcrumbEl.appendChild(p));
  }

  private async renderContent(): Promise<void> {
    this.contentEl.innerHTML = '';
    this.renderBreadcrumb();

    if (!this.activeActId) {
      // Show Act selector
      this.renderActSelector();
    } else if (this.selectedBeatId) {
      // Beat view (has Todos)
      await this.loadBeats();
      await this.loadTodos();
      await this.loadKbFiles();
      this.renderBeatView();
    } else if (this.selectedSceneId) {
      // Scene view (has Beats)
      await this.loadScenes();
      await this.loadBeats();
      await this.loadKbFiles();
      this.renderSceneView();
    } else {
      // Act view (has Scenes)
      await this.loadScenes();
      await this.loadKbFiles();
      this.renderActView();
    }
  }

  // ========================================
  // Act Selector (when no act is active)
  // ========================================

  private renderActSelector(): void {
    const container = el('div');
    container.style.padding = '20px';

    const title = el('h2');
    title.textContent = 'Select an Act';
    title.style.marginBottom = '16px';
    container.appendChild(title);

    if (this.acts.length === 0) {
      const emptyMsg = el('p');
      emptyMsg.textContent = 'No Acts yet. Use chat to create one: "Create a new Act called..."';
      emptyMsg.style.color = '#666';
      emptyMsg.style.fontStyle = 'italic';
      container.appendChild(emptyMsg);
    } else {
      this.acts.forEach(act => {
        const actBtn = el('button');
        actBtn.textContent = `${act.title} ${act.active ? '(active)' : ''}`;
        actBtn.style.display = 'block';
        actBtn.style.width = '100%';
        actBtn.style.padding = '12px';
        actBtn.style.marginBottom = '8px';
        actBtn.style.textAlign = 'left';
        actBtn.style.cursor = 'pointer';
        actBtn.style.border = '1px solid #ddd';
        actBtn.style.borderRadius = '4px';
        actBtn.style.backgroundColor = act.active ? '#f0f8ff' : '#fff';

        actBtn.addEventListener('click', async () => {
          try {
            await this.kernelRequest('play/acts/set_active', { act_id: act.act_id });
            await this.loadActs();
            await this.renderContent();
          } catch (err) {
            console.error('Failed to set active act:', err);
          }
        });

        container.appendChild(actBtn);
      });
    }

    this.contentEl.appendChild(container);
  }

  // ========================================
  // Act View (Charter / Notes / Scenes / KB)
  // ========================================

  private renderActView(): void {
    const act = this.acts.find(a => a.act_id === this.activeActId);
    if (!act) return;

    const tabs: Tab[] = [
      {
        id: 'charter',
        label: '📜 Charter',
        content: () => this.renderCharterTab(act.charter, async (newCharter) => {
          await this.saveActCharter(newCharter);
        }),
      },
      {
        id: 'notes',
        label: '📝 Notes',
        content: () => this.renderNotesTab(act.notes, async (newNotes) => {
          await this.saveActNotes(newNotes);
        }),
      },
      {
        id: 'scenes',
        label: '🎬 Scenes',
        content: () => this.renderScenesList(),
      },
      {
        id: 'kb',
        label: '📚 KB',
        content: () => this.renderKbTab(),
      },
    ];

    const { container } = createTabs(tabs);
    this.contentEl.appendChild(container);
  }

  // ========================================
  // Scene View (Charter / Notes / Beats / KB)
  // ========================================

  private renderSceneView(): void {
    const scene = this.scenes.find(s => s.scene_id === this.selectedSceneId);
    if (!scene) return;

    const tabs: Tab[] = [
      {
        id: 'charter',
        label: '📜 Charter',
        content: () => this.renderCharterTab(scene.charter, async (newCharter) => {
          await this.saveSceneCharter(newCharter);
        }),
      },
      {
        id: 'notes',
        label: '📝 Notes',
        content: () => this.renderNotesTab(scene.notes, async (newNotes) => {
          await this.saveSceneNotes(newNotes);
        }),
      },
      {
        id: 'beats',
        label: '🥁 Beats',
        content: () => this.renderBeatsList(),
      },
      {
        id: 'kb',
        label: '📚 KB',
        content: () => this.renderKbTab(),
      },
    ];

    const { container } = createTabs(tabs);
    this.contentEl.appendChild(container);
  }

  // ========================================
  // Beat View (Charter / Notes / Todos / KB)
  // ========================================

  private renderBeatView(): void {
    const beat = this.beats.find(b => b.beat_id === this.selectedBeatId);
    if (!beat) return;

    const tabs: Tab[] = [
      {
        id: 'charter',
        label: '📜 Charter',
        content: () => this.renderCharterTab(beat.charter, async (newCharter) => {
          await this.saveBeatCharter(newCharter);
        }),
      },
      {
        id: 'notes',
        label: '📝 Notes',
        content: () => this.renderNotesTab(beat.notes, async (newNotes) => {
          await this.saveBeatNotes(newNotes);
        }),
      },
      {
        id: 'todos',
        label: '✅ Todos',
        content: () => this.renderTodosList(),
      },
      {
        id: 'kb',
        label: '📚 KB',
        content: () => this.renderKbTab(),
      },
    ];

    const { container } = createTabs(tabs);
    this.contentEl.appendChild(container);
  }

  // ========================================
  // Reusable Tab Content Renderers
  // ========================================

  private renderCharterTab(charter: string, onSave: (text: string) => Promise<void>): HTMLElement {
    const container = el('div');
    container.style.padding = '8px';

    const hint = el('p');
    hint.textContent = 'Define the purpose and goals (like a project charter). Edit here or use chat.';
    hint.style.fontSize = '12px';
    hint.style.color = '#666';
    hint.style.marginBottom = '8px';
    container.appendChild(hint);

    const textarea = textArea(charter, 200);
    container.appendChild(textarea);

    const saveBtn = smallButton('Save Charter');
    saveBtn.style.marginTop = '8px';
    saveBtn.addEventListener('click', async () => {
      saveBtn.disabled = true;
      saveBtn.textContent = 'Saving...';
      try {
        await onSave(textarea.value);
        saveBtn.textContent = '✓ Saved';
        setTimeout(() => {
          saveBtn.textContent = 'Save Charter';
          saveBtn.disabled = false;
        }, 1500);
      } catch (err) {
        console.error('Save failed:', err);
        saveBtn.textContent = 'Save failed';
        saveBtn.disabled = false;
      }
    });
    container.appendChild(saveBtn);

    return container;
  }

  private renderNotesTab(notes: string, onSave: (text: string) => Promise<void>): HTMLElement {
    const container = el('div');
    container.style.padding = '8px';

    const hint = el('p');
    hint.textContent = 'Markdown notes for this level. Edit here or use chat.';
    hint.style.fontSize = '12px';
    hint.style.color = '#666';
    hint.style.marginBottom = '8px';
    container.appendChild(hint);

    const textarea = textArea(notes, 200);
    container.appendChild(textarea);

    const saveBtn = smallButton('Save Notes');
    saveBtn.style.marginTop = '8px';
    saveBtn.addEventListener('click', async () => {
      saveBtn.disabled = true;
      saveBtn.textContent = 'Saving...';
      try {
        await onSave(textarea.value);
        saveBtn.textContent = '✓ Saved';
        setTimeout(() => {
          saveBtn.textContent = 'Save Notes';
          saveBtn.disabled = false;
        }, 1500);
      } catch (err) {
        console.error('Save failed:', err);
        saveBtn.textContent = 'Save failed';
        saveBtn.disabled = false;
      }
    });
    container.appendChild(saveBtn);

    return container;
  }

  private renderScenesList(): HTMLElement {
    const container = el('div');
    container.style.padding = '8px';

    const hint = el('p');
    hint.textContent = 'Scenes (1+ months). Click to drill down. Use chat to create: "Add a scene called..."';
    hint.style.fontSize = '12px';
    hint.style.color = '#666';
    hint.style.marginBottom = '12px';
    container.appendChild(hint);

    if (this.scenes.length === 0) {
      const empty = el('p');
      empty.textContent = 'No scenes yet.';
      empty.style.fontStyle = 'italic';
      empty.style.color = '#999';
      container.appendChild(empty);
    } else {
      this.scenes.forEach(scene => {
        const sceneCard = el('div');
        sceneCard.style.padding = '12px';
        sceneCard.style.border = '1px solid #ddd';
        sceneCard.style.borderRadius = '4px';
        sceneCard.style.marginBottom = '8px';
        sceneCard.style.cursor = 'pointer';
        sceneCard.style.transition = 'background 0.2s';

        sceneCard.addEventListener('mouseenter', () => {
          sceneCard.style.backgroundColor = '#f5f5f5';
        });
        sceneCard.addEventListener('mouseleave', () => {
          sceneCard.style.backgroundColor = '#fff';
        });
        sceneCard.addEventListener('click', () => {
          this.selectedSceneId = scene.scene_id;
          void this.renderContent();
        });

        const title = el('div');
        title.textContent = scene.title;
        title.style.fontWeight = '600';
        title.style.marginBottom = '4px';
        sceneCard.appendChild(title);

        if (scene.intent) {
          const intent = el('div');
          intent.textContent = scene.intent;
          intent.style.fontSize = '12px';
          intent.style.color = '#666';
          sceneCard.appendChild(intent);
        }

        container.appendChild(sceneCard);
      });
    }

    return container;
  }

  private renderBeatsList(): HTMLElement {
    const container = el('div');
    container.style.padding = '8px';

    const hint = el('p');
    hint.textContent = 'Beats (1+ weeks). Click to drill down. Use chat to create: "Add a beat called..."';
    hint.style.fontSize = '12px';
    hint.style.color = '#666';
    hint.style.marginBottom = '12px';
    container.appendChild(hint);

    if (this.beats.length === 0) {
      const empty = el('p');
      empty.textContent = 'No beats yet.';
      empty.style.fontStyle = 'italic';
      empty.style.color = '#999';
      container.appendChild(empty);
    } else {
      this.beats.forEach(beat => {
        const beatCard = el('div');
        beatCard.style.padding = '12px';
        beatCard.style.border = '1px solid #ddd';
        beatCard.style.borderRadius = '4px';
        beatCard.style.marginBottom = '8px';
        beatCard.style.cursor = 'pointer';
        beatCard.style.transition = 'background 0.2s';

        beatCard.addEventListener('mouseenter', () => {
          beatCard.style.backgroundColor = '#f5f5f5';
        });
        beatCard.addEventListener('mouseleave', () => {
          beatCard.style.backgroundColor = '#fff';
        });
        beatCard.addEventListener('click', () => {
          this.selectedBeatId = beat.beat_id;
          void this.renderContent();
        });

        const title = el('div');
        title.textContent = beat.title;
        title.style.fontWeight = '600';
        beatCard.appendChild(title);

        if (beat.status) {
          const status = el('div');
          status.textContent = `Status: ${beat.status}`;
          status.style.fontSize = '12px';
          status.style.color = '#666';
          status.style.marginTop = '4px';
          beatCard.appendChild(status);
        }

        container.appendChild(beatCard);
      });
    }

    return container;
  }

  private renderTodosList(): HTMLElement {
    const container = el('div');
    container.style.padding = '8px';

    const hint = el('p');
    hint.textContent = 'Todos (< 1 week). Check off when complete. Use chat to manage: "Add a todo..."';
    hint.style.fontSize = '12px';
    hint.style.color = '#666';
    hint.style.marginBottom = '12px';
    container.appendChild(hint);

    if (this.todos.length === 0) {
      const empty = el('p');
      empty.textContent = 'No todos yet.';
      empty.style.fontStyle = 'italic';
      empty.style.color = '#999';
      container.appendChild(empty);
    } else {
      this.todos.forEach(todo => {
        const todoRow = el('div');
        todoRow.style.display = 'flex';
        todoRow.style.alignItems = 'center';
        todoRow.style.padding = '8px';
        todoRow.style.borderBottom = '1px solid #eee';

        const checkbox = el('input');
        checkbox.type = 'checkbox';
        checkbox.checked = todo.completed;
        checkbox.style.marginRight = '8px';
        checkbox.addEventListener('change', async () => {
          await this.toggleTodoCompleted(todo.todo_id, checkbox.checked);
        });
        todoRow.appendChild(checkbox);

        const titleSpan = el('span');
        titleSpan.textContent = todo.title;
        titleSpan.style.flex = '1';
        if (todo.completed) {
          titleSpan.style.textDecoration = 'line-through';
          titleSpan.style.color = '#999';
        }
        todoRow.appendChild(titleSpan);

        container.appendChild(todoRow);
      });
    }

    return container;
  }

  private renderKbTab(): HTMLElement {
    const container = el('div');
    container.style.padding = '8px';

    const hint = el('p');
    hint.textContent = 'Knowledge Base - scoped to current context. Files: ' + (this.kbFiles.length || '0');
    hint.style.fontSize = '12px';
    hint.style.color = '#666';
    hint.style.marginBottom = '12px';
    container.appendChild(hint);

    // KB file list
    if (this.kbFiles.length > 0) {
      const fileList = el('div');
      fileList.style.marginBottom = '12px';
      this.kbFiles.forEach(file => {
        const fileBtn = smallButton(file);
        fileBtn.style.marginRight = '4px';
        fileBtn.style.marginBottom = '4px';
        fileBtn.addEventListener('click', () => {
          this.kbPath = file;
          void this.loadKbFile();
        });
        fileList.appendChild(fileBtn);
      });
      container.appendChild(fileList);
    }

    // Simple KB viewer/editor
    const pathLabel = label(`File: ${this.kbPath}`);
    container.appendChild(pathLabel);

    const kbTextarea = textArea(this.kbText, 150);
    container.appendChild(kbTextarea);

    const btnRow = el('div');
    btnRow.style.marginTop = '8px';

    const loadBtn = smallButton('Load');
    loadBtn.addEventListener('click', async () => {
      await this.loadKbFile();
      kbTextarea.value = this.kbText;
    });
    btnRow.appendChild(loadBtn);

    const saveBtn = smallButton('Save');
    saveBtn.style.marginLeft = '4px';
    saveBtn.addEventListener('click', async () => {
      this.kbText = kbTextarea.value;
      await this.saveKbFile();
    });
    btnRow.appendChild(saveBtn);

    container.appendChild(btnRow);

    return container;
  }

  // ========================================
  // Save methods
  // ========================================

  private async saveActCharter(charter: string): Promise<void> {
    if (!this.activeActId) return;
    await this.kernelRequest('play/acts/update', {
      act_id: this.activeActId,
      charter,
    });
    await this.loadActs();
  }

  private async saveActNotes(notes: string): Promise<void> {
    if (!this.activeActId) return;
    await this.kernelRequest('play/acts/update', {
      act_id: this.activeActId,
      notes,
    });
    await this.loadActs();
  }

  private async saveSceneCharter(charter: string): Promise<void> {
    if (!this.activeActId || !this.selectedSceneId) return;
    await this.kernelRequest('play/scenes/update', {
      act_id: this.activeActId,
      scene_id: this.selectedSceneId,
      charter,
    });
    await this.loadScenes();
  }

  private async saveSceneNotes(notes: string): Promise<void> {
    if (!this.activeActId || !this.selectedSceneId) return;
    await this.kernelRequest('play/scenes/update', {
      act_id: this.activeActId,
      scene_id: this.selectedSceneId,
      notes,
    });
    await this.loadScenes();
  }

  private async saveBeatCharter(charter: string): Promise<void> {
    if (!this.activeActId || !this.selectedSceneId || !this.selectedBeatId) return;
    await this.kernelRequest('play/beats/update', {
      act_id: this.activeActId,
      scene_id: this.selectedSceneId,
      beat_id: this.selectedBeatId,
      charter,
    });
    await this.loadBeats();
  }

  private async saveBeatNotes(notes: string): Promise<void> {
    if (!this.activeActId || !this.selectedSceneId || !this.selectedBeatId) return;
    await this.kernelRequest('play/beats/update', {
      act_id: this.activeActId,
      scene_id: this.selectedSceneId,
      beat_id: this.selectedBeatId,
      notes,
    });
    await this.loadBeats();
  }

  private async toggleTodoCompleted(todoId: string, completed: boolean): Promise<void> {
    if (!this.activeActId || !this.selectedSceneId || !this.selectedBeatId) return;
    await this.kernelRequest('play/todos/update', {
      act_id: this.activeActId,
      scene_id: this.selectedSceneId,
      beat_id: this.selectedBeatId,
      todo_id: todoId,
      completed,
    });
    await this.loadTodos();
  }

  private async loadKbFile(): Promise<void> {
    if (!this.activeActId) return;
    try {
      const res = (await this.kernelRequest('play/kb/read', {
        act_id: this.activeActId,
        scene_id: this.selectedSceneId,
        beat_id: this.selectedBeatId,
        path: this.kbPath,
      })) as { text: string };
      this.kbText = res.text || '';
    } catch (err) {
      console.error('Failed to load KB file:', err);
      this.kbText = '';
    }
  }

  private async saveKbFile(): Promise<void> {
    if (!this.activeActId) return;
    try {
      // Preview
      const preview = (await this.kernelRequest('play/kb/write_preview', {
        act_id: this.activeActId,
        scene_id: this.selectedSceneId,
        beat_id: this.selectedBeatId,
        path: this.kbPath,
        text: this.kbText,
      })) as KbWritePreviewResult;

      // Apply
      await this.kernelRequest('play/kb/write_apply', {
        act_id: this.activeActId,
        scene_id: this.selectedSceneId,
        beat_id: this.selectedBeatId,
        path: this.kbPath,
        text: this.kbText,
        expected_sha256_current: preview.sha256_current,
      });

      await this.loadKbFiles();
      alert('KB file saved!');
    } catch (err) {
      console.error('Failed to save KB file:', err);
      alert('Failed to save KB file');
    }
  }
}
