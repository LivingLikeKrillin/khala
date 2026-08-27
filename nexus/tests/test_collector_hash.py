"""collector 가 frontmatter 제외 body 를 정규화해 content_hash 를 계산하는지(스펙 ⑥)."""
import asyncio

from nexus.ingest.collector import collect_files


def test_frontmatter_timestamp_and_crlf_jitter_do_not_change_hash(tmp_path):
    body = "# 제목\n\n결제 서비스 설명\n"
    (tmp_path / "a.md").write_text(
        "---\ntitle: X\nupdated: 2024-01-01\n---\n" + body, encoding="utf-8", newline="")
    # 같은 body, frontmatter 타임스탬프만 다르고 개행은 CRLF
    (tmp_path / "b.md").write_text(
        "---\ntitle: X\nupdated: 2025-12-31\n---\n" + body.replace("\n", "\r\n"),
        encoding="utf-8", newline="")
    files = asyncio.run(collect_files(str(tmp_path), force=True, tenant="t")).files
    hashes = {f.relative_path: f.content_hash for f in files}
    assert hashes["a.md"] == hashes["b.md"], "frontmatter 타임스탬프·CRLF 지터는 해시를 바꾸면 안 됨"


def test_real_body_change_changes_hash(tmp_path):
    (tmp_path / "a.md").write_text("---\ntitle: X\n---\n# 제목\n\n한 줄\n", encoding="utf-8", newline="")
    (tmp_path / "c.md").write_text("---\ntitle: X\n---\n# 제목\n\n두 줄\n", encoding="utf-8", newline="")
    files = asyncio.run(collect_files(str(tmp_path), force=True, tenant="t")).files
    hashes = {f.relative_path: f.content_hash for f in files}
    assert hashes["a.md"] != hashes["c.md"], "실제 body 변경은 해시가 달라야 함"


def test_the_scan_separates_not_seen_from_not_changed(tmp_path, monkeypatch):
    """⛔ 요약이 이 셋을 한 숫자로 덮으면, 안 바뀐 파일과 **못 본 파일**이 같아 보인다.
    2026-08-28 에 그 줄 하나 때문에 없는 결함(글롭이 루트를 안 잡는다)을 보고했다."""
    import asyncio

    from nexus.ingest import collector

    (tmp_path / "a.md").write_text("본문 A", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.md").write_text("본문 B", encoding="utf-8")

    async def _hash_of_a(sql, *args):
        # a.md 만 이미 같은 내용으로 들어가 있다고 답한다.
        import hashlib

        from nexus.ingest.normalize import normalize_for_hash
        return (hashlib.sha256(normalize_for_hash("본문 A").encode("utf-8")).hexdigest()
                if args and str(args[0]).endswith("a.md") else None)

    monkeypatch.setattr(collector.db, "fetch_val", _hash_of_a)
    got = asyncio.run(collector.collect_files(str(tmp_path), "**/*.md", False, "t"))

    assert got.found == 2, "패턴이 찾은 수는 루트 파일도 센다"
    assert got.changed == 1
    assert got.unchanged == 1
    assert [f.relative_path for f in got.files] == ["sub/b.md"]
