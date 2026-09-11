"""판독 비교의 토큰화는 **한 곳에만 산다**.

⛔ **왜 있나 (실측 2026-09-11).** `scripts/vision_crosscheck.py` 가 `normalize`·`tokens` 의
사본을 들고 있었고, 그 사본의 식별자 패턴은 `[A-Za-z0-9]` 로 시작해야 해서
`툴팁_사용가이드_02` 를 `02` 로 잘랐다.

같은 결함을 2026-08-11 에 `ingest/vision_health.py` 에서 고쳤는데(커밋 7c2d75a) **그 커밋이
건드린 것은 그 모듈과 그 검사 둘뿐**이라 이 사본은 그대로 남았다. 그래서 같은 판독 데이터에서
자기 변동(재현율)은 정정된 값이 나오고 **판독기 사이 차이는 옛 값이 나왔다.** 승인 문서의
철회 기록이 두 백분율만 되돌린 이유가 그것이다 — 셋째 수의 계측기는 고쳐진 적이 없었다.

⭐ **한 번 고쳐서 끝나는 문제가 아니다.** 사본이 다시 생기면 다음 고침도 한쪽에만 닿는다.
그래서 여기서 지키는 것은 값이 아니라 **집이 하나라는 사실**이다.

⚠ 소스를 읽어서 판정한다. `vision_crosscheck` 를 import 하면 `httpx` 와 판독기 모듈이 따라
올라오고, 그건 이 검사가 물어보는 것과 상관이 없다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOME = "nexus/ingest/vision_health.py"

#: 판독 텍스트를 비교하는 쪽. 여기 사본이 있으면 고침이 갈린다.
CONSUMERS = (
    "scripts/vision_crosscheck.py",
)

_OWN_DEF = re.compile(r"^def (normalize|tokens)\(", re.M)
#: ASCII 로만 시작하는 식별자 패턴 — 그것이 혼종 식별자를 자르던 그 모양이다.
_ASCII_ONLY_IDENT = re.compile(r"re\.compile\(\s*r?[\"']\[A-Za-z0-9\]\[")


def _src(rel: str) -> str:
    p = ROOT / rel
    assert p.is_file(), f"{rel} 이 없다 — 파일이 옮겨졌으면 이 검사의 목록을 고쳐라"
    return p.read_text(encoding="utf-8")


def test_the_home_defines_it():
    """대조군. 정본이 사라졌는데 소비자만 보면 이 검사는 조용히 통과한다."""
    src = _src(HOME)
    assert "def tokens(" in src and "def normalize(" in src
    assert "가-힣" in src, "정본의 식별자 패턴이 한글을 안 받는다 — 그 결함이 되돌아왔다"


@pytest.mark.parametrize("rel", CONSUMERS)
def test_a_consumer_does_not_keep_its_own_copy(rel: str):
    src = _src(rel)
    own = _OWN_DEF.findall(src)
    assert not own, f"{rel} 이 {own} 을 스스로 정의한다 — 정본에서 import 하라"


@pytest.mark.parametrize("rel", CONSUMERS)
def test_a_consumer_imports_from_the_home(rel: str):
    assert "from nexus.ingest.vision_health import" in _src(rel), \
        f"{rel} 이 정본을 안 쓴다"


@pytest.mark.parametrize("rel", CONSUMERS)
def test_the_ascii_only_identifier_pattern_is_gone(rel: str):
    """`[A-Za-z0-9][...]` 로 시작하는 패턴이 그 결함의 모양이다."""
    assert not _ASCII_ONLY_IDENT.search(_src(rel)), \
        f"{rel} 에 ASCII 로만 시작하는 식별자 패턴이 있다 — 혼종 식별자가 잘린다"


def test_the_canonical_tokeniser_keeps_a_mixed_script_identifier_whole():
    """값 쪽 고정. 이 하나가 무너지면 위의 세 검사는 전부 무의미하다."""
    from nexus.ingest.vision_health import tokens
    idents, hangul = tokens("툴팁_사용가이드_02 와 안내문구")
    assert "툴팁_사용가이드_02" in idents
    assert "02" not in idents
    assert "안내문구" in hangul
