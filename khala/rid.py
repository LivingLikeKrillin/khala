"""Canonical Resource ID 생성 + Entity name 정규화.

rid는 "내용이 바뀌어도 동일 객체로 취급되는 단위"에서 안정적이어야 한다.
직접 rid를 문자열로 만들지 말 것. 반드시 이 모듈의 함수를 사용할 것.
"""

import hashlib
import re


def make_rid(prefix: str, *parts: str) -> str:
    """SHA-256 해시의 앞 12자를 사용한 canonical rid 생성."""
    raw = ":".join([prefix] + [str(p) for p in parts])
    hash_hex = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{hash_hex}"


def doc_rid(canonical_uri: str) -> str:
    """문서 rid. canonical_uri 기반이므로 내용이 바뀌어도 rid 유지."""
    return make_rid("doc", canonical_uri)


def chunk_rid(parent_doc_rid: str, section_path: str, chunk_index: int) -> str:
    """청크 rid. chunking 규칙이 바뀌면 rid도 바뀜. doc_rid는 유지."""
    return make_rid("chunk", parent_doc_rid, section_path, str(chunk_index))


def entity_rid(tenant: str, entity_type: str, canonical_name: str) -> str:
    """엔티티 rid. canonicalize_entity_name()을 반드시 먼저 적용할 것."""
    return make_rid("ent", tenant, entity_type, canonical_name)


def edge_rid(tenant: str, edge_type: str, from_rid: str, to_rid: str) -> str:
    """설계 기반 edge rid. deterministic composite key로 idempotent upsert."""
    return make_rid("edge", tenant, edge_type, from_rid, to_rid)


def observed_edge_rid(tenant: str, edge_type: str, from_rid: str, to_rid: str) -> str:
    """관측 기반 edge rid. window를 rid에 넣지 않음 → 같은 from→to는 같은 rid."""
    return make_rid("obs_edge", tenant, edge_type, from_rid, to_rid)


def evidence_rid(subject_rid: str, evidence_source_rid: str) -> str:
    """Evidence rid. subject(근거 대상) → evidence(근거 소스) 쌍으로 유일."""
    return make_rid("evi", subject_rid, evidence_source_rid)


def canonicalize_entity_name(raw_name: str, entity_type: str) -> str:
    """Entity name → canonical form.

    추출기(regex/dep.parsing/LLM)가 바뀌어도 동일 entity가 동일 rid를 받도록,
    name 정규화를 추출기와 독립적으로 수행한다.

    규칙:
    - 양쪽 공백 제거
    - lowercase
    - 언더스코어 → 하이픈 통일
    - 연속 공백/하이픈 정리
    - 한국어 변형 통일은 aliases(entities.yaml)에서 관리

    Examples:
        >>> canonicalize_entity_name("Payment_Service", "Service")
        'payment-service'
        >>> canonicalize_entity_name("  Order  Service ", "Service")
        'order-service'
    """
    name = raw_name.strip().lower()
    name = name.replace("_", "-")
    name = re.sub(r"\s+", "-", name)
    name = re.sub(r"-+", "-", name)
    name = name.strip("-")
    return name
