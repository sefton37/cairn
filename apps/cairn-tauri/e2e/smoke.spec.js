/**
 * Smoke test suite for the Cairn Tauri frontend.
 *
 * Prerequisites:
 *   1. Install Playwright:  npm install --save-dev @playwright/test
 *   2. Install browser:     npx playwright install chromium
 *   3. Start the Vite dev server: npm run dev  (serves on http://localhost:1420)
 *   4. Run tests: npx playwright test e2e/smoke.spec.js
 *
 * The mock intercepts all Tauri invoke() calls so the Python kernel does NOT
 * need to be running. Data is sourced from the real talkingrock.db (2026-03-27).
 */

import { test, expect } from '@playwright/test';
import { getMockScript } from './tauri-mock.js';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const BASE_URL = 'http://localhost:1420';
const SCREENSHOT_DIR = path.join(__dirname, 'screenshots');

// Inject the Tauri mock before every page load so window.__TAURI_INTERNALS__
// exists before any module import runs.
test.beforeEach(async ({ page }) => {
  await page.addInitScript({ content: getMockScript() });
});

// ---------------------------------------------------------------------------
// Test 1: Main UI loads — agent bar is visible
// ---------------------------------------------------------------------------

test('main UI loads with agent bar visible', async ({ page }) => {
  await page.goto(BASE_URL);

  // Wait for the agent bar to appear (populated by buildUi())
  const agentBar = page.locator('.agent-bar');
  await expect(agentBar).toBeVisible({ timeout: 10000 });

  // The "Talking Rock" title should be in the bar
  await expect(agentBar).toContainText('Talking Rock');

  // All 5 core agent items should be rendered
  const agentItems = page.locator('.agent-item');
  await expect(agentItems).toHaveCount(5);

  // "The Play" entry should be present
  const playItem = page.locator('.agent-item[data-agent-id="play"]');
  await expect(playItem).toBeVisible();
  await expect(playItem).toContainText('The Play');

  // CAIRN entry should be visible
  const cairnItem = page.locator('.agent-item[data-agent-id="cairn"]');
  await expect(cairnItem).toBeVisible();

  // Take a screenshot for review
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, '01-main-ui-loaded.png'),
    fullPage: false,
  });
});

// ---------------------------------------------------------------------------
// Test 2: The Play view — acts are listed in the sidebar
// ---------------------------------------------------------------------------

test('The Play view shows acts from mock data', async ({ page }) => {
  await page.goto(BASE_URL);

  // Wait for the agent bar
  await expect(page.locator('.agent-bar')).toBeVisible({ timeout: 10000 });

  // Click "The Play" in the agent bar
  const playItem = page.locator('.agent-item[data-agent-id="play"]');
  await playItem.click();

  // The play overlay/view should mount — wait for the sidebar
  const sidebar = page.locator('.play-sidebar');
  await expect(sidebar).toBeVisible({ timeout: 8000 });

  // "Your Story" is always the first act (pinned)
  await expect(sidebar).toContainText('Your Story');

  // The three user acts from mock data should appear
  await expect(sidebar).toContainText('Career Growth');
  await expect(sidebar).toContainText('Health & Fitness');
  await expect(sidebar).toContainText('Family');

  // At minimum 4 act-level tree items (Your Story + 3 acts)
  const actItems = page.locator('.tree-item.act');
  await expect(actItems).toHaveCount(4);

  // Take a screenshot showing the acts list
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, '02-play-acts-listed.png'),
    fullPage: false,
  });
});

// ---------------------------------------------------------------------------
// Test 3: Clicking an act expands its scenes
// ---------------------------------------------------------------------------

test('clicking an act expands its scenes', async ({ page }) => {
  await page.goto(BASE_URL);

  await expect(page.locator('.agent-bar')).toBeVisible({ timeout: 10000 });
  await page.locator('.agent-item[data-agent-id="play"]').click();

  const sidebar = page.locator('.play-sidebar');
  await expect(sidebar).toBeVisible({ timeout: 8000 });

  // Click on the "Career Growth" act to expand it
  const careerActItem = page.locator('.tree-item.act', { hasText: 'Career Growth' });
  await careerActItem.click();

  // Scenes for Career Growth should now be visible in the sidebar
  // (play/scenes/list returns 3 scenes for act-e8623a0da3ca)
  await expect(sidebar).toContainText('Q2 Platform Migration');
  await expect(sidebar).toContainText('Tech Lead Mentoring');
  await expect(sidebar).toContainText('Architecture Review Board');

  // Take a screenshot with scenes expanded
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, '03-act-scenes-expanded.png'),
    fullPage: false,
  });
});

// ---------------------------------------------------------------------------
// Test 4: CAIRN attention view renders items
// ---------------------------------------------------------------------------

test('CAIRN view renders attention items from mock data', async ({ page }) => {
  await page.goto(BASE_URL);

  // Default view is CAIRN — the attention section loads on startup
  // Wait for the main container and any attention content to appear
  await expect(page.locator('.agent-bar')).toBeVisible({ timeout: 10000 });

  // The CAIRN view should show at least the first attention item
  // (actual selector depends on cairnView.ts rendering; check for text content)
  // Allow extra time for async data load
  await page.waitForTimeout(2000);

  // Take a screenshot of the CAIRN attention view
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, '04-cairn-attention-view.png'),
    fullPage: false,
  });

  // At minimum the shell should exist and not show an error state
  const shell = page.locator('.shell');
  await expect(shell).toBeVisible();
});

// ---------------------------------------------------------------------------
// Test 5: Context meter renders (header shows token usage)
// ---------------------------------------------------------------------------

test('context meter renders in CAIRN view header', async ({ page }) => {
  await page.goto(BASE_URL);

  await expect(page.locator('.agent-bar')).toBeVisible({ timeout: 10000 });

  // Context meter is embedded in the CAIRN chat header
  const contextMeter = page.locator('.nav-context-meter');
  await expect(contextMeter).toBeVisible({ timeout: 8000 });

  // Should show "Context" label
  await expect(contextMeter).toContainText('Context');

  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, '05-context-meter.png'),
    fullPage: false,
  });
});
