from khala.claims.answer import format_value_answer
from khala.claims.value_query import ValueAnswer


def test_high_conf_states_value_and_cites_source():
    s = format_value_answer(
        "준회원",
        [ValueAnswer("a", "준회원 최대 N개", "5", "PlaylistPolicy.ASSOCIATE_MAX_PLAYLISTS", "high", True)],
    )
    assert "5" in s and "PlaylistPolicy.ASSOCIATE_MAX_PLAYLISTS" in s and "확실" in s


def test_drift_is_surfaced():
    s = format_value_answer(
        "준회원",
        [ValueAnswer("a", "...", "10", "P.X", "high", True, drifted=True,
                     note="마지막 검증 이후 코드 변경됨(현재값은 정확)")],
    )
    assert "10" in s and "변경" in s


def test_resolved_suppresses_unresolved_for_same_concept():
    answers = [
        ValueAnswer("broken", "준회원 (옛)", None, "PlaylistPolicy.OLD", "low", False,
                    note="소스 심볼을 코드에서 찾지 못함"),
        ValueAnswer("real", "준회원(AM)", "1", "PlaylistCreationPolicy.AM_MAX", "high", True),
    ]
    s = format_value_answer("준회원", answers)
    assert "현재 1" in s
    assert "값 확인 실패" not in s and "찾지 못" not in s  # 깨진 cruft 숨김


def test_unknown_is_not_fabricated():
    s = format_value_answer(
        "x",
        [ValueAnswer("x", "...", None, "Foo.BAR", "low", False, note="소스 심볼을 코드에서 찾지 못함")],
    )
    assert "찾지 못" in s and "확실" not in s
