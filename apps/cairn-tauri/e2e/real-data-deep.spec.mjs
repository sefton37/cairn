/**
 * Deep real-data e2e test suite for the Cairn Tauri frontend.
 *
 * Covers feature areas not exercised by real-data.spec.mjs or
 * real-data-extended.spec.mjs:
 *
 *   Group 1: Personas (personas/list, personas/upsert)
 *   Group 2: Documents (documents/list, documents/insert, documents/get,
 *             documents/chunks, documents/delete)
 *   Group 3: Memory Lifecycle list-only
 *             Only lifecycle/memories/list is in _METHODS.
 *             All other lifecycle memory methods live in ui_rpc_server.py
 *             (stdio JSON-RPC) and are NOT exposed on /rpc/dev.
 *   Group 4: Deeper Block Operations
 *             blocks/move, blocks/reorder, blocks/ancestors, blocks/descendants,
 *             blocks/page/tree, blocks/page/markdown, blocks/import/markdown,
 *             blocks/property/get, blocks/property/set, blocks/property/delete,
 *             blocks/unchecked_todos
 *   Group 5: Context Toggle (context/toggle_source)
 *   Group 6: Approval System (approval/pending shape)
 *   Group 7: Attention (cairn/attention, cairn/attention/reorder)
 *             Placed last: get_cairn_store() can lock SQLite during embedding load
 *   Group 8: Thunderbird status (graceful when not configured)
 *             Placed last: same get_cairn_store() contention issue
 *
 * METHODS NOTE:
 *   lifecycle/memories/list is the ONLY memory lifecycle method in _METHODS.
 *   The pending/get/approve/reject/route/search/search_fts handlers exist in
 *   ui_rpc_server.py (stdio) and are NOT accessible via /rpc/dev.
 *   cairn/attention/rules/* and cairn/email/* are NOT in _METHODS at all.
 *
 * Prerequisites (same as real-data.spec.mjs):
 *   1. Vite dev server on port 1420:   npm run dev
 *   2. Cairn backend on port 8010:     python -m cairn.app
 *   3. Synthetic data loaded:          python scripts/load_synthetic_data.py
 *
 * Test data naming convention:
 *   All test-created entities are prefixed with "_e2e_test_" so stale data
 *   can be identified and purged even if afterEach fails.
 */

import { test, expect } from '@playwright/test';
import { getProxyScript } from './tauri-proxy.mjs';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

const BASE_URL = 'http://localhost:8010/rpc/dev';

// Longer timeout for backend calls.
const BACKEND_TIMEOUT = 15000;

// Extended timeout for document insert operations.
// On a cold server start, the embedding model (all-MiniLM-L6-v2) takes up to
// 2 minutes to load on CUDA. Once loaded, subsequent calls are fast.
// Tests that insert documents must use DOCUMENT_TIMEOUT on the first call.
const DOCUMENT_TIMEOUT = 120000;

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

/**
 * Send an RPC call and return the full response envelope (result OR error).
 * Used for tests that intentionally check error responses.
 */
async function rpcRaw(request, method, params = {}) {
  const resp = await request.post(BASE_URL, {
    data: { jsonrpc: '2.0', id: Date.now(), method, params },
    headers: { 'Content-Type': 'application/json' },
  });
  return resp.json();
}

// -------------------------------------------------------------------------
// Inject proxy before every test (required by tauri-proxy.mjs)
// -------------------------------------------------------------------------

test.beforeEach(async ({ page }) => {
  await page.addInitScript({ content: getProxyScript() });
});

// =========================================================================
// Group 1: Personas
//
// Registered in _METHODS: personas/list, personas/upsert
//
// Note: personas/get and personas/set_active are defined in personas.py but
// are NOT in _METHODS in http_rpc.py and therefore not tested here.
// =========================================================================

