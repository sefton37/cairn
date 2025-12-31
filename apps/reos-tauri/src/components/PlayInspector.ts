/**
 * Play Inspector component for Acts/Scenes/Beats with integrated KB
 *
 * The knowledge base is fully integrated into The Play structure - KB files
 * belong to Acts, Scenes, or Beats based on the current selection context.
 */

import {
  Component,
  KernelRequestFn,
  KernelError,
  el,
  rowHeader,
  label,
  textInput,
  textArea,
  smallButton
} from './types';

interface ActData {
  act_id: string;
  title: string;
  active: boolean;
  notes: string;
}

interface SceneData {
  scene_id: string;
  title: string;
  intent: string;
  status: string;
  time_horizon: string;
  notes: string;
}

interface BeatData {
  beat_id: string;
  title: string;
  status: string;
  notes: string;
  link: string | null;
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
  private titleEl: HTMLDivElement;
  private bodyEl: HTMLDivElement;

  // State
  private activeActId: string | null = null;
  private actsCache: ActData[] = [];
  private selectedSceneId: string | null = null;
  private scenesCache: SceneData[] = [];
  private selectedBeatId: string | null = null;
  private beatsCache: BeatData[] = [];

  // KB state (integrated into Play)
  private kbSelectedPath = 'kb.md';
  private kbTextDraft = '';
  private kbPreview: KbWritePreviewResult | null = null;

  constructor(private kernelRequest: KernelRequestFn) {
    this.container = el('div');
    this.container.className = 'play-inspector';
    this.container.style.padding = '12px';
    this.container.style.overflow = 'auto';

    this.titleEl = el('div');
    this.titleEl.style.fontWeight = '600';
    this.titleEl.style.marginBottom = '8px';
    this.titleEl.textContent = 'The Play';

    this.bodyEl = el('div');

    this.container.appendChild(this.titleEl);
    this.container.appendChild(this.bodyEl);
  }

  async init(): Promise<void> {
    await this.refreshActs();
    this.renderContent();
  }

  private async refreshActs(): Promise<void> {
    try {
      const res = await this.kernelRequest('play/acts/list', {}) as {
        active_act_id: string | null;
        acts: ActData[];
      };
      this.activeActId = res.active_act_id;
      this.actsCache = res.acts || [];

      // Load scenes for active act
      if (this.activeActId) {
        await this.refreshScenes(this.activeActId);
      }
    } catch (error) {
      console.error('Failed to load acts:', error);
    }
  }

  private async refreshScenes(actId: string): Promise<void> {
    try {
      const res = await this.kernelRequest('play/scenes/list', { act_id: actId }) as {
        scenes: SceneData[];
      };
      this.scenesCache = res.scenes || [];
    } catch (error) {
      console.error('Failed to load scenes:', error);
      this.scenesCache = [];
    }
  }

  private async refreshBeats(actId: string, sceneId: string): Promise<void> {
    try {
      const res = await this.kernelRequest('play/beats/list', {
        act_id: actId,
        scene_id: sceneId
      }) as { beats: BeatData[] };
      this.beatsCache = res.beats || [];
    } catch (error) {
      console.error('Failed to load beats:', error);
      this.beatsCache = [];
    }
  }

  private async refreshKbForSelection(): Promise<void> {
    if (!this.activeActId) return;

    const sceneId = this.selectedSceneId ?? undefined;
    const beatId = this.selectedBeatId ?? undefined;

    try {
      const filesRes = await this.kernelRequest('play/kb/list', {
        act_id: this.activeActId,
        scene_id: sceneId,
        beat_id: beatId
      }) as { files: string[] };

      const files = filesRes.files || [];
      if (files.length > 0 && !files.includes(this.kbSelectedPath)) {
        this.kbSelectedPath = files[0];
      }

      try {
        const readRes = await this.kernelRequest('play/kb/read', {
          act_id: this.activeActId,
          scene_id: sceneId,
          beat_id: beatId,
          path: this.kbSelectedPath
        }) as { path: string; text: string };
        this.kbTextDraft = readRes.text || '';
      } catch {
        // If missing, keep draft as-is (acts as a create)
      }
      this.kbPreview = null;
    } catch (error) {
      console.error('Failed to refresh KB:', error);
    }
  }

  private renderContent(): void {
    this.bodyEl.innerHTML = '';

    if (!this.activeActId) {
      this.renderNoActState();
      return;
    }

    this.renderActEditor();
    this.renderScenesSection();
    this.renderBeatsSection();
    void this.renderKbSection();
  }

