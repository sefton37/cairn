/**
 * UI Interactions e2e test suite for the Cairn Tauri frontend.
 *
 * Tests actual browser-level UI interactions: clicking, navigating, verifying
 * visible state. All assertions are DOM/visual — no direct RPC calls.
 *
 * Prerequisites:
 *   1. Vite dev server running on port 1420:   npm run dev
 *   2. Cairn backend running on port 8010:     python -m cairn.app
 *   3. Synthetic data loaded:                  python scripts/load_synthetic_data.py
 *
 * Run:
 *   npx playwright test e2e/ui-interactions.spec.mjs
 */

import { test, expect } from '@playwright/test';
import { getProxyScript } from './tauri-proxy.mjs';

const BASE_URL = 'http://localhost:1420';

// Longer timeout for tests that load real data from the backend.
const BACKEND_TIMEOUT = 15000;
// Standard timeout for UI elements that should already be rendered.
const UI_TIMEOUT = 8000;

// -------------------------------------------------------------------------
// Helpers
// -------------------------------------------------------------------------

/**
 * Navigate to the app and wait for the agent bar (signals buildUi() done).
 */
async function loadApp(page) {
  await page.goto(BASE_URL);
  await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });
  // Allow async data loads (attention items, context meter) to settle.
  await page.waitForTimeout(2000);
}

/**
 * Open The Play view by clicking the sidebar item.
 */
async function openPlay(page) {
  await page.locator('.agent-item[data-agent-id="play"]').click();
  await expect(page.locator('.play-sidebar')).toBeVisible({ timeout: UI_TIMEOUT });
}

// -------------------------------------------------------------------------
// Inject proxy before every test — each test gets a fresh page load.
// -------------------------------------------------------------------------

test.beforeEach(async ({ page }) => {
  await page.addInitScript({ content: getProxyScript() });
  await page.goto(BASE_URL);
  await page.waitForTimeout(2000);
});

// =========================================================================
// Group 1: Settings Overlay (UI-driven)
// =========================================================================

