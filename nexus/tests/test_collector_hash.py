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
    files = asyncio.run(collect_files(str(tmp_path), force=True, tenant="t"))
    hashes = {f.relative_path: f.content_hash for f in files}
    assert hashes["a.md"] == hashes["b.md"], "frontmatter 타임스탬프·CRLF 지터는 해시를 바꾸면 안 됨"


def test_real_body_change_changes_hash(tmp_path):
    (tmp_path / "a.md").write_text("---\ntitle: X\n---\n# 제목\n\n한 줄\n", encoding="utf-8", newline="")
    (tmp_path / "c.md").write_text("---\ntitle: X\n---\n# 제목\n\n두 줄\n", encoding="utf-8", newline="")
    files = asyncio.run(collect_files(str(tmp_path), force=True, tenant="t"))
    hashes = {f.relative_path: f.content_hash for f in files}
    assert hashes["a.md"] != hashes["c.md"], "실제 body 변경은 해시가 달라야 함"
