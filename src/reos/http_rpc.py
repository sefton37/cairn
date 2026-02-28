"""FastAPI APIRouter that bridges the PWA to the existing RPC handler functions.

This module is the HTTP-facing twin of ui_rpc_server.py.  Where that server
speaks JSON-RPC 2.0 over stdio (Tauri IPC), this one speaks JSON-RPC 2.0 over
HTTP — needed by the Progressive Web App which cannot use native IPC.

Auth model differs from the Tauri path:
- Tauri: Polkit native dialog, session token injected by Rust into every RPC
  params dict as `__session`.
- PWA: PAM via python-pam, session token returned as a Bearer token, validated
  on every request via the `require_auth` FastAPI dependency.

The dispatcher is a flat `_METHODS` registry mapping JSON-RPC method names to
`(handler, needs_db)` pairs so adding a new handler is a one-line change.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from reos import auth
from reos.db import Database, get_db
from reos.mcp_tools import ToolError, call_tool
from reos.rpc_handlers import RpcError
from reos.rpc_handlers.approvals import (
    handle_approval_explain,
    handle_approval_pending,
    handle_approval_respond,
)
from reos.rpc_handlers.archive import (
    handle_archive_assess,
    handle_archive_feedback,
    handle_archive_get,
    handle_archive_learning_stats,
    handle_archive_list,
    handle_conversation_archive,
    handle_conversation_archive_confirm,
    handle_conversation_archive_preview,
    handle_conversation_delete,
)
from reos.rpc_handlers.blocks import (
    handle_blocks_ancestors,
    handle_blocks_create,
    handle_blocks_create_scene,
    handle_blocks_delete,
    handle_blocks_descendants,
    handle_blocks_get,
    handle_blocks_import_markdown,
    handle_blocks_list,
    handle_blocks_move,
    handle_blocks_page_markdown,
    handle_blocks_page_tree,
    handle_blocks_property_delete,
    handle_blocks_property_get,
    handle_blocks_property_set,
    handle_blocks_reorder,
    handle_blocks_rich_text_get,
    handle_blocks_rich_text_set,
    handle_blocks_search,
    handle_blocks_unchecked_todos,
    handle_blocks_update,
    handle_blocks_validate_scene,
)
from reos.rpc_handlers.chat import (
    handle_chat_clear,
    handle_chat_respond,
    handle_conversation_messages,
    handle_conversations_list,
)
from reos.rpc_handlers.consciousness import (
    handle_cairn_chat_async,
    handle_cairn_chat_status,
    handle_consciousness_persist,
    handle_consciousness_poll,
    handle_consciousness_snapshot,
    handle_consciousness_start,
    handle_handoff_validate_all,
)
from reos.rpc_handlers.context import handle_context_stats, handle_context_toggle_source
from reos.rpc_handlers.documents import (
    handle_documents_delete,
    handle_documents_get,
    handle_documents_get_chunks,
    handle_documents_insert,
    handle_documents_list,
)
from reos.rpc_handlers.execution import (
    handle_code_diff_apply,
    handle_code_diff_reject,
    handle_code_exec_state,
    handle_code_plan_approve,
    handle_code_plan_result,
    handle_code_plan_start,
    handle_code_plan_state,
    handle_execution_kill,
    handle_execution_status,
    handle_plan_preview,
)
from reos.rpc_handlers.health import (
    handle_health_acknowledge,
    handle_health_findings,
    handle_health_status,
)
from reos.rpc_handlers.memory import (
    handle_memory_auto_link,
    handle_memory_extract_relationships,
    handle_memory_index_batch,
    handle_memory_index_block,
    handle_memory_learn_from_feedback,
    handle_memory_path,
    handle_memory_related,
    handle_memory_relationships_create,
    handle_memory_relationships_delete,
    handle_memory_relationships_list,
    handle_memory_relationships_update,
    handle_memory_remove_index,
    handle_memory_search,
    handle_memory_stats,
)
from reos.rpc_handlers.personas import handle_persona_upsert, handle_personas_list
from reos.rpc_handlers.play import (
    handle_play_acts_assign_repo,
    handle_play_acts_create,
    handle_play_acts_delete,
    handle_play_acts_list,
    handle_play_acts_set_active,
    handle_play_acts_update,
    handle_play_attachments_add,
    handle_play_attachments_list,
    handle_play_attachments_remove,
    handle_play_kb_list,
    handle_play_kb_read,
    handle_play_kb_write_apply,
    handle_play_kb_write_preview,
    handle_play_me_read,
    handle_play_me_write,
    handle_play_pages_content_read,
    handle_play_pages_content_write,
    handle_play_pages_create,
    handle_play_pages_delete,
    handle_play_pages_list,
    handle_play_pages_move,
    handle_play_pages_tree,
    handle_play_pages_update,
    handle_play_scenes_create,
    handle_play_scenes_delete,
    handle_play_scenes_list,
    handle_play_scenes_list_all,
    handle_play_scenes_update,
)
from reos.rpc_handlers.providers import (
    handle_ollama_check_installed,
    handle_ollama_model_info,
    handle_ollama_pull_start,
    handle_ollama_pull_status,
    handle_ollama_set_context,
    handle_ollama_set_gpu,
    handle_ollama_set_model,
    handle_ollama_set_url,
    handle_ollama_status,
    handle_ollama_test_connection,
    handle_providers_list,
    handle_providers_set,
)
from reos.rpc_handlers.reasoning import (
    handle_reasoning_chain_get,
    handle_reasoning_chains_list,
    handle_reasoning_feedback,
)
from reos.rpc_handlers.safety import (
    handle_safety_set_command_length,
    handle_safety_set_max_iterations,
    handle_safety_set_rate_limit,
    handle_safety_set_sudo_limit,
    handle_safety_set_wall_clock_timeout,
    handle_safety_settings,
)
from reos.rpc_handlers.system import (
    handle_autostart_get,
    handle_autostart_set,
    handle_cairn_attention,
    handle_cairn_thunderbird_status,
    handle_system_live_state,
    handle_thunderbird_check,
    handle_thunderbird_configure,
    handle_thunderbird_decline,
    handle_thunderbird_reset,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

_bearer_scheme = HTTPBearer(auto_error=False)


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),  # noqa: B008
) -> str:
    """FastAPI dependency: validate Bearer session and refresh its idle timer.

    Refreshing on every authenticated request keeps the 15-minute idle window
    rolling as long as the user is actively using the PWA, matching the
    behaviour of the Tauri path where the Rust frontend calls auth/refresh
    periodically.

    Returns the raw session string so endpoints that need it (logout) can use it.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    session_val = credentials.credentials
    if not auth.refresh_session(session_val):
        # refresh_session returns False when absent or expired
        raise HTTPException(status_code=401, detail="Session expired or invalid")

    return session_val


