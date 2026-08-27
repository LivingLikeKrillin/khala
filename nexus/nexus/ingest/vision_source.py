"""인용에서 원본 그림으로 — SPEC-nexus-vision-source-ref.

ADR-0010 §2 는 기계가 읽은 텍스트를 **독자가 원본을 다시 읽을 수 있다는 이유로** 받아들이고,
§3.1 은 재해석 가능한 참조가 없으면 그 등급이 "뒤에 아무것도 없는 이름표" 라고 적는다.
이 모듈이 그 참조를 실제로 해석한다.

**"없다" 와 "실패했다" 를 섞지 않는다.** 둘을 뭉개는 것은 `ObjectNotFound` 를 삭제로 읽은 것과
같은 종류의 실수이고, 그 오독으로 2026-08-11 에 한 턴을 태웠다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from nexus.ingest.vision import HANDLE_CHARS

#: 마커 문법 (SPEC §2.5). 쓰는 쪽은 `vision.build_block()`, 읽는 쪽은 여기다 — 둘이 갈리지
#: 않도록 시험이 **writer 가 만든 문자열**을 읽는다. 모르는 필드는 무시한다: 나중에 필드를
#: 더해도 옛 청크가 좌초하지 않아야 한다.
_MARKER = re.compile(r"!\[\]\(\)\{:\s*(?P<fields>[^}]*)\}")
_FIELD = re.compile(r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>[^\s}]+)")
_HANDLE = re.compile(r"^[0-9a-f]{%d}$" % HANDLE_CHARS)


class AmbiguousHandle(RuntimeError):
    """한 식별자가 두 행에 걸렸다. **고르지 않는다** — 인용이 다른 그림으로 해석되는 것은
    해석 못 하는 것보다 나쁘다."""


@dataclass(frozen=True)
class SourceRef:
    source_uri: str
    block_id: str
    image_sha256: str
    extractor_identity: str

    def render(self) -> str:
        """`vision.source_ref()` 와 같은 형식."""
        from nexus.ingest.vision import source_ref

        return source_ref(self.source_uri, self.block_id, self.image_sha256)


@dataclass(frozen=True)
class Unresolvable:
    """참조가 없다 — 오류가 아니라 **상태**다. 왜인지가 붙는다."""
    reason: str


def parse_marker(chunk_text: str) -> dict[str, str] | None:
    """청크 본문 → 마커 필드. 마커가 없으면 None (= 저자 청크, 오류 아님)."""
    m = _MARKER.search(chunk_text or "")
    if not m:
        return None
    return {f.group("key"): f.group("value") for f in _FIELD.finditer(m.group("fields"))}


async def resolve_source(tenant: str, chunk_text: str) -> SourceRef | Unresolvable | None:
    """청크 → 원본 참조. 결과는 SPEC §2.2 의 표 그대로다."""
    from nexus import db

    fields = parse_marker(chunk_text)
    if fields is None or fields.get("derived") != "vision":
        return None                                   # 저자 청크
    handle = (fields.get("img") or "").lower()
    if not handle:
        return Unresolvable("pre-migration marker")   # 이 변경 이전에 적재된 청크
    if not _HANDLE.match(handle):
        return Unresolvable("malformed handle")
    identity = fields.get("extractor") or ""

    rows = await db.fetch_all(
        "SELECT image_sha256, block_id, source_uri FROM vision_extractions "
        "WHERE tenant = $1 AND left(image_sha256, $2) = $3 AND extractor_identity = $4",
        tenant, HANDLE_CHARS, handle, identity)
    if not rows:
        return Unresolvable("no extraction row")      # 행이 지워졌거나 신원이 옮겨졌다
    if len(rows) > 1:
        raise AmbiguousHandle(
            f"식별자 {handle} 가 {len(rows)}개 행에 걸렸다 (tenant={tenant}) — "
            "유일 인덱스(idx_vision_handle)가 없거나 깨졌다. 어느 하나를 고르지 않는다.")
    row = rows[0]
    if not (row["block_id"] or "").strip():
        return Unresolvable("reference not recorded")  # 행은 있는데 참조가 없다
    return SourceRef(row["source_uri"], row["block_id"], row["image_sha256"], identity)


async def unresolvable_count(tenant: str) -> dict:
    """참조가 없는 추출이 몇 건인가 (SPEC §5.9).

    **추출 행 기준**으로 센다 — 청크와 추출은 서로 조인되지 않는 별개 모집단이고(§1), 청크 쪽
    술어로 억제하면 청크가 없는 추출의 미해석 상태가 0 으로 보고된다.

    **현 판독기와 은퇴한 판독기를 가른다.** SPEC 이 예상하지 못한 것이 실적재에서 나왔다:
    ADR-0010 §5 는 저장을 `(bytes, extractor_identity)` 로 키잉하므로 걷기는 **현 신원의 행만**
    만난다. 은퇴한 신원의 44 행은 어떤 걷기도 다시 닿지 않고, 합쳐 세면 영원히 안 꺼지는 ⚠ 가
    된다 — 이 리포가 방금 다른 자리에서 지운 실패 모양 그대로다.

    그리고 그것은 부정확하기도 하다: 활성 인용은 전부 현 신원의 마커를 이고 있으므로, 은퇴한
    행을 가리키는 인용은 **없다**. 세되, 경보로 세지 않는다.
    """
    from nexus import db
    from nexus.ingest.vision import extractor_identity

    now = extractor_identity()
    row = await db.fetch_one(
        "SELECT count(*) AS rows, "
        "       count(*) FILTER (WHERE extractor_identity = $2) AS current_rows, "
        "       count(*) FILTER (WHERE extractor_identity = $2 "
        "                          AND coalesce(btrim(block_id), '') = '') AS unresolvable, "
        "       count(*) FILTER (WHERE extractor_identity <> $2 "
        "                          AND coalesce(btrim(block_id), '') = '') AS retired, "
        "       count(*) FILTER (WHERE extractor_identity = $2 "
        "                          AND coalesce(text, '') = '') AS empty_text "
        "FROM vision_extractions WHERE tenant = $1", tenant, now)
    return {"rows": row["rows"] if row else 0,
            "identity": now,
            "current_rows": row["current_rows"] if row else 0,
            "unresolvable": row["unresolvable"] if row else 0,
            "retired_unresolvable": row["retired"] if row else 0,
            "empty_text": row["empty_text"] if row else 0}
