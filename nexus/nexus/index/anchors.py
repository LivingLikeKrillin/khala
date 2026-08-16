"""문서 → 코드 앵커: 후보 추출과 **바인딩 거부** (SPEC-nexus-doc-code-anchors §3.2, §3.3).

여기에도 LLM 은 없다. 정밀도를 지는 것은 판단이 아니라 **유일 해소 규칙**이다:
후보가 정확히 하나의 심볼로 풀릴 때만 엣지가 된다.

엣지가 없다는 것은 *"믿을 만한 연결을 아직 확인하지 못했다"* 이지 *"무관하다"* 가 아니다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable

#: 백틱 안의 토큰. 점이 있으면(`Foo.bar`) 받지 않는다 — 마지막 조각만 떼는 것은 추측이고,
#: 추측한 앵커는 코퍼스에 영구히 남는다.
_BACKTICKED = re.compile(r"`([^`\n]{1,120})`")
#: **이름 자체만** 감싼 취소선 — `~~`OldName`~~`. 이때의 취소선은 철회다: 문서가 그 이름을
#: 더는 주장하지 않는다는 표시이므로 후보에서 뺀다. 그러지 않으면 문서를 고친 사람에게 같은
#: 항목이 다시 뜨고, 목록이 신뢰를 잃는다.
#:
#: **문장을 감싼 취소선은 건드리지 않는다.** 실측에서 취소선의 뜻은 하나가 아니었다: 대상
#: 저장소의 취소선 112개 중 이름 철회는 2개뿐이고 나머지는 위험표·체크리스트의 "해소됨"
#: 표시였다. 그리고 해소된 우려 문장은 **살아 있는 이름**을 부른다 —
#: `~~`A`/`B`에 `partyroomId` 미노출~~ → 해소됨` 이 그 예다. 문장째 지웠더니 실재하는
#: 메서드로 유일 해소되던 진짜 앵커 하나가 사라졌다. 취소선이 곧 철회라는 전제가 틀렸다.
_STRUCK_NAME = re.compile(r"~~\s*`([^`\n]{1,120})`\s*~~")
_IDENT = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")

#: 예약어는 선언 이름이 될 수 없으므로 후보가 아니다. 걸러내면 거부 분모가 정직해진다.
_RESERVED = frozenset("""
abstract assert boolean break byte case catch char class const continue default do double else
enum extends final finally float for goto if implements import instanceof int interface long
native new package private protected public return short static strictfp super switch
synchronized this throw throws transient try void volatile while var record sealed permits yield
true false null
""".split())

#: 한 글자 토큰은 산문에서 변수처럼 쓰이지 실제 참조가 아니다.
_MIN_LEN = 2


def extract_candidates(text: str) -> list[str]:
    """청크 본문에서 백틱 식별자 후보를 뽑는다. 중복은 한 번만.

    파일 경로·HTTP 엔드포인트·설정 키는 **뽑지 않는다** (SPEC §2). Java 심볼 인덱스에 대해
    파일 경로는 항상 ambiguous, 나머지는 항상 zero 라 구조적으로 바인딩 불가이고, 거부 분모만
    오염시켜 수율 수치를 해석 불가로 만든다.

    **이름만 감싼 취소선은 뽑지 않는다.** `~~`OldName`~~` 는 문서가 그 이름을 더는 주장하지
    않는다는 표시다. 고친 사람에게 같은 항목을 다시 올리면 목록 전체가 신뢰를 잃는다.
    반면 **문장을 감싼 취소선의 이름은 그대로 뽑는다** — 그 취소선은 "이 우려는 해소됐다" 는
    뜻이고, 해소된 문장이 부르는 이름은 대개 실재한다.
    """
    seen: dict[str, None] = {}
    for raw in _BACKTICKED.findall(_STRUCK_NAME.sub(" ", text)):
        token = raw.strip()
        if len(token) < _MIN_LEN:
            continue
        if not _IDENT.match(token):
            continue
        if token in _RESERVED:
            continue
        seen.setdefault(token, None)
    return list(seen)


@dataclass(frozen=True)
class Anchor:
    candidate: str
    symbol_name: str
    file_path: str
    span_hash: str


@dataclass(frozen=True)
class Refusal:
    candidate: str
    reason: str        # 'unresolved' | 'ambiguous'
    match_count: int


@dataclass(frozen=True)
class BindResult:
    anchors: list[Anchor]
    refusals: list[Refusal]


#: (name) -> 그 이름의 심볼들. 각 항목은 (symbol_name, file_path, span_hash).
Resolver = Callable[[str], Iterable[tuple[str, str, str]]]


def bind(candidates: Iterable[str], resolve: Resolver) -> BindResult:
    """유일 해소만 엣지로. 0건과 다건은 **행으로 남는 거부**다.

    거부를 버리면 재바인딩이 불가능해지고(§3.6), 스캔보다 먼저 적재된 문서는 영구히 미앵커로
    남아 수율 수치가 코퍼스가 아니라 실행 순서를 재게 된다.
    """
    anchors: list[Anchor] = []
    refusals: list[Refusal] = []

    for cand in candidates:
        matches = list(resolve(cand))
        if len(matches) == 1:
            name, path, digest = matches[0]
            anchors.append(Anchor(cand, name, path, digest))
        elif not matches:
            refusals.append(Refusal(cand, "unresolved", 0))
        else:
            refusals.append(Refusal(cand, "ambiguous", len(matches)))

    return BindResult(anchors=anchors, refusals=refusals)


# ----------------------------------------------------------------- 재검사

FRESH = "fresh"
CHANGED = "changed"
ORPHANED = "orphaned"
AMBIGUOUS_NOW = "ambiguous_now"


def recheck(bound_span_hash: str, matches: list[tuple[str, str, str]]) -> str:
    """저장된 앵커가 지금 어떤 상태인가 (SPEC §3.4).

    해시가 같은지 확인하는 데 LLM 을 부를 필요는 없다. 비결정성을 **실제로 바뀐 행**에만
    가두는 것이 비용 통제이자 품질 통제다.

    같은 텍스트로 파일만 옮긴 심볼은 `fresh` 다 — 키는 이름이고, 문서가 주장한 것은 텍스트다.
    """
    if not matches:
        return ORPHANED
    if len(matches) > 1:
        return AMBIGUOUS_NOW
    return FRESH if matches[0][2] == bound_span_hash else CHANGED
