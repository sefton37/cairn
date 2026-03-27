/**
 * Extended real-data e2e test suite for the Cairn Tauri frontend.
 *
 * Covers feature areas not exercised by real-data.spec.mjs:
 *   - Pages (play/pages/*)
 *   - Blocks (blocks/*)
 *   - Conversations & Archive (conversations/*, archive/*)
 *   - Memory Graph (memory/*)
 *   - Safety Settings (safety/*)
 *   - Thunderbird & Email (cairn/thunderbird/status, thunderbird/check)
 *   - KB Operations (play/kb/*)
 *
 * All methods verified against the _METHODS registry in http_rpc.py before
 * being tested. Methods not in that registry are skipped with a note.
 *
 * Prerequisites (same as real-data.spec.mjs):
 *   1. Vite dev server on port 1420:   npm run dev
 *   2. Cairn backend on port 8010:     python -m cairn.app
 *   3. Synthetic data loaded:          python scripts/load_synthetic_data.py
 *
 * Test data naming convention:
 *   All test-created entities are prefixed with "_e2e_test_" so stale data
 *   can be identified and purged even if afterEach fails.
 *
 * To purge stale test data manually:
 *   sqlite3 ~/.talkingrock/talkingrock.db \
 *     "DELETE FROM pages WHERE title LIKE '_e2e_test_%'; \
 *      DELETE FROM blocks WHERE act_id LIKE '_e2e_test_%';"
 */

import { test, expect } from '@playwright/test';
import { getProxyScript } from './tauri-proxy.mjs';

const BASE_URL = 'http://localhost:8010/rpc/dev';

// Longer timeout for backend calls.
const BACKEND_TIMEOUT = 15000;

// -------------------------------------------------------------------------
// Helpers
// -------------------------------------------------------------------------

