"""E2E test runner — drives CairnAgent with mock data per profile."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

# Ensure Cairn src is importable
CAIRN_SRC = Path(__file__).parent.parent.parent / "src"
if str(CAIRN_SRC) not in sys.path:
    sys.path.insert(0, str(CAIRN_SRC))

from harness.mock_thunderbird import install_mock
from harness.question_generator import generate_questions
from harness.recorder import Recorder


def _extract_classification(events: list) -> dict[str, Any]:
    """Extract classification data from ConsciousnessObserver events."""
    result: dict[str, Any] = {}
    for ev in events:
        name = ev.event_type.name

        if name == "INTENT_EXTRACTED":
            result["classification_domain"] = ev.metadata.get("category")
            result["classification_action"] = ev.metadata.get("action")
            result["classification_confident"] = (
                1 if ev.metadata.get("confidence", 0) > 0.5 else 0
            )
            result["classification_reasoning"] = ev.metadata.get("reasoning", "")

        elif name == "TOOL_CALL_START":
            result["tool_called"] = ev.metadata.get("tool")
            result["tool_args"] = ev.metadata.get("args")

        elif name == "TOOL_CALL_COMPLETE":
            summary = ev.metadata.get("summary") or ev.content[:200]
            result["tool_result_summary"] = summary

    return result


def _check_ollama() -> bool:
    """Check that Ollama is reachable."""
    try:
        import httpx

        resp = httpx.get("http://localhost:11434/api/tags", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def _load_profile_meta(profile_dir: str) -> dict:
    """Load profile.json metadata."""
    meta_path = os.path.join(profile_dir, "profile.json")
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            data = json.load(f)
        # Flatten identity into top level for easy access
        identity = data.get("identity", {})
        return {
            "personality": data.get("personality", "analytical"),
            "department": identity.get("department", ""),
            "role": identity.get("title", ""),
            "full_name": identity.get("full_name", ""),
        }
    return {"personality": "analytical", "department": "", "role": "", "full_name": ""}


def run_profile(
    profile_id: str,
    profile_dir: str,
    recorder: Recorder,
    model_name: str,
    *,
    limit: int | None = None,
    dry_run: bool = False,
) -> int:
    """Run all questions for a single profile against a specific model.

    Returns:
        Number of questions completed (not skipped).
    """
    db_path = os.path.join(profile_dir, "talkingrock.db")
    if not os.path.exists(db_path):
        print(f"  [SKIP] No database at {db_path}")
        return 0

    profile_meta = _load_profile_meta(profile_dir)

    # Generate questions
    questions = generate_questions(profile_id, profile_meta, db_path)
    if limit:
        questions = questions[:limit]

    if dry_run:
        for q in questions:
            print(f"  [{profile_id}] {q['query_type']:<15} {q['text'][:60]}")
        return len(questions)

    # Copy DB to temp dir for isolation
    tmp_dir = tempfile.mkdtemp(prefix=f"harness_{profile_id}_")
    tmp_db = os.path.join(tmp_dir, "talkingrock.db")
    shutil.copy2(db_path, tmp_db)

    # Point Cairn at the temp dir and set the model
    os.environ["TALKINGROCK_DATA_DIR"] = tmp_dir
    os.environ["TALKINGROCK_OLLAMA_MODEL"] = model_name

    # Install mock Thunderbird bridge BEFORE importing agent
    install_mock(tmp_db)

    # Import agent components (after env is set)
    from cairn.agent import ChatAgent
    from cairn.cairn.consciousness_stream import ConsciousnessObserver
    from cairn.db import Database

    db = Database(tmp_db)
    db.migrate()  # Ensure app_state, agent_personas, etc. exist
    agent = ChatAgent(db=db)
    observer = ConsciousnessObserver.get_instance()

    completed = 0
    for i, question in enumerate(questions):
        qid = question["question_id"]

        # Resumability: skip already-completed questions
        if recorder.is_complete(qid):
            print(f"  [{profile_id}] {i + 1}/{len(questions)} "
                  f"{question['query_type']:<15} SKIP (done)")
            continue

        recorder.mark_started(question, profile_meta)
        print(f"  [{profile_id}] {i + 1}/{len(questions)} "
              f"{question['query_type']:<15} ", end="", flush=True)

        t0 = time.time()
        try:
            observer.start_session()

            response = agent.respond(
                question["text"],
                agent_type="cairn",
            )

            # Auto-approve: if the approval gate triggered, simulate the
            # user clicking "Approve" so we observe full tool execution.
            approval_was_needed = False
            if response.pending_approval_id:
                approval_was_needed = True
                print("APPROVE→ ", end="", flush=True)

                # Re-execute with force_approve to bypass the gate
                observer.end_session()
                observer.start_session()

                response = agent.respond(
                    question["text"],
                    agent_type="cairn",
                    force_approve=True,
                )

            events = observer.get_all()
            observer.end_session()

            elapsed_ms = int((time.time() - t0) * 1000)

            # Build result dict
            result: dict[str, Any] = {
                "response_text": response.answer,
                "behavior_mode": "tool" if response.tool_calls else "conversational",
                "verification_passed": 1,
                "needs_approval": 1 if approval_was_needed else 0,
                "total_ms": elapsed_ms,
                "consciousness_events": [
                    {
                        "type": ev.event_type.name,
                        "title": ev.title,
                        "content": ev.content[:500],
                        "metadata": ev.metadata,
                    }
                    for ev in events
                ],
            }

            # Merge classification data from events
            result.update(_extract_classification(events))

            recorder.record_result(qid, result)
            completed += 1

            tool_str = result.get("tool_called") or "-"
            approval_tag = " [approved]" if approval_was_needed else ""
            print(f"{elapsed_ms / 1000:.1f}s {tool_str}{approval_tag} OK")

        except Exception as e:
            elapsed_ms = int((time.time() - t0) * 1000)
            recorder.record_error(qid, str(e))
            print(f"{elapsed_ms / 1000:.1f}s ERR: {e}")

    # Cleanup
    db.close()
    shutil.rmtree(tmp_dir, ignore_errors=True)

    return completed


def run_harness(
    profile_dirs: dict[str, str],
    run_id: str,
    model_name: str,
    *,
    limit: int | None = None,
    dry_run: bool = False,
    resume: bool = False,
) -> Recorder:
    """Run the full harness across all profiles for one model.

    Args:
        profile_dirs: Map of profile_id -> directory path.
        run_id: Unique run identifier.
        model_name: Ollama model name to use.
        limit: Max questions per profile.
        dry_run: Print questions without calling LLM.
        resume: If True, reuse existing run_id and skip completed questions.

    Returns:
        Recorder with all results.
    """
    if not dry_run and not _check_ollama():
        print("ERROR: Ollama is not reachable at localhost:11434.")
        print("Start Ollama before running the harness.")
        sys.exit(1)

    recorder = Recorder(run_id, model_name)
    profile_ids = list(profile_dirs.keys())

    total_questions = len(profile_ids) * (limit or 8)
    if not resume:
        recorder.start_run(profile_ids, total_questions)

    print(f"\n{'=' * 60}")
    print(f"Model: {model_name}")
    print(f"Run:   {run_id}")
    print(f"Profiles: {len(profile_ids)}  Questions/profile: {limit or 8}")
    if dry_run:
        print("Mode: DRY RUN (no LLM calls)")
    print(f"{'=' * 60}")

    for profile_id, profile_dir in profile_dirs.items():
        print(f"\n--- {profile_id} ---")
        run_profile(
            profile_id,
            profile_dir,
            recorder,
            model_name,
            limit=limit,
            dry_run=dry_run,
        )

    if not dry_run:
        recorder.finish_run()
        print()
        recorder.print_summary()

    recorder.close()
    return recorder
