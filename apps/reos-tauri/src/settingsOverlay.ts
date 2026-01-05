/**
 * Settings Overlay - Configuration panel for ReOS
 *
 * Tabs:
 * - LLM Provider: Ollama connection, model selection, downloads
 * - Agent Persona: Prompts review, parameters, customization
 */

import { kernelRequest } from './kernel';
import { el } from './dom';

type SettingsTab = 'llm' | 'persona';

interface OllamaStatus {
  url: string;
  model: string;
  reachable: boolean;
  model_count: number | null;
  error: string | null;
  available_models: string[];
  gpu_enabled: boolean;
  gpu_available: boolean;
  gpu_name: string | null;
  gpu_vram_gb: number | null;
  num_ctx: number | null;
  hardware: {
    ram_gb: number;
    gpu_available: boolean;
    gpu_name: string | null;
    gpu_vram_gb: number | null;
    gpu_type: string | null;
    recommended_max_params: string;
  };
}

interface ModelInfo {
  model: string;
  parameter_size: string | null;
  family: string;
  families: string[];
  quantization: string;
  context_length: number | null;
  format: string;
  capabilities: {
    vision: boolean;
    tools: boolean;
    thinking: boolean;
    embedding: boolean;
  };
  error?: string;
}

interface PersonaData {
  id: string;
  name: string;
  system_prompt: string;
  default_context: string;
  temperature: number;
  top_p: number;
  tool_call_limit: number;
}

interface SettingsOverlay {
  element: HTMLElement;
  show: () => void;
  hide: () => void;
}

interface PullStatus {
  model: string;
  status: string;
  progress: number;
  total: number;
  completed: number;
  error: string | null;
  done: boolean;
}

interface PullStartResult {
  pull_id: string;
  model: string;
}

/**
 * Download a model with progress tracking.
 * @param modelName Model to download
 * @param onProgress Called with progress updates
 * @returns Final status
 */
async function downloadModelWithProgress(
  modelName: string,
  onProgress: (status: PullStatus) => void
): Promise<PullStatus> {
  // Start the pull
  const startResult = await kernelRequest('ollama/pull_start', { model: modelName }) as PullStartResult;
  const pullId = startResult.pull_id;

  // Poll for status
  return new Promise((resolve, reject) => {
    const poll = async () => {
      try {
        const status = await kernelRequest('ollama/pull_status', { pull_id: pullId }) as PullStatus;
        onProgress(status);

        if (status.done) {
          if (status.error) {
            reject(new Error(status.error));
          } else {
            resolve(status);
          }
        } else {
          // Poll again in 500ms
          setTimeout(poll, 500);
        }
      } catch (e) {
        reject(e);
      }
    };
    poll();
  });
}

/**
 * Format bytes to human readable string
 */
function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

