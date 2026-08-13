"""로컬 LLM 답변 온램프: 키 미설정을 감지해 행동지침 안내로 표면화.

목적: nexus/.env 에 ANTHROPIC_API_KEY 가 없을 때 채팅 답변이 *일시적 API 오류와
구분 불가한* '답변을 생성할 수 없습니다'로 떨어지지 않고, 키를 넣으라는 안내를 준다.
근거+신뢰배지는 그대로 제공(System decides, LLM narrates 원칙 유지).

[[user-workflow-autonomous-prs]] · [[usability-first-overriding-priority]] 정렬:
무키는 '버그'가 아니라 '미설정' — 사용자가 한 스텝으로 해소하도록 self-explanatory 하게.
"""

from __future__ import annotations

import pytest

from nexus.providers.llm import LLMService


@pytest.fixture(autouse=True)
def _anthropic_backend(monkeypatch):
    """이 파일은 **anthropic 백엔드**의 온램프를 잰다 — provider 를 고정한다.

    2026-08-13 에 배포 `.env` 에 `NEXUS_LLM_PROVIDER=claude-code`(무료 브리지)를 넣자 두 검사가
    빨개졌다. 코드가 깨진 게 아니라 **가정이 새 것**이었다: 브리지는 키가 없어도 `configured`
    이고, 그게 맞는 동작이다. 검사는 자기가 재는 백엔드를 스스로 세워야 한다 — 안 그러면
    배포 설정 하나가 스위트를 빨갛게 만들고, 그 빨강이 진짜 신호를 묻는다.
    """
    monkeypatch.delenv("NEXUS_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("NEXUS_LLM_BRIDGE_URL", raising=False)


def test_configured_false_when_no_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert LLMService(api_key=None).configured is False


def test_configured_true_when_key_passed(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert LLMService(api_key="sk-ant-xxx").configured is True


def test_configured_true_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env")
    assert LLMService().configured is True


def test_configured_false_when_env_empty(monkeypatch):
    # docker-compose 는 미설정 시 ANTHROPIC_API_KEY="" (빈 문자열)로 주입한다.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    assert LLMService(api_key=None).configured is False


def test_not_configured_notice_is_actionable():
    """무키 안내는 *행동지침*이어야 한다 — 무엇을, 어디에 넣을지 명시."""
    from nexus.api import LLM_NOT_CONFIGURED_NOTICE

    assert "ANTHROPIC_API_KEY" in LLM_NOT_CONFIGURED_NOTICE
    assert ".env" in LLM_NOT_CONFIGURED_NOTICE
    # 일시적 오류 메시지와 구분되어야 한다(동일 문구 금지).
    assert LLM_NOT_CONFIGURED_NOTICE != "답변을 생성할 수 없습니다. 위 근거를 직접 확인해주세요."
