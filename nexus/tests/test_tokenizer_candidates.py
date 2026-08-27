"""토크나이저 후보들 — **기본값은 안 바뀐다**, 그리고 후보는 형태소를 잃지 않는다.

두 실험이 여기 남아 있다(`tests/eval/tokenizer-surface/`, `tests/eval/tokenizer-protected-terms/`).
둘 다 **기각**됐고, 코드는 다음 사람이 같은 것을 다시 발명하지 않도록 남긴다. 그러니 이 파일이
지키는 것은 두 가지다: 기본값이 조용히 바뀌지 않을 것, 그리고 후보가 **원래 토큰을 잃지 않을 것**.

⚠ 두 번째가 왜 필요한가. 첫 판은 낱말 사이 기호에서 정렬이 어긋나 그 낱말의 형태소를 통째로
버렸다 — `[파티룸] 디제잉 정책` 이 `['파티룸','디제잉']` 이 됐고(형태소 5개 소실), 그 상태로
측정한 숫자를 "표면형을 더한 결과" 라고 읽을 뻔했다.
"""

from __future__ import annotations

import pytest

from nexus.index.bm25 import (
    _get_mecab,
    MecabTokenizer,
    ProtectedTermTokenizer,
    SurfaceFormTokenizer,
    active_tokenizer,
    compound_names,
    use_tokenizer,
)

#: mecab 이 없으면 토크나이저는 공백 분해로 떨어지고, 형태소에 대한 단언은 **아무것도 측정하지
#: 않는다**(CI 의 unit 잡에 mecab 이 없어 첫 판이 빈 목록을 받고 빨간불이 났다).
#: 그렇다고 파일 전체를 건너뛰지는 않는다 — 기본값·이음매 검사는 mecab 과 무관하고, 그 둘이
#: CI 에서 안 도는 것이 더 나쁘다.
needs_mecab = pytest.mark.skipif(
    _get_mecab() is None,
    reason="mecab-ko 없음 — 형태소 동작은 프로덕션 토크나이저에서만 측정한다")


def test_the_default_is_still_mecab():
    """실험이 남아 있어도 배포되는 것은 mecab 이다. 기본값이 조용히 바뀌면 이 검사가 죽는다."""
    assert active_tokenizer().id == "mecab-ko"
    assert isinstance(active_tokenizer(), MecabTokenizer)


@needs_mecab
def test_candidates_never_lose_a_morpheme():
    """후보는 **더하기만** 한다 — 현직이 낸 토큰은 전부 들어 있어야 한다.

    기호가 낱말 앞뒤에 붙은 경우가 이 검사의 요점이다(`[파티룸]`, `**디제잉 포인트**`).
    """
    base = MecabTokenizer()
    cands = [SurfaceFormTokenizer(), ProtectedTermTokenizer({"파티룸", "디제잉", "플레이리스트"})]
    texts = [
        "[파티룸] 디제잉 정책",
        "[디제잉 아바타  10] - **디제잉 포인트**: 4000",
        "플레이리스트 정책 — 1 playlist = 100곡",
        "값은 같은 것이고 거부한다",
    ]
    for text in texts:
        want = base.tokenize(text)
        for cand in cands:
            got = cand.tokenize(text)
            for tok in want:
                assert tok in got, f"{cand.id}: {text!r} 에서 {tok!r} 가 사라졌다 → {got}"


@needs_mecab
def test_protected_tokenizer_adds_only_listed_terms():
    """지정 보호는 **목록에 있는 것만** 더한다. 그것이 무차별 판과 갈리는 지점이다."""
    base = MecabTokenizer()
    only_party = ProtectedTermTokenizer({"파티룸"})
    text = "[파티룸] 디제잉 정책"
    added = [t for t in only_party.tokenize(text) if t not in base.tokenize(text)]
    assert added == ["파티룸"], added


@needs_mecab
def test_compound_names_finds_names_not_inflections():
    """유도기는 **이름**을 뽑고 활용형은 안 뽑는다.

    앞선 두 판이 여기서 무너졌다: Notion 식별자 조각과 `값은`·`거부한다` 같은 활용형이 섞여
    351개·314개짜리 목록이 나왔고, 그 목록으로는 "지정 보호" 가 무차별과 구별되지 않았다.
    """
    assert compound_names("[파티룸] 디제잉 정책") == ["파티룸", "디제잉"]
    assert compound_names("파티룸 연결 웹소켓 연결 실패") == ["파티룸", "웹소켓"]
    # 조사·어미가 떨어지는 것은 형태소 분석이 **옳게** 동작한 것이다 — 이름이 아니다.
    assert compound_names("값은 같은 것이고 거부한다") == []
    # 라틴·숫자가 섞인 것도 이름 목록이 아니다(식별자 조각이 들어오던 자리).
    assert compound_names("2c7836e4e06f 3gb 100곡") == []


def test_use_tokenizer_restores_the_default():
    """평가용 이음매가 새면 이후 모든 색인이 다른 토크나이저로 돈다."""
    with use_tokenizer(SurfaceFormTokenizer()):
        assert active_tokenizer().id == "mecab-ko+surface"
    assert active_tokenizer().id == "mecab-ko"
