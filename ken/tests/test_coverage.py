from ken.coverage import compute_coverage
from ken.models import ArtifactRef, Vouch


def test_coverage_counts_only_fresh():
    arts = [ArtifactRef("a1", "/a", "sha256:cur"), ArtifactRef("a2", "/b", "sha256:cur2")]
    vouches = [
        Vouch("a1", "kr", "sha256:cur", 0.9, True, 5, "2026-06-23T00:00:00Z"),
        Vouch("a2", "kr", "sha256:OLD", 0.9, True, 5, "2026-06-23T00:00:00Z"),  # stale: hash differs
    ]
    rep = compute_coverage(arts, vouches, now="2026-06-23T01:00:00Z", ttl_days=90)
    assert rep.total == 2 and rep.covered == 1
    assert rep.orphans == ["a2"] and abs(rep.ratio - 0.5) < 1e-9


def test_empty_registry_is_full_coverage_or_zero():
    rep = compute_coverage([], [], now="2026-06-23T00:00:00Z", ttl_days=90)
    assert rep.total == 0 and rep.orphans == []
