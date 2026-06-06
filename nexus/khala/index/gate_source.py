"""GateExtractor — 코드의 권한 게이트를 AST(tree-sitter)로 추출.

CodeQL(유료) 없이 무료 tree-sitter로 "액션 → 요구 등급" 게이트와 등급 enum 레벨을 뽑는다.
지역 가드(`if (x.isBelowGrade(GradeType.MOD)) throw`)는 단일 메서드 내에 있으므로 AST로 충분.
추출은 고재현 *후보*까지 결정론 — "액션가드 vs 필터" 의미확정은 상위 도출/캘리브레이션 레이어 몫.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Language, Parser
import tree_sitter_java

_JAVA = Language(tree_sitter_java.language())
_GRADE_CHECKS = {"isBelowGrade", "isEqualOrHigherThan", "isHigherThan", "isLowerThan"}


@dataclass(frozen=True)
class GateFact:
    class_name: str
    method: str
    check: str
    grade: str | None  # 고정 임계면 GradeType.X 의 X, 상대 비교면 None
    kind: str  # "fixed" | "relative"
    arg: str = ""


def _parser() -> Parser:
    return Parser(_JAVA)


def _txt(src: bytes, n) -> str:
    return src[n.start_byte : n.end_byte].decode("utf-8", "ignore")


def _enclosing(node, types: set[str]):
    p = node.parent
    while p is not None:
        if p.type in types:
            return p
        p = p.parent
    return None


def _name(decl, src: bytes) -> str:
    n = decl.child_by_field_name("name") if decl else None
    return _txt(src, n) if n else "?"


def _iter_java(repo_path, subpath: str = ""):
    base = Path(repo_path)
    if subpath:
        base = base / subpath
    for f in base.rglob("*.java"):
        if "/test/" in f.as_posix():
            continue
        yield f


def extract_gates(repo_path, subpath: str = "") -> list[GateFact]:
    """권한 게이트 추출. ungated 메서드는 포함하지 않는다."""
    parser = _parser()
    out: set[GateFact] = set()
    for f in _iter_java(repo_path, subpath):
        src = f.read_bytes()
        tree = parser.parse(src)
        stack = [tree.root_node]
        while stack:
            n = stack.pop()
            if n.type == "method_invocation":
                nm = n.child_by_field_name("name")
                if nm and _txt(src, nm) in _GRADE_CHECKS:
                    args = n.child_by_field_name("arguments")
                    at = _txt(src, args) if args else ""
                    meth = _name(_enclosing(n, {"method_declaration"}), src)
                    cls = _name(_enclosing(n, {"class_declaration", "enum_declaration"}), src)
                    m = re.search(r"GradeType\.(\w+)", at)
                    out.add(
                        GateFact(
                            class_name=cls, method=meth, check=_txt(src, nm),
                            grade=(m.group(1) if m else None),
                            kind=("fixed" if m else "relative"), arg=at.strip(),
                        )
                    )
            stack.extend(n.children)
    return sorted(out, key=lambda g: (g.class_name, g.method, g.check, g.grade or ""))


def extract_grade_levels(repo_path, enum_name: str) -> dict[str, int]:
    """등급 enum(예: GradeType)의 상수→레벨 매핑 추출. `NAME(level)` 형태."""
    parser = _parser()
    for f in _iter_java(repo_path):
        src = f.read_bytes()
        tree = parser.parse(src)
        stack = [tree.root_node]
        while stack:
            n = stack.pop()
            if n.type == "enum_declaration" and _name(n, src) == enum_name:
                levels: dict[str, int] = {}
                ebody = [c for c in n.children if c.type == "enum_body"]
                consts = []
                if ebody:
                    consts = [c for c in ebody[0].children if c.type == "enum_constant"]
                for ec in consts:
                    cname = _name(ec, src)
                    args = ec.child_by_field_name("arguments")
                    if args:
                        mm = re.search(r"\d+", _txt(src, args))
                        if mm:
                            levels[cname] = int(mm.group(0))
                if levels:
                    return levels
            stack.extend(n.children)
    return {}