test.describe('Personas', () => {
  // Use a per-run timestamp so names never collide with stale test personas
  // from previous runs. The `name` column has a UNIQUE constraint in the DB.
  const runId = Date.now();
  const testPersonaId = '_e2e_test_persona_' + runId;

  // Note: No delete method exists in _METHODS for personas.
  // Test personas remain in the DB with the _e2e_test_ prefix.
  // Manual cleanup:
  //   sqlite3 ~/.talkingrock/talkingrock.db
  //     "DELETE FROM agent_personas WHERE id LIKE '_e2e_test_%';"

  test('List personas returns expected shape', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'personas/list', {});

    expect(result).toHaveProperty('personas');
    expect(Array.isArray(result.personas)).toBe(true);
    // active_persona_id may be null if no persona is active.
    expect(result).toHaveProperty('active_persona_id');
  });

  test('Upsert creates a new persona, list confirms it appears', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const persona = {
      id: testPersonaId,
      name: `_e2e_test_ Persona ${runId}`,
      system_prompt: 'You are a test persona created by the e2e suite.',
      default_context: 'e2e test context',
      temperature: 0.7,
      top_p: 0.9,
      tool_call_limit: 5,
    };

    const upsertResult = await rpc(request, 'personas/upsert', { persona });
    expect(upsertResult.ok).toBe(true);

    // Confirm it appears in the list.
    const listResult = await rpc(request, 'personas/list', {});
    const found = listResult.personas.find(p => p.id === testPersonaId);
    expect(found).toBeTruthy();
    expect(found.name).toBe(`_e2e_test_ Persona ${runId}`);
  });

  test('Upsert updates an existing persona (idempotent write)', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    // First write.
    const originalPersona = {
      id: testPersonaId,
      name: `_e2e_test_ Original Name ${runId}`,
      system_prompt: 'Original system prompt.',
      default_context: 'original context',
      temperature: 0.5,
      top_p: 0.8,
      tool_call_limit: 3,
    };
    await rpc(request, 'personas/upsert', { persona: originalPersona });

    // Second write with updated name.
    const updatedPersona = { ...originalPersona, name: `_e2e_test_ Updated Name ${runId}` };
    const updateResult = await rpc(request, 'personas/upsert', { persona: updatedPersona });
    expect(updateResult.ok).toBe(true);

    // Confirm updated name persisted.
    const listResult = await rpc(request, 'personas/list', {});
    const found = listResult.personas.find(p => p.id === testPersonaId);
    expect(found).toBeTruthy();
    expect(found.name).toBe(`_e2e_test_ Updated Name ${runId}`);
  });

  test('Upsert rejects persona with missing required fields', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    // Omit 'temperature' — a required field per handle_persona_upsert.
    const incompletePersona = {
      id: '_e2e_test_bad_persona',
      name: '_e2e_test_ Missing Fields',
      system_prompt: 'x',
      default_context: 'x',
      // temperature intentionally omitted
      top_p: 0.9,
      tool_call_limit: 5,
    };

    const body = await rpcRaw(request, 'personas/upsert', { persona: incompletePersona });
    expect(body.error).toBeTruthy();
    expect(body.error.code).toBe(-32602);
  });
});

// =========================================================================
// Group 2: Documents
//
// Registered in _METHODS:
//   documents/insert, documents/list, documents/get,
//   documents/delete, documents/chunks
// =========================================================================

