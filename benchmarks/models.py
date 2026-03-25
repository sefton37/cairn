"""Model matrix for the Cairn benchmark framework.

16 Ollama models spanning four capability tiers plus Anthropic API baseline.
Copied from ReOS/benchmarks/models.py — identical model matrix for
cross-project comparison.
"""

MODEL_MATRIX = [
    # ── Sub-1B: sanity floor ────────────────────────────────────────────────
    {
        "name": "qwen2.5:0.5b",
        "family": "qwen2.5",
        "params": "0.5b",
        "rationale": "Smallest useful Qwen; establishes the capability floor",
    },
    # ── 1–2B: lightweight tier ──────────────────────────────────────────────
    {
        "name": "qwen2.5:1.5b",
        "family": "qwen2.5",
        "params": "1.5b",
        "rationale": "Strong instruction following for size; fast inference",
    },
    {
        "name": "llama3.2:1b",
        "family": "llama3.2",
        "params": "1b",
        "rationale": "Meta's 1B; representative of Llama family at minimum size",
    },
    {
        "name": "gemma2:2b",
        "family": "gemma2",
        "params": "2b",
        "rationale": "Google's 2B; known good instruction tuning",
    },
    # ── 3–4B: mid-lightweight ───────────────────────────────────────────────
    {
        "name": "qwen2.5:3b",
        "family": "qwen2.5",
        "params": "3b",
        "rationale": "Qwen 3B step; tests family scaling curve",
    },
    {
        "name": "llama3.2:3b",
        "family": "llama3.2",
        "params": "3b",
        "rationale": "Meta's 3B; Llama family scaling comparison",
    },
    {
        "name": "phi3:mini-128k",
        "family": "phi3",
        "params": "3.8b",
        "rationale": "Microsoft Phi-3 mini; strong reasoning relative to size",
    },
    # ── 7–9B: main production tier ──────────────────────────────────────────
    {
        "name": "qwen2.5:7b",
        "family": "qwen2.5",
        "params": "7b",
        "rationale": "Qwen 7B; widely used, good instruction following",
    },
    {
        "name": "llama3.1:8b-instruct-q5_K_M",
        "family": "llama3.1",
        "params": "8b",
        "rationale": "Meta's 8B instruct q5_K_M; popular production choice",
    },
    {
        "name": "mistral:latest",
        "family": "mistral",
        "params": "7b",
        "rationale": "Mistral 7B v0.3; strong on short structured outputs",
    },
    {
        "name": "codellama:7b",
        "family": "codellama",
        "params": "7b",
        "rationale": "Code-specialized; hypothesis: may excel at structured tool selection",
    },
    {
        "name": "gemma2:9b",
        "family": "gemma2",
        "params": "9b",
        "rationale": "Google 9B; cross-family comparison at this size tier",
    },
    # ── 13–16B: large tier ──────────────────────────────────────────────────
    {
        "name": "codellama:13b",
        "family": "codellama",
        "params": "13b",
        "rationale": "Code-specialized 13B; tests if specialization still helps at scale",
    },
    {
        "name": "qwen2.5:14b",
        "family": "qwen2.5",
        "params": "14b",
        "rationale": "Qwen family ceiling in practical GPU memory range",
    },
    {
        "name": "phi3:medium-128k",
        "family": "phi3",
        "params": "14b",
        "rationale": "Phi-3 medium; tests whether Phi's efficiency scales",
    },
    {
        "name": "deepseek-coder-v2:16b",
        "family": "deepseek",
        "params": "16b",
        "rationale": "DeepSeek code model; structured output hypothesis",
    },
    # ── Anthropic API models ────────────────────────────────────────────────
    {
        "name": "claude-sonnet-4-20250514",
        "family": "claude",
        "params": "api",
        "rationale": "Anthropic Sonnet 4; API baseline for comparison with local models",
    },
]


def get_model_info(model_name: str) -> dict | None:
    """Look up a model entry by name."""
    for m in MODEL_MATRIX:
        if m["name"] == model_name:
            return m
    return None


def is_anthropic_model(model_name: str) -> bool:
    """Check if a model name is an Anthropic API model."""
    info = get_model_info(model_name)
    return info is not None and info.get("params") == "api"
