"""코드 심볼 인덱스 — tree-sitter 로 Java 를 읽어 (이름, 위치, span_hash) 를 남긴다.

SPEC-nexus-doc-code-anchors §3.1. 여기에 LLM 은 없다. 전부 파스 결과이므로 틀린 값은
확률이 아니라 버그다.

⚠ **코드 본문을 반환하지도 저장하지도 않는다.** `SymbolRow` 에 소스 텍스트 필드가 없는 것은
   실수가 아니라 계약이다. 해시는 변경 감지에 충분하고 원문은 체크아웃에 있다. 디버깅이
   편하다는 이유로 스니펫 필드를 더하는 순간, 이 인덱스는 대상 저장소의 소스를 담기 시작한다.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import structlog
import tree_sitter_java
from tree_sitter import Language, Parser

logger = structlog.get_logger(__name__)

_JAVA = Language(tree_sitter_java.language())

#: 앵커가 걸릴 만한 선언만. 지역 변수·파라미터는 문서가 부르지 않는다.
_DECLS: dict[str, str] = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "record_declaration": "record",
    "annotation_type_declaration": "annotation",
    "method_declaration": "method",
    "constructor_declaration": "constructor",
}


@dataclass(frozen=True)
class SymbolRow:
    """한 심볼. **소스 텍스트 필드는 의도적으로 없다** (모듈 docstring 참조)."""

    file_path: str
    symbol_kind: str
    symbol_name: str
    start_line: int
    end_line: int
    span_hash: str


def normalize_span(text: str) -> str:
    """`span_hash` 를 계산하기 전의 정규화. 이 함수가 규칙의 정본이다 (SPEC §3.1).

    - 줄바꿈을 `\\n` 으로 통일 — 없으면 Windows 체크아웃에서 CRLF 하나로 전 앵커가 뒤집힌다.
    - 행말 공백 제거 — 편집기가 남기는 잡음이지 변경이 아니다.
    - 앞뒤 빈 줄 제거.

    주석과 어노테이션은 **포함한다**. 계약을 서술하는 주석이 바뀌는 것은 진짜 신호다.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).strip("\n")


def span_hash(text: str) -> str:
    return hashlib.sha256(normalize_span(text).encode("utf-8")).hexdigest()


def _name_of(node) -> str | None:
    n = node.child_by_field_name("name")
    return n.text.decode("utf-8", "ignore") if n is not None else None


def extract_symbols(source: str, file_path: str) -> list[SymbolRow]:
    """한 파일의 심볼. 파스 실패는 예외가 아니라 빈 목록 — 호출자가 미파싱으로 센다."""
    parser = Parser(_JAVA)
    src = source.encode("utf-8")
    tree = parser.parse(src)

    rows: list[SymbolRow] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        kind = _DECLS.get(node.type)
        if kind:
            name = _name_of(node)
            if name:
                body = src[node.start_byte : node.end_byte].decode("utf-8", "ignore")
                rows.append(
                    SymbolRow(
                        file_path=file_path,
                        symbol_kind=kind,
                        symbol_name=name,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        span_hash=span_hash(body),
                    )
                )
        stack.extend(node.children)
    return rows


@dataclass(frozen=True)
class ScanResult:
    symbols: list[SymbolRow]
    unparsed_files: int
    scanned_files: int


def scan_repo(repo_path: Path) -> ScanResult:
    """저장소의 `*.java` 를 훑는다. 미파싱 파일 수를 함께 돌려준다 — 커버리지를 비율로만
    보고하면 거짓이 되므로 분모가 필요하다 (SPEC §6.6)."""
    symbols: list[SymbolRow] = []
    unparsed = 0
    scanned = 0

    for path in sorted(repo_path.rglob("*.java")):
        rel = path.relative_to(repo_path).as_posix()
        scanned += 1
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            unparsed += 1
            # 파일 경로는 대상 저장소의 내용이다. 로그에 남기되 본문은 절대 남기지 않는다.
            logger.warning("code_scan_unreadable", file=rel, error=type(e).__name__)
            continue

        found = extract_symbols(source, rel)
        if not found:
            unparsed += 1
        symbols.extend(found)

    return ScanResult(symbols=symbols, unparsed_files=unparsed, scanned_files=scanned)