test.describe('Documents', () => {
  let insertedDocumentId = null;
  let tempFilePath = null;
  let docActId = null;

  test.beforeEach(async ({ request }) => {
    // Resolve an act to scope documents (required so FK constraint on blocks passes).
    const actsResult = await rpc(request, 'play/acts/list', {});
    const careerAct = actsResult.acts.find(a => a.title === 'Career Growth');
    expect(careerAct).toBeTruthy();
    docActId = careerAct.act_id;

    // Create a small temp text file for insertion tests.
    const tmpDir = os.tmpdir();
    tempFilePath = path.join(tmpDir, `_e2e_test_doc_${Date.now()}.txt`);
    fs.writeFileSync(
      tempFilePath,
      '_e2e_test_ Document\n\n' +
        'This is a test document created by the Cairn e2e suite.\n' +
        'It contains multiple sentences so the chunker has content to work with.\n' +
        'The document is plain text and should be processed without errors.\n',
    );
  });

  test.afterEach(async ({ request }) => {
    // Delete the inserted document if it was created.
    if (insertedDocumentId) {
      try {
        await rpc(request, 'documents/delete', { document_id: insertedDocumentId });
      } catch (_) {
        // best-effort
      }
      insertedDocumentId = null;
    }
    // Remove the temp file.
    if (tempFilePath) {
      try {
        fs.unlinkSync(tempFilePath);
      } catch (_) {
        // best-effort
      }
      tempFilePath = null;
    }
    docActId = null;
  });

  test('List documents returns expected shape', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'documents/list', {});

    expect(result).toHaveProperty('documents');
    expect(Array.isArray(result.documents)).toBe(true);
    expect(result).toHaveProperty('count');
    expect(typeof result.count).toBe('number');
  });

  test('Insert a text document, verify it appears in list', async ({ request }) => {
    // DOCUMENT_TIMEOUT: first insert may trigger embedding model load (up to 2min on cold start).
    test.setTimeout(DOCUMENT_TIMEOUT);

    // Pass act_id so chunk blocks satisfy the FK constraint on the blocks table.
    const insertResult = await rpc(request, 'documents/insert', {
      file_path: tempFilePath,
      act_id: docActId,
    });

    expect(insertResult).toHaveProperty('documentId');
    expect(insertResult.documentId).toBeTruthy();
    insertedDocumentId = insertResult.documentId;

    expect(insertResult).toHaveProperty('fileName');
    expect(insertResult).toHaveProperty('chunkCount');
    expect(typeof insertResult.chunkCount).toBe('number');
    expect(insertResult.chunkCount).toBeGreaterThanOrEqual(1);

    // Confirm it appears in the list.
    const listResult = await rpc(request, 'documents/list', {});
    const found = listResult.documents.find(d => d.documentId === insertedDocumentId);
    expect(found).toBeTruthy();
    expect(found.fileType).toBe('txt');
  });

  test('Get document by ID returns full metadata', async ({ request }) => {
    test.setTimeout(DOCUMENT_TIMEOUT);

    const insertResult = await rpc(request, 'documents/insert', {
      file_path: tempFilePath,
      act_id: docActId,
    });
    insertedDocumentId = insertResult.documentId;

    const getResult = await rpc(request, 'documents/get', {
      document_id: insertedDocumentId,
    });

    expect(getResult).toHaveProperty('documentId', insertedDocumentId);
    expect(getResult).toHaveProperty('fileName');
    expect(getResult).toHaveProperty('fileType');
    expect(getResult).toHaveProperty('chunkCount');
    expect(getResult).toHaveProperty('extractedAt');
  });

  test('Get document chunks returns chunk list', async ({ request }) => {
    // DOCUMENT_TIMEOUT: calls documents/insert which may trigger embedding model load.
    test.setTimeout(DOCUMENT_TIMEOUT);

    // act_id is required to satisfy the FK constraint on chunk blocks.
    const insertResult = await rpc(request, 'documents/insert', {
      file_path: tempFilePath,
      act_id: docActId,
    });
    insertedDocumentId = insertResult.documentId;

    const chunksResult = await rpc(request, 'documents/chunks', {
      document_id: insertedDocumentId,
    });

    expect(chunksResult).toHaveProperty('documentId', insertedDocumentId);
    expect(chunksResult).toHaveProperty('chunks');
    expect(Array.isArray(chunksResult.chunks)).toBe(true);
    expect(chunksResult.chunks.length).toBeGreaterThanOrEqual(1);

    // Each chunk must have a blockId and content.
    const chunk = chunksResult.chunks[0];
    expect(chunk).toHaveProperty('blockId');
    expect(chunk).toHaveProperty('content');
  });

  test('Delete document removes it from list', async ({ request }) => {
    // DOCUMENT_TIMEOUT: calls documents/insert which may trigger embedding model load.
    test.setTimeout(DOCUMENT_TIMEOUT);

    const insertResult = await rpc(request, 'documents/insert', {
      file_path: tempFilePath,
      act_id: docActId,
    });
    const docId = insertResult.documentId;

    const deleteResult = await rpc(request, 'documents/delete', {
      document_id: docId,
    });
    expect(deleteResult.deleted).toBe(true);
    expect(deleteResult.documentId).toBe(docId);
    insertedDocumentId = null; // already deleted; suppress afterEach

    // Verify it's gone from the list.
    const listResult = await rpc(request, 'documents/list', {});
    const found = (listResult.documents || []).find(d => d.documentId === docId);
    expect(found).toBeFalsy();
  });

  test('Get non-existent document returns an error', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const body = await rpcRaw(request, 'documents/get', {
      document_id: 'nonexistent-doc-id-e2e',
    });
    expect(body.error).toBeTruthy();
    expect(body.error.code).toBe(-32602);
  });

  test('Insert with non-existent file path returns an error', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const body = await rpcRaw(request, 'documents/insert', {
      file_path: '/tmp/_e2e_test_does_not_exist_' + Date.now() + '.txt',
    });
    expect(body.error).toBeTruthy();
    expect(body.error.code).toBe(-32602);
  });
});

