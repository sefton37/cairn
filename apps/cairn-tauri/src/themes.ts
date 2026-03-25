/**
 * Theme System for Cairn/Talking Rock
 *
 * 6 themes derived from the Sonora Sunrise brand palette:
 * - 3 dark: Desert Ember, Sunset Blaze, Dusk & Stone (default)
 * - 3 light: Morning Mesa, Sunlit Clay, High Desert
 *
 * Persisted to localStorage. Applied via CSS custom properties on <html>.
 */

export type ThemeId =
  | 'desert-ember'
  | 'sunset-blaze'
  | 'dusk-and-stone'
  | 'morning-mesa'
  | 'sunlit-clay'
  | 'high-desert';

export interface ThemeDefinition {
  id: ThemeId;
  name: string;
  group: 'dark' | 'light';
  description: string;
  colors: {
    // Core accent
    primary: string;
    primaryRgb: string; // for rgba() usage
    secondary: string;
    secondaryRgb: string;

    // Backgrounds
    bgBase: string; // raw background color
    bgPrimary: string;
    bgSecondary: string;
    bgTertiary: string;
    bgSurface: string;
    bgElevated: string;
    bgInput: string;

    // Body gradient
    gradientStart: string;
    gradientMid: string;
    gradientEnd: string;

    // Text
    textPrimary: string;
    textSecondary: string;
    textTertiary: string;
    textMuted: string;

    // Borders
    borderColor: string;
    borderFocus: string;

    // Chat
    chatUserBg: string;
    chatCairnBg: string;
    chatBubbleText: string;

    // Surfaces (nav, modal, etc.)
    navBg: string;
    modalBg: string;
    inputBarBg: string;

    // Color scheme for browser controls
    colorScheme: 'dark' | 'light';
  };
}

// ============ Dark Themes ============

const desertEmber: ThemeDefinition = {
  id: 'desert-ember',
  name: 'Desert Ember',
  group: 'dark',
  description: 'Warm copper on near-black. Earthy, mature, understated.',
  colors: {
    primary: '#c4956a',
    primaryRgb: '196, 149, 106',
    secondary: '#8a7560',
    secondaryRgb: '138, 117, 96',

    bgBase: '#111110',
    bgPrimary: '#111110',
    bgSecondary: '#161615',
    bgTertiary: '#1e1d1b',
    bgSurface: 'rgba(17, 17, 16, 0.95)',
    bgElevated: 'rgba(255, 255, 255, 0.04)',
    bgInput: 'rgba(0, 0, 0, 0.4)',

    gradientStart: '#111110',
    gradientMid: '#161615',
    gradientEnd: '#1e1d1b',

    textPrimary: '#e8e4de',
    textSecondary: 'rgba(232, 228, 222, 0.7)',
    textTertiary: 'rgba(232, 228, 222, 0.5)',
    textMuted: 'rgba(232, 228, 222, 0.3)',

    borderColor: 'rgba(255, 255, 255, 0.08)',
    borderFocus: 'rgba(196, 149, 106, 0.6)',

    chatUserBg: 'rgba(196, 149, 106, 0.85)',
    chatCairnBg: 'rgba(138, 117, 96, 0.15)',
    chatBubbleText: 'rgba(255, 255, 255, 0.97)',

    navBg: 'rgba(17, 17, 16, 0.95)',
    modalBg: '#1a1918',
    inputBarBg: 'rgba(17, 17, 16, 0.9)',

    colorScheme: 'dark',
  },
};

const sunsetBlaze: ThemeDefinition = {
  id: 'sunset-blaze',
  name: 'Sunset Blaze',
  group: 'dark',
  description: 'Coral-red primary. Bolder, more energetic — the fire in the sky.',
  colors: {
    primary: '#d4654a',
    primaryRgb: '212, 101, 74',
    secondary: '#7a6e65',
    secondaryRgb: '122, 110, 101',

    bgBase: '#12100f',
    bgPrimary: '#12100f',
    bgSecondary: '#181614',
    bgTertiary: '#201c19',
    bgSurface: 'rgba(18, 16, 15, 0.95)',
    bgElevated: 'rgba(255, 255, 255, 0.04)',
    bgInput: 'rgba(0, 0, 0, 0.4)',

    gradientStart: '#12100f',
    gradientMid: '#181614',
    gradientEnd: '#201c19',

    textPrimary: '#f0ebe5',
    textSecondary: 'rgba(240, 235, 229, 0.7)',
    textTertiary: 'rgba(240, 235, 229, 0.5)',
    textMuted: 'rgba(240, 235, 229, 0.3)',

    borderColor: 'rgba(255, 255, 255, 0.08)',
    borderFocus: 'rgba(212, 101, 74, 0.6)',

    chatUserBg: 'rgba(212, 101, 74, 0.85)',
    chatCairnBg: 'rgba(122, 110, 101, 0.15)',
    chatBubbleText: 'rgba(255, 255, 255, 0.97)',

    navBg: 'rgba(18, 16, 15, 0.95)',
    modalBg: '#1a1816',
    inputBarBg: 'rgba(18, 16, 15, 0.9)',

    colorScheme: 'dark',
  },
};

