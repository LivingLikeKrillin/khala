"""정정 확인 패스 — **정정당한 문서가 정정한 문서를 이기는 것**을 막는다.

**왜 있나 (2026-08-29 실측).** 라이브 코퍼스에 이런 자리가 있다: 어떤 필드가 지워졌다는 것을
적은 변경 이력이 코퍼스에 **있는데**, 질문을 던지면 그 필드가 아직 있다고 말하는 옛 문서가
대신 올라온다. 답변은 근거를 정확히 읽고 **낡은 사실**을 말한다. 경로로는 못 가른다 — 정정한
문서도 같은 `archive/` 아래 있었다.

**무엇을 하나.** 1차 근거가 부른 **이름**(camelCase·PascalCase)을 뽑아, 그 이름에 변경 어휘를
붙여 한 번 더 검색한다. 정정 문서가 있으면 그때 올라온다. 그 뒤는 답변 계약이 맡는다 —
근거가 서로 다르게 말하면 감추지 말라는 규칙이 이미 있고, 지금까지는 **한쪽만 와서** 그 규칙이
볼 것이 없었다.

**측정 (라벨 3개 × 5회, 근거는 결정론이라 회차 무관)**::

    처치 대상 R2   1패스 0/5  →  2패스 5/5      (정정 문서가 근거에 들어옴: ✗ → ○)
    대조군  R1     3/5       →  5/5
    대조군  S1     5/5       →  5/5
    검색 지연      300 ms    →  1,065 ms       (답변 경로 끝단의 2% 안쪽)

⚠ **처음 측정은 3/5 였고 그것은 라벨의 구멍이었다** (2026-08-29). 시스템은 `hard-delete`·
`물리 삭제` 로 답하는데 라벨엔 `Hard-Delete` 만 있었다. 표기를 넓히고 다시 재니 5/5 다.
그 사이 나는 없는 병("답변이 낡은 쪽을 고른다")에 처방을 만들어 측정까지 했고, 사전 규칙이
그것을 기각했다. **실패를 진단하기 전에 실패한 답변을 읽어라** — 점수는 어느 값이 빠졌는지만
알려 주고, 그 값이 정말 빠졌는지는 안 알려 준다.

⚠ 이 하니스의 잡음은 크다(대조군 R1 이 같은 조건에서 3/5 와 5/5 사이를 오갔다). 2회는 판정이
아니다.

**코드 기본값은 꺼짐**이다. `section_fill` 과 같은 이유로 — 설정 없는 호출부가 검색을 세 번 더
치지 않게 한다. 켜는 것은 배포 설정이고, **검색만 하는 경로에는 켜지 않는다**(거기서는 3.5배가
그대로 사용자에게 보인다).
"""

from __future__ import annotations

import collections
import re

import structlog

logger = structlog.get_logger(__name__)

#: 정정을 부르는 말. 문서는 한국어인데 이름은 영문이라 둘 다 넣는다.
CHANGE_WORDS = "삭제 제거 대체 전환 변경 폐기 deprecated removed"

#: 2차 검색을 돌릴 이름 수와 이름당 가져올 청크 수. **넉넉하게 두지 않는다** —
#: 2026-08-28 에 근거를 네 배로 불리고 점수를 하나도 못 산 실험이 있었다.
MAX_NAMES = 3
MAX_PER_NAME = 3

#: 이름 후보. **camelCase·PascalCase 만** 본다. 영어 산문 낱말을 이름으로 오인하면 2차 검색이
#: 잡음으로 채워지고, 그 잡음은 근거 자리를 정확히 먹는다.
_TOKEN = re.compile(r"\b[A-Za-z][A-Za-z0-9]{3,}\b")
_HAS_CASE_SHIFT = re.compile(r"[a-z][A-Z]")


def names_in(text: str, limit: int = MAX_NAMES) -> list[str]:
    """근거가 부른 이름들, 많이 나온 순."""
    counts = collections.Counter(
        t for t in _TOKEN.findall(text or "") if _HAS_CASE_SHIFT.search(t))
    return [t for t, _ in counts.most_common(limit)]


async def corrections_for(hits, tenant, clearance, *, search, exclude_rids=None,
                          embedding_svc=None, config=None) -> list:
    """1차 근거가 부른 이름에 대한 **정정 문서** 청크. 실패는 삼키되 조용하지 않게.

    ``search`` 는 `hybrid_search` 를 받는다 — 이 모듈이 검색 구현을 알 필요가 없고,
    테스트가 진짜 DB 없이 배선을 확인할 수 있다.
    """
    if not hits:
        return []
    seen = set(exclude_rids or ()) | {h.rid for h in hits}
    base = " ".join((getattr(h, "chunk_text", "") or "") for h in hits)
    out: list = []
    for name in names_in(base):
        try:
            found = await search(f"{name} {CHANGE_WORDS}", tenant=tenant, clearance=clearance,
                                 top_k=MAX_PER_NAME, embedding_svc=embedding_svc, config=config)
        except Exception as e:  # noqa: BLE001 — 보강 실패가 검색을 죽이면 안 된다
            logger.warning("reconcile_pass_failed", name=name, error=str(e))
            continue
        # **상한은 여기서 건다.** `top_k` 를 넘겨 두고 상대가 지키리라 믿으면, 그 약속을
        # 안 지키는 구현 하나에 근거가 통째로 부풀어 오른다. 검사가 이 자리를 잡았다.
        for h in list(found.hits)[:MAX_PER_NAME]:
            if h.rid not in seen:
                seen.add(h.rid)
                out.append(h)
    if out:
        logger.info("reconcile_pass", added=len(out), names=len(names_in(base)))
    return out


