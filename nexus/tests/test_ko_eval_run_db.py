"""한국어 평가셋 실행 — 팩 적재 → 키워드 다리 → 바닥값 (SPEC-nexus-korean-retrieval-eval §4.5, §6).

**바닥값이 '첫 실행이 낸 값' 이면 그건 표준이 아니다.** 그래서 두 가지가 함께 있다:

- **절대 하한** — Recall@10 ≥ 0.50, 미스 ≤ 10/40. 실행이 이보다 낮으면 그건 바닥값이 아니라
  고장 신고다(색인·팩·라벨 중 하나가 틀렸다는 뜻). **그 하한이 실제로 울렸고**, 조사 결과
  키워드 다리의 동점 정렬이 비결정적이라는 사실이 나왔다 — 그래서 바닥값은 지금 **보류**다
  (`FLOORS_PENDING`).
- **음성 대조군** — 질의 조립을 역사적 결함(`AND`)으로 되돌리면 재현율이 무너져야 한다. 바닥값
  상수가 아니라 **같은 실행의 기준선**과 비교하므로, 바닥값이 보류인 지금도 이빨은 살아 있다.

이 스위트는 mecab-ko 가 있어야 의미가 있다(프로덕션 토크나이저). 없으면 공백 분리로 내려앉고,
다른 자로 잰 숫자는 바닥값이 아니다 — CI 는 이미지 안에서 돌린다.
"""

from __future__ import annotations

import copy
import os

import pytest

from scripts.ko_eval_harness import load_pack, run_keyword_leg, verdict
from scripts.ko_eval_labels import DEFAULT_LABELS, check, load
from scripts.ko_eval_pack import DEFAULT_PACK_DIR

from nexus.index.bm25 import _get_mecab

pytestmark = [
    pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요"),
    pytest.mark.skipif(_get_mecab() is None,
                       reason="mecab-ko 없음 — 프로덕션 토크나이저가 아니면 재지 않는다"),
]

_TENANT = "ko_eval"

#: **바닥값은 아직 기록하지 않는다 — 자가 흔들리기 때문이다.**
#:
#: 2026-08-03 실측(pack=ko-k8s-2026-08-01 · labels revision=1 · mecab-ko · 키워드 다리):
#: 같은 팩·같은 라벨·같은 tsvector(집계 md5 동일)인데 적재본마다 Recall@10 0.700~0.775,
#: 미스 9~12 로 갈렸다. 원인은 `_bm25_search` 의 `ORDER BY rank_score DESC` 에 **결정적 2차
#: 정렬 키가 없다**는 것이다 — `ts_rank_cd` 동점 묶음이 빽빽해서(상위 25행에 13~16종 점수),
#: 동점 안 순서가 물리적 행 순서를 따라 바뀌고, 그 순서가 LIMIT 20 경계와 문서 접기(top-10)를
#: 흔든다. 같은 질의에 같은 코퍼스인데 결과가 달라진다는 뜻이므로 평가만의 문제가 아니다.
#:
#: SPEC §4.5 는 이 상황을 위해 절대 하한을 뒀다: **하한 아래 실행은 바닥값으로 기록하지 않고
#: 조사한다.** 조사는 끝났고 원인은 위와 같다. 결정성 수정이 들어온 뒤 이 자리에 바닥값을 박고
#: 아래 두 테스트의 skip 을 걷는다.
FLOORS_PACK = "ko-k8s-2026-08-01"
FLOORS_LABEL_REVISION = 1
FLOORS_PENDING = (
    "바닥값 보류 — 키워드 다리의 동점 정렬이 비결정적이라 같은 코퍼스에서 실행마다 "
    "Recall@10 0.700~0.775 로 흔들린다(2026-08-03 실측). 결정적 2차 정렬 키가 들어온 뒤 기록한다."
)
KEYWORD_RECALL10_MIN = 0.74     # 관측 중앙값 근처. 아직 **미기록** — FLOORS_PENDING 참조.
KEYWORD_MRR10_MIN = 0.37
KEYWORD_MISSES_MAX = 10

#: 절대 하한 (§4.5). 바닥값은 이 위에 있어야 한다 — 아래면 고장이지 표준이 아니다.
SANITY_RECALL_MIN = 0.50
SANITY_MISSES_MAX = 10


@pytest.fixture(scope="module")
def labels():
    return load(DEFAULT_LABELS)


@pytest.fixture
async def corpus(db_pool):
    """팩 265문서를 버려도 되는 테넌트에 적재한다(프로덕션 청커·프로덕션 토크나이저)."""
    from nexus import db

    db._pool = db_pool
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)
        chunk_doc = await load_pack(DEFAULT_PACK_DIR, _TENANT, con)

    yield chunk_doc

    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)
    db._pool = None


# ── 측정 전에 자를 검사한다 ──────────────────────────────────────────────────


def test_the_labels_pass_their_gate_against_this_pack(labels):
    assert check(labels, DEFAULT_PACK_DIR) == []


