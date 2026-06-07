from specledger.artifacts import Artifact, ArtifactType, Status


def test_load_reads_meta_and_body(docs_root):
    p = docs_root / "specs" / "SPEC-x.md"
    p.write_text("---\nid: SPEC-x\ntype: spec\nstatus: draft\n---\nbody\n", encoding="utf-8")
    a = Artifact.load(p)
    assert a.id == "SPEC-x"
    assert a.type == ArtifactType.SPEC
    assert a.status == Status.DRAFT
    assert a.body.strip() == "body"


def test_save_roundtrips(docs_root):
    p = docs_root / "specs" / "SPEC-y.md"
    p.write_text("---\nid: SPEC-y\ntype: spec\nstatus: draft\n---\nbody\n", encoding="utf-8")
    a = Artifact.load(p)
    a.meta["status"] = "in_review"
    a.save()
    assert Artifact.load(p).status == Status.IN_REVIEW


def test_recompute_hash_matches_hashing_module(docs_root):
    from specledger.hashing import content_hash
    p = docs_root / "specs" / "SPEC-z.md"
    p.write_text("---\nid: SPEC-z\ntype: spec\nstatus: draft\n---\nthe body\n", encoding="utf-8")
    a = Artifact.load(p)
    assert a.recompute_hash() == content_hash("the body\n")
