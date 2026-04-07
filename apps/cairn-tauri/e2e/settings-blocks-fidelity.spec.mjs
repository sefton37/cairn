/**
 * Settings & Blocks Fidelity e2e test suite.
 *
 * Verifies that Settings overlay data and Blocks CRUD operations accurately
 * reflect DB state. Three test groups:
 *
 *   Group 1: Settings / Provider Fidelity — verify RPC endpoints that back
 *            the Settings overlay return accurate, correctly-shaped data.
 *
 *   Group 2: Blocks CRUD Fidelity — verify block operations persist to DB
 *            and tree/list queries reflect mutations correctly.
 *
 *   Group 3: Memory & Conversations via RPC — verify memory and context
 *            endpoints are reachable and return expected shapes.
 *
 * Prerequisites (same as real-data.spec.mjs):
 *   1. Vite dev server on port 1420:   npm run dev
 *   2. Cairn backend on port 8010:     python -m cairn.app
 *   3. Synthetic data loaded:          python scripts/load_synthetic_data.py
 *
 * Test data naming convention:
 *   All test-created entities are prefixed with "_e2e_fidelity_" so stale
 *   data can be identified and purged even if afterEach fails.
 *
 *   To purge stale test data manually:
 *     sqlite3 ~/.talkingrock/talkingrock.db \
 *       "DELETE FROM blocks WHERE act_id LIKE '_e2e_fidelity_%'; \
 *        DELETE FROM pages WHERE title LIKE '_e2e_fidelity_%';"
 */

import { test, expect } from '@playwright/test';
import { getProxyScript } from './tauri-proxy.mjs';

const BASE_URL = 'http://localhost:8010/rpc/dev';
const APP_URL = 'http://localhost:1420';

const BACKEND_TIMEOUT = 15000;
const UI_TIMEOUT = 10000;

// -------------------------------------------------------------------------
// Helpers
// -------------------------------------------------------------------------

/**
 * Send a raw JSON-RPC request directly to the backend.
 * Identical pattern to real-data.spec.mjs and real-data-extended.spec.mjs.
 */
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

/**
 * Navigate to the app and wait for the agent bar (signals buildUi() done).
 */
async function loadApp(page) {
  await page.goto(APP_URL);
  await expect(page.locator('.agent-bar')).toBeVisible({ timeout: UI_TIMEOUT });
}

/**
 * Resolve Career Growth act_id from backend. Used as anchor act for block tests.
 */
async function getCareerActId(request) {
  const actsResult = await rpc(request, 'play/acts/list', {});
  const act = actsResult.acts.find(a => a.title === 'Career Growth');
  if (!act) throw new Error('Career Growth act not found — is synthetic data loaded?');
  return act.act_id;
}

// -------------------------------------------------------------------------
// Inject proxy before every test
// -------------------------------------------------------------------------

test.beforeEach(async ({ page }) => {
  await page.addInitScript({ content: getProxyScript() });
});

// =========================================================================
// Group 1: Settings / Provider Fidelity
//
// These tests verify that the RPC endpoints backing the Settings overlay
// return accurate, correctly-shaped data. Settings navigation via the UI is
// attempted where practical; RPC-only verification is used as fallback for
// data shape assertions.
// =========================================================================

