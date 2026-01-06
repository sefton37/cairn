"""Intent Discovery - understanding user intent from multiple sources.

Intent is discovered by synthesizing understanding from:
1. The user's prompt (what they explicitly asked for)
2. The Play context (Act goals, Scene context, historical Beats)
3. The codebase state (existing patterns, architecture, conventions)

This multi-source approach prevents hallucination by grounding intent
in concrete, observable reality.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from reos.code_mode.sandbox import CodeSandbox
    from reos.ollama import OllamaClient
    from reos.play_fs import Act

logger = logging.getLogger(__name__)


@dataclass
class PromptIntent:
    """Intent extracted from the user's explicit request."""

    raw_prompt: str
    action_verb: str          # What they want done: "add", "fix", "refactor", etc.
    target: str               # What they want it done to: "function", "test", "module"
    constraints: list[str]    # Any explicit constraints mentioned
    examples: list[str]       # Any examples they provided
    summary: str              # One-sentence summary of the request


@dataclass
class PlayIntent:
    """Intent derived from The Play context."""

    act_goal: str             # The Act's overarching goal
    act_artifact: str         # What artifact this Act produces
    scene_context: str        # Current Scene context if any
    recent_work: list[str]    # Recent Beats/commits showing trajectory
    knowledge_hints: list[str]  # Relevant knowledge from KB


@dataclass
class CodebaseIntent:
    """Intent derived from codebase analysis."""

    language: str             # Primary language
    architecture_style: str   # "monolith", "microservices", "layered", etc.
    conventions: list[str]    # Observed conventions (naming, structure)
    related_files: list[str]  # Files likely relevant to this task
    existing_patterns: list[str]  # Patterns to follow
    test_patterns: str        # How tests are structured


@dataclass
class DiscoveredIntent:
    """Complete intent synthesized from all sources.

    This is the single source of truth for what the system believes
    the user wants. It must be explicit and grounded in evidence.
    """

    # Core understanding
    goal: str                 # Clear statement of what should be accomplished
    why: str                  # Why this matters (from Play context)
    what: str                 # What specifically needs to change
    how_constraints: list[str]  # How it should be done (constraints)

    # Source intents
    prompt_intent: PromptIntent
    play_intent: PlayIntent
    codebase_intent: CodebaseIntent

    # Metadata
    confidence: float         # 0-1 confidence in this understanding
    ambiguities: list[str]    # Things that are unclear
    assumptions: list[str]    # Assumptions being made
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def summary(self) -> str:
        """Generate human-readable summary of discovered intent."""
        lines = [
            "## Discovered Intent",
            "",
            f"**Goal:** {self.goal}",
            f"**Why:** {self.why}",
            f"**What:** {self.what}",
            "",
        ]

        if self.how_constraints:
            lines.append("**Constraints:**")
            for c in self.how_constraints:
                lines.append(f"- {c}")
            lines.append("")

        if self.assumptions:
            lines.append("**Assumptions:**")
            for a in self.assumptions:
                lines.append(f"- {a}")
            lines.append("")

        if self.ambiguities:
            lines.append("**Ambiguities to resolve:**")
            for amb in self.ambiguities:
                lines.append(f"- {amb}")
            lines.append("")

        lines.append(f"**Confidence:** {self.confidence:.0%}")

        return "\n".join(lines)