  private renderNoActState(): void {
    const empty = el('div');
    empty.textContent = 'Create an Act to begin.';
    empty.style.opacity = '0.8';
    this.bodyEl.appendChild(empty);

    this.bodyEl.appendChild(rowHeader('Act'));
    const actCreateRow = el('div');
    actCreateRow.style.display = 'flex';
    actCreateRow.style.gap = '8px';

    const actNewTitle = textInput('');
    actNewTitle.placeholder = 'New act title';
    const actCreate = smallButton('Create');
    actCreateRow.appendChild(actNewTitle);
    actCreateRow.appendChild(actCreate);
    this.bodyEl.appendChild(actCreateRow);

    actCreate.addEventListener('click', async () => {
      const title = actNewTitle.value.trim();
      if (!title) return;

      try {
        const res = await this.kernelRequest('play/acts/create', { title }) as {
          created_act_id: string;
          acts: ActData[];
        };
        this.activeActId = res.created_act_id;
        this.selectedSceneId = null;
        this.selectedBeatId = null;
        await this.refreshActs();
        if (this.activeActId) await this.refreshScenes(this.activeActId);
        this.renderContent();
      } catch (error) {
        console.error('Failed to create act:', error);
      }
    });
  }

  private renderActEditor(): void {
    const activeAct = this.actsCache.find((a) => a.act_id === this.activeActId) ?? null;

    const status = el('div');
    status.style.fontSize = '12px';
    status.style.opacity = '0.85';
    status.style.marginBottom = '8px';
    status.textContent = this.selectedBeatId
      ? 'Act → Scene → Beat'
      : this.selectedSceneId
        ? 'Act → Scene'
        : 'Act';
    this.bodyEl.appendChild(status);

    // Act editor
    this.bodyEl.appendChild(rowHeader('Act'));

    const actTitle = textInput('');
    const actNotes = textArea('', 70);
    const actSave = smallButton('Save Act');

    this.bodyEl.appendChild(label('Title'));
    this.bodyEl.appendChild(actTitle);
    this.bodyEl.appendChild(label('Notes'));
    this.bodyEl.appendChild(actNotes);
    this.bodyEl.appendChild(actSave);

    if (activeAct) {
      actTitle.value = activeAct.title || '';
      actNotes.value = activeAct.notes || '';
    }

    actSave.addEventListener('click', async () => {
      if (!this.activeActId) return;
      try {
        await this.kernelRequest('play/acts/update', {
          act_id: this.activeActId,
          title: actTitle.value,
          notes: actNotes.value
        });
        await this.refreshActs();
        this.renderContent();
      } catch (error) {
        console.error('Failed to save act:', error);
      }
    });

    // Create new act
    this.bodyEl.appendChild(label('Create new act'));
    const actCreateRow = el('div');
    actCreateRow.style.display = 'flex';
    actCreateRow.style.gap = '8px';

    const actNewTitle = textInput('');
    actNewTitle.placeholder = 'New act title';
    const actCreate = smallButton('Create');
    actCreateRow.appendChild(actNewTitle);
    actCreateRow.appendChild(actCreate);
    this.bodyEl.appendChild(actCreateRow);

    actCreate.addEventListener('click', async () => {
      const title = actNewTitle.value.trim();
      if (!title) return;
      try {
        const res = await this.kernelRequest('play/acts/create', { title }) as {
          created_act_id: string;
          acts: ActData[];
        };
        this.activeActId = res.created_act_id;
        this.selectedSceneId = null;
        this.selectedBeatId = null;
        await this.refreshActs();
        if (this.activeActId) await this.refreshScenes(this.activeActId);
        this.renderContent();
      } catch (error) {
        console.error('Failed to create act:', error);
      }
    });
  }

