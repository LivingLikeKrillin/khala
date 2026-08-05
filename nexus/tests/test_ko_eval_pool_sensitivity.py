"""SPEC-nexus-ko-eval-pool-sensitivity §7.

The two figures the SPEC rests on — the minimum of 10 and the concentration curve — were computed on
2026-08-05 from an eval store that no longer exists. So the coverage here is split, and the split is
the point:

* **hand-built ledgers** pin the costing rules and the DP. They do not depend on any store, and they
  are what would catch a change in the arithmetic.
* **the committed sample** pins that the draw reproduces from committed files alone.
* **the store-dependent half** recomputes costs from `ko_eval_embeddings` when both arms are present.
  It is skipped otherwise, and the skip is reported, so "it passed" and "it did not run" stay
  distinguishable.
"""

from __future__ import annotations

import json
import os


import pytest
import yaml

from scripts.ko_eval_pool_sensitivity import (
    EVAL_KO,
    MAX_SUBSET,
    QueryMoves,
    cost_moves,
    draw_sample,
    load_refused_docs,
    minimum_cost,
    population,
    score,
)

REFUSED = {"refused-doc.md"}


def _moves(gold, champion, challenger, candidates, refused=REFUSED, qid="q"):
    return cost_moves(qid, set(gold), champion, challenger, candidates, refused)


# ── the costing rules ────────────────────────────────────────────────────────


def test_a_recall_decided_win_needs_two_relevant_documents_to_flip():
    """Champion holds the only gold document. One new gold ties the recall; two wins it."""
    m = _moves(["g.md"], ["g.md", "x.md"], ["a.md", "b.md"], ["a.md", "b.md", "c.md"])
    assert m.outcome == "win"
    assert m.flip == 2


def test_a_win_decided_by_mrr_on_equal_recall_flips_on_one():
    """Both arms hold the gold document, the champion ranks it first. Recall ties, MRR decides — so
    a single relevant document on the challenger's side turns it into a recall loss.

    This is why `m* = a - b + 1` is the wrong formula: it only describes the recall-decided case.
    """
    m = _moves(["g.md"], ["g.md", "x.md"], ["y.md", "g.md"], ["y.md", "z.md"])
    assert m.outcome == "win"
    assert m.flip == 1


def test_an_exact_tie_is_not_a_win_and_carries_no_tie_move():
    """A tie move on an already-tied query buys nothing, so it must not be costed as available."""
    # different rankings, same (recall, rr): both hold the gold document first
    m = _moves(["g.md"], ["g.md", "x.md"], ["g.md", "a.md"], ["a.md", "b.md"])
    assert m.outcome == "tie"
    assert m.tie is None
    assert m.flip == 1, "one relevant document the challenger holds and the champion does not"


def test_identical_rankings_can_never_be_flipped():
    """Nothing distinguishes two arms that returned the same list, at any adjudication. The move is
    unavailable, not expensive - and the DP must be told the difference."""
    m = _moves(["g.md"], ["g.md", "x.md"], ["g.md", "x.md"], ["a.md", "b.md"])
    assert m.outcome == "tie"
    assert m.flip is None and "flip" in m.unreachable


def test_the_tie_move_can_be_strictly_cheaper_than_the_flip():
    """On the real data this held for 17 of 27 wins, and omitting the move understated the
    adversary's options — an upper bound on their price presented as a lower bound."""
    # champion holds both gold documents; the challenger holds three candidates and no gold.
    # recall(champ) = 2/(2+k), recall(chall) = k/(2+k): equal at k=2, ahead at k=3.
    m = _moves(["g1.md", "g2.md"], ["g1.md", "g2.md"], ["a.md", "b.md", "c.md"],
               ["a.md", "b.md", "c.md", "d.md"])
    assert m.outcome == "win"
    assert m.tie == 2 and m.flip == 3
    assert m.tie < m.flip


def test_a_refused_chunk_document_is_a_removal_not_a_flip():
    """§4.7's comparable subset is defined by the document, so a newly relevant refused-chunk
    document takes the query out of the test rather than reversing it. Flip search must exclude it."""
    m = _moves(["g.md"], ["g.md"], ["a.md"], ["refused-doc.md", "a.md"])
    assert m.removal == 1
    # the flip cost must be computed without the refused document
    assert m.flip == _moves(["g.md"], ["g.md"], ["a.md"], ["a.md"]).flip


def test_a_move_beyond_the_search_cap_is_unavailable_not_cheap():
    """Scoring an unreachable move as available would understate the price. It is recorded."""
    gold = ["g.md"]
    champion = ["g.md"]
    challenger = ["z.md"]
    candidates = [f"c{i}.md" for i in range(8)]
    m = _moves(gold, champion, challenger, candidates)
    # champion holds the gold and the challenger holds none of the candidates it would need
    assert m.flip is None or m.flip <= MAX_SUBSET
    if m.flip is None:
        assert "flip" in m.unreachable


