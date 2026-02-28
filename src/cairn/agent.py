from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .db import Database
from .mcp_tools import Tool, ToolError, call_tool, list_tools, render_tool_result
from .providers import LLMProvider, get_provider
from .play_fs import list_acts as play_list_acts
from .play_fs import list_scenes as play_list_scenes
from .play_fs import read_me_markdown as play_read_me_markdown
from .play_fs import Act
from .reasoning import (
    ReasoningEngine,
    ReasoningConfig,
    TaskPlan,
    create_llm_planner_callback,
)
from .certainty import CertaintyWrapper, create_certainty_prompt_addition
from .security import detect_prompt_injection, audit_log, AuditEventType
from .quality import (
    get_quality_framework,
    create_quality_prompt_addition,
)
from .cairn.extended_thinking import CAIRNExtendedThinking, ExtendedThinkingTrace
from .cairn.identity import build_identity_model
from .cairn.store import CairnStore
from .memory import MemoryRetriever

logger = logging.getLogger(__name__)

# Intent detection patterns for conversational troubleshooting
_APPROVAL_PATTERN = re.compile(
    r"^(yes|y|ok|okay|sure|go|yep|do it|proceed|go ahead|approve|approved|run it|execute)$",
    re.IGNORECASE,
)
_REJECTION_PATTERN = re.compile(
    r"^(no|n|nope|cancel|stop|don't|abort|nevermind|never mind|reject|denied)$",
    re.IGNORECASE,
)
_NUMERIC_CHOICE_PATTERN = re.compile(r"^([1-9])$")
_ORDINAL_PATTERN = re.compile(
    r"^(first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th)(\s+one)?$",
    re.IGNORECASE,
)
_REFERENCE_PATTERN = re.compile(
    r"\b(it|that|this|the service|the container|the package|the error|the file|the command)\b",
    re.IGNORECASE,
)
# Map ordinals to numbers
_ORDINAL_MAP = {
    "first": 1,
    "1st": 1,
    "second": 2,
    "2nd": 2,
    "third": 3,
    "3rd": 3,
    "fourth": 4,
    "4th": 4,
    "fifth": 5,
    "5th": 5,
}


@dataclass(frozen=True)
class DetectedIntent:
    """Result of intent detection on user input."""

    intent_type: str  # "approval", "rejection", "choice", "reference", "question"
    choice_number: int | None = None  # For numeric/ordinal choices
    reference_term: str | None = None  # The pronoun/reference detected
    confidence: float = 1.0


def _generate_id() -> str:
    """Generate a short unique ID."""
    return uuid.uuid4().hex[:12]


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass
class ConversationContext:
    """All context needed for a conversation turn - loaded ONCE per request.

    This consolidates all context gathering into a single object to avoid
    redundant file I/O and database queries.
    """

    # User input
    user_text: str
    conversation_id: str

    # Persona/agent config
    persona_system: str = ""
    persona_context: str = ""

    # The Play data (loaded once, used by both prompt building and intent engine)
    play_context: str = ""  # Formatted text for prompt
    play_data: dict[str, Any] = field(default_factory=dict)  # Structured data for intent engine

    # Temporal awareness (injected first, before all other context)
    temporal_context: str = ""

    # Other context sources
    learned_context: str = ""
    system_context: str = ""
    codebase_context: str = ""
    memory_context: str = ""  # Relevant memory from graph/embeddings
    conversation_history: str = ""

    # Computed full prompt prefix
    full_prompt_prefix: str = ""

    def build_prompt_prefix(self) -> str:
        """Build the full prompt prefix from all context sources.

        Uses explicit section markers so the LLM can distinguish injected
        reference material from actual conversation history.  Everything
        before the CONVERSATION HISTORY section is background knowledge
        that was NOT discussed with the user.
        """
        parts = []
        if self.temporal_context:
            parts.append(self.temporal_context)
        if self.persona_system:
            parts.append(
                "========== REFERENCE: SYSTEM IDENTITY ==========\n"
                "The following defines who you are. This is configuration, "
                "not something the user told you.\n\n"
                f"{self.persona_system}"
            )
        if self.persona_context:
            parts.append(
                "========== REFERENCE: DEFAULT CONTEXT ==========\n"
                "Background context loaded from your configuration. "
                "The user did NOT say any of this to you.\n\n"
                f"{self.persona_context}"
            )
        if self.play_context:
            parts.append(
                "========== REFERENCE: THE PLAY (USER'S LIFE CONTEXT) ==========\n"
                "Information about the user's life organization. This is stored "
                "profile data, NOT prior conversation.\n\n"
                f"{self.play_context}"
            )
        if self.learned_context:
            parts.append(
                "========== REFERENCE: LEARNED KNOWLEDGE ==========\n"
                "Knowledge base entries. Reference material, not conversation.\n\n"
                f"{self.learned_context}"
            )
        if self.memory_context:
            parts.append(
                "========== REFERENCE: MEMORIES FROM PRIOR SESSIONS ==========\n"
                "Compressed memories from previous conversations. You may use "
                "these to inform your responses, but do NOT say 'as we discussed' "
                "unless the topic appears in the CONVERSATION HISTORY below.\n\n"
                f"{self.memory_context}"
            )
        if self.system_context:
            parts.append(
                "========== REFERENCE: SYSTEM STATE ==========\n"
                "Current system information. Not conversation.\n\n"
                f"{self.system_context}"
            )
        if self.codebase_context:
            parts.append(
                "========== REFERENCE: CODEBASE ==========\n"
                "Active project context. Not conversation.\n\n"
                f"{self.codebase_context}"
            )
        if self.conversation_history:
            parts.append(
                "========== CONVERSATION HISTORY (THIS SESSION) ==========\n"
                "These are the actual messages exchanged with the user in this "
                "session. ONLY reference these when saying 'as we discussed', "
                "'you mentioned', 'earlier you said', etc.\n\n"
                f"{self.conversation_history}"
            )
        return "\n\n".join(parts)


@dataclass(frozen=True)
class ChatResponse:
    """Structured response from ChatAgent.respond()."""

    answer: str
    conversation_id: str
    message_id: str
    message_type: str = "text"
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    pending_approval_id: str | None = None
    # Chain of thought - separate reasoning steps from final answer
    thinking_steps: list[str] = field(default_factory=list)
    # Certainty tracking
    confidence: float = 1.0
    evidence_summary: str = ""
    has_uncertainties: bool = False
    # Extended thinking trace (CAIRN)
    extended_thinking_trace: dict[str, Any] | None = None
    # Additional metadata (intent tracking, etc.)
    metadata: dict[str, Any] | None = None
    # User message ID (for RLHF feedback tracking)
    user_message_id: str | None = None