test.describe('Settings / Provider Fidelity', () => {

  test('ollama/status returns url, reachable flag, and model name', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'ollama/status', {});

    // The settings overlay reads these exact fields to populate the LLM tab.
    expect(result).toHaveProperty('url');
    expect(result).toHaveProperty('reachable');
    expect(result).toHaveProperty('model');

    // url must be a non-empty string (even if Ollama is unreachable).
    expect(typeof result.url).toBe('string');
    expect(result.url.length).toBeGreaterThan(0);

    // reachable is a boolean.
    expect(typeof result.reachable).toBe('boolean');

    // model must be a string (may be empty if not configured, but field present).
    expect(typeof result.model).toBe('string');
  });

  test('ollama/status model list is array when Ollama is reachable', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'ollama/status', {});

    // available_models is always an array (empty if unreachable).
    expect(result).toHaveProperty('available_models');
    expect(Array.isArray(result.available_models)).toBe(true);

    if (result.reachable) {
      // When reachable, at least one model should be listed.
      // This is a soft assertion — CI may not have Ollama running.
      if (result.available_models.length === 0) {
        console.warn('[fidelity] Ollama reachable but no models listed — no models pulled?');
      }
      // available_models_detailed is present and an array when reachable.
      expect(result).toHaveProperty('available_models_detailed');
      expect(Array.isArray(result.available_models_detailed)).toBe(true);
    }
  });

  test('safety/settings returns all required fields with correct types', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'safety/settings', {});

    // Fields the Safety tab in Settings overlay displays.
    // The handler returns the subset it tracks; max_sudo_escalations and
    // max_iterations live in separate safety/set_* endpoints, not in this response.
    expect(result).toHaveProperty('rate_limits');
    expect(result).toHaveProperty('max_command_length');
    expect(result).toHaveProperty('dangerous_pattern_count');
    expect(result).toHaveProperty('injection_pattern_count');
    expect(result).toHaveProperty('max_service_name_length');

    // Numeric types.
    expect(typeof result.max_command_length).toBe('number');
    expect(result.max_command_length).toBeGreaterThan(0);

    expect(typeof result.dangerous_pattern_count).toBe('number');
    expect(result.dangerous_pattern_count).toBeGreaterThan(0);

    expect(typeof result.injection_pattern_count).toBe('number');
    expect(result.injection_pattern_count).toBeGreaterThanOrEqual(0);

    // rate_limits is an object (map of named configs).
    expect(typeof result.rate_limits).toBe('object');
    expect(result.rate_limits).not.toBeNull();
  });

  test('providers/list returns Ollama as local provider', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'providers/list', {});

    // Required fields from ProvidersListResult interface in settingsOverlay.ts.
    expect(result).toHaveProperty('current_provider');
    expect(result).toHaveProperty('available_providers');
    expect(result).toHaveProperty('keyring_available');

    expect(Array.isArray(result.available_providers)).toBe(true);
    expect(result.available_providers.length).toBeGreaterThan(0);

    // Cairn is Ollama-only per project philosophy.
    const ollama = result.available_providers.find(p => p.id === 'ollama');
    expect(ollama).toBeTruthy();
    expect(ollama.is_local).toBe(true);
    expect(ollama.requires_api_key).toBe(false);

    // Ollama must be the current provider in an Ollama-only deployment.
    expect(result.current_provider).toBe('ollama');
  });

  test('health/status returns overall_severity and finding_count', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'health/status', {});

    expect(result).toHaveProperty('overall_severity');
    expect(result).toHaveProperty('finding_count');
    expect(result).toHaveProperty('unacknowledged_count');

    const validSeverities = ['healthy', 'info', 'warning', 'critical'];
    expect(validSeverities).toContain(result.overall_severity);

    expect(typeof result.finding_count).toBe('number');
    expect(result.finding_count).toBeGreaterThanOrEqual(0);

    expect(typeof result.unacknowledged_count).toBe('number');
    expect(result.unacknowledged_count).toBeGreaterThanOrEqual(0);
  });

  test('cairn/thunderbird/status returns graceful shape when Thunderbird absent', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'cairn/thunderbird/status', {});

    // Always present, regardless of whether Thunderbird is installed.
    expect(result).toHaveProperty('available');
    expect(typeof result.available).toBe('boolean');

    if (result.available) {
      // When Thunderbird is installed and accessible.
      expect(result).toHaveProperty('profile_path');
      expect(result).toHaveProperty('has_contacts');
      expect(result).toHaveProperty('has_calendar');
    } else {
      // When absent — the UI shows a "not configured" message.
      // The message field must be present so the UI can render it.
      expect(result).toHaveProperty('message');
      expect(typeof result.message).toBe('string');
      expect(result.message.length).toBeGreaterThan(0);
    }
  });

});

// =========================================================================
// Group 2: Blocks CRUD Fidelity
//
// Verify that block CRUD operations through the RPC layer correctly persist
// to the DB and that tree / list queries reflect those mutations.
//
// These are RPC-only tests: the block editor DOM is complex and its React
// component tree is outside the scope of fidelity testing. The value here
// is verifying that the HTTP transport and persistence layer work end-to-end.
// =========================================================================

