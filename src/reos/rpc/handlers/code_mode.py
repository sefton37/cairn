"""Code Mode handlers.

Manages Code Mode execution, planning, diff preview, repo mapping, and sessions.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from reos.db import Database
from reos.rpc.router import register
from reos.rpc.types import INVALID_PARAMS, RpcError

logger = logging.getLogger(__name__)

# Track active Code Mode executions
_active_code_executions: dict[str, Any] = {}
_code_exec_lock = threading.Lock()

# Track active Code Mode planning sessions
_active_code_plans: dict[str, Any] = {}
_code_plan_lock = threading.Lock()

# Track active diff preview managers per session
_diff_preview_managers: dict[str, Any] = {}

# Track active RepoMap instances per session
_repo_map_instances: dict[str, Any] = {}


def get_code_execution(execution_id: str) -> Any:
    """Get a code execution context by ID (used by execution handlers)."""
    with _code_exec_lock:
        return _active_code_executions.get(execution_id)


# -------------------------------------------------------------------------
# Code Mode Execution handlers
# -------------------------------------------------------------------------


@register("code/exec/start", needs_db=True)
def handle_exec_start(
    db: Database,
    *,
    session_id: str,
    prompt: str,
    repo_path: str,
    max_iterations: int = 10,
    auto_approve: bool = True,
) -> dict[str, Any]:
    """Start a Code Mode execution in a background thread.

    Returns immediately with an execution_id that can be polled for state.
    """
    from reos.code_mode import (
        CodeSandbox,
        CodeExecutor,
        ExecutionObserver,
        create_execution_context,
    )
    from reos.play_fs import list_acts

    # Create execution context
    context = create_execution_context(
        session_id=session_id,
        prompt=prompt,
        max_iterations=max_iterations,
    )

    # Create observer that updates the context
    observer = ExecutionObserver(context)

    # Create sandbox and executor
    sandbox = CodeSandbox(Path(repo_path))

    # Get LLM provider if configured
    llm = None
    try:
        from reos.ollama import OllamaClient
        stored_url = db.get_state(key="ollama_url")
        stored_model = db.get_state(key="ollama_model")
        if stored_url and stored_model:
            llm = OllamaClient(url=stored_url, model=stored_model)
    except Exception as e:
        logger.warning("Failed to initialize LLM provider for code execution: %s", e)

    # Get project memory if available
    project_memory = None
    try:
        from reos.code_mode.project_memory import ProjectMemoryStore
        project_memory = ProjectMemoryStore(db=db)
    except Exception as e:
        logger.warning("Failed to initialize project memory: %s", e)

    executor = CodeExecutor(
        sandbox=sandbox,
        llm=llm,
        project_memory=project_memory,
        observer=observer,
    )

    # Load the Act for context
    acts, active_id = list_acts()
    act = next((a for a in acts if a.act_id == active_id), None) if active_id else None

    def run_execution() -> None:
        """Run the execution in background thread."""
        try:
            result = executor.execute(
                prompt=prompt,
                act=act,
                max_iterations=max_iterations,
                auto_approve=auto_approve,
            )
            context.result = result
            context.is_complete = True
        except Exception as e:
            context.error = str(e)
            context.is_complete = True
            observer.on_error(str(e))

    # Start background thread
    thread = threading.Thread(target=run_execution, daemon=True)
    context.thread = thread

    # Track the execution
    with _code_exec_lock:
        _active_code_executions[context.execution_id] = context

    thread.start()

    return {
        "execution_id": context.execution_id,
        "session_id": session_id,
        "status": "started",
    }


@register("code/exec/state", needs_db=True)
def handle_exec_state(
    db: Database,
    *,
    execution_id: str,
) -> dict[str, Any]:
    """Get the current state of a Code Mode execution."""
    with _code_exec_lock:
        context = _active_code_executions.get(execution_id)

    if not context:
        raise RpcError(code=INVALID_PARAMS, message=f"Code execution not found: {execution_id}")

    # Get current output lines
    output_lines = context.get_output_lines()

    # Update state with latest output
    if context.state:
        context.state.output_lines = output_lines

        # Return serialized state
        return context.state.to_dict()

    # Fallback if no state
    return {
        "execution_id": execution_id,
        "status": "unknown",
        "is_complete": context.is_complete,
        "error": context.error,
        "output_lines": output_lines,
    }


@register("code/exec/cancel", needs_db=True)
def handle_exec_cancel(
    db: Database,
    *,
    execution_id: str,
) -> dict[str, Any]:
    """Cancel a running Code Mode execution."""
    with _code_exec_lock:
        context = _active_code_executions.get(execution_id)

    if not context:
        raise RpcError(code=INVALID_PARAMS, message=f"Code execution not found: {execution_id}")

    if context.is_complete:
        return {"ok": False, "message": "Execution already complete"}

    # Request cancellation
    context.request_cancel()

    return {"ok": True, "message": "Cancellation requested"}


@register("code/exec/list", needs_db=True)
def handle_exec_list(db: Database) -> dict[str, Any]:
    """List all active Code Mode executions."""
    with _code_exec_lock:
        executions = []
        for exec_id, context in _active_code_executions.items():
            executions.append({
                "execution_id": exec_id,
                "session_id": context.state.session_id if context.state else "",
                "prompt": context.state.prompt[:100] if context.state else "",
                "status": context.state.status if context.state else "unknown",
                "is_complete": context.is_complete,
            })

    return {"executions": executions}


@register("code/exec/cleanup", needs_db=True)
def handle_exec_cleanup(
    db: Database,
    *,
    execution_id: str | None = None,
) -> dict[str, Any]:
    """Clean up completed Code Mode executions."""
    with _code_exec_lock:
        if execution_id:
            # Clean up specific execution
            if execution_id in _active_code_executions:
                context = _active_code_executions[execution_id]
                if context.is_complete:
                    del _active_code_executions[execution_id]
                    return {"ok": True, "cleaned": 1}
                else:
                    return {"ok": False, "message": "Execution still running"}
            return {"ok": False, "message": "Execution not found"}

        # Clean up all completed executions
        to_remove = [
            exec_id
            for exec_id, context in _active_code_executions.items()
            if context.is_complete
        ]
        for exec_id in to_remove:
            del _active_code_executions[exec_id]

        return {"ok": True, "cleaned": len(to_remove)}


# -------------------------------------------------------------------------
# Code Mode Planning handlers
# -------------------------------------------------------------------------


@register("code/plan/start", needs_db=True)
def handle_plan_start(
    db: Database,
    *,
    prompt: str,
    conversation_id: str,
    act_id: str | None = None,
) -> dict[str, Any]:
    """Start Code Mode planning in background thread."""
    from reos.code_mode.streaming import (
        create_planning_context,
        PlanningObserver,
        PlanningCancelledError,
    )
    from reos.code_mode.intent import IntentDiscoverer
    from reos.code_mode.contract import ContractBuilder
    from reos.code_mode import CodeSandbox, CodePlanner
    from reos.providers import get_provider, check_provider_health
    from reos.play_fs import list_acts

    # Get the active act
    active_act = None
    acts, active_act_id = list_acts()

    # Use provided act_id or fall back to active_act_id
    target_act_id = act_id or active_act_id
    if target_act_id:
        for act in acts:
            if act.act_id == target_act_id:
                active_act = act
                break

    if not active_act or not active_act.repo_path:
        raise RpcError(
            code=INVALID_PARAMS,
            message="No active Act with repository. Please set up an Act first."
        )

    # Check LLM health
    health = check_provider_health(db)
    if not health.reachable:
        raise RpcError(
            code=-32603,
            message=f"Cannot connect to LLM provider: {health.error or 'Unknown error'}"
        )

    # Create planning context
    context = create_planning_context(prompt)
    observer = PlanningObserver(context)

    def run_planning() -> None:
        """Background planning thread."""
        try:
            repo_path = Path(active_act.repo_path)  # type: ignore
            sandbox = CodeSandbox(repo_path)
            llm = get_provider(db)

            # Phase 1: Intent Discovery
            observer.on_phase_change("analyzing_prompt")
            observer.on_activity("Starting intent discovery...")
            intent_discoverer = IntentDiscoverer(
                sandbox=sandbox,
                llm=llm,
                observer=observer,
            )

            discovered_intent = intent_discoverer.discover(prompt, active_act)
            observer.on_activity(f"Intent discovered: {discovered_intent.goal[:50]}...")

            # Phase 2: Contract Building
            observer.on_phase_change("generating_criteria")
            observer.on_activity("Building acceptance contract...")
            contract_builder = ContractBuilder(
                sandbox=sandbox,
                llm=llm,
                observer=observer,
            )

            contract = contract_builder.build_from_intent(discovered_intent)
            observer.on_activity(f"Contract built with {len(contract.acceptance_criteria)} criteria")

            # Phase 3: Create CodeTaskPlan
            observer.on_phase_change("decomposing")
            observer.on_activity("Generating execution plan...")
            planner = CodePlanner(sandbox=sandbox, llm=llm)
            plan = planner.create_plan(request=prompt, act=active_act)
            observer.on_activity(f"Plan created with {len(plan.steps)} steps")

            # Store result
            context.result = {
                "intent": discovered_intent,
                "contract": contract,
                "plan": plan,
            }

            # Planning complete - waiting for user approval
            observer.on_phase_change("ready")
            observer.on_activity("Plan ready for your approval")
            context.update_state(
                is_complete=True,
                success=True,
                intent_summary=discovered_intent.goal,
                contract_summary=contract.summary(),
                ambiguities=discovered_intent.ambiguities,
                assumptions=discovered_intent.assumptions,
            )
            context.is_complete = True

        except PlanningCancelledError:
            context.error = "Planning cancelled by user"
            context.is_complete = True
            observer.on_phase_change("failed")
            context.update_state(
                is_complete=True,
                success=False,
                error="Cancelled by user",
            )

        except Exception as e:
            logger.exception("Planning failed: %s", e)
            context.error = str(e)
            context.is_complete = True
            observer.on_phase_change("failed")
            context.update_state(
                is_complete=True,
                success=False,
                error=str(e),
            )

    # Start planning thread
    thread = threading.Thread(target=run_planning, daemon=True)
    context.thread = thread

    # Store context
    with _code_plan_lock:
        _active_code_plans[context.planning_id] = context

    thread.start()

    return {
        "planning_id": context.planning_id,
        "status": "started",
        "prompt": prompt,
    }


@register("code/plan/state", needs_db=True)
def handle_plan_state(
    db: Database,
    *,
    planning_id: str,
) -> dict[str, Any]:
    """Get the current state of a Code Mode planning session."""
    with _code_plan_lock:
        context = _active_code_plans.get(planning_id)

    if not context:
        raise RpcError(code=INVALID_PARAMS, message=f"Planning session not found: {planning_id}")

    # Return serialized state
    if context.state:
        return context.state.to_dict()

    # Fallback
    return {
        "planning_id": planning_id,
        "phase": "unknown",
        "is_complete": context.is_complete,
        "error": context.error,
        "activity_log": [],
    }


@register("code/plan/cancel", needs_db=True)
def handle_plan_cancel(
    db: Database,
    *,
    planning_id: str,
) -> dict[str, Any]:
    """Cancel a running Code Mode planning session."""
    with _code_plan_lock:
        context = _active_code_plans.get(planning_id)

    if not context:
        raise RpcError(code=INVALID_PARAMS, message=f"Planning session not found: {planning_id}")

    if context.is_complete:
        return {"ok": False, "message": "Planning already complete"}

    # Request cancellation
    context.request_cancel()

    return {"ok": True, "message": "Cancellation requested"}


@register("code/plan/result", needs_db=True)
def handle_plan_result(
    db: Database,
    *,
    planning_id: str,
    conversation_id: str,
) -> dict[str, Any]:
    """Get the final result of a completed planning session."""
    from reos.agent import _generate_id

    with _code_plan_lock:
        context = _active_code_plans.get(planning_id)

    if not context:
        raise RpcError(code=INVALID_PARAMS, message=f"Planning session not found: {planning_id}")

    if not context.is_complete:
        raise RpcError(code=INVALID_PARAMS, message="Planning not yet complete")

    if context.error:
        return {
            "success": False,
            "error": context.error,
        }

    result = context.result
    if not result:
        return {
            "success": False,
            "error": "No result available",
        }

    intent = result["intent"]
    contract = result["contract"]
    plan = result["plan"]

    # Build response text
    thinking_log = ""
    if intent.discovery_steps:
        thinking_log = "\n### What ReOS understood:\n"
        for step in intent.discovery_steps[:8]:
            thinking_log += f"- {step}\n"

    clarifications = ""
    if intent.ambiguities:
        clarifications = "\n### Clarification needed:\n"
        for ambiguity in intent.ambiguities:
            clarifications += f"- {ambiguity}\n"

    assumptions = ""
    if intent.assumptions:
        assumptions = "\n### Assumptions:\n"
        for assumption in intent.assumptions:
            assumptions += f"- {assumption}\n"

    contract_summary = contract.summary()

    response_text = (
        f"**Code Mode Active** (repo: `{plan.repo_path if hasattr(plan, 'repo_path') else 'unknown'}`)\n"
        f"{thinking_log}"
        f"\n{contract_summary}\n"
        f"{clarifications}{assumptions}\n"
        f"Do you want me to proceed? (yes/no)"
    )

    # Store pending plan for approval flow
    db.set_state(key="pending_code_plan_json", value=json.dumps(plan.to_dict()))
    db.set_state(key="pending_code_plan_id", value=plan.id)

    # Store message
    message_id = _generate_id() if callable(_generate_id) else f"msg-{planning_id}"
    db.add_message(
        message_id=message_id,
        conversation_id=conversation_id,
        role="assistant",
        content=response_text,
        message_type="code_plan_preview",
        metadata=json.dumps({
            "code_mode": True,
            "plan_id": plan.id,
            "contract_id": contract.id,
            "intent_goal": intent.goal,
        }),
    )

    return {
        "success": True,
        "response_text": response_text,
        "message_id": message_id,
        "plan_id": plan.id,
        "contract_id": contract.id,
    }


@register("code/plan/approve", needs_db=True)
def handle_plan_approve(
    db: Database,
    *,
    conversation_id: str,
    plan_id: str | None = None,
) -> dict[str, Any]:
    """Approve and execute a pending Code Mode plan with streaming."""
    from reos.code_mode import (
        CodeSandbox,
        CodeExecutor,
        ExecutionObserver,
        create_execution_context,
    )
    from reos.code_mode.planner import (
        CodeTaskPlan,
        CodeStep,
        CodeStepType,
        ImpactLevel,
    )
    from reos.play_fs import list_acts

    # Get the pending code plan from database
    plan_json = db.get_state(key="pending_code_plan_json")
    if not plan_json:
        raise RpcError(code=INVALID_PARAMS, message="No pending code plan to approve")

    try:
        plan_data = json.loads(plan_json)
    except json.JSONDecodeError as e:
        raise RpcError(code=INVALID_PARAMS, message=f"Invalid plan data: {e}")

    # Reconstruct the CodeTaskPlan from stored JSON
    plan_context = None
    try:
        steps = []
        for step_data in plan_data.get("steps", []):
            step_type_str = step_data.get("type", "write_file")
            try:
                step_type = CodeStepType(step_type_str)
            except ValueError:
                step_type = CodeStepType.WRITE_FILE

            steps.append(CodeStep(
                id=step_data.get("id", f"step-{len(steps)}"),
                type=step_type,
                description=step_data.get("description", ""),
                target_path=step_data.get("target_path"),
            ))

        impact_str = plan_data.get("estimated_impact", "minor")
        try:
            impact = ImpactLevel(impact_str)
        except ValueError:
            impact = ImpactLevel.MINOR

        plan_context = CodeTaskPlan(
            id=plan_data.get("id", "plan-unknown"),
            goal=plan_data.get("goal", ""),
            steps=steps,
            context_files=plan_data.get("context_files", []),
            files_to_modify=plan_data.get("files_to_modify", []),
            files_to_create=plan_data.get("files_to_create", []),
            files_to_delete=plan_data.get("files_to_delete", []),
            estimated_impact=impact,
        )
    except Exception as e:
        logger.warning("Could not reconstruct plan context: %s", e)

    # Clear the pending plan
    db.set_state(key="pending_code_plan_json", value="")

    # Get the active Act with repo
    acts, active_act_id = list_acts()
    act = None
    if active_act_id:
        for a in acts:
            if a.act_id == active_act_id:
                act = a
                break

    if not act:
        raise RpcError(code=INVALID_PARAMS, message="No active Act found")

    if not act.repo_path:
        raise RpcError(code=INVALID_PARAMS, message="Active Act has no repository assigned")

    repo_path = act.repo_path
    prompt = plan_data.get("goal", "Execute code plan")
    session_id = conversation_id

    # Create execution context
    context = create_execution_context(
        session_id=session_id,
        prompt=prompt,
        max_iterations=10,
    )

    # Create observer that updates the context
    observer = ExecutionObserver(context)

    # Create sandbox and executor
    sandbox = CodeSandbox(Path(repo_path))

    # Get LLM provider
    llm = None
    try:
        from reos.providers import get_provider
        llm = get_provider(db)
    except Exception as e:
        logger.warning("Failed to get LLM provider, falling back to Ollama: %s", e)
        try:
            from reos.ollama import OllamaClient
            stored_url = db.get_state("ollama_url")
            stored_model = db.get_state("ollama_model")
            if stored_url and stored_model:
                llm = OllamaClient(base_url=stored_url, model=stored_model)
        except Exception as e2:
            logger.error("Failed to initialize Ollama fallback: %s", e2)

    # Get project memory if available
    project_memory = None
    try:
        from reos.code_mode.project_memory import ProjectMemoryStore
        project_memory = ProjectMemoryStore(db=db)
    except Exception as e:
        logger.warning("Failed to initialize project memory: %s", e)

    executor = CodeExecutor(
        sandbox=sandbox,
        llm=llm,
        project_memory=project_memory,
        observer=observer,
    )

    def run_execution() -> None:
        """Run the execution in background thread."""
        try:
            result = executor.execute(
                prompt=prompt,
                act=act,
                max_iterations=10,
                auto_approve=True,
                plan_context=plan_context,
            )
            context.result = result
            context.is_complete = True
        except Exception as e:
            context.error = str(e)
            context.is_complete = True
            observer.on_error(str(e))

    # Start background thread
    thread = threading.Thread(target=run_execution, daemon=True)
    context.thread = thread

    # Track the execution
    with _code_exec_lock:
        _active_code_executions[context.execution_id] = context

    thread.start()

    return {
        "execution_id": context.execution_id,
        "session_id": session_id,
        "status": "started",
        "prompt": prompt,
    }


# -------------------------------------------------------------------------
# Code Mode Session handlers
# -------------------------------------------------------------------------


@register("code/sessions/list", needs_db=True)
def handle_sessions_list(
    db: Database,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    """List recent Code Mode sessions with their log files."""
    from reos.code_mode.session_logger import list_sessions

    sessions = list_sessions(limit=limit)
    return {
        "sessions": sessions,
        "count": len(sessions),
    }


@register("code/sessions/get", needs_db=True)
def handle_sessions_get(
    db: Database,
    *,
    session_id: str,
) -> dict[str, Any]:
    """Get full session log for a specific session."""
    from reos.code_mode.session_logger import get_session_log

    session = get_session_log(session_id)
    if not session:
        raise RpcError(code=INVALID_PARAMS, message=f"Session not found: {session_id}")

    return session


@register("code/sessions/raw", needs_db=True)
def handle_sessions_raw(
    db: Database,
    *,
    session_id: str,
) -> dict[str, Any]:
    """Get raw log file content for a session."""
    from reos.code_mode.session_logger import get_session_log

    session = get_session_log(session_id)
    if not session:
        raise RpcError(code=INVALID_PARAMS, message=f"Session not found: {session_id}")

    return {
        "session_id": session.get("session_id"),
        "raw_log": session.get("raw_log", ""),
    }


# -------------------------------------------------------------------------
# Code Mode Diff Preview handlers
# -------------------------------------------------------------------------


def _get_diff_preview_manager(session_id: str, repo_path: str | None = None) -> Any:
    """Get or create a DiffPreviewManager for a session."""
    from reos.code_mode import CodeSandbox, DiffPreviewManager

    if session_id not in _diff_preview_managers:
        if not repo_path:
            raise RpcError(code=INVALID_PARAMS, message="repo_path required for new diff session")
        sandbox = CodeSandbox(Path(repo_path))
        _diff_preview_managers[session_id] = DiffPreviewManager(sandbox)

    return _diff_preview_managers[session_id]


@register("code/diff/preview", needs_db=True)
def handle_diff_preview(
    db: Database,
    *,
    session_id: str,
) -> dict[str, Any]:
    """Get the current diff preview for a session."""
    if session_id not in _diff_preview_managers:
        return {"preview": None, "message": "No pending changes"}

    manager = _diff_preview_managers[session_id]
    preview = manager.get_preview()
    return {
        "preview": preview.to_dict(),
        "message": f"{preview.total_files} file(s) with {preview.total_additions} additions, {preview.total_deletions} deletions",
    }


@register("code/diff/add_change", needs_db=True)
def handle_diff_add_change(
    db: Database,
    *,
    session_id: str,
    repo_path: str,
    change_type: str,
    path: str,
    content: str | None = None,
    old_str: str | None = None,
    new_str: str | None = None,
) -> dict[str, Any]:
    """Add a file change to the diff preview."""
    manager = _get_diff_preview_manager(session_id, repo_path)

    if change_type == "create":
        if content is None:
            raise RpcError(code=INVALID_PARAMS, message="content required for create")
        change = manager.add_create(path, content)
    elif change_type == "write":
        if content is None:
            raise RpcError(code=INVALID_PARAMS, message="content required for write")
        change = manager.add_write(path, content)
    elif change_type == "edit":
        if old_str is None or new_str is None:
            raise RpcError(code=INVALID_PARAMS, message="old_str and new_str required for edit")
        change = manager.add_edit(path, old_str, new_str)
    elif change_type == "delete":
        change = manager.add_delete(path)
    else:
        raise RpcError(code=INVALID_PARAMS, message=f"Unknown change_type: {change_type}")

    return {
        "ok": True,
        "change": change.to_dict(),
    }


@register("code/diff/apply", needs_db=True)
def handle_diff_apply(
    db: Database,
    *,
    session_id: str,
    path: str | None = None,
) -> dict[str, Any]:
    """Apply changes - either all or a specific file."""
    if session_id not in _diff_preview_managers:
        raise RpcError(code=INVALID_PARAMS, message="No pending changes for this session")

    manager = _diff_preview_managers[session_id]

    if path:
        # Apply single file
        success = manager.apply_file(path)
        if not success:
            raise RpcError(code=INVALID_PARAMS, message=f"No pending change for path: {path}")
        return {"ok": True, "applied": [path]}
    else:
        # Apply all
        applied = manager.apply_all()
        # Clean up manager if all changes applied
        if session_id in _diff_preview_managers:
            del _diff_preview_managers[session_id]
        return {"ok": True, "applied": applied}


@register("code/diff/reject", needs_db=True)
def handle_diff_reject(
    db: Database,
    *,
    session_id: str,
    path: str | None = None,
) -> dict[str, Any]:
    """Reject changes - either all or a specific file."""
    if session_id not in _diff_preview_managers:
        raise RpcError(code=INVALID_PARAMS, message="No pending changes for this session")

    manager = _diff_preview_managers[session_id]

    if path:
        # Reject single file
        success = manager.reject_file(path)
        if not success:
            raise RpcError(code=INVALID_PARAMS, message=f"No pending change for path: {path}")
        return {"ok": True, "rejected": [path]}
    else:
        # Reject all
        manager.reject_all()
        # Clean up manager
        if session_id in _diff_preview_managers:
            del _diff_preview_managers[session_id]
        return {"ok": True, "rejected": "all"}


@register("code/diff/clear", needs_db=True)
def handle_diff_clear(
    db: Database,
    *,
    session_id: str,
) -> dict[str, Any]:
    """Clear all pending changes for a session."""
    if session_id in _diff_preview_managers:
        _diff_preview_managers[session_id].clear()
        del _diff_preview_managers[session_id]
    return {"ok": True}


# -------------------------------------------------------------------------
# Repository Map handlers
# -------------------------------------------------------------------------


def _get_repo_map(db: Database, session_id: str) -> Any:
    """Get or create a RepoMap instance for a session."""
    from reos.code_mode import CodeSandbox, RepoMap

    if session_id in _repo_map_instances:
        return _repo_map_instances[session_id]

    # Get repo path from session/sandbox
    if session_id not in _diff_preview_managers:
        raise ValueError(f"No sandbox found for session {session_id}")

    sandbox = _diff_preview_managers[session_id].sandbox
    repo_map = RepoMap(sandbox, db)
    _repo_map_instances[session_id] = repo_map
    return repo_map


@register("code/map/index", needs_db=True)
def handle_map_index(
    db: Database,
    *,
    session_id: str,
    force: bool = False,
) -> dict[str, Any]:
    """Index or re-index the repository for semantic search."""
    try:
        repo_map = _get_repo_map(db, session_id)
        result = repo_map.index_repo(force=force)
        return result.to_dict()
    except ValueError as e:
        return {"error": str(e), "indexed": 0, "total_files": 0}


@register("code/map/search", needs_db=True)
def handle_map_search(
    db: Database,
    *,
    session_id: str,
    query: str,
    kind: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Search for symbols by name."""
    try:
        repo_map = _get_repo_map(db, session_id)
        symbols = repo_map.find_symbol(query, kind=kind)[:limit]
        return {
            "symbols": [s.to_dict() for s in symbols],
            "count": len(symbols),
        }
    except ValueError as e:
        return {"error": str(e), "symbols": [], "count": 0}