# ---------------------------------------------------------------------------
# Method blacklist — these exist on the stdio server but are not surfaced here
# ---------------------------------------------------------------------------

_BLACKLISTED_METHODS: frozenset[str] = frozenset(
    {
        # Auth is handled by dedicated HTTP endpoints, not via JSON-RPC dispatch
        "auth/login",
        "auth/logout",
        "auth/refresh",
        "auth/validate",
        # Terminal opens a GUI process; not meaningful over HTTP
        "system/open-terminal",
        # Frontend debug helper; no-op for PWA clients
        "debug/log",
        # MCP noise that the PWA should never send
        "ping",
        "initialize",
    }
)

# ---------------------------------------------------------------------------
# Method registry
#
# Each entry is (handler_callable, needs_db).
# Handlers with needs_db=True are called as handler(db, **params).
# Handlers with needs_db=False are called as handler(**params).
#
# tools/call is handled separately in the dispatcher because it needs the
# ToolError → RpcError conversion wrapper from ui_rpc_server.
# ---------------------------------------------------------------------------

_METHODS: dict[str, tuple[Callable[..., Any], bool]] = {
    # chat
    "chat/respond": (handle_chat_respond, True),
    "chat/clear": (handle_chat_clear, True),
    "conversations/list": (handle_conversations_list, True),
    "conversations/messages": (handle_conversation_messages, True),
    # consciousness / async CAIRN
    "consciousness/start": (handle_consciousness_start, True),
    "consciousness/poll": (handle_consciousness_poll, True),
    "consciousness/snapshot": (handle_consciousness_snapshot, True),
    "consciousness/persist": (handle_consciousness_persist, True),
    "cairn/chat_async": (handle_cairn_chat_async, True),
    "cairn/chat_status": (handle_cairn_chat_status, True),
    "handoff/validate_all": (handle_handoff_validate_all, True),
    # approvals
    "approval/pending": (handle_approval_pending, True),
    "approval/respond": (handle_approval_respond, True),
    "approval/explain": (handle_approval_explain, True),
    # play — acts
    "play/acts/list": (handle_play_acts_list, True),
    "play/acts/create": (handle_play_acts_create, True),
    "play/acts/update": (handle_play_acts_update, True),
    "play/acts/set_active": (handle_play_acts_set_active, True),
    "play/acts/assign_repo": (handle_play_acts_assign_repo, True),
    "play/acts/delete": (handle_play_acts_delete, True),
    # play — scenes
    "play/scenes/list": (handle_play_scenes_list, True),
    "play/scenes/list_all": (handle_play_scenes_list_all, True),
    "play/scenes/create": (handle_play_scenes_create, True),
    "play/scenes/update": (handle_play_scenes_update, True),
    "play/scenes/delete": (handle_play_scenes_delete, True),
    # play — knowledge base
    "play/kb/list": (handle_play_kb_list, True),
    "play/kb/read": (handle_play_kb_read, True),
    "play/kb/write_preview": (handle_play_kb_write_preview, True),
    "play/kb/write_apply": (handle_play_kb_write_apply, True),
    # play — attachments
    "play/attachments/list": (handle_play_attachments_list, True),
    "play/attachments/add": (handle_play_attachments_add, True),
    "play/attachments/remove": (handle_play_attachments_remove, True),
    # play — me
    "play/me/read": (handle_play_me_read, True),
    "play/me/write": (handle_play_me_write, True),
    # play — pages
    "play/pages/list": (handle_play_pages_list, True),
    "play/pages/tree": (handle_play_pages_tree, True),
    "play/pages/create": (handle_play_pages_create, True),
    "play/pages/update": (handle_play_pages_update, True),
    "play/pages/delete": (handle_play_pages_delete, True),
    "play/pages/move": (handle_play_pages_move, True),
    "play/pages/content/read": (handle_play_pages_content_read, True),
    "play/pages/content/write": (handle_play_pages_content_write, True),
    # providers / ollama
    "ollama/status": (handle_ollama_status, True),
    "ollama/check_installed": (handle_ollama_check_installed, True),
    "ollama/set_url": (handle_ollama_set_url, True),
    "ollama/set_model": (handle_ollama_set_model, True),
    "ollama/model_info": (handle_ollama_model_info, True),
    "ollama/pull_start": (handle_ollama_pull_start, True),
    "ollama/pull_status": (handle_ollama_pull_status, False),  # no db — uses module-level state
    "ollama/test_connection": (handle_ollama_test_connection, True),
    "ollama/set_gpu": (handle_ollama_set_gpu, True),
    "ollama/set_context": (handle_ollama_set_context, True),
    "providers/list": (handle_providers_list, True),
    "providers/set": (handle_providers_set, True),
    # system
    "system/live_state": (handle_system_live_state, True),
    "cairn/thunderbird/status": (handle_cairn_thunderbird_status, True),
    "thunderbird/check": (handle_thunderbird_check, True),
    "thunderbird/reset": (handle_thunderbird_reset, True),
    "thunderbird/configure": (handle_thunderbird_configure, True),
    "thunderbird/decline": (handle_thunderbird_decline, True),
    "autostart/get": (handle_autostart_get, True),
    "autostart/set": (handle_autostart_set, True),
    "cairn/attention": (handle_cairn_attention, True),
    # personas
    "personas/list": (handle_personas_list, True),
    "personas/upsert": (handle_persona_upsert, True),
    # safety
    "safety/settings": (handle_safety_settings, True),
    "safety/set_sudo_limit": (handle_safety_set_sudo_limit, True),
    "safety/set_command_length": (handle_safety_set_command_length, True),
    "safety/set_max_iterations": (handle_safety_set_max_iterations, True),
    "safety/set_wall_clock_timeout": (handle_safety_set_wall_clock_timeout, True),
    "safety/set_rate_limit": (handle_safety_set_rate_limit, True),
    # health
    "health/status": (handle_health_status, True),
    "health/findings": (handle_health_findings, True),
    "health/acknowledge": (handle_health_acknowledge, True),
    # blocks
    "blocks/create": (handle_blocks_create, True),
    "blocks/get": (handle_blocks_get, True),
    "blocks/list": (handle_blocks_list, True),
    "blocks/update": (handle_blocks_update, True),
    "blocks/delete": (handle_blocks_delete, True),
    "blocks/move": (handle_blocks_move, True),
    "blocks/reorder": (handle_blocks_reorder, True),
    "blocks/ancestors": (handle_blocks_ancestors, True),
    "blocks/descendants": (handle_blocks_descendants, True),
    "blocks/page/tree": (handle_blocks_page_tree, True),
    "blocks/page/markdown": (handle_blocks_page_markdown, True),
    "blocks/import/markdown": (handle_blocks_import_markdown, True),
    "blocks/scene/create": (handle_blocks_create_scene, True),
    "blocks/scene/validate": (handle_blocks_validate_scene, True),
    "blocks/rich_text/get": (handle_blocks_rich_text_get, True),
    "blocks/rich_text/set": (handle_blocks_rich_text_set, True),
    "blocks/property/get": (handle_blocks_property_get, True),
    "blocks/property/set": (handle_blocks_property_set, True),
    "blocks/property/delete": (handle_blocks_property_delete, True),
    "blocks/search": (handle_blocks_search, True),
    "blocks/unchecked_todos": (handle_blocks_unchecked_todos, True),
    # memory
    "memory/relationships/create": (handle_memory_relationships_create, True),
    "memory/relationships/list": (handle_memory_relationships_list, True),
    "memory/relationships/update": (handle_memory_relationships_update, True),
    "memory/relationships/delete": (handle_memory_relationships_delete, True),
    "memory/search": (handle_memory_search, True),
    "memory/related": (handle_memory_related, True),
    "memory/path": (handle_memory_path, True),
    "memory/index/block": (handle_memory_index_block, True),
    "memory/index/batch": (handle_memory_index_batch, True),
    "memory/index/remove": (handle_memory_remove_index, True),
    "memory/extract": (handle_memory_extract_relationships, True),
    "memory/learn": (handle_memory_learn_from_feedback, True),
    "memory/auto_link": (handle_memory_auto_link, True),
    "memory/stats": (handle_memory_stats, True),
    # documents
    "documents/insert": (handle_documents_insert, True),
    "documents/list": (handle_documents_list, True),
    "documents/get": (handle_documents_get, True),
    "documents/delete": (handle_documents_delete, True),
    "documents/chunks": (handle_documents_get_chunks, True),
    # context
    "context/stats": (handle_context_stats, True),
    "context/toggle_source": (handle_context_toggle_source, True),
    # execution / code mode
    "plan/preview": (handle_plan_preview, True),
    "execution/status": (handle_execution_status, True),
    "execution/kill": (handle_execution_kill, True),
    "code/diff/apply": (handle_code_diff_apply, True),
    "code/diff/reject": (handle_code_diff_reject, True),
    "code/plan/approve": (handle_code_plan_approve, True),
    "code/exec/state": (handle_code_exec_state, True),
    "code/plan/start": (handle_code_plan_start, True),
    "code/plan/state": (handle_code_plan_state, True),
    "code/plan/result": (handle_code_plan_result, True),
    # archive
    "conversation/archive/preview": (handle_conversation_archive_preview, True),
    "conversation/archive/confirm": (handle_conversation_archive_confirm, True),
    "conversation/archive": (handle_conversation_archive, True),
    "conversation/delete": (handle_conversation_delete, True),
    "archive/list": (handle_archive_list, True),
    "archive/get": (handle_archive_get, True),
    "archive/assess": (handle_archive_assess, True),
    "archive/feedback": (handle_archive_feedback, True),
    "archive/learning_stats": (handle_archive_learning_stats, True),
    # reasoning
    "reasoning/feedback": (handle_reasoning_feedback, True),
    "reasoning/chain": (handle_reasoning_chain_get, True),
    "reasoning/list": (handle_reasoning_chains_list, True),
}

# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str
    credential: str


@router.post("/auth/login")
async def login(body: LoginRequest) -> dict[str, Any]:
    """Authenticate via PAM and return a Bearer session value.

    Unlike the Tauri path (which shows a native Polkit dialog), the PWA
    supplies the credential directly so PAM can verify it without a GUI.
    """
    from reos.rpc_handlers.http_auth import http_login

    return await asyncio.to_thread(http_login, username=body.username, credential=body.credential)


@router.post("/auth/logout")
async def logout(bearer_val: str = Depends(require_auth)) -> dict[str, Any]:
    """Invalidate the current session."""
    from reos.rpc_handlers.http_auth import http_logout

    return await asyncio.to_thread(http_logout, session_token=bearer_val)


@router.post("/auth/refresh")
async def refresh(bearer_val: str = Depends(require_auth)) -> dict[str, Any]:  # noqa: ARG001
    """Extend the session idle timer.

    The actual refresh already happened inside require_auth; this endpoint
    exists so the PWA can poll it to keep the session alive without making a
    full RPC call.
    """
    return {"success": True}


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 dispatcher
# ---------------------------------------------------------------------------


def _build_rpc_error(
    req_id: str | int | None, code: int, message: str, data: Any = None
) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


def _build_rpc_result(req_id: str | int | None, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


async def _dispatch(db: Database, body: dict[str, Any]) -> dict[str, Any]:
    """Core JSON-RPC 2.0 dispatcher for a single request object.

    Separated from the route handler so it can be tested without a full HTTP
    request cycle.
    """
    req_id: str | int | None = body.get("id")
    method: str | None = body.get("method")
    params: Any = body.get("params") or {}

    if not isinstance(method, str) or not method:
        return _build_rpc_error(req_id, -32600, "Invalid Request: method is required")

    if not isinstance(params, dict):
        return _build_rpc_error(req_id, -32600, "Invalid Request: params must be an object")

    # Blacklisted methods — handled elsewhere or outright forbidden
    if method in _BLACKLISTED_METHODS:
        return _build_rpc_error(
            req_id,
            -32601,
            f"Method not available via HTTP: {method}",
        )

    # Special case: tools/call wraps call_tool() with ToolError conversion
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments")
        if not isinstance(name, str) or not name:
            return _build_rpc_error(req_id, -32602, "name is required")
        if arguments is not None and not isinstance(arguments, dict):
            return _build_rpc_error(req_id, -32602, "arguments must be an object or null")
        try:
            result = await asyncio.to_thread(call_tool, db, name=name, arguments=arguments)
            return _build_rpc_result(req_id, result)
        except ToolError as exc:
            code = -32602 if exc.code in {"invalid_args", "path_escape"} else -32000
            return _build_rpc_error(req_id, code, exc.message, exc.data)
        except RpcError as exc:
            return _build_rpc_error(req_id, exc.code, exc.message, exc.data)
        except Exception as exc:
            logger.exception("Unexpected error in tools/call name=%s", name)
            return _build_rpc_error(req_id, -32603, f"Internal error: {exc}")

    # Generic handler lookup
    entry = _METHODS.get(method)
    if entry is None:
        return _build_rpc_error(req_id, -32601, f"Method not found: {method}")

    handler, needs_db = entry

    # Strip internal bookkeeping keys before passing params to the handler so
    # handlers never see __session or other HTTP-layer fields.
    handler_params = {k: v for k, v in params.items() if not k.startswith("__")}

    try:
        if needs_db:
            result = await asyncio.to_thread(handler, db, **handler_params)
        else:
            result = await asyncio.to_thread(handler, **handler_params)
        return _build_rpc_result(req_id, result)
    except RpcError as exc:
        return _build_rpc_error(req_id, exc.code, exc.message, exc.data)
    except TypeError as exc:
        # Wrong / missing parameters — surface as invalid params
        return _build_rpc_error(req_id, -32602, f"Invalid parameters: {exc}")
    except Exception as exc:
        logger.exception("Unexpected error in method=%s", method)
        return _build_rpc_error(
            req_id,
            -32603,
            f"Internal error in {method}",
            {"error_type": type(exc).__name__},
        )


@router.post("/rpc")
async def rpc_dispatch(
    request: Request,
    bearer_val: str = Depends(require_auth),  # noqa: ARG001
) -> dict[str, Any]:
    """JSON-RPC 2.0 endpoint for all PWA → backend calls.

    Accepts a single JSON-RPC request object (batch not supported — the PWA
    client is our own code and we keep the protocol surface minimal).
    """
    try:
        body = await request.json()
    except Exception:
        return _build_rpc_error(None, -32700, "Parse error: invalid JSON")

    if not isinstance(body, dict):
        return _build_rpc_error(None, -32600, "Invalid Request: expected a JSON object")

    db = get_db()
    return await _dispatch(db, body)


# ---------------------------------------------------------------------------
# SSE: consciousness event stream
# ---------------------------------------------------------------------------

_SSE_POLL_INTERVAL = 0.25  # seconds between consciousness polls


async def _sse_event(event: str, data: Any) -> str:
    """Format a single SSE frame."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _consciousness_stream(
    db: Database,
    text: str,
    conversation_id: str | None,
    extended_thinking: bool,
) -> AsyncGenerator[str, None]:
    """Drive a CAIRN async chat and stream consciousness events to the client.

    Flow:
    1. Start the async chat — get a chat_id.
    2. Poll consciousness events (250 ms) while the chat runs.
    3. Emit each batch as `event: consciousness`.
    4. When the chat completes: emit `event: result`, then `event: done`.
    5. On error: emit `event: error`.

    The sync handlers run in a thread pool via asyncio.to_thread so they
    cannot block the event loop.
    """
    # Step 1: kick off the async chat
    try:
        start_result: dict[str, Any] = await asyncio.to_thread(
            handle_cairn_chat_async,
            db,
            text=text,
            conversation_id=conversation_id,
            extended_thinking=extended_thinking,
        )
    except Exception as exc:
        logger.exception("Failed to start CAIRN async chat")
        yield await _sse_event("error", {"message": str(exc)})
        return

    chat_id: str | None = start_result.get("chat_id")
    if not chat_id:
        yield await _sse_event("error", {"message": "chat_id missing from cairn/chat_async result"})
        return

    # Step 2–4: poll until complete
    event_index = 0
    while True:
        await asyncio.sleep(_SSE_POLL_INTERVAL)

        # Poll consciousness events accumulated since last check
        try:
            poll_result: dict[str, Any] = await asyncio.to_thread(
                handle_consciousness_poll,
                db,
                since_index=event_index,
            )
            events: list[Any] = poll_result.get("events", [])
            next_index: int = poll_result.get("next_index", event_index)
        except Exception as exc:
            logger.warning("Consciousness poll failed: %s", exc)
            events = []
            next_index = event_index

        for ev in events:
            yield await _sse_event("consciousness", ev)
        if events:
            event_index = next_index

        # Check whether the chat finished
        try:
            status_result: dict[str, Any] = await asyncio.to_thread(
                handle_cairn_chat_status,
                db,
                chat_id=chat_id,
            )
        except Exception as exc:
            logger.exception("Failed to poll CAIRN chat status for chat_id=%s", chat_id)
            yield await _sse_event("error", {"message": str(exc)})
            return

        chat_status: str = status_result.get("status", "processing")
        error: str | None = status_result.get("error")

        if chat_status == "error" or error:
            yield await _sse_event("error", {"message": error or "Unknown error"})
            return

        if chat_status == "complete":
            chat_result: Any = status_result.get("result", {})
            yield await _sse_event("result", chat_result or {})
            yield await _sse_event("done", {})
            return


@router.get("/rpc/events")
async def rpc_events(
    text: str,
    conversation_id: str | None = None,
    extended_thinking: bool = False,
    bearer_val: str = Depends(require_auth),  # noqa: ARG001
) -> StreamingResponse:
    """Server-Sent Events stream for CAIRN consciousness events.

    The PWA opens this as a long-lived GET (EventSource API) and receives:
    - `event: consciousness` — incremental thinking events while CAIRN works
    - `event: result`        — the final chat response
    - `event: done`          — signals the stream is finished
    - `event: error`         — unrecoverable error; stream closes

    Query parameters mirror the cairn/chat_async RPC method.
    """
    db = get_db()
    return StreamingResponse(
        _consciousness_stream(db, text, conversation_id, extended_thinking),
        media_type="text/event-stream",
        headers={
            # Prevent proxies and browsers from buffering SSE frames
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