const duskAndStone: ThemeDefinition = {
  id: 'dusk-and-stone',
  name: 'Dusk & Stone',
  group: 'dark',
  description: 'Golden amber meets cool blue-slate. Warmth meets calm.',
  colors: {
    primary: '#d4a856',
    primaryRgb: '212, 168, 86',
    secondary: '#5e7a94',
    secondaryRgb: '94, 122, 148',

    bgBase: '#0f1114',
    bgPrimary: '#0f1114',
    bgSecondary: '#141619',
    bgTertiary: '#1a1d22',
    bgSurface: 'rgba(15, 17, 20, 0.95)',
    bgElevated: 'rgba(255, 255, 255, 0.04)',
    bgInput: 'rgba(0, 0, 0, 0.4)',

    gradientStart: '#0f1114',
    gradientMid: '#141619',
    gradientEnd: '#1a1d22',

    textPrimary: '#e8e4de',
    textSecondary: 'rgba(232, 228, 222, 0.7)',
    textTertiary: 'rgba(232, 228, 222, 0.5)',
    textMuted: 'rgba(232, 228, 222, 0.3)',

    borderColor: 'rgba(255, 255, 255, 0.08)',
    borderFocus: 'rgba(212, 168, 86, 0.6)',

    chatUserBg: 'rgba(212, 168, 86, 0.85)',
    chatCairnBg: 'rgba(94, 122, 148, 0.15)',
    chatBubbleText: 'rgba(255, 255, 255, 0.97)',

    navBg: 'rgba(15, 17, 20, 0.95)',
    modalBg: '#161920',
    inputBarBg: 'rgba(15, 17, 20, 0.9)',

    colorScheme: 'dark',
  },
};

// ============ Light Themes ============

const morningMesa: ThemeDefinition = {
  id: 'morning-mesa',
  name: 'Morning Mesa',
  group: 'light',
  description: 'Warm parchment. Like morning sun on sandstone walls.',
  colors: {
    primary: '#8b6540',
    primaryRgb: '139, 101, 64',
    secondary: '#78716a',
    secondaryRgb: '120, 113, 106',

    bgBase: '#faf7f3',
    bgPrimary: '#faf7f3',
    bgSecondary: '#f0ebe4',
    bgTertiary: '#e5ded5',
    bgSurface: '#ffffff',
    bgElevated: 'rgba(0, 0, 0, 0.02)',
    bgInput: '#f5f0ea',

    gradientStart: '#faf7f3',
    gradientMid: '#f5f0ea',
    gradientEnd: '#f0ebe4',

    textPrimary: '#1c1917',
    textSecondary: '#57534e',
    textTertiary: '#78716a',
    textMuted: '#a8a198',

    borderColor: '#e0d8ce',
    borderFocus: 'rgba(139, 101, 64, 0.6)',

    chatUserBg: '#8b6540',
    chatCairnBg: '#ffffff',
    chatBubbleText: '#ffffff',

    navBg: '#ffffff',
    modalBg: '#ffffff',
    inputBarBg: '#ffffff',

    colorScheme: 'light',
  },
};

const sunlitClay: ThemeDefinition = {
  id: 'sunlit-clay',
  name: 'Sunlit Clay',
  group: 'light',
  description: 'Terracotta warmth. The heat of midday sun on red rock.',
  colors: {
    primary: '#a84432',
    primaryRgb: '168, 68, 50',
    secondary: '#6b5f58',
    secondaryRgb: '107, 95, 88',

    bgBase: '#faf6f3',
    bgPrimary: '#faf6f3',
    bgSecondary: '#f0eae4',
    bgTertiary: '#e5ddd5',
    bgSurface: '#ffffff',
    bgElevated: 'rgba(0, 0, 0, 0.02)',
    bgInput: '#f5f0ea',

    gradientStart: '#faf6f3',
    gradientMid: '#f5f0ea',
    gradientEnd: '#f0eae4',

    textPrimary: '#1c1614',
    textSecondary: '#57504a',
    textTertiary: '#6b5f58',
    textMuted: '#a8a098',

    borderColor: '#e0d5cc',
    borderFocus: 'rgba(168, 68, 50, 0.6)',

    chatUserBg: '#a84432',
    chatCairnBg: '#ffffff',
    chatBubbleText: '#ffffff',

    navBg: '#ffffff',
    modalBg: '#ffffff',
    inputBarBg: '#ffffff',

    colorScheme: 'light',
  },
};

