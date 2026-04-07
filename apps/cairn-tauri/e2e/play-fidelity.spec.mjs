/**
 * Play Overlay State-Fidelity Tests
 *
 * Verifies that the Play overlay UI accurately reflects database state.
 * Every test queries the real backend via RPC and compares against what the
 * UI renders — no hardcoded assumptions about IDs or titles except for the
 * permanent synthetic-data fixtures (Career Growth, Your Story, etc.).
 *
 * Prerequisites:
 *   1. Vite dev server running on port 1420:   npm run dev
 *   2. Cairn backend running on port 8010:     python -m cairn.app
 *   3. Synthetic data loaded:                  python scripts/load_synthetic_data.py
 *
 * Test data naming convention:
 *   All acts and scenes created by these tests are prefixed with "_e2e_fidelity_"
 *   To purge stale test data manually:
 *     sqlite3 ~/.talkingrock/talkingrock.db \
 *       "DELETE FROM scenes WHERE title LIKE '_e2e_fidelity_%'; \
 *        DELETE FROM acts WHERE title LIKE '_e2e_fidelity_%';"
 *
 * DOM structure reference (from playOverlay.ts):
 *   .play-sidebar
 *     .tree-item.act[.selected][.active]  — one per act
 *       .tree-expand                      — expand toggle (▶/▼)
 *       (actLabel span)                   — act title text
 *       .act-color-btn                    — color swatch (always present, defaults to purple)
 *     .tree-item.scene                    — scenes under expanded+active act only
 *       .tree-icon                        — bullet/checkmark
 *       (sceneLabel span)                 — scene title
 *       .scene-stage.scene-stage-<stage>  — badge (only when stage != 'planning')
 *     .tree-new-btn                       — "+ New Act"
 *     .tree-new-btn.scene-level           — "+ New Scene" (under expanded act)
 *   .play-content
 *     .play-title-input                   — editable title for selected item
 *
 * Key behaviors that affect test design:
 *   - Scenes only render in sidebar when their act is BOTH expanded AND active.
 *   - Clicking an act sets it active AND expands it.
 *   - "Archived Conversations" is skipped in the sidebar render loop entirely.
 *   - "Your Story" is rendered as a hardcoded first item, not from actsCache loop.
 *   - .active class marks the act whose act_id === state.activeActId.
 *   - Planning-stage scenes have no badge; all other stages show a badge.
 *   - .act-color-btn always exists; it falls back to default purple when act.color is null.
 */

import { test, expect } from '@playwright/test';
import { getProxyScript } from './tauri-proxy.mjs';

const BASE_URL = 'http://localhost:8010/rpc/dev';
const APP_URL = 'http://localhost:1420';

const BACKEND_TIMEOUT = 15000;
const UI_TIMEOUT = 10000;

// Known fixture IDs from synthetic data
const CAREER_ACT_ID = 'act-e8623a0da3ca';
const FAMILY_ACT_ID = 'act-02634cb2ca1c';

// First known Career Growth scene title — used to wait for scene loading
const CAREER_FIRST_SCENE = 'Q2 Platform Migration';

// -------------------------------------------------------------------------
// Color helpers
// -------------------------------------------------------------------------

/**
 * Convert hex color string (#RRGGBB) to "rgb(r, g, b)" string.
 * The browser normalizes inline background colors to rgb() format.
 */
function hexToRgb(hex) {
  const clean = hex.replace('#', '');
  const r = parseInt(clean.substring(0, 2), 16);
  const g = parseInt(clean.substring(2, 4), 16);
  const b = parseInt(clean.substring(4, 6), 16);
  return `rgb(${r}, ${g}, ${b})`;
}

// -------------------------------------------------------------------------
// Helpers
// -------------------------------------------------------------------------

async function rpc(request, method, params = {}) {
  const resp = await request.post(BASE_URL, {
    data: { jsonrpc: '2.0', id: Date.now(), method, params },
    headers: { 'Content-Type': 'application/json' },
  });
  const body = await resp.json();
  if (body.error) {
    throw new Error(`RPC ${method} failed: ${JSON.stringify(body.error)}`);
  }
  return body.result;
}

async function loadApp(page) {
  await page.goto(APP_URL);
  await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });
}