class IntentDiscoverer:
    """Discovers user intent from multiple sources.

    Uses different analytical perspectives to build a complete picture
    of what the user wants, grounded in observable evidence.
    """

    def __init__(
        self,
        sandbox: CodeSandbox,
        ollama: OllamaClient | None = None,
    ) -> None:
        self.sandbox = sandbox
        self._ollama = ollama

    def discover(
        self,
        prompt: str,
        act: Act,
        knowledge_context: str = "",
    ) -> DiscoveredIntent:
        """Discover intent from all available sources.

        Args:
            prompt: The user's explicit request.
            act: The active Act with context.
            knowledge_context: Optional knowledge base context.

        Returns:
            DiscoveredIntent synthesizing all sources.
        """
        # Phase 1: Extract intent from each source
        prompt_intent = self._analyze_prompt(prompt)
        play_intent = self._analyze_play_context(act, knowledge_context)
        codebase_intent = self._analyze_codebase(prompt)

        # Phase 2: Synthesize into unified intent
        return self._synthesize_intent(
            prompt=prompt,
            prompt_intent=prompt_intent,
            play_intent=play_intent,
            codebase_intent=codebase_intent,
        )

    def _analyze_prompt(self, prompt: str) -> PromptIntent:
        """Extract intent from the user's explicit prompt."""
        if self._ollama is not None:
            return self._analyze_prompt_with_llm(prompt)
        return self._analyze_prompt_heuristic(prompt)

    def _analyze_prompt_heuristic(self, prompt: str) -> PromptIntent:
        """Fallback prompt analysis without LLM."""
        # Simple heuristic extraction
        words = prompt.lower().split()

        # Find action verb
        action_verbs = ["add", "create", "write", "implement", "fix", "debug",
                       "refactor", "update", "modify", "remove", "delete", "test"]
        action_verb = next((w for w in words if w in action_verbs), "implement")

        # Find target
        targets = ["function", "class", "method", "test", "module", "file",
                  "feature", "endpoint", "api", "bug", "error"]
        target = next((w for w in words if w in targets), "code")

        return PromptIntent(
            raw_prompt=prompt,
            action_verb=action_verb,
            target=target,
            constraints=[],
            examples=[],
            summary=prompt[:200],
        )

    def _analyze_prompt_with_llm(self, prompt: str) -> PromptIntent:
        """Extract intent from prompt using LLM."""
        system = """You analyze user requests to extract structured intent.
Output JSON with these fields:
{
    "action_verb": "the main action (add, fix, create, refactor, etc.)",
    "target": "what the action applies to (function, class, test, etc.)",
    "constraints": ["any explicit constraints or requirements"],
    "examples": ["any examples the user provided"],
    "summary": "one clear sentence summarizing the request"
}"""

        try:
            response = self._ollama.chat_json(  # type: ignore
                system=system,
                user=prompt,
                temperature=0.1,
            )
            data = json.loads(response)
            return PromptIntent(
                raw_prompt=prompt,
                action_verb=data.get("action_verb", "implement"),
                target=data.get("target", "code"),
                constraints=data.get("constraints", []),
                examples=data.get("examples", []),
                summary=data.get("summary", prompt[:200]),
            )
        except Exception as e:
            logger.warning("LLM prompt analysis failed: %s", e)
            return self._analyze_prompt_heuristic(prompt)

    def _analyze_play_context(
        self,
        act: Act,
        knowledge_context: str,
    ) -> PlayIntent:
        """Extract intent from The Play context."""
        # Get Act context
        act_goal = act.title
        act_artifact = act.artifact_type or "software"

        # Parse code_config for additional context
        code_config = act.code_config or {}
        language = code_config.get("language", "unknown")

        # Get recent work from git
        recent_work = []
        try:
            commits = self.sandbox.recent_commits(count=5)
            recent_work = [c.message for c in commits]
        except Exception:
            pass

        # Parse knowledge hints
        knowledge_hints = []
        if knowledge_context:
            # Extract key points from knowledge context
            for line in knowledge_context.split("\n"):
                if line.strip() and len(line) < 200:
                    knowledge_hints.append(line.strip())
            knowledge_hints = knowledge_hints[:5]  # Limit

        return PlayIntent(
            act_goal=act_goal,
            act_artifact=act_artifact,
            scene_context="",  # TODO: Get from active Scene
            recent_work=recent_work,
            knowledge_hints=knowledge_hints,
        )

    def _analyze_codebase(self, prompt: str) -> CodebaseIntent:
        """Extract intent from codebase analysis."""
        # Detect language
        language = self._detect_language()

        # Detect architecture style
        architecture = self._detect_architecture()

        # Find related files
        related = self._find_related_files(prompt)

        # Detect conventions
        conventions = self._detect_conventions()

        # Detect test patterns
        test_patterns = self._detect_test_patterns()

        return CodebaseIntent(
            language=language,
            architecture_style=architecture,
            conventions=conventions,
            related_files=related,
            existing_patterns=[],  # TODO: Extract patterns
            test_patterns=test_patterns,
        )

    def _detect_language(self) -> str:
        """Detect primary language of the codebase."""
        py_files = len(self.sandbox.find_files("**/*.py"))
        ts_files = len(self.sandbox.find_files("**/*.ts"))
        js_files = len(self.sandbox.find_files("**/*.js"))
        rs_files = len(self.sandbox.find_files("**/*.rs"))
        go_files = len(self.sandbox.find_files("**/*.go"))

        counts = {
            "python": py_files,
            "typescript": ts_files,
            "javascript": js_files,
            "rust": rs_files,
            "go": go_files,
        }

        if max(counts.values()) == 0:
            return "unknown"

        return max(counts, key=lambda k: counts[k])

    def _detect_architecture(self) -> str:
        """Detect architecture style from structure."""
        has_src = len(self.sandbox.find_files("src/**/*")) > 0
        has_tests = len(self.sandbox.find_files("tests/**/*")) > 0
        has_services = len(self.sandbox.find_files("**/services/**/*")) > 0
        has_handlers = len(self.sandbox.find_files("**/handlers/**/*")) > 0

        if has_services and has_handlers:
            return "layered"
        if has_src and has_tests:
            return "standard"
        return "flat"

    def _find_related_files(self, prompt: str) -> list[str]:
        """Find files likely relevant to the request."""
        related = []

        # Extract potential file/module names from prompt
        words = prompt.lower().split()
        for word in words:
            # Search for files matching the word
            matches = self.sandbox.grep(
                pattern=word,
                glob_pattern="**/*.py",
                max_results=5,
            )
            for m in matches:
                if m.path not in related:
                    related.append(m.path)

        return related[:10]  # Limit to 10

    def _detect_conventions(self) -> list[str]:
        """Detect coding conventions from the codebase."""
        conventions = []

        # Check for type hints
        try:
            type_hints = self.sandbox.grep(
                pattern=r"def \w+\([^)]*:[^)]+\)",
                glob_pattern="**/*.py",
                max_results=1,
            )
            if type_hints:
                conventions.append("Uses type hints")
        except Exception:
            pass

        # Check for docstrings
        try:
            docstrings = self.sandbox.grep(
                pattern=r'""".*"""',
                glob_pattern="**/*.py",
                max_results=1,
            )
            if docstrings:
                conventions.append("Uses docstrings")
        except Exception:
            pass

        # Check for dataclasses
        try:
            dataclasses = self.sandbox.grep(
                pattern=r"@dataclass",
                glob_pattern="**/*.py",
                max_results=1,
            )
            if dataclasses:
                conventions.append("Uses dataclasses")
        except Exception:
            pass

        return conventions

    def _detect_test_patterns(self) -> str:
        """Detect how tests are structured."""
        test_files = self.sandbox.find_files("**/test_*.py")
        if test_files:
            return "pytest (test_*.py)"

        spec_files = self.sandbox.find_files("**/*_spec.py")
        if spec_files:
            return "spec (*_spec.py)"

        return "unknown"

    def _synthesize_intent(
        self,
        prompt: str,
        prompt_intent: PromptIntent,
        play_intent: PlayIntent,
        codebase_intent: CodebaseIntent,
    ) -> DiscoveredIntent:
        """Synthesize all intents into unified understanding."""
        if self._ollama is not None:
            return self._synthesize_with_llm(
                prompt, prompt_intent, play_intent, codebase_intent
            )
        return self._synthesize_heuristic(
            prompt, prompt_intent, play_intent, codebase_intent
        )

    def _synthesize_heuristic(
        self,
        prompt: str,
        prompt_intent: PromptIntent,
        play_intent: PlayIntent,
        codebase_intent: CodebaseIntent,
    ) -> DiscoveredIntent:
        """Synthesize without LLM."""
        goal = prompt_intent.summary
        why = f"Part of {play_intent.act_goal}"
        what = f"{prompt_intent.action_verb} {prompt_intent.target}"

        constraints = list(prompt_intent.constraints)
        if codebase_intent.language != "unknown":
            constraints.append(f"Use {codebase_intent.language}")
        if codebase_intent.conventions:
            constraints.extend(codebase_intent.conventions)

        return DiscoveredIntent(
            goal=goal,
            why=why,
            what=what,
            how_constraints=constraints,
            prompt_intent=prompt_intent,
            play_intent=play_intent,
            codebase_intent=codebase_intent,
            confidence=0.7,
            ambiguities=[],
            assumptions=[],
        )

    def _synthesize_with_llm(
        self,
        prompt: str,
        prompt_intent: PromptIntent,
        play_intent: PlayIntent,
        codebase_intent: CodebaseIntent,
    ) -> DiscoveredIntent:
        """Synthesize using LLM for deeper understanding."""
        system = """You synthesize user intent from multiple sources into a clear understanding.

Given:
1. The user's prompt and extracted intent
2. The Play context (project goals, recent work)
3. The codebase context (language, architecture, conventions)

Output JSON:
{
    "goal": "Clear, specific statement of what should be accomplished",
    "why": "Why this matters in the context of the project",
    "what": "Specifically what needs to change in the code",
    "how_constraints": ["Constraints on how to implement"],
    "confidence": 0.0-1.0,
    "ambiguities": ["Things that are unclear"],
    "assumptions": ["Assumptions being made"]
}

Be specific. Ground everything in the provided context. Flag ambiguities honestly."""

        context = f"""
USER PROMPT: {prompt}

PROMPT ANALYSIS:
- Action: {prompt_intent.action_verb}
- Target: {prompt_intent.target}
- Summary: {prompt_intent.summary}

PLAY CONTEXT:
- Act Goal: {play_intent.act_goal}
- Artifact: {play_intent.act_artifact}
- Recent Work: {', '.join(play_intent.recent_work[:3])}

CODEBASE CONTEXT:
- Language: {codebase_intent.language}
- Architecture: {codebase_intent.architecture_style}
- Conventions: {', '.join(codebase_intent.conventions)}
- Related Files: {', '.join(codebase_intent.related_files[:5])}
"""

        try:
            response = self._ollama.chat_json(  # type: ignore
                system=system,
                user=context,
                temperature=0.2,
            )
            data = json.loads(response)

            return DiscoveredIntent(
                goal=data.get("goal", prompt_intent.summary),
                why=data.get("why", f"Part of {play_intent.act_goal}"),
                what=data.get("what", f"{prompt_intent.action_verb} {prompt_intent.target}"),
                how_constraints=data.get("how_constraints", []),
                prompt_intent=prompt_intent,
                play_intent=play_intent,
                codebase_intent=codebase_intent,
                confidence=data.get("confidence", 0.7),
                ambiguities=data.get("ambiguities", []),
                assumptions=data.get("assumptions", []),
            )
        except Exception as e:
            logger.warning("LLM synthesis failed: %s", e)
            return self._synthesize_heuristic(
                prompt, prompt_intent, play_intent, codebase_intent
            )