test.describe('Blocks CRUD Fidelity', () => {
  // Track resources created during each test for cleanup.
  let createdBlockIds = [];
  let createdPageIds = [];
  let testActId = null;

  test.afterEach(async ({ request }) => {
    // Delete blocks first (before their parent pages).
    for (const blockId of createdBlockIds) {
      try {
        await rpc(request, 'blocks/delete', { block_id: blockId });
      } catch (_) {
        // best-effort
      }
    }
    createdBlockIds = [];

    // Delete pages.
    for (const pageId of createdPageIds) {
      try {
        await rpc(request, 'play/pages/delete', { page_id: pageId });
      } catch (_) {
        // best-effort
      }
    }
    createdPageIds = [];
    testActId = null;
  });

  /**
   * Create a page in Career Growth and return its ID.
   * Registers the page for cleanup.
   */
  async function createPage(request, suffix = '') {
    if (!testActId) {
      testActId = await getCareerActId(request);
    }
    const title = `_e2e_fidelity_Page_${suffix || Date.now()}`;
    const result = await rpc(request, 'play/pages/create', {
      act_id: testActId,
      title,
    });
    const pageId = result.created_page_id;
    createdPageIds.push(pageId);
    return pageId;
  }

  /**
   * Create a paragraph block and return its ID.
   * Registers the block for cleanup.
   * Note: span dicts use 'content' (not 'text') — that is what blocks_db reads.
   */
  async function createBlock(request, pageId, text = '_e2e_fidelity_ block') {
    if (!testActId) {
      testActId = await getCareerActId(request);
    }
    const result = await rpc(request, 'blocks/create', {
      type: 'paragraph',
      act_id: testActId,
      page_id: pageId,
      rich_text: [{ content: text }],
    });
    const blockId = result.block.id;
    createdBlockIds.push(blockId);
    return blockId;
  }

  test('create block via RPC then verify it appears in blocks/page/tree', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const pageId = await createPage(request);
    const blockId = await createBlock(request, pageId, '_e2e_fidelity_ tree-check block');

    // blocks/page/tree takes page_id (not act_id).
    const treeResult = await rpc(request, 'blocks/page/tree', { page_id: pageId });
    expect(treeResult).toHaveProperty('blocks');
    expect(Array.isArray(treeResult.blocks)).toBe(true);

    const found = treeResult.blocks.find(b => b.id === blockId);
    expect(found).toBeTruthy();
    expect(found.type).toBe('paragraph');
  });

  test('block rich_text roundtrip: create with text, get and verify content', async ({
    request,
  }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const pageId = await createPage(request);
    const sentinel = `_e2e_fidelity_richtext_${Date.now()}`;
    const blockId = await createBlock(request, pageId, sentinel);

    // Retrieve the block and verify the rich_text content matches.
    const getResult = await rpc(request, 'blocks/get', { block_id: blockId });
    expect(getResult.block).toBeTruthy();
    expect(getResult.block.id).toBe(blockId);

    // rich_text is an array of inline text objects.
    const richText = getResult.block.rich_text;
    expect(Array.isArray(richText)).toBe(true);
    expect(richText.length).toBeGreaterThan(0);

    // At least one span must contain the sentinel in its 'content' field.
    // The backend stores spans with a 'content' field (not 'text').
    const found = richText.some(segment => segment.content && segment.content.includes(sentinel));
    expect(found).toBe(true);
  });

  test('block property roundtrip: set property, get it back with same value', async ({
    request,
  }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const pageId = await createPage(request);
    const blockId = await createBlock(request, pageId);

    const propKey = '_e2e_fidelity_prop';
    const propValue = `value_${Date.now()}`;

    // Set the property.
    const setResult = await rpc(request, 'blocks/property/set', {
      block_id: blockId,
      key: propKey,
      value: propValue,
    });
    expect(setResult.ok).toBe(true);
    expect(setResult.key).toBe(propKey);

    // Get it back.
    const getResult = await rpc(request, 'blocks/property/get', {
      block_id: blockId,
      key: propKey,
    });
    expect(getResult.key).toBe(propKey);
    expect(getResult.value).toBe(propValue);
  });

  test('delete block removes it from blocks/page/tree', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const pageId = await createPage(request);
    const blockId = await createBlock(request, pageId, '_e2e_fidelity_ to-delete');

    // Confirm it exists in the tree first.
    const before = await rpc(request, 'blocks/page/tree', { page_id: pageId });
    const existsBefore = before.blocks.some(b => b.id === blockId);
    expect(existsBefore).toBe(true);

    // Delete it.
    const deleteResult = await rpc(request, 'blocks/delete', { block_id: blockId });
    expect(deleteResult.deleted).toBe(true);
    // Remove from cleanup list since already deleted.
    createdBlockIds = createdBlockIds.filter(id => id !== blockId);

    // Verify it's gone from the tree.
    const after = await rpc(request, 'blocks/page/tree', { page_id: pageId });
    const existsAfter = (after.blocks || []).some(b => b.id === blockId);
    expect(existsAfter).toBe(false);
  });

  test('blocks/list for a page returns all created blocks', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const pageId = await createPage(request);

    // Create 3 blocks on the same page.
    const id1 = await createBlock(request, pageId, '_e2e_fidelity_ block-one');
    const id2 = await createBlock(request, pageId, '_e2e_fidelity_ block-two');
    const id3 = await createBlock(request, pageId, '_e2e_fidelity_ block-three');

    const listResult = await rpc(request, 'blocks/list', { page_id: pageId });
    expect(listResult).toHaveProperty('blocks');
    expect(Array.isArray(listResult.blocks)).toBe(true);

    // All three must be present.
    const ids = listResult.blocks.map(b => b.id);
    expect(ids).toContain(id1);
    expect(ids).toContain(id2);
    expect(ids).toContain(id3);

    // Count must be at least 3 (page may have pre-existing blocks from other tests).
    expect(listResult.blocks.length).toBeGreaterThanOrEqual(3);
  });

  test('blocks/move changes block parent_id to new page', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    // Create two pages and a block on the first.
    const page1Id = await createPage(request, `move_src_${Date.now()}`);
    const page2Id = await createPage(request, `move_dst_${Date.now()}`);
    const blockId = await createBlock(request, page1Id, '_e2e_fidelity_ movable block');

    // Confirm block is on page1.
    const before = await rpc(request, 'blocks/get', { block_id: blockId });
    expect(before.block.page_id).toBe(page1Id);

    // Move block to page2 (new_parent_id=null moves to page root, new_page_id targets the page).
    const moveResult = await rpc(request, 'blocks/move', {
      block_id: blockId,
      new_parent_id: null,
      new_page_id: page2Id,
    });
    expect(moveResult.block).toBeTruthy();
    expect(moveResult.block.id).toBe(blockId);

    // Verify new page_id is page2.
    const after = await rpc(request, 'blocks/get', { block_id: blockId });
    expect(after.block.page_id).toBe(page2Id);
  });

});