# ── the dynamic program ──────────────────────────────────────────────────────


def _ledger(wins: int, losses: int = 0, ties: int = 0, flip: int = 1,
            tie: int | None = None, removal: int | None = None) -> list[QueryMoves]:
    out = [QueryMoves(f"w{i}", "win", flip=flip, tie=tie, removal=removal) for i in range(wins)]
    out += [QueryMoves(f"l{i}", "loss", flip=flip) for i in range(losses)]
    out += [QueryMoves(f"t{i}", "tie", flip=flip) for i in range(ties)]
    return out


def test_the_dp_finds_the_hand_computed_minimum():
    """27 W / 1 L / 8 T, every move at cost 1: flipping wins is the strongest per-unit move, and
    two-sided exact p first exceeds 0.05 at 19 W / 9 L — eight flips."""
    got = minimum_cost(_ledger(27, 1, 8, flip=1))
    assert got is not None
    cost, w, ell = got
    assert cost == 8 and (w, ell) == (19, 9)


def test_the_underpowered_route_counts_as_a_defeat():
    """Removals delete discordant pairs. Below MIN_DISCORDANT the rule returns 'underpowered', which
    defeats the confirmatory claim as surely as a large p — an earlier design granted only flips and
    therefore did not dominate this."""
    moves = _ledger(6, 0, 0, flip=9, removal=1)   # flipping is expensive, removing is not
    got = minimum_cost(moves)
    assert got is not None
    cost, w, ell = got
    assert w + ell < 6, "the defeat is by pair count, not by p"
    assert cost == 1, "at exactly MIN_DISCORDANT, one removal is enough"


def test_an_unreachable_move_is_not_used_by_the_dp():
    reachable = minimum_cost(_ledger(27, 1, 8, flip=1))
    unreachable = minimum_cost([QueryMoves(m.qid, m.outcome, flip=None)
                                for m in _ledger(27, 1, 8)])
    assert reachable is not None
    assert unreachable is None, "with no move available the verdict cannot be defeated"


def test_a_verdict_with_no_available_move_is_reported_as_undefeatable():
    """With no move anywhere the verdict stands - but only if it was powered to begin with. A
    ledger below MIN_DISCORDANT is already 'underpowered' and needs no adversary at all, which the
    DP reports at cost 0."""
    assert minimum_cost(_ledger(27, 1, 8, flip=None)) is None
    already = minimum_cost([QueryMoves("w0", "win")])
    assert already == (0, 1, 0), "one discordant pair is underpowered before anyone touches it"


# ── the sample, reproducible from committed files alone ──────────────────────


def test_the_committed_sample_reproduces_from_the_seed():
    """§A.1's procedure. If a future CPython changes `Random.sample` this fails, and the recorded
    list — not the algorithm — is what the sample was."""
    artifact = json.loads((EVAL_KO / "pool-sensitivity-sample.json").read_text(encoding="utf-8"))
    labels = yaml.safe_load((EVAL_KO / "labels.yaml").read_text(encoding="utf-8"))
    pool = json.loads((EVAL_KO / "pool-blind.json").read_text(encoding="utf-8"))

    pairs = population(labels, pool, load_refused_docs())
    assert len(pairs) == artifact["population"]["pairs"]

    drawn = draw_sample(pairs, artifact["draw"]["seed"], artifact["draw"]["n"])
    recorded = [(j["qid"], j["document"]) for j in artifact["judgements"]]
    assert drawn == recorded


def test_the_sample_is_not_consumable_as_gold():
    """`ko_eval_labels.load()` refuses `kind: sensitivity`. A cheap backstop, not a proof of
    non-consumption — the artifact is JSON and the gold set is YAML, so a misuse may never traverse
    that loader at all. The load-bearing separations are the filename, the schema and this test."""
    artifact = json.loads((EVAL_KO / "pool-sensitivity-sample.json").read_text(encoding="utf-8"))
    assert artifact["kind"] == "sensitivity"


def test_every_judgement_carries_a_proposer_and_a_distinct_reviewer():
    artifact = json.loads((EVAL_KO / "pool-sensitivity-sample.json").read_text(encoding="utf-8"))
    for j in artifact["judgements"]:
        assert j["proposed_by"] and j["reviewed_by"], j
        assert j["proposed_by"] != j["reviewed_by"], j
        assert j["basis"].strip(), j