@register("code/map/find_symbol", needs_db=True)
def handle_map_find_symbol(
    db: Database,
    *,
    session_id: str,
    name: str,
) -> dict[str, Any]:
    """Find symbol by exact name."""
    try:
        repo_map = _get_repo_map(db, session_id)
        symbols = repo_map.find_symbol_exact(name)
        return {
            "symbols": [s.to_dict() for s in symbols],
            "count": len(symbols),
        }
    except ValueError as e:
        return {"error": str(e), "symbols": [], "count": 0}


@register("code/map/find_callers", needs_db=True)
def handle_map_find_callers(
    db: Database,
    *,
    session_id: str,
    symbol_name: str,
    file_path: str,
) -> dict[str, Any]:
    """Find all callers of a symbol."""
    try:
        repo_map = _get_repo_map(db, session_id)
        callers = repo_map.find_callers(symbol_name, file_path)
        return {
            "callers": [loc.to_dict() for loc in callers],
            "count": len(callers),
        }
    except ValueError as e:
        return {"error": str(e), "callers": [], "count": 0}


@register("code/map/file_context", needs_db=True)
def handle_map_file_context(
    db: Database,
    *,
    session_id: str,
    file_path: str,
) -> dict[str, Any]:
    """Get context for a file (symbols, dependencies)."""
    try:
        repo_map = _get_repo_map(db, session_id)
        context = repo_map.get_file_context(file_path)
        if context is None:
            return {"error": "File not indexed", "context": None}
        return {"context": context.to_dict()}
    except ValueError as e:
        return {"error": str(e), "context": None}


