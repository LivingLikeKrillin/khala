"""질의에 섞인 **식별자**만 따로 뽑는다 — 그 한 낱말이 문서를 가르는데 묻히기 때문이다.

⛔ **왜 생겼나 (실측 2026-09-20, 소비자 실행 열 건).** 설명 층이 사건 번들로 질의를 만드는데,
그 번들이 드는 것은 `failureClass=PAYLOAD_LOST` 같은 **범주 값**이다. 그런데 키워드 경로가
그 값을 이렇게 본다:

    'failureClass=LOCALIZATION_LOST'  →  ['failureclass', 'localization', 'lost']
    tsquery                           →  'failureclass' | 'localization' | 'lost'

세 가지가 겹쳤다.

1. 식별자가 **밑줄에서 쪼개진다.** 인접 판정이 없으므로 `LOCALIZATION_LOST` 라는 한 덩어리는
   사라지고 흔한 낱말 둘이 남는다
2. 항이 **OR** 로 묶인다. 질의가 2,000글자면 항이 수백 개가 되고, `ts_rank_cd` 는 커버
   밀도를 보므로 **많은 항을 덮는 긴 조각**이 이긴다
3. `lost` 는 여섯 절차 문서의 적용 범위 표에 **전부** 있다(`PAYLOAD_LOST` ·
   `LOCALIZATION_LOST` · `CONTROL_AUTHORITY_LOST` …). 가르는 항은 `localization` 하나이고,
   그 하나가 수백 중 하나로 묻힌다

⭐ **끊긴 곳은 없다.** 같은 토큰을 **단독으로** 던지면 키워드 경로가 제대로 찾는다 —
`LOCALIZATION_LOST` → 맞는 문서 6위, `PAYLOAD_LOST` → 맞는 문서 5위 (실측). 색인도 토큰화도
정상이고, 무너지는 것은 질의가 길어질 때뿐이다.

그래서 이 모듈이 하는 일은 하나다: **그 토큰만 뽑아 따로 한 번 더 묻게 해 준다.**
묻는 것은 `hybrid_search` 의 기존 채널 기제이고, 여기서 새로 만드는 개념은 없다.

⚠ **이것은 처치이고 측정 대상이다** — `nexus/docs/PROCEDURE_RETRIEVAL_PREREGISTRATION.md`
의 T2. 기본은 꺼져 있고, 켜는 것은 요청이다.
"""

from __future__ import annotations

import re

#: 식별자로 볼 모양: **대문자로 시작하고 밑줄이 최소 하나.** `PAYLOAD_LOST` ·
#: `HOLD_KIND_EMPTY` · `X_FIXTURE_E4412` 가 걸리고, `API` · `SOP` 같은 민낯 약어는 안 걸린다.
#:
#: ⛔ **밑줄을 요구하는 것이 이 정규식의 전부다.** 약어까지 받으면 한국어 산문에 흔히 섞이는
#: 대문자 낱말이 전부 들어와, 이 채널이 *"대문자가 있는가"* 를 묻게 된다 — 그러면 가르는
#: 힘이 사라지고 원래 질의와 같은 것을 두 번 묻는 것이 된다.
IDENTIFIER = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")

#: 한 질의에서 받을 식별자 수의 상한. 사건 번들이 드는 범주 값은 손에 꼽는다 — 그보다 많이
#: 나오면 질의가 식별자 목록에 가깝다는 뜻이고, 그때는 이 채널이 원문과 같아져 값이 없다.
MAX_IDENTIFIERS = 12


def extract_identifiers(query: str) -> tuple[str, ...]:
    """질의에서 식별자형 토큰만. 순서는 **처음 나온 순서**, 중복 없음, 없으면 빈 튜플.

    순서를 지키는 이유는 SQL 이 아니라 **기록**이다 — 이 값이 그대로 응답과 진단에 나가는데,
    정렬하면 호출자가 보낸 것과 우리가 쓴 것이 달라 보인다.
    """
    if not query:
        return ()
    seen: dict[str, None] = {}
    for m in IDENTIFIER.finditer(query):
        seen.setdefault(m.group(0), None)
    return tuple(seen)[:MAX_IDENTIFIERS]


def identifier_query(query: str) -> str:
    """식별자만 남긴 **둘째 질의**. 없으면 빈 문자열 — 그러면 채널을 만들지 않는다.

    ⛔ **빈 문자열과 원문은 다르다.** 식별자가 없을 때 원문을 돌려주면 같은 질의를 두 번
    묻게 되고, 가중 합산은 모든 문서에 같은 배수를 곱할 뿐 순서를 안 바꾼다 — 경로만 두 배로
    돌고 절대 점수가 팽창한다(`fuse_channels` 머리말이 같은 것을 적어 뒀다).
    """
    return " ".join(extract_identifiers(query))
