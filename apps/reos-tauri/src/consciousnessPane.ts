/**
 * Consciousness Pane - Real-time visibility into CAIRN's thinking process.
 *
 * Philosophy: Full transparency as our open-source competitive advantage.
 * Users see headlines of each reasoning step and memory creation in real-time.
 *
 * This component renders consciousness events as a compact stream:
 * - Intent extraction and tool calls
 * - Reasoning phases
 * - Memory creation from turn assessment
 * - Response generation
 */

import { escapeHtml } from "./dom";
import type { ConsciousnessEvent } from "./types";

// Event type to CSS class mapping
const EVENT_TYPE_CLASSES: Record<string, string> = {
  // Phases
  PHASE_START: "event-phase",
  PHASE_COMPLETE: "event-phase",

  // Intent extraction
  INTENT_EXTRACTED: "event-result",
  INTENT_VERIFIED: "event-result",
  PATTERN_MATCHED: "event-result",

  // Extended thinking
  COMPREHENSION_START: "event-phase",
  COMPREHENSION_RESULT: "event-result",
  DECOMPOSITION_START: "event-phase",
  DECOMPOSITION_RESULT: "event-result",
  REASONING_START: "event-phase",
  REASONING_ITERATION: "event-reasoning",
  REASONING_RESULT: "event-result",
  COHERENCE_START: "event-phase",
  COHERENCE_RESULT: "event-result",
  DECISION_START: "event-phase",
  DECISION_RESULT: "event-result",

  // Conversational reasoning
  EXPLORE_PASS: "event-reasoning",
  IDEATE_PASS: "event-reasoning",
  SYNTHESIZE_PASS: "event-reasoning",

  // LLM/Tool interaction
  LLM_CALL_START: "event-llm",
  LLM_CALL_COMPLETE: "event-llm",
  TOOL_CALL_START: "event-llm",
  TOOL_CALL_COMPLETE: "event-llm",

  // Memory
  MEMORY_ASSESSING: "event-memory",
  MEMORY_CREATED: "event-memory",
  MEMORY_NO_CHANGE: "event-memory",

  // Final
  RESPONSE_READY: "event-result",
};

// Compact single-character or small icons — no emoji clutter
const EVENT_TYPE_ICONS: Record<string, string> = {
  PHASE_START: "\u25B6",
  PHASE_COMPLETE: "\u2713",
  INTENT_EXTRACTED: "\u25C9",
  INTENT_VERIFIED: "\u2713",
  COMPREHENSION_START: "\u25B6",
  COMPREHENSION_RESULT: "\u2713",
  DECOMPOSITION_START: "\u25B6",
  DECOMPOSITION_RESULT: "\u2713",
  REASONING_START: "\u25B6",
  REASONING_ITERATION: "\u21BB",
  REASONING_RESULT: "\u2713",
  COHERENCE_START: "\u25B6",
  COHERENCE_RESULT: "\u2713",
  DECISION_START: "\u25B6",
  DECISION_RESULT: "\u2713",
  EXPLORE_PASS: "\u25B6",
  IDEATE_PASS: "\u25B6",
  SYNTHESIZE_PASS: "\u25B6",
  TOOL_CALL_START: "\u2699",
  TOOL_CALL_COMPLETE: "\u2713",
  LLM_CALL_START: "\u25CF",
  LLM_CALL_COMPLETE: "\u2713",
  MEMORY_ASSESSING: "\u25CB",
  MEMORY_CREATED: "\u2726",
  MEMORY_NO_CHANGE: "\u2013",
  RESPONSE_READY: "\u2714",
};

export interface ConsciousnessPaneState {
  events: ConsciousnessEvent[];
  expanded: Set<number>;
  isActive: boolean;
  autoScroll: boolean;
}