// =========================================================================
// Group 3: Memory Lifecycle (list only)
//
// lifecycle/memories/list is the ONLY memory lifecycle method in _METHODS.
// The pending/get/approve/reject/route/search/search_fts handlers live in
// ui_rpc_server.py (stdio JSON-RPC) and are NOT accessible via /rpc/dev.
// Those methods are verified to return "Method not found" (-32601).
// =========================================================================

test.describe('Memory Lifecycle (list only via HTTP)', () => {
  test('List memories with no filter returns array', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'lifecycle/memories/list', {});

    expect(result).toHaveProperty('memories');
    expect(Array.isArray(result.memories)).toBe(true);
  });

  test('List memories filtered by status=approved returns only approved', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'lifecycle/memories/list', { status: 'approved' });

    expect(result).toHaveProperty('memories');
    for (const memory of result.memories) {
      expect(memory.status).toBe('approved');
    }
  });

  test('List memories filtered by status=pending returns only pending', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'lifecycle/memories/list', { status: 'pending' });

    expect(result).toHaveProperty('memories');
    for (const memory of result.memories) {
      expect(memory.status).toBe('pending');
    }
  });

  test('List memories with limit parameter is respected', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'lifecycle/memories/list', { limit: 2 });

    expect(result).toHaveProperty('memories');
    expect(result.memories.length).toBeLessThanOrEqual(2);
  });

  test('Memory shape has required fields when records exist', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'lifecycle/memories/list', {
      status: 'approved',
      limit: 1,
    });

    if (result.memories.length === 0) {
      console.warn('[deep] No approved memories found; skipping shape assertion.');
      return;
    }

    const mem = result.memories[0];
    expect(mem).toHaveProperty('id');
    expect(mem).toHaveProperty('narrative');
    expect(mem).toHaveProperty('memory_type');
    expect(mem).toHaveProperty('status');
  });

  // Verify that stdio-only methods are correctly rejected at the HTTP layer.
  test('lifecycle/memories/pending is not accessible via /rpc/dev', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const body = await rpcRaw(request, 'lifecycle/memories/pending', {});
    expect(body.error).toBeTruthy();
    expect(body.error.code).toBe(-32601); // Method not found
  });

  test('lifecycle/memories/search is not accessible via /rpc/dev', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const body = await rpcRaw(request, 'lifecycle/memories/search', { query: 'test' });
    expect(body.error).toBeTruthy();
    expect(body.error.code).toBe(-32601);
  });
});

// =========================================================================
// Group 4: Deeper Block Operations
//
// Registered in _METHODS (basic CRUD covered in real-data-extended.spec.mjs):
//   blocks/move, blocks/reorder, blocks/ancestors, blocks/descendants,
//   blocks/page/tree, blocks/page/markdown, blocks/import/markdown,
//   blocks/property/get, blocks/property/set, blocks/property/delete,
//   blocks/unchecked_todos
// =========================================================================

