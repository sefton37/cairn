"""Chat handlers.

Manages chat/respond, chat/clear, and intent detection.
"""

from __future__ import annotations

from typing import Any

from reos.agent import ChatAgent
from reos.db import Database
from reos.rpc.router import register
from reos.rpc.types import RpcError


@register("chat/respond", needs_db=True)
def handle_respond(
    db: Database,
    *,
    text: str,
    conversation_id: str | None = None,
    use_code_mode: bool = False,
    agent_type: str | None = None,
    extended_thinking: bool | None = None,
) -> dict[str, Any]:
    """Process a chat message and return a response.

    Args:
        text: The user's message text
        conversation_id: Optional conversation ID for context
        use_code_mode: Whether to use code mode (RIVA) - default is conversational (CAIRN)
        agent_type: Explicit agent type ('cairn', 'riva', 'reos')
        extended_thinking: None=auto, True=force, False=disable
    """
    from reos.rpc.handlers.approvals import handle_respond as approval_respond

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
                    result = approval_respond(
                        db,
                        approval_id=str(pending["id"]),
                        action=action,
                    )
                    # Return a synthetic response
                    import uuid
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
    return {
        "answer": response.answer,
        "conversation_id": response.conversation_id,
        "message_id": response.message_id,
        "message_type": response.message_type,
        "tool_calls": response.tool_calls,
        "thinking_steps": response.thinking_steps,
        "pending_approval_id": response.pending_approval_id,
        "extended_thinking_trace": response.extended_thinking_trace,
    }


@register("chat/clear", needs_db=True)
def handle_clear(
    db: Database,
    *,
    conversation_id: str,
) -> dict[str, Any]:
    """Clear (delete) a conversation without archiving."""
    # Delete all messages in the conversation
    db.execute(
        "DELETE FROM messages WHERE conversation_id = ?",
        (conversation_id,),
    )
    # Delete the conversation itself
    db.execute(
        "DELETE FROM conversations WHERE conversation_id = ?",
        (conversation_id,),
    )
    return {"ok": True}


@register("intent/detect", needs_db=True)
def handle_intent_detect(
    db: Database,
    *,
    text: str,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """Detect the intent of a user message."""
    agent = ChatAgent(db=db)
    intent = agent.detect_intent(text)

    if not intent:
        return {"detected": False}

    result: dict[str, Any] = {
        "detected": True,
        "intent_type": intent.intent_type,
        "confidence": intent.confidence,
    }

    if intent.choice_number is not None:
        result["choice_number"] = intent.choice_number

    if intent.reference_term:
        result["reference_term"] = intent.reference_term

        # Try to resolve the reference if we have a conversation
        if conversation_id:
            resolved = agent.resolve_reference(intent.reference_term, conversation_id)
            if resolved:
                result["resolved_entity"] = resolved

    return result
