"""Chat RPC handlers.

These handlers manage chat interactions with the AI agent.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from cairn.agent import ChatAgent
from cairn.db import Database

from .approvals import handle_approval_respond

# =============================================================================
# Chat Handlers
# =============================================================================


def _slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_-]+', '-', slug)
    return slug[:50]  # Limit length


def handle_chat_respond(
    db: Database,
    *,
    text: str,
    conversation_id: str | None = None,
    use_code_mode: bool = False,
    agent_type: str | None = None,
    extended_thinking: bool | None = None,
) -> dict[str, Any]:
    """Process a chat message and get AI response."""
    agent = ChatAgent(db=db, use_code_mode=use_code_mode)

    # Check for conversational intents (Phase 6)
    if conversation_id:
        intent = agent.detect_intent(text)

        if intent:
            # Handle approval/rejection of pending approvals
            if intent.intent_type in ("approval", "rejection"):
                pending = agent.get_pending_approval_for_conversation(conversation_id)
                if pending:
                    action = "approve" if intent.intent_type == "approval" else "reject"
                    result = handle_approval_respond(
                        db,
                        approval_id=str(pending["id"]),
                        action=action,
                    )
                    # Return a synthetic response
                    message_id = uuid.uuid4().hex[:12]
                    if action == "approve":
                        if result.get("status") == "executed":
                            answer = f"Command executed. Return code: {result.get('result', {}).get('return_code', 'unknown')}"
                        else:
                            answer = f"Command execution failed: {result.get('result', {}).get('error', 'unknown error')}"
                    else:
                        answer = "Command rejected."

                    # Store the response
                    db.add_message(
                        message_id=message_id,
                        conversation_id=conversation_id,
                        role="assistant",
                        content=answer,
                        message_type="text",
                    )

                    return {
                        "answer": answer,
                        "conversation_id": conversation_id,
                        "message_id": message_id,
                        "message_type": "text",
                        "tool_calls": [],
                        "thinking_steps": [],
                        "pending_approval_id": None,
                        "intent_handled": intent.intent_type,
                    }

            # Handle reference resolution
            if intent.intent_type == "reference" and intent.reference_term:
                resolved = agent.resolve_reference(intent.reference_term, conversation_id)
                if resolved:
                    # Expand the text to include the resolved entity
                    text = text.replace(
                        intent.reference_term,
                        f"{intent.reference_term} ({resolved.get('type', '')}: {resolved.get('name', resolved.get('id', ''))})"
                    )

    response = agent.respond(
        text,
        conversation_id=conversation_id,
        agent_type=agent_type,
        extended_thinking=extended_thinking,
    )

    # Fire turn assessment asynchronously — zero latency impact on the caller.
    _maybe_submit_turn_assessment(
        user_message=text,
        cairn_response=response.answer,
    )

    return {
        "answer": response.answer,
        "conversation_id": response.conversation_id,
        "message_id": response.message_id,
        "message_type": response.message_type,
        "tool_calls": response.tool_calls,
        "thinking_steps": response.thinking_steps,
        "pending_approval_id": response.pending_approval_id,
        "extended_thinking_trace": response.extended_thinking_trace,
        "user_message_id": response.user_message_id,
    }


def _maybe_submit_turn_assessment(
    *,
    user_message: str,
    cairn_response: str,
) -> None:
    """Submit a turn for background assessment if an active lifecycle conversation exists.

    Imports lazily to avoid circular imports. Silently no-ops when:
    - The reos.services imports are unavailable
    - No active lifecycle conversation exists (soft bridge between DB systems)
    - Any other unexpected error occurs

    This must never raise — it runs after a response is already generated.
    """
    try:
        # Lazy imports to avoid circular dependency at module load time.
        from cairn.services.conversation_service import ConversationService
        from cairn.services.turn_delta_assessor import get_turn_assessment_queue

        conv_service = ConversationService()
        active = conv_service.get_active()
        if active is None:
            # No lifecycle conversation open — skip silently.
            return

        queue = get_turn_assessment_queue()
        turn_position = active.message_count  # approximate position after this turn

        queue.submit(
            conversation_id=active.id,
            turn_position=turn_position,
            user_message=user_message,
            cairn_response=cairn_response,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(
            "Turn assessment submission skipped: %s", e
        )


def handle_conversations_list(
    db: Database,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    """List recent conversations for the PWA conversation picker."""
    rows = db.iter_conversations(limit=limit)
    return {"conversations": rows}


def handle_conversation_messages(
    db: Database,
    *,
    conversation_id: str,
    limit: int = 50,
) -> dict[str, Any]:
    """Get messages for a conversation to restore chat history in the PWA."""
    rows = db.get_messages(conversation_id=conversation_id, limit=limit)
    return {"messages": rows, "conversation_id": conversation_id}


def handle_chat_clear(
    db: Database,
    *,
    conversation_id: str,
) -> dict[str, Any]:
    """Clear (delete) a conversation without archiving."""
    # Delete all messages in the conversation (uses proper Database method)
    db.clear_messages(conversation_id=conversation_id)
    # Delete the conversation itself
    with db.transaction() as conn:
        conn.execute(
            "DELETE FROM conversations WHERE id = ?",
            (conversation_id,),
        )
    return {"ok": True}
