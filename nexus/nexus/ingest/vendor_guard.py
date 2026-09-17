"""벤더 원문은 코퍼스에 들어오지 않는다 — **격리가 아니라 거절이다.**

PII 는 격리한다(저장하되 숨긴다). 벤더 원문은 **저장 자체가 규율 위반**이라 다르게 처분한다:
청크가 되기 전에 돌려보내고, 그 사실을 세어서 낸다. 조용히 건너뛰면 규율이 이름만 남는다.

⛔ **"벤더 이름" 을 찾지 않는다.** 우리 조사 노트는 벤더 이름과 심볼과 해시로 가득하다 —
그게 그 노트의 존재 이유다(원문 대신 심볼과 해시만 남긴다). 이름으로 거르면 지켜야 할 것을
막고 막아야 할 것은 그대로 들어온다.

⭐ **보는 것은 「이 문서가 자기 자신에 대한 남의 권리를 주장하는가」 하나다.** 원문에는
저작권 표시·기밀 표시가 붙어 있고, 그것을 **옮겨 적은 노트**에는 없다. 실측(2026-09-18):
`docs/vendors/orbit.md` 는 Boston Dynamics 의 OpenAPI 를 323개 심볼까지 분석하지만 권리
주장은 한 줄도 없다 — 통과해야 할 대조군이다.

⚠ **인용은 주장이 아니다.** 코드 스팬과 인용 블록 안의 권리 표시는 *"저쪽 문서에 이렇게
적혀 있다"* 는 서술이지 이 문서의 주장이 아니다. `check_terms.py` 가 걷어낸 말을 백틱 안에서
허용하는 것과 같은 규칙을 쓴다.

⚠ **이 검사는 완전하지 않다.** 권리 표시를 지우고 붙여 넣은 원문은 통과한다. 그것까지
막으려면 본문의 축자성을 봐야 하는데, 그 판정은 우리 노트(심볼 323개를 그대로 나열한다)와
구별되지 않는다. 막는 것은 **표시를 달고 오는 원문**이고, 그 범위를 여기 적어 둔다.
"""

from __future__ import annotations

import re

#: 권리 주장으로 읽는 표현들. **패턴을 설정으로 빼지 않는다** — 이건 조정값이 아니라 규율이고,
#: 설정이면 어느 날 조용히 꺼진다. `fingerprint_scan.py` 와 같은 이유로 코드에 둔다.
_ASSERTIONS: tuple[tuple[str, str], ...] = (
    (r"©\s*\d{4}", "저작권 표시(©)"),
    (r"\bcopyright\b\s*(?:\(c\)\s*)?\d{4}", "저작권 표시(Copyright + 연도)"),
    (r"\ball rights reserved\b", "All Rights Reserved"),
    (r"\bproprietary and confidential\b", "Proprietary and Confidential"),
    (r"\bconfidential and proprietary\b", "Confidential and Proprietary"),
    (r"\bredistribution and use in source and binary forms\b", "SDK 라이선스 헤더"),
)

_CODE_SPAN = re.compile(r"`[^`]*`|```.*?```", re.S)
_QUOTE_LINE = re.compile(r"^\s*>.*$", re.M)


def _prose(text: str) -> str:
    """주장을 찾을 자리 — 인용과 코드를 걷어낸 나머지.

    걷어내는 순서가 코드 먼저다. 코드 블록 안에 `>` 로 시작하는 줄이 있을 수 있고, 그것을
    인용으로 먼저 지우면 블록의 나머지가 붙어 버린다.
    """
    return _QUOTE_LINE.sub(" ", _CODE_SPAN.sub(" ", text))


def rights_assertions(text: str) -> list[str]:
    """이 문서가 **자기 자신에 대해** 주장하는 권리 표시들. 없으면 빈 목록."""
    prose = _prose(text)
    return [name for pat, name in _ASSERTIONS
            if re.search(pat, prose, re.IGNORECASE)]


class VendorOriginalRefused(Exception):
    """벤더 원문으로 식별돼 적재를 거절했다. **격리가 아니다** — 저장하지 않는다."""

    def __init__(self, path: str, found: list[str]):
        self.path = path
        self.found = found
        super().__init__(
            f"벤더 원문으로 식별돼 적재를 거절한다: {path} — {', '.join(found)}. "
            f"원문 대신 심볼명과 해시를 담은 조사 노트를 넣어라."
        )


def refuse_if_vendor_original(path: str, text: str) -> None:
    """벤더 원문이면 예외. 아니면 조용히 돌아온다 — 통과가 정상 경로다."""
    found = rights_assertions(text)
    if found:
        raise VendorOriginalRefused(path, found)
