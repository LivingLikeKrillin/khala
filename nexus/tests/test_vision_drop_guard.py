"""판독이 꺼진 재적재가 **이미 읽어 둔 그림 텍스트를 지우는 것**을 막는가.

⛔ **왜 있나 (사고 2026-09-02).** 메타데이터 한 칸을 백필하려고 `ingest-notion --force` 를
돌렸다. `NEXUS_VISION` 은 꺼짐이 기본이라 적재가 그림 자리 표식을 빈 이미지로 지웠다:

    청크 466 → 385 · machine_read 81 → 0

라이브 답변이 값을 답하다가 *"확인할 수 없습니다"* 로 기권했다. 경고도 확인도 없었고
**끝났다는 출력만 초록이었다.** 판독 텍스트 자체는 캐시에 살아 있어서 `NEXUS_VISION=on` 으로
다시 돌려 466/81 로 복구했지만, 그 사실을 아는 사람만 복구할 수 있다.

이 리포는 같은 모양의 규율을 이미 갖고 있다 — 테스트 DB 는 **스스로** 버려도 된다고
선언해야 한다. 지우려면 선언해야 한다.
"""

from __future__ import annotations

from nexus.ingest.vision_guard import OVERRIDE_ENV, refusal, vision_is_on


def test_it_refuses_when_it_would_delete_extracted_text():
    """⛔ 사고 그 자체. 판독 꺼짐 + 지울 것 있음 + 선언 없음."""
    why = refusal(81, {})
    assert why and "81" in why
    assert OVERRIDE_ENV in why, "지우는 길을 안 알려 주면 운영자가 가드를 지운다"


def test_vision_on_passes():
    """대조군 — 켜져 있으면 지워지지 않으므로 막을 이유가 없다."""
    assert refusal(81, {"NEXUS_VISION": "on"}) == ""
    assert refusal(81, {"NEXUS_VISION": " ON "}) == ""


def test_nothing_to_lose_passes():
    """⭐ 그림에서 읽은 청크가 없는 코퍼스는 이 경로로 잃을 것이 없다.

    가드가 여기서도 물면 그림 없는 배포가 전부 막히고, **막힌 가드는 곧 지워진다.**
    """
    assert refusal(0, {}) == ""


def test_an_explicit_declaration_passes():
    """지우는 것이 의도일 수 있다. 다만 **선언해야** 한다."""
    for value in ("1", "true", "on", "yes", "YES"):
        assert refusal(81, {OVERRIDE_ENV: value}) == "", value


def test_a_vague_declaration_does_not_count():
    """`0`·`no`·빈 문자열은 선언이 아니다 — 오타 하나로 코퍼스를 잃으면 안 된다."""
    for value in ("", "0", "no", "off", "아마도"):
        assert refusal(81, {OVERRIDE_ENV: value}), value


def test_the_judgment_matches_the_ingest_path():
    """⛔ **같은 판정을 두 곳에 적으면 언젠가 갈린다.**

    적재는 `(NEXUS_VISION or "off").strip().lower() == "on"` 으로 켜짐을 정한다. 가드가 그와
    다르게 읽으면, 가드는 통과시키는데 적재는 지우는 조합이 생긴다.
    """
    for value, expected in (("on", True), ("ON", True), (" on ", True),
                            ("off", False), ("", False), ("1", False), (None, False)):
        assert vision_is_on({"NEXUS_VISION": value}) is expected, value
    assert vision_is_on({}) is False
