"""판독기가 자기 자신을 반복하는가 — SPEC-nexus-vision-reproducibility.

ADR-0010 §5 의 불변식("같은 바이트·같은 신원 → 같은 텍스트")은 **재 본 적이 없었고, 재 보니
프로덕션에서 거짓이었다.** 이 모듈은 그 재현율을 재고 판정하는 순수 로직이다.

정규화가 스크립트가 아니라 여기 있는 이유: 이 규칙이 판정을 만들기 때문이다. 스크립트 안에
있으면 시험할 수 없고, 시험할 수 없는 규칙은 조용히 바뀐다.
"""

from __future__ import annotations

import re
import unicodedata

#: 판독기가 기록의 판독기로 채택되려면 넘어야 하는 선 (SPEC §2.1).
#:
#: 10% 인 이유는 두 측정에서 멀어서가 아니다 — 3.6% → 10% 는 2.8배다. **ADR-0010 §5 의 해석 키가
#: 의미를 갖는 최대 불일치**라서다: 10% 면 같은 바이트를 다시 읽었을 때 값 열 중 아홉이 재현되고,
#: 인용은 두 번째 판독이 대체로 동의할 텍스트를 가리킨다. 84.7% 에서는 키가 장식이다.
MAX_VARIATION = 0.10

_SCAFFOLD = re.compile(r"^\s*[|#>\-\s]*$")
_IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]*")
_HANGUL = re.compile(r"[가-힣]{2,}")

#: NFKC 가 접지 않는 것들. 수학 빼기표와 대시류는 판독기마다 다르게 쓴다.
_DASHES = {"−": "-", "–": "-", "—": "-"}


def normalize(text: str) -> str:
    """서식을 접고 내용은 접지 않는다.

    `|` 는 **공백으로 치환**한다. 지우면 두 셀이 붙어 어느 판독에도 없는 식별자가 만들어지고
    (`60|FENDI` → `60FENDI`), 표를 쓰는 쪽만 그 피해를 입어 한쪽으로 기운다.
    """
    t = unicodedata.normalize("NFKC", text or "")
    for src, dst in _DASHES.items():
        t = t.replace(src, dst)
    out = []
    for line in t.splitlines():
        if _SCAFFOLD.match(line):
            continue
        line = line.replace("|", " ").lstrip("#> ").strip()
        if line:
            out.append(re.sub(r"\s+", " ", line))
    return "\n".join(out)


def tokens(text: str) -> tuple[set[str], set[str]]:
    """(식별자·숫자, 한글) 토큰 집합.

    식별자만 판정에 쓴다. 한글 산문은 판독기마다 줄바꿈·조사가 정당하게 달라서, 그 변동을
    판독기 불안정으로 세면 안정된 판독기도 떨어진다 (SPEC §5).
    """
    n = normalize(text)
    idents = {m.group(0) for m in _IDENT.finditer(n) if len(m.group(0)) > 1}
    hangul = {m.group(0) for m in _HANGUL.finditer(n)}
    return idents, hangul


def variation(first: str, second: str) -> float:
    """두 판독의 **식별자 토큰 변동률**. 0.0 = 동일, 1.0 = 겹치는 것이 없다.

    합집합 대비 대칭차 — 어느 쪽을 기준으로 삼지 않는다. 둘 다 비면 잴 것이 없으므로 0.0 이다
    (그림에 글자가 없는 경우이고, 그건 불안정이 아니다).
    """
    a, _ = tokens(first)
    b, _ = tokens(second)
    union = a | b
    if not union:
        return 0.0
    return len(a ^ b) / len(union)


def passes(rate: float | None) -> bool:
    """재지 않은 것(None)은 통과가 아니다 — 그게 지금 44행의 상태다."""
    return rate is not None and rate <= MAX_VARIATION


def summarize(pairs: list[tuple[str, str]]) -> dict:
    """(1회차, 2회차) 목록 → 재현율 요약. 순수 함수."""
    if not pairs:
        return {"images": 0, "identical": 0, "variation": None, "passes": False}
    identical = 0
    sym, uni = 0, 0
    for first, second in pairs:
        a, _ = tokens(first)
        b, _ = tokens(second)
        if a == b:
            identical += 1
        sym += len(a ^ b)
        uni += len(a | b)
    rate = (sym / uni) if uni else 0.0
    return {"images": len(pairs), "identical": identical,
            "variation": rate, "passes": passes(rate)}


async def fetch_reader_health(tenant: str) -> dict:
    """이 테넌트의 그림 판독이 **어떤 재현율의 판독기에서 왔는가** (SPEC §2.3 의 표면).

    컬럼 하나를 만들어 두고 아무도 안 읽으면 그건 신호가 아니다 —
    [[SPEC-nexus-index-completeness]] 가 정확히 그 실패(옳은 측정이 로그에서 하루를 지나감)를
    기록했다. 그래서 `nexus status` 가 이걸 부른다.

    **청크와 추출 행을 잇지 못한다.** 청크 마커는 `extractor=<신원>` 만 담고 이미지 해시를 담지
    않으며, `vision.source_ref()` 는 정의돼 있으나 부르는 곳이 없다. 그래서 두 모집단을 각각
    세고 **잇지 않은 채로** 보고한다 — 없는 연결을 정규식으로 지어내면 그 숫자가 거짓말을 한다.
    """
    from nexus import db

    ext = await db.fetch_one(
        "SELECT count(*) AS rows, "
        "       count(*) FILTER (WHERE reader_variation IS NULL) AS unmeasured, "
        "       count(*) FILTER (WHERE reader_variation > $2) AS above_threshold "
        "FROM vision_extractions WHERE tenant = $1",
        tenant, MAX_VARIATION,
    )
    chunks = await db.fetch_val(
        "SELECT count(*) FROM chunks c JOIN documents d ON d.rid = c.doc_rid "
        "WHERE c.tenant = $1 AND c.status = 'active' AND d.status = 'active' "
        "  AND c.is_quarantined = false AND c.provenance_tier = 'machine_read'",
        tenant,
    )
    return {"extractions": ext["rows"] if ext else 0,
            "unmeasured": ext["unmeasured"] if ext else 0,
            "above_threshold": ext["above_threshold"] if ext else 0,
            "machine_read_chunks": int(chunks or 0)}