async function openPlay(page) {
  await page.locator('.agent-item[data-agent-id="play"]').click();
  await expect(page.locator('.play-sidebar')).toBeVisible({ timeout: UI_TIMEOUT });
  // Wait for act items to render after async data load
  await expect(page.locator('.tree-item.act').first()).toBeVisible({ timeout: BACKEND_TIMEOUT });
}

// -------------------------------------------------------------------------
// Inject proxy before every test
// -------------------------------------------------------------------------

test.beforeEach(async ({ page }) => {
  await page.addInitScript({ content: getProxyScript() });
});

// =========================================================================
// Group 1: Act Listing Fidelity
// =========================================================================

test.describe('Act Listing Fidelity', () => {

  // Establish a stable known active act before each test.
  test.beforeEach(async ({ request }) => {
    await rpc(request, 'play/acts/set_active', { act_id: FAMILY_ACT_ID });
  });

  test('all non-your-story db acts visible in sidebar', async ({ page, request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const actsResult = await rpc(request, 'play/acts/list', {});
    // "your-story" is rendered separately as first item; "archived-conversations" is
    // filtered out by the backend. All remaining acts are rendered in the loop.
    const loopActs = actsResult.acts.filter(a => a.act_id !== 'your-story');

    await loadApp(page);
    await openPlay(page);

    const sidebar = page.locator('.play-sidebar');
    for (const act of loopActs) {
      await expect(sidebar).toContainText(act.title, { timeout: BACKEND_TIMEOUT });
    }

    // "Your Story" appears as the hardcoded first item
    await expect(sidebar).toContainText('Your Story', { timeout: BACKEND_TIMEOUT });
  });

  test('act color buttons reflect db colors', async ({ page, request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const actsResult = await rpc(request, 'play/acts/list', {});
    const actsWithColors = actsResult.acts.filter(
      a => a.color && a.act_id !== 'your-story' && a.act_id !== 'archived-conversations'
    );
    expect(actsWithColors.length).toBeGreaterThan(0);

    await loadApp(page);
    await openPlay(page);

    await page.screenshot({ path: 'test-results/act-colors-initial.png' });

    for (const act of actsWithColors) {
      const actItem = page.locator('.tree-item.act', { hasText: act.title });
      await expect(actItem).toBeVisible({ timeout: UI_TIMEOUT });

      const colorBtn = actItem.locator('.act-color-btn');
      await expect(colorBtn).toBeVisible({ timeout: UI_TIMEOUT });

      const bgColor = await colorBtn.evaluate(el => el.style.background || el.style.backgroundColor);
      // Browser normalizes hex inline styles to rgb(...) format
      const expectedRgb = hexToRgb(act.color);
      expect(bgColor.toLowerCase()).toBe(expectedRgb.toLowerCase());
    }
  });

  test('active act has active css class in sidebar', async ({ page, request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const actsResult = await rpc(request, 'play/acts/list', {});
    const activeActId = actsResult.active_act_id;
    expect(activeActId).toBeTruthy();

    const activeAct = actsResult.acts.find(a => a.act_id === activeActId);
    expect(activeAct).toBeTruthy();

    await loadApp(page);
    await openPlay(page);

    await page.screenshot({ path: 'test-results/active-act-initial.png' });

    // The active act's tree-item should have the 'active' class
    const activeActItem = page.locator('.tree-item.act.active');
    await expect(activeActItem).toBeVisible({ timeout: UI_TIMEOUT });
    await expect(activeActItem).toContainText(activeAct.title, { timeout: UI_TIMEOUT });
  });

  test('your story is always the first tree item act in sidebar', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await loadApp(page);
    await openPlay(page);

    const firstActItem = page.locator('.tree-item.act').first();
    await expect(firstActItem).toBeVisible({ timeout: UI_TIMEOUT });
    await expect(firstActItem).toContainText('Your Story', { timeout: UI_TIMEOUT });
  });

  test('all expected user acts render as tree items', async ({ page, request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const actsResult = await rpc(request, 'play/acts/list', {});
    // Sidebar loop renders all acts except 'your-story' (shown as hardcoded first item).
    // 'archived-conversations' is now filtered by the backend.
    const loopActs = actsResult.acts.filter(a => a.act_id !== 'your-story');
    expect(loopActs.length).toBeGreaterThanOrEqual(2);

    await loadApp(page);
    await openPlay(page);

    const actItems = page.locator('.tree-item.act');
    const count = await actItems.count();
    // count = loopActs.length (from the for-loop) + 1 (hardcoded "Your Story")
    expect(count).toBe(loopActs.length + 1);
  });

});

// =========================================================================
// Group 2: Scene Listing & Stage Fidelity
// =========================================================================

test.describe('Scene Listing and Stage Fidelity', () => {

  // Ensure Career Growth is NOT the active act before each test in this group.
  // If it were active and a test clicked it, the toggle would deselect it instead
  // of expanding it and loading scenes.
  test.beforeEach(async ({ request }) => {
    const actsResult = await rpc(request, 'play/acts/list', {});
    if (actsResult.active_act_id === CAREER_ACT_ID) {
      await rpc(request, 'play/acts/set_active', { act_id: FAMILY_ACT_ID });
    }
  });

  test('scenes visible after expanding career growth act', async ({ page, request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const scenesResult = await rpc(request, 'play/scenes/list', { act_id: CAREER_ACT_ID });
    const scenes = scenesResult.scenes;
    expect(scenes.length).toBeGreaterThanOrEqual(3);

    await loadApp(page);
    await openPlay(page);

    const careerAct = page.locator('.tree-item.act', { hasText: 'Career Growth' });
    await careerAct.click();

    // Wait for first known scene to confirm async load completed
    const sidebar = page.locator('.play-sidebar');
    await expect(sidebar).toContainText(CAREER_FIRST_SCENE, { timeout: BACKEND_TIMEOUT });

    for (const scene of scenes) {
      await expect(sidebar).toContainText(scene.title, { timeout: BACKEND_TIMEOUT });
    }
  });

  test('non-planning scene stages render correct badge css class', async ({ page, request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const scenesResult = await rpc(request, 'play/scenes/list', { act_id: CAREER_ACT_ID });
    const nonPlanningScenes = scenesResult.scenes.filter(s => s.stage !== 'planning');
    expect(nonPlanningScenes.length).toBeGreaterThan(0);

    await loadApp(page);
    await openPlay(page);

    const careerAct = page.locator('.tree-item.act', { hasText: 'Career Growth' });
    await careerAct.click();

    // Wait for scenes to load
    await expect(page.locator('.play-sidebar')).toContainText(CAREER_FIRST_SCENE, { timeout: BACKEND_TIMEOUT });

    await page.screenshot({ path: 'test-results/scene-stages.png' });

    for (const scene of nonPlanningScenes) {
      const sceneItem = page.locator('.tree-item.scene', { hasText: scene.title });
      await expect(sceneItem).toBeVisible({ timeout: UI_TIMEOUT });
      const stageBadge = sceneItem.locator(`.scene-stage-${scene.stage}`);
      await expect(stageBadge).toBeVisible({ timeout: UI_TIMEOUT });
    }
  });

  test('planning stage scenes have no stage badge', async ({ page, request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const scenesResult = await rpc(request, 'play/scenes/list', { act_id: CAREER_ACT_ID });
    const planningScenes = scenesResult.scenes.filter(s => s.stage === 'planning');
    expect(planningScenes.length).toBeGreaterThan(0);

    await loadApp(page);
    await openPlay(page);

    const careerAct = page.locator('.tree-item.act', { hasText: 'Career Growth' });
    await careerAct.click();
    // Wait for scenes to load
    await expect(page.locator('.play-sidebar')).toContainText(CAREER_FIRST_SCENE, { timeout: BACKEND_TIMEOUT });

    for (const scene of planningScenes) {
      const sceneItem = page.locator('.tree-item.scene', { hasText: scene.title });
      await expect(sceneItem).toBeVisible({ timeout: UI_TIMEOUT });
      const stageBadge = sceneItem.locator('.scene-stage');
      await expect(stageBadge).toHaveCount(0);
    }
  });

  test('scene titles match db titles exactly', async ({ page, request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const scenesResult = await rpc(request, 'play/scenes/list', { act_id: CAREER_ACT_ID });
    const scenes = scenesResult.scenes;

    await loadApp(page);
    await openPlay(page);

    const careerAct = page.locator('.tree-item.act', { hasText: 'Career Growth' });
    await careerAct.click();
    // Wait for scenes to load before checking titles
    await expect(page.locator('.play-sidebar')).toContainText(CAREER_FIRST_SCENE, { timeout: BACKEND_TIMEOUT });

    for (const scene of scenes) {
      // Each scene title should appear as text content in the sidebar
      const sceneItem = page.locator('.tree-item.scene', { hasText: scene.title });
      await expect(sceneItem).toBeVisible({ timeout: UI_TIMEOUT });
    }
  });

  test('no phantom scenes in sidebar beyond what db returns', async ({ page, request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const scenesResult = await rpc(request, 'play/scenes/list', { act_id: CAREER_ACT_ID });
    const expectedCount = scenesResult.scenes.length;

    await loadApp(page);
    await openPlay(page);

    const careerAct = page.locator('.tree-item.act', { hasText: 'Career Growth' });
    await careerAct.click();
    // Wait for scenes to load
    await expect(page.locator('.play-sidebar')).toContainText(CAREER_FIRST_SCENE, { timeout: BACKEND_TIMEOUT });

    // Count scene-level tree items. The "Memories" item also has tree-item.scene class,
    // so we add 1 to account for it.
    const sceneItems = page.locator('.play-sidebar .tree-item.scene');
    const count = await sceneItems.count();
    // count = expectedCount scenes + 1 Memories nav item
    expect(count).toBe(expectedCount + 1);
  });

});

// =========================================================================
// Group 3: Write Round-Trip Fidelity
// =========================================================================

test.describe('Write Round-Trip Fidelity', () => {

  let createdSceneIds = [];
  let createdActIds = [];
  let originalActiveActId = null;

  // Ensure Career Growth is NOT active before each test so clicking it
  // activates rather than deselects (toggle behavior).
  test.beforeEach(async ({ request }) => {
    const actsResult = await rpc(request, 'play/acts/list', {});
    if (actsResult.active_act_id === CAREER_ACT_ID) {
      await rpc(request, 'play/acts/set_active', { act_id: FAMILY_ACT_ID });
    }
  });

  test.afterEach(async ({ request }) => {
    for (const sceneId of createdSceneIds) {
      try {
        await rpc(request, 'play/scenes/delete', { scene_id: sceneId, act_id: '_cleanup' });
      } catch (_) {}
    }
    for (const actId of createdActIds) {
      try {
        await rpc(request, 'play/acts/delete', { act_id: actId });
      } catch (_) {}
    }
    // Restore original active act if it was changed
    if (originalActiveActId) {
      try {
        await rpc(request, 'play/acts/set_active', { act_id: originalActiveActId });
      } catch (_) {}
      originalActiveActId = null;
    }
    createdSceneIds = [];
    createdActIds = [];
  });

  test('act created via rpc appears in ui after reload', async ({ page, request }) => {
    test.setTimeout(BACKEND_TIMEOUT * 2);

    const actName = '_e2e_fidelity_Act_' + Date.now();
    const createResult = await rpc(request, 'play/acts/create', { title: actName });
    expect(createResult.created_act_id).toBeTruthy();
    createdActIds.push(createResult.created_act_id);

    await loadApp(page);
    await openPlay(page);

    await expect(page.locator('.play-sidebar')).toContainText(actName, {
      timeout: BACKEND_TIMEOUT,
    });
  });

  test('scene created via rpc appears in ui after reload', async ({ page, request }) => {
    test.setTimeout(BACKEND_TIMEOUT * 2);

    const sceneName = '_e2e_fidelity_Scene_' + Date.now();
    const createResult = await rpc(request, 'play/scenes/create', {
      act_id: CAREER_ACT_ID,
      title: sceneName,
      stage: 'planning',
    });
    expect(createResult.created_scene_id).toBeTruthy();
    createdSceneIds.push(createResult.created_scene_id);

    await loadApp(page);
    await openPlay(page);

    const careerAct = page.locator('.tree-item.act', { hasText: 'Career Growth' });
    await careerAct.click();
    // Wait for known scenes to appear before checking for the new scene
    await expect(page.locator('.play-sidebar')).toContainText(CAREER_FIRST_SCENE, {
      timeout: BACKEND_TIMEOUT,
    });

    await expect(page.locator('.play-sidebar')).toContainText(sceneName, {
      timeout: BACKEND_TIMEOUT,
    });
  });

  test('act title updated via rpc reflected in ui after reload', async ({ page, request }) => {
    test.setTimeout(BACKEND_TIMEOUT * 2);

    const originalTitle = '_e2e_fidelity_TitleOrig_' + Date.now();
    const updatedTitle = '_e2e_fidelity_TitleNew_' + Date.now();

    const createResult = await rpc(request, 'play/acts/create', { title: originalTitle });
    const actId = createResult.created_act_id;
    createdActIds.push(actId);

    await rpc(request, 'play/acts/update', { act_id: actId, title: updatedTitle });

    await loadApp(page);
    await openPlay(page);

    const sidebar = page.locator('.play-sidebar');
    await expect(sidebar).toContainText(updatedTitle, { timeout: BACKEND_TIMEOUT });
    const text = await sidebar.textContent();
    expect(text).not.toContain(originalTitle);
  });

  test('scene updated to in_progress via rpc shows stage badge in ui', async ({ page, request }) => {
    test.setTimeout(BACKEND_TIMEOUT * 2);

    const sceneName = '_e2e_fidelity_Stage_' + Date.now();
    const createResult = await rpc(request, 'play/scenes/create', {
      act_id: CAREER_ACT_ID,
      title: sceneName,
      stage: 'planning',
    });
    const sceneId = createResult.created_scene_id;
    createdSceneIds.push(sceneId);

    await rpc(request, 'play/scenes/update', {
      act_id: CAREER_ACT_ID,
      scene_id: sceneId,
      stage: 'in_progress',
    });

    await loadApp(page);
    await openPlay(page);

    const careerAct = page.locator('.tree-item.act', { hasText: 'Career Growth' });
    await careerAct.click();
    // Wait for known scenes to appear first
    await expect(page.locator('.play-sidebar')).toContainText(CAREER_FIRST_SCENE, {
      timeout: BACKEND_TIMEOUT,
    });

    await page.screenshot({ path: 'test-results/scene-stage-in-progress.png' });

    const sceneItem = page.locator('.tree-item.scene', { hasText: sceneName });
    await expect(sceneItem).toBeVisible({ timeout: BACKEND_TIMEOUT });
    await expect(sceneItem.locator('.scene-stage-in_progress')).toBeVisible({ timeout: UI_TIMEOUT });
  });

  test('act deleted via rpc is removed from ui after reload', async ({ page, request }) => {
    test.setTimeout(BACKEND_TIMEOUT * 2);

    const actName = '_e2e_fidelity_Delete_' + Date.now();
    const createResult = await rpc(request, 'play/acts/create', { title: actName });
    const actId = createResult.created_act_id;

    await loadApp(page);
    await openPlay(page);
    await expect(page.locator('.play-sidebar')).toContainText(actName, {
      timeout: BACKEND_TIMEOUT,
    });

    await rpc(request, 'play/acts/delete', { act_id: actId });
    // Act is now deleted — don't add to cleanup list

    await loadApp(page);
    await openPlay(page);

    const sidebar = page.locator('.play-sidebar');
    await expect(sidebar).toBeVisible({ timeout: UI_TIMEOUT });
    const text = await sidebar.textContent();
    expect(text).not.toContain(actName);
  });

  test('set active act via rpc changes active indicator in ui', async ({ page, request }) => {
    test.setTimeout(BACKEND_TIMEOUT * 2);

    // Capture original active act so we can restore it in afterEach
    const actsResult = await rpc(request, 'play/acts/list', {});
    originalActiveActId = actsResult.active_act_id;

    // Find an act that is NOT currently active to switch to
    const inactiveAct = actsResult.acts.find(
      a => a.act_id !== originalActiveActId
        && a.act_id !== 'your-story'
        && a.act_id !== 'archived-conversations'
    );
    expect(inactiveAct).toBeTruthy();

    await rpc(request, 'play/acts/set_active', { act_id: inactiveAct.act_id });

    await loadApp(page);
    await openPlay(page);

    await page.screenshot({ path: 'test-results/active-act-switched.png' });

    const activeActItem = page.locator('.tree-item.act.active');
    await expect(activeActItem).toBeVisible({ timeout: UI_TIMEOUT });
    await expect(activeActItem).toContainText(inactiveAct.title, { timeout: UI_TIMEOUT });
  });

});

// =========================================================================
// Group 4: Content Editing Fidelity
// =========================================================================

test.describe('Content Editing Fidelity', () => {

  // Ensure Career Growth is NOT active before each test so clicking it
  // activates (rather than deselects via toggle behavior).
  test.beforeEach(async ({ request }) => {
    const actsResult = await rpc(request, 'play/acts/list', {});
    if (actsResult.active_act_id === CAREER_ACT_ID) {
      await rpc(request, 'play/acts/set_active', { act_id: FAMILY_ACT_ID });
    }
  });

  test('your story content area is visible when your story selected', async ({ page }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await loadApp(page);
    await openPlay(page);

    const yourStory = page.locator('.tree-item.act', { hasText: 'Your Story' });
    await yourStory.click();
    await page.waitForTimeout(300);

    await page.screenshot({ path: 'test-results/your-story-content.png' });

    // The content area (block editor, editor wrap, or play-editor-wrap) should be visible
    const contentArea = page.locator('.play-content .play-editor-wrap, .play-content [class*="editor"]');
    await expect(contentArea.first()).toBeVisible({ timeout: BACKEND_TIMEOUT });
  });

  test('act title input shows act title when act selected', async ({ page, request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const actsResult = await rpc(request, 'play/acts/list', {});
    const careerAct = actsResult.acts.find(a => a.act_id === CAREER_ACT_ID);
    expect(careerAct).toBeTruthy();

    await loadApp(page);
    await openPlay(page);

    const careerActItem = page.locator('.tree-item.act', { hasText: 'Career Growth' });
    await careerActItem.click();
    // Wait for scenes to load (confirms async refreshData completed)
    await expect(page.locator('.play-sidebar')).toContainText(CAREER_FIRST_SCENE, { timeout: BACKEND_TIMEOUT });

    await page.screenshot({ path: 'test-results/act-title-input.png' });

    const titleInput = page.locator('.play-title-input');
    await expect(titleInput).toBeVisible({ timeout: UI_TIMEOUT });
    const value = await titleInput.inputValue();
    expect(value).toBe(careerAct.title);
  });

  test('scene title shown in title input when scene selected', async ({ page, request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const scenesResult = await rpc(request, 'play/scenes/list', { act_id: CAREER_ACT_ID });
    const firstScene = scenesResult.scenes[0];
    expect(firstScene).toBeTruthy();

    await loadApp(page);
    await openPlay(page);

    const careerAct = page.locator('.tree-item.act', { hasText: 'Career Growth' });
    await careerAct.click();
    // Wait for scenes to load
    await expect(page.locator('.play-sidebar')).toContainText(CAREER_FIRST_SCENE, { timeout: BACKEND_TIMEOUT });

    const sceneItem = page.locator('.tree-item.scene', { hasText: firstScene.title });
    await sceneItem.click();
    await page.waitForTimeout(300);

    await page.screenshot({ path: 'test-results/scene-title-input.png' });

    const titleInput = page.locator('.play-title-input');
    await expect(titleInput).toBeVisible({ timeout: UI_TIMEOUT });
    const value = await titleInput.inputValue();
    expect(value).toBe(firstScene.title);
  });

  test('play content area is visible when scene selected', async ({ page, request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const scenesResult = await rpc(request, 'play/scenes/list', { act_id: CAREER_ACT_ID });
    const firstScene = scenesResult.scenes[0];
    expect(firstScene).toBeTruthy();

    await loadApp(page);
    await openPlay(page);

    const careerAct = page.locator('.tree-item.act', { hasText: 'Career Growth' });
    await careerAct.click();
    // Wait for scenes to load
    await expect(page.locator('.play-sidebar')).toContainText(CAREER_FIRST_SCENE, { timeout: BACKEND_TIMEOUT });

    const sceneItem = page.locator('.tree-item.scene', { hasText: firstScene.title });
    await sceneItem.click();
    await page.waitForTimeout(300);

    await page.screenshot({ path: 'test-results/scene-content-area.png' });

    const contentArea = page.locator('.play-content .play-editor-wrap, .play-content [class*="editor"]');
    await expect(contentArea.first()).toBeVisible({ timeout: BACKEND_TIMEOUT });
  });

});

// =========================================================================
// Group 5: Color Picker Fidelity
// =========================================================================

test.describe('Color Picker Fidelity', () => {

  let createdActIds = [];

  test.afterEach(async ({ request }) => {
    for (const actId of createdActIds) {
      try {
        await rpc(request, 'play/acts/delete', { act_id: actId });
      } catch (_) {}
    }
    createdActIds = [];
  });

  test('career growth color btn shows correct hex color', async ({ page, request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const actsResult = await rpc(request, 'play/acts/list', {});
    const careerAct = actsResult.acts.find(a => a.act_id === CAREER_ACT_ID);
    expect(careerAct).toBeTruthy();
    expect(careerAct.color).toBeTruthy();

    await loadApp(page);
    await openPlay(page);

    const actItem = page.locator('.tree-item.act', { hasText: 'Career Growth' });
    await expect(actItem).toBeVisible({ timeout: UI_TIMEOUT });

    const colorBtn = actItem.locator('.act-color-btn');
    await expect(colorBtn).toBeVisible({ timeout: UI_TIMEOUT });

    await page.screenshot({ path: 'test-results/career-growth-color.png' });

    const bgStyle = await colorBtn.evaluate(el => el.style.background || el.style.backgroundColor);
    // Browser normalizes hex inline styles to rgb(...) format
    const expectedRgb = hexToRgb(careerAct.color);
    expect(bgStyle.toLowerCase()).toBe(expectedRgb.toLowerCase());
  });

  test('acts without color have color btn with default purple color', async ({ page, request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const actsResult = await rpc(request, 'play/acts/list', {});
    // your-story has null color — it's the hardcoded first item; find user acts without color
    const noColorAct = actsResult.acts.find(
      a => !a.color && a.act_id !== 'your-story' && a.act_id !== 'archived-conversations'
    );

    if (!noColorAct) {
      // Create an act without a color to test with
      const actName = '_e2e_fidelity_NoColor_' + Date.now();
      const createResult = await rpc(request, 'play/acts/create', { title: actName });
      createdActIds.push(createResult.created_act_id);

      await loadApp(page);
      await openPlay(page);

      const actItem = page.locator('.tree-item.act', { hasText: actName });
      await expect(actItem).toBeVisible({ timeout: UI_TIMEOUT });

      const colorBtn = actItem.locator('.act-color-btn');
      await expect(colorBtn).toBeVisible({ timeout: UI_TIMEOUT });
      // Default is #8b5cf6 (purple) — browser normalizes to rgb(139, 92, 246)
      const bgStyle = await colorBtn.evaluate(el => el.style.background || el.style.backgroundColor);
      const expectedDefaultRgb = hexToRgb('#8b5cf6');
      expect(bgStyle.toLowerCase()).toBe(expectedDefaultRgb.toLowerCase());
    } else {
      await loadApp(page);
      await openPlay(page);

      const actItem = page.locator('.tree-item.act', { hasText: noColorAct.title });
      await expect(actItem).toBeVisible({ timeout: UI_TIMEOUT });

      const colorBtn = actItem.locator('.act-color-btn');
      await expect(colorBtn).toBeVisible({ timeout: UI_TIMEOUT });
      // Default is #8b5cf6 (purple) — browser normalizes to rgb(139, 92, 246)
      const bgStyle = await colorBtn.evaluate(el => el.style.background || el.style.backgroundColor);
      const expectedDefaultRgb = hexToRgb('#8b5cf6');
      expect(bgStyle.toLowerCase()).toBe(expectedDefaultRgb.toLowerCase());
    }
  });

  test('act color updated via rpc is reflected in color btn after reload', async ({ page, request }) => {
    test.setTimeout(BACKEND_TIMEOUT * 2);

    const actName = '_e2e_fidelity_Color_' + Date.now();
    const createResult = await rpc(request, 'play/acts/create', { title: actName });
    const actId = createResult.created_act_id;
    createdActIds.push(actId);

    const newColor = '#ff6600';
    await rpc(request, 'play/acts/update', { act_id: actId, color: newColor });

    // Verify DB now has the updated color
    const verifyResult = await rpc(request, 'play/acts/list', {});
    const updatedAct = verifyResult.acts.find(a => a.act_id === actId);
    expect(updatedAct).toBeTruthy();
    expect(updatedAct.color).toBe(newColor);

    await loadApp(page);
    await openPlay(page);

    await page.screenshot({ path: 'test-results/act-color-updated.png' });

    const actItem = page.locator('.tree-item.act', { hasText: actName });
    await expect(actItem).toBeVisible({ timeout: UI_TIMEOUT });

    const colorBtn = actItem.locator('.act-color-btn');
    await expect(colorBtn).toBeVisible({ timeout: UI_TIMEOUT });
    const bgStyle = await colorBtn.evaluate(el => el.style.background || el.style.backgroundColor);
    // Browser normalizes hex to rgb(...) format
    const expectedRgb = hexToRgb(newColor);
    expect(bgStyle.toLowerCase()).toBe(expectedRgb.toLowerCase());
  });

});