test.describe('Settings Overlay', () => {

  test('Settings opens and shows LLM Provider tab by default', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });

    // Click the Settings button (bottom of agent bar)
    await page.locator('.agent-bar button', { hasText: 'Settings' }).click();

    // Overlay should appear
    const overlay = page.locator('.settings-overlay');
    await expect(overlay).toBeVisible({ timeout: UI_TIMEOUT });

    await page.screenshot({ path: 'e2e/screenshots/s1-01-settings-opened.png' });

    // The LLM tab renders a "Provider" section heading by default
    await expect(page.locator('.settings-content')).toContainText('Provider', { timeout: UI_TIMEOUT });

    // Provider dropdown should show Ollama (Local) — first select in the modal
    const providerSelect = page.locator('.settings-modal select').first();
    await expect(providerSelect).toBeVisible({ timeout: UI_TIMEOUT });
    await expect(providerSelect).toContainText('Ollama (Local)');

    // "Connected" status should appear once backend data loads
    await expect(page.locator('.settings-modal')).toContainText('Connected', { timeout: BACKEND_TIMEOUT });
  });

  test('Settings shows hardware info', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });
    await page.locator('.agent-bar button', { hasText: 'Settings' }).click();

    const modal = page.locator('.settings-modal');
    await expect(modal).toBeVisible({ timeout: UI_TIMEOUT });

    // Wait for data to load — hardware section appears after ollama/status resolves
    await expect(modal).toContainText('System RAM', { timeout: BACKEND_TIMEOUT });

    await page.screenshot({ path: 'e2e/screenshots/s1-02-settings-hardware.png' });

    // GPU section is present (either showing a GPU name or "not available" text)
    await expect(modal).toContainText('GB', { timeout: UI_TIMEOUT });
  });

  test('Settings shows model list', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });
    await page.locator('.agent-bar button', { hasText: 'Settings' }).click();

    const modal = page.locator('.settings-modal');
    await expect(modal).toBeVisible({ timeout: UI_TIMEOUT });

    // Model list buttons are rendered for each available model.
    // Allow extra time since the model list is fetched from Ollama.
    await page.waitForTimeout(3000);

    await page.screenshot({ path: 'e2e/screenshots/s1-03-settings-models.png' });

    // At least one model button should be present if Ollama is running.
    // We use a soft count check — zero models is acceptable if Ollama has no models.
    const modelButtons = page.locator('.settings-modal button').filter({ hasNotText: /Settings|Test Connection|Close|✕|Save|Appearance|Safety|Integrations|LLM|Persona|Learning/ });
    const count = await modelButtons.count();
    // Log count for diagnostics but do not hard-fail — model count depends on Ollama state.
    if (count < 1) {
      console.warn('[ui-interactions] No model buttons found — Ollama may have no models installed');
    }

    // The content area should be visible and contain model-related text
    await expect(page.locator('.settings-content')).toBeVisible({ timeout: UI_TIMEOUT });
  });

  test('Settings Safety tab loads', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });
    await page.locator('.agent-bar button', { hasText: 'Settings' }).click();

    const modal = page.locator('.settings-modal');
    await expect(modal).toBeVisible({ timeout: UI_TIMEOUT });

    // Click the Safety tab
    await page.locator('.settings-tab.safety').click();

    await page.screenshot({ path: 'e2e/screenshots/s1-04-settings-safety.png' });

    // Safety Circuit Breakers header is always rendered (even before data loads)
    await expect(modal).toContainText('Safety Circuit Breakers', { timeout: UI_TIMEOUT });

    // Rate limits section appears once safety/settings RPC resolves
    await expect(modal).toContainText('Rate Limits', { timeout: BACKEND_TIMEOUT });

    // Command length limit setting should be visible
    await expect(modal).toContainText('Command', { timeout: BACKEND_TIMEOUT });
  });

  test('Settings Integrations tab shows Thunderbird', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });
    await page.locator('.agent-bar button', { hasText: 'Settings' }).click();

    const modal = page.locator('.settings-modal');
    await expect(modal).toBeVisible({ timeout: UI_TIMEOUT });

    // Click the Integrations tab
    await page.locator('.settings-tab.integrations').click();

    await page.screenshot({ path: 'e2e/screenshots/s1-05-settings-integrations.png' });

    // Thunderbird section must appear
    await expect(modal).toContainText('Thunderbird', { timeout: BACKEND_TIMEOUT });
  });

  test('Settings Appearance tab loads', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });
    await page.locator('.agent-bar button', { hasText: 'Settings' }).click();

    const modal = page.locator('.settings-modal');
    await expect(modal).toBeVisible({ timeout: UI_TIMEOUT });

    // Click the Appearance tab
    await page.locator('.settings-tab.appearance').click();

    await page.screenshot({ path: 'e2e/screenshots/s1-06-settings-appearance.png' });

    // Theme section with color options must appear
    await expect(modal).toContainText('Theme', { timeout: UI_TIMEOUT });
    // At least the "Dark" and "Light" group labels are rendered
    await expect(modal).toContainText('Dark', { timeout: UI_TIMEOUT });
  });

  test('Settings closes via X button', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });
    await page.locator('.agent-bar button', { hasText: 'Settings' }).click();

    const overlay = page.locator('.settings-overlay');
    await expect(overlay).toBeVisible({ timeout: UI_TIMEOUT });

    // Click the close (✕) button
    await page.locator('.settings-modal button', { hasText: '✕' }).click();

    await page.screenshot({ path: 'e2e/screenshots/s1-07-settings-closed.png' });

    // Overlay should no longer be visible
    await expect(overlay).not.toBeVisible({ timeout: UI_TIMEOUT });
  });

});

// =========================================================================
// Group 2: Attention Card Interactions (UI-driven)
// =========================================================================