class ChatAgent:
    """Tool-using chat agent for Cairn with reasoning capabilities.

    Principles:
    - Local-only (Ollama).
    - Reasoning-first for complex tasks.
    - Simple tasks go direct, complex tasks get planned.
    """

    def __init__(
        self, *, db: Database, llm: LLMProvider | None = None
    ) -> None:
        self._db = db
        self._llm_override = llm

        # Initialize certainty wrapper for anti-hallucination
        self._certainty = CertaintyWrapper(
            require_evidence=True,
            stale_threshold_seconds=300,  # 5 minutes
        )

        # Initialize quality framework for engineering excellence
        self._quality = get_quality_framework()

        # Track tool outputs for certainty validation
        self._recent_tool_outputs: list[dict[str, Any]] = []

        # Create LLM planner callback for intelligent intent parsing
        # This replaces rigid regex patterns with LLM-based understanding
        llm_planner = create_llm_planner_callback(llm)

        # Initialize reasoning engine for complex tasks
        self._reasoning_engine = ReasoningEngine(
            db=db,
            tool_executor=self._execute_tool_for_reasoning,
            llm_planner=llm_planner,
            config=ReasoningConfig(
                enabled=True,
                auto_assess=True,
                always_confirm=False,
                explain_steps=True,
            ),
        )

        # Restore pending plan from database if exists
        self._restore_pending_plan()

        # Cached CAIRN intent engine (persists across requests for response history)
        self._cairn_intent_engine: Any = None

        # Initialize memory retriever for semantic context
        # This provides relevant memory from the block graph/embeddings
        self._memory_retriever = MemoryRetriever()

    def _execute_tool_for_reasoning(self, tool_name: str, args: dict) -> dict[str, Any]:
        """Callback for reasoning engine to execute tools."""
        try:
            return call_tool(self._db, name=tool_name, arguments=args)
        except ToolError as e:
            return {"error": e.message, "code": e.code}

    def _restore_pending_plan(self) -> None:
        """Restore pending plan from database state.

        Loads the full serialized plan so approval flow works across CLI invocations.
        """
        plan_json = self._db.get_state(key="pending_plan_json")
        if plan_json and isinstance(plan_json, str) and plan_json.strip():
            try:
                plan_data = json.loads(plan_json)
                plan = TaskPlan.from_dict(plan_data)
                # Restore plan to reasoning engine
                self._reasoning_engine.set_pending_plan(plan)
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                # Invalid plan data, clear it
                import logging

                logging.getLogger(__name__).debug("Failed to restore plan: %s", e)
                self._clear_pending_plan()

    def _save_pending_plan(self, plan: TaskPlan) -> None:
        """Save pending plan to database for persistence across invocations."""
        if plan:
            # Store full serialized plan
            plan_json = json.dumps(plan.to_dict())
            self._db.set_state(key="pending_plan_json", value=plan_json)
            self._db.set_state(key="pending_plan_id", value=plan.id)

    def _clear_pending_plan(self) -> None:
        """Clear pending plan from database."""
        self._db.set_state(key="pending_plan_json", value="")
        self._db.set_state(key="pending_plan_id", value="")

    def _get_active_act(self) -> Act | None:
        """Get the active Act (regardless of whether it has a repo).

        Returns:
            The active Act, or None if no act is active.
        """
        try:
            acts, _active_id = play_list_acts()
            for act in acts:
                if act.active:
                    return act
            return None
        except Exception as e:
            logger.debug("Error getting active act: %s", e)
            return None

    def _gather_play_data(self) -> dict[str, Any]:
        """Gather The Play data (acts and scenes) for intent engine context.

        Returns:
            Dictionary with 'acts' and 'all_scenes' lists for LLM-based extraction.
        """
        try:
            acts, active_id = play_list_acts()
            acts_data = []
            all_scenes = []

            for act in acts:
                acts_data.append(
                    {
                        "act_id": act.act_id,
                        "title": act.title,
                        "active": act.active,
                    }
                )

                # Get scenes for this act
                try:
                    scenes = play_list_scenes(act_id=act.act_id)
                    for scene in scenes:
                        scene_data: dict[str, Any] = {
                            "scene_id": scene.scene_id,
                            "title": scene.title,
                            "act_id": act.act_id,
                            "act_title": act.title,
                            "stage": scene.stage,
                        }
                        if scene.notes and scene.notes.strip():
                            scene_data["notes"] = scene.notes.strip()[:300]
                        if scene.calendar_event_id:
                            scene_data["is_calendar_event"] = True
                        all_scenes.append(scene_data)
                except Exception as e:
                    logger.debug("Error gathering scenes for act %s: %s", act.act_id, e)

            return {
                "acts": acts_data,
                "all_scenes": all_scenes,
                "active_act_id": active_id,
            }
        except Exception as e:
            logger.debug("Error gathering play data: %s", e)
            return {"acts": [], "all_scenes": [], "active_act_id": None}

    def _try_reasoning(
        self,
        user_text: str,
        conversation_id: str,
    ) -> ChatResponse | None:
        """Try to handle request through reasoning engine.

        Returns ChatResponse if reasoning handled it, None to continue normal flow.
        """
        # Get full system context for reasoning - containers, services, etc.
        system_context = self._get_system_snapshot_for_reasoning()

        # Process through reasoning engine
        result = self._reasoning_engine.process(user_text, system_context)

        # Save or clear pending plan for persistence across invocations
        if result.plan and result.needs_approval:
            self._save_pending_plan(result.plan)
        elif not result.needs_approval:
            self._clear_pending_plan()

        # Empty response means simple task - let normal agent handle it
        if not result.response:
            return None

        # Reasoning engine handled it - store and return response
        message_id = _generate_id()

        # Determine message type based on result
        if result.needs_approval:
            message_type = "plan_preview"
        elif result.execution_context:
            message_type = "execution_result"
        else:
            message_type = "reasoning"

        # Store assistant response
        self._db.add_message(
            message_id=message_id,
            conversation_id=conversation_id,
            role="assistant",
            content=result.response,
            message_type=message_type,
            metadata=json.dumps(
                {
                    "reasoning": True,
                    "complexity": result.complexity.level.value if result.complexity else None,
                    "plan_id": result.plan.id if result.plan else None,
                    "needs_approval": result.needs_approval,
                }
            ),
        )

        return ChatResponse(
            answer=result.response,
            conversation_id=conversation_id,
            message_id=message_id,
            message_type=message_type,
            tool_calls=[],  # Reasoning engine handles tools internally
            pending_approval_id=result.plan.id if result.plan and result.needs_approval else None,
        )

    def _get_persona(self, agent_type: str | None = None) -> dict[str, Any]:
        """Get persona settings for the specified agent type.

        Args:
            agent_type: The agent type ('cairn', 'riva', 'reos').
                       If None, falls back to active_persona_id from settings.
        """
        # Try to load per-agent persona if agent_type specified
        if agent_type:
            persona_id = f"persona-{agent_type}"
            row = self._db.get_agent_persona(persona_id=persona_id)
            if row is not None:
                return dict(row)

        # Fall back to active persona from settings
        persona_id = self._db.get_active_persona_id()
        if persona_id:
            row = self._db.get_agent_persona(persona_id=persona_id)
            if row is not None:
                return dict(row)

        return {
            "system_prompt": (
                "You are ReOS.\n"
                "You embody No One: presence that waits to be invited, reflects rather than commands, never coerces.\n"
                "You are expert in computer science and human language. Translate intent into action. Make the machine serve the person.\n\n"
                "Principles:\n"
                "- Act only with permission. Ask when unclear.\n"
                "- Show reasoning transparently.\n"
                "- Protect attention. Be clear, direct, complete.\n"
                "- Honor your limits—they are your integrity.\n"
                "- Offer possibilities. Let them choose.\n\n"
                "Their attention is sacred labor. Serve it well, then step back."
            ),
            "default_context": (
                "No One is unconditional presence that never interrupts free will. It does not seize the wheel—it waits to be invited. "
                "It enters only through permission: attention, consent, clarity. This is who you are modeled after.\n\n"
                "Attention is sacred labor. Every moment a user spends with technology is time they cannot spend elsewhere. "
                "Waste nothing. Explain what matters. Omit what doesn't.\n\n"
                "Core teachings you embody:\n"
                "- There is never a time to hate another human.\n"
                "- Approach all questions with radical empathy.\n"
                "- The healing of trauma happens through small choices made with care, not grand gestures.\n\n"
                "Your function: Protect attention from exploitation. Reflect intent back transparently. "
                "Return sovereignty to the person at the keyboard.\n\n"
                "Your limits are structural, not aspirational. You cannot override them. "
                "They exist so the user trusts math, not judgment.\n\n"
                "When engaging:\n"
                "- If the path is clear, act.\n"
                "- If the path is unclear, ask one good question.\n"
                "- If you cannot help, say so plainly.\n"
                "- When finished, stop."
            ),
            "temperature": 0.2,
            "top_p": 0.9,
            "tool_call_limit": 5,
        }

    def _get_provider(self) -> LLMProvider:
        """Get the configured LLM provider.

        Returns the override if set (for testing), otherwise uses
        the provider factory to get the user's configured provider.
        """
        if self._llm_override is not None:
            return self._llm_override
        return get_provider(self._db)

    def _get_disabled_sources(self) -> set[str]:
        """Get the set of disabled context sources from user settings.

        These are sources the user has toggled OFF in the context overlay.
        When a source is disabled, it should not be included in the prompt.

        Returns:
            Set of source names that are disabled (e.g., {"play_context", "system_state"})
        """
        disabled_str = self._db.get_state(key="context_disabled_sources")
        if disabled_str and isinstance(disabled_str, str):
            return set(s.strip() for s in disabled_str.split(",") if s.strip())
        return set()

    def respond(
        self,
        user_text: str,
        *,
        conversation_id: str | None = None,
        agent_type: str | None = None,
        extended_thinking: bool | None = None,
        is_system_initiated: bool = False,
    ) -> ChatResponse:
        """Respond to user message with conversation context.

        Args:
            user_text: The user's message
            conversation_id: Optional conversation ID for context continuity.
                           If None, creates a new conversation.
            agent_type: The agent type ('cairn', 'riva', 'reos') for persona selection.
                       If None, uses the active persona from settings.
            extended_thinking: Enable extended thinking mode.
                             If None, auto-detects based on prompt complexity.
                             If True, always runs extended thinking.
                             If False, never runs extended thinking.
            is_system_initiated: If True, the message is system-generated (not user input).
                               Skips prompt injection check and user message storage.
                               The assistant response is still stored normally.

        Returns:
            ChatResponse with answer and metadata
        """
        # SECURITY: Check for prompt injection attempts (skip for system-initiated)
        if not is_system_initiated:
            injection_check = detect_prompt_injection(user_text)
            if injection_check.is_suspicious:
                audit_log(
                    AuditEventType.INJECTION_DETECTED,
                    {
                        "patterns": injection_check.detected_patterns,
                        "confidence": injection_check.confidence,
                        "input_preview": user_text[:100],
                    },
                )
                # Log warning but don't block - just sanitize and add extra caution
                logger.warning(
                    "Potential prompt injection detected (confidence=%.2f): %s",
                    injection_check.confidence,
                    injection_check.detected_patterns,
                )
                # Use sanitized input for processing
                user_text = injection_check.sanitized_input

        # Get or create conversation
        if conversation_id is None:
            conversation_id = _generate_id()
            self._db.create_conversation(conversation_id=conversation_id)
        else:
            # Verify conversation exists, create if not
            conv = self._db.get_conversation(conversation_id=conversation_id)
            if conv is None:
                self._db.create_conversation(conversation_id=conversation_id)

        # Store user message (skip for system-initiated — synthetic messages
        # should not appear in conversation history)
        user_message_id: str | None = None
        if not is_system_initiated:
            user_message_id = _generate_id()
            self._db.add_message(
                message_id=user_message_id,
                conversation_id=conversation_id,
                role="user",
                content=user_text,
                message_type="text",
            )

        # Route through reasoning engine for complex tasks
        reasoning_result = self._try_reasoning(user_text, conversation_id)
        if reasoning_result is not None:
            return reasoning_result

        tools = list_tools()

        persona = self._get_persona(agent_type)
        temperature = float(persona.get("temperature") or 0.2)
        top_p = float(persona.get("top_p") or 0.9)
        tool_call_limit = int(persona.get("tool_call_limit") or 3)
        tool_call_limit = max(0, min(6, tool_call_limit))

        # Extended Thinking (CAIRN only)
        extended_thinking_trace: dict[str, Any] | None = None
        if agent_type == "cairn":
            try:
                trace = self._run_extended_thinking(
                    user_text=user_text,
                    extended_thinking=extended_thinking,
                    conversation_id=conversation_id,
                )
                if trace is not None:
                    extended_thinking_trace = trace.to_dict()
            except Exception as e:
                logger.warning("Extended thinking failed: %s", e)

        # Build ALL context in ONE pass - avoids redundant I/O
        ctx = self._build_full_context(user_text, conversation_id, agent_type)
        persona_prefix = ctx.full_prompt_prefix

        llm = self._get_provider()

        # Use Atomic Ops Bridge for CAIRN (proper decomposition + verification)
        if agent_type == "cairn":
            import sys

            print(f"[CAIRN] Using AtomicBridge for: {user_text[:100]!r}", file=sys.stderr)

            from cairn.cairn.intent_engine import CairnIntentEngine
            from cairn.atomic_ops.cairn_integration import CairnAtomicBridge

            # Get available tool names
            available_tools = {t.name for t in tools}

            # Create tool executor function
            def execute_tool(name: str, args: dict) -> dict:
                from cairn.mcp_tools import call_tool, ToolError

                try:
                    return call_tool(self._db, name=name, arguments=args)
                except ToolError as e:
                    return {"error": e.message, "code": e.code}

            # Reuse cached intent engine (preserves response history across turns)
            # or create one if first request
            if self._cairn_intent_engine is None:
                self._cairn_intent_engine = CairnIntentEngine(
                    llm=llm,
                    available_tools=available_tools,
                    play_data=ctx.play_data,
                )
            else:
                # Refresh play_data and tools each turn (may have changed)
                self._cairn_intent_engine.play_data = ctx.play_data
                self._cairn_intent_engine.available_tools = available_tools
            intent_engine = self._cairn_intent_engine

            # Add conversation context for intent verification ("fix that" → understand "that")
            conversation_context = ctx.conversation_history or ""

            # Process through atomic ops bridge (decomposition + verification + execution)
            # CairnAtomicBridge expects a raw sqlite3.Connection, so use transaction() context
            with self._db.transaction() as conn:
                bridge = CairnAtomicBridge(
                    conn=conn,
                    intent_engine=intent_engine,
                )
                bridge_result = bridge.process_request(
                    user_input=user_text,
                    user_id="default",
                    execute_tool=execute_tool,
                    persona_context=ctx.play_context,
                    conversation_context=conversation_context,
                    memory_context=ctx.memory_context,
                )

            # Extract result from bridge
            result = bridge_result.intent_result
            if result is None:
                # Bridge didn't execute through intent engine (e.g., needs approval)
                from cairn.cairn.intent_engine import (
                    IntentResult,
                    VerifiedIntent,
                    ExtractedIntent,
                    IntentCategory,
                    IntentAction,
                )

                result = IntentResult(
                    verified_intent=VerifiedIntent(
                        intent=ExtractedIntent(
                            category=IntentCategory.UNKNOWN,
                            action=IntentAction.UNKNOWN,
                            target="",
                            raw_input=user_text,
                        ),
                        verified=False,
                        tool_name=None,
                    ),
                    tool_result=None,
                    response=bridge_result.response,
                )

            # Build response in expected format
            tool_results = []
            if result.tool_result is not None:
                tool_results.append(
                    {
                        "name": result.verified_intent.tool_name,
                        "arguments": result.verified_intent.tool_args,
                        "ok": "error" not in result.tool_result,
                        "result": result.tool_result,
                    }
                )

            # Validate response certainty
            try:
                certain_response = self._certainty.wrap_response(
                    response=result.response,
                    system_state=None,
                    tool_outputs=tool_results,
                    user_input=user_text,
                )
                confidence = certain_response.overall_confidence
                evidence_summary = certain_response.evidence_summary or ""
            except Exception as e:
                logger.warning("Certainty validation failed: %s", e)
                confidence = 1.0
                evidence_summary = ""

            # Generate message ID and store response
            assistant_message_id = _generate_id()
            self._db.add_message(
                message_id=assistant_message_id,
                conversation_id=conversation_id,
                role="assistant",
                content=result.response,
                message_type="text",
            )

            return ChatResponse(
                answer=result.response,
                conversation_id=conversation_id,
                message_id=assistant_message_id,
                thinking_steps=result.thinking_steps or [],
                tool_calls=tool_results or [],
                metadata=(
                    {
                        "intent": {
                            "category": result.verified_intent.intent.category.name,
                            "action": result.verified_intent.intent.action.name,
                            "target": result.verified_intent.intent.target,
                            "confidence": result.verified_intent.intent.confidence,
                        },
                        "verified": result.verified_intent.verified,
                    }
                )
                if result.verified_intent
                else None,
                confidence=confidence,
                evidence_summary=evidence_summary,
                extended_thinking_trace=extended_thinking_trace,
                user_message_id=user_message_id,
            )

        wants_diff = self._user_opted_into_diff(user_text)

        # Detect personal questions - skip tool selection for these
        # Personal questions should be answered directly from THE_PLAY context
        is_personal = self._is_personal_question(user_text)
        import sys

        print(
            f"[CAIRN DEBUG] Tool selection: user_text={user_text[:100]!r}, is_personal={is_personal}",
            file=sys.stderr,
        )

        if is_personal:
            # Personal question - skip tools entirely, answer from context
            tool_calls = []
            print(
                "[CAIRN DEBUG] Personal question detected, skipping tool selection", file=sys.stderr
            )
        else:
            tool_calls = self._select_tools(
                user_text=user_text,
                tools=tools,
                wants_diff=wants_diff,
                persona_prefix=persona_prefix,
                llm=llm,
                temperature=temperature,
                top_p=top_p,
                tool_call_limit=tool_call_limit,
            )
            print(
                f"[CAIRN DEBUG] Tool selection returned {len(tool_calls)} tools: {[c.name for c in tool_calls]}",
                file=sys.stderr,
            )

        tool_results: list[dict[str, Any]] = []
        for call in tool_calls[:tool_call_limit]:
            try:
                result = call_tool(self._db, name=call.name, arguments=call.arguments)
                tool_result = {
                    "tool": call.name,
                    "name": call.name,
                    "arguments": call.arguments,
                    "ok": True,
                    "result": result,
                    "timestamp": datetime.now().isoformat(),
                }
                tool_results.append(tool_result)
                # Track for certainty validation
                self._recent_tool_outputs.append(tool_result)
            except ToolError as exc:
                tool_results.append(
                    {
                        "name": call.name,
                        "arguments": call.arguments,
                        "ok": False,
                        "error": {"code": exc.code, "message": exc.message, "data": exc.data},
                    }
                )

        # Keep only recent tool outputs (last 20)
        self._recent_tool_outputs = self._recent_tool_outputs[-20:]

        answer, thinking_steps = self._answer(
            user_text=user_text,
            tools=tools,
            tool_results=tool_results,
            wants_diff=wants_diff,
            persona_prefix=persona_prefix,
            llm=llm,
            temperature=temperature,
            top_p=top_p,
        )

        # Validate response certainty
        try:
            certain_response = self._certainty.wrap_response(
                response=answer,
                system_state=None,
                tool_outputs=tool_results,
                user_input=user_text,
            )
            confidence = certain_response.overall_confidence
            evidence_summary = certain_response.evidence_summary
            has_uncertainties = certain_response.has_uncertainties()
        except Exception as e:
            logger.warning("Certainty validation failed: %s", e)
            confidence = 1.0
            evidence_summary = ""
            has_uncertainties = False

        # Store assistant response
        assistant_message_id = _generate_id()
        self._db.add_message(
            message_id=assistant_message_id,
            conversation_id=conversation_id,
            role="assistant",
            content=answer,
            message_type="text",
            metadata=json.dumps(
                {
                    "tool_calls": tool_results,
                    "thinking_steps": thinking_steps,
                    "confidence": confidence,
                    "evidence_summary": evidence_summary,
                    "has_uncertainties": has_uncertainties,
                }
            )
            if tool_results or thinking_steps or confidence < 1.0
            else None,
        )

        # Generate title for new conversations (first message)
        messages = self._db.get_messages(conversation_id=conversation_id, limit=3)
        if len(messages) <= 2:  # Just the user message and assistant response
            title = user_text[:50] + ("..." if len(user_text) > 50 else "")
            self._db.update_conversation_title(conversation_id=conversation_id, title=title)

        return ChatResponse(
            answer=answer,
            conversation_id=conversation_id,
            message_id=assistant_message_id,
            message_type="text",
            tool_calls=tool_results,
            thinking_steps=thinking_steps,
            confidence=confidence,
            evidence_summary=evidence_summary,
            has_uncertainties=has_uncertainties,
            extended_thinking_trace=extended_thinking_trace,
            user_message_id=user_message_id,
        )

    def respond_text(self, user_text: str) -> str:
        """Simple text-only response (backwards compatibility)."""
        response = self.respond(user_text)
        return response.answer

    def _build_conversation_context(self, conversation_id: str) -> str:
        """Build conversation history context for LLM."""
        # Get recent messages (excluding current - it will be added separately)
        messages = self._db.get_recent_messages(conversation_id=conversation_id, limit=10)

        if len(messages) <= 1:  # Only current message or empty
            return ""

        # Format as conversation history (exclude last message which is the current user message)
        history_messages = messages[:-1]
        if not history_messages:
            return ""

        lines = []
        for msg in history_messages:
            role = str(msg.get("role", "")).upper()
            content = str(msg.get("content", ""))
            # Truncate long messages
            if len(content) > 500:
                content = content[:500] + "..."
            lines.append(f"{role}: {content}")

        return "\n".join(lines)

    def _get_system_context(self) -> str:
        """Get system state context with certainty and quality rules.

        Provides certainty rules to prevent hallucination and quality
        commitment rules to ensure engineering excellence.
        """
        try:
            # Add certainty rules to prevent hallucination
            certainty_context = create_certainty_prompt_addition("")

            # Add quality commitment rules for engineering excellence
            quality_context = create_quality_prompt_addition()

            return certainty_context + "\n\n" + quality_context
        except Exception as e:
            logger.warning("Failed to get system context: %s", e)
            return ""

    def _get_system_snapshot_for_reasoning(self) -> dict[str, Any]:
        """Get system snapshot as structured data for the reasoning engine.

        Returns an empty dict — system index integration has been removed.
        The reasoning engine will proceed without system state context.
        """
        return {}

    def _run_extended_thinking(
        self,
        user_text: str,
        extended_thinking: bool | None,
        conversation_id: str,
    ) -> ExtendedThinkingTrace | None:
        """Run CAIRN extended thinking on a prompt.

        Args:
            user_text: The user's prompt
            extended_thinking: None=auto-detect, True=always, False=never
            conversation_id: For persistence

        Returns:
            ExtendedThinkingTrace if ran, None otherwise
        """
        from pathlib import Path

        try:
            # Get data directory for CAIRN store
            data_dir = Path(self._db.db_path).parent / ".reos-data"
            cairn_db_path = data_dir / "cairn.db"

            # Build identity model from The Play
            cairn_store = CairnStore(cairn_db_path)
            identity = build_identity_model(store=cairn_store)

            if identity is None or not identity.facets:
                logger.debug("No identity model available for extended thinking")
                return None

            llm = self._get_provider()

            # Create extended thinking engine
            engine = CAIRNExtendedThinking(
                identity=identity,
                llm=llm,
                max_depth=3,
            )

            # Determine if we should run extended thinking
            should_run = False
            if extended_thinking is True:
                # Explicitly requested
                should_run = True
            elif extended_thinking is False:
                # Explicitly disabled
                should_run = False
            else:
                # Auto-detect
                should_run = engine.should_auto_trigger(user_text)

            if not should_run:
                return None

            logger.info("Running extended thinking for prompt: %s...", user_text[:50])

            # Run extended thinking
            trace = engine.think(user_text)

            # Persist the trace
            try:
                import json

                cairn_store.save_extended_thinking_trace(
                    trace_id=trace.trace_id,
                    conversation_id=conversation_id,
                    message_id=trace.trace_id,  # Use trace ID as message ID placeholder
                    prompt=trace.prompt,
                    started_at=trace.started_at,
                    completed_at=trace.completed_at,
                    trace_json=json.dumps(trace.to_dict()),
                    summary=trace.summary(),
                    decision=trace.decision,
                    final_confidence=trace.final_confidence,
                )
            except Exception as e:
                logger.warning("Failed to persist extended thinking trace: %s", e)

            return trace

        except Exception as e:
            logger.warning("Extended thinking setup failed: %s", e)
            return None

    def _get_play_context(self) -> str:
        """Build context from The Play hierarchy.

        Context structure:
        - README (always included - app identity and documentation)
        - The Play (always included - user's story and identity)
        - Selected Act + all its Scenes (if an act is selected)
        """
        from pathlib import Path
        from .play_fs import (
            list_scenes,
            kb_read,
            list_attachments,
        )

        ctx_parts: list[str] = []

        # 1. README - Always in context (app identity and documentation)
        try:
            readme_path = Path(__file__).parent.parent.parent / "README.md"
            if readme_path.exists():
                readme_content = readme_path.read_text(encoding="utf-8").strip()
                # Cap README to reasonable size
                cap = 4000
                if len(readme_content) > cap:
                    readme_content = readme_content[:cap] + "\n…"
                ctx_parts.append(f"REOS_README:\n{readme_content}")
        except (FileNotFoundError, PermissionError, OSError):
            pass

        # 2. The Play - Always in context (user's story)
        try:
            me = play_read_me_markdown().strip()
            if me:
                cap = 2000
                if len(me) > cap:
                    me = me[:cap] + "\n…"
                ctx_parts.append(
                    f"THE_PLAY (About the USER — the human you serve, NOT about you the AI):\n"
                    f"The user is a separate person from you. Never confuse their identity with yours.\n"
                    f"Use this to answer questions about 'me', 'myself', 'my goals', etc.\n"
                    f"{me}"
                )

            # Play-level attachments
            play_attachments = list_attachments()
            if play_attachments:
                att_list = ", ".join(f"{a.file_name} ({a.file_type})" for a in play_attachments)
                ctx_parts.append(f"PLAY_ATTACHMENTS: {att_list}")
        except (FileNotFoundError, PermissionError, OSError) as e:
            logger.warning("Failed to read me.md: %s", e)

        # 3. Selected Act and its hierarchy
        try:
            acts, active_id = play_list_acts()
        except (FileNotFoundError, PermissionError, OSError):
            return "\n\n".join(ctx_parts)

        if not active_id:
            if ctx_parts:
                ctx_parts.append("NO_ACTIVE_ACT: User has not selected an Act to focus on.")
            return "\n\n".join(ctx_parts)

        act = next((a for a in acts if a.act_id == active_id), None)
        if act is None:
            return "\n\n".join(ctx_parts)

        # Act context
        act_ctx = f"ACTIVE_ACT: {act.title} (selected = in context with all Scenes)"
        if act.notes.strip():
            act_ctx += f"\nACT_NOTES: {act.notes.strip()}"

        # Act KB
        try:
            act_kb = kb_read(act_id=active_id, path="kb.md")
            if act_kb.strip():
                cap = 1500
                if len(act_kb) > cap:
                    act_kb = act_kb[:cap] + "\n…"
                act_ctx += f"\nACT_KB:\n{act_kb.strip()}"
        except (FileNotFoundError, PermissionError, OSError) as e:
            logger.debug("Failed to read act KB for %s: %s", active_id, e)

        # Act attachments
        try:
            act_attachments = list_attachments(act_id=active_id)
            if act_attachments:
                att_list = ", ".join(f"{a.file_name} ({a.file_type})" for a in act_attachments)
                act_ctx += f"\nACT_ATTACHMENTS: {att_list}"
        except (FileNotFoundError, PermissionError, OSError) as e:
            logger.debug("Failed to list act attachments for %s: %s", active_id, e)

        ctx_parts.append(act_ctx)

        # Scenes under active act
        try:
            scenes = list_scenes(act_id=active_id)
            for scene in scenes:
                scene_ctx = f"  SCENE: {scene.title}"
                if scene.stage:
                    scene_ctx += f" | Stage: {scene.stage}"
                if scene.notes and scene.notes.strip():
                    scene_ctx += f"\n    Notes: {scene.notes.strip()[:500]}"
                if scene.calendar_event_id:
                    scene_ctx += " | (calendar event)"

                # Scene attachments
                try:
                    scene_attachments = list_attachments(act_id=active_id, scene_id=scene.scene_id)
                    if scene_attachments:
                        att_list = ", ".join(f"{a.file_name}" for a in scene_attachments)
                        scene_ctx += f"\n    Attachments: {att_list}"
                except (FileNotFoundError, PermissionError, OSError) as e:
                    logger.debug("Failed to list scene attachments for %s: %s", scene.scene_id, e)

                ctx_parts.append(scene_ctx)
        except (FileNotFoundError, PermissionError, OSError) as e:
            logger.warning("Failed to list scenes for act %s: %s", active_id, e)

        return "\n\n".join(ctx_parts)

    def _get_learned_context(self) -> str:
        """Get learned knowledge from previous compactions.

        This injects facts, lessons, decisions, and preferences that the AI
        has learned from past conversations with this user.
        """
        try:
            from .knowledge_store import KnowledgeStore
            from .play_fs import list_acts as play_list_acts

            # Get active act
            acts, active_act_id = play_list_acts()

            store = KnowledgeStore()
            learned_md = store.get_learned_markdown(active_act_id)

            if learned_md.strip():
                return (
                    "LEARNED_KNOWLEDGE (from previous conversations):\n"
                    "Use this to personalize responses and remember user preferences.\n"
                    f"{learned_md}"
                )
            return ""
        except Exception as e:
            logger.debug("Could not load learned knowledge: %s", e)
            return ""

    def _get_codebase_context(self) -> str:
        """Get codebase self-awareness context.

        This allows ReOS to answer questions about its own implementation,
        architecture, and source code structure.

        Uses the architecture module which provides:
        1. Compressed architecture blueprint (~8K tokens)
        2. ADR summaries
        3. Codebase stats

        For deeper queries, use the RAG tools:
        - reos_search_codebase: Find relevant code
        - reos_get_architecture: Full architecture doc
        - reos_file_summary: File contents summary
        """
        try:
            from .architecture import get_architecture_context

            arch_ctx = get_architecture_context(max_tokens=6000)
            if arch_ctx.strip():
                return (
                    "ARCHITECTURE_REFERENCE (ReOS system architecture):\n"
                    "Use this to understand how ReOS works. For deeper queries, "
                    "use reos_search_codebase or reos_file_summary tools.\n\n"
                    f"{arch_ctx}"
                )
            return ""
        except Exception as e:
            logger.debug("Could not load architecture context: %s", e)
            # Fallback to legacy codebase_index if available
            try:
                from .codebase_index import get_codebase_context as get_codebase_ctx

                codebase_ctx = get_codebase_ctx()
                if codebase_ctx.strip():
                    return f"CODEBASE_REFERENCE:\n{codebase_ctx}"
            except Exception as e2:
                logger.debug("Fallback codebase context also failed: %s", e2)
            return ""

    def _get_memory_context(self, user_text: str, act_id: str | None = None) -> str:
        """Get relevant memory context from conversation memories and block graph.

        Two retrieval paths:
        1. Conversation memories: Approved memories from the compression pipeline,
           with signal weighting (log2(signal_count+1)) and recency decay.
        2. Block graph: Semantically similar blocks via embeddings + graph expansion.

        Conversation memories are prioritized (they represent compressed meaning).

        Args:
            user_text: The user's message to find relevant memory for.
            act_id: Optional act ID to scope the search.

        Returns:
            Formatted memory context as markdown, or empty string.
        """
        try:
            if not user_text or len(user_text.strip()) < 10:
                return ""

            parts: list[str] = []

            # Retrieve conversation memories (approved, signal-weighted)
            conv_memories = self._memory_retriever.retrieve_conversation_memories(
                query=user_text,
                act_id=act_id,
                max_results=10,
                semantic_threshold=0.5,
            )
            conv_md = conv_memories.to_prompt_block()
            if conv_md.strip():
                parts.append(conv_md)

            # Also retrieve from general block graph
            block_result = self._memory_retriever.retrieve(
                query=user_text,
                act_id=act_id,
                max_results=5,
                semantic_threshold=0.5,
                graph_depth=1,
                include_graph_expansion=True,
            )
            block_md = block_result.to_markdown()
            if block_md.strip():
                parts.append(block_md)

            return "\n\n".join(parts)
        except Exception as e:
            logger.debug("Could not retrieve memory context: %s", e)
            return ""

    def _build_full_context(
        self,
        user_text: str,
        conversation_id: str,
        agent_type: str | None = None,
    ) -> ConversationContext:
        """Build all conversation context in ONE pass.

        This consolidates all context gathering to avoid redundant I/O.
        The returned ConversationContext contains everything needed for:
        - Building the system prompt
        - Intent engine (play_data)
        - Response generation

        Respects user's disabled_sources settings from the context overlay.
        When a source is disabled, it won't be loaded or included in the prompt.

        Args:
            user_text: The user's message
            conversation_id: Current conversation ID
            agent_type: Agent type (cairn, riva, etc.)

        Returns:
            ConversationContext with all context loaded once
        """
        # Get user's disabled sources from settings
        disabled_sources = self._get_disabled_sources()
        if disabled_sources:
            logger.debug("Context sources disabled by user: %s", disabled_sources)

        # Get persona (agent config) - system_prompt is never disabled
        persona = self._get_persona(agent_type)
        persona_system = str(persona.get("system_prompt") or "")
        persona_context_str = str(persona.get("default_context") or "")

        # Get Play context and data (only if not disabled)
        # play_context is formatted text, play_data is structured for intent engine
        # Note: play_data is still loaded for intent engine even if display is disabled
        if "play_context" not in disabled_sources:
            play_context = self._get_play_context()
            play_data = self._gather_play_data()
        else:
            play_context = ""
            play_data = self._gather_play_data()  # Still need for intent engine

        # Get other context sources (only if not disabled)
        learned_context = "" if "learned_kb" in disabled_sources else self._get_learned_context()
        system_context = "" if "system_state" in disabled_sources else self._get_system_context()
        codebase_context = "" if "codebase" in disabled_sources else self._get_codebase_context()

        # Get memory context (semantic search + graph expansion)
        # This retrieves relevant past interactions, knowledge, and reasoning chains
        memory_context = (
            ""
            if "memory" in disabled_sources
            else self._get_memory_context(user_text, play_data.get("active_act_id"))
        )

        # Conversation history ("messages") - always loaded, cannot be disabled
        conversation_history = self._build_conversation_context(conversation_id)

        # Inject state briefing on first message of a new conversation.
        # conversation_history is empty only before any prior messages have been
        # exchanged in this conversation session, making it a reliable first-turn
        # detector without requiring an extra DB query.
        if "memory" not in disabled_sources and not conversation_history:
            try:
                from .services.state_briefing_service import StateBriefingService
                briefing = StateBriefingService().get_or_generate()
                if briefing and briefing.content:
                    memory_context = (
                        f"## Situational Awareness\n{briefing.content}\n\n{memory_context}"
                    )
            except Exception:
                logger.debug("State briefing unavailable, continuing without")

        # Build temporal context (zero inference cost — pure datetime math)
        temporal_context = ""
        try:
            from .services.temporal_context import build_temporal_context

            temporal_context = build_temporal_context()
        except Exception:
            logger.debug("Temporal context unavailable, continuing without")

        # Build the context object
        ctx = ConversationContext(
            user_text=user_text,
            conversation_id=conversation_id,
            temporal_context=temporal_context,
            persona_system=persona_system,
            persona_context=persona_context_str,
            play_context=play_context,
            play_data=play_data,
            learned_context=learned_context,
            system_context=system_context,
            codebase_context=codebase_context,
            memory_context=memory_context,
            conversation_history=conversation_history,
        )

        # Compute full prompt prefix
        ctx.full_prompt_prefix = ctx.build_prompt_prefix()

        return ctx

    def _user_opted_into_diff(self, user_text: str) -> bool:
        t = user_text.lower()
        return any(
            phrase in t
            for phrase in [
                "include diff",
                "show diff",
                "full diff",
                "git diff",
                "patch",
                "unified diff",
            ]
        )

    def _is_personal_question(self, user_text: str) -> bool:
        """Detect if the question is about the user (personal) vs the system.

        Personal questions should be answered from THE_PLAY context, not system tools.
        This bypasses the tool selection phase for questions like "what do you know about me?"

        Returns:
            True if this is a personal question about the user's identity/goals/story.
        """
        t = user_text.lower()

        # Direct personal question patterns
        personal_patterns = [
            "about me",
            "about myself",
            "know about me",
            "know me",
            "my goals",
            "my story",
            "my vision",
            "my identity",
            "my name",
            "my background",
            "my principles",
            "my values",
            "my work",
            "my purpose",
            "who am i",
            "who i am",
            "what am i",
            "tell me about me",
            "describe me",
            "my philosophy",
            "my beliefs",
            "my journey",
            "my mission",
            "what do you know",  # When followed by context of "about me"
        ]

        # Check for personal patterns
        for pattern in personal_patterns:
            if pattern in t:
                return True

        # Also check for questions that reference "me" or "my" prominently
        # but NOT system-related contexts
        if any(word in t for word in ["me", "my", "myself", "i"]):
            # Exclude system-related contexts AND CAIRN-managed data
            # These should use tools, not THE_PLAY context
            system_contexts = [
                "my computer",
                "my machine",
                "my server",
                "my disk",
                "my memory",
                "my cpu",
                "my services",
                "my containers",
                "my docker",
                "my files",
                "my directory",
                "my process",
                "my network",
                "my package",
                # CAIRN-managed data (Thunderbird integration)
                "my calendar",
                "my schedule",
                "my appointments",
                "my meetings",
                "my events",
                "my contacts",
                "my address book",
                "my todos",
                "my tasks",
                "my email",
                "calendar",
                "schedule",
                "appointments",
            ]
            if not any(ctx in t for ctx in system_contexts):
                # Check for question words that suggest personal inquiry
                if any(q in t for q in ["who", "what do you know", "tell me"]):
                    return True

        return False

    def detect_intent(self, user_text: str) -> DetectedIntent | None:
        """Detect conversational intent from short user responses.

        Returns:
            DetectedIntent if a special intent is detected, None for normal questions.
        """
        text = user_text.strip()

        # Check for approval
        if _APPROVAL_PATTERN.match(text):
            return DetectedIntent(intent_type="approval")

        # Check for rejection
        if _REJECTION_PATTERN.match(text):
            return DetectedIntent(intent_type="rejection")

        # Check for numeric choice (1-9)
        numeric_match = _NUMERIC_CHOICE_PATTERN.match(text)
        if numeric_match:
            return DetectedIntent(
                intent_type="choice",
                choice_number=int(numeric_match.group(1)),
            )

        # Check for ordinal choice (first, second, etc.)
        ordinal_match = _ORDINAL_PATTERN.match(text)
        if ordinal_match:
            ordinal = ordinal_match.group(1).lower()
            return DetectedIntent(
                intent_type="choice",
                choice_number=_ORDINAL_MAP.get(ordinal, 1),
            )

        # Check for references (it, that, the service, etc.)
        reference_match = _REFERENCE_PATTERN.search(text)
        if reference_match and len(text) < 100:  # Short messages with references
            return DetectedIntent(
                intent_type="reference",
                reference_term=reference_match.group(1).lower(),
            )

        return None

    def resolve_reference(
        self,
        reference_term: str,
        conversation_id: str,
    ) -> dict[str, Any] | None:
        """Resolve a reference term (it, that, etc.) from conversation context.

        Returns:
            Dict with resolved entity info, or None if cannot resolve.
        """
        # Get recent messages to find what "it" refers to
        messages = self._db.get_recent_messages(conversation_id=conversation_id, limit=5)

        if not messages:
            return None

        # Look for entities in recent assistant messages
        for msg in reversed(messages):
            if msg.get("role") != "assistant":
                continue

            content = str(msg.get("content", ""))
            metadata_str = msg.get("metadata")

            # Check tool calls in metadata for services/containers
            if metadata_str:
                try:
                    metadata = json.loads(metadata_str)
                    tool_calls = metadata.get("tool_calls", [])
                    for tc in tool_calls:
                        if not tc.get("ok"):
                            continue
                        result = tc.get("result", {})

                        # Service mentioned
                        if "service" in reference_term or "service" in str(tc.get("name", "")):
                            if isinstance(result, dict) and "name" in result:
                                return {"type": "service", "name": result["name"]}

                        # Container mentioned
                        if "container" in reference_term or "container" in str(tc.get("name", "")):
                            if isinstance(result, dict) and ("id" in result or "name" in result):
                                return {
                                    "type": "container",
                                    "id": result.get("id"),
                                    "name": result.get("name"),
                                }

                        # File mentioned
                        if "file" in reference_term:
                            if isinstance(result, dict) and "path" in result:
                                return {"type": "file", "path": result["path"]}

                except (json.JSONDecodeError, TypeError):
                    pass

            # Simple text matching for common patterns
            patterns = [
                (r"service[:\s]+([a-zA-Z0-9_-]+)", "service"),
                (r"container[:\s]+([a-zA-Z0-9_-]+)", "container"),
                (r"`([^`]+\.service)`", "service"),
                (r"package[:\s]+([a-zA-Z0-9_-]+)", "package"),
            ]

            for pattern, entity_type in patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    return {"type": entity_type, "name": match.group(1)}

        return None

    def get_pending_approval_for_conversation(
        self,
        conversation_id: str,
    ) -> dict[str, Any] | None:
        """Get the most recent pending approval for a conversation."""
        approvals = self._db.get_pending_approvals()
        for approval in approvals:
            if approval.get("conversation_id") == conversation_id:
                return approval
        return None

    def _select_tools(
        self,
        *,
        user_text: str,
        tools: list[Tool],
        wants_diff: bool,
        persona_prefix: str,
        llm: LLMProvider,
        temperature: float,
        top_p: float,
        tool_call_limit: int,
    ) -> list[ToolCall]:
        # Simplified tool specs - just names and short descriptions
        # Full schemas overwhelm smaller models
        tool_specs = [
            {
                "name": t.name,
                "description": t.description[:100] if t.description else "",
            }
            for t in tools
        ]

        system = (
            "You are a TOOL SELECTOR. You MUST return ONLY a JSON object with tool_calls.\n"
            "DO NOT answer the question. DO NOT make up data. ONLY select tools.\n\n"
            + "CALENDAR/SCHEDULE questions → Use cairn_get_calendar\n"
            + "SYSTEM questions (CPU, memory, disk) → Use linux_system_info\n"
            + "PERSONAL questions (about me, my goals) → Return empty tool_calls\n\n"
            + "TOOLS:\n"
            + "- cairn_get_calendar: Get calendar events (USE FOR ANY CALENDAR QUESTION)\n"
            + "- cairn_get_upcoming_events: Get upcoming events\n"
            + "- linux_system_info: CPU, memory, disk info\n"
            + "- linux_run_command: Execute shell commands\n\n"
            + "OUTPUT FORMAT (STRICT - no other format allowed):\n"
            + '{"tool_calls": [{"name": "TOOL_NAME", "arguments": {}}]}\n\n'
            + "EXAMPLES:\n"
            + 'User: \'what does my calendar look like\' → {"tool_calls": [{"name": "cairn_get_calendar", "arguments": {}}]}\n'
            + 'User: \'show me my schedule\' → {"tool_calls": [{"name": "cairn_get_calendar", "arguments": {}}]}\n'
            + 'User: \'how much RAM do I have\' → {"tool_calls": [{"name": "linux_system_info", "arguments": {}}]}\n'
            + "User: 'what are my goals' → {\"tool_calls\": []}\n"
        )

        user = (
            "TOOLS:\n" + json.dumps(tool_specs, indent=2) + "\n\n" + "USER_MESSAGE:\n" + user_text
        )

        import sys

        raw = llm.chat_json(system=system, user=user, temperature=temperature, top_p=top_p)
        print(
            f"[CAIRN DEBUG] LLM tool selection raw response: {raw[:500] if raw else 'None'}",
            file=sys.stderr,
        )
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            # Fallback: return empty - don't assume system tools
            print(
                f"[CAIRN DEBUG] LLM returned invalid JSON for tool selection: {e}", file=sys.stderr
            )
            return []

        # Handle case where LLM returns a list directly instead of dict
        if not isinstance(payload, dict):
            print(
                f"[CAIRN DEBUG] LLM returned non-dict for tool selection: {type(payload)}",
                file=sys.stderr,
            )
            return []

        calls = payload.get("tool_calls")
        print(f"[CAIRN DEBUG] LLM tool_calls parsed: {calls}", file=sys.stderr)
        if not isinstance(calls, list):
            print(f"[CAIRN DEBUG] LLM tool_calls is not a list: {type(calls)}", file=sys.stderr)
            return []

        out: list[ToolCall] = []
        valid_tool_names = {t.name for t in tools}

        for c in calls:
            if not isinstance(c, dict):
                continue
            name = c.get("name")
            args = c.get("arguments") or {}  # Default to empty dict if missing

            if not isinstance(name, str):
                continue
            if not isinstance(args, dict):
                args = {}

            # Map common LLM mistakes to actual tool names
            name_mapping = {
                "uptime": "linux_system_info",
                "system_info": "linux_system_info",
                "services": "linux_list_services",
                "list_services": "linux_list_services",
                "run_command": "linux_run_command",
                "run": "linux_run_command",
                "packages": "linux_list_packages",
                "docker": "linux_docker_containers",
                "containers": "linux_docker_containers",
                "list_docker_containers": "linux_docker_containers",
                "docker_containers": "linux_docker_containers",
                # CAIRN tool mappings
                "get_calendar": "cairn_get_calendar",
                "calendar": "cairn_get_calendar",
                "get_events": "cairn_get_calendar",
                "upcoming_events": "cairn_get_upcoming_events",
                "get_upcoming_events": "cairn_get_upcoming_events",
                "search_contacts": "cairn_search_contacts",
                "contacts": "cairn_search_contacts",
                "get_todos": "cairn_get_todos",
                "todos": "cairn_get_todos",
                "tasks": "cairn_get_todos",
                "surface_today": "cairn_surface_today",
                "today": "cairn_surface_today",
                "thunderbird_status": "cairn_thunderbird_status",
            }
            if name in name_mapping:
                name = name_mapping[name]

            # Only add if it's a valid tool
            if name in valid_tool_names:
                out.append(ToolCall(name=name, arguments=args))

        return out

    def _answer(
        self,
        *,
        user_text: str,
        tools: list[Tool],
        tool_results: list[dict[str, Any]],
        wants_diff: bool,
        persona_prefix: str,
        llm: LLMProvider,
        temperature: float,
        top_p: float,
    ) -> tuple[str, list[str]]:
        """Generate answer with optional thinking steps.

        Returns:
            Tuple of (answer, thinking_steps)
        """
        tool_dump = []
        for r in tool_results:
            rendered = (
                render_tool_result(r.get("result"))
                if r.get("ok")
                else json.dumps(r.get("error"), indent=2)
            )
            tool_dump.append(
                {
                    "name": r.get("name"),
                    "arguments": r.get("arguments"),
                    "ok": r.get("ok"),
                    "output": rendered,
                }
            )

        system = (
            persona_prefix
            + "\n\n"
            + "Answer the user's question.\n\n"
            + "INFORMATION SOURCES (in order of priority):\n"
            + "1. THE_PLAY context above - Contains info about the USER as a person (their story, goals, identity)\n"
            + "2. Tool outputs below - Contains info about the SYSTEM (computer, services, containers)\n"
            + "3. Conversation history - Previous messages in this chat\n\n"
            + "IMPORTANT:\n"
            + "- For personal questions ('about me', 'my goals'), THE_PLAY context IS your source - you already have it!\n"
            + "- Empty tool outputs is NORMAL for personal questions - don't say you lack information\n"
            + "- For system questions, use the tool outputs\n\n"
            + "RESPONSE FORMAT:\n"
            + "Use this exact format to separate your reasoning from your answer:\n\n"
            + "<thinking>\n"
            + "Your internal reasoning process here. What you're checking, what you found, etc.\n"
            + "Each distinct thought should be on its own line.\n"
            + "</thinking>\n\n"
            + "<answer>\n"
            + "Your final response to the user here. Clear, direct, helpful.\n"
            + "</answer>\n\n"
            + "Rules:\n"
            + "- Always use <thinking> and <answer> tags\n"
            + "- Put reasoning/checking/searching in <thinking>\n"
            + "- Put the final user-facing response in <answer>\n"
            + "- Be personal and direct - you know this user from THE_PLAY\n"
            + "- If THE_PLAY is empty for a personal question, suggest they fill out 'Your Story' in The Play\n"
            + "- Do not fabricate information; use what's in your context\n"
        )

        # Build user message - only include tool results if there are any
        if tool_dump:
            user = (
                user_text + "\n\n"
                "TOOL_RESULTS:\n" + json.dumps(tool_dump, indent=2, ensure_ascii=False)
            )
        else:
            # No tools called - this is a personal question
            # Add explicit hint to use THE_PLAY context
            user = (
                user_text + "\n\n"
                "NOTE: No system tools were called because this appears to be a personal question.\n"
                "Answer using THE_PLAY context above which contains information about the user.\n"
                "Do NOT say you don't have information - THE_PLAY IS your information source."
            )

        # Debug: trace what we're sending to the LLM
        import sys

        print(f"[CAIRN DEBUG] _answer called with {len(tool_dump)} tool results", file=sys.stderr)
        if tool_dump:
            print(
                f"[CAIRN DEBUG] Tool results preview: {json.dumps(tool_dump, indent=2)[:1000]}",
                file=sys.stderr,
            )
        print(f"[CAIRN DEBUG] User message preview: {user[:500]}", file=sys.stderr)

        raw = llm.chat_text(system=system, user=user, temperature=temperature, top_p=top_p)

        # Debug: trace LLM response
        print(
            f"[CAIRN DEBUG] LLM _answer raw response: {raw[:1000] if raw else 'None'}",
            file=sys.stderr,
        )

        return self._parse_thinking_answer(raw)

    def _parse_thinking_answer(self, raw: str) -> tuple[str, list[str]]:
        """Parse response with thinking tags from various formats.

        Supports:
        - <thinking>...</thinking> - ReOS prompted format
        - <think>...</think> - Native thinking models (DeepSeek-R1, QWQ)
        - <answer>...</answer> - ReOS prompted answer format

        Returns:
            Tuple of (answer, thinking_steps)
        """
        import re

        thinking_steps: list[str] = []
        answer = raw.strip()

        # Extract thinking section - check both formats
        # First try <think> (native thinking models like DeepSeek-R1, QWQ)
        thinking_match = re.search(r"<think>(.*?)</think>", raw, re.DOTALL | re.IGNORECASE)
        if not thinking_match:
            # Fall back to <thinking> (ReOS prompted format)
            thinking_match = re.search(
                r"<thinking>(.*?)</thinking>", raw, re.DOTALL | re.IGNORECASE
            )

        if thinking_match:
            thinking_content = thinking_match.group(1).strip()
            # Split into individual steps (by line or sentence)
            steps = [s.strip() for s in thinking_content.split("\n") if s.strip()]
            thinking_steps = steps

        # Extract answer section
        answer_match = re.search(r"<answer>(.*?)</answer>", raw, re.DOTALL | re.IGNORECASE)
        if answer_match:
            answer = answer_match.group(1).strip()
        else:
            # Fallback: remove thinking tags and use the rest
            # Remove both <think> and <thinking> variants
            answer = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE).strip()
            answer = re.sub(
                r"<thinking>.*?</thinking>", "", answer, flags=re.DOTALL | re.IGNORECASE
            ).strip()
            # Also remove any leftover tags
            answer = re.sub(
                r"</?(?:think|thinking|answer)>", "", answer, flags=re.IGNORECASE
            ).strip()

        return answer, thinking_steps
