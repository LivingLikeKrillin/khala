"""검색 품질 신호 추출(순수) + 영속(best-effort IO).

extract_signals는 SearchResult/AnswerResult에서 신호를 조립하는 순수 함수,
record_search는 structlog(항상) + best-effort DB insert(절대 raise 안 함)다.
a2a/audit.py의 record_audit 패턴을 미러링한다. 원문 query는 sha256+len으로만 기록.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from nexus import db

if TYPE_CHECKING:  # 런타임 import 불필요(순환 회피) — 속성 접근만 한다
    from nexus.llm.answer import AnswerResult
    from nexus.search.hybrid import SearchResult

log = structlog.get_logger("nexus.search.signals")


def _answer_prompt_sha() -> str:
    """지연 import — 프롬프트 모듈을 신호 모듈이 무조건 끌고 오지 않게."""
    from nexus.llm.prompt_version import answer_prompt_sha

    return answer_prompt_sha()


def _rewrite_prompt_sha() -> str:
    from nexus.llm.prompt_version import rewrite_prompt_sha

    return rewrite_prompt_sha()

SIGNAL_EVENT = "search.signal"
# Must stay in sync with route values produced by nexus/search/router.py / hybrid_search `route_used`.
_GRAPH_ROUTES = ("hybrid_then_graph", "graph_then_hybrid")

# Strong references to fire-and-forget tasks — prevents CPython GC from collecting them before completion.
_background_tasks: set = set()


def query_sha256(query: str) -> str:
    """원문 query의 sha256 hex — 신호에 들어갈 수 있는 유일한 형태."""
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SearchSignals:
    path: str
    tenant: str | None
    clearance: str | None
    route: str
    query_sha256: str
    query_len: int
    n_snippets: int
    top_score: float | None
    n_entities: int
    graph_requested: bool
    n_graph_edges: int
    no_answer: bool
    llm_failed: bool
    latency_ms: int
    #: 재작성 흔적 (SPEC §3.5, U4). **텍스트는 없다** — 재작성문은 원 질문보다 민감하다
    #: (§3.2 항목 3 이 이력의 사실을 일부러 채워 넣는다). 해시·길이·바뀌었는가로 탐지한다.
    rewrite_applied: bool = False
    rephrased_sha256: str = ""
    rephrased_len: int = 0
    rewrite_changed: bool = False
    #: 재작성 호출의 비용 — **답변 비용과 다른 칸**이다. 같은 칸에 접으면
    #: `budget.py::measured_averages` 의 "답변 1회 비용" 이 조용히 편향된다. None = 미측정.
    rewrite_prompt_tokens: int | None = None
    rewrite_completion_tokens: int | None = None
    rewrite_cost_usd: float | None = None
    #: 어떤 프롬프트가 이 답을 만들었는가. 값은 프롬프트 **텍스트에서 파생**되므로 사람이
    #: 올릴 것이 없다(nexus/llm/prompt_version.py). 빈 문자열 = 그 프롬프트를 안 썼다.
    answer_prompt_sha: str = ""
    rewrite_prompt_sha: str = ""
    #: 융합에 쓰인 채널 수 (SPEC §4 I6). 1 = 단일 채널(= U3 이전의 모든 행). 채널이 늘면
    #: RRF 점수의 **절대값이 팽창**한다 — 순서는 그대로지만 `top_score` 의 크기가 달라지므로,
    #: 절대 임계값을 쓰는 쪽이 세대를 구분할 수 있어야 한다.
    fusion_channels: int = 1
    # 인용 지표(SPEC-nexus-search-signal-completeness). None = 미측정(답변 없는 경로) ≠ 0(측정된 0건).
    n_citations: int | None = None
    unverified_citations: int | None = None
    # LLM 토큰/비용(SPEC-nexus-llm-usage-persistence). None = 미측정/미가격 ≠ 0. cost 있으면 토큰도 있음.
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    #: 근거가 **얼마나 잘 맞았는가**의 크기 (`search/confidence.py`). RRF 가 지워 버리는 값이라
    #: 다리에서 되살려 여기까지 들고 온다. **불리언(`weak`)을 남기지 않는다** — 그 값은 오늘의
    #: 문턱으로 계산된 것이고, 문턱을 옮기면 지나간 행의 뜻이 조용히 바뀐다. 거리와 점수는
    #: 문턱과 무관한 사실이다. 지금 문턱은 지어낸 질문 17개에서 나왔고, 다시 잴 재료는
    #: **실사용 질문**뿐인데 그것이 매 요청마다 버려지고 있었다.
    #: None = 그 다리가 안 돌았다(못 잼) ≠ 0(재서 낮음).
    top_distance: float | None = None
    top_bm25: float | None = None
    #: 근거가 나온 문서 중 그림을 가진 것의 수 (migration 011). ADR-0002 가 요구하는 게이트
    #: 형식 — "관측된 기록된 비율이 설정 임계를 롤링 윈도에서 넘을 때" — 의 관측 쪽이다.
    #: **기능이 아니라 세는 일이다.** 이 값으로 무엇을 짓지 않는다.
    n_image_bearing_docs: int = 0


def extract_signals(
    result: SearchResult,
    answer: AnswerResult | None = None,
    *,
    path: str,
    tenant: str | None,
    clearance: str | None,
    query: str,
    n_entities: int = 0,
    fusion_channels: int = 1,
    rewrite=None,
    latency_ms: int = 0,
    n_citations: int | None = None,
    unverified_citations: int | None = None,
    llm_failed: bool | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    cost_usd: float | None = None,
) -> SearchSignals:
    """SearchResult(+선택 AnswerResult)와 진입점 스칼라에서 신호를 조립. 순수.

    인용 지표(n_citations/unverified_citations)와 llm_failed 는 명시 인자가 우선, 없으면
    AnswerResult 에서 유도, 그것도 없으면 None/False(미측정). 스트림은 answer 없이 명시로 넘긴다.
    """
    hits = result.hits
    graph = result.graph
    n_graph_edges = (len(graph.edges) + len(graph.observed_edges)) if graph else 0
    route = result.route_used or ""
    n_cit = n_citations if n_citations is not None else (
        len(getattr(answer, "citations", []) or []) if answer is not None else None)
    unver = unverified_citations if unverified_citations is not None else (
        getattr(answer, "unverified_citations", None) if answer is not None else None)
    failed = llm_failed if llm_failed is not None else (
        bool(answer.llm_failed) if answer is not None else False)
    # usage 3개는 각각 독립: 명시 인자 우선, 없으면 answer.usage(dict)에서 .get 유도, 없으면 None.
    _usage = getattr(answer, "usage", None) if answer is not None else None
    ptok = prompt_tokens if prompt_tokens is not None else (
        _usage.get("input_tokens") if _usage else None)
    ctok = completion_tokens if completion_tokens is not None else (
        _usage.get("output_tokens") if _usage else None)
    cost = cost_usd if cost_usd is not None else (
        _usage.get("cost_usd") if _usage else None)
    return SearchSignals(
        path=path,
        tenant=tenant,
        clearance=clearance,
        route=route,
        query_sha256=query_sha256(query),
        query_len=len(query),
        n_snippets=len(hits),
        top_score=hits[0].score if hits else None,
        # `SearchResult` 는 늘 `confidence` 를 갖지만(기본 팩토리), 이 함수는 덕타이핑 더블도
        # 받는다. getattr 로 없는 경우를 None 으로 접는다 — 신호 하나가 신호 전체를 죽이면 안 된다.
        top_distance=getattr(getattr(result, "confidence", None), "top_distance", None),
        top_bm25=getattr(getattr(result, "confidence", None), "top_bm25", None),
        n_entities=n_entities,
        graph_requested=route in _GRAPH_ROUTES,
        n_graph_edges=n_graph_edges,
        no_answer=len(hits) == 0,
        fusion_channels=fusion_channels,
        # 답변 경로에서만 답변 프롬프트를 쓴다. 검색 전용 경로에 그 지문을 적으면 거짓이다.
        answer_prompt_sha=_answer_prompt_sha() if answer is not None else "",
        rewrite_prompt_sha=_rewrite_prompt_sha() if (rewrite and rewrite.called) else "",
        rewrite_applied=bool(rewrite and rewrite.called),
        rephrased_sha256=rewrite.sha256 if (rewrite and rewrite.changed) else "",
        rephrased_len=len(rewrite.query) if (rewrite and rewrite.changed) else 0,
        rewrite_changed=bool(rewrite and rewrite.changed),
        rewrite_prompt_tokens=getattr(getattr(rewrite, "usage", None), "input_tokens", None),
        rewrite_completion_tokens=getattr(getattr(rewrite, "usage", None), "output_tokens", None),
        rewrite_cost_usd=getattr(getattr(rewrite, "usage", None), "cost_usd", None),
        # 근거가 그림 있는 문서에서 왔는가 — 게이트 신호원(migration 011). 문서 단위로 센다:
        # 같은 문서에서 스니펫이 셋 와도 "그림 있는 문서 하나" 다.
        n_image_bearing_docs=len({h.doc_rid for h in hits if getattr(h, "doc_n_images", 0) > 0}),
        llm_failed=failed,
        latency_ms=latency_ms,
        n_citations=n_cit,
        unverified_citations=unver,
        prompt_tokens=ptok,
        completion_tokens=ctok,
        cost_usd=cost,
    )


#: 좌초(stranded) 문턱 — **고정 상수**다. `2 × NEXUS_SUFFICIENCY_TIMEOUT` 처럼 조정 가능한 값에서
#: 유도하면 운영자가 timeout 을 바꾸는 순간 **과거 행이 전부 재분류된다**. UPDATE 의 가드도 같은
#: 상수를 쓴다: 좌초로 선언된 행을 뒤늦게 도착한 판정이 되살리면 "재시도 없음" 은 문장일 뿐이다.
STRANDED_SECONDS = 300

#: 판정 호출이 이 상수의 절반을 넘으면 정상 완료가 좌초로 읽힐 수 있다. 그 설정을 만들 수 없게 막는다.
_MAX_TIMEOUT_SECONDS = STRANDED_SECONDS // 2

_inflight = 0


@dataclass(frozen=True)
class JudgeInput:
    """판정자에게만 가는 호출 범위 값. **`SearchSignals` 에 절대 넣지 않는다.**

    `search_log` 는 원문 질의를 담은 적이 없고(init.sql, 원칙 #3) 이 SPEC 도 담지 않는다. 신호
    객체에 텍스트 필드를 하나라도 만들면 그 불변식은 관례가 되고, 관례는 다음 컬럼에서 깨진다.
    그래서 질의·근거는 인자로만 흐르고 `_persist` 가 끝나면 닿을 수 없다.
    """
    query: str
    evidence: str
    config: dict | None = None
    llm_svc: object | None = None


def _enabled_for(tenant: str | None) -> bool:
    """이 배포·이 tenant 에서 판정자가 켜져 있는가. **기본 off.**

    켜는 것은 원문 질의와 근거 텍스트가 공급자로 나가는 것을 받아들이는 행위다. 그리고 그 결정은
    배포 단위가 아니라 **코퍼스 단위**여야 한다 — 한 배포가 여러 tenant 를 담으므로 전역 플래그
    하나면 한 사람이 모두를 대신 결정하게 된다. 목록에 없으면 꺼진 것이고 `*` 는 없다.
    """
    if (os.getenv("NEXUS_SUFFICIENCY") or "off").strip().lower() != "on":
        return False
    allow = {t.strip() for t in (os.getenv("NEXUS_SUFFICIENCY_TENANTS") or "").split(",") if t.strip()}
    return bool(tenant) and tenant in allow


def evidence_fingerprint(config: dict | None) -> str:
    """검색 스택 설정의 sha256 앞 8자.

    판정의 분리 가능성은 **검색 스택의 성질**이다. 임베딩 컷오버나 mecab→nori 교체를 사이에 둔
    창은 서로 다른 두 측정을 한 이름으로 평균낸다. 임베딩 컬럼은 env 오버라이드가 있으므로
    설정 파일 텍스트가 아니라 `configured_column()` 에서 읽는다 — 파일을 읽으면 컷오버한 배포에서
    틀린 세대를 적는다.
    """
    from nexus.index.bm25 import active_tokenizer
    from nexus.index.vector_index import configured_column

    cfg = (config or {}).get("search") or {}
    parts = [
        configured_column(config),
        str(((config or {}).get("embedding") or {}).get("model", "")),
        type(active_tokenizer()).__name__,
        str(cfg.get("bm25_top_k", 20)), str(cfg.get("vector_top_k", 20)),
        str(cfg.get("rrf_k", 60)), str(cfg.get("snippet_max_chars", 300)),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:8]


def _eligibility(sig: SearchSignals, ji: JudgeInput | None) -> tuple[str | None, str, str | None]:
    """(종결값 | None, judge_id, fingerprint). None = 판정을 시도해도 된다.

    **한 곳에서만 판단한다.** 진입점 5곳이 각자 정하면 같은 배포 상태가 경로마다 다른 값으로
    저장되고, 그러면 시계열이 조용히 갈라진다.
    """
    if ji is None:                       # 답변을 시도하지 않은 검색 행 — 판정할 대상이 없다
        return "not_applicable", "off", None
    if not _enabled_for(sig.tenant):
        return "disabled", "off", None
    from nexus.llm.sufficiency import judge_identity
    return None, judge_identity(ji.llm_svc), evidence_fingerprint(ji.config)


def _try_take_slot() -> bool:
    """상한 안이면 슬롯을 잡는다. **검사와 증가 사이에 `await` 가 없다** → 단일 이벤트 루프에서
    race 가 성립하지 않는다.

    `asyncio.Semaphore` 를 안 쓰는 이유는 비차단 acquire 가 없기 때문이다. `locked()` 로 보고
    `await acquire()` 하는 것은 check-then-act 라, 상한 1 에서도 둘이 통과할 수 있다.
    """
    global _inflight
    cap = max(1, int(os.getenv("NEXUS_SUFFICIENCY_CONCURRENCY") or 2))
    if _inflight >= cap:
        return False
    _inflight += 1
    return True


def _release_slot() -> None:
    global _inflight
    _inflight = max(0, _inflight - 1)


async def _judge_with_timeout(ji: JudgeInput) -> str:
    """판정 1회 → 저장할 값. 예외를 값으로 바꾼다.

    timeout 은 **답변 지연을 막으려는 것이 아니다**(판정은 이미 요청 경로 밖이다). 슬롯을
    돌려받기 위한 것이다 — 안 그러면 멈춘 호출 하나가 슬롯을 영원히 물고, 기본 상한 2 에서 두
    개면 이후 모든 요청이 `shed` 로 굳는다.
    """
    from nexus.llm.sufficiency import Sufficiency, judge_raw

    timeout = float(os.getenv("NEXUS_SUFFICIENCY_TIMEOUT") or 30)
    if timeout > _MAX_TIMEOUT_SECONDS:
        # 판정이 좌초 문턱보다 오래 살면 정상 완료가 좌초로 읽히고 UPDATE 가드에 걸려 버려진다.
        raise ValueError(
            f"NEXUS_SUFFICIENCY_TIMEOUT={timeout}s 는 상한 {_MAX_TIMEOUT_SECONDS}s 를 넘는다 "
            f"(좌초 문턱 {STRANDED_SECONDS}s 의 절반).")
    try:
        v = await asyncio.wait_for(judge_raw(ji.query, ji.evidence, ji.llm_svc), timeout)
    except (TimeoutError, asyncio.TimeoutError):
        return "timeout"
    except Exception as exc:  # noqa: BLE001 — 부르지도 못한 것과 이상한 답을 낸 것은 다른 사실이다
        log.warning("search.signal.judge_error", error=str(exc))
        return "error"
    return (v.label.value if v.label in (Sufficiency.SUFFICIENT, Sufficiency.INSUFFICIENT)
            else "unparseable")


async def _insert(sig: SearchSignals, sufficiency: str | None,
                  judge: str | None, fingerprint: str | None) -> int | None:
    """search_log에 1행 insert. **id 를 돌려준다** — 판정 UPDATE 가 기본키로만 겨눌 수 있게.

    이 테이블에 다른 유일키는 없다. 비유일 튜플로 매칭해 판정을 찍으면 엉뚱한 행에 조용히
    도장을 찍는다.
    """
    return await db.fetch_val(
        """
        INSERT INTO search_log (
            path, tenant, clearance, route, query_sha256, query_len,
            n_snippets, top_score, n_entities, graph_requested, n_graph_edges,
            no_answer, llm_failed, latency_ms, n_citations, unverified_citations,
            prompt_tokens, completion_tokens, cost_usd, n_image_bearing_docs,
            sufficiency, sufficiency_at, sufficiency_judge, evidence_fingerprint,
            fusion_channels,
            rewrite_applied, rephrased_sha256, rephrased_len, rewrite_changed,
            rewrite_prompt_tokens, rewrite_completion_tokens, rewrite_cost_usd,
            answer_prompt_sha, rewrite_prompt_sha,
            top_distance, top_bm25
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,
                  $21, now(), $22, $23, $24, $25, $26, $27, $28, $29, $30, $31, $32, $33,
                  $34, $35)
        RETURNING id
        """,
        sig.path, sig.tenant, sig.clearance, sig.route, sig.query_sha256, sig.query_len,
        sig.n_snippets, sig.top_score, sig.n_entities, sig.graph_requested,
        sig.n_graph_edges, sig.no_answer, sig.llm_failed, sig.latency_ms,
        sig.n_citations, sig.unverified_citations,
        sig.prompt_tokens, sig.completion_tokens, sig.cost_usd,
        sig.n_image_bearing_docs,
        sufficiency, judge, fingerprint, sig.fusion_channels,
        sig.rewrite_applied, sig.rephrased_sha256, sig.rephrased_len, sig.rewrite_changed,
        sig.rewrite_prompt_tokens, sig.rewrite_completion_tokens, sig.rewrite_cost_usd,
        sig.answer_prompt_sha, sig.rewrite_prompt_sha,
        sig.top_distance, sig.top_bm25,
    )


async def _persist(sig: SearchSignals, judge_input: JudgeInput | None = None,
                   query_text: str | None = None,
                   principal: str | None = None,
                   rewritten_text: str | None = None) -> None:
    """search_log에 1행 insert(+선택적 충분성 판정). 실패는 삼킴.

    두 개의 지역 try/except 가 있고 **둘 다 필요하다**:

    * **프롤로그** (적격성·지문 계산·슬롯) — 여기서 터지면 바깥 핸들러가 `_persist` 를 통째로
      중단시켜 **search_log 행 자체가 사라진다**. v_search_health·v_image_gap_signal 이 같이
      망가진다. 그래서 프롤로그 실패는 `uninstrumented` 로 적고 나머지 신호는 그대로 넣는다:
      계측기가 고장 나면 아무것도 기록 안 할 뿐, 신호를 같이 끌고 내려가지 않는다.
    * **판정 호출** — 여기서 터지면 UPDATE 를 건너뛰어 행이 영원히 `pending` 에 남는다.
      `error`/`timeout` 이 도달 가능한 것은 이 핸들러 덕이다.
    """
    # 질문 보존은 **옵트인한 테넌트에서만** 일어나고, 어느 경우에도 raise 하지 않는다
    # (SPEC-nexus-query-text-retention §3.5). search_log 쓰기보다 먼저 두는 이유는 없다 —
    # 뒤에 두면 신호 적재가 실패했을 때 보존도 같이 사라지고, 둘은 독립이어야 한다.
    from nexus.search.query_retention import retain
    await retain(sig.tenant, query_text, principal)
    # 재작성문도 **같은 동의 범위·같은 만료**로 간다(SPEC §3.5). 다만 `kind` 로 갈라 둔다 —
    # 이 테이블의 존재 이유는 실사용 질문을 모으는 것이고, 기계가 쓴 문장이 구분 없이 섞이면
    # 그 코퍼스로 만든 평가셋이 자기 재작성기를 채점하게 된다.
    if rewritten_text:
        await retain(sig.tenant, rewritten_text, principal, kind="rewritten")

    sufficiency, judge_id, fingerprint, took_slot = "uninstrumented", "off", None, False
    try:
        terminal, judge_id, fingerprint = _eligibility(sig, judge_input)
        # 슬롯 획득은 **프롤로그의 마지막 문장**이다. 앞에 두면 지문 계산이 터졌을 때 슬롯이
        # 샌다 — 기본 상한 2 에서 두 번 새면 이후 모든 검색이 조용히 `shed` 로 굳는다.
        if terminal is not None:
            sufficiency = terminal
        elif _try_take_slot():
            sufficiency, took_slot = "pending", True
        else:
            sufficiency = "shed"
    except Exception as exc:  # noqa: BLE001 - 계측기 고장이 신호를 끌고 내려가면 안 된다
        log.warning("search.signal.sufficiency_prologue_failed", error=str(exc))
        sufficiency, judge_id, fingerprint = "uninstrumented", "off", None

    row_id = None
    try:
        row_id = await _insert(sig, sufficiency, judge_id, fingerprint)
    except Exception as exc:  # noqa: BLE001 - signal persistence must never break the request
        log.warning("search.signal.persist_failed", error=str(exc))

    if not took_slot:
        return
    try:
        if row_id is None:                      # 행이 없으면 찍을 곳도 없다
            return
        assert judge_input is not None
        verdict = await _judge_with_timeout(judge_input)
        await db.execute(
            """
            UPDATE search_log SET sufficiency = $1
             WHERE id = $2 AND sufficiency = 'pending'
               AND sufficiency_at > now() - make_interval(secs => $3)
            """,
            verdict, row_id, float(STRANDED_SECONDS),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("search.signal.sufficiency_failed", error=str(exc), row_id=row_id)
    finally:
        _release_slot()


async def record_search(sig: SearchSignals, *, await_persist: bool = False,
                        judge_input: JudgeInput | None = None,
                        query_text: str | None = None,
                        principal: str | None = None,
                        rewritten_text: str | None = None) -> None:
    """structlog(항상, 동기) + best-effort DB 적재. 절대 raise 안 함.

    서버 경로(api/a2a)는 기본 fire-and-forget(create_task) — 응답 지연에 DB 쓰기 미가산.
    CLI는 await_persist=True — asyncio.run 종료/close_pool 이전에 적재 완료 보장.

    `query_text` 는 **`SearchSignals` 에 넣지 않는다.** 그 객체는 통째로 로그 한 줄이 되고,
    보존은 옵트인한 테넌트의 DB 행에서만 일어나야 한다(SPEC-nexus-query-text-retention §3.2).
    필드로 두면 옵트인하지 않은 배포의 로그 파일에 질문이 남는다.
    """
    log.info(
        SIGNAL_EVENT,
        path=sig.path, tenant=sig.tenant, clearance=sig.clearance, route=sig.route,
        query_sha256=sig.query_sha256, query_len=sig.query_len,
        n_snippets=sig.n_snippets, top_score=sig.top_score, n_entities=sig.n_entities,
        graph_requested=sig.graph_requested, n_graph_edges=sig.n_graph_edges,
        no_answer=sig.no_answer, llm_failed=sig.llm_failed, latency_ms=sig.latency_ms,
        n_citations=sig.n_citations, unverified_citations=sig.unverified_citations,
        prompt_tokens=sig.prompt_tokens, completion_tokens=sig.completion_tokens,
        cost_usd=sig.cost_usd,
    )
    if not db.has_pool():
        return
    if await_persist:
        await _persist(sig, judge_input, query_text, principal, rewritten_text)
    else:
        # Retain a strong reference so the task isn't GC'd before completion (stdlib-recommended pattern).
        task = asyncio.create_task(_persist(sig, judge_input, query_text, principal, rewritten_text))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