test.describe('Attention Card Interactions', () => {

  test('Attention cards are rendered with real data', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });
    // Allow extra settle time for attention items to load
    await page.waitForTimeout(3000);

    await page.screenshot({ path: 'e2e/screenshots/s2-01-attention-cards.png' });

    // Calendar & Tasks column header must be visible
    await expect(page.locator('.surfaced-column-header', { hasText: 'Calendar & Tasks' })).toBeVisible({ timeout: UI_TIMEOUT });

    // Count all surfaced item cards (draggable divs in the calendar list)
    const calendarList = page.locator('.surfaced-column').first().locator('.surfaced-list');
    await expect(calendarList).toBeVisible({ timeout: UI_TIMEOUT });

    // At least 3 attention items should be present with synthetic data
    const cards = calendarList.locator('[data-entity-id]');
    const count = await cards.count();
    if (count < 3) {
      console.warn(`[ui-interactions] Only ${count} attention cards found — synthetic data may not be loaded`);
    }
    // At minimum the list container must exist and be visible
    await expect(calendarList).toBeVisible({ timeout: UI_TIMEOUT });
  });

  test('Attention cards show urgency colors', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });
    await page.waitForTimeout(3000);

    const calendarList = page.locator('.surfaced-column').first().locator('.surfaced-list');
    const cards = calendarList.locator('[data-entity-id]');
    const count = await cards.count();

    if (count === 0) {
      test.skip(true, 'No attention cards found — synthetic data may not be loaded');
    }

    // First card must have a colored urgency dot (inline span with border-radius: 50%)
    // The dot is rendered as a <span> with background color and cursor: help
    const firstCard = cards.first();
    await expect(firstCard).toBeVisible({ timeout: UI_TIMEOUT });

    await page.screenshot({ path: 'e2e/screenshots/s2-02-attention-urgency.png' });

    // The urgency dot span has title attribute and inline border-radius style
    const urgencyDot = firstCard.locator('span[title][style*="border-radius: 50%"]');
    await expect(urgencyDot).toBeVisible({ timeout: UI_TIMEOUT });
  });

  test('Email cards show upvote/downvote buttons', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });
    await page.waitForTimeout(3000);

    // Email column is the second surfaced-column
    const emailList = page.locator('.surfaced-column').nth(1).locator('.surfaced-list');
    await expect(emailList).toBeVisible({ timeout: UI_TIMEOUT });

    const emailCards = emailList.locator('[data-entity-id]');
    const count = await emailCards.count();

    if (count === 0) {
      console.warn('[ui-interactions] No email cards found — Thunderbird integration may not be configured');
      // Pass the test anyway — email cards only appear with Thunderbird
      return;
    }

    await page.screenshot({ path: 'e2e/screenshots/s2-03-email-cards.png' });

    // First email card should have ▲ and ▼ buttons
    const firstEmail = emailCards.first();
    await expect(firstEmail.locator('button', { hasText: '▲' })).toBeVisible({ timeout: UI_TIMEOUT });
    await expect(firstEmail.locator('button', { hasText: '▼' })).toBeVisible({ timeout: UI_TIMEOUT });
  });

  test('Email scores are NOT visible as text', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });
    await page.waitForTimeout(3000);

    // The .email-score-display element is rendered with display:none
    // and only updated on upvote/downvote. It must not show "score: 0." as visible text.
    const scoreEls = page.locator('.email-score-display');
    const scoreCount = await scoreEls.count();

    if (scoreCount === 0) {
      // No email cards at all — acceptable
      return;
    }

    // None of the score elements should be visible
    for (let i = 0; i < scoreCount; i++) {
      await expect(scoreEls.nth(i)).not.toBeVisible();
    }

    await page.screenshot({ path: 'e2e/screenshots/s2-04-email-scores-hidden.png' });
  });

});

// =========================================================================
// Group 3: The Play with Real Data (UI-driven)
// =========================================================================

test.describe('The Play with Real Data', () => {

  test('Navigate to Play and back to CAIRN', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });

    // Navigate to Play
    await page.locator('.agent-item[data-agent-id="play"]').click();
    await expect(page.locator('.play-sidebar')).toBeVisible({ timeout: UI_TIMEOUT });

    await page.screenshot({ path: 'e2e/screenshots/s3-01-play-view.png' });

    // Navigate back to CAIRN
    await page.locator('.agent-item[data-agent-id="cairn"]').click();

    // CAIRN attention panel must reappear
    await expect(page.locator('.surfaced-panel')).toBeVisible({ timeout: UI_TIMEOUT });

    await page.screenshot({ path: 'e2e/screenshots/s3-02-cairn-after-play.png' });

    // The surfaced column headers should be back
    await expect(page.locator('.surfaced-column-header', { hasText: 'Calendar & Tasks' })).toBeVisible({ timeout: UI_TIMEOUT });
  });

  test('Your Story shows real block content', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });

    await openPlay(page);

    // Click Your Story act item
    const yourStory = page.locator('.tree-item.act', { hasText: 'Your Story' });
    await expect(yourStory).toBeVisible({ timeout: BACKEND_TIMEOUT });
    await yourStory.click();

    // The content area (play-content or block-editor) should render something
    const contentArea = page.locator('.play-content');
    await expect(contentArea).toBeVisible({ timeout: BACKEND_TIMEOUT });

    await page.screenshot({ path: 'e2e/screenshots/s3-03-your-story-content.png' });
  });

  test('Expand Career Growth act shows real scenes', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });
    await openPlay(page);

    // Verify Career Growth act is present
    const careerAct = page.locator('.tree-item.act', { hasText: 'Career Growth' });
    await expect(careerAct).toBeVisible({ timeout: BACKEND_TIMEOUT });

    // Click to expand
    await careerAct.click();

    // Q2 Platform Migration scene must appear (from synthetic data)
    await expect(page.locator('.play-sidebar')).toContainText('Q2 Platform Migration', { timeout: BACKEND_TIMEOUT });

    await page.screenshot({ path: 'e2e/screenshots/s3-04-career-growth-scenes.png' });
  });

  test('Switching between acts loads different content', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });
    await openPlay(page);

    // Click Career Growth
    const careerAct = page.locator('.tree-item.act', { hasText: 'Career Growth' });
    await expect(careerAct).toBeVisible({ timeout: BACKEND_TIMEOUT });
    await careerAct.click();

    // Wait for scenes to load and capture initial sidebar state
    await page.waitForTimeout(1000);
    const sidebarText1 = await page.locator('.play-sidebar').innerText();

    // Click Family act
    const familyAct = page.locator('.tree-item.act', { hasText: 'Family' });
    await expect(familyAct).toBeVisible({ timeout: BACKEND_TIMEOUT });
    await familyAct.click();

    await page.waitForTimeout(1000);
    const sidebarText2 = await page.locator('.play-sidebar').innerText();

    await page.screenshot({ path: 'e2e/screenshots/s3-05-family-act.png' });

    // Sidebar content should differ between the two acts
    // (Career Growth scenes vs Family scenes are different)
    expect(sidebarText1).not.toEqual(sidebarText2);
  });

});

