"""Central wiring for the ken-web API: storage paths + the LLM factory seam.

Storage paths come from the environment so a deployment (or a test) can point the
API at an isolated data directory. `make_llm()` is the **test seam**: handlers call
it at request time, so tests can `monkeypatch.setattr(deps, "make_llm", ...)` to
inject a `FakeLLM` without a live API key.
"""

from __future__ import annotations

import os
from pathlib import Path

from ken.llm import AnthropicLLM, LLMClient

# Default count of questions to generate per artifact (overridable via env).
N_QUESTIONS = int(os.getenv("KEN_N_QUESTIONS", "5"))


def _data_dir() -> Path:
    """The base directory for ken's file stores (env: KEN_DATA_DIR, default ./).

    Read lazily so tests that set KEN_DATA_DIR after import are honoured.
    """
    return Path(os.getenv("KEN_DATA_DIR", "."))


def manifest_path() -> str:
    return os.getenv("KEN_MANIFEST", str(_data_dir() / "ken.manifest.yaml"))


def questions_path() -> str:
    return os.getenv("KEN_QUESTIONS", str(_data_dir() / "ken.questions.json"))


def ledger_path() -> str:
    return os.getenv("KEN_LEDGER", str(_data_dir() / "ken.attempts.jsonl"))


def make_llm() -> LLMClient:
    """LLM factory — the test seam. Handlers call this at request time."""
    return AnthropicLLM()
