"""멀티턴 스레드 평가 하니스 — 커밋된 평가 하니스가 스스로 성립하는지 지킨다 (SPEC-nexus-multi-turn-retrieval §3.4).

`multiturn-threads.yaml` 은 리포에 들어간다. 코퍼스도 gold 도 이미 리포에 있으므로 누구나
재현할 수 있고, 그 말은 **검사가 사람의 기억을 대신할 수 있다**는 뜻이다.

여기서 지키는 것은 DB 없이 확인 가능한 것뿐이다. 실제 수(실험군 넷의 Recall/MRR)는
`scripts/ko_eval_multiturn.py` 가 측정하고, 그 실행은 자기 대조군으로 스스로를 검사한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ko_eval_labels import load  # noqa: E402
from scripts.ko_eval_multiturn import (  # noqa: E402
    ARMS,
    arm_queries,
    control_failures,
    gate_reasons,
    summarise,
)

THREADS = ROOT / "tests" / "eval" / "ko" / "multiturn-threads.yaml"
LABELS = ROOT / "tests" / "eval" / "ko" / "answer-labels.yaml"


@pytest.fixture(scope="module")
def threads():
    return yaml.safe_load(THREADS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def labels():
    return load(LABELS)


# ── 평가 하니스가 자기 라벨과 맞물리는가 ────────────────────────────────────────────────

def test_the_thread_file_passes_its_own_gate(threads, labels):
    assert gate_reasons(threads, labels) == []


def test_every_thread_points_at_an_answerable_labelled_query(threads, labels):
    by_id = {q["id"]: q for q in labels["queries"]}
    for t in threads["threads"]:
        q = by_id[t["qid"]]
        assert q["answerable"] and q["gold"], f"{t['qid']}: 채점할 gold 가 없다"


def test_gold_is_inherited_never_re_authored(threads):
    """스레드 파일은 gold 를 갖지 않는다 — 가지는 순간 두 번째 평가 하니스가 생기고, 둘은 갈라진다.

    같은 이유로 이 리포는 등급 목록과 채점 규칙의 사본을 없앤 적이 있다
    (memory: suspect-the-instrument-first §2026-08-12~13, 사본은 고치지 말고 없애라).
    """
    for t in threads["threads"]:
        assert set(t) == {"qid", "turn1", "turn2"}, f"{t['qid']}: 스레드에 gold 를 적지 마라"


# ── 평가 하니스가 측정하려는 것을 실제로 측정하는가 ─────────────────────────────────────────────

def test_the_follow_up_drops_something_the_query_had(threads, labels):
    """turn2 는 원 질의에서 **무언가를 떨어뜨려야** 한다. 안 그러면 생략형 실험군 = 독립형 팔이다.

    판정 규칙을 고르는 데 두 번 실패했다. "가장 긴 토큰이 주제어" 는 q011 에서 어미 덩어리
    (`업데이트하려면`)를 주제어로 골랐고, "turn2 가 더 짧다" 는 대화체 어미가 길이를 늘리는
    q014·q024 에서 깨졌다. 둘 다 데이터가 아니라 **계측기**가 틀린 것이었다
    (memory: suspect-the-instrument-first).

    그래서 형태소에 기대지 않는 규칙만 남긴다: 원 질의의 공백 토큰 중 최소 하나가 turn2 에
    없다. 무엇이 빠졌는지까지는 말하지 않지만, **빠졌다는 것**은 확실히 말한다.
    """
    by_id = {q["id"]: q for q in labels["queries"]}
    for t in threads["threads"]:
        query = by_id[t["qid"]]["query"]
        dropped = [tok for tok in query.split() if tok not in t["turn2"]]
        assert dropped, f"{t['qid']}: turn2 가 원 질의의 모든 토큰을 갖고 있다 — 생략형이 아니다"
        assert t["turn2"].strip() != query.strip()


def test_the_leading_turn_is_not_the_answer(threads, labels):
    """turn1 은 주제를 세우는 앞턴이지 정답 질의가 아니다 — 원 질의를 그대로 쓰면 실험군이 무의미하다."""
    by_id = {q["id"]: q for q in labels["queries"]}
    for t in threads["threads"]:
        assert t["turn1"].strip() != by_id[t["qid"]]["query"].strip()


def test_every_arm_is_assembled_in_one_place(threads, labels):
    """실험군 넷의 검색어는 한 함수에서만 나온다. 정의가 갈라지면 그것은 비교가 아니다."""
    by_id = {q["id"]: q for q in labels["queries"]}
    t = threads["threads"][0]
    q = by_id[t["qid"]]
    got = arm_queries(t, q["query"], threads["drift_turn"])
    assert set(got) == set(ARMS)
    assert got["standalone"] == q["query"]
    assert got["elliptical"] == t["turn2"]
    assert got["concat"] == f"{t['turn1']} {t['turn2']}"
    # 판정 실험군은 앞 화제를 **앞에** 붙인다 — 그것이 재작성이 이겨야 할 조건이다.
    assert got["drift_concat"].startswith(threads["drift_turn"])
    assert got["concat"] in got["drift_concat"]


# ── 집계가 거짓말하지 않는가 ───────────────────────────────────────────────────

def test_mrr_counts_the_misses_as_zero():
    """못 찾은 질의를 빼고 평균 내면 **적게 찾을수록 좋아 보인다.** 그 평가 하니스는 거꾸로 간다."""
    rows = [
        {a: {"hits": 1, "rank": 1} for a in ARMS},
        {a: {"hits": 0, "rank": None} for a in ARMS},
    ]
    s = summarise(rows)
    assert s["standalone"] == {"found": 1, "mrr": 0.5}


def test_the_control_arm_gates_the_run():
    """독립형이 베이스라인을 재현하지 못하면 그 실행은 결과가 아니다 — 계측기를 먼저 의심하라."""
    base = {"standalone": {"found": 24, "mrr": 0.938}}
    ok = {"standalone": {"found": 24, "mrr": 0.938}}
    assert control_failures(ok, base, 24) == []

    for broken in ({"found": 23, "mrr": 0.938}, {"found": 24, "mrr": 0.900}):
        assert control_failures({"standalone": broken}, base, 24), f"{broken} 를 통과시켰다"


def test_the_committed_baseline_is_the_one_the_runner_checks(threads):
    """베이스라인은 스레드 파일에 산다 — 실행기에 하드코딩하면 평가 하니스를 고치는 사람이 못 본다."""
    base = threads["baseline"]
    assert set(ARMS) <= set(base)
    for arm in ARMS:
        assert set(base[arm]) == {"found", "mrr"}
    # 기록된 격차가 이 평가 하니스의 존재 이유다. 사라지면 SPEC 을 다시 읽어야 한다.
    assert base["standalone"]["found"] > base["elliptical"]["found"]
    # 그리고 싸구려 하한은 판정 실험군에서 무너진다 — 그래서 재작성을 측정하는 것이다.
    assert base["drift_concat"]["mrr"] < base["concat"]["mrr"]
