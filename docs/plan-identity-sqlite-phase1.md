# Plan: Identity SQLite Phase 1 — Read Your Story Core from Blocks

## Context

`build_identity_model()` in `identity.py` (line 95) calls `play_fs.read_me_markdown()`, which
reads `~/.talkingrock/play/me.md` from the filesystem. This file is the "core" string
passed to `IdentityModel(core=...)`.

The block editor already stores Your Story content in SQLite. When a user edits the
Your Story page in the block editor, blocks are written to the `blocks` table with
`act_id = 'your-story'` and linked to a `page_id` from the `pages` table. The existing
sync in `play_fs.kb_write_apply()` (lines 893–901) keeps `me.md` in lockstep with the
KB file, but this is a one-way write path from the KB editor — it does not reflect the
block editor's content.

The goal of Phase 1: change `identity.py` to read Your Story content from SQLite blocks
instead of `me.md`, using the existing rendering pipeline.

### Current read path
```
build_identity_model()
  → play_fs.read_me_markdown()
    → _read_text(_me_path())        # reads ~/.talkingrock/play/me.md
```

### Target read path
```
build_identity_model()
  → read_your_story_from_blocks()   # new function
    → play_db.list_pages(act_id='your-story')   # find root page(s)
    → blocks_db.list_blocks(page_id=page_id)    # get root-level blocks
    → blocks_db.get_page_blocks(page_id, recursive=True)  # with children
    → markdown_renderer.render_markdown(blocks)  # blocks → markdown string
```

### What already exists (no new wheels needed)
- `blocks_db.get_page_blocks(page_id, recursive=True)` — loads a page's full block tree
  (`src/cairn/play/blocks_db.py:675–691`)
- `markdown_renderer.render_markdown(blocks)` — renders `list[Block]` to a markdown string
  (`src/cairn/play/markdown_renderer.py:13–33`)
- `play_db.list_pages(act_id, parent_page_id=None)` — returns root pages for an act
  (`src/cairn/play_db.py:3169–3188`)
- `YOUR_STORY_ACT_ID = "your-story"` — constant in both `play_fs.py:77` and `play_db.py:1870`

### Callers of `read_me_markdown()` (all affected by this migration)
Evidence from grep:
- `src/cairn/cairn/identity.py:95` — PRIMARY TARGET of this plan
- `src/cairn/agent.py:1108` — agent context building (Phase 2 scope)
- `src/cairn/services/context_service.py:219` — context service (Phase 2 scope)
- `src/cairn/rpc_handlers/context.py:74` — RPC context stats (Phase 2 scope)
- `src/cairn/rpc_handlers/play.py:107` — `handle_play_me_read` RPC handler (Phase 2 scope)

Phase 1 is scoped to `identity.py` only. The other callers retain the filesystem path
until Phase 2, giving a safe migration window.

---

## Approach (Recommended): New function in `play_fs.py`, fallback to `me.md`

Add `read_your_story_from_blocks()` to `play_fs.py`. Call it from `identity.py` in place
of `read_me_markdown()`, with a fallback to `read_me_markdown()` if no blocks are found.

**Why this wins over the alternatives:**
- Follows the existing pattern: `play_fs.py` is the gateway to all Play data reads;
  `identity.py` already imports `play_fs`
- The fallback preserves safety for users who have data only in `me.md` and have not
  yet used the block editor
- All block-to-markdown conversion is already implemented; this is assembly, not invention
- Keeps `identity.py` import-clean — it already imports `play_fs`; no new imports needed
  in that file

**Trade-offs:**
- The function lives in `play_fs.py` which already imports `play_db`; adding imports of
  `blocks_db` and `markdown_renderer` is a small additional coupling. These are already
  siblings in the `play/` package.
- Fallback logic means two sources of truth can co-exist briefly, but this is intentional
  for safety and is clearly documented.

---

## Alternatives Considered

### Alternative A: Inline the logic directly in `identity.py`

Import `play_db`, `blocks_db`, and `markdown_renderer` directly in `identity.py`.

**Rejected because:** `identity.py` currently has zero SQLite coupling — it delegates all
data access to `play_fs`. Breaking that encapsulation is a bigger architectural footprint
for a Phase 1 change. It also scatters the "how to read Your Story" logic across two files.

### Alternative B: Add a method to `blocks_db.py`