  private renderScenesSection(): void {
    this.bodyEl.appendChild(rowHeader('Scenes'));

    const sceneCreateTitle = textInput('');
    sceneCreateTitle.placeholder = 'New scene title';
    const sceneCreateBtn = smallButton('Create');
    const sceneCreateRow = el('div');
    sceneCreateRow.style.display = 'flex';
    sceneCreateRow.style.gap = '8px';
    sceneCreateRow.appendChild(sceneCreateTitle);
    sceneCreateRow.appendChild(sceneCreateBtn);
    this.bodyEl.appendChild(sceneCreateRow);

    const scenesList = el('div');
    scenesList.style.display = 'flex';
    scenesList.style.flexDirection = 'column';
    scenesList.style.gap = '6px';
    scenesList.style.marginTop = '8px';
    this.bodyEl.appendChild(scenesList);

    const sceneDetails = el('div');
    this.bodyEl.appendChild(sceneDetails);

    // Render scenes list
    if (this.scenesCache.length === 0) {
      const empty = el('div');
      empty.textContent = '(no scenes yet)';
      empty.style.opacity = '0.7';
      scenesList.appendChild(empty);
    } else {
      for (const s of this.scenesCache) {
        const btn = smallButton(
          this.selectedSceneId === s.scene_id ? `• ${s.title}` : s.title
        );
        btn.style.textAlign = 'left';
        btn.addEventListener('click', async () => {
          this.selectedSceneId = s.scene_id;
          this.selectedBeatId = null;
          if (this.activeActId) {
            await this.refreshBeats(this.activeActId, s.scene_id);
            await this.refreshKbForSelection();
          }
          this.renderContent();
        });
        scenesList.appendChild(btn);
      }
    }

    // Render scene details if one is selected
    if (this.selectedSceneId) {
      const s = this.scenesCache.find((x) => x.scene_id === this.selectedSceneId);
      if (s) {
        sceneDetails.appendChild(rowHeader('Scene Details'));
        const tTitle = textInput(s.title || '');
        const tIntent = textInput(s.intent || '');
        const tStatus = textInput(s.status || '');
        const tH = textInput(s.time_horizon || '');
        const tNotes = textArea(s.notes || '', 80);
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

        save.addEventListener('click', async () => {
          if (!this.activeActId || !this.selectedSceneId) return;
          try {
            await this.kernelRequest('play/scenes/update', {
              act_id: this.activeActId,
              scene_id: this.selectedSceneId,
              title: tTitle.value,
              intent: tIntent.value,
              status: tStatus.value,
              time_horizon: tH.value,
              notes: tNotes.value
            });
            if (this.activeActId) await this.refreshScenes(this.activeActId);
            this.renderContent();
          } catch (error) {
            console.error('Failed to save scene:', error);
          }
        });
      }
    }

    // Create scene handler
    sceneCreateBtn.addEventListener('click', async () => {
      const title = sceneCreateTitle.value.trim();
      if (!title || !this.activeActId) return;
      try {
        await this.kernelRequest('play/scenes/create', {
          act_id: this.activeActId,
          title
        });
        await this.refreshScenes(this.activeActId);
        this.renderContent();
      } catch (error) {
        console.error('Failed to create scene:', error);
      }
    });
  }

  private renderBeatsSection(): void {
    if (!this.activeActId || !this.selectedSceneId) return;

    const beatsDetails = el('div');
    this.bodyEl.appendChild(beatsDetails);

    beatsDetails.appendChild(rowHeader('Beats'));

    const createRow = el('div');
    createRow.style.display = 'flex';
    createRow.style.gap = '8px';
    const newTitle = textInput('');
    newTitle.placeholder = 'New beat title';
    const newStatus = textInput('');
    newStatus.placeholder = 'status';
    const createBtn = smallButton('Create');
    createRow.appendChild(newTitle);
    createRow.appendChild(newStatus);
    createRow.appendChild(createBtn);
    beatsDetails.appendChild(createRow);

    const list = el('div');
    list.style.display = 'flex';
    list.style.flexDirection = 'column';
    list.style.gap = '6px';
    list.style.marginTop = '8px';
    beatsDetails.appendChild(list);

    const detail = el('div');
    beatsDetails.appendChild(detail);

    // Render beats list
    if (this.beatsCache.length === 0) {
      const empty = el('div');
      empty.textContent = '(no beats yet)';
      empty.style.opacity = '0.7';
      list.appendChild(empty);
    } else {
      for (const b of this.beatsCache) {
        const btn = smallButton(
          this.selectedBeatId === b.beat_id ? `• ${b.title}` : b.title
        );
        btn.style.textAlign = 'left';
        btn.addEventListener('click', async () => {
          this.selectedBeatId = b.beat_id;
          await this.refreshKbForSelection();
          this.renderContent();
        });
        list.appendChild(btn);
      }
    }

    // Render beat details if one is selected
    if (this.selectedBeatId) {
      const b = this.beatsCache.find((x) => x.beat_id === this.selectedBeatId);
      if (b) {
        detail.appendChild(rowHeader('Beat Details'));
        const tTitle = textInput(b.title || '');
        const tStatus = textInput(b.status || '');
        const tLink = textInput(b.link || '');
        const tNotes = textArea(b.notes || '', 80);
        const save = smallButton('Save Beat');

        detail.appendChild(label('Title'));
        detail.appendChild(tTitle);
        detail.appendChild(label('Status'));
        detail.appendChild(tStatus);
        detail.appendChild(label('Link'));
        detail.appendChild(tLink);
        detail.appendChild(label('Notes'));
        detail.appendChild(tNotes);
        detail.appendChild(save);

        save.addEventListener('click', async () => {
          if (!this.activeActId || !this.selectedSceneId || !this.selectedBeatId) return;
          try {
            await this.kernelRequest('play/beats/update', {
              act_id: this.activeActId,
              scene_id: this.selectedSceneId,
              beat_id: this.selectedBeatId,
              title: tTitle.value,
              status: tStatus.value,
              link: tLink.value || null,
              notes: tNotes.value
            });
            await this.refreshBeats(this.activeActId, this.selectedSceneId);
            this.renderContent();
          } catch (error) {
            console.error('Failed to save beat:', error);
          }
        });
      }
    }

    // Create beat handler
    createBtn.addEventListener('click', async () => {
      const title = newTitle.value.trim();
      if (!title || !this.activeActId || !this.selectedSceneId) return;
      try {
        await this.kernelRequest('play/beats/create', {
          act_id: this.activeActId,
          scene_id: this.selectedSceneId,
          title,
          status: newStatus.value
        });
        await this.refreshBeats(this.activeActId, this.selectedSceneId);
        this.renderContent();
      } catch (error) {
        console.error('Failed to create beat:', error);
      }
    });
  }