async def code_values_for(question, tenant, clearance, *, config, pool):
    """질문에 걸린 claim 의 **코드 현재값**.

    ⛔ **왜 이 배선이 필요했나 (2026-08-30).** 코드 값 해석기도, claim 표도, 전용 CLI 도
    다 있었는데 **답변 경로가 부르는 곳이 없었다**. 그래서 슬랙에서 *"파티 이름 몇 자까지"*
    를 물으면 문서만 보고 답했고, 코드가 다른 값을 갖고 있어도 화면에 나타날 길이 없었다.
    이 리포가 반복해서 데인 모양이다 — 만들어 놓고 읽는 쪽이 없다.

    **요청 경로라 트리를 훑지 않는다.** claim 이 파일을 알고 있으므로 그 파일만 읽는다
    (`resolve_at`). 전체 해석은 이 배포에서 첫 호출이 55.9초다.

    실패는 **조용히** 넘긴다 — 코드 값은 답변의 덤이지 답변의 조건이 아니다. 값이 안 나오면
    오늘과 같은 프롬프트가 나가고, 왜 안 나왔는지는 시드 보고가 말한다.
    """
    from nexus.claims.matching import claims_for_question
    from nexus.claims.repository import ClaimRepository
    from nexus.index.code_source import CodeValueResolver
    from nexus.search.evidence_packet import CodeValue

    repo_path = (config or {}).get("code_source", {}).get("repo_path", "")
    if not repo_path:
        return []
    matched = claims_for_question(
        question, await ClaimRepository(pool).find_all(tenant, clearance))
    if not matched:
        return []

    resolver = CodeValueResolver(repo_path)
    out = []
    for c in matched:
        if not (c.value_source and c.source_uri):
            continue
        r = resolver.resolve_at(c.source_uri, c.value_source)
        if not r.found:
            continue
        out.append(CodeValue(
            statement=c.statement, value=r.value or "", source=c.source_uri,
            drifted=bool(c.value_symbol_hash) and c.value_symbol_hash != r.symbol_hash))
    return out


async def packet_for_answer(result, tenant, clearance, *, config, search,
                            embedding_svc=None, question=None, pool=None):
    """**답변용 근거 패킷은 이 함수 하나로 만든다.**

    답변 경로가 셋이다(HTTP · CLI · A2A). 각자 `assemble_packet` 을 부르면, 보강을 한 곳에만
    붙이는 배선이 가능해지고 **그 조합은 검사가 초록인 채로 프로덕션에서 조용히 틀린다** —
    이 리포가 `build_prompts` 주석에 이미 적어 둔 실패다. 2026-08-29 에 내가 그대로 반복했고
    (api.py 한 곳만 배선), 그래서 여기로 모은다.

    검색만 하는 경로는 이 함수를 부르지 않는다. 정정 확인 패스의 3.5배가 거기서는 그대로
    사용자에게 보인다.
    """
    from nexus.search.evidence_packet import assemble_packet

    from nexus.search.hybrid import SearchHit, _truncate_snippet

    def _as_hit(r):
        return SearchHit(
            rid=r["rid"], doc_rid=r["doc_rid"], doc_title=r["doc_title"] or "",
            section_path=r["section_path"], source_uri=r["source_uri"],
            source_version=r["source_version"] or "",
            snippet=_truncate_snippet(r["chunk_text"], 300), chunk_text=r["chunk_text"],
            doc_n_images=r["n_images"] or 0,
            provenance_tier=r["provenance_tier"] or "authored",
            # 점수는 0 이다 — 이 청크들은 순위 경쟁을 하지 않았다.
            score=0.0, classification=r["classification"],
            approved_hash=r["approved_hash"] or "", doc_type=r["doc_type"] or "",
            updated_at=r["updated_at"], tenant=r["tenant"] or "")

    search_cfg = (config or {}).get("search", {}) or {}
    fill = list(result.fill or [])
    if search_cfg.get("reconcile_pass"):
        fill += await corrections_for(result.hits, tenant, clearance, search=search,
                                      exclude_rids={f.rid for f in fill},
                                      embedding_svc=embedding_svc, config=config)
    if search_cfg.get("pair_expansion"):
        from nexus.search.pairs import paired_chunks
        fill += [_as_hit(r) for r in await paired_chunks(
            result.hits, tenant, clearance, exclude_rids={f.rid for f in fill})]
    # `result.spans` 는 SPEC-nexus-stage-spans 캡처(기본 꺼짐, None). 여기서 넘기지 않으면
    # 답변 경로의 packet span 은 영원히 못 남는다 — 답변 경로 셋이 전부 이 함수 하나로 모이므로
    # (docstring 참조), 캡처 배선도 여기 한 곳이면 된다.
    packet = await assemble_packet(result.hits, result.graph, tenant, fill=fill,
                                   clearance=clearance, spans=getattr(result, "spans", None))
    if search_cfg.get("code_values") and question and pool is not None:
        try:
            packet.code_values = await code_values_for(
                question, tenant, clearance, config=config, pool=pool)
        except Exception:                                   # noqa: BLE001
            # 답변을 막지 않는다. 코드 값은 덤이고, 여기서 터지면 질문 전체가 죽는다.
            logger.warning("code_values_failed", tenant=tenant)
    # 이 답이 **무엇을 뒤졌는지** 패킷에 실어 보낸다. 표면마다 붙이면 하나가 조용히 빠지고,
    # 그 조합은 검사가 초록인 채로 프로덕션에서 틀린다 — 이 파일이 이미 데인 자리다(F2).
    packet.searched_tenants = [tenant] if isinstance(tenant, str) else list(tenant)
    return packet
