/**
 * MemoryBlock - Renders a memory block with type badge, status indicator,
 * and approve/reject controls for pending_review memories.
 */

import { useState, useEffect } from 'react';
import type { Block } from '../types';

interface MemoryData {
  id: string;
  narrative: string;
  memory_type: string | null;
  status: string;
  signal_count: number;
  block_id: string;
}

interface MemoryBlockProps {
  block: Block;
  onUpdate?: (block: Block) => void;
  onDelete?: (blockId: string) => void;
  isEditing?: boolean;
  depth?: number;
  kernelRequest?: (method: string, params: Record<string, unknown>) => Promise<unknown>;
}

// Color palette for memory types
const MEMORY_TYPE_COLORS: Record<string, { bg: string; text: string; border: string; label: string }> = {
  fact: {
    bg: 'rgba(59, 130, 246, 0.15)',
    text: '#60a5fa',
    border: 'rgba(59, 130, 246, 0.3)',
    label: 'Fact',
  },
  preference: {
    bg: 'rgba(139, 92, 246, 0.15)',
    text: '#a78bfa',
    border: 'rgba(139, 92, 246, 0.3)',
    label: 'Preference',
  },
  priority: {
    bg: 'rgba(245, 158, 11, 0.15)',
    text: '#fbbf24',
    border: 'rgba(245, 158, 11, 0.3)',
    label: 'Priority',
  },
  commitment: {
    bg: 'rgba(239, 68, 68, 0.15)',
    text: '#f87171',
    border: 'rgba(239, 68, 68, 0.3)',
    label: 'Commitment',
  },
  relationship: {
    bg: 'rgba(34, 197, 94, 0.15)',
    text: '#4ade80',
    border: 'rgba(34, 197, 94, 0.3)',
    label: 'Relationship',
  },
  unknown: {
    bg: 'rgba(255, 255, 255, 0.05)',
    text: 'rgba(255, 255, 255, 0.4)',
    border: 'rgba(255, 255, 255, 0.1)',
    label: 'Memory',
  },
};

// Status dot colors
const STATUS_COLORS: Record<string, string> = {
  pending_review: '#f59e0b',
  approved: '#22c55e',
  rejected: '#ef4444',
  superseded: 'rgba(255, 255, 255, 0.3)',
};

const STATUS_LABELS: Record<string, string> = {
  pending_review: 'Pending Review',
  approved: 'Approved',
  rejected: 'Rejected',
  superseded: 'Superseded',
};

interface ByActPageResult {
  memories: MemoryData[];
  memories_page_id: string | null;
}