@register("code/map/relevant_context", needs_db=True)
def handle_map_relevant_context(
    db: Database,
    *,
    session_id: str,
    query: str,
    token_budget: int = 800,
) -> dict[str, Any]:
    """Get relevant code context for a query."""
    try:
        repo_map = _get_repo_map(db, session_id)
        context = repo_map.get_relevant_context(query, token_budget=token_budget)
        return {"context": context}
    except ValueError as e:
        return {"error": str(e), "context": ""}


@register("code/map/stats", needs_db=True)
def handle_map_stats(
    db: Database,
    *,
    session_id: str,
) -> dict[str, Any]:
    """Get statistics about the repository index."""
    try:
        repo_map = _get_repo_map(db, session_id)
        stats = repo_map.get_stats()
        return {"stats": stats}
    except ValueError as e:
        return {"error": str(e), "stats": {}}


@register("code/map/clear", needs_db=True)
def handle_map_clear(
    db: Database,
    *,
    session_id: str,
) -> dict[str, Any]:
    """Clear the repository index."""
    try:
        repo_map = _get_repo_map(db, session_id)
        repo_map.clear_index()
        if session_id in _repo_map_instances:
            del _repo_map_instances[session_id]
        return {"ok": True}
    except ValueError as e:
        return {"error": str(e), "ok": False}