export function createSettingsOverlay(onClose?: () => void): SettingsOverlay {
  // State
  let activeTab: SettingsTab = 'llm';
  let ollamaStatus: OllamaStatus | null = null;
  let selectedModelInfo: ModelInfo | null = null;
  let personas: PersonaData[] = [];
  let activePersonaId: string | null = null;
  let customContext: string = '';

  // Create overlay container
  const overlay = el('div');
  overlay.className = 'settings-overlay';
  overlay.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.8);
    display: none;
    z-index: 1000;
    justify-content: center;
    align-items: center;
  `;

  // Modal container
  const modal = el('div');
  modal.className = 'settings-modal';
  modal.style.cssText = `
    width: 800px;
    max-width: 90vw;
    height: 600px;
    max-height: 85vh;
    background: #1e1e1e;
    border-radius: 12px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  `;

  // Header
  const header = el('div');
  header.style.cssText = `
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;
    border-bottom: 1px solid #333;
  `;

  const title = el('div');
  title.textContent = '⚙️ Settings';
  title.style.cssText = 'font-size: 18px; font-weight: 600; color: #fff;';

  const closeBtn = el('button');
  closeBtn.textContent = '✕';
  closeBtn.style.cssText = `
    background: none;
    border: none;
    color: rgba(255,255,255,0.6);
    font-size: 20px;
    cursor: pointer;
    padding: 4px 8px;
  `;
  closeBtn.addEventListener('click', hide);

  header.appendChild(title);
  header.appendChild(closeBtn);

  // Tabs
  const tabsContainer = el('div');
  tabsContainer.style.cssText = `
    display: flex;
    border-bottom: 1px solid #333;
    background: rgba(0,0,0,0.2);
  `;

  const createTab = (id: SettingsTab, label: string, icon: string) => {
    const tab = el('button');
    tab.className = `settings-tab ${id}`;
    tab.textContent = `${icon} ${label}`;
    tab.style.cssText = `
      padding: 12px 24px;
      background: none;
      border: none;
      color: rgba(255,255,255,0.6);
      cursor: pointer;
      font-size: 13px;
      border-bottom: 2px solid transparent;
      transition: all 0.2s;
    `;
    tab.addEventListener('click', () => {
      activeTab = id;
      render();
    });
    return tab;
  };

  const llmTab = createTab('llm', 'LLM Provider', '🤖');
  const personaTab = createTab('persona', 'Agent Persona', '🎭');

  tabsContainer.appendChild(llmTab);
  tabsContainer.appendChild(personaTab);

  // Content area
  const content = el('div');
  content.className = 'settings-content';
  content.style.cssText = `
    flex: 1;
    overflow: auto;
    padding: 20px;
  `;

  modal.appendChild(header);
  modal.appendChild(tabsContainer);
  modal.appendChild(content);
  overlay.appendChild(modal);

  // Close on backdrop click
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) hide();
  });

  // Close on Escape
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && overlay.style.display === 'flex') hide();
  });

  function show() {
    overlay.style.display = 'flex';
    void loadData();
  }

  function hide() {
    overlay.style.display = 'none';
    onClose?.();
  }

  async function loadData() {
    try {
      // Load Ollama status
      ollamaStatus = await kernelRequest('ollama/status', {}) as OllamaStatus;

      // Load model info for selected model
      if (ollamaStatus.model && ollamaStatus.reachable) {
        try {
          selectedModelInfo = await kernelRequest('ollama/model_info', { model: ollamaStatus.model }) as ModelInfo;
        } catch {
          selectedModelInfo = null;
        }
      }
    } catch (e) {
      // Set error state so UI can show what went wrong
      ollamaStatus = {
        url: 'http://127.0.0.1:11434',
        model: '',
        reachable: false,
        model_count: null,
        error: e instanceof Error ? e.message : 'Failed to fetch status',
        available_models: [],
        gpu_enabled: true,
        gpu_available: false,
        gpu_name: null,
        gpu_vram_gb: null,
        num_ctx: null,
        hardware: {
          ram_gb: 0,
          gpu_available: false,
          gpu_name: null,
          gpu_vram_gb: null,
          gpu_type: null,
          recommended_max_params: '3b',
        },
      };
    }

    try {
      // Load personas
      const personasResult = await kernelRequest('personas/list', {}) as {
        personas: PersonaData[];
        active_persona_id: string | null;
      };
      personas = personasResult.personas || [];
      activePersonaId = personasResult.active_persona_id;
    } catch {
      // Personas not loaded, continue with empty list
    }

    render();
  }

  function render() {
    // Update tab styles
    llmTab.style.color = activeTab === 'llm' ? '#fff' : 'rgba(255,255,255,0.6)';
    llmTab.style.borderBottomColor = activeTab === 'llm' ? '#3b82f6' : 'transparent';
    personaTab.style.color = activeTab === 'persona' ? '#fff' : 'rgba(255,255,255,0.6)';
    personaTab.style.borderBottomColor = activeTab === 'persona' ? '#3b82f6' : 'transparent';

    content.innerHTML = '';

    if (activeTab === 'llm') {
      renderLLMTab();
    } else {
      renderPersonaTab();
    }
  }

  function renderLLMTab() {
    // Connection Status Section
    const statusSection = createSection('Connection Status');

    const statusBox = el('div');
    statusBox.style.cssText = `
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 12px;
      background: rgba(0,0,0,0.2);
      border-radius: 8px;
      margin-bottom: 16px;
    `;

    const statusIndicator = el('div');
    statusIndicator.style.cssText = `
      width: 12px;
      height: 12px;
      border-radius: 50%;
      background: ${ollamaStatus?.reachable ? '#22c55e' : '#ef4444'};
    `;

    const statusText = el('div');
    statusText.innerHTML = ollamaStatus?.reachable
      ? `<strong style="color: #22c55e;">Connected</strong> <span style="color: rgba(255,255,255,0.7);">- ${ollamaStatus.model_count} models available</span>`
      : `<strong style="color: #ef4444;">Not Connected</strong> <span style="color: rgba(255,255,255,0.7);">- ${ollamaStatus?.error || 'Unknown error'}</span>`;
    statusText.style.cssText = 'flex: 1;';

    const testBtn = el('button');
    testBtn.textContent = 'Test Connection';
    testBtn.style.cssText = `
      padding: 6px 12px;
      background: rgba(59, 130, 246, 0.2);
      border: 1px solid rgba(59, 130, 246, 0.4);
      border-radius: 4px;
      color: #3b82f6;
      cursor: pointer;
      font-size: 12px;
    `;
    testBtn.addEventListener('click', async () => {
      testBtn.textContent = 'Testing...';
      testBtn.style.opacity = '0.6';
      try {
        const result = await kernelRequest('ollama/test_connection', {}) as { reachable: boolean; error?: string };
        if (result.reachable) {
          testBtn.textContent = '✓ Connected!';
          testBtn.style.color = '#22c55e';
          testBtn.style.borderColor = '#22c55e';
        } else {
          testBtn.textContent = '✗ Failed';
          testBtn.style.color = '#ef4444';
          testBtn.style.borderColor = '#ef4444';
        }
        await loadData();
      } catch {
        testBtn.textContent = '✗ Error';
        testBtn.style.color = '#ef4444';
      }
      testBtn.style.opacity = '1';
      setTimeout(() => {
        testBtn.textContent = 'Test Connection';
        testBtn.style.color = '#3b82f6';
        testBtn.style.borderColor = 'rgba(59, 130, 246, 0.4)';
      }, 2000);
    });

    statusBox.appendChild(statusIndicator);
    statusBox.appendChild(statusText);
    statusBox.appendChild(testBtn);
    statusSection.appendChild(statusBox);


    // URL Setting
    const urlRow = createSettingRow('Ollama URL', 'The address where Ollama is running');
    const urlInput = el('input') as HTMLInputElement;
    urlInput.type = 'text';
    urlInput.value = ollamaStatus?.url || 'http://localhost:11434';
    urlInput.style.cssText = `
      flex: 1;
      padding: 8px 12px;
      background: rgba(0,0,0,0.3);
      border: 1px solid #444;
      border-radius: 4px;
      color: #fff;
      font-family: monospace;
      font-size: 13px;
    `;

    const urlSaveBtn = el('button');
    urlSaveBtn.textContent = 'Save';
    urlSaveBtn.style.cssText = `
      padding: 8px 16px;
      background: #3b82f6;
      border: none;
      border-radius: 4px;
      color: #fff;
      cursor: pointer;
      font-size: 13px;
    `;
    urlSaveBtn.addEventListener('click', async () => {
      try {
        await kernelRequest('ollama/set_url', { url: urlInput.value });
        await loadData();
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        alert('Failed to save URL: ' + msg);
      }
    });

    urlRow.appendChild(urlInput);
    urlRow.appendChild(urlSaveBtn);
    statusSection.appendChild(urlRow);

    content.appendChild(statusSection);

    // Hardware & Inference Section
    const hardwareSection = createSection('Hardware & Inference');

    // Hardware info box
    const hw = ollamaStatus?.hardware;
    const hardwareBox = el('div');
    hardwareBox.style.cssText = `
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 12px;
      margin-bottom: 16px;
    `;

    // RAM info
    const ramBox = el('div');
    ramBox.style.cssText = `
      padding: 12px;
      background: rgba(0,0,0,0.2);
      border-radius: 8px;
    `;
    ramBox.innerHTML = `
      <div style="font-size: 11px; color: rgba(255,255,255,0.5); margin-bottom: 4px;">System RAM</div>
      <div style="font-size: 16px; font-weight: 500; color: #fff;">${hw?.ram_gb || 0} GB</div>
    `;
    hardwareBox.appendChild(ramBox);

    // GPU info
    const gpuBox = el('div');
    gpuBox.style.cssText = `
      padding: 12px;
      background: rgba(0,0,0,0.2);
      border-radius: 8px;
    `;
    if (hw?.gpu_available) {
      gpuBox.innerHTML = `
        <div style="font-size: 11px; color: rgba(255,255,255,0.5); margin-bottom: 4px;">GPU (${hw.gpu_type?.toUpperCase() || 'GPU'})</div>
        <div style="font-size: 14px; font-weight: 500; color: #22c55e;">${hw.gpu_name || 'Available'}</div>
        <div style="font-size: 12px; color: rgba(255,255,255,0.6);">${hw.gpu_vram_gb || '?'} GB VRAM</div>
      `;
    } else {
      gpuBox.innerHTML = `
        <div style="font-size: 11px; color: rgba(255,255,255,0.5); margin-bottom: 4px;">GPU</div>
        <div style="font-size: 14px; font-weight: 500; color: #f59e0b;">Not Detected</div>
        <div style="font-size: 11px; color: rgba(255,255,255,0.5);">CPU inference only</div>
      `;
    }
    hardwareBox.appendChild(gpuBox);
    hardwareSection.appendChild(hardwareBox);

    // Recommended models note
    const recommendedNote = el('div');
    recommendedNote.style.cssText = `
      padding: 10px 12px;
      background: rgba(59, 130, 246, 0.1);
      border: 1px solid rgba(59, 130, 246, 0.3);
      border-radius: 6px;
      font-size: 12px;
      color: rgba(255,255,255,0.8);
      margin-bottom: 16px;
    `;
    const maxParams = hw?.recommended_max_params?.toUpperCase() || '3B';
    const gpuVram = hw?.gpu_vram_gb || 0;
    const sysRam = hw?.ram_gb || 0;

    let speedNote = '';
    if (hw?.gpu_available && sysRam > gpuVram * 2) {
      speedNote = `<div style="margin-top: 6px; font-size: 11px; color: rgba(255,255,255,0.6);">
        ⚡ Models ≤${gpuVram}GB run fully on GPU (fastest). Larger models use CPU offloading (slower but possible up to ${sysRam}GB).
      </div>`;
    }

    recommendedNote.innerHTML = `
      💡 <strong>Recommended:</strong> Based on your ${sysRam}GB RAM${hw?.gpu_available ? ` + ${gpuVram}GB VRAM` : ''}, models up to <strong>${maxParams} parameters</strong> should run.
      ${speedNote}
    `;
    hardwareSection.appendChild(recommendedNote);

    // GPU toggle (only show if GPU is available)
    if (hw?.gpu_available) {
      const gpuToggleRow = el('div');
      gpuToggleRow.style.cssText = `
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 12px;
        background: rgba(0,0,0,0.2);
        border-radius: 8px;
        margin-bottom: 12px;
      `;

      const gpuLabel = el('div');
      gpuLabel.innerHTML = `
        <div style="font-size: 13px; font-weight: 500; color: #fff;">GPU Acceleration</div>
        <div style="font-size: 11px; color: rgba(255,255,255,0.5);">Use GPU for faster inference (recommended)</div>
      `;

      const gpuToggle = el('button');
      const gpuEnabled = ollamaStatus?.gpu_enabled !== false;
      gpuToggle.textContent = gpuEnabled ? 'Enabled' : 'Disabled';
      gpuToggle.style.cssText = `
        padding: 6px 16px;
        background: ${gpuEnabled ? 'rgba(34, 197, 94, 0.2)' : 'rgba(255,255,255,0.1)'};
        border: 1px solid ${gpuEnabled ? '#22c55e' : '#444'};
        border-radius: 4px;
        color: ${gpuEnabled ? '#22c55e' : 'rgba(255,255,255,0.6)'};
        cursor: pointer;
        font-size: 12px;
        min-width: 80px;
      `;
      gpuToggle.addEventListener('click', async () => {
        const newValue = !gpuEnabled;
        try {
          await kernelRequest('ollama/set_gpu', { enabled: newValue });
          await loadData();
        } catch (e) {
          alert('Failed to update GPU setting');
        }
      });

      gpuToggleRow.appendChild(gpuLabel);
      gpuToggleRow.appendChild(gpuToggle);
      hardwareSection.appendChild(gpuToggleRow);
    } else {
      // Show warning that GPU is not available
      const gpuWarning = el('div');
      gpuWarning.style.cssText = `
        padding: 10px 12px;
        background: rgba(245, 158, 11, 0.1);
        border: 1px solid rgba(245, 158, 11, 0.3);
        border-radius: 6px;
        font-size: 12px;
        color: #f59e0b;
        margin-bottom: 12px;
      `;
      gpuWarning.innerHTML = `
        ⚠️ <strong>GPU not available for Ollama.</strong> Inference will use CPU only, which is slower.
        For GPU support, install NVIDIA CUDA drivers or AMD ROCm.
      `;
      hardwareSection.appendChild(gpuWarning);
    }

    // Context length setting
    const ctxRow = el('div');
    ctxRow.style.cssText = `
      padding: 12px;
      background: rgba(0,0,0,0.2);
      border-radius: 8px;
    `;

    const currentCtx = ollamaStatus?.num_ctx || selectedModelInfo?.context_length || 4096;
    const maxCtx = selectedModelInfo?.context_length || 8192;

    ctxRow.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
        <div>
          <div style="font-size: 13px; font-weight: 500; color: #fff;">Context Length</div>
          <div style="font-size: 11px; color: rgba(255,255,255,0.5);">Max tokens the model can remember (affects memory usage)</div>
        </div>
        <div style="font-family: monospace; font-size: 14px; color: #3b82f6;" id="ctx-value">${currentCtx.toLocaleString()}</div>
      </div>
    `;

    const ctxSlider = el('input') as HTMLInputElement;
    ctxSlider.type = 'range';
    ctxSlider.min = '512';
    ctxSlider.max = String(Math.min(maxCtx * 2, 131072));
    ctxSlider.step = '512';
    ctxSlider.value = String(currentCtx);
    ctxSlider.style.cssText = `
      width: 100%;
      accent-color: #3b82f6;
    `;

    ctxSlider.addEventListener('input', () => {
      const valueEl = ctxRow.querySelector('#ctx-value');
      if (valueEl) valueEl.textContent = parseInt(ctxSlider.value).toLocaleString();
    });

    ctxSlider.addEventListener('change', async () => {
      try {
        await kernelRequest('ollama/set_context', { num_ctx: parseInt(ctxSlider.value) });
      } catch (e) {
        alert('Failed to update context length');
      }
    });

    ctxRow.appendChild(ctxSlider);

    const ctxHint = el('div');
    ctxHint.style.cssText = 'font-size: 10px; color: rgba(255,255,255,0.4); margin-top: 6px;';
    ctxHint.textContent = `Model default: ${maxCtx.toLocaleString()} tokens. Higher values use more memory.`;
    ctxRow.appendChild(ctxHint);

    hardwareSection.appendChild(ctxRow);
    content.appendChild(hardwareSection);

    // Model Selection Section
    const modelSection = createSection('Model Selection');

    // Current model box with more details
    const currentModelBox = el('div');
    currentModelBox.style.cssText = `
      padding: 12px;
      background: rgba(0,0,0,0.2);
      border-radius: 8px;
      margin-bottom: 16px;
    `;

    const modelName = ollamaStatus?.model || 'Not set';
    const paramSize = selectedModelInfo?.parameter_size || '';
    const ctxLen = selectedModelInfo?.context_length;
    const quantization = selectedModelInfo?.quantization || '';
    const caps = selectedModelInfo?.capabilities;

    currentModelBox.innerHTML = `
      <div style="margin-bottom: 4px; color: rgba(255,255,255,0.7); font-size: 12px;">Current Model</div>
      <div style="font-size: 16px; font-weight: 500; color: #fff; margin-bottom: 8px;">${modelName}</div>
      ${paramSize || ctxLen || quantization ? `
        <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px;">
          ${paramSize ? `<div style="font-size: 11px; padding: 3px 8px; background: rgba(59,130,246,0.2); border-radius: 4px; color: #60a5fa;">${paramSize} params</div>` : ''}
          ${ctxLen ? `<div style="font-size: 11px; padding: 3px 8px; background: rgba(34,197,94,0.2); border-radius: 4px; color: #4ade80;">${ctxLen.toLocaleString()} ctx</div>` : ''}
          ${quantization ? `<div style="font-size: 11px; padding: 3px 8px; background: rgba(168,85,247,0.2); border-radius: 4px; color: #c084fc;">${quantization}</div>` : ''}
        </div>
      ` : ''}
      ${caps ? `
        <div style="display: flex; gap: 8px; flex-wrap: wrap;">
          <div style="font-size: 10px; color: rgba(255,255,255,0.5);">Capabilities:</div>
          ${caps.tools ? `<div style="font-size: 10px; padding: 2px 6px; background: rgba(34,197,94,0.2); border-radius: 3px; color: #4ade80;">🔧 Tools</div>` : `<div style="font-size: 10px; padding: 2px 6px; background: rgba(255,255,255,0.05); border-radius: 3px; color: rgba(255,255,255,0.3);">🔧 Tools</div>`}
          ${caps.vision ? `<div style="font-size: 10px; padding: 2px 6px; background: rgba(34,197,94,0.2); border-radius: 3px; color: #4ade80;">👁️ Vision</div>` : `<div style="font-size: 10px; padding: 2px 6px; background: rgba(255,255,255,0.05); border-radius: 3px; color: rgba(255,255,255,0.3);">👁️ Vision</div>`}
          ${caps.thinking ? `<div style="font-size: 10px; padding: 2px 6px; background: rgba(34,197,94,0.2); border-radius: 3px; color: #4ade80;">🧠 Thinking</div>` : `<div style="font-size: 10px; padding: 2px 6px; background: rgba(255,255,255,0.05); border-radius: 3px; color: rgba(255,255,255,0.3);">🧠 Thinking</div>`}
          ${caps.embedding ? `<div style="font-size: 10px; padding: 2px 6px; background: rgba(34,197,94,0.2); border-radius: 3px; color: #4ade80;">📊 Embed</div>` : ''}
        </div>
      ` : ''}
    `;
    modelSection.appendChild(currentModelBox);

    // Available models
    if (ollamaStatus?.available_models && ollamaStatus.available_models.length > 0) {
      const modelsLabel = el('div');
      modelsLabel.textContent = 'Available Models';
      modelsLabel.style.cssText = 'margin-bottom: 8px; font-size: 13px; color: rgba(255,255,255,0.7);';
      modelSection.appendChild(modelsLabel);

      const modelsList = el('div');
      modelsList.style.cssText = `
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-bottom: 16px;
      `;

      for (const model of ollamaStatus.available_models) {
        const modelBtn = el('button');
        modelBtn.textContent = model;
        const isActive = model === ollamaStatus.model;
        modelBtn.style.cssText = `
          padding: 6px 12px;
          background: ${isActive ? 'rgba(34, 197, 94, 0.2)' : 'rgba(255,255,255,0.05)'};
          border: 1px solid ${isActive ? '#22c55e' : '#444'};
          border-radius: 4px;
          color: ${isActive ? '#22c55e' : 'rgba(255,255,255,0.8)'};
          cursor: pointer;
          font-size: 12px;
        `;
        modelBtn.addEventListener('click', async () => {
          try {
            await kernelRequest('ollama/set_model', { model });
            await loadData();
          } catch (e: unknown) {
            const msg = e instanceof Error ? e.message : String(e);
            alert('Failed to set model: ' + msg);
          }
        });
        modelsList.appendChild(modelBtn);
      }
      modelSection.appendChild(modelsList);
    }

    // Popular Models Section
    const popularLabel = el('div');
    popularLabel.textContent = 'Recommended Models';
    popularLabel.style.cssText = 'margin-bottom: 8px; font-size: 13px; color: rgba(255,255,255,0.7);';
    modelSection.appendChild(popularLabel);

    // Models with full specs - sorted by size for hardware recommendations
    // caps: { tools?, vision?, thinking? }
    const allPopularModels = [
      { name: 'phi3:mini', params: '3.8B', desc: 'Microsoft\'s compact model', size: '2.3GB', ramNeeded: 4, ctx: 4096, caps: {} },
      { name: 'llama3.2:3b', params: '3B', desc: 'Meta\'s efficient small model', size: '2.0GB', ramNeeded: 4, ctx: 8192, caps: { tools: true } },
      { name: 'gemma2:2b', params: '2B', desc: 'Google\'s tiny powerhouse', size: '1.6GB', ramNeeded: 3, ctx: 8192, caps: {} },
      { name: 'qwen2.5:3b', params: '3B', desc: 'Alibaba\'s multilingual', size: '2.0GB', ramNeeded: 4, ctx: 32768, caps: { tools: true } },
      { name: 'llava:7b', params: '7B', desc: 'Vision-language model', size: '4.7GB', ramNeeded: 8, ctx: 4096, caps: { vision: true } },
      { name: 'mistral:7b', params: '7B', desc: 'Fast & efficient', size: '4.1GB', ramNeeded: 8, ctx: 32768, caps: { tools: true } },
      { name: 'llama3.2:latest', params: '8B', desc: 'Meta\'s latest balanced', size: '4.7GB', ramNeeded: 8, ctx: 8192, caps: { tools: true } },
      { name: 'llama3.1:8b', params: '8B', desc: 'High quality general', size: '4.7GB', ramNeeded: 8, ctx: 8192, caps: { tools: true } },
      { name: 'qwq:latest', params: '32B', desc: 'Alibaba reasoning model', size: '20GB', ramNeeded: 24, ctx: 32768, caps: { thinking: true } },
      { name: 'deepseek-r1:7b', params: '7B', desc: 'DeepSeek reasoning', size: '4.7GB', ramNeeded: 8, ctx: 16384, caps: { thinking: true } },
      { name: 'deepseek-r1:14b', params: '14B', desc: 'DeepSeek reasoning', size: '9GB', ramNeeded: 16, ctx: 16384, caps: { thinking: true } },
      { name: 'codellama:7b', params: '7B', desc: 'Optimized for coding', size: '3.8GB', ramNeeded: 8, ctx: 16384, caps: {} },
      { name: 'deepseek-coder:6.7b', params: '6.7B', desc: 'Code specialist', size: '3.8GB', ramNeeded: 8, ctx: 16384, caps: {} },
      { name: 'gemma2:9b', params: '9B', desc: 'Google\'s capable model', size: '5.4GB', ramNeeded: 10, ctx: 8192, caps: {} },
      { name: 'llava:13b', params: '13B', desc: 'Larger vision model', size: '8GB', ramNeeded: 16, ctx: 4096, caps: { vision: true } },
      { name: 'qwen2.5:14b', params: '14B', desc: 'Strong multilingual', size: '9GB', ramNeeded: 16, ctx: 32768, caps: { tools: true } },
      { name: 'deepseek-r1:32b', params: '32B', desc: 'DeepSeek reasoning', size: '20GB', ramNeeded: 24, ctx: 16384, caps: { thinking: true } },
      { name: 'codellama:34b', params: '34B', desc: 'Advanced coding', size: '19GB', ramNeeded: 24, ctx: 16384, caps: {} },
      { name: 'llava:34b', params: '34B', desc: 'Large vision model', size: '20GB', ramNeeded: 24, ctx: 4096, caps: { vision: true } },
      { name: 'mixtral:8x7b', params: '47B', desc: 'MoE, fast for size', size: '26GB', ramNeeded: 32, ctx: 32768, caps: { tools: true } },
      { name: 'deepseek-r1:70b', params: '70B', desc: 'DeepSeek reasoning', size: '43GB', ramNeeded: 48, ctx: 16384, caps: { thinking: true } },
      { name: 'llama3.1:70b', params: '70B', desc: 'Meta\'s flagship', size: '40GB', ramNeeded: 48, ctx: 8192, caps: { tools: true } },
      { name: 'qwen2.5:72b', params: '72B', desc: 'Top-tier multilingual', size: '42GB', ramNeeded: 48, ctx: 32768, caps: { tools: true } },
      { name: 'deepseek-coder:33b', params: '33B', desc: 'Expert coder', size: '19GB', ramNeeded: 24, ctx: 16384, caps: {} },
      { name: 'llama3.1:405b', params: '405B', desc: 'Largest open model', size: '230GB', ramNeeded: 256, ctx: 8192, caps: { tools: true } },
    ];

    // Filter models based on available memory
    // Use max of GPU VRAM and RAM since Ollama can offload to CPU
    const gpuMem = hw?.gpu_vram_gb || 0;
    const ramMem = hw?.ram_gb || 8;
    const availableMem = Math.max(gpuMem, ramMem);
    const popularModels = allPopularModels.filter(m => m.ramNeeded <= availableMem + 4); // +4GB buffer

    const popularGrid = el('div');
    popularGrid.style.cssText = `
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 8px;
      margin-bottom: 16px;
    `;

    for (const model of popularModels) {
      const isInstalled = ollamaStatus?.available_models?.some(m => m.startsWith(model.name.split(':')[0]));
      const modelCard = el('button');
      modelCard.style.cssText = `
        padding: 10px 12px;
        background: ${isInstalled ? 'rgba(34, 197, 94, 0.1)' : 'rgba(255,255,255,0.03)'};
        border: 1px solid ${isInstalled ? 'rgba(34, 197, 94, 0.3)' : '#333'};
        border-radius: 6px;
        text-align: left;
        cursor: ${isInstalled ? 'default' : 'pointer'};
        transition: all 0.2s;
      `;
      if (!isInstalled) {
        modelCard.addEventListener('mouseenter', () => {
          modelCard.style.background = 'rgba(59, 130, 246, 0.1)';
          modelCard.style.borderColor = 'rgba(59, 130, 246, 0.4)';
        });
        modelCard.addEventListener('mouseleave', () => {
          modelCard.style.background = 'rgba(255,255,255,0.03)';
          modelCard.style.borderColor = '#333';
        });
      }

      // Build capability badges
      const capBadges: string[] = [];
      if (model.caps.tools) capBadges.push('<span style="color: #4ade80;">🔧</span>');
      if (model.caps.vision) capBadges.push('<span style="color: #60a5fa;">👁️</span>');
      if (model.caps.thinking) capBadges.push('<span style="color: #f472b6;">🧠</span>');
      const capBadgeHtml = capBadges.length > 0 ? `<span style="margin-left: 6px;">${capBadges.join(' ')}</span>` : '';

      modelCard.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 4px;">
          <div style="font-size: 13px; font-weight: 500; color: #fff;">
            ${model.name} ${isInstalled ? '<span style="color: #22c55e; font-size: 11px;">✓</span>' : ''}${capBadgeHtml}
          </div>
          <div style="font-size: 10px; padding: 2px 6px; background: rgba(59,130,246,0.2); border-radius: 3px; color: #60a5fa;">
            ${model.params}
          </div>
        </div>
        <div style="font-size: 11px; color: rgba(255,255,255,0.5); margin-bottom: 4px;">${model.desc}</div>
        <div style="display: flex; gap: 8px; font-size: 10px; color: rgba(255,255,255,0.4);">
          <span>📦 ${model.size}</span>
          <span>📝 ${model.ctx.toLocaleString()} ctx</span>
        </div>
      `;

      if (!isInstalled) {
        modelCard.addEventListener('click', async () => {
          // Disable hover effects during download
          modelCard.onmouseenter = null;
          modelCard.onmouseleave = null;
          modelCard.style.cursor = 'default';
          modelCard.style.background = 'rgba(59, 130, 246, 0.1)';
          modelCard.style.borderColor = 'rgba(59, 130, 246, 0.4)';

          modelCard.innerHTML = `
            <div style="font-size: 13px; font-weight: 500; color: #3b82f6; margin-bottom: 4px;">
              Downloading ${model.name}...
            </div>
            <div style="height: 6px; background: rgba(0,0,0,0.3); border-radius: 3px; overflow: hidden; margin-bottom: 4px;">
              <div class="progress-bar" style="height: 100%; width: 0%; background: #3b82f6; transition: width 0.3s;"></div>
            </div>
            <div class="progress-text" style="font-size: 11px; color: rgba(255,255,255,0.5);">Starting...</div>
          `;

          const progressBar = modelCard.querySelector('.progress-bar') as HTMLElement;
          const progressText = modelCard.querySelector('.progress-text') as HTMLElement;

          try {
            await downloadModelWithProgress(model.name, (status) => {
              if (progressBar) progressBar.style.width = `${status.progress}%`;
              if (progressText) {
                if (status.total > 0) {
                  progressText.textContent = `${status.progress}% - ${formatBytes(status.completed)} / ${formatBytes(status.total)}`;
                } else {
                  progressText.textContent = status.status || 'Downloading...';
                }
              }
            });

            modelCard.style.background = 'rgba(34, 197, 94, 0.1)';
            modelCard.style.borderColor = 'rgba(34, 197, 94, 0.3)';
            modelCard.innerHTML = `
              <div style="font-size: 13px; font-weight: 500; color: #22c55e; margin-bottom: 2px;">
                ✓ ${model.name}
              </div>
              <div style="font-size: 11px; color: rgba(255,255,255,0.5);">Download complete!</div>
            `;
            setTimeout(() => void loadData(), 1500);
          } catch (e: unknown) {
            const msg = e instanceof Error ? e.message : String(e);
            modelCard.style.background = 'rgba(239, 68, 68, 0.1)';
            modelCard.style.borderColor = 'rgba(239, 68, 68, 0.3)';
            modelCard.innerHTML = `
              <div style="font-size: 13px; font-weight: 500; color: #ef4444; margin-bottom: 2px;">✗ Failed</div>
              <div style="font-size: 11px; color: rgba(255,255,255,0.5);">${msg}</div>
            `;
          }
        });
      }
      popularGrid.appendChild(modelCard);
    }
    modelSection.appendChild(popularGrid);

    // Custom model download
    const downloadRow = createSettingRow('Download Other Model', 'Enter any model from ollama.com/library');
    const downloadInput = el('input') as HTMLInputElement;
    downloadInput.type = 'text';
    downloadInput.placeholder = 'e.g., qwen2:7b, solar:10.7b';
    downloadInput.style.cssText = `
      flex: 1;
      padding: 8px 12px;
      background: rgba(0,0,0,0.3);
      border: 1px solid #444;
      border-radius: 4px;
      color: #fff;
      font-size: 13px;
    `;

    const downloadBtn = el('button');
    downloadBtn.textContent = 'Download';
    downloadBtn.style.cssText = `
      padding: 8px 16px;
      background: #22c55e;
      border: none;
      border-radius: 4px;
      color: #fff;
      cursor: pointer;
      font-size: 13px;
      min-width: 100px;
    `;

    // Progress indicator for custom download (replaces input row during download)
    const progressContainer = el('div');
    progressContainer.style.cssText = `
      display: none;
      flex-direction: column;
      gap: 4px;
      flex: 1;
    `;
    progressContainer.innerHTML = `
      <div class="dl-model-name" style="font-size: 13px; color: #3b82f6; font-weight: 500;"></div>
      <div style="height: 6px; background: rgba(0,0,0,0.3); border-radius: 3px; overflow: hidden;">
        <div class="dl-progress-bar" style="height: 100%; width: 0%; background: #3b82f6; transition: width 0.3s;"></div>
      </div>
      <div class="dl-progress-text" style="font-size: 11px; color: rgba(255,255,255,0.5);">Starting...</div>
    `;

    downloadBtn.addEventListener('click', async () => {
      const modelName = downloadInput.value.trim();
      if (!modelName) return;

      // Hide input, show progress
      downloadInput.style.display = 'none';
      downloadBtn.style.display = 'none';
      progressContainer.style.display = 'flex';

      const modelNameEl = progressContainer.querySelector('.dl-model-name') as HTMLElement;
      const progressBar = progressContainer.querySelector('.dl-progress-bar') as HTMLElement;
      const progressText = progressContainer.querySelector('.dl-progress-text') as HTMLElement;

      if (modelNameEl) modelNameEl.textContent = `Downloading ${modelName}...`;

      try {
        await downloadModelWithProgress(modelName, (status) => {
          if (progressBar) progressBar.style.width = `${status.progress}%`;
          if (progressText) {
            if (status.total > 0) {
              progressText.textContent = `${status.progress}% - ${formatBytes(status.completed)} / ${formatBytes(status.total)}`;
            } else {
              progressText.textContent = status.status || 'Downloading...';
            }
          }
        });

        if (modelNameEl) modelNameEl.textContent = `✓ ${modelName} downloaded!`;
        modelNameEl.style.color = '#22c55e';
        if (progressBar) progressBar.style.background = '#22c55e';
        if (progressText) progressText.textContent = 'Complete';

        downloadInput.value = '';
        setTimeout(() => void loadData(), 1500);
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        if (modelNameEl) {
          modelNameEl.textContent = `✗ Failed: ${modelName}`;
          modelNameEl.style.color = '#ef4444';
        }
        if (progressBar) progressBar.style.background = '#ef4444';
        if (progressText) progressText.textContent = msg;
      }

      // Reset after a delay
      setTimeout(() => {
        progressContainer.style.display = 'none';
        downloadInput.style.display = 'block';
        downloadBtn.style.display = 'block';
        if (modelNameEl) modelNameEl.style.color = '#3b82f6';
        if (progressBar) {
          progressBar.style.width = '0%';
          progressBar.style.background = '#3b82f6';
        }
        if (progressText) progressText.textContent = 'Starting...';
      }, 3000);
    });

    downloadRow.appendChild(downloadInput);
    downloadRow.appendChild(progressContainer);
    downloadRow.appendChild(downloadBtn);
    modelSection.appendChild(downloadRow);

    content.appendChild(modelSection);
  }

  function renderPersonaTab() {
    const activePersona = personas.find(p => p.id === activePersonaId) || personas[0];

    // Prompts Review Section
    const promptsSection = createSection('System Prompts & Context');
    promptsSection.innerHTML += `
      <div style="color: rgba(255,255,255,0.7); font-size: 13px; margin-bottom: 12px;">
        These prompts shape how ReOS understands and responds to you. They're read-only for stability.
      </div>
    `;

    if (activePersona) {
      // System Prompt
      const systemPromptBox = createPromptBox(
        'System Prompt',
        'The core instructions that define ReOS personality and behavior',
        activePersona.system_prompt
      );
      promptsSection.appendChild(systemPromptBox);

      // Default Context
      const contextBox = createPromptBox(
        'Default Context',
        'Additional context provided to every conversation',
        activePersona.default_context || '(No default context set)'
      );
      promptsSection.appendChild(contextBox);
    }

    content.appendChild(promptsSection);

    // Parameters Section
    const paramsSection = createSection('LLM Parameters');

    if (activePersona) {
      // Temperature
      const tempParam = createParameterControl(
        'Temperature',
        activePersona.temperature,
        0, 2, 0.1,
        'Controls randomness in responses. Lower values (0.1-0.3) make responses more focused and deterministic. Higher values (0.7-1.0) make responses more creative and varied. Very high values (1.5+) can produce chaotic output.',
        async (val) => {
          activePersona.temperature = val;
          await savePersona(activePersona);
        }
      );
      paramsSection.appendChild(tempParam);

      // Top P
      const topPParam = createParameterControl(
        'Top P (Nucleus Sampling)',
        activePersona.top_p,
        0, 1, 0.05,
        'Controls diversity by limiting to top probability tokens. At 0.9, only tokens in the top 90% probability mass are considered. Lower values (0.5) give more predictable outputs. Higher values (0.95) allow more variety.',
        async (val) => {
          activePersona.top_p = val;
          await savePersona(activePersona);
        }
      );
      paramsSection.appendChild(topPParam);

      // Tool Call Limit
      const toolParam = createParameterControl(
        'Tool Call Limit',
        activePersona.tool_call_limit,
        1, 10, 1,
        'Maximum number of tools ReOS can use in a single response. Higher values let ReOS gather more information but may slow responses. Lower values keep responses quick but may limit capability.',
        async (val) => {
          activePersona.tool_call_limit = Math.round(val);
          await savePersona(activePersona);
        }
      );
      paramsSection.appendChild(toolParam);
    }

    content.appendChild(paramsSection);

    // Custom Context Section
    const customSection = createSection('Custom Persona Text');
    customSection.innerHTML += `
      <div style="color: rgba(255,255,255,0.7); font-size: 13px; margin-bottom: 12px;">
        Add your own text to customize how ReOS interacts with you. This is appended to the system prompt.
      </div>
    `;

    const customTextarea = el('textarea') as HTMLTextAreaElement;
    customTextarea.value = activePersona?.default_context || '';
    customTextarea.placeholder = 'Add custom instructions, preferences, or context here...\n\nExamples:\n- "Always explain technical concepts simply"\n- "I prefer concise responses"\n- "When writing code, add comments"';
    customTextarea.style.cssText = `
      width: 100%;
      min-height: 120px;
      padding: 12px;
      background: rgba(0,0,0,0.3);
      border: 1px solid #444;
      border-radius: 8px;
      color: #fff;
      font-size: 13px;
      resize: vertical;
      margin-bottom: 12px;
    `;

    const saveCustomBtn = el('button');
    saveCustomBtn.textContent = 'Save Custom Context';
    saveCustomBtn.style.cssText = `
      padding: 10px 20px;
      background: #3b82f6;
      border: none;
      border-radius: 6px;
      color: #fff;
      cursor: pointer;
      font-size: 13px;
    `;
    saveCustomBtn.addEventListener('click', async () => {
      if (activePersona) {
        activePersona.default_context = customTextarea.value;
        await savePersona(activePersona);
        saveCustomBtn.textContent = 'Saved!';
        setTimeout(() => { saveCustomBtn.textContent = 'Save Custom Context'; }, 1500);
      }
    });

    customSection.appendChild(customTextarea);
    customSection.appendChild(saveCustomBtn);

    content.appendChild(customSection);
  }

  function createSection(title: string): HTMLElement {
    const section = el('div');
    section.style.cssText = 'margin-bottom: 24px;';

    const header = el('div');
    header.textContent = title;
    header.style.cssText = `
      font-size: 15px;
      font-weight: 600;
      color: #fff;
      margin-bottom: 12px;
      padding-bottom: 8px;
      border-bottom: 1px solid #333;
    `;

    section.appendChild(header);
    return section;
  }

  function createSettingRow(label: string, description: string): HTMLElement {
    const row = el('div');
    row.style.cssText = 'margin-bottom: 12px;';

    const labelEl = el('div');
    labelEl.innerHTML = `<strong>${label}</strong>`;
    labelEl.style.cssText = 'margin-bottom: 4px; font-size: 13px; color: #fff;';

    const descEl = el('div');
    descEl.textContent = description;
    descEl.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.6); margin-bottom: 8px;';

    const inputRow = el('div');
    inputRow.style.cssText = 'display: flex; gap: 8px;';

    row.appendChild(labelEl);
    row.appendChild(descEl);
    row.appendChild(inputRow);

    return inputRow;
  }

  function createPromptBox(title: string, description: string, content: string): HTMLElement {
    const box = el('div');
    box.style.cssText = `
      margin-bottom: 16px;
      padding: 12px;
      background: rgba(0,0,0,0.2);
      border-radius: 8px;
      border-left: 3px solid #3b82f6;
    `;

    const titleEl = el('div');
    titleEl.innerHTML = `<strong>${title}</strong>`;
    titleEl.style.cssText = 'margin-bottom: 4px; font-size: 13px; color: #fff;';

    const descEl = el('div');
    descEl.textContent = description;
    descEl.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.6); margin-bottom: 8px;';

    const contentEl = el('pre');
    contentEl.textContent = content.length > 500 ? content.slice(0, 500) + '...' : content;
    contentEl.style.cssText = `
      margin: 0;
      padding: 8px;
      background: rgba(0,0,0,0.3);
      border-radius: 4px;
      font-size: 11px;
      color: rgba(255,255,255,0.8);
      white-space: pre-wrap;
      word-break: break-word;
      max-height: 150px;
      overflow: auto;
    `;

    box.appendChild(titleEl);
    box.appendChild(descEl);
    box.appendChild(contentEl);

    return box;
  }

  function createParameterControl(
    name: string,
    value: number,
    min: number,
    max: number,
    step: number,
    description: string,
    onChange: (val: number) => Promise<void>
  ): HTMLElement {
    const container = el('div');
    container.style.cssText = `
      margin-bottom: 20px;
      padding: 12px;
      background: rgba(0,0,0,0.2);
      border-radius: 8px;
    `;

    const header = el('div');
    header.style.cssText = 'display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;';

    const nameEl = el('div');
    nameEl.innerHTML = `<strong>${name}</strong>`;
    nameEl.style.cssText = 'font-size: 13px; color: #fff;';

    const valueEl = el('div');
    valueEl.textContent = value.toFixed(step < 1 ? 2 : 0);
    valueEl.style.cssText = 'font-family: monospace; font-size: 14px; color: #3b82f6;';

    header.appendChild(nameEl);
    header.appendChild(valueEl);

    const slider = el('input') as HTMLInputElement;
    slider.type = 'range';
    slider.min = String(min);
    slider.max = String(max);
    slider.step = String(step);
    slider.value = String(value);
    slider.style.cssText = `
      width: 100%;
      margin-bottom: 8px;
      accent-color: #3b82f6;
    `;

    slider.addEventListener('input', () => {
      valueEl.textContent = parseFloat(slider.value).toFixed(step < 1 ? 2 : 0);
    });

    slider.addEventListener('change', async () => {
      await onChange(parseFloat(slider.value));
    });

    const descEl = el('div');
    descEl.textContent = description;
    descEl.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.6); line-height: 1.4;';

    container.appendChild(header);
    container.appendChild(slider);
    container.appendChild(descEl);

    return container;
  }

  async function savePersona(persona: PersonaData) {
    try {
      await kernelRequest('personas/upsert', { persona });
    } catch (e) {
      console.error('Failed to save persona:', e);
    }
  }

  return {
    element: overlay,
    show,
    hide,
  };
}