export function MemoryBlock({
  block,
  isEditing = false,
  kernelRequest,
}: MemoryBlockProps) {
  const [memoryData, setMemoryData] = useState<MemoryData | null>(null);
  const [isActing, setIsActing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  // Fetch memory metadata using act_id + block.id correlation
  useEffect(() => {
    if (!kernelRequest || !block.act_id) return;

    let cancelled = false;

    async function fetchMemoryData() {
      try {
        const result = (await kernelRequest!('lifecycle/memories/by_act_page', {
          act_id: block.act_id,
        })) as ByActPageResult;

        if (cancelled) return;

        const match = (result.memories ?? []).find((m) => m.block_id === block.id);
        if (match) {
          setMemoryData(match);
        }
      } catch (e) {
        // Memory data unavailable; render with block-level fallback
        console.warn('MemoryBlock: failed to load memory metadata:', e);
      }
    }

    void fetchMemoryData();
    return () => { cancelled = true; };
  }, [block.id, block.act_id, kernelRequest]);

  // Narrative: prefer fetched data, fall back to block rich_text plain text
  const richTextNarrative = block.rich_text.map((s) => s.content).join('');
  const narrative = (memoryData?.narrative ?? richTextNarrative) || '(No narrative)';

  const memoryType = memoryData?.memory_type ?? null;
  const status = memoryData?.status ?? 'pending_review';
  const signalCount = memoryData?.signal_count ?? null;
  const memoryId = memoryData?.id ?? null;

  const typeInfo = MEMORY_TYPE_COLORS[memoryType ?? 'unknown'] ?? MEMORY_TYPE_COLORS.unknown;
  const statusColor = STATUS_COLORS[status] ?? STATUS_COLORS.pending_review;
  const statusLabel = STATUS_LABELS[status] ?? status;

  async function handleApprove() {
    if (!kernelRequest || !memoryId) return;
    setIsActing(true);
    setActionError(null);
    try {
      await kernelRequest('lifecycle/memories/approve', { memory_id: memoryId });
      setMemoryData((prev) => prev ? { ...prev, status: 'approved' } : prev);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Approve failed');
    } finally {
      setIsActing(false);
    }
  }

  async function handleReject() {
    if (!kernelRequest || !memoryId) return;
    setIsActing(true);
    setActionError(null);
    try {
      await kernelRequest('lifecycle/memories/reject', { memory_id: memoryId });
      setMemoryData((prev) => prev ? { ...prev, status: 'rejected' } : prev);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Reject failed');
    } finally {
      setIsActing(false);
    }
  }

  return (
    <div
      style={{
        padding: '12px 16px',
        background: typeInfo.bg,
        borderRadius: '8px',
        border: `1px solid ${typeInfo.border}`,
        margin: '0.5em 0',
      }}
    >
      {/* Header row: type badge + status dot */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          marginBottom: '8px',
        }}
      >
        {/* Memory type badge */}
        <span
          style={{
            padding: '2px 8px',
            background: 'rgba(0, 0, 0, 0.25)',
            color: typeInfo.text,
            fontSize: '11px',
            fontWeight: 600,
            borderRadius: '4px',
            border: `1px solid ${typeInfo.border}`,
            textTransform: 'uppercase',
            letterSpacing: '0.4px',
          }}
        >
          {typeInfo.label}
        </span>

        {/* Status dot + label */}
        <span
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            fontSize: '11px',
            color: 'rgba(255, 255, 255, 0.5)',
          }}
          title={statusLabel}
        >
          <span
            style={{
              display: 'inline-block',
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              background: statusColor,
              flexShrink: 0,
            }}
          />
          {statusLabel}
        </span>

        {/* Signal count */}
        {signalCount !== null && signalCount > 1 && (
          <span
            style={{
              fontSize: '11px',
              color: 'rgba(255, 255, 255, 0.4)',
              marginLeft: 'auto',
            }}
            title={`Reinforced ${signalCount} times`}
          >
            x{signalCount}
          </span>
        )}
      </div>

      {/* Narrative text */}
      <div
        style={{
          color: '#e5e7eb',
          fontSize: '14px',
          lineHeight: 1.6,
        }}
      >
        {narrative}
      </div>

      {/* Approve/Reject controls for pending_review (only when kernelRequest available) */}
      {status === 'pending_review' && kernelRequest && memoryId && (
        <div
          style={{
            display: 'flex',
            gap: '8px',
            marginTop: '10px',
          }}
        >
          <button
            onClick={() => void handleApprove()}
            disabled={isActing}
            style={{
              padding: '4px 12px',
              border: '1px solid rgba(34, 197, 94, 0.4)',
              borderRadius: '4px',
              background: 'rgba(34, 197, 94, 0.1)',
              color: '#22c55e',
              fontSize: '12px',
              fontWeight: 500,
              cursor: isActing ? 'wait' : 'pointer',
              opacity: isActing ? 0.6 : 1,
            }}
          >
            Approve
          </button>
          <button
            onClick={() => void handleReject()}
            disabled={isActing}
            style={{
              padding: '4px 12px',
              border: '1px solid rgba(239, 68, 68, 0.4)',
              borderRadius: '4px',
              background: 'rgba(239, 68, 68, 0.1)',
              color: '#f87171',
              fontSize: '12px',
              fontWeight: 500,
              cursor: isActing ? 'wait' : 'pointer',
              opacity: isActing ? 0.6 : 1,
            }}
          >
            Reject
          </button>
          {actionError && (
            <span
              style={{
                fontSize: '11px',
                color: '#f87171',
                alignSelf: 'center',
              }}
            >
              {actionError}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export default MemoryBlock;
