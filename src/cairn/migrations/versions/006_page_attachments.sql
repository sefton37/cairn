-- Migration 006: Add page_id column to attachments table
-- Enables attaching files directly to knowledgebase pages.

ALTER TABLE attachments ADD COLUMN page_id TEXT REFERENCES pages(page_id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS idx_attachments_page ON attachments(page_id);