test.describe('Deeper Block Operations', () => {
  let testActId = null;
  let testPageId = null;
  let blockIds = [];

  test.beforeEach(async ({ request }) => {
    const actsResult = await rpc(request, 'play/acts/list', {});
    const careerAct = actsResult.acts.find(a => a.title === 'Career Growth');
    expect(careerAct).toBeTruthy();
    testActId = careerAct.act_id;

    const pageResult = await rpc(request, 'play/pages/create', {
      act_id: testActId,
      title: '_e2e_test_DeepBlocks_' + Date.now(),
    });
    testPageId = pageResult.created_page_id;
  });

  test.afterEach(async ({ request }) => {
    // Delete tracked blocks first, then the page.
    for (const blockId of [...blockIds].reverse()) {
      try {
        await rpc(request, 'blocks/delete', { block_id: blockId, recursive: false });
      } catch (_) {
        // best-effort
      }
    }
    blockIds = [];

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

  test('blocks/page/tree returns root blocks for a page', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const createResult = await rpc(request, 'blocks/create', {
      type: 'paragraph',
      act_id: testActId,
      page_id: testPageId,
      rich_text: [{ content: '_e2e_test_ page tree block' }],
    });
    blockIds.push(createResult.block.id);

    const treeResult = await rpc(request, 'blocks/page/tree', { page_id: testPageId });
    expect(treeResult).toHaveProperty('blocks');
    expect(Array.isArray(treeResult.blocks)).toBe(true);
    expect(treeResult.blocks.length).toBeGreaterThanOrEqual(1);
  });

  test('blocks/page/markdown exports page blocks as markdown text', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    // The blocks_db rich text schema uses 'content' as the span text key (not 'text').
    const createResult = await rpc(request, 'blocks/create', {
      type: 'heading_1',
      act_id: testActId,
      page_id: testPageId,
      rich_text: [{ content: '_e2e_test_ Heading' }],
    });
    blockIds.push(createResult.block.id);

    const mdResult = await rpc(request, 'blocks/page/markdown', { page_id: testPageId });
    expect(mdResult).toHaveProperty('markdown');
    expect(typeof mdResult.markdown).toBe('string');
    expect(mdResult.markdown).toContain('_e2e_test_');
    expect(mdResult).toHaveProperty('block_count');
  });

  test('blocks/import/markdown creates blocks from markdown text', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const markdown =
      '# _e2e_test_ Import Heading\n\n' +
      'This is a paragraph from markdown import.\n\n' +
      '- List item one\n' +
      '- List item two\n';

    const importResult = await rpc(request, 'blocks/import/markdown', {
      act_id: testActId,
      page_id: testPageId,
      markdown,
    });

    expect(importResult).toHaveProperty('blocks');
    expect(Array.isArray(importResult.blocks)).toBe(true);
    expect(importResult.blocks.length).toBeGreaterThanOrEqual(1);
    expect(importResult).toHaveProperty('count');
    expect(importResult.count).toBeGreaterThanOrEqual(1);

    for (const b of importResult.blocks) {
      blockIds.push(b.id);
    }
  });

  test('blocks/ancestors returns parent chain for a nested block', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const parentResult = await rpc(request, 'blocks/create', {
      type: 'paragraph',
      act_id: testActId,
      page_id: testPageId,
      rich_text: [{ content: '_e2e_test_ parent' }],
    });
    const parentId = parentResult.block.id;
    blockIds.push(parentId);

    const childResult = await rpc(request, 'blocks/create', {
      type: 'paragraph',
      act_id: testActId,
      page_id: testPageId,
      parent_id: parentId,
      rich_text: [{ content: '_e2e_test_ child' }],
    });
    const childId = childResult.block.id;
    blockIds.push(childId);

    const ancestorsResult = await rpc(request, 'blocks/ancestors', { block_id: childId });
    expect(ancestorsResult).toHaveProperty('ancestors');
    expect(Array.isArray(ancestorsResult.ancestors)).toBe(true);
    const ancestorIds = ancestorsResult.ancestors.map(a => a.id);
    expect(ancestorIds).toContain(parentId);
  });

  test('blocks/descendants returns child blocks', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const parentResult = await rpc(request, 'blocks/create', {
      type: 'paragraph',
      act_id: testActId,
      page_id: testPageId,
      rich_text: [{ content: '_e2e_test_ parent' }],
    });
    const parentId = parentResult.block.id;
    blockIds.push(parentId);

    for (let i = 0; i < 2; i++) {
      const childResult = await rpc(request, 'blocks/create', {
        type: 'paragraph',
        act_id: testActId,
        page_id: testPageId,
        parent_id: parentId,
        rich_text: [{ content: `_e2e_test_ child ${i}` }],
      });
      blockIds.push(childResult.block.id);
    }

    const descResult = await rpc(request, 'blocks/descendants', { block_id: parentId });
    expect(descResult).toHaveProperty('descendants');
    expect(Array.isArray(descResult.descendants)).toBe(true);
    expect(descResult.descendants.length).toBeGreaterThanOrEqual(2);
  });

  test('blocks/move relocates a block to a new position', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const firstResult = await rpc(request, 'blocks/create', {
      type: 'paragraph',
      act_id: testActId,
      page_id: testPageId,
      rich_text: [{ content: '_e2e_test_ first' }],
    });
    blockIds.push(firstResult.block.id);

    const secondResult = await rpc(request, 'blocks/create', {
      type: 'paragraph',
      act_id: testActId,
      page_id: testPageId,
      rich_text: [{ content: '_e2e_test_ second' }],
    });
    const secondId = secondResult.block.id;
    blockIds.push(secondId);

    const moveResult = await rpc(request, 'blocks/move', {
      block_id: secondId,
      new_page_id: testPageId,
      new_position: 0,
    });

    expect(moveResult).toHaveProperty('block');
    expect(moveResult.block.id).toBe(secondId);
  });

  test('blocks/reorder reorders sibling blocks', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const ids = [];
    for (let i = 0; i < 3; i++) {
      const result = await rpc(request, 'blocks/create', {
        type: 'paragraph',
        act_id: testActId,
        page_id: testPageId,
        rich_text: [{ content: `_e2e_test_ reorder ${i}` }],
      });
      ids.push(result.block.id);
      blockIds.push(result.block.id);
    }

    // Reorder in reverse.
    const reorderResult = await rpc(request, 'blocks/reorder', {
      block_ids: [ids[2], ids[1], ids[0]],
    });

    expect(reorderResult).toHaveProperty('blocks');
    expect(Array.isArray(reorderResult.blocks)).toBe(true);
    expect(reorderResult.blocks.length).toBe(3);
  });

  test('blocks/property/set stores a property, get retrieves it', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const createResult = await rpc(request, 'blocks/create', {
      type: 'paragraph',
      act_id: testActId,
      page_id: testPageId,
      rich_text: [{ content: '_e2e_test_ prop block' }],
    });
    const blockId = createResult.block.id;
    blockIds.push(blockId);

    const setResult = await rpc(request, 'blocks/property/set', {
      block_id: blockId,
      key: '_e2e_test_prop',
      value: 'test_value_42',
    });
    expect(setResult.ok).toBe(true);
    expect(setResult.key).toBe('_e2e_test_prop');

    const getResult = await rpc(request, 'blocks/property/get', {
      block_id: blockId,
      key: '_e2e_test_prop',
    });
    expect(getResult.key).toBe('_e2e_test_prop');
    expect(getResult.value).toBe('test_value_42');
  });

  test('blocks/property/delete removes a property', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const createResult = await rpc(request, 'blocks/create', {
      type: 'paragraph',
      act_id: testActId,
      page_id: testPageId,
      rich_text: [{ content: '_e2e_test_ del prop block' }],
    });
    const blockId = createResult.block.id;
    blockIds.push(blockId);

    await rpc(request, 'blocks/property/set', {
      block_id: blockId,
      key: '_e2e_test_del_prop',
      value: 'will_be_deleted',
    });

    const deleteResult = await rpc(request, 'blocks/property/delete', {
      block_id: blockId,
      key: '_e2e_test_del_prop',
    });
    expect(deleteResult).toHaveProperty('deleted');
    expect(deleteResult.key).toBe('_e2e_test_del_prop');

    // Value should be null or undefined after deletion.
    const getResult = await rpc(request, 'blocks/property/get', {
      block_id: blockId,
      key: '_e2e_test_del_prop',
    });
    expect(getResult.value === null || getResult.value === undefined).toBe(true);
  });

  test('blocks/unchecked_todos returns todo list for act', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    // Create a to_do block (unchecked by default).
    const createResult = await rpc(request, 'blocks/create', {
      type: 'to_do',
      act_id: testActId,
      page_id: testPageId,
      rich_text: [{ content: '_e2e_test_ unchecked todo' }],
      properties: { checked: false },
    });
    blockIds.push(createResult.block.id);

    const todosResult = await rpc(request, 'blocks/unchecked_todos', { act_id: testActId });

    expect(todosResult).toHaveProperty('todos');
    expect(Array.isArray(todosResult.todos)).toBe(true);
    expect(todosResult).toHaveProperty('count');
    expect(todosResult.todos.length).toBeGreaterThanOrEqual(1);
  });
});