def test_a_disagreement_is_recorded_as_disputed_and_reported_both_ways():
    """§4.1: a disputed pair is counted non-relevant in the actual reading and relevant in the
    safety reading, and both are reported rather than resolved by fiat."""
    artifact = json.loads((EVAL_KO / "pool-sensitivity-sample.json").read_text(encoding="utf-8"))
    disputed = [j for j in artifact["judgements"] if j.get("disputed")]
    assert len(disputed) == artifact["result"]["disputed"]
    assert (artifact["result"]["relevant_safety"]
            == artifact["result"]["relevant_actual"] + len(disputed))


def test_the_refused_document_list_covers_the_recorded_count():
    docs = json.loads((EVAL_KO / "refused-chunk-docs.json").read_text(encoding="utf-8"))
    assert len(docs["documents"]) == 9
    assert docs["derived_from"]["refused_chunks"] == 10, "10 chunks over 9 documents"


# ── the store-dependent half ─────────────────────────────────────────────────


_STORE_URL = os.getenv("NEXUS_TEST_DB_URL")


@pytest.mark.integration
@pytest.mark.skipif(not _STORE_URL, reason="no database: the store-dependent half did not run")
@pytest.mark.asyncio
async def test_costs_recompute_from_the_store_when_both_arms_are_present(db_url):
    """Recompute the move costs from `ko_eval_embeddings` and check them against the committed
    per-query record. Skipped — and reported as skipped — while the store lacks an arm, which is its
    state since 2026-08-05 (KOREAN_SEARCH_QUALITY.md §6, eval store loss)."""
    import asyncpg

    conn = await asyncpg.connect(db_url)
    try:
        rows = await conn.fetch(
            "SELECT model, count(*) FROM ko_eval_embeddings WHERE tenant='ko_eval_embed' "
            "GROUP BY model")
    except asyncpg.UndefinedTableError:
        pytest.skip("eval store table absent: the store-dependent half did not run")
    finally:
        await conn.close()

    arms = {r["model"] for r in rows}
    if {"nomic-embed-text", "KURE-v1"} - arms:
        pytest.skip(f"eval store holds only {sorted(arms) or 'no'} arm(s): "
                    "the store-dependent half did not run")

    pytest.fail("both arms are present - wire the recompute in and pin it against the record")


def test_score_matches_the_harness_definition():
    """Recall@10 over gold, MRR from the first hit — the pair the verdict rule compares."""
    assert score(["a.md", "g.md"], {"g.md"}) == (1.0, 0.5)
    assert score(["x.md"], {"g.md"}) == (0.0, 0.0)
    assert score(["g1.md", "g2.md"], {"g1.md", "g2.md"}) == (1.0, 1.0)


# ── separating costing from judging (debt I-010) ─────────────────────────────

_COST_FIELDS = ("flip", "tie", "removal", "cost", "m_star", "decisive", "concentration",
                "outcome", "win", "loss")


def test_the_judging_input_carries_no_cost_information():
    """I-010: on the 2026-08-05 sample the same actor computed the move costs and proposed the
    judgements, with no held-out artifact between them. That cannot be undone for a sample already
    taken; it can be made unrepeatable.

    The judging input is the blind pool. It must carry the query, its candidates and nothing that
    reveals which candidates buy a move - otherwise a judge learns which pairs matter while judging
    them, which is the correlation that biases a base-rate estimate in either direction.
    """
    pool = json.loads((EVAL_KO / "pool-blind.json").read_text(encoding="utf-8"))
    for q in pool:
        assert set(q) <= {"id", "query", "stratum", "gold", "candidates"}, q["id"]
        for field_name in _COST_FIELDS:
            assert field_name not in q, f"{q['id']} leaks {field_name} into the judging input"


def test_the_sample_artifact_records_who_proposed_and_who_reviewed_separately():
    """The record has to make the correlation visible even where it could not be removed."""
    artifact = json.loads((EVAL_KO / "pool-sensitivity-sample.json").read_text(encoding="utf-8"))
    for j in artifact["judgements"]:
        assert "proposed_by" in j and "reviewed_by" in j
        for field_name in _COST_FIELDS:
            assert field_name not in j, f"pair {j['n']} carries {field_name} beside its judgement"


def test_a_future_sample_cannot_be_drawn_from_a_cost_ranked_population():
    """The draw is over the population in labels/pool file order, never in cost order - the ordering
    §4.3 forbids, and the one an earlier protocol draft mandated in the same document."""
    labels = yaml.safe_load((EVAL_KO / "labels.yaml").read_text(encoding="utf-8"))
    pool = json.loads((EVAL_KO / "pool-blind.json").read_text(encoding="utf-8"))
    pairs = population(labels, pool, load_refused_docs())

    order = [qid for qid, _ in pairs]
    expected = [q["id"] for q in labels["queries"]
                if q.get("answerable") and not (set(q["gold"]) & load_refused_docs())]
    assert [k for i, k in enumerate(order) if i == 0 or order[i - 1] != k] == expected