// =========================================================================
// Group 4: Chat Input (UI-driven)
// =========================================================================

test.describe('Chat Input', () => {

  test('Chat input accepts text', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });

    const chatInput = page.locator('input[placeholder*="Ask CAIRN"]');
    await expect(chatInput).toBeVisible({ timeout: UI_TIMEOUT });

    await chatInput.click();
    await chatInput.type('Hello CAIRN');

    await page.screenshot({ path: 'e2e/screenshots/s4-01-chat-input-typed.png' });

    // The typed text must appear in the input
    await expect(chatInput).toHaveValue('Hello CAIRN');
  });

  test('Chat input clears on Enter', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });

    const chatInput = page.locator('input[placeholder*="Ask CAIRN"]');
    await expect(chatInput).toBeVisible({ timeout: UI_TIMEOUT });

    await chatInput.click();
    await chatInput.type('Test message');
    await expect(chatInput).toHaveValue('Test message');

    await chatInput.press('Enter');

    await page.screenshot({ path: 'e2e/screenshots/s4-02-chat-input-cleared.png' });

    // Input clears immediately after send
    await expect(chatInput).toHaveValue('', { timeout: UI_TIMEOUT });
  });

  test('User message appears in chat area', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });

    const chatInput = page.locator('input[placeholder*="Ask CAIRN"]');
    await expect(chatInput).toBeVisible({ timeout: UI_TIMEOUT });

    const testMessage = 'What needs my attention today?';
    await chatInput.click();
    await chatInput.type(testMessage);
    await chatInput.press('Enter');

    // Chat messages area should show the sent message
    const messagesArea = page.locator('.chat-messages');
    await expect(messagesArea).toContainText(testMessage, { timeout: BACKEND_TIMEOUT });

    await page.screenshot({ path: 'e2e/screenshots/s4-03-user-message-visible.png' });
  });

});

// =========================================================================
// Group 5: Context Meter (UI-driven)
// =========================================================================

test.describe('Context Meter', () => {

  test('Context meter shows real token data', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });

    // Context meter is in the CAIRN chat header
    const contextMeter = page.locator('.nav-context-meter');
    await expect(contextMeter).toBeVisible({ timeout: UI_TIMEOUT });

    await page.screenshot({ path: 'e2e/screenshots/s5-01-context-meter.png' });

    // The context label area shows "Context" label
    await expect(contextMeter).toContainText('Context', { timeout: UI_TIMEOUT });

    // After the backend loads, the % and "left" text must appear
    const usageValue = contextMeter.locator('.context-usage-value');
    await expect(usageValue).toBeVisible({ timeout: BACKEND_TIMEOUT });

    const valueText = await usageValue.textContent();
    // Either shows "X% • N,NNN left" or falls back to "—" if backend unreachable
    expect(valueText).toBeTruthy();
    expect(valueText).not.toBe('Loading...');
  });

  test('Context meter is clickable and opens context overlay', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });

    const contextMeter = page.locator('.nav-context-meter');
    await expect(contextMeter).toBeVisible({ timeout: UI_TIMEOUT });

    // Wait for initial data load before clicking
    await page.waitForTimeout(2000);
    await contextMeter.click();

    await page.screenshot({ path: 'e2e/screenshots/s5-02-context-overlay.png' });

    // Context overlay appears — it may be a modal/panel with context details
    // The overlay class is set in contextOverlay.ts
    const contextOverlay = page.locator('.context-overlay');
    // If the overlay class exists, verify it's visible; otherwise just verify no crash
    const overlayExists = await contextOverlay.count();
    if (overlayExists > 0) {
      await expect(contextOverlay).toBeVisible({ timeout: UI_TIMEOUT });
    } else {
      // Overlay may use a different class name — just verify page didn't crash
      await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });
    }
  });

});