export function createConsciousnessPane(
  container: HTMLElement
): {
  update: (events: ConsciousnessEvent[], isActive: boolean) => void;
  clear: () => void;
  getState: () => ConsciousnessPaneState;
} {
  const state: ConsciousnessPaneState = {
    events: [],
    expanded: new Set<number>(),
    isActive: false,
    autoScroll: true,
  };

  // Render the pane structure
  container.innerHTML = `
    <div class="consciousness-pane">
      <div class="consciousness-header">
        <span class="consciousness-title">Consciousness Stream</span>
        <div class="consciousness-header-actions">
          <button class="consciousness-scroll-btn" title="Toggle auto-scroll">\u2B07</button>
          <button class="consciousness-clear-btn" title="Clear">\u00D7</button>
        </div>
      </div>
      <div class="consciousness-events"></div>
      <div class="consciousness-footer">
        <span class="consciousness-status">Idle</span>
      </div>
    </div>
  `;

  const eventsContainer = container.querySelector(
    ".consciousness-events"
  ) as HTMLElement;
  const statusEl = container.querySelector(
    ".consciousness-status"
  ) as HTMLElement;
  const clearBtn = container.querySelector(
    ".consciousness-clear-btn"
  ) as HTMLButtonElement;
  const scrollBtn = container.querySelector(
    ".consciousness-scroll-btn"
  ) as HTMLButtonElement;

  // Update scroll button appearance
  function updateScrollBtn() {
    if (state.autoScroll) {
      scrollBtn.textContent = "\u2B07";
      scrollBtn.title = "Auto-scroll ON (click to stop)";
      scrollBtn.style.opacity = "1";
    } else {
      scrollBtn.textContent = "\u23F8";
      scrollBtn.title = "Auto-scroll OFF (click to resume)";
      scrollBtn.style.opacity = "0.5";
    }
  }
  updateScrollBtn();

  // Clear button handler
  clearBtn.addEventListener("click", () => {
    state.events = [];
    state.expanded.clear();
    renderEvents();
  });

  // Scroll toggle button handler
  scrollBtn.addEventListener("click", () => {
    state.autoScroll = !state.autoScroll;
    updateScrollBtn();
    if (state.autoScroll) {
      eventsContainer.scrollTop = eventsContainer.scrollHeight;
    }
  });

  function renderEvent(event: ConsciousnessEvent, index: number): string {
    const typeClass = EVENT_TYPE_CLASSES[event.type] || "event-phase";
    const icon = EVENT_TYPE_ICONS[event.type] || "\u2022";
    const isExpanded = state.expanded.has(index);
    const hasContent = event.content && event.content.length > 0;

    let contentHtml = "";
    if (hasContent && isExpanded) {
      try {
        const escapedContent = event.content
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/\n/g, "<br>");
        contentHtml = `<div class="consciousness-content">${escapedContent}</div>`;
      } catch {
        contentHtml = `<div class="consciousness-content">${escapeHtml(event.content)}</div>`;
      }
    }

    return `
      <div class="consciousness-event ${typeClass}" data-index="${index}">
        <div class="consciousness-event-header">
          <span class="consciousness-icon">${icon}</span>
          <span class="consciousness-headline">${escapeHtml(event.title)}</span>
          ${hasContent ? `<button class="consciousness-expand-btn">${isExpanded ? "\u2212" : "+"}</button>` : ""}
        </div>
        ${contentHtml}
      </div>
    `;
  }

  function renderEvents() {
    const html = state.events.map(renderEvent).join("");
    eventsContainer.innerHTML = html;

    // Attach expand/collapse handlers
    eventsContainer.querySelectorAll(".consciousness-expand-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const eventEl = (e.target as HTMLElement).closest(".consciousness-event");
        if (!eventEl) return;
        const index = parseInt(eventEl.getAttribute("data-index") || "0", 10);

        if (state.expanded.has(index)) {
          state.expanded.delete(index);
        } else {
          state.expanded.add(index);
        }
        renderEvents();
      });
    });

    // Auto-scroll to bottom only when enabled
    if (state.autoScroll) {
      eventsContainer.scrollTop = eventsContainer.scrollHeight;
    }
  }

  function update(events: ConsciousnessEvent[], isActive: boolean) {
    state.events = events;
    state.isActive = isActive;

    renderEvents();

    // Update status
    if (isActive) {
      statusEl.textContent = "Processing...";
      statusEl.classList.add("active");
    } else if (events.length > 0) {
      statusEl.textContent = `${events.length} steps`;
      statusEl.classList.remove("active");
    } else {
      statusEl.textContent = "Idle";
      statusEl.classList.remove("active");
    }
  }

  function clear() {
    state.events = [];
    state.expanded.clear();
    state.isActive = false;
    renderEvents();
    statusEl.textContent = "Idle";
    statusEl.classList.remove("active");
  }

  function getState() {
    return { ...state };
  }

  return { update, clear, getState };
}
