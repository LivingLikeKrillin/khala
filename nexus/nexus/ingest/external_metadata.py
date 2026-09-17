"""외부-적재(ungoverned Path B) 후처리 메타데이터 — label · doc_type · prov_inputs.

`_default_external_ingest_fn` 이 run_ingest 로 본문을 넣은 **뒤에** documents 행에 남기는 것들.
sink 안에 인라인되어 있으면 run_ingest(임베딩·mecab) 없이는 규칙을 검증할 수 없어 떼어냈다.

규칙(순서 무관, 서로 독립):
  · quarantined 행에는 아무것도 쓰지 않는다.
  · label/doc_type 은 실제로 재색인된 경우(=멱등 히트가 아닐 때)에만.
  · prov_inputs(source_roots)는 **멱등 히트에도** 쓴다 — 변경 없는 페이지의 root 귀속이
    갱신되어야 재조정의 containment 술어가 성립하고, 레거시 행이 백필된다.
    (SPEC-nexus-notion-reconciliation §3.1)
"""

from __future__ import annotations

from nexus import db

#: CRM label — classification 레벨이 아니다. 거버넌스 밖(approved_hash 없음)임을 표시한다.
#: **정본은 `nexus.labels` 로 옮겼다.** 라벨이 둘이 되면서(합성 표식이 붙었다) 선언이 한 곳에
#: 있어야 했고, `ingest` 와 `a2a` 가 서로를 못 끌어오므로 의존 없는 최상위 모듈이 유일한 자리다.
#: 여기서는 재수출만 한다 — 기존 호출부의 import 경로를 깨지 않는다.
from nexus.labels import EXTERNAL_LABEL  # noqa: E402,F401

# 레거시 CSF kind → 축-A 정본 타입(S1). Arbiter doctypes 레지스트리의 aliases 미러 —
# 패키지 디커플링 때문에 소량 중복한다.
_KIND_ALIASES = {"SPEC": "DESIGN", "FLOW": "NOTE"}


def normalize_csf_kind(kind: str) -> str:
    """레거시 CSF kind → 축-A 정본 타입. alias 없으면 그대로."""
    return _KIND_ALIASES.get(kind, kind)


async def apply_external_metadata(
    rid: str,
    tenant: str,
    doc: dict,
    *,
    idempotent: bool,
    quarantined: bool,
) -> None:
    if quarantined:
        return

    if not idempotent:
        await db.execute(
            "UPDATE documents SET labels = array_append(labels, $3) "
            "WHERE rid = $1 AND tenant = $2 AND NOT ($3 = ANY(labels))",
            rid, tenant, EXTERNAL_LABEL,
        )
        await db.execute(
            "UPDATE documents SET doc_type = $3 WHERE rid = $1 AND tenant = $2",
            rid, tenant, normalize_csf_kind(str(doc.get("kind", "") or "NOTE")),
        )

    prov = doc.get("provenance") or {}
    reached = prov.get("source_roots")
    if reached:
        from nexus.ingest.sources.notion_reconcile import write_source_roots

        # walked_roots 가 없으면(단일 root 호출자) 이번에 닿은 root 만 걸었다고 본다.
        walked = prov.get("walked_roots") or reached
        await write_source_roots(rid, tenant, reached=list(reached), walked=list(walked))
