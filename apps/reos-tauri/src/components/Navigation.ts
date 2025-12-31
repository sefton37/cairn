/**
 * Navigation component for the left sidebar
 */

import { Component, KernelRequestFn, el } from './types';

interface ActData {
  act_id: string;
  title: string;
  active: boolean;
  notes: string;
}

export class Navigation implements Component {
  private container: HTMLDivElement;
  private actsList: HTMLDivElement;
  private activeActId: string | null = null;
  private actsCache: ActData[] = [];
  private onActSelected?: (actId: string | null) => void;
  private onMeClick?: () => void;

  constructor(private kernelRequest: KernelRequestFn) {
    this.container = el('div');
    this.container.className = 'nav';
    this.container.style.width = '240px';
    this.container.style.borderRight = '1px solid #ddd';
    this.container.style.padding = '12px';
    this.container.style.overflow = 'auto';

    const navTitle = el('div');
    navTitle.textContent = 'ReOS';
    navTitle.style.fontWeight = '600';
    navTitle.style.marginBottom = '10px';

    const meHeader = el('div');
    meHeader.textContent = 'Me (The Play)';
    meHeader.style.marginTop = '12px';
    meHeader.style.fontWeight = '600';

    const meBtn = el('button');
    meBtn.textContent = 'Me';
    meBtn.addEventListener('click', () => {
      if (this.onMeClick) {
        this.onMeClick();
      }
    });

    const actsHeader = el('div');
    actsHeader.textContent = 'Acts';
    actsHeader.style.marginTop = '12px';
    actsHeader.style.fontWeight = '600';

    this.actsList = el('div');
    this.actsList.style.display = 'flex';
    this.actsList.style.flexDirection = 'column';
    this.actsList.style.gap = '6px';

    this.container.appendChild(navTitle);
    this.container.appendChild(meHeader);
    this.container.appendChild(meBtn);
    this.container.appendChild(actsHeader);
    this.container.appendChild(this.actsList);
  }

  async init(): Promise<void> {
    await this.refreshActs();
  }

  setOnActSelected(callback: (actId: string | null) => void): void {
    this.onActSelected = callback;
  }

  setOnMeClick(callback: () => void): void {
    this.onMeClick = callback;
  }

  async refreshActs(): Promise<void> {
    try {
      const res = await this.kernelRequest('play/acts/list', {}) as {
        active_act_id: string | null;
        acts: ActData[];
      };
      this.activeActId = res.active_act_id ?? null;
      this.actsCache = res.acts || [];
      this.renderActsList();
    } catch (error) {
      console.error('Failed to load acts:', error);
    }
  }

  private renderActsList(): void {
    this.actsList.innerHTML = '';

    if (this.actsCache.length === 0) {
      const empty = el('div');
      empty.textContent = '(no acts yet)';
      empty.style.opacity = '0.7';
      this.actsList.appendChild(empty);
      return;
    }

    for (const a of this.actsCache) {
      const btn = el('button');
      btn.textContent = a.act_id === this.activeActId ? `• ${a.title}` : a.title;
      btn.addEventListener('click', async () => {
        try {
          const setRes = await this.kernelRequest('play/acts/set_active', {
            act_id: a.act_id
          }) as { active_act_id: string | null; acts: ActData[] };
          this.activeActId = setRes.active_act_id ?? null;
          await this.refreshActs();

          if (this.onActSelected) {
            this.onActSelected(this.activeActId);
          }
        } catch (error) {
          console.error('Failed to set active act:', error);
        }
      });
      this.actsList.appendChild(btn);
    }
  }

  render(): HTMLElement {
    return this.container;
  }

  destroy(): void {
    // Cleanup if needed
  }
}