  private async renderKbSection(): Promise<void> {
    const kbSection = el('div');
    this.bodyEl.appendChild(kbSection);

    kbSection.appendChild(rowHeader('Mini Knowledgebase'));

    const who = el('div');
    who.style.fontSize = '12px';
    who.style.opacity = '0.8';
    who.style.marginBottom = '6px';
    who.textContent = this.selectedBeatId
      ? 'Beat KB'
      : this.selectedSceneId
        ? 'Scene KB'
        : 'Act KB';
    kbSection.appendChild(who);

    const fileRow = el('div');
    fileRow.style.display = 'flex';
    fileRow.style.gap = '8px';
    const pathInput = textInput(this.kbSelectedPath);
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

    const editor = textArea(this.kbTextDraft, 180);
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
    diffPre.textContent = this.kbPreview ? this.kbPreview.diff : '';
    kbSection.appendChild(diffPre);

    const errorLine = el('div');
    errorLine.style.fontSize = '12px';
    errorLine.style.marginTop = '6px';
    errorLine.style.opacity = '0.85';
    kbSection.appendChild(errorLine);

    // Event handlers
    editor.addEventListener('input', () => {
      this.kbTextDraft = editor.value;
    });

    pathInput.addEventListener('input', () => {
      this.kbSelectedPath = pathInput.value;
    });

    loadBtn.addEventListener('click', async () => {
      errorLine.textContent = '';
      this.kbSelectedPath = pathInput.value || 'kb.md';
      await this.refreshKbForSelection();
      this.renderContent();
    });

    previewBtn.addEventListener('click', async () => {
      errorLine.textContent = '';
      if (!this.activeActId) return;
      try {
        const res = await this.kernelRequest('play/kb/write_preview', {
          act_id: this.activeActId,
          scene_id: this.selectedSceneId,
          beat_id: this.selectedBeatId,
          path: this.kbSelectedPath,
          text: editor.value
        }) as KbWritePreviewResult;
        this.kbPreview = res;
        diffPre.textContent = res.diff || '';
      } catch (e) {
        errorLine.textContent = `Preview error: ${String(e)}`;
      }
    });

    applyBtn.addEventListener('click', async () => {
      errorLine.textContent = '';
      if (!this.activeActId) return;
      if (!this.kbPreview) {
        errorLine.textContent = 'Preview first.';
        return;
      }
      try {
        await this.kernelRequest('play/kb/write_apply', {
          act_id: this.activeActId,
          scene_id: this.selectedSceneId,
          beat_id: this.selectedBeatId,
          path: this.kbSelectedPath,
          text: editor.value,
          expected_sha256_current: this.kbPreview.expected_sha256_current
        });
        await this.refreshKbForSelection();
        this.renderContent();
      } catch (e) {
        if (e instanceof KernelError && e.code === -32009) {
          errorLine.textContent = 'Conflict: file changed since preview. Re-preview to continue.';
        } else {
          errorLine.textContent = `Apply error: ${String(e)}`;
        }
      }
    });

    // Load and render file pills
    try {
      if (!this.activeActId) return;
      const filesRes = await this.kernelRequest('play/kb/list', {
        act_id: this.activeActId,
        scene_id: this.selectedSceneId,
        beat_id: this.selectedBeatId
      }) as { files: string[] };
      const files = filesRes.files || [];
      listWrap.innerHTML = '';
      for (const f of files) {
        const pill = smallButton(f);
        pill.addEventListener('click', async () => {
          this.kbSelectedPath = f;
          await this.refreshKbForSelection();
          this.renderContent();
        });
        listWrap.appendChild(pill);
      }
    } catch {
      // Ignore errors when loading file list
    }
  }

  render(): HTMLElement {
    return this.container;
  }

  destroy(): void {
    // Cleanup if needed
  }
}
