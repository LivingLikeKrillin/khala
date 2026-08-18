"""코드 심볼 인덱스 — tree-sitter 로 Java 를 읽어 (이름, 위치, span_hash) 를 남긴다.

SPEC-nexus-doc-code-anchors §3.1. 여기에 LLM 은 없다. 전부 파스 결과이므로 틀린 값은
확률이 아니라 버그다.

⚠ **코드 본문을 반환하지도 저장하지도 않는다.** `SymbolRow` 에 소스 텍스트 필드가 없는 것은
   실수가 아니라 계약이다. 해시는 변경 감지에 충분하고 원문은 체크아웃에 있다. 디버깅이
   편하다는 이유로 스니펫 필드를 더하는 순간, 이 인덱스는 대상 저장소의 소스를 담기 시작한다.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import structlog
import tree_sitter_java
import tree_sitter_python
from tree_sitter import Language, Parser

logger = structlog.get_logger(__name__)

_JAVA = Language(tree_sitter_java.language())
_PYTHON = Language(tree_sitter_python.language())

#: 앵커가 걸릴 만한 선언만. 지역 변수·파라미터는 문서가 부르지 않는다.
_JAVA_DECLS: dict[str, str] = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "record_declaration": "record",
    "annotation_type_declaration": "annotation",
    "method_declaration": "method",
    "constructor_declaration": "constructor",
}

_PYTHON_DECLS: dict[str, str] = {
    "class_definition": "class",
    "function_definition": "function",
}


@dataclass(frozen=True)
class _Grammar:
    language: Language
    decls: dict[str, str]


#: 확장자 → 문법. 여기 없는 확장자는 스캔 대상이 아니다 — 파서 없는 언어를 세면
#: 미파싱 분모가 "언어를 지원하지 않는다" 와 "파스에 실패했다" 를 섞어버린다.
GRAMMARS: dict[str, _Grammar] = {
    ".java": _Grammar(_JAVA, _JAVA_DECLS),
    ".py": _Grammar(_PYTHON, _PYTHON_DECLS),
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
    """한 파일의 심볼. 파스 실패는 예외가 아니라 빈 목록 — 호출자가 미파싱으로 센다.

    문법은 확장자로 고른다. 모르는 확장자는 빈 목록이다.
    """
    grammar = GRAMMARS.get(Path(file_path).suffix.lower())
    if grammar is None:
        return []

    parser = Parser(grammar.language)
    src = source.encode("utf-8")
    tree = parser.parse(src)

    rows: list[SymbolRow] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        kind = grammar.decls.get(node.type)
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


#: 스캔에서 뺄 경로 조각. 없으면 벤더 디렉터리 하나가 인덱스를 남의 코드로 뒤덮고,
#: 그러면 유일 해소가 무너져 전부 ambiguous 거부가 된다.
_SKIP_PARTS = frozenset({
    "node_modules", ".venv", "venv", "site-packages", "build", "dist", "target",
    "__pycache__", ".git", ".tox", ".mypy_cache", "migrations",
})


def _skip(rel_path: str) -> bool:
    return any(part in _SKIP_PARTS for part in rel_path.split("/"))


#: `import a.b.C;` 의 `C`. 저장소가 **선언하지 않고 빌려 쓰는** 이름을 알아내는 데 쓴다.
_JAVA_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)\s*;", re.M)
#: `from a.b import C` / `import a.b as C`
_PY_IMPORT = re.compile(r"^\s*(?:from\s+[\w.]+\s+import\s+([\w, ]+)|import\s+([\w.]+))", re.M)


def imported_names(source: str, suffix: str) -> set[str]:
    """이 파일이 **밖에서 들여온** 이름들. 선언이 아니라 차용이다."""
    out: set[str] = set()
    if suffix == ".java":
        for path in _JAVA_IMPORT.findall(source):
            last = path.rsplit(".", 1)[-1]
            if last and last != "*":
                out.add(last)
    elif suffix == ".py":
        for names, mod in _PY_IMPORT.findall(source):
            if names:
                out |= {n.strip() for n in names.split(",") if n.strip()}
            elif mod:
                out.add(mod.rsplit(".", 1)[-1])
    return out


@dataclass(frozen=True)
class ScanResult:
    symbols: list[SymbolRow]
    #: **읽지 못한 파일** — 인덱스의 진짜 구멍이다. 그 파일의 심볼은 통째로 없으므로 문서가
    #: 그 이름을 부르면 `orphaned`(코드에 없는 이름)로 읽힌다. 거짓 드리프트의 원인.
    unreadable_files: int = 0
    #: **선언이 하나도 없는 파일** (`__init__.py`, 스크립트). 평범한 사실이지 구멍이 아니다.
    #: 예전에는 위와 한 칸에 뭉쳐 있었고, 뭉쳐 있는 동안 이 수에는 경보를 걸 수 없었다 —
    #: 걸면 정상 상태에서 영원히 울린다.
    no_symbol_files: int = 0
    scanned_files: int = 0
    #: 저장소가 들여오기만 하고 선언하지 않는 이름. 문서가 이것을 불렀는데 심볼 인덱스에
    #: 없다고 해서 "사라졌다" 고 보고하면 안 된다 — 애초에 이 저장소 것이 아니었다.
    imported_names: frozenset[str] = frozenset()


def scan_repo(repo_path: Path) -> ScanResult:
    """저장소에서 `GRAMMARS` 가 아는 확장자를 훑는다. 미파싱 파일 수를 함께 돌려준다 —
    커버리지를 비율로만 보고하면 거짓이 되므로 분모가 필요하다 (SPEC §6.6)."""
    symbols: list[SymbolRow] = []
    imported: set[str] = set()
    unreadable = 0
    no_symbols = 0
    scanned = 0

    for path in sorted(p for ext in GRAMMARS for p in repo_path.rglob(f"*{ext}")):
        rel = path.relative_to(repo_path).as_posix()
        if _skip(rel):
            continue
        scanned += 1
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            unreadable += 1
            # 파일 경로는 대상 저장소의 내용이다. 로그에 남기되 본문은 절대 남기지 않는다.
            logger.warning("code_scan_unreadable", file=rel, error=type(e).__name__)
            continue

        imported |= imported_names(source, path.suffix.lower())
        found = extract_symbols(source, rel)
        if not found:
            no_symbols += 1
        symbols.extend(found)

    declared = {s.symbol_name for s in symbols}
    # 선언도 되고 차용도 되는 이름은 **우리 것**이다 (같은 이름의 자체 클래스가 있다).
    return ScanResult(symbols=symbols, unreadable_files=unreadable,
                      no_symbol_files=no_symbols, scanned_files=scanned,
                      imported_names=frozenset(imported - declared))