Add `read_act_root_markdown(act_id)` to `blocks_db.py`.

**Rejected because:** `blocks_db.py` is a pure CRUD layer with no rendering logic.
Pulling `markdown_renderer` into it reverses the dependency direction
(`blocks_db` → `markdown_renderer` already exists at render time, but introducing it
at the CRUD layer conflates persistence and presentation). The rendering belongs above
the CRUD layer.

---

## Implementation Steps

### Step 1 — Add `read_your_story_from_blocks()` to `play_fs.py`

**File:** `src/cairn/play_fs.py`

Add the new function after the existing `read_me_markdown()` (currently at line 293).
Insert at approximately line 297 (after `write_me_markdown`).

```python
def read_your_story_from_blocks() -> str:
    """Read Your Story content from SQLite blocks, falling back to me.md.

    The block editor stores content in the blocks table. This function renders
    all root-page blocks for the 'your-story' act to markdown. If no blocks
    exist (user has not yet used the block editor), falls back to me.md.

    Returns:
        Markdown string of Your Story content.
    """
    from . import play_db
    from .play.blocks_db import get_page_blocks
    from .play.markdown_renderer import render_markdown

    try:
        pages = play_db.list_pages(YOUR_STORY_ACT_ID)
        if pages:
            # Use the first root page (positional order)
            page_id = pages[0]["page_id"]
            blocks = get_page_blocks(page_id, recursive=True)
            if blocks:
                return render_markdown(blocks)
    except Exception:
        logger.debug(
            "Failed to read Your Story from blocks, falling back to me.md",
            exc_info=True,
        )

    # Fallback: read from filesystem (legacy path)
    return read_me_markdown()
```

Note: `logger` is already defined at module level in `play_fs.py` (confirm at line ~33).
The deferred imports (`from . import play_db` etc.) follow the existing pattern used in
`ensure_your_story_act()` at line 285 which does `from . import play_db`.

### Step 2 — Update `identity.py` to call the new function

**File:** `src/cairn/cairn/identity.py`

Change lines 95–96:

Before:
```python
core = play_fs.read_me_markdown()
logger.debug("Read core identity from me.md: %d chars", len(core))
```

After:
```python
core = play_fs.read_your_story_from_blocks()
logger.debug("Read core identity from blocks/me.md: %d chars", len(core))
```

No import changes needed — `play_fs` is already imported at line 27.

### Step 3 — Update tests

**File:** `tests/test_play_fs.py`

The existing `TestMeMarkdown` class tests `read_me_markdown` directly (lines 265–283).
These are not broken by this change — `read_me_markdown` still exists.

Add a new test class `TestReadYourStoryFromBlocks` in the same file:

- `test_falls_back_to_me_md_when_no_pages()` — assert that when there are no pages for
  `your-story`, the function returns the same content as `read_me_markdown()`
- `test_returns_block_content_when_pages_exist()` — create a page for `your-story`,
  insert a paragraph block, assert the rendered markdown is returned
- `test_falls_back_on_db_error()` — patch `play_db.list_pages` to raise, assert fallback
  to `read_me_markdown()` is returned without exception

**File:** `tests/test_e2e_cairn.py`

The test at line 456 (`test_read_me_markdown_with_real_structure`) exercises the full
`build_identity_model` path. After this change, `build_identity_model` calls
`read_your_story_from_blocks`, which will fall back to `read_me_markdown` in tests that
don't set up blocks — so existing tests are unaffected. Confirm by running the suite.

---

## Files Affected

| File | Change | Type |
|------|--------|------|
| `src/cairn/cairn/identity.py` | Line 95: call `read_your_story_from_blocks()` instead of `read_me_markdown()` | Modify |
| `src/cairn/play_fs.py` | Add `read_your_story_from_blocks()` after `write_me_markdown()` (~line 297) | Modify |
| `tests/test_play_fs.py` | Add `TestReadYourStoryFromBlocks` test class | Modify |

Files NOT changed in Phase 1:
- `src/cairn/agent.py` (still calls `read_me_markdown` directly — Phase 2)
- `src/cairn/services/context_service.py` (still calls `read_me_markdown` — Phase 2)
- `src/cairn/rpc_handlers/context.py` (still calls `read_me_markdown` — Phase 2)
- `src/cairn/rpc_handlers/play.py` (still calls `read_me_markdown` — Phase 2)

