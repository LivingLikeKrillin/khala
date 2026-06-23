from ken.models import Vouch


def test_vouch_roundtrip():
    v = Vouch(
        artifact_id="a1",
        person="kr",
        content_hash="sha256:x",
        score=0.9,
        passed=True,
        n_questions=5,
        ts="2026-06-23T00:00:00Z",
    )
    assert Vouch.from_dict(v.to_dict()) == v
