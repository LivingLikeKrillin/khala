"""한국어 평가 코퍼스 팩 — 규칙·정규화·매니페스트 (SPEC-nexus-korean-retrieval-eval §4.1, §6).

**팩이 흔들리면 그 위의 모든 숫자가 무의미하다.** 그래서 여기서 지키는 건 세 가지다:
선택 규칙이 결정적인가 · 정규화가 플랫폼과 무관하게 같은 바이트를 내는가 · 커밋된 팩이
커밋된 매니페스트와 일치하는가.

NFD/NFC 테스트가 특히 값비싼 자리다. 한글은 플랫폼을 오가며 두 형태로 표현되는데, 둘은
해시가 다를 뿐 아니라 **형태소 분해도 다르다** — 정규화를 안 하면 OS 가 측정 대상을 흔든다.
"""

from __future__ import annotations

import json
import unicodedata

import pytest

from scripts.ko_eval_pack import (
    DEFAULT_PACK_DIR,
    MAX_BYTES,
    MIN_BYTES,
    build,
    normalize,
    pack_relative,
    select_tree,
    selects,
    strip_front_matter,
    strip_shortcodes,
    verify,
)

# ── 선택 규칙 ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("path", "size", "expected"),
    [
        ("content/ko/docs/concepts/x.md", 5000, True),
        ("content/ko/docs/tasks/a/b.md", MIN_BYTES, True),        # 경계 포함
        ("content/ko/docs/tasks/a/b.md", MAX_BYTES, True),        # 경계 포함
        ("content/ko/docs/tasks/a/b.md", MIN_BYTES - 1, False),
        ("content/ko/docs/tasks/a/b.md", MAX_BYTES + 1, False),
        ("content/ko/docs/concepts/_index.md", 5000, False),      # 스텁 제외
        ("content/ko/docs/reference/x.md", 5000, False),          # 섹션 밖
        ("content/en/docs/concepts/x.md", 5000, False),           # 영어
        ("content/ko/docs/concepts/x.png", 5000, False),          # md 아님
    ],
)
def test_selection_rule(path, size, expected):
    assert selects(path, size) is expected


def test_select_tree_sorts_and_ignores_non_blobs():
    tree = [
        {"type": "blob", "path": "content/ko/docs/tasks/b.md", "size": 3000, "sha": "b"},
        {"type": "tree", "path": "content/ko/docs/tasks", "size": 0, "sha": "t"},
        {"type": "blob", "path": "content/ko/docs/concepts/a.md", "size": 3000, "sha": "a"},
    ]
    assert [e["path"] for e in select_tree(tree)] == [
        "content/ko/docs/concepts/a.md", "content/ko/docs/tasks/b.md"]


def test_pack_relative_strips_the_prefix():
    assert pack_relative("content/ko/docs/concepts/a/b.md") == "concepts/a/b.md"


# ── 정규화 ────────────────────────────────────────────────────────────────────


def test_front_matter_removed_and_title_kept_as_heading():
    out = strip_front_matter("---\ntitle: 파드 개요\nweight: 10\n---\n본문\n")
    assert out == "# 파드 개요\n\n본문\n"


def test_front_matter_without_title_just_disappears():
    assert strip_front_matter("---\nweight: 10\n---\n본문\n") == "본문\n"


def test_text_attribute_survives_the_shortcode():
    """`text=` 를 버리면 외래어 층이 재려는 어휘 자체가 사라진다 (SPEC §4.1 규칙 1)."""
    assert strip_shortcodes('{{< glossary_tooltip text="파드" term_id="pod" >}}는 최소 단위다') \
        == "파드는 최소 단위다"


def test_paired_tags_keep_their_content():
    assert strip_shortcodes("{{< note >}}\n주의할 점\n{{< /note >}}").strip() == "주의할 점"


def test_text_attribute_wins_inside_a_paired_block():
    out = strip_shortcodes('{{% note %}}{{< glossary_tooltip text="노드" term_id="node" >}} 참고{{% /note %}}')
    assert out.strip() == "노드 참고"


def test_percent_form_behaves_like_the_angle_form():
    assert strip_shortcodes("{{% heading whatsnext %}}남는다") == "남는다"


def test_other_tags_leave_no_marker():
    assert strip_shortcodes('앞 {{< codenew file="pod.yaml" >}} 뒤') == "앞  뒤"


def test_nfd_and_nfc_inputs_produce_identical_bytes():
    nfc = "# 파드\n\n스테이트풀셋\n"
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfd != nfc                                    # 입력은 다르고
    assert normalize(nfd) == normalize(nfc)              # 결과는 같아야 한다
    assert normalize(nfd) == unicodedata.normalize("NFC", nfc)


