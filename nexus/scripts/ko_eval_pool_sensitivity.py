"""How far the deferred pool adjudication could move the KURE verdict.

`SPEC-nexus-ko-eval-pool-sensitivity`. The deferral was defended with an argument — unjudged
documents count as non-relevant and the winner absorbs more of that penalty, so the gap is
"conservative against the conclusion". That counts the term that widens the margin and omits the one
that reverses it. This computes the omitted term.

Three moves are available to an adversary who gets to choose which pooled candidates turn out to be
relevant, costed per query by exhaustive subset search:

* **flip**   — smallest `S` making `(Recall@10, MRR@10)` strictly better for the challenger;
* **tie**    — smallest `S` making the pair exactly equal. Applies to **wins only**: a win→tie
               deletes a discordant pair, and on this data it is cheaper than flipping on 17 of 27;
* **removal** — one refused-chunk document, which takes the query out of the comparable subset
               (§4.7's rule, a property of the *document*, not of its class).

A dynamic program over the `(W, L)` states then minimises total cost subject to `p > 0.05` **or**
`W + L < MIN_DISCORDANT` — the "underpowered" route defeats the claim just as a large p does.

The unit throughout is the **(query, document) pair**: relevance is judged per query, so a document
pooled for seven queries is seven judgements, not one.
"""

from __future__ import annotations

import argparse
import itertools
import json
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ko_eval_harness import MIN_DISCORDANT, sign_test_p  # noqa: E402

MAX_SUBSET = 4
EVAL_KO = Path(__file__).resolve().parents[1] / "tests" / "eval" / "ko"


def score(ranked_docs: list[str], gold: set[str]) -> tuple[float, float]:
    """`(Recall@10, MRR@10)` for one arm — the pair the verdict rule compares, in that order."""
    hits = [d for d in ranked_docs if d in gold]
    rr = 1.0 / (ranked_docs.index(hits[0]) + 1) if hits else 0.0
    return len(hits) / len(gold), rr


@dataclass
class QueryMoves:
    qid: str
    outcome: str                      # "win" | "loss" | "tie" — for the incumbent's challenger
    flip: int | None = None
    tie: int | None = None
    removal: int | None = None
    candidates: int = 0
    unreachable: list[str] = field(default_factory=list)


def cost_moves(qid: str, gold: set[str], champion: list[str], challenger: list[str],
               candidates: list[str], refused_docs: set[str],
               max_subset: int = MAX_SUBSET) -> QueryMoves:
    """Cost the three moves for one query.

    `champion` is the arm currently ahead (KURE in the shipped comparison); `challenger` is the one
    an adversary wants to lift. A subset that includes a refused-chunk document *removes* the query
    rather than flipping it, so flip/tie search over the candidates that are not refused documents.
    """
    a, b = score(champion, gold), score(challenger, gold)
    outcome = "win" if a > b else ("loss" if a < b else "tie")
    m = QueryMoves(qid=qid, outcome=outcome, candidates=len(candidates))
    m.removal = 1 if (set(candidates) & refused_docs) else None

    pool = [c for c in candidates if c not in refused_docs]
    for k in range(1, max_subset + 1):
        for s in itertools.combinations(pool, k):
            g = gold | set(s)
            ax, bx = score(champion, g), score(challenger, g)
            if m.flip is None and bx > ax:
                m.flip = k
            # a tie move only means something on a query the champion currently wins
            if m.tie is None and outcome == "win" and bx == ax:
                m.tie = k
        if m.flip is not None and (m.tie is not None or outcome != "win"):
            break

    if m.flip is None:
        m.unreachable.append("flip")
    if outcome == "win" and m.tie is None:
        m.unreachable.append("tie")
    return m


def minimum_cost(moves: list[QueryMoves]) -> tuple[int, int, int] | None:
    """Cheapest defeat as `(cost, W, L)`, or None if no combination defeats the verdict.

    A move the search could not reach within `MAX_SUBSET` is **not available** — treating it as
    cheap would understate the adversary's price, which is the unsafe direction.
    """
    w0 = sum(1 for m in moves if m.outcome == "win")
    l0 = sum(1 for m in moves if m.outcome == "loss")
    best: dict[tuple[int, int], int] = {(w0, l0): 0}

    for m in moves:
        nxt: dict[tuple[int, int], int] = {}
        for (w, lost), c in best.items():
            options = [(w, lost, c)]
            if m.flip is not None:
                options.append((w - 1 if m.outcome == "win" else w, lost + 1, c + m.flip))
            if m.tie is not None and m.outcome == "win":
                options.append((w - 1, lost, c + m.tie))
            if m.removal is not None:
                options.append((w - 1 if m.outcome == "win" else w,
                                lost - 1 if m.outcome == "loss" else lost, c + m.removal))
            for w2, l2, c2 in options:
                if nxt.get((w2, l2), 1 << 30) > c2:
                    nxt[(w2, l2)] = c2
        best = nxt

    defeats = [(c, w, losses) for (w, losses), c in best.items()
               if (w + losses) < MIN_DISCORDANT or sign_test_p(w, losses) > 0.05]
    return min(defeats) if defeats else None


def concentration(moves_by_query: dict[str, QueryMoves],
                  cheap_pairs: dict[str, set[str]]) -> list[tuple[int, str]]:
    """Documents ranked by how many queries they buy a cost-1 move on.

    Concentration is real and does not purchase safety: removing the most concentrated documents
    leaves the minimum where it was, because the bench of cost-1 documents is deep. Measured, not
    assumed — see the SPEC §4 table.
    """
    return sorted(((len(qs), doc) for doc, qs in cheap_pairs.items()), reverse=True)


def draw_sample(pairs: list[tuple[str, str]], seed: int, n: int) -> list[tuple[str, str]]:
    """The base-rate sample. `Random.sample` is an implementation detail, so the runtime is pinned
    in the artifact and a test asserts this reproduces the committed list."""
    return random.Random(seed).sample(pairs, n)


def population(labels: dict, pool: list[dict], refused_docs: set[str]) -> list[tuple[str, str]]:
    """`(query_id, document)` pairs over the comparable subset, in a fixed order."""
    by_id = {q["id"]: q for q in pool}
    out: list[tuple[str, str]] = []
    for q in labels["queries"]:
        if not q.get("answerable") or (set(q["gold"]) & refused_docs):
            continue
        for doc in by_id[q["id"]]["candidates"]:
            out.append((q["id"], doc))
    return out


def load_refused_docs(path: Path | None = None) -> set[str]:
    p = path or (EVAL_KO / "refused-chunk-docs.json")
    return set(json.loads(p.read_text(encoding="utf-8"))["documents"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", action="store_true", help="redraw the base-rate sample and print it")
    ap.add_argument("--seed", type=int, default=20260805)
    ap.add_argument("--n", type=int, default=30)
    args = ap.parse_args(argv)

    import yaml

    labels = yaml.safe_load((EVAL_KO / "labels.yaml").read_text(encoding="utf-8"))
    pool = json.loads((EVAL_KO / "pool-blind.json").read_text(encoding="utf-8"))
    pairs = population(labels, pool, load_refused_docs())

    if args.sample:
        for i, (qid, doc) in enumerate(draw_sample(pairs, args.seed, args.n), 1):
            print(f"{i:2}. [{qid}] {doc}")
        return 0

    print(f"population: {len(pairs)} (query, document) pairs over the comparable subset")
    print("costing the three moves needs both arms in ko_eval_embeddings; run the store-dependent")
    print("half of the suite where that store exists (SPEC §7).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