const highDesert: ThemeDefinition = {
  id: 'high-desert',
  name: 'High Desert',
  group: 'light',
  description: 'Cool clarity. Bright, dry, focused — high desert sky at midday.',
  colors: {
    primary: '#8a6c20',
    primaryRgb: '138, 108, 32',
    secondary: '#456480',
    secondaryRgb: '69, 100, 128',

    bgBase: '#f5f6f9',
    bgPrimary: '#f5f6f9',
    bgSecondary: '#eaecf1',
    bgTertiary: '#dfe2e8',
    bgSurface: '#ffffff',
    bgElevated: 'rgba(0, 0, 0, 0.02)',
    bgInput: '#eff0f4',

    gradientStart: '#f5f6f9',
    gradientMid: '#eff0f4',
    gradientEnd: '#eaecf1',

    textPrimary: '#14161c',
    textSecondary: '#4a4d56',
    textTertiary: '#6b6f7a',
    textMuted: '#9a9da6',

    borderColor: '#d8dbe2',
    borderFocus: 'rgba(138, 108, 32, 0.6)',

    chatUserBg: '#8a6c20',
    chatCairnBg: '#ffffff',
    chatBubbleText: '#ffffff',

    navBg: '#ffffff',
    modalBg: '#ffffff',
    inputBarBg: '#ffffff',

    colorScheme: 'light',
  },
};

// ============ Registry ============

export const THEMES: ThemeDefinition[] = [
  duskAndStone,
  desertEmber,
  sunsetBlaze,
  morningMesa,
  sunlitClay,
  highDesert,
];

export const DEFAULT_THEME: ThemeId = 'dusk-and-stone';

const STORAGE_KEY = 'cairn-theme';

export function getThemeById(id: ThemeId): ThemeDefinition {
  return THEMES.find(t => t.id === id) || duskAndStone;
}

export function getSavedThemeId(): ThemeId {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved && THEMES.some(t => t.id === saved)) {
    return saved as ThemeId;
  }
  return DEFAULT_THEME;
}

export function applyTheme(id: ThemeId): void {
  const theme = getThemeById(id);
  const root = document.documentElement;
  const c = theme.colors;

  // Persist
  localStorage.setItem(STORAGE_KEY, id);

  // Set data attribute for CSS rule matching
  root.setAttribute('data-theme', id);

  // Set CSS custom properties
  root.style.setProperty('--theme-primary', c.primary);
  root.style.setProperty('--theme-primary-rgb', c.primaryRgb);
  root.style.setProperty('--theme-secondary', c.secondary);
  root.style.setProperty('--theme-secondary-rgb', c.secondaryRgb);

  root.style.setProperty('--bg-base', c.bgBase);
  root.style.setProperty('--bg-primary', c.bgPrimary);
  root.style.setProperty('--bg-secondary', c.bgSecondary);
  root.style.setProperty('--bg-tertiary', c.bgTertiary);
  root.style.setProperty('--bg-surface', c.bgSurface);
  root.style.setProperty('--bg-elevated', c.bgElevated);
  root.style.setProperty('--bg-input', c.bgInput);

  root.style.setProperty('--gradient-start', c.gradientStart);
  root.style.setProperty('--gradient-mid', c.gradientMid);
  root.style.setProperty('--gradient-end', c.gradientEnd);

  root.style.setProperty('--text-primary', c.textPrimary);
  root.style.setProperty('--text-secondary', c.textSecondary);
  root.style.setProperty('--text-tertiary', c.textTertiary);
  root.style.setProperty('--text-muted', c.textMuted);

  root.style.setProperty('--border-color', c.borderColor);
  root.style.setProperty('--border-focus', c.borderFocus);

  root.style.setProperty('--chat-user-bg', c.chatUserBg);
  root.style.setProperty('--chat-cairn-bg', c.chatCairnBg);
  root.style.setProperty('--chat-bubble-text', c.chatBubbleText);

  root.style.setProperty('--nav-bg', c.navBg);
  root.style.setProperty('--modal-bg', c.modalBg);
  root.style.setProperty('--input-bar-bg', c.inputBarBg);

  // Update color scheme for browser controls
  root.style.colorScheme = c.colorScheme;

  // Update body/app gradient
  const app = document.getElementById('app');
  if (app) {
    app.style.background = `linear-gradient(135deg, ${c.gradientStart} 0%, ${c.gradientMid} 50%, ${c.gradientEnd} 100%)`;
  }
}

/**
 * Initialize theme on app startup. Call before first render.
 */
export function initTheme(): void {
  applyTheme(getSavedThemeId());
}
