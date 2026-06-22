from ken.models import Attempt
from ken.schedule import LADDER, due, rebuild


def att(qid, passed, ts, h="sha256:cur"):
    return Attempt("kr", "a1", qid, h, passed, 1.0, ts)


def test_ladder_shape():
    assert len(LADDER) == 5


def test_pass_advances_fail_resets():
    atts = [
        att("q", True, "2026-06-01T00:00:00Z"),
        att("q", True, "2026-06-02T00:00:00Z"),
        att("q", False, "2026-06-03T00:00:00Z"),
    ]
    st = rebuild(atts, current_hashes={"q": "sha256:cur"})["q"]
    assert st.interval_idx == 0 and st.last_passed is False and st.fail_count == 1


def test_pass_advance_caps_at_last_rung():
    atts = [att("q", True, f"2026-06-0{i}T00:00:00Z") for i in range(1, 9)]
    st = rebuild(atts, current_hashes={"q": "sha256:cur"})["q"]
    assert st.interval_idx == len(LADDER) - 1


def test_next_due_is_last_ts_plus_ladder():
    atts = [att("q", True, "2026-06-01T00:00:00Z")]  # idx becomes 1 -> +1d
    states = rebuild(atts, current_hashes={"q": "sha256:cur"})
    assert "q" not in due(states, ["q"], now="2026-06-01T12:00:00Z")  # 12h < 1d
    assert "q" in due(states, ["q"], now="2026-06-03T00:00:00Z")  # >1d


def test_never_attempted_is_due():
    # a question with no state (never attempted / stale) is ALWAYS due — due owns this
    assert due({}, ["qNew"], now="2026-06-01T00:00:00Z") == ["qNew"]


def test_hash_change_resets_state():
    atts = [att("q", True, "2026-06-01T00:00:00Z", h="sha256:OLD")]
    st = rebuild(atts, current_hashes={"q": "sha256:NEW"})
    assert "q" not in st  # OLD-hash attempts ignored -> no state -> never-attempted


def test_orphan_question_ignored():
    atts = [att("gone", True, "2026-06-01T00:00:00Z")]
    assert rebuild(atts, current_hashes={"q": "sha256:cur"}) == {}  # 'gone' not in current set


def test_due_handles_naive_last_ts_vs_aware_now():
    # A hand-edited ledger line may carry a NAIVE (offset-less) last_ts. due must
    # not raise when subtracting it against an aware `now` (TypeError would poison
    # org-wide coverage) — _parse_ts coerces the naive ts to UTC. Locks that contract.
    atts = [att("q", True, "2026-06-01T00:00:00")]  # naive: no trailing Z / offset
    states = rebuild(atts, current_hashes={"q": "sha256:cur"})
    # idx advanced to 1 (+1d). 12h after the naive ts is NOT yet due.
    assert "q" not in due(states, ["q"], now="2026-06-01T12:00:00Z")
    # >1d after is due — same behaviour as the aware-ts path, no raise.
    assert "q" in due(states, ["q"], now="2026-06-03T00:00:00Z")


def test_rebuild_sorts_by_ts():
    # out-of-order ledger lines must replay in ts order
    atts = [
        att("q", False, "2026-06-03T00:00:00Z"),
        att("q", True, "2026-06-01T00:00:00Z"),
        att("q", True, "2026-06-02T00:00:00Z"),
    ]
    st = rebuild(atts, current_hashes={"q": "sha256:cur"})["q"]
    assert st.last_passed is False and st.interval_idx == 0
