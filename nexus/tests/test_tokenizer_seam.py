"""토크나이저 seam — 프로덕션은 그대로, 주입은 한 곳에서만 (SPEC-nexus-korean-retrieval-eval §4.4, §6).

이 평가셋이 존재하는 이유가 **자기 무효를 스스로 못 알아채는 계측기**였다. 그러니 seam 자체가
같은 병에 걸리면 안 된다. 여기서 지키는 것:

- 아무것도 주입 안 하면 색인·질의는 **여전히 mecab** 이다.
- 주입은 **한 곳**에서 갈아끼우고 색인·질의가 같은 객체를 본다 — 색인은 mecab, 질의는 nori 로
  돈 실행은 그럴듯한 숫자를 내지만 아무 의미가 없다.
- 세 번째 호출 지점이 생기면 실패한다. import 검사만으로는 **같은 파일 안에 추가된 호출**을
  못 잡으므로 AST 로 센다.
"""

from __future__ import annotations

import ast
from pathlib import Path

from nexus.index import bm25
from nexus.index.bm25 import MecabTokenizer, active_tokenizer, tokenize_korean, use_tokenizer

_NEXUS = Path(bm25.__file__).resolve().parents[1]
_INDEX_SITE = _NEXUS / "index" / "bm25.py"
_QUERY_SITE = _NEXUS / "search" / "hybrid.py"


def _calls(path: Path, name: str, inside: str | None = None) -> int:
    """`name` 호출 횟수. `inside` 를 주면 그 함수 본문 안에서만 센다."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    if inside is not None:
        tree = next(n for n in ast.walk(tree)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == inside)
    return sum(1 for n in ast.walk(tree)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name)


# ── 기본값 ───────────────────────────────────────────────────────────────────


def test_the_default_tokenizer_is_mecab():
    t = active_tokenizer()
    assert isinstance(t, MecabTokenizer)
    assert t.id == "mecab-ko"


def test_the_default_path_produces_exactly_what_tokenize_korean_produces():
    """'주입이 없으면 동작이 한 글자도 안 바뀐다' 는 주장은 단언되어야 주장이다."""
    for text in ["파드를 어떻게 만드나", "StatefulSet 확장", "", "노드 오토 스케일링"]:
        assert active_tokenizer().tokenize(text) == tokenize_korean(text)


def test_the_policy_names_the_filter_actually_applied():
    """한쪽만 품사 필터가 걸린 채 비교하고 그 차이를 '분해 차이' 라 부르는 것을 막는 문자열."""
    policy = active_tokenizer().policy
    for tag in bm25._INCLUDE_POS:
        assert tag in policy


# ── 주입 ─────────────────────────────────────────────────────────────────────


class _Fake:
    id = "fake"
    policy = "fake — 테스트용"

    def tokenize(self, text: str) -> list[str]:
        return ["고정"]


def test_injection_is_scoped_and_restores_the_default():
    with use_tokenizer(_Fake()) as t:
        assert t.id == "fake"
        assert active_tokenizer().tokenize("아무거나") == ["고정"]
    assert isinstance(active_tokenizer(), MecabTokenizer)


def test_injection_restores_even_when_the_body_raises():
    try:
        with use_tokenizer(_Fake()):
            raise RuntimeError("실행 중 실패")
    except RuntimeError:
        pass
    assert isinstance(active_tokenizer(), MecabTokenizer)


def test_both_call_sites_see_the_same_injected_object():
    """색인과 질의가 다른 토크나이저를 보면 그 실행의 숫자는 의미가 없다."""
    from nexus.search import hybrid

    fake = _Fake()
    with use_tokenizer(fake):
        assert bm25.active_tokenizer() is fake
        assert hybrid.active_tokenizer() is fake


# ── 호출 지점은 둘뿐이다 ─────────────────────────────────────────────────────


def test_the_seam_has_exactly_one_call_site_on_each_side():
    """세 번째 호출 지점이 생기면 이후 실행이 절반만 다른 토크나이저로 돌게 된다.

    색인·질의 **함수 본문 안**에서 센다. 모듈 전체를 세면 `use_tokenizer` 가 자기 자신을 확인하는
    호출까지 잡혀서, 정작 막으려는 '색인 함수에 몰래 추가된 두 번째 호출' 과 구분이 안 된다.
    """
    assert _calls(_INDEX_SITE, "active_tokenizer", inside="index_chunk_bm25") == 1
    assert _calls(_QUERY_SITE, "active_tokenizer", inside="_bm25_search") == 1


def test_the_query_path_never_calls_the_mecab_function_directly():
    assert _calls(_QUERY_SITE, "tokenize_korean") == 0


def test_only_the_wrapper_calls_tokenize_korean_inside_the_index_module():
    """bm25.py 안에서 `tokenize_korean` 을 부르는 것은 MecabTokenizer 하나여야 한다."""
    assert _calls(_INDEX_SITE, "tokenize_korean") == 1


def test_no_production_module_imports_the_tokenizer_function_directly():
    """테스트·스크립트는 자유롭게 쓴다. 프로덕션 경로에서 우회하는 것만 막는다."""
    offenders = []
    for f in _NEXUS.rglob("*.py"):
        if f == _INDEX_SITE:
            continue
        if "tokenize_korean" in f.read_text(encoding="utf-8"):
            offenders.append(f.relative_to(_NEXUS).as_posix())
    assert offenders == [], f"seam 을 우회하는 프로덕션 모듈: {offenders}"
