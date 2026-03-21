"""Scoring functions for Cairn memory benchmark results.

Five scoring dimensions, all pure functions:
    detection       — did the assessor produce the correct CREATE/NO_CHANGE decision?
    type            — was the memory type classified correctly?
    routing         — did the memory land in the right Act?
    narrative       — does the compressed narrative contain required phrases?
    auto_approve    — did the auto-approve gate behave correctly for the detected type?
"""

from __future__ import annotations

# Memory types that are auto-approved (no human review required)
_AUTO_APPROVE_TYPES = {"fact", "preference", "relationship"}

# Memory types that stay in pending_review for human confirmation
_PENDING_REVIEW_TYPES = {"commitment", "priority"}


def score_detection(actual: str | None, expected: str) -> int:
    """Score whether the assessor produced the correct CREATE/NO_CHANGE decision.

    Args:
        actual: The detection result returned by the assessor ('CREATE' or
            'NO_CHANGE'), or None if the pipeline errored.
        expected: The expected result ('CREATE' or 'NO_CHANGE').

    Returns:
        1 if actual == expected, else 0.
    """
    return 1 if actual == expected else 0


def score_type(
    actual_type: str | None,
    expected_type: str | None,
    detection_correct: int,
) -> int | None:
    """Score whether the memory type was classified correctly.

    Args:
        actual_type: The memory type assigned by the pipeline, or None.
        expected_type: The expected type from the corpus. None for negative
            cases where no memory should be created.
        detection_correct: Result of score_detection() for this case.

    Returns:
        None if expected_type is None (negative case — type not applicable).
        0 if detection_correct == 0 (detection was wrong; type is moot).
        1 if actual_type == expected_type, else 0.
    """
    if expected_type is None:
        return None
    if detection_correct == 0:
        return 0
    return 1 if actual_type == expected_type else 0


def score_routing(
    destination_act_title: str | None,
    expected_act_hint: str | None,
    detection_correct: int,
) -> int | None:
    """Score whether the memory was routed to the correct Act.

    Routing is checked by substring match: the expected_act_hint should appear
    in the resolved Act title (case-insensitive). This avoids brittle exact-
    title matching while still verifying domain-level routing.

    Args:
        destination_act_title: The title of the Act the memory was routed to,
            or None if routing did not occur.
        expected_act_hint: A fragment that should appear in the correct Act's
            title (e.g. "Career", "Health"). None means no routing constraint
            for this case (e.g. Your Story or cross-cutting memories).
        detection_correct: Result of score_detection() for this case.

    Returns:
        None if detection_correct == 0 (detection wrong; routing is moot).
        None if expected_act_hint is None (no routing constraint for this case).
        1 if expected_act_hint.lower() is found in destination_act_title.lower(),
        else 0.
    """
    if detection_correct == 0:
        return None
    if expected_act_hint is None:
        return None
    if destination_act_title is None:
        return 0
    return 1 if expected_act_hint.lower() in destination_act_title.lower() else 0


def score_narrative(
    narrative: str | None,
    required_phrases: list[str],
    detection_correct: int,
) -> int | None:
    """Score whether the compressed narrative contains all required phrases.

    Phrase matching is case-insensitive. All phrases must be present for a
    score of 1 — partial phrase presence scores 0.

    Args:
        narrative: The compressed narrative text produced by the pipeline,
            or None if no narrative was produced.
        required_phrases: List of strings that must all appear in the narrative.
            Empty list means narrative quality is not scored for this case.
        detection_correct: Result of score_detection() for this case.

    Returns:
        None if detection_correct == 0 (detection wrong; narrative is moot).
        None if required_phrases is empty (not scored for this case).
        1 if all phrases appear in narrative (case-insensitive), else 0.
    """
    if detection_correct == 0:
        return None
    if not required_phrases:
        return None
    if not narrative:
        return 0
    narrative_lower = narrative.lower()
    return 1 if all(phrase.lower() in narrative_lower for phrase in required_phrases) else 0


def score_auto_approve(
    detected_type: str | None,
    memory_status: str | None,
    expected_detection: str,
) -> int | None:
    """Score whether the auto-approve gate behaved correctly.

    Business rules:
    - fact, preference, relationship → should be auto-approved (status='approved')
    - commitment, priority → should stay pending_review (status='pending_review')

    Args:
        detected_type: The memory type assigned by the pipeline, or None.
        memory_status: The status field of the created memory record, or None
            if no memory was created or status could not be read.
        expected_detection: The expected detection result for this case
            ('CREATE' or 'NO_CHANGE').

    Returns:
        None if expected_detection == 'NO_CHANGE' (no memory expected; gate
            not applicable).
        None if detected_type or memory_status is None (pipeline did not
            produce the data needed to evaluate the gate).
        1 if the gate behaved correctly for the detected type, else 0.
    """
    if expected_detection == "NO_CHANGE":
        return None
    if detected_type is None or memory_status is None:
        return None

    if detected_type in _AUTO_APPROVE_TYPES:
        return 1 if memory_status == "approved" else 0
    if detected_type in _PENDING_REVIEW_TYPES:
        return 1 if memory_status == "pending_review" else 0

    # Unknown type — cannot evaluate gate
    return None
