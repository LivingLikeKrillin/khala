"""답변을 내는 표면은 **전부** `packet_for_answer` 를 지나는가.

⛔ **왜 생겼나 (외부 평가 F2, 2026-09-02).** `reconcile.py` 의 `packet_for_answer` docstring 이
이렇게 적어 두었다 — *"답변용 근거 패킷은 이 함수 하나로만 만든다. 답변 경로가 셋이다 …
각자 `assemble_packet` 을 부르면 보강을 한 곳에만 붙이는 배선이 가능해지고 **그 조합은 검사가
초록인 채로 프로덕션에서 조용히 틀린다**."* `nexus/CLAUDE.md` 이음매 지도도 같은 말을 한다.

**그 문장을 지키는 검사가 없었다.** `/search/answer/stream` 이 `assemble_packet` 을 직접
불렀고, 그래서 정정 확인 패스·짝 확장·코드 값이 그 경로에서만 빠졌다. 웹 채팅이 타는 경로가
바로 그것이다(`web/js/api.js`). 외부 평가 실측: 정책 8질의 중 4건에서 근거가 적게 갔고
가장 큰 것이 19 → 13(−32%).

⚠ **이 검사는 "호출이 존재하는가" 까지만 본다.** 그 호출이 실제로 돌아 보강이 붙는지는
`test_read_scope_reaches_every_enrichment.py` 가 진짜 DB 로 확인한다. 둘이 짝이다 — 이쪽만
있으면 이 리포가 이미 데인 "소스 문자열 검사" 가 된다.
"""

from __future__ import annotations

import pytest


def _names(func) -> set[str]:
    """이 함수와 **그 안에 중첩된 함수들**이 부르는 이름 전부.

    ⛔ 중첩까지 걸어야 한다. 스트리밍 핸들러의 패킷 조립은 `event_stream()` 안에 있어서,
    바깥 함수의 `co_names` 만 보면 **결함이 있는 판에서도 초록**이다.
    """
    seen, out = set(), set()

    def walk(code) -> None:
        if id(code) in seen:
            return
        seen.add(id(code))
        out.update(code.co_names)
        for const in code.co_consts:
            if hasattr(const, "co_names"):
                walk(const)

    walk(func.__code__)
    return out


def _surfaces():
    from nexus import api, cli
    from nexus.a2a import server

    return {
        "HTTP /search/answer": api.search_answer,
        "HTTP /search/answer/stream": api.search_answer_stream,
        "A2A": server._default_answer_fn,
        "CLI": cli.query,
    }


@pytest.mark.parametrize("label", list(_surfaces()))
def test_every_answer_surface_goes_through_the_shared_seam(label):
    """⛔ 표면 하나가 빠지면 그 표면의 사용자만 보강 없는 답을 받는다 — 화면에 안 보인다."""
    names = _names(_surfaces()[label])
    assert "packet_for_answer" in names, (
        f"{label} 이 `packet_for_answer` 를 안 지난다 — 정정·짝·코드 값이 이 표면에서만 빠진다")


@pytest.mark.parametrize("label", list(_surfaces()))
def test_no_answer_surface_assembles_the_packet_itself(label):
    """대조군 — 지나가면서 **직접 조립도** 하면 두 패킷이 생기고 어느 쪽이 답에 갔는지 모른다."""
    assert "assemble_packet" not in _names(_surfaces()[label]), (
        f"{label} 이 `assemble_packet` 을 직접 부른다 — 이음매를 지나는 의미가 없어진다")


def test_the_check_can_actually_fail():
    """⛔ **일부러 깨뜨려 본다.** 이 리포는 '찾아내고 종료코드 0' 인 검사기를 만든 적이 있다."""
    def bypasses():
        from nexus.search.evidence_packet import assemble_packet
        return assemble_packet

    assert "packet_for_answer" not in _names(bypasses)
    assert "assemble_packet" in _names(bypasses)


def test_it_sees_calls_made_inside_a_nested_function():
    """중첩을 안 걸으면 스트리밍 핸들러가 결함이 있는 판에서도 통과한다."""
    def outer():
        async def inner():
            return packet_for_answer  # noqa: F821 — 이름 존재만 본다
        return inner

    assert "packet_for_answer" in _names(outer)
