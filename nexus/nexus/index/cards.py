"""코드 시맨틱 카드 — 코드에 대한 서술을 만들고, **모델이 낸 것을 규칙으로 다시 검사한다.**

SPEC-nexus-code-semantic-cards §3.1~§3.4.

문서는 `RetryPolicy` 라고 쓰지 않고 "결제 실패 시 3회 재시도" 라고 쓴다. 어휘가 겹치지 않으므로
어휘 앵커가 닿지 않는다. 그래서 코드 쪽에서 업무 언어로 된 서술을 **생성**해 다리를 놓는다.

이 파일의 대부분은 LLM 이 없다. 생성 호출은 얇고, 나머지는 전부 결정론적 검사다:

  - 후보 선택 (§3.1)      — 어떤 심볼에 카드를 만들 값어치가 있는가
  - 파싱 (§3.2)          — 모델 출력을 카드로
  - 규칙 재검사 (§3.2)    — **소스가 산문으로 새지 않았는가**를 포함
  - 낡음 판정 (§3.4)      — span_hash 비교. 조회이지 판단이 아니다

⚠ **카드는 권위가 아니다.** 어떤 시점 커밋에서 모델이 쓴 것이고 코드는 그 뒤로 움직였다.
   설명에 기대는 쪽은 반드시 span 을 다시 읽는다. 여기서는 그것이 가능하도록 span_hash 를 싣고,
   움직인 카드를 `stale` 로 드러내는 데까지 한다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------- 카드

#: `code_terms` 상한. 식별자 목록이지 코드 조각이 아니라는 것을 개수로도 못박는다.
MAX_CODE_TERMS = 12
#: 산문에서 소스 줄과 대조할 때 무시할 짧은 줄. `}` `);` 같은 것까지 검사하면 전부 걸린다.
_MIN_SOURCE_LINE = 12
_IDENT = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")
#: 소스의 문자열 리터럴. 산문에 그대로 나타나면 소스를 옮긴 것이다.
_STRING_LITERAL = re.compile(r"""["']([^"'\n]{3,})["']""")


@dataclass(frozen=True)
class CardSpan:
    repo: str
    file_path: str
    start_line: int
    end_line: int
    symbol: str
    span_hash: str


@dataclass(frozen=True)
class Card:
    """코드에 대한 서술. **소스 본문 필드는 없다** — 있으면 그게 유출 경로다."""

    subject: str
    behavior: str
    domain_terms: tuple[str, ...]
    code_terms: tuple[str, ...]
    spans: tuple[CardSpan, ...]
    commit_sha: str
    generator: str          # model · prompt_version · traversal — 선언과 다르면 읽지 않는다
    notes: tuple[str, ...] = field(default=())


# ---------------------------------------------------------------- §3.1 후보

#: 본문 줄 수 문턱 기본값. 실행마다 기록한다 — 비용과 커버리지를 동시에 움직인다.
DEFAULT_BODY_LINES = 8

_ALWAYS_CARD = {"class", "interface", "record", "enum"}


def is_card_candidate(symbol_kind: str, start_line: int, end_line: int,
                      *, anchored: bool = False,
                      body_lines: int = DEFAULT_BODY_LINES) -> bool:
    """이 심볼에 카드를 만들 값어치가 있는가 (§3.1).

    게터·생성자·한 줄 위임자는 모델 호출을 쓰고 아무것도 서술하지 않으며, 거의 같은 텍스트로
    카드 모집단을 희석한다.

    `anchored` — 어휘 앵커가 이미 걸린 심볼은 길이와 무관하게 후보다. 문서가 이미 그 이름을
    불렀으므로 서술할 값어치가 증명돼 있다.
    """
    if anchored:
        return True
    if symbol_kind in _ALWAYS_CARD:
        return True
    return (end_line - start_line + 1) >= body_lines


# ---------------------------------------------------------------- §3.2 파싱

class CardParseError(ValueError):
    """모델 출력이 카드가 아니다. 예외로 올린다 — 반쯤 읽은 카드를 저장하는 것보다 낫다."""


def parse_card(raw: str, *, spans: list[CardSpan], commit_sha: str,
               generator: str) -> Card:
    """모델 출력(JSON)을 카드로. span·commit·generator 는 **모델이 아니라 호출자가** 채운다.

    모델에게 파일 경로나 줄 번호를 말하게 하면 그 값이 틀릴 수 있고, 틀린 포인터는 재검증을
    통과하지 못해 카드가 통째로 버려진다. 아는 쪽이 채우는 게 맞다.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n|\n```$", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise CardParseError(f"JSON 아님: {e}") from None
    if not isinstance(data, dict):
        raise CardParseError("객체가 아님")

    def _strs(key: str) -> tuple[str, ...]:
        v = data.get(key) or []
        if not isinstance(v, list):
            raise CardParseError(f"{key} 가 배열이 아님")
        return tuple(str(x).strip() for x in v if str(x).strip())

    subject = str(data.get("subject", "")).strip()
    behavior = str(data.get("behavior", "")).strip()
    if not subject or not behavior:
        raise CardParseError("subject/behavior 가 비었음")

    return Card(subject=subject, behavior=behavior,
                domain_terms=_strs("domain_terms"), code_terms=_strs("code_terms"),
                spans=tuple(spans), commit_sha=commit_sha, generator=generator)


# ------------------------------------------------- §3.2 규칙 재검사 (소스 경계 포함)

def _normalise(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def check_card(card: Card, span_sources: dict[str, str],
               *, known_spans: set[tuple[str, int, int]] | None = None) -> list[str]:
    """모델 출력을 그대로 저장하지 않기 위한 검사. 위반 사유 목록을 돌려준다(빈 목록=통과).

    `span_sources` — span 키(`file:start-end`) → 그 구간의 소스. 검사용으로만 쓰이고
    **저장되지 않는다.**

    소스 경계(§3.2)가 이 함수의 존재 이유다. 앞 단위는 이름·경로·줄·해시만 저장했으므로
    "소스 미저장" 이 자명했지만, 카드는 **소스를 막 읽은 모델이 쓴 산문**이라 자명하지 않다.
    """
    problems: list[str] = []
    prose = f"{card.subject}\n{card.behavior}"

    # 1) span 이 실재하는가
    if known_spans is not None:
        for s in card.spans:
            if (s.file_path, s.start_line, s.end_line) not in known_spans:
                problems.append(f"span 미실재: {s.file_path}:{s.start_line}-{s.end_line}")

    # 2) code_terms 는 맨 식별자이고, 개수 상한이 있으며, span 안에 실재해야 한다
    if len(card.code_terms) > MAX_CODE_TERMS:
        problems.append(f"code_terms 과다: {len(card.code_terms)} > {MAX_CODE_TERMS}")
    joined_src = "\n".join(span_sources.values())
    for term in card.code_terms:
        if not _IDENT.match(term):
            problems.append(f"code_terms 가 식별자가 아님: {term!r}")
        elif term not in joined_src:
            problems.append(f"code_terms 가 span 에 없음: {term!r}")

    # 3) 소스 줄이 산문으로 새지 않았는가 — 이 검사가 유출을 막는다
    prose_flat = _normalise(prose)
    for src in span_sources.values():
        for line in src.splitlines():
            norm = _normalise(line)
            if len(norm) >= _MIN_SOURCE_LINE and norm in prose_flat:
                problems.append(f"산문에 소스 줄이 그대로 들어감: {norm[:40]!r}")
                break

    # 4) 문자열 리터럴이 산문에 옮겨지지 않았는가.
    #    숫자는 검사하지 않는다 — "3회 재시도" 는 서술로서 정당하고, 막으면 카드의 값이 사라진다.
    #    막는 것은 `MAX_ATTEMPTS = 2` 같은 **소스 줄**(3번)과 문자열 리터럴이다.
    for src in span_sources.values():
        for lit in _STRING_LITERAL.findall(src):
            if lit in prose:
                problems.append(f"산문에 소스 문자열 리터럴: {lit[:40]!r}")
                break

    return problems


def is_near_duplicate(a: Card, b: Card, *, threshold: float = 0.9) -> bool:
    """같은 파일에 거의 같은 카드가 반복되는가 (§3.2 밀도 상한).

    자카드로 본다 — 임베딩을 쓰면 이 검사 자체가 비결정적이 되고, 그러면 무엇을 버렸는지
    설명할 수 없다.
    """
    ta = set(_normalise(f"{a.subject} {a.behavior}").split())
    tb = set(_normalise(f"{b.subject} {b.behavior}").split())
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= threshold


# ---------------------------------------------------------------- §3.4 낡음

FRESH = "fresh"
STALE = "stale"
ORPHANED = "orphaned"


def card_state(card: Card, current: dict[tuple[str, str], str]) -> str:
    """카드가 아직 현재 코드를 설명하는가. **모델을 부르지 않는다** — 해시 비교다.

    `current` — (file_path, symbol) → 현재 span_hash.

    span 이 하나라도 사라졌으면 `orphaned`, 하나라도 해시가 달라졌으면 `stale`.
    stale 은 틀렸다는 뜻이 아니라 *설명이 참이었던 코드가 움직였다* 는 뜻이고, 그것이 이
    방향이 드러내려는 신호다. 다만 카드에 관한 사실이지 코드에 관한 사실이 아니다.
    """
    if not card.spans:
        return ORPHANED
    for s in card.spans:
        now = current.get((s.file_path, s.symbol))
        if now is None:
            return ORPHANED
        if now != s.span_hash:
            return STALE
    return FRESH


# ------------------------------------------------- §6.1 재현성 측정

@dataclass(frozen=True)
class Agreement:
    """여러 실행 사이의 일치도. **점추정이 아니라 분포로 보고한다** (§6.1).

    2회는 구간 없는 한 숫자를 준다. 스크린샷 판독기 때 잡음 폭을 측정하지 않고 SPEC 을 네 개
    썼다가 근거 32건이 전부 잡음이었던 일이 있다 — 그래서 여기서는 쌍을 전부 본다.
    """
    mean: float
    low: float
    high: float
    pairs: int

    def __str__(self) -> str:
        return f"{self.mean:.3f} (범위 {self.low:.3f}~{self.high:.3f}, 쌍 {self.pairs}개)"


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def term_agreement(runs: list[tuple[str, ...]]) -> Agreement:
    """같은 심볼에 대한 여러 실행의 `domain_terms` 일치도.

    비교 전에 소문자·공백 정규화만 한다. 그 이상(동의어 병합 등)을 하면 생성기의 흔들림을
    측정 코드가 가려버린다 — 측정하려는 것이 바로 그 흔들림이다.
    """
    norm = [{t.strip().lower() for t in r if t.strip()} for r in runs]
    scores = [
        _jaccard(norm[i], norm[j])
        for i in range(len(norm))
        for j in range(i + 1, len(norm))
    ]
    if not scores:
        raise ValueError("일치도를 측정하려면 실행이 둘 이상이어야 한다")
    return Agreement(mean=sum(scores) / len(scores), low=min(scores),
                     high=max(scores), pairs=len(scores))
