"""Central wiring for the adept-web API: storage paths + the LLM factory seam.

Storage paths come from the environment so a deployment (or a test) can point the
API at an isolated data directory. `make_llm()` is the **test seam**: handlers call
it at request time, so tests can `monkeypatch.setattr(deps, "make_llm", ...)` to
inject a `FakeLLM` without a live API key.
"""

from __future__ import annotations

import os
from pathlib import Path

from khala.adept.llm import AnthropicLLM, LLMClient
from khala.adept.store import AdeptStore
from khala.adept_web.auth_store import AuthStore, PostgresAuthStore

# Default count of questions to generate per artifact (overridable via env).
N_QUESTIONS = int(os.getenv("ADEPT_N_QUESTIONS", "5"))


def _data_dir() -> Path:
    """The base directory for adept's file stores (env: ADEPT_DATA_DIR, default ./).

    Read lazily so tests that set ADEPT_DATA_DIR after import are honoured.
    """
    return Path(os.getenv("ADEPT_DATA_DIR", "."))


def manifest_path() -> str:
    return os.getenv("ADEPT_MANIFEST", str(_data_dir() / "adept.manifest.yaml"))


def questions_path() -> str:
    return os.getenv("ADEPT_QUESTIONS", str(_data_dir() / "adept.questions.json"))


def ledger_path() -> str:
    return os.getenv("ADEPT_LEDGER", str(_data_dir() / "adept.attempts.jsonl"))


SESSION_COOKIE = "adept_session"
DEFAULT_PERSON = "local"           # the identity when auth is OFF
DEFAULT_TENANT = "default"         # the tenant when auth is OFF or unspecified
SESSION_TTL_DAYS = 14


# The default keeps pre-Chunk-4 callers green; handlers pass principal.tenant_slug.
def make_store(tenant_slug: str = DEFAULT_TENANT) -> AdeptStore:
    """Storage factory — selects the backend by env, called at REQUEST TIME.

    `ADEPT_DATABASE_URL` set -> tenant-bound PostgresStore over that DSN (per-request
    connection); unset -> FileStore over the ADEPT_DATA_DIR paths (the default;
    CLI/local stays file-based and unbroken; file backend is single-tenant so
    `tenant_slug` is ignored for FileStore). Same request-time seam style as
    `make_llm`.
    """
    dsn = os.getenv("ADEPT_DATABASE_URL")
    if dsn:
        from khala.adept.stores.postgres_store import PostgresStore

        return PostgresStore(dsn, tenant_slug)
    from khala.adept.stores.file_store import FileStore

    return FileStore(
        manifest=manifest_path(),
        questions=questions_path(),
        ledger=ledger_path(),
    )


def make_llm() -> LLMClient:
    """LLM factory — the test seam. Handlers call this at request time."""
    return AnthropicLLM()


def auth_enabled() -> bool:
    """True only for the exact env value ADEPT_AUTH=1 (a typo resolves to OFF)."""
    return os.getenv("ADEPT_AUTH") == "1"


def make_auth_store() -> AuthStore:
    """Postgres-only auth store (request-time seam; tests monkeypatch to a Fake)."""
    return PostgresAuthStore(os.environ["ADEPT_DATABASE_URL"])
