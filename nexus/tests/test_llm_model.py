"""LLM 모델 선택: EOL 모델 하드코딩 제거 — 현행 기본값 + env 오버라이드.

라이브 실증: 하드코딩된 claude-sonnet-4-20250514 가 2026-06-15 EOL 후 404 not_found 로
답변 생성을 막았다(키가 있어도). 현행 모델 기본값 + NEXUS_LLM_MODEL 오버라이드로,
다음 EOL 은 코드가 아니라 .env 한 줄로 넘긴다([[lower-entry-barrier-survival-law]] 온램프).
"""

from __future__ import annotations

from nexus.providers.llm import LLMService


def test_default_model_is_current_not_eol(monkeypatch):
    monkeypatch.delenv("NEXUS_LLM_MODEL", raising=False)
    svc = LLMService()
    # EOL(2026-06-15) 스냅샷이면 안 된다.
    assert svc.model != "claude-sonnet-4-20250514"
    assert svc.model == "claude-sonnet-4-6"


def test_model_env_override(monkeypatch):
    monkeypatch.setenv("NEXUS_LLM_MODEL", "claude-opus-4-8")
    assert LLMService().model == "claude-opus-4-8"


def test_explicit_model_arg_wins_over_env(monkeypatch):
    monkeypatch.setenv("NEXUS_LLM_MODEL", "claude-opus-4-8")
    assert LLMService(model="claude-haiku-4-5").model == "claude-haiku-4-5"
