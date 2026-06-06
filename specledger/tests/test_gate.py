from specledger.gate import Gate


def test_begin_sets_single_active(tmp_path):
    g = Gate(tmp_path, now=lambda: "t")
    g.begin_implementation("SPEC-a", set_by="agent")
    assert g.active_spec() == "SPEC-a"
    g.begin_implementation("SPEC-b", set_by="user")
    assert g.active_spec() == "SPEC-b"


def test_end_clears(tmp_path):
    g = Gate(tmp_path, now=lambda: "t")
    g.begin_implementation("SPEC-a", set_by="agent")
    g.end_implementation()
    assert g.active_spec() is None
