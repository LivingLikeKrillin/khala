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
from ken.store import KenStore
from ken_web_api.auth_store import AuthStore, PostgresAuthStore

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


SESSION_COOKIE = "ken_session"
DEFAULT_PERSON = "local"           # the identity when auth is OFF
DEFAULT_TENANT = "default"         # the tenant when auth is OFF or unspecified
SESSION_TTL_DAYS = 14


def make_store(tenant_slug: str = DEFAULT_TENANT) -> KenStore:  # default keeps pre-Chunk-4 callers green; handlers pass principal.tenant_slug
    """Storage factory — selects the backend by env, called at REQUEST TIME.

    `KEN_DATABASE_URL` set -> tenant-bound PostgresStore over that DSN (per-request
    connection); unset -> FileStore over the KEN_DATA_DIR paths (the default;
    CLI/local stays file-based and unbroken; file backend is single-tenant so
    `tenant_slug` is ignored for FileStore). Same request-time seam style as
    `make_llm`.
    """
    dsn = os.getenv("KEN_DATABASE_URL")
    if dsn:
        from ken.stores.postgres_store import PostgresStore

        return PostgresStore(dsn, tenant_slug)
    from ken.stores.file_store import FileStore

    return FileStore(
        manifest=manifest_path(),
        questions=questions_path(),
        ledger=ledger_path(),
    )


def make_llm() -> LLMClient:
    """LLM factory — the test seam. Handlers call this at request time."""
    return AnthropicLLM()


def auth_enabled() -> bool:
    """True only for the exact env value KEN_AUTH=1 (a typo resolves to OFF)."""
    return os.getenv("KEN_AUTH") == "1"


def make_auth_store() -> AuthStore:
    """Postgres-only auth store (request-time seam; tests monkeypatch to a Fake)."""
    return PostgresAuthStore(os.environ["KEN_DATABASE_URL"])