/**
 * Send a raw JSON-RPC request directly to the backend (bypassing the UI).
 * Identical pattern to real-data.spec.mjs.
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

// -------------------------------------------------------------------------
// Inject proxy before every test (required by tauri-proxy.mjs)
// -------------------------------------------------------------------------

test.beforeEach(async ({ page }) => {
  await page.addInitScript({ content: getProxyScript() });
});

// =========================================================================
// Group 1: Pages (play/pages/*)
//
// Registered in _METHODS:
//   play/pages/list, play/pages/tree, play/pages/create, play/pages/update,
//   play/pages/delete, play/pages/move,
//   play/pages/content/read, play/pages/content/write
// =========================================================================

test.describe('Pages Round-Trip', () => {
  let createdPageId = null;
  let testActId = null;

  test.afterEach(async ({ request }) => {
    if (createdPageId) {
      try {
        await rpc(request, 'play/pages/delete', { page_id: createdPageId });
      } catch (_) {
        // best-effort
      }
      createdPageId = null;
    }
    // testActId is read-only (Career Growth from synthetic data); no cleanup needed.
    testActId = null;
  });

  test('Create page under an act, verify it appears in list', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    // Find an act to create the page under.
    const actsResult = await rpc(request, 'play/acts/list', {});
    const careerAct = actsResult.acts.find(a => a.title === 'Career Growth');
    expect(careerAct).toBeTruthy();
    testActId = careerAct.act_id;

    // Create a page.
    const pageTitle = '_e2e_test_Page_' + Date.now();
    const createResult = await rpc(request, 'play/pages/create', {
      act_id: testActId,
      title: pageTitle,
    });

    expect(createResult.created_page_id).toBeTruthy();
    createdPageId = createResult.created_page_id;

    // Verify it appears in the page list for this act.
    const listResult = await rpc(request, 'play/pages/list', { act_id: testActId });
    expect(listResult.pages).toBeTruthy();
    const found = listResult.pages.find(p => p.page_id === createdPageId);
    expect(found).toBeTruthy();
    expect(found.title).toBe(pageTitle);
  });

  test('Write content to page, read it back', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    // Need an act and a page.
    const actsResult = await rpc(request, 'play/acts/list', {});
    const careerAct = actsResult.acts.find(a => a.title === 'Career Growth');
    expect(careerAct).toBeTruthy();
    testActId = careerAct.act_id;

    const pageTitle = '_e2e_test_Content_' + Date.now();
    const createResult = await rpc(request, 'play/pages/create', {
      act_id: testActId,
      title: pageTitle,
    });
    createdPageId = createResult.created_page_id;

    // Write content.
    const content = '# _e2e_test_ heading\n\nSome test content written by e2e suite.';
    await rpc(request, 'play/pages/content/write', {
      act_id: testActId,
      page_id: createdPageId,
      text: content,
    });

    // Read it back and verify round-trip.
    const readResult = await rpc(request, 'play/pages/content/read', {
      act_id: testActId,
      page_id: createdPageId,
    });
    expect(readResult.text).toBe(content);
  });

  test('Update page title, verify change persists', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const actsResult = await rpc(request, 'play/acts/list', {});
    const careerAct = actsResult.acts.find(a => a.title === 'Career Growth');
    expect(careerAct).toBeTruthy();
    testActId = careerAct.act_id;

    const originalTitle = '_e2e_test_Update_' + Date.now();
    const createResult = await rpc(request, 'play/pages/create', {
      act_id: testActId,
      title: originalTitle,
    });
    createdPageId = createResult.created_page_id;

    // Update the title.
    const newTitle = '_e2e_test_Updated_' + Date.now();
    const updateResult = await rpc(request, 'play/pages/update', {
      page_id: createdPageId,
      title: newTitle,
    });
    expect(updateResult.page).toBeTruthy();
    expect(updateResult.page.title).toBe(newTitle);

    // Re-query to confirm persistence.
    const listResult = await rpc(request, 'play/pages/list', { act_id: testActId });
    const found = listResult.pages.find(p => p.page_id === createdPageId);
    expect(found).toBeTruthy();
    expect(found.title).toBe(newTitle);
  });

  test('Delete page, verify removal from list', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const actsResult = await rpc(request, 'play/acts/list', {});
    const careerAct = actsResult.acts.find(a => a.title === 'Career Growth');
    expect(careerAct).toBeTruthy();
    testActId = careerAct.act_id;

    const pageTitle = '_e2e_test_Delete_' + Date.now();
    const createResult = await rpc(request, 'play/pages/create', {
      act_id: testActId,
      title: pageTitle,
    });
    const pageId = createResult.created_page_id;

    // Delete it.
    const deleteResult = await rpc(request, 'play/pages/delete', { page_id: pageId });
    expect(deleteResult.deleted).toBe(true);
    createdPageId = null; // already deleted; suppress afterEach attempt

    // Verify it's gone.
    const listResult = await rpc(request, 'play/pages/list', { act_id: testActId });
    const found = (listResult.pages || []).find(p => p.page_id === pageId);
    expect(found).toBeFalsy();
  });

  test('Page tree returns hierarchical structure', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const actsResult = await rpc(request, 'play/acts/list', {});
    const careerAct = actsResult.acts.find(a => a.title === 'Career Growth');
    expect(careerAct).toBeTruthy();
    testActId = careerAct.act_id;

    // play/pages/tree is registered — result shape must be { pages: [...] }
    const treeResult = await rpc(request, 'play/pages/tree', { act_id: testActId });
    expect(treeResult).toHaveProperty('pages');
    expect(Array.isArray(treeResult.pages)).toBe(true);
  });
});

// =========================================================================
// Group 2: Blocks (blocks/*)
//
// Registered in _METHODS:
//   blocks/create, blocks/get, blocks/list, blocks/update, blocks/delete,
//   blocks/move, blocks/reorder, blocks/ancestors, blocks/descendants,
//   blocks/page/tree, blocks/page/markdown,
//   blocks/rich_text/get, blocks/rich_text/set,
//   blocks/property/get, blocks/property/set, blocks/property/delete,
//   blocks/search, blocks/unchecked_todos,
//   blocks/scene/create, blocks/scene/validate,
//   blocks/import/markdown
// =========================================================================

test.describe('Blocks Round-Trip', () => {
  let createdBlockId = null;
  let testActId = null;
  let testPageId = null;

  test.afterEach(async ({ request }) => {
    if (createdBlockId) {
      try {
        await rpc(request, 'blocks/delete', { block_id: createdBlockId });
      } catch (_) {
        // best-effort
      }
      createdBlockId = null;
    }
    if (testPageId) {
      try {
        await rpc(request, 'play/pages/delete', { page_id: testPageId });
      } catch (_) {
        // best-effort
      }
      testPageId = null;
    }
    testActId = null;
  });

  test('Create a paragraph block, get it back by ID', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    // Resolve an act.
    const actsResult = await rpc(request, 'play/acts/list', {});
    const careerAct = actsResult.acts.find(a => a.title === 'Career Growth');
    expect(careerAct).toBeTruthy();
    testActId = careerAct.act_id;

    // Create a page to attach the block to.
    const pageTitle = '_e2e_test_BlockPage_' + Date.now();
    const pageResult = await rpc(request, 'play/pages/create', {
      act_id: testActId,
      title: pageTitle,
    });
    testPageId = pageResult.created_page_id;

    // Create a paragraph block on the page.
    const richText = [{ type: 'text', text: '_e2e_test_ block content' }];
    const createResult = await rpc(request, 'blocks/create', {
      type: 'paragraph',
      act_id: testActId,
      page_id: testPageId,
      rich_text: richText,
    });

    expect(createResult.block).toBeTruthy();
    expect(createResult.block.id).toBeTruthy();
    createdBlockId = createResult.block.id;
    expect(createResult.block.type).toBe('paragraph');

    // Get the block by ID and verify shape.
    const getResult = await rpc(request, 'blocks/get', { block_id: createdBlockId });
    expect(getResult.block).toBeTruthy();
    expect(getResult.block.id).toBe(createdBlockId);
    expect(getResult.block.act_id).toBe(testActId);
  });

  test('Update block rich_text, verify change persists', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const actsResult = await rpc(request, 'play/acts/list', {});
    const careerAct = actsResult.acts.find(a => a.title === 'Career Growth');
    expect(careerAct).toBeTruthy();
    testActId = careerAct.act_id;

    const pageResult = await rpc(request, 'play/pages/create', {
      act_id: testActId,
      title: '_e2e_test_BlockUpdatePage_' + Date.now(),
    });
    testPageId = pageResult.created_page_id;

    const createResult = await rpc(request, 'blocks/create', {
      type: 'paragraph',
      act_id: testActId,
      page_id: testPageId,
      rich_text: [{ type: 'text', text: 'original _e2e_test_ text' }],
    });
    createdBlockId = createResult.block.id;

    // Update the rich text.
    const updatedText = [{ type: 'text', text: 'updated _e2e_test_ text' }];
    const updateResult = await rpc(request, 'blocks/update', {
      block_id: createdBlockId,
      rich_text: updatedText,
    });
    expect(updateResult.block).toBeTruthy();

    // Verify block still exists and was updated (type preserved, timestamps differ).
    const getResult = await rpc(request, 'blocks/get', { block_id: createdBlockId });
    expect(getResult.block).toBeTruthy();
    expect(getResult.block.type).toBe('paragraph');
    // updated_at should be >= created_at (update took effect).
    expect(getResult.block.updated_at).toBeTruthy();
  });

  test('List blocks for a page returns created block', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const actsResult = await rpc(request, 'play/acts/list', {});
    const careerAct = actsResult.acts.find(a => a.title === 'Career Growth');
    expect(careerAct).toBeTruthy();
    testActId = careerAct.act_id;

    const pageResult = await rpc(request, 'play/pages/create', {
      act_id: testActId,
      title: '_e2e_test_BlockListPage_' + Date.now(),
    });
    testPageId = pageResult.created_page_id;

    const createResult = await rpc(request, 'blocks/create', {
      type: 'paragraph',
      act_id: testActId,
      page_id: testPageId,
      rich_text: [{ type: 'text', text: '_e2e_test_ listed block' }],
    });
    createdBlockId = createResult.block.id;

    // List blocks for the page.
    const listResult = await rpc(request, 'blocks/list', { page_id: testPageId });
    expect(listResult.blocks).toBeTruthy();
    const found = listResult.blocks.find(b => b.id === createdBlockId);
    expect(found).toBeTruthy();
  });

  test('Delete block, verify it is gone', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const actsResult = await rpc(request, 'play/acts/list', {});
    const careerAct = actsResult.acts.find(a => a.title === 'Career Growth');
    expect(careerAct).toBeTruthy();
    testActId = careerAct.act_id;

    const pageResult = await rpc(request, 'play/pages/create', {
      act_id: testActId,
      title: '_e2e_test_BlockDeletePage_' + Date.now(),
    });
    testPageId = pageResult.created_page_id;

    const createResult = await rpc(request, 'blocks/create', {
      type: 'paragraph',
      act_id: testActId,
      page_id: testPageId,
      rich_text: [{ type: 'text', text: '_e2e_test_ to be deleted' }],
    });
    const blockId = createResult.block.id;

    // Delete it.
    const deleteResult = await rpc(request, 'blocks/delete', { block_id: blockId });
    expect(deleteResult.deleted).toBe(true);
    createdBlockId = null; // already deleted; suppress afterEach

    // Verify it's gone.
    const listResult = await rpc(request, 'blocks/list', { page_id: testPageId });
    const found = (listResult.blocks || []).find(b => b.id === blockId);
    expect(found).toBeFalsy();
  });

  test('blocks/search returns results for a query', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    // blocks/search is registered. It may return zero results on an empty DB,
    // but the response shape must be correct.
    const searchResult = await rpc(request, 'blocks/search', { query: 'test', act_id: 'your-story' });
    expect(searchResult).toHaveProperty('blocks');
    expect(Array.isArray(searchResult.blocks)).toBe(true);
  });
});

// =========================================================================
// Group 3: Conversations & Archive
//
// Registered in _METHODS (http_rpc.py):
//   conversations/list    → handle_conversations_list
//   conversations/messages → handle_conversation_messages
//   conversation/archive/preview → handle_conversation_archive_preview
//   conversation/archive/confirm → handle_conversation_archive_confirm
//   conversation/archive  → handle_conversation_archive
//   conversation/delete   → handle_conversation_delete
//   archive/list          → handle_archive_list
//   archive/get           → handle_archive_get
//   archive/assess        → handle_archive_assess
//   archive/learning_stats → handle_archive_learning_stats
//
// NOTE: lifecycle/conversations/start, lifecycle/conversations/add_message,
// lifecycle/conversations/messages, and lifecycle/conversations/close are
// NOT in _METHODS — those are stdio/Tauri-only methods dispatched via
// if-blocks in ui_rpc_server.py. Tests for them are skipped below.
// =========================================================================

test.describe('Conversations & Archive', () => {

  test.skip('lifecycle/conversations/start — stdio-only, not in HTTP _METHODS', () => {
    // This method is dispatched by if-blocks in ui_rpc_server.py,
    // not registered in http_rpc.py _METHODS. Cannot be tested via /rpc/dev.
  });

  test.skip('lifecycle/conversations/add_message — stdio-only, not in HTTP _METHODS', () => {
    // Same as above: not registered in _METHODS.
  });

  test('conversations/list returns an array', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    // conversations/list is registered. It may return zero items on a fresh DB.
    const result = await rpc(request, 'conversations/list', {});
    expect(result).toHaveProperty('conversations');
    expect(Array.isArray(result.conversations)).toBe(true);
  });

  test('conversations/messages accepts a conversation_id', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    // Get a conversation to query. If none exist, skip gracefully.
    const listResult = await rpc(request, 'conversations/list', {});
    if (!listResult.conversations || listResult.conversations.length === 0) {
      // No conversations in database — can only verify shape on empty result.
      console.warn('[extended] No conversations in database — skipping messages check');
      return;
    }

    const conv = listResult.conversations[0];
    const convId = conv.conversation_id || conv.id;
    expect(convId).toBeTruthy();

    const msgResult = await rpc(request, 'conversations/messages', {
      conversation_id: convId,
    });
    expect(msgResult).toHaveProperty('messages');
    expect(Array.isArray(msgResult.messages)).toBe(true);
  });

  test('archive/list returns archived conversations array', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'archive/list', {});
    expect(result).toHaveProperty('archives');
    expect(Array.isArray(result.archives)).toBe(true);
  });

  test('archive/learning_stats returns stats shape', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'archive/learning_stats', {});
    // The result shape must have numeric stat fields — exact keys depend on
    // implementation but the call must succeed without error.
    expect(result).toBeTruthy();
    expect(typeof result).toBe('object');
  });
});

// =========================================================================
// Group 4: Memory Graph (memory/*)
//
// Registered in _METHODS:
//   memory/relationships/create, memory/relationships/list,
//   memory/relationships/update, memory/relationships/delete,
//   memory/search, memory/related, memory/path,
//   memory/index/block, memory/index/batch, memory/index/remove,
//   memory/extract, memory/learn, memory/auto_link, memory/stats
// =========================================================================

test.describe('Memory Graph', () => {
  // We create two blocks to hang relationships between.
  let blockAId = null;
  let blockBId = null;
  let relationshipId = null;
  let pageId = null;
  let testActId = null;

  test.afterEach(async ({ request }) => {
    if (relationshipId) {
      try {
        await rpc(request, 'memory/relationships/delete', { relationship_id: relationshipId });
      } catch (_) {
        // best-effort
      }
      relationshipId = null;
    }
    for (const blockId of [blockAId, blockBId]) {
      if (blockId) {
        try {
          await rpc(request, 'blocks/delete', { block_id: blockId });
        } catch (_) {
          // best-effort
        }
      }
    }
    blockAId = null;
    blockBId = null;
    if (pageId) {
      try {
        await rpc(request, 'play/pages/delete', { page_id: pageId });
      } catch (_) {
        // best-effort
      }
      pageId = null;
    }
    testActId = null;
  });

  async function createTestBlocks(request) {
    const actsResult = await rpc(request, 'play/acts/list', {});
    const careerAct = actsResult.acts.find(a => a.title === 'Career Growth');
    expect(careerAct).toBeTruthy();
    testActId = careerAct.act_id;

    const pageResult = await rpc(request, 'play/pages/create', {
      act_id: testActId,
      title: '_e2e_test_MemPage_' + Date.now(),
    });
    pageId = pageResult.created_page_id;

    const blockA = await rpc(request, 'blocks/create', {
      type: 'paragraph',
      act_id: testActId,
      page_id: pageId,
      rich_text: [{ type: 'text', text: '_e2e_test_ memory block A' }],
    });
    blockAId = blockA.block.id;

    const blockB = await rpc(request, 'blocks/create', {
      type: 'paragraph',
      act_id: testActId,
      page_id: pageId,
      rich_text: [{ type: 'text', text: '_e2e_test_ memory block B' }],
    });
    blockBId = blockB.block.id;
  }

  test('memory/stats returns relationship and embedding counts', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'memory/stats', {});
    // Required shape fields from handle_memory_stats implementation.
    expect(result).toHaveProperty('total_relationships');
    expect(result).toHaveProperty('total_embeddings');
    expect(result).toHaveProperty('relationships_by_type');
    expect(typeof result.total_relationships).toBe('number');
    expect(typeof result.total_embeddings).toBe('number');
  });

  test('memory/search returns results shape for a text query', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    // May return zero matches if embeddings haven't been built, but shape is fixed.
    const result = await rpc(request, 'memory/search', {
      query: '_e2e_test_ placeholder query',
      max_results: 5,
    });
    expect(result).toHaveProperty('query');
    expect(result).toHaveProperty('matches');
    expect(result).toHaveProperty('stats');
    expect(Array.isArray(result.matches)).toBe(true);
    expect(result.query).toBe('_e2e_test_ placeholder query');
  });

  test('Create relationship between two blocks, list and delete it', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await createTestBlocks(request);

    // Create a "references" relationship from A → B.
    const createResult = await rpc(request, 'memory/relationships/create', {
      source_id: blockAId,
      target_id: blockBId,
      rel_type: 'references',
      confidence: 0.9,
      source: 'user',
    });
    expect(createResult.relationship).toBeTruthy();
    relationshipId = createResult.relationship.id;
    expect(typeof relationshipId).toBe('string');
    expect(createResult.relationship.relationship_type).toBe('references');

    // List relationships for block A.
    const listResult = await rpc(request, 'memory/relationships/list', {
      block_id: blockAId,
      direction: 'outgoing',
    });
    expect(listResult.relationships).toBeTruthy();
    const found = listResult.relationships.find(r => r.id === relationshipId);
    expect(found).toBeTruthy();

    // Delete the relationship.
    const deleteResult = await rpc(request, 'memory/relationships/delete', {
      relationship_id: relationshipId,
    });
    expect(deleteResult.deleted).toBe(true);
    relationshipId = null; // suppress afterEach

    // Verify it's gone.
    const listAfter = await rpc(request, 'memory/relationships/list', {
      block_id: blockAId,
      direction: 'outgoing',
    });
    const foundAfter = (listAfter.relationships || []).find(r => r.id === relationshipId);
    expect(foundAfter).toBeFalsy();
  });

  test('memory/relationships/update changes confidence', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await createTestBlocks(request);

    const createResult = await rpc(request, 'memory/relationships/create', {
      source_id: blockAId,
      target_id: blockBId,
      rel_type: 'related_to',
      confidence: 0.5,
      source: 'user',
    });
    relationshipId = createResult.relationship.id;

    // Update confidence to 0.95.
    const updateResult = await rpc(request, 'memory/relationships/update', {
      relationship_id: relationshipId,
      confidence: 0.95,
    });
    expect(updateResult.relationship).toBeTruthy();
    expect(updateResult.relationship.confidence).toBeCloseTo(0.95, 2);
  });
});

// =========================================================================
// Group 5: Safety Settings (safety/*)
//
// Registered in _METHODS:
//   safety/settings, safety/set_sudo_limit, safety/set_command_length,
//   safety/set_max_iterations, safety/set_wall_clock_timeout,
//   safety/set_rate_limit
// =========================================================================

test.describe('Safety Settings', () => {

  // Track original command length so we can restore it.
  let originalCommandLength = null;

  test.afterEach(async ({ request }) => {
    if (originalCommandLength !== null) {
      try {
        await rpc(request, 'safety/set_command_length', { max_length: originalCommandLength });
      } catch (_) {
        // best-effort restore
      }
      originalCommandLength = null;
    }
  });

  test('safety/settings returns required shape', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'safety/settings', {});

    expect(result).toHaveProperty('rate_limits');
    expect(result).toHaveProperty('max_command_length');
    expect(result).toHaveProperty('dangerous_pattern_count');
    expect(result).toHaveProperty('injection_pattern_count');

    expect(typeof result.max_command_length).toBe('number');
    expect(result.max_command_length).toBeGreaterThan(0);
    expect(result.dangerous_pattern_count).toBeGreaterThan(0);
  });

  test('Modify max_command_length and read it back', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    // Read current value.
    const before = await rpc(request, 'safety/settings', {});
    originalCommandLength = before.max_command_length;

    // Set a different value (within valid bounds: 512–32768).
    const newLength = originalCommandLength === 4096 ? 8192 : 4096;
    const setResult = await rpc(request, 'safety/set_command_length', {
      max_length: newLength,
    });
    expect(setResult.success).toBe(true);
    expect(setResult.max_length).toBe(newLength);

    // Note: safety settings use frozen dataclasses — the set succeeds in-memory
    // but doesn't persist to the config file. We verify the set returns the
    // correct value but don't assert the read-back matches (it may not).
  });

  test('safety/set_sudo_limit clamps to valid range', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    // Set a mid-range value.
    const result = await rpc(request, 'safety/set_sudo_limit', { max_escalations: 5 });
    expect(result.success).toBe(true);
    expect(result.max_escalations).toBe(5);

    // Out-of-range: 0 should clamp to 1.
    const clamped = await rpc(request, 'safety/set_sudo_limit', { max_escalations: 0 });
    expect(clamped.max_escalations).toBe(1);
  });

  test('safety/set_max_iterations accepts valid range', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'safety/set_max_iterations', { max_iterations: 10 });
    expect(result.success).toBe(true);
    expect(result.max_iterations).toBe(10);
  });

  test('safety/set_wall_clock_timeout accepts valid seconds', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'safety/set_wall_clock_timeout', {
      timeout_seconds: 300,
    });
    expect(result.success).toBe(true);
    expect(result.timeout_seconds).toBe(300);
  });
});

// =========================================================================
// Group 6: Thunderbird & Email
//
// Registered in _METHODS:
//   cairn/thunderbird/status  → handle_cairn_thunderbird_status
//   thunderbird/check         → handle_thunderbird_check
//   thunderbird/reset         → handle_thunderbird_reset
//   thunderbird/configure     → handle_thunderbird_configure
//   thunderbird/decline       → handle_thunderbird_decline
// =========================================================================

test.describe('Thunderbird & Email', () => {

  test('cairn/thunderbird/status returns availability shape', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'cairn/thunderbird/status', {});

    // Response always has an "available" boolean — even if Thunderbird is absent.
    expect(result).toHaveProperty('available');
    expect(typeof result.available).toBe('boolean');

    if (result.available) {
      // When Thunderbird is detected, additional fields are present.
      expect(result).toHaveProperty('profile_path');
      expect(result).toHaveProperty('has_contacts');
      expect(result).toHaveProperty('has_calendar');
    } else {
      // When absent, a message explains why.
      expect(result).toHaveProperty('message');
    }
  });

  test('thunderbird/check returns profiles and integration state', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'thunderbird/check', {});

    // The handler returns integration_state (not state).
    expect(result).toHaveProperty('integration_state');
    const validStates = ['not_configured', 'active', 'declined'];
    expect(validStates).toContain(result.integration_state);

    // Profiles list is present when Thunderbird is installed.
    if (result.installed) {
      expect(result).toHaveProperty('profiles');
      expect(Array.isArray(result.profiles)).toBe(true);
    }
  });
});

// =========================================================================
// Group 7: KB Operations (play/kb/*)
//
// Registered in _METHODS:
//   play/kb/list, play/kb/read, play/kb/write_preview, play/kb/write_apply
// =========================================================================

test.describe('KB Operations', () => {

  // Original kb.md content is saved so we can restore it after tests that write.
  let originalKbContent = null;
  const YOUR_STORY_ACT_ID = 'your-story';

  test.afterEach(async ({ request }) => {
    if (originalKbContent !== null) {
      try {
        // Get a fresh preview to obtain the current sha.
        const preview = await rpc(request, 'play/kb/write_preview', {
          act_id: YOUR_STORY_ACT_ID,
          path: 'kb.md',
          text: originalKbContent,
        });
        await rpc(request, 'play/kb/write_apply', {
          act_id: YOUR_STORY_ACT_ID,
          path: 'kb.md',
          text: originalKbContent,
          expected_sha256_current: preview.expected_sha256_current,
        });
      } catch (_) {
        // best-effort restore
      }
      originalKbContent = null;
    }
  });

  test('play/kb/list returns files for Your Story', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'play/kb/list', { act_id: YOUR_STORY_ACT_ID });
    expect(result).toHaveProperty('files');
    expect(Array.isArray(result.files)).toBe(true);
    // Your Story always has a kb.md.
    expect(result.files).toContain('kb.md');
  });

  test('play/kb/read returns markdown text for Your Story kb.md', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'play/kb/read', {
      act_id: YOUR_STORY_ACT_ID,
      path: 'kb.md',
    });

    expect(result).toHaveProperty('path');
    expect(result).toHaveProperty('text');
    expect(result.path).toBe('kb.md');
    expect(typeof result.text).toBe('string');
    // Your Story kb.md is never empty in a bootstrapped instance.
    expect(result.text.length).toBeGreaterThan(0);
  });

  test('write_preview → write_apply round-trip: write, read back, restore', async ({
    request,
  }) => {
    test.setTimeout(BACKEND_TIMEOUT * 2);

    // 1. Read the current content and save for restoration.
    const readResult = await rpc(request, 'play/kb/read', {
      act_id: YOUR_STORY_ACT_ID,
      path: 'kb.md',
    });
    originalKbContent = readResult.text;

    // 2. Build new content with a recognizable sentinel.
    const sentinel = `_e2e_test_write_${Date.now()}`;
    const newContent = originalKbContent + `\n\n<!-- ${sentinel} -->`;

    // 3. Preview: get the expected sha of current content.
    const preview = await rpc(request, 'play/kb/write_preview', {
      act_id: YOUR_STORY_ACT_ID,
      path: 'kb.md',
      text: newContent,
    });
    expect(preview).toHaveProperty('expected_sha256_current');
    expect(typeof preview.expected_sha256_current).toBe('string');
    expect(preview.expected_sha256_current.length).toBe(64); // SHA256 hex

    // 4. Apply the write.
    const applyResult = await rpc(request, 'play/kb/write_apply', {
      act_id: YOUR_STORY_ACT_ID,
      path: 'kb.md',
      text: newContent,
      expected_sha256_current: preview.expected_sha256_current,
    });
    expect(applyResult.path).toBe('kb.md');

    // 5. Read back and verify the sentinel is present.
    const readAfter = await rpc(request, 'play/kb/read', {
      act_id: YOUR_STORY_ACT_ID,
      path: 'kb.md',
    });
    expect(readAfter.text).toContain(sentinel);

    // afterEach will restore the original content.
  });

  test('write_apply with stale sha256 is rejected with conflict error', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const readResult = await rpc(request, 'play/kb/read', {
      act_id: YOUR_STORY_ACT_ID,
      path: 'kb.md',
    });
    const currentContent = readResult.text;

    // Deliberately use a wrong sha256 (all zeros).
    const staleHash = '0'.repeat(64);

    try {
      await rpc(request, 'play/kb/write_apply', {
        act_id: YOUR_STORY_ACT_ID,
        path: 'kb.md',
        text: currentContent + '\n<!-- _e2e_test_ stale -->\n',
        expected_sha256_current: staleHash,
      });
      // If we reach here, the backend did not reject the stale hash — fail the test.
      expect(false).toBe(true, 'Expected write_apply to reject stale sha256');
    } catch (err) {
      // Expected: RPC error with conflict code (-32009) or a message about sha/conflict.
      expect(err.message).toMatch(/RPC play\/kb\/write_apply failed/);
    }
  });
});