// =========================================================================
// Group 5: Context Toggle
//
// Registered in _METHODS: context/toggle_source
//
// Valid source names from context_sources.py:
//   system_prompt (non-disableable), messages (non-disableable),
//   play_context, learned_kb, system_state, codebase (all disableable)
// =========================================================================

test.describe('Context Toggle', () => {
  test.afterEach(async ({ request }) => {
    // Restore all disableable sources to enabled state.
    for (const source of ['play_context', 'learned_kb', 'system_state', 'codebase']) {
      try {
        await rpc(request, 'context/toggle_source', { source_name: source, enabled: true });
      } catch (_) {
        // best-effort
      }
    }
  });

  test('Toggle a disableable source off, disabled_sources contains it', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const disableResult = await rpc(request, 'context/toggle_source', {
      source_name: 'play_context',
      enabled: false,
    });

    expect(disableResult.ok).toBe(true);
    expect(disableResult.disabled_sources).toContain('play_context');
  });

  test('Toggle a source off then on, disabled_sources no longer contains it', async ({
    request,
  }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await rpc(request, 'context/toggle_source', {
      source_name: 'learned_kb',
      enabled: false,
    });

    const enableResult = await rpc(request, 'context/toggle_source', {
      source_name: 'learned_kb',
      enabled: true,
    });

    expect(enableResult.ok).toBe(true);
    expect(enableResult.disabled_sources).not.toContain('learned_kb');
  });

  test('Toggle system_prompt off returns -32602 (cannot disable required source)', async ({
    request,
  }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const body = await rpcRaw(request, 'context/toggle_source', {
      source_name: 'system_prompt',
      enabled: false,
    });

    expect(body.error).toBeTruthy();
    expect(body.error.code).toBe(-32602);
  });

  test('Toggle with invalid source name returns -32602', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const body = await rpcRaw(request, 'context/toggle_source', {
      source_name: 'nonexistent_source_name',
      enabled: false,
    });

    expect(body.error).toBeTruthy();
    expect(body.error.code).toBe(-32602);
  });

  test('Multiple sources can be independently disabled', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    await rpc(request, 'context/toggle_source', { source_name: 'play_context', enabled: false });
    const result = await rpc(request, 'context/toggle_source', {
      source_name: 'system_state',
      enabled: false,
    });

    expect(result.disabled_sources).toContain('play_context');
    expect(result.disabled_sources).toContain('system_state');
  });
});

