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

from nexus import db
from nexus.ingest.normalize import normalize_for_hash

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
    #: 이 본문의 비전 마커를 **우리가 썼는가.** 기본 False — 마커는 그냥 문자열이고 저자
    #: 문서에도 들어 있을 수 있다. 비전 블록을 직접 써 넣은 경로만 True 로 올린다.
    #: 이것이 False 이면 청킹 직전에 마커가 제거되어, 남의 문서가 자기 산문을 machine_read 로
    #: 찍게 만들 수 없다 (ADR-0010 §3, SPEC §4.3).
    vision_extracted: bool = False


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

        relative = str(file_path.relative_to(base)).replace("\\", "/")
        canonical_uri = f"{tenant}:{relative}"

        # frontmatter 파싱 (해시 전에 body 확보)
        fm: dict = {}
        body = raw_content
        try:
            post = frontmatter.loads(raw_content)
            fm = dict(post.metadata)
            body = post.content
        except Exception:
            pass

        # 변경감지 해시 = frontmatter 제외 body 를 정규화한 것 (스펙 ⑥)
        content_hash = hashlib.sha256(
            normalize_for_hash(body).encode("utf-8")
        ).hexdigest()

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
