"""CodeValueResolver — 코드 상수의 *현재값*을 읽고 (상대경로+심볼) hash를 낸다.

MVP: Java `static final` 상수. 'System decides, LLM narrates' — 파싱은 결정론, LLM 미개입.
값을 복사 저장하지 않고 코드를 가리켜 조회 시점에 재읽기(anti-shelfware).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ResolvedValue:
    found: bool
    value: str | None = None
    rel_path: str | None = None
    symbol: str | None = None
    symbol_hash: str | None = None


class CodeValueResolver:
    def __init__(self, repo_path):
        self.repo_path = Path(repo_path)

    def resolve(self, source: str) -> ResolvedValue:
        # source 예: "PlaylistPolicy.ASSOCIATE_MAX_PLAYLISTS"
        _, _, symbol = source.rpartition(".")
        if not symbol:
            return ResolvedValue(found=False)
        pat = re.compile(
            r"static\s+final\s+\w+\s+" + re.escape(symbol) + r"\s*=\s*([^;]+);"
        )
        for path in self.repo_path.rglob("*.java"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            m = pat.search(text)
            if m:
                value = m.group(1).strip()
                rel = str(path.relative_to(self.repo_path)).replace("\\", "/")
                symbol_hash = hashlib.sha256(
                    (rel + "::" + symbol + "::" + m.group(0)).encode("utf-8")
                ).hexdigest()[:12]
                return ResolvedValue(True, value, rel, symbol, symbol_hash)
        return ResolvedValue(found=False)