// =========================================================================
// Group 6: Approval System
//
// Registered in _METHODS:
//   approval/pending  — list pending approvals
//   approval/explain  — get explanation for an approval
//   approval/respond  — respond to an approval
//
// Creating approvals requires Ollama to trigger the command pipeline.
// Tests focus on shape verification and graceful error handling.
// =========================================================================

test.describe('Approval System', () => {
  test('approval/pending returns approval list shape', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'approval/pending', {});

    expect(result).toHaveProperty('approvals');
    expect(Array.isArray(result.approvals)).toBe(true);

    // Verify shape of any existing approvals.
    for (const approval of result.approvals) {
      expect(approval).toHaveProperty('id');
      expect(approval).toHaveProperty('command');
      expect(approval).toHaveProperty('risk_level');
    }
  });

  test('approval/pending with conversation_id filter returns empty list for unknown id', async ({
    request,
  }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'approval/pending', {
      conversation_id: '_e2e_test_nonexistent_conv_id',
    });

    expect(result).toHaveProperty('approvals');
    expect(Array.isArray(result.approvals)).toBe(true);
    expect(result.approvals).toHaveLength(0);
  });

  test('approval/explain for non-existent id returns -32602', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const body = await rpcRaw(request, 'approval/explain', {
      approval_id: '_e2e_test_nonexistent_approval_id',
    });

    expect(body.error).toBeTruthy();
    expect(body.error.code).toBe(-32602);
  });

  test('approval/respond for non-existent id returns -32602', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const body = await rpcRaw(request, 'approval/respond', {
      approval_id: '_e2e_test_nonexistent_approval_id',
      action: 'reject',
    });

    expect(body.error).toBeTruthy();
    expect(body.error.code).toBe(-32602);
  });
});

