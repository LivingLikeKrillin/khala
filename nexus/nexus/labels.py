"""CRM 라벨 정본 — **등급이 아니라 표식이다.**

`classification` 은 누가 읽어도 되는가를 정하고, 라벨은 **이 문서가 무엇인가**를 말한다.
둘을 섞으면 안 된다: 합성 자료를 `RESTRICTED` 로 가리는 것은 합성이라고 말하는 것이 아니고,
가려 두면 쓸 수 없게만 된다.

의존이 없는 최상위 모듈인 이유는 하나다. `ingest` 와 `a2a` 가 둘 다 이 값을 쓰는데 그 둘은
서로를 끌어오면 안 된다(a2a 는 SDK 에 묶여 있다). 라벨을 어느 한쪽에 두면 다른 쪽이 사본을
만들고, 사본 둘은 반드시 갈린다.

⚠ **라벨은 검색 결과까지 가야 뜻이 있다.** 문서 행에만 있고 근거에 안 실리면 읽는 사람은
합성 자료와 실제 자료를 구별할 수 없다 — `provenance_tier` 가 여섯 hop 을 다 통과해야 하는
것과 같은 이유다(ADR-0010 §4: *"추출 안 하느니만 못하다"*).
"""

from __future__ import annotations

#: 거버넌스 밖(`approved_hash` 없음)의 외부 사양. 2026-08 서브프로젝트 A 가 도입했다.
EXTERNAL_LABEL = "external_spec"

#: **실제 현장 문서가 아니다.** 시연·평가용으로 사람이 지어낸 자료에 붙인다.
#:
#: 이것이 없으면 합성 SOP 가 실제 운영 문서와 같은 얼굴로 근거에 실린다. 검색이 잘 되면
#: 잘 될수록 나쁜 종류의 결함이다 — 지어낸 절차를 정확히 인용해 온다.
SYNTHETIC_LABEL = "synthetic"

#: 문서가 **자기 frontmatter 로 선언할 수 있는** 라벨.
#:
#: ⛔ **둘의 성질이 다르다.** `synthetic` 은 *"나는 지어낸 문서다"* 로, 그 문서를 쓴 사람만
#: 할 수 있는 말이고 본인 말고는 알 수 없다. `external_spec` 은 *"나는 외부 사양 관문으로
#: 들어왔다"* 로, **경로에 대한 주장**이다 — 그건 그 경로(`a2a` 게이트웨이)가 붙여야지
#: 문서가 자칭하면 안 된다. 자칭을 허용하면 파일 한 줄로 거버넌스 밖 문서인 척할 수 있고,
#: 읽는 사람에게는 `approved_hash` 가 없는 것이 정상으로 보인다.
#:
#: 그래서 **허용 목록이다.** 모르는 라벨은 조용히 넣지도, 조용히 버리지도 않는다 — 세어서
#: 적재 요약에 낸다(`IngestResult.refused_labels`).
SELF_DECLARABLE = frozenset({SYNTHETIC_LABEL})


def merge_sql(declarable_param: int, incoming: str = "EXCLUDED.labels") -> str:
    """재적재가 라벨을 어떻게 갱신하는가 — **정본은 이 한 곳이다.**

    규칙 한 줄: *자칭 가능한 몫만 갈아 끼우고 나머지는 보존한다.*

    ⛔ 통째로 덮으면 다른 경로가 붙인 표식(`external_spec`)이 재적재 한 번에 사라지고,
    거버넌스 밖 문서가 거버넌스 안 문서 얼굴이 된다. 반대로 병합만 하면 frontmatter 에서
    `synthetic` 을 지워도 표식이 영원히 남아 **끌 수가 없다.** 둘 다 틀리므로 두 방향이다.

    ⚠ **함수인 이유가 검사 때문이다.** 문자열 상수로 두면 검사가 SQL 을 베껴 쓰게 되고,
    그러면 본체가 바뀌어도 검사는 자기 사본을 통과시킨다 — 이 리포가 반복해서 데인 모양이다.
    """
    return (
        "("
        " SELECT coalesce(array_agg(DISTINCT l), '{}'::text[])"
        " FROM unnest("
        "   ARRAY(SELECT x FROM unnest(documents.labels) x"
        f"        WHERE NOT (x = ANY(${declarable_param}::text[])))"
        f"   || {incoming}"
        " ) AS l"
        ")"
    )


def declarable(raw: object) -> tuple[list[str], list[str]]:
    """frontmatter 의 `labels` 를 (받은 것, 물린 것) 으로 가른다.

    문자열 하나도 받는다 — `labels: synthetic` 은 YAML 에서 리스트가 아니라 문자열이다.
    """
    if raw is None:
        return [], []
    items = [raw] if isinstance(raw, str) else list(raw)
    names = [str(x).strip() for x in items if str(x).strip()]
    ok = sorted({n for n in names if n in SELF_DECLARABLE})
    no = sorted({n for n in names if n not in SELF_DECLARABLE})
    return ok, no