def test_the_label_gate_fires_on_a_gold_that_is_not_in_the_pack(labels):
    """게이트가 실제로 무는지. 라벨이 틀리면 **재현율이 아니라 라벨에서** 실패해야 한다."""
    bad = copy.deepcopy(labels)
    next(q for q in bad["queries"] if q["answerable"])["gold"] = ["concepts/nope.md"]
    assert any("팩에 없는 gold" in p for p in check(bad, DEFAULT_PACK_DIR))


def test_the_floors_cite_the_label_revision_they_were_measured_on(labels):
    """라벨이 바뀌면(풀 판정으로 gold 가 늘면) 분모가 바뀐다 — 바닥값도 같은 커밋에서 다시 박는다."""
    assert labels["revision"] == FLOORS_LABEL_REVISION
    assert labels["pack"] == FLOORS_PACK


def test_the_pending_floors_would_still_sit_above_the_sanity_bound():
    """'첫 실행이 낸 값' 이 곧 표준이 되는 것을 막는 독립 하한 (§4.5).

    바닥값은 아직 기록 전이지만(FLOORS_PENDING), 후보값이 하한 아래로 내려가는 순간
    그건 바닥값이 아니라 고장 신고다 — 그 규칙은 지금도 지킨다.
    """
    assert KEYWORD_RECALL10_MIN >= SANITY_RECALL_MIN
    assert KEYWORD_MISSES_MAX <= SANITY_MISSES_MAX


# ── 코퍼스가 실제로 적재되었는가 ─────────────────────────────────────────────


async def test_the_whole_pack_is_indexed(corpus):
    from nexus import db

    docs = await db.fetch_val("SELECT count(*) FROM documents WHERE tenant=$1", _TENANT)
    chunks = await db.fetch_val(
        "SELECT count(*) FROM chunks WHERE tenant=$1 AND tsvector_ko IS NOT NULL", _TENANT)
    assert docs == 265
    assert chunks > docs, "청크가 문서 수 이하면 청킹이 안 돈 것이다"


async def test_the_corpus_is_far_larger_than_the_window(corpus):
    """5문서/창20 이면 미스는 산술적으로 불가능했다. 265문서/창10 이라야 미스가 측정이 된다."""
    assert len(set(corpus.values())) == 265


# ── 키워드 다리 ──────────────────────────────────────────────────────────────


async def test_the_keyword_leg_runs_over_the_whole_answerable_set(corpus, labels):
    """바닥값과 무관하게 항상 도는 부분 — 분모와 실행 자체."""
    leg = await run_keyword_leg(labels, _TENANT, corpus)
    assert leg.n == 40, "분모는 답변가능 40건이다 (답변불가 5건은 어떤 집계에도 안 들어간다)"
    assert 0.0 <= leg.recall <= 1.0


@pytest.mark.skip(reason=FLOORS_PENDING)
async def test_the_keyword_leg_holds_its_floors(corpus, labels):
    leg = await run_keyword_leg(labels, _TENANT, corpus)

    assert leg.recall >= KEYWORD_RECALL10_MIN, f"Recall@10 {leg.recall:.3f} < {KEYWORD_RECALL10_MIN}"
    assert leg.mrr >= KEYWORD_MRR10_MIN, f"MRR@10 {leg.mrr:.3f} < {KEYWORD_MRR10_MIN}"
    assert leg.misses <= KEYWORD_MISSES_MAX, f"미스 {leg.misses} > {KEYWORD_MISSES_MAX}"


async def test_and_semantics_collapses_recall_against_the_same_run(corpus, labels):
    """음성 대조군 — **같은 실행 안에서** OR 과 AND 를 비교한다.

    바닥값 상수에 기대면 지금은 잴 수 없다(위 skip). 하지만 이빨은 지금도 확인할 수 있다:
    같은 코퍼스·같은 적재본에서 질의 조립만 역사적 결함(`AND`)으로 되돌리면 재현율이 무너져야
    한다. 이 비교는 동점 정렬 잡음(±0.04)보다 훨씬 큰 차이를 요구하므로 흔들림에 안 걸린다.
    """
    from nexus.search import hybrid

    baseline = await run_keyword_leg(labels, _TENANT, corpus)

    original = hybrid.tokens_to_tsquery
    hybrid.tokens_to_tsquery = lambda ts: " & ".join(f"'{t}'" for t in ts if t.strip())
    try:
        sabotaged = await run_keyword_leg(labels, _TENANT, corpus)
    finally:
        hybrid.tokens_to_tsquery = original

    assert sabotaged.recall < baseline.recall * 0.6, (
        f"AND 로 되돌려도 재현율이 {sabotaged.recall:.3f} (기준 {baseline.recall:.3f}) — "
        "이 스위트는 이빨이 없다")
    assert sabotaged.misses > baseline.misses


async def test_the_verdict_rule_runs_end_to_end_on_a_real_leg(corpus, labels):
    """같은 설정끼리 비교하면 전부 무승부여야 하고, 규칙은 그것을 **검정력 부족**으로 적어야 한다."""
    leg = await run_keyword_leg(labels, _TENANT, corpus)
    from scripts.ko_eval_harness import outcomes

    wins, losses, ties = outcomes(leg.scores, leg.scores)
    assert (wins, losses) == (0, 0)
    assert ties == 40
    v = verdict(wins, losses, ties, name_a="self", name_b="self")
    assert v.underpowered and v.p is None