def test_normalize_handles_crlf_comments_and_trailing_space():
    out = normalize("---\r\ntitle: T\r\n---\r\n<!-- 숨김 -->본문   \r\n\r\n\r\n")
    assert "\r" not in out
    assert "숨김" not in out
    assert out == "# T\n\n본문\n"


def test_normalize_is_idempotent():
    once = normalize("---\ntitle: T\n---\n본문 {{< note >}}주의{{< /note >}}\n")
    assert normalize(once) == once


# ── 빌드·매니페스트·검증 (네트워크 없이) ─────────────────────────────────────


@pytest.fixture
def fake_pack(tmp_path):
    """트리와 blob 을 주입해 빌드한다 — 네트워크 없이 전 경로를 돈다."""
    tree = [
        {"type": "blob", "path": "content/ko/docs/concepts/a.md", "size": 3000, "sha": "sha-a"},
        {"type": "blob", "path": "content/ko/docs/tasks/b/c.md", "size": 4000, "sha": "sha-c"},
        {"type": "blob", "path": "content/ko/docs/concepts/_index.md", "size": 3000, "sha": "skip"},
    ]
    bodies = {
        "content/ko/docs/concepts/a.md": "---\ntitle: 파드\n---\n본문 A\n",
        "content/ko/docs/tasks/b/c.md": '{{< glossary_tooltip text="노드" term_id="node" >}} 본문 C\n',
    }
    manifest = build(tmp_path, tree=tree, fetch=lambda p: bodies[p].encode("utf-8"), workers=2)
    return tmp_path, manifest


def test_build_writes_only_selected_documents(fake_pack):
    pack_dir, manifest = fake_pack
    assert manifest["count"] == 2
    assert [d["path"] for d in manifest["documents"]] == ["concepts/a.md", "tasks/b/c.md"]
    assert (pack_dir / "docs" / "concepts" / "a.md").read_text(encoding="utf-8") == "# 파드\n\n본문 A\n"
    assert (pack_dir / "docs" / "tasks" / "b" / "c.md").read_text(encoding="utf-8") == "노드 본문 C\n"


def test_build_records_upstream_and_totals(fake_pack):
    _, manifest = fake_pack
    assert manifest["upstream"]["sha"]
    assert manifest["bytes_total"] == sum(d["bytes"] for d in manifest["documents"])
    assert manifest["documents"][0]["blob_sha1"] == "sha-a"


def test_fresh_pack_verifies(fake_pack):
    pack_dir, _ = fake_pack
    assert verify(pack_dir) == []


def test_a_mutated_file_fails_verification(fake_pack):
    pack_dir, _ = fake_pack
    f = pack_dir / "docs" / "concepts" / "a.md"
    f.write_text(f.read_text(encoding="utf-8") + "몰래 한 줄\n", encoding="utf-8")
    assert any("해시 불일치" in p for p in verify(pack_dir))


def test_a_missing_file_fails_verification(fake_pack):
    pack_dir, _ = fake_pack
    (pack_dir / "docs" / "concepts" / "a.md").unlink()
    assert any("누락" in p for p in verify(pack_dir))


def test_an_extra_file_fails_verification(fake_pack):
    pack_dir, _ = fake_pack
    (pack_dir / "docs" / "concepts" / "sneaky.md").write_text("끼워넣기\n", encoding="utf-8")
    assert any("매니페스트에 없는" in p for p in verify(pack_dir))


def test_a_wrong_count_fails_verification(fake_pack):
    pack_dir, _ = fake_pack
    mpath = pack_dir / "manifest.json"
    m = json.loads(mpath.read_text(encoding="utf-8"))
    m["count"] = 99
    mpath.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    assert any("count" in p for p in verify(pack_dir))


def test_missing_manifest_is_not_silently_ok(tmp_path):
    assert verify(tmp_path) == [f"매니페스트 없음: {tmp_path / 'manifest.json'}"]


# ── 커밋된 팩 (오프라인) ──────────────────────────────────────────────────────


def test_the_committed_pack_verifies():
    """리포에 있는 실제 팩. 이게 깨지면 그 위의 모든 측정이 무효다."""
    assert verify(DEFAULT_PACK_DIR) == []


def test_the_committed_pack_is_the_size_the_spec_says():
    manifest = json.loads((DEFAULT_PACK_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["count"] == 265
    assert manifest["pack"] == "ko-k8s-2026-08-01"


def test_the_committed_pack_carries_no_shortcodes_or_comments():
    for f in (DEFAULT_PACK_DIR / "docs").rglob("*.md"):
        text = f.read_text(encoding="utf-8")
        assert "{{<" not in text and "{{%" not in text, f
        assert "<!--" not in text, f


def test_the_committed_pack_is_nfc():
    for f in (DEFAULT_PACK_DIR / "docs").rglob("*.md"):
        text = f.read_text(encoding="utf-8")
        assert text == unicodedata.normalize("NFC", text), f