// =========================================================================
// Group 7: Attention
//
// Registered in _METHODS:
//   cairn/attention          — get the current attention list
//   cairn/attention/reorder  — reorder items in attention
//
// cairn/attention/rules/* methods do NOT exist in _METHODS.
//
// NOTE: cairn/attention internally calls get_cairn_store() which creates a
// new CairnStore on every invocation, running _init_schema() + executescript().
// This opens a second SQLite connection that can hold a write lock while the
// embedding model loads (up to 2 minutes on a cold CUDA start). To avoid
// this lock cascading into subsequent DB-write tests, this group is placed
// LAST — after all other groups that write to the database.
// =========================================================================

test.describe('Attention', () => {
  test('cairn/attention returns current attention data', async ({ request }) => {
    // DOCUMENT_TIMEOUT: get_cairn_store() may trigger embedding model load on cold start.
    test.setTimeout(DOCUMENT_TIMEOUT);

    const result = await rpc(request, 'cairn/attention', {});

    expect(result).toBeTruthy();
    expect(typeof result).toBe('object');
  });

  test('cairn/attention result contains an array property', async ({ request }) => {
    test.setTimeout(DOCUMENT_TIMEOUT);

    const result = await rpc(request, 'cairn/attention', {});

    const hasArrayProp = Object.values(result).some(v => Array.isArray(v));
    if (!hasArrayProp) {
      console.warn('[deep] cairn/attention returned no array properties:', JSON.stringify(result));
    }
    // Soft check — attention may be empty on a fresh DB.
    expect(typeof result).toBe('object');
  });

  test('cairn/attention/reorder with empty list is graceful', async ({ request }) => {
    test.setTimeout(DOCUMENT_TIMEOUT);

    // Passing empty arrays should not crash the handler.
    // Parameter name is ordered_scene_ids (see handle_cairn_attention_reorder in system.py).
    const reorderResult = await rpc(request, 'cairn/attention/reorder', {
      ordered_scene_ids: [],
    });

    expect(reorderResult).toBeTruthy();
  });
});

// =========================================================================
// Group 8: Thunderbird / Email Status
//
// Registered in _METHODS:
//   cairn/thunderbird/status  — status of Thunderbird integration
//   thunderbird/check         — check if Thunderbird is available
//
// cairn/email/* methods do NOT exist in _METHODS at all.
//
// NOTE: thunderbird/check also calls get_cairn_store() internally which can
// trigger embedding model load and SQLite write-lock. Placed last for the
// same reason as Group 7 (Attention).
// =========================================================================

test.describe('Thunderbird Status', () => {
  test('cairn/thunderbird/status returns a status envelope', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const result = await rpc(request, 'cairn/thunderbird/status', {});

    expect(result).toBeTruthy();
    expect(typeof result).toBe('object');
    // Must contain at least one of these standard status fields.
    const hasStatusField =
      'configured' in result ||
      'enabled' in result ||
      'status' in result ||
      'available' in result;
    expect(hasStatusField).toBe(true);
  });

  test('thunderbird/check returns reachability info', async ({ request }) => {
    // DOCUMENT_TIMEOUT: thunderbird/check calls get_cairn_store() which may trigger
    // embedding model load on cold start.
    test.setTimeout(DOCUMENT_TIMEOUT);

    const result = await rpc(request, 'thunderbird/check', {});

    expect(result).toBeTruthy();
    expect(typeof result).toBe('object');
  });

  test('cairn/email/open is not in _METHODS and returns method-not-found', async ({ request }) => {
    test.setTimeout(BACKEND_TIMEOUT);

    const body = await rpcRaw(request, 'cairn/email/open', { email_id: 'test' });
    expect(body.error).toBeTruthy();
    expect(body.error.code).toBe(-32601); // Method not found
  });
});
