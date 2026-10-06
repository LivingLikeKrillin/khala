"""이 답이 **어떤 코퍼스**에서, **어떤 검색 설정**으로 나왔는가.

같은 질문의 답이 어제와 다르면 까닭이 다섯 갈래다 — 프롬프트 · 코퍼스 내용 · 검색 스택 · 모델 ·
표본. 프롬프트는 `llm/prompt_version.py` 가 가르고, 여기 둘이 코퍼스와 검색 스택을 가른다.

값은 공유 접합부(`search/reconcile.py::packet_for_answer`)가 근거 묶음에 찍고, 두 답변 API 표면의 응답과
`search_log` 가 그 값을 옮긴다 — 자리마다 다시 세면 응답과 기록이 갈릴 수 있다.
"""

from __future__ import annotations

import hashlib
import json
from typing import Iterable, Sequence

import structlog

from nexus.search.scope_sql import normalize_scope, tenant_predicate

logger = structlog.get_logger(__name__)

#: 구간을 가르는 표시이지 암호학적 증명이 아니다 — `prompt_version` 과 같은 길이.
_LEN = 12


def _digest(parts: Iterable[str]) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")          # 청크 경계 — 이어붙임 모호성을 없앤다
    return h.hexdigest()[:_LEN]


def search_fingerprint(config: dict | None) -> str:
    """검색 핑거프린트 — 임베딩 컬럼 · 모델 · 토크나이저 + **`search` 설정 절 전체**.

    ⛔ **목록이 아니라 절 전체를 본다.** 먼저 있던 검색 스택 핑거프린트(`signals.evidence_fingerprint`,
    충분성 판정자 전용)은 일곱 값을 골라 적었고, 그 뒤에 생긴 보강 설정(정정 확인 패스 · 페어 확장 ·
    참조 필 · 코드 값)은 거기 없다. 목록을 사람이 적는 한 같은 일이 난다 — `prompt_version` 의
    첫 버전이 똑같이 낡았다. 절 전체면 내일 생길 설정도 오늘 이미 들어간다.

    ⚠ `search` 밖의 절은 안 넣는다. 신선도 TTL 같은 설정까지 넣으면 버전이 검색과 무관하게 바뀌어
    경계가 뜻을 잃는다. 임베딩 컬럼은 env 가 덮을 수 있으므로 설정 파일이 아니라
    `configured_column()` 에서 읽는다(`evidence_fingerprint` 와 같은 이유).
    """
    from nexus.index.bm25 import active_tokenizer
    from nexus.index.vector_index import configured_column

    cfg = config or {}
    return _digest([
        configured_column(cfg),
        str((cfg.get("embedding") or {}).get("model", "")),
        type(active_tokenizer()).__name__,
        json.dumps(cfg.get("search") or {}, sort_keys=True, ensure_ascii=False, default=str),
    ])


def corpus_version_of(rows: Iterable[tuple[str, str, str | None]]) -> str:
    """`(tenant, rid, content_hash)` 행들의 버전. **순서와 무관하다** — 정렬해서 센다.

    `content_hash` 는 적재 경로가 내용 변화를 가르는 데 이미 쓰는 값이라, 재적재돼도 내용이 같으면
    버전이 같다. ⚠ 조각내기 · 임베딩 · 검색 설정의 변화는 못 본다 — 그건 `search_fingerprint` 몫이다.
    """
    lines = sorted((t, r, h or "") for t, r, h in rows)
    return _digest(f"{t}\t{r}\t{h}" for t, r, h in lines)


async def corpus_version(tenant: str | Sequence[str], clearance: str, pool) -> str:
    """이번 답이 뒤진 코퍼스의 버전. **이 호출자가 읽을 수 있는 문서만** 센다.

    ⛔ `nexus/CLAUDE.md`: *모든 SELECT 에 정책 필터를 건다. 예외 없음.* 숨긴 · 격리된 · 등급 밖 ·
    범위 밖 문서는 이 답의 코퍼스가 아니다 — 세면 답이 볼 수 없던 변화로 버전이 바뀐다.

    못 세면 빈 문자열이다(모른다). 진단이 답을 죽이지 않는다.

    ⚠ 빈 문자열의 까닭은 둘이다 — 셀 DB 가 없었다(접합부가 풀 없이 불렸다), 또는 조회가 터졌다.
    받는 쪽에게는 둘 다 「모른다」가 맞는 값이고(가짜 버전을 지어 주면 같은 코퍼스로 읽힌다), 둘을
    가르는 것은 운영자의 몫이라 터진 쪽은 경고 로그 `corpus_version_failed` 에 남긴다.
    """
    if not normalize_scope(tenant) or not clearance:
        return ""
    try:
        pred, val = tenant_predicate("tenant", 1, tenant)
        async with pool.acquire() as con:
            rows = await con.fetch(
                f"""
                SELECT tenant, rid, content_hash FROM documents
                 WHERE {pred}
                   AND classification <= $2::classification_level
                   AND is_quarantined = false
                   AND status = 'active'
                """,
                val, clearance)
        return corpus_version_of((r["tenant"], r["rid"], r["content_hash"]) for r in rows)
    except Exception as e:  # noqa: BLE001
        logger.warning("corpus_version_failed", tenant=tenant, error=str(e))
        return ""
