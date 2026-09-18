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

    async def _row_for_a(sql, *args):
        # a.md 만 이미 같은 내용·같은 라벨로 들어가 있다고 답한다.
        #
        # ⚠ **대역이 실제 호출을 그대로 받아야 한다.** 이 자리는 원래 `fetch_val` 을 물고
        # 있었는데, 수집기가 라벨까지 보게 되면서 `fetch_one` 으로 바뀌었다. 대역을 안 따라
        # 옮기면 조회가 대역을 안 타고 진짜 DB 로 가서 실패하고, 수집기의 `except: pass` 가
        # 그것을 삼켜 **모든 파일이 「바뀜」으로 나온다.** 검사가 깨져서 알았다 (2026-09-18).
        import hashlib

        from nexus.ingest.normalize import normalize_for_hash
        if not (args and str(args[0]).endswith("a.md")):
            return None
        return {
            "content_hash": hashlib.sha256(
                normalize_for_hash("본문 A").encode("utf-8")).hexdigest(),
            "labels": [],
        }

    monkeypatch.setattr(collector.db, "fetch_one", _row_for_a)
    got = asyncio.run(collector.collect_files(str(tmp_path), "**/*.md", False, "t"))

    assert got.found == 2, "패턴이 찾은 수는 루트 파일도 센다"
    assert got.changed == 1
    assert got.unchanged == 1
    assert [f.relative_path for f in got.files] == ["sub/b.md"]