// =========================================================================
// Group 3: Memory & Conversations via RPC
//
// These are RPC-only tests — memory lifecycle is stdio-only, so we test
// only what is accessible through the HTTP /rpc/dev transport.
// =========================================================================

test.describe('Memory & Conversations via RPC', () => {

  test('lifecycle/memories/list response has memories array', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'lifecycle/memories/list', { status: 'approved' });

    // Shape must have memories array — even if empty on a fresh DB.
    expect(result).toHaveProperty('memories');
    expect(Array.isArray(result.memories)).toBe(true);

    // Every returned memory must have the status we requested.
    for (const memory of result.memories) {
      expect(memory.status).toBe('approved');
    }
  });

  test('conversations/list response has conversations array with correct shape', async ({
    request,
  }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'conversations/list', {});

    expect(result).toHaveProperty('conversations');
    expect(Array.isArray(result.conversations)).toBe(true);

    // If conversations exist, verify required fields on the first one.
    if (result.conversations.length > 0) {
      const conv = result.conversations[0];
      // A conversation must have an id or conversation_id field.
      const hasId = 'conversation_id' in conv || 'id' in conv;
      expect(hasId).toBe(true);
    }
  });

  test('context/stats returns estimated_tokens, context_limit, and usage_percent', async ({
    request,
  }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'context/stats', {});

    expect(result).toHaveProperty('estimated_tokens');
    expect(result).toHaveProperty('context_limit');
    expect(result).toHaveProperty('usage_percent');

    expect(typeof result.estimated_tokens).toBe('number');
    expect(result.estimated_tokens).toBeGreaterThanOrEqual(0);

    expect(typeof result.context_limit).toBe('number');
    expect(result.context_limit).toBeGreaterThan(0);

    expect(typeof result.usage_percent).toBe('number');
    expect(result.usage_percent).toBeGreaterThanOrEqual(0);
    expect(result.usage_percent).toBeLessThanOrEqual(100);
  });

});