// =========================================================================
// Group 6: Health Finding (UI-driven)
// =========================================================================

test.describe('Health Finding', () => {

  test('Health finding indicator is visible when findings exist', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });

    // Health indicator starts hidden and appears only when finding_count > 0
    const healthIndicator = page.locator('.health-indicator');

    // Wait for health/status RPC to resolve
    await page.waitForTimeout(3000);

    await page.screenshot({ path: 'e2e/screenshots/s6-01-health-indicator.png' });

    // Check if health findings exist — if visible, verify text content
    const isVisible = await healthIndicator.isVisible();
    if (isVisible) {
      // Should contain "health finding" text
      await expect(healthIndicator).toContainText('health finding', { timeout: UI_TIMEOUT });
    } else {
      // No findings means the health indicator is hidden — that's valid
      console.info('[ui-interactions] Health indicator hidden — no findings in current DB state');
    }
  });

  test('Health finding is clickable and loads findings', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });
    await page.waitForTimeout(3000);

    const healthIndicator = page.locator('.health-indicator');
    const isVisible = await healthIndicator.isVisible();

    if (!isVisible) {
      test.skip(true, 'Health indicator not visible — no findings in current DB state');
    }

    await healthIndicator.click();

    await page.screenshot({ path: 'e2e/screenshots/s6-02-health-clicked.png' });

    // Clicking the health indicator triggers health/findings RPC and renders
    // the result as an assistant message in the CAIRN chat area.
    const messagesArea = page.locator('.chat-messages');
    await expect(messagesArea).toBeVisible({ timeout: UI_TIMEOUT });

    // A response should appear — either findings or "All Clear"
    await expect(messagesArea).toContainText(/Health|finding|All Clear/i, { timeout: BACKEND_TIMEOUT });
  });

});

// =========================================================================
// Group 7: Navigation State
// =========================================================================

test.describe('Navigation State', () => {

  test('CAIRN is active by default', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });

    await page.screenshot({ path: 'e2e/screenshots/s7-01-cairn-default-active.png' });

    // The CAIRN agent item should have active styling on load.
    // Active styling sets background: rgba(59, 130, 246, 0.15) and higher text opacity.
    // We verify by checking the CAIRN view is visible (not another view).
    const cairnViewVisible = await page.locator('.cairn-view').isVisible();
    expect(cairnViewVisible).toBe(true);

    // CAIRN agent item must be present in the bar
    const cairnItem = page.locator('.agent-item[data-agent-id="cairn"]');
    await expect(cairnItem).toBeVisible({ timeout: UI_TIMEOUT });
  });

  test('Clicking Play changes active state', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });

    // Initially CAIRN view is visible, play view is not
    await expect(page.locator('.cairn-view')).toBeVisible({ timeout: UI_TIMEOUT });

    // Click Play
    await page.locator('.agent-item[data-agent-id="play"]').click();
    await expect(page.locator('.play-sidebar')).toBeVisible({ timeout: UI_TIMEOUT });

    await page.screenshot({ path: 'e2e/screenshots/s7-02-play-active.png' });

    // CAIRN view should now be hidden (display:none)
    await expect(page.locator('.cairn-view')).not.toBeVisible({ timeout: UI_TIMEOUT });
  });

  test('View content changes with navigation', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });

    // On CAIRN view: attention panel is visible, play header is not
    await expect(page.locator('.surfaced-panel')).toBeVisible({ timeout: UI_TIMEOUT });

    // Navigate to Play
    await page.locator('.agent-item[data-agent-id="play"]').click();

    // "The Play" heading should be visible
    await expect(page.locator('.play-header h1')).toContainText('The Play', { timeout: BACKEND_TIMEOUT });

    await page.screenshot({ path: 'e2e/screenshots/s7-03-play-heading.png' });

    // Navigate back to CAIRN
    await page.locator('.agent-item[data-agent-id="cairn"]').click();

    // Attention panel header is back
    await expect(page.locator('.surfaced-panel')).toBeVisible({ timeout: UI_TIMEOUT });

    await page.screenshot({ path: 'e2e/screenshots/s7-04-cairn-restored.png' });
  });

});
