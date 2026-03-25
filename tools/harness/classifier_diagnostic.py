#!/usr/bin/env python3
"""Diagnostic: test classifier directly against all models.

Bypasses agent.respond() to isolate whether the LLM classifier returns
confident=true, or whether exceptions trigger the keyword fallback.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

CAIRN_SRC = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(CAIRN_SRC))

MODELS = [
    "llama3.2:1b",
    "qwen2.5:3b",
    "phi3:mini-128k",
    "mistral:latest",
    "CognitiveComputations/dolphin-llama3.1:8b",
    "llama3.1:8b-instruct-q5_K_M",
    "qwen2.5:14b",
    "magistral:24b",
]

TEST_QUERIES = [
    ("calendar", "What's on my calendar today?"),
    ("calendar_anxious", "Hey, I'm a bit worried — do i have any conflicts on my calendar? Can you help?"),
    ("calendar_terse", "Schedule?"),
    ("email", "Any urgent emails I should know about?"),
    ("project", "What's the status of the Q2 migration?"),
    ("task", "What should I work on next?"),
    ("personal", "Tell me about myself."),
    ("vague", "stuff"),
    ("off_topic", "What's the weather like in Tokyo?"),
]


def test_raw_llm(model: str) -> list[dict]:
    """Call the LLM directly with the classifier prompt and capture raw output."""
    from cairn.atomic_ops.classifier import CLASSIFICATION_SYSTEM_PROMPT

    import httpx

    system = CLASSIFICATION_SYSTEM_PROMPT.replace("{corrections_block}", "")
    results = []

    for label, query in TEST_QUERIES:
        user = f'Classify this request: "{query}"'
        try:
            resp = httpx.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.1, "top_p": 0.9},
                },
                timeout=60,
            )
            raw = resp.json()["message"]["content"]
            try:
                data = json.loads(raw)
                confident = data.get("confident", "MISSING")
                domain = data.get("domain", "MISSING")
                semantics = data.get("semantics", "MISSING")
                results.append({
                    "label": label,
                    "query": query,
                    "confident": confident,
                    "domain": domain,
                    "semantics": semantics,
                    "raw_json": data,
                    "error": None,
                })
            except json.JSONDecodeError as e:
                results.append({
                    "label": label,
                    "query": query,
                    "confident": None,
                    "domain": None,
                    "semantics": None,
                    "raw_json": None,
                    "raw_text": raw[:300],
                    "error": f"JSON parse: {e}",
                })
        except Exception as e:
            results.append({
                "label": label,
                "query": query,
                "confident": None,
                "domain": None,
                "semantics": None,
                "raw_json": None,
                "error": str(e),
            })

    return results


def test_classifier_object(model: str) -> list[dict]:
    """Test through the actual Classifier class to see if it falls back."""
    os.environ["TALKINGROCK_OLLAMA_MODEL"] = model

    # Force fresh provider creation
    from cairn.providers.ollama import OllamaProvider

    provider = OllamaProvider(
        url="http://localhost:11434",
        model=model,
    )

    from cairn.atomic_ops.classifier import AtomicClassifier as Classifier

    classifier = Classifier(llm=provider)

    results = []
    for label, query in TEST_QUERIES:
        try:
            result = classifier.classify(query)
            cls = result.classification
            results.append({
                "label": label,
                "query": query,
                "confident": cls.confident,
                "domain": cls.domain,
                "semantics": cls.semantics.value,
                "reasoning": cls.reasoning[:100] if cls.reasoning else "",
                "model_used": result.model,
                "fallback": result.model == "keyword_fallback",
                "error": None,
            })
        except Exception as e:
            results.append({
                "label": label,
                "query": query,
                "confident": None,
                "domain": None,
                "semantics": None,
                "model_used": None,
                "fallback": True,
                "error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc(),
            })

    return results


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="*", default=MODELS)
    parser.add_argument("--raw-only", action="store_true",
                        help="Only test raw LLM, skip Classifier object")
    parser.add_argument("--classifier-only", action="store_true",
                        help="Only test Classifier object, skip raw LLM")
    args = parser.parse_args()

    for model in args.models:
        print(f"\n{'#' * 70}")
        print(f"MODEL: {model}")
        print(f"{'#' * 70}")

        if not args.classifier_only:
            print(f"\n--- Raw LLM Output ---")
            raw_results = test_raw_llm(model)
            print(f"{'Label':<20} {'Confident':<12} {'Domain':<15} "
                  f"{'Semantics':<12} {'Error'}")
            print("-" * 75)
            for r in raw_results:
                conf = str(r["confident"]) if r["confident"] is not None else "FAIL"
                dom = str(r["domain"]) if r["domain"] is not None else "FAIL"
                sem = str(r["semantics"]) if r["semantics"] is not None else "FAIL"
                err = r["error"] or ""
                print(f"{r['label']:<20} {conf:<12} {dom:<15} {sem:<12} {err}")

        if not args.raw_only:
            print(f"\n--- Through Classifier Object ---")
            cls_results = test_classifier_object(model)
            print(f"{'Label':<20} {'Confident':<10} {'Domain':<15} "
                  f"{'Semantics':<12} {'Fallback':<10} {'Error'}")
            print("-" * 85)
            for r in cls_results:
                conf = str(r["confident"]) if r["confident"] is not None else "FAIL"
                dom = str(r["domain"]) if r["domain"] is not None else "FAIL"
                sem = str(r["semantics"]) if r["semantics"] is not None else "FAIL"
                fb = "YES" if r.get("fallback") else ""
                err = r["error"] or ""
                print(f"{r['label']:<20} {conf:<10} {dom:<15} {sem:<12} {fb:<10} {err}")
                if r.get("traceback") and r["error"]:
                    print(f"  TB: {r['traceback'].strip().split(chr(10))[-1]}")

        print()


if __name__ == "__main__":
    main()
