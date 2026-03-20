-- Migration 005: Clean up orphaned attachments
--
-- Attachments table can contain rows referencing acts/scenes that no longer
-- exist. This migration deletes orphaned rows where the parent act is gone.
--
-- Play tables (acts, scenes, attachments) are created lazily by play_db,
-- not by the migration system. We guard with CREATE TABLE IF NOT EXISTS
-- so the DELETE statements have valid targets on any database.

CREATE TABLE IF NOT EXISTS acts (
    act_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    repo_path TEXT,
    artifact_type TEXT,
    code_config TEXT,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    color TEXT,
    root_block_id TEXT,
    system_role TEXT
);

CREATE TABLE IF NOT EXISTS attachments (
    attachment_id TEXT PRIMARY KEY,
    act_id TEXT REFERENCES acts(act_id) ON DELETE CASCADE,
    scene_id TEXT,
    file_path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_type TEXT NOT NULL,
    added_at TEXT NOT NULL
);

DELETE FROM attachments
WHERE act_id NOT IN (SELECT act_id FROM acts);

SELECT 1;
