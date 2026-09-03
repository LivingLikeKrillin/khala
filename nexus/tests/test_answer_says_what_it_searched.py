"""답이 **자기가 무엇을 뒤졌는지** 말하는가.

⛔ **왜 생겼나 (실측 2026-09-03).** 설계 문서 122건이 `design_docs` 테넌트에 있는데, 웹·CLI 가
쓰는 principal(`local-dev`)의 읽기 범위는 `default` 하나였다. 그래서 설계 질문을 던지면
**정책 코퍼스만 본 답**이 확신 있게 나왔고, 사용자는 그것이 설계 문서를 본 답인 줄 읽었다.
근거 인용은 *어느 문서를 썼나*를 보여 주지만 *어느 코퍼스가 애초에 후보였나*는 어디에도 없었다.

그 사실을 알아내는 데 코드를 읽어야 했다 — 로그의 `read_scope` 는 1,083행이 비어 있었고 응답에는
아예 없었다. **답이 스스로 말하지 않으면, 답이 무엇 위에 섰는지는 매번 조사거리가 된다.**

⚠ **`out_of_scope` 는 여기 안 싣는다.** 범위 밖 테넌트를 물었다는 사실을 호출자에게 알리면
**그 테넌트의 존재가 새어 나간다**(`api.py` 1R I-009). 그건 운영자 로그로만 간다. 여기서 다루는
것은 호출자 자신의 범위와, 실제로 기여한 코퍼스뿐이다 — 둘 다 호출자가 이미 볼 수 있는 것이다.
"""

from __future__ import annotations

from nexus.search.evidence_packet import EvidencePacket


def test_a_packet_carries_the_scope_it_was_built_for():
    """공유 이음매가 범위를 받는다 — 표면마다 붙이면 하나가 조용히 빠진다(외부 평가 F2)."""
    p = EvidencePacket(searched_tenants=["default", "design_docs"])
    assert p.searched_tenants == ["default", "design_docs"]


def test_a_packet_without_a_scope_says_nothing_rather_than_guessing():
    """모르면 비운다. 기본값으로 `default` 를 넣으면 **틀린 사실**을 답에 싣게 된다."""
    assert EvidencePacket().searched_tenants == []


def test_the_contributing_corpora_are_counted_from_the_packet_not_the_hits():
    """근거 점유율은 패킷에서 센다 — 히트만 세면 채운 절·짝 문서·정정 패스가 빠진다.

    (SPEC-nexus-design-corpus-cutover §5.3 이 같은 이유로 같은 자리를 고른다.)
    """
    from nexus.search.evidence_share import counts

    class _S:
        def __init__(self, t):
            self.tenant = t

    got = dict(counts([_S("default"), _S("design_docs"), _S("default")]))
    assert got == {"default": 2, "design_docs": 1}


def test_every_answer_surface_reports_the_scope():
    """표면 하나만 고치면 F2 가 그대로 재현된다 — **셋 다** 범위를 응답에 실어야 한다.

    소스 문자열이 아니라 **컴파일된 참조**를 본다. 서식이 바뀌어도 안 깨지고, 이름을 지운
    판에서는 깨진다.
    """
    from nexus import api

    surfaces = {
        "search_answer": api.search_answer,
        "search_answer_stream": api.search_answer_stream,
    }
    missing = [name for name, fn in surfaces.items()
               if "searched_tenants" not in _names(fn)]
    assert not missing, f"범위를 응답에 안 싣는 표면: {missing}"


def _names(func) -> set[str]:
    """이 함수와 **중첩 함수들**이 쓰는 이름 전부.

    스트리밍 핸들러는 응답 조립이 `event_stream()` 안에 있어서, 바깥 함수의 `co_names` 만
    보면 결함이 있는 판에서도 초록이다 — `test_answer_surfaces_share_the_seam` 이 같은 자리에서
    같은 이유로 중첩을 걷는다.
    """
    seen: set = set()
    out: set[str] = set()
    stack = [func.__code__]
    while stack:
        code = stack.pop()
        if id(code) in seen:
            continue
        seen.add(id(code))
        out |= set(code.co_names) | set(code.co_consts and () or ())
        for c in code.co_consts:
            if hasattr(c, "co_names"):
                stack.append(c)
    return out


# ── 이름이 아니라 **행동**을 건다 ────────────────────────────────────────────
#
# ⛔ 위의 표면 검사는 이름만 본다. 처음 판에서 이음매의 대입을 통째로 지워도 **한 검사도 안
# 깨졌다** — 표면은 여전히 `packet.searched_tenants` 를 읽고 있었고 그 값이 비었을 뿐이다.
# 이 리포가 이미 적어 둔 실패다: *"문자열은 그 코드가 돌았다는 것을 증명하지 않는다."*

async def test_the_seam_actually_fills_the_scope(monkeypatch):
    """공유 이음매가 범위를 **채우는지** 본다. 지우면 이 검사가 깨진다."""
    from nexus.search import reconcile

    class _R:
        hits: list = []
        graph = None
        fill: list = []

    packet = await reconcile.packet_for_answer(
        _R(), ["default", "design_docs"], "INTERNAL",
        config={"search": {}}, search=None, question=None, pool=None)
    assert packet.searched_tenants == ["default", "design_docs"]


async def test_a_single_tenant_string_still_becomes_a_list():
    """호출부 넷 중 옛 서명을 쓰는 곳이 남아 있다 — 문자열이 와도 목록으로 나가야 한다."""
    from nexus.search import reconcile

    class _R:
        hits: list = []
        graph = None
        fill: list = []

    packet = await reconcile.packet_for_answer(
        _R(), "default", "INTERNAL", config={"search": {}},
        search=None, question=None, pool=None)
    assert packet.searched_tenants == ["default"]
