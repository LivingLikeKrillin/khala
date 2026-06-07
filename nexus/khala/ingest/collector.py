"""파일 수집 — glob + hash 변경 감지.

지정된 폴더에서 Markdown 파일을 수집하고, SHA-256 해시로
변경 여부를 판별한다. force=True 시 해시 무시, 전체 재인덱싱.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter
import structlog

from khala import db

logger = structlog.get_logger(__name__)


@dataclass
class CollectedFile:
    """수집된 파일 정보."""
    path: Path
    relative_path: str
    content: str
    content_hash: str
    frontmatter: dict = field(default_factory=dict)
    canonical_uri: str = ""


async def collect_files(
    docs_path: str,
    glob_pattern: str = "**/*.md",
    force: bool = False,
    tenant: str = "default",
) -> list[CollectedFile]:
    """문서 폴더에서 파일 수집. 변경된 파일만 반환 (force 시 전체)."""
    base = Path(docs_path).resolve()
    if not base.is_dir():
        raise FileNotFoundError(f"문서 경로를 찾을 수 없습니다: {docs_path}")

    collected: list[CollectedFile] = []

    for file_path in sorted(base.glob(glob_pattern)):
        if not file_path.is_file():
            continue

        try:
            raw_content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("file_read_failed", path=str(file_path), error=str(e))
            continue

        content_hash = hashlib.sha256(raw_content.encode("utf-8")).hexdigest()
        relative = str(file_path.relative_to(base)).replace("\\", "/")
        canonical_uri = f"{tenant}:{relative}"

        # frontmatter 파싱
        fm: dict = {}
        body = raw_content
        try:
            post = frontmatter.loads(raw_content)
            fm = dict(post.metadata)
            body = post.content
        except Exception:
            pass

        # hash 변경 감지 (force가 아닐 때만)
        if not force:
            try:
                existing_hash = await db.fetch_val(
                    "SELECT content_hash FROM documents WHERE source_uri = $1 AND tenant = $2 AND status = 'active'",
                    canonical_uri, tenant,
                )
                if existing_hash == content_hash:
                    logger.debug("file_unchanged", path=relative)
                    continue
            except Exception:
                pass  # DB 미연결 시 전부 수집

        collected.append(CollectedFile(
            path=file_path,
            relative_path=relative,
            content=body,
            content_hash=content_hash,
            frontmatter=fm,
            canonical_uri=canonical_uri,
        ))

    logger.info("files_collected", total=len(collected), path=str(base))
    return collected