---

## Risks & Mitigations

### Risk 1: Your Story act has multiple root pages
The query `play_db.list_pages(YOUR_STORY_ACT_ID)` with `parent_page_id=None` returns all
root-level pages ordered by `position ASC, created_at ASC`. Taking `pages[0]` gives the
first by position. If multiple root pages exist (unusual but possible), content from
subsequent pages is silently ignored.

**Mitigation:** Phase 1 only reads the first page. Log a debug warning if `len(pages) > 1`.
If this becomes a problem in practice, Phase 2 can concatenate all root pages.

### Risk 2: Blocks exist but page has no blocks (empty block editor)
If the user opened the block editor and immediately closed it, a page row may exist with
no blocks. `get_page_blocks` returns `[]`, `render_markdown([])` returns `""`. The
`if blocks:` guard catches this and falls back to `me.md`.

**Mitigation:** The `if blocks:` check is explicit in the implementation above.

### Risk 3: `_load_children_recursive` performance with 3,376 total blocks
`get_page_blocks(recursive=True)` calls `_load_children_recursive` which issues one
`list_blocks(parent_id=block_id)` query per block. For a typical Your Story page with
~20–50 blocks, this is 20–50 round trips. Not a concern for a synchronous identity build,
but worth noting.

**Mitigation:** No action needed for Phase 1. If profiling ever shows this as hot, the
fix is a single recursive CTE query in `blocks_db.py`. That is out of scope here.

### Risk 4: `markdown_renderer` silently drops blocks with unrecognized `BlockType`
The renderer's `else` branch (line 61) falls back to `_render_paragraph`. This is safe
but means non-standard block types render as plain text rather than nothing. This is
acceptable for an identity context string.

### Risk 5: Circular imports
`play_fs.py` uses deferred imports for `play_db` already (line 285). The same deferred
import pattern for `play.blocks_db` and `play.markdown_renderer` avoids any import cycle.
Evidence: `markdown_renderer` already imports from `play_db` (line 197 of
`markdown_renderer.py`), and `play_fs.py` is not imported by either of those modules.

**Mitigation:** Use deferred imports inside the function body, matching the existing
pattern in `ensure_your_story_act()`.

---

## Testing Strategy

### Unit tests (`tests/test_play_fs.py`)

1. **Fallback test** — with a real SQLite but no pages for `your-story`, assert
   `read_your_story_from_blocks()` returns the same string as `read_me_markdown()`.
2. **Happy path test** — create a page via `play_db.create_page(act_id='your-story', ...)`,
   create a paragraph block via `blocks_db.create_block(...)`, assert the rendered
   markdown is returned (not the `me.md` content).
3. **Error fallback test** — monkeypatch `play_db.list_pages` to raise `Exception`,
   assert the function returns `read_me_markdown()` without raising.
4. **Empty blocks fallback test** — create a page but no blocks, assert fallback to
   `read_me_markdown()`.

Use the existing `initialized_fs` fixture from `test_play_fs.py` for filesystem setup.

### Regression: existing test suite

Run `PYTHONPATH="/home/kellogg/dev/Cairn/src" .venv/bin/python3 -m pytest tests/test_play_fs.py tests/test_e2e_cairn.py tests/test_coherence.py -x --tb=short -q --no-cov`

All passing tests must continue to pass. The key risk is `test_read_me_markdown_with_real_structure` in `test_e2e_cairn.py` (line 456) and `test_build_identity_model` (line 512). Both call `build_identity_model()`, which now calls `read_your_story_from_blocks()`. In test environments that don't set up blocks, the fallback path returns `me.md` content — behavior is unchanged.

---

## Definition of Done

- [ ] `read_your_story_from_blocks()` added to `play_fs.py` with fallback and deferred imports
- [ ] `build_identity_model()` in `identity.py` calls `read_your_story_from_blocks()` at line 95
- [ ] Log message at line 96 updated to say "blocks/me.md" not "me.md"
- [ ] 4 new unit tests in `test_play_fs.py`: fallback, happy path, error fallback, empty-blocks fallback
- [ ] Full test suite passes (2232+ tests, 0 failures)
- [ ] `ruff check` and `ruff format` pass on changed files
- [ ] `mypy src/` passes (return type of `read_your_story_from_blocks` is `str`, matching `read_me_markdown`)
