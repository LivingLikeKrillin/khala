"""코드 심볼 인덱스 + 스냅샷 가드 (SPEC-nexus-doc-code-anchors §3.1, §3.5).

⚠ 이 파일의 Java 는 전부 **여기서 지어낸 것**이다. 대상 저장소의 소스를 픽스처로 복사하지
   말 것 — 그 순간 공개 리포가 그 저장소의 코드를 담게 되고, 지문 스캐너는 코드 구조를 보지
   않으므로 잡아주지 않는다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from nexus.index import snapshot
from nexus.index.symbols import (
    SymbolRow,
    extract_symbols,
    normalize_span,
    scan_repo,
    span_hash,
)

SAMPLE = """\
package com.example.widget;

/** Retry policy for widget dispatch. */
public class WidgetDispatcher {
    public static final int MAX_ATTEMPTS = 2;

    public void dispatch(String payload) {
        send(payload);
    }

    private void send(String payload) {
        // no-op
    }
}

interface WidgetSink {
    void accept(String payload);
}
"""


# ---------------------------------------------------------------- 정규화

def test_crlf_does_not_change_the_hash():
    """이 규칙이 없으면 Windows 체크아웃에서 전 앵커가 한 번에 뒤집힌다."""
    assert span_hash("a {\n  b;\n}") == span_hash("a {\r\n  b;\r\n}")


def test_trailing_whitespace_does_not_change_the_hash():
    assert span_hash("a {\n  b;   \n}") == span_hash("a {\n  b;\n}")


def test_a_real_edit_does_change_the_hash():
    """회귀 검사이 실제로 잡는지 — 한 글자를 바꾸면 달라져야 한다."""
    assert span_hash("int MAX = 2;") != span_hash("int MAX = 3;")


def test_comments_are_inside_the_hash():
    """계약을 서술하는 주석이 바뀌는 것은 진짜 신호다 (SPEC §3.1)."""
    assert span_hash("// two\nint MAX = 2;") != span_hash("// three\nint MAX = 2;")


def test_normalize_strips_leading_and_trailing_blank_lines():
    assert normalize_span("\n\nx\n\n") == "x"


# ---------------------------------------------------------------- 추출

def test_extracts_declarations_with_kinds():
    rows = extract_symbols(SAMPLE, "Widget.java")
    found = {(r.symbol_name, r.symbol_kind) for r in rows}
    assert ("WidgetDispatcher", "class") in found
    assert ("WidgetSink", "interface") in found
    assert ("dispatch", "method") in found
    assert ("send", "method") in found


def test_line_numbers_are_one_based_and_bounded():
    rows = extract_symbols(SAMPLE, "Widget.java")
    cls = next(r for r in rows if r.symbol_name == "WidgetDispatcher")
    assert cls.start_line >= 1
    assert cls.end_line > cls.start_line
    assert cls.end_line <= len(SAMPLE.splitlines())


def test_two_methods_with_different_bodies_hash_differently():
    rows = {r.symbol_name: r for r in extract_symbols(SAMPLE, "Widget.java")}
    assert rows["dispatch"].span_hash != rows["send"].span_hash


def test_unparsable_source_yields_no_symbols_rather_than_raising():
    """파스 실패는 예외가 아니라 빈 목록 — 호출자가 미파싱으로 센다 (분모, SPEC §6.6)."""
    assert extract_symbols("}{ not java at all ((", "Broken.java") == []


# ------------------------------------------------- 노출 금지 (사용자 제약)

def test_symbol_rows_carry_no_source_text():
    """**대상 저장소의 코드 본문은 어디에도 담기지 않는다.**

    실수가 아니라 계약이다. 디버깅이 편하다는 이유로 스니펫 필드가 생기면 이 인덱스는
    그 저장소의 소스를 담기 시작하고, 그때부터 덤프·픽스처·로그가 전부 유출 경로가 된다.
    """
    rows = extract_symbols(SAMPLE, "Widget.java")
    assert rows

    # 본문에만 있고 이름에는 없는 토큰들. 어떤 필드에도 나타나면 안 된다.
    body_only = ["MAX_ATTEMPTS", "payload", "no-op", "com.example.widget"]
    for row in rows:
        blob = " ".join(str(v) for v in vars(row).values())
        for token in body_only:
            assert token not in blob, f"{row.symbol_name} 행에 본문 토큰 {token!r} 가 샜다"


def test_symbol_row_has_no_text_like_field():
    """필드 이름 수준에서도 막는다 — 나중에 누가 추가하면 여기서 걸린다."""
    banned = {"source", "text", "body", "snippet", "content", "code"}
    assert banned.isdisjoint(SymbolRow.__dataclass_fields__.keys())


# ---------------------------------------------------------------- 스캔

def test_scan_counts_unparsed_files_as_a_denominator(tmp_path: Path):
    """읽히지만 **선언이 안 나오는** 파일은 `no_symbol_files` 다 (migration 033 이 가른 쪽).

    옛 `unparsed_files` 는 이것과 *읽기 실패* 를 한 칸에 셌다. 이 파일은 읽히므로 여기서
    세어지는 것이 맞고, 그래서 이 수에는 경보를 걸지 않는다.
    """
    (tmp_path / "Good.java").write_text(SAMPLE, encoding="utf-8")
    (tmp_path / "Bad.java").write_text("}{ nope", encoding="utf-8")

    result = scan_repo(tmp_path)

    assert result.scanned_files == 2
    assert result.no_symbol_files == 1
    assert result.unreadable_files == 0
    assert any(r.symbol_name == "WidgetDispatcher" for r in result.symbols)


# ---------------------------------------------------------------- 가드

def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True,
                   capture_output=True, text=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.invalid")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "Widget.java").write_text(SAMPLE, encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "first")
    return tmp_path


def _head(repo: Path) -> str:
    return snapshot.head_commit(repo)


def test_guard_passes_on_a_clean_checkout_at_the_scanned_commit(repo: Path):
    assert snapshot.check(repo, _head(repo)).ok


def test_guard_refuses_a_dirty_tree(repo: Path):
    """더러운 트리에서 계산한 fresh 는 확신에 찬 거짓말이다."""
    (repo / "Widget.java").write_text(SAMPLE + "\n// edited\n", encoding="utf-8")

    state = snapshot.check(repo, _head(repo))

    assert not state.ok
    assert state.reason == "dirty"


def test_guard_refuses_detached_head(repo: Path):
    _git(repo, "checkout", "-q", "--detach", "HEAD")

    state = snapshot.check(repo, _head(repo))

    assert not state.ok
    assert state.reason == "detached"


def test_guard_passes_when_the_scan_is_an_ancestor_of_head(repo: Path):
    """스캔 이후의 커밋은 정상이다 — 그 변화는 changed/orphaned 가 잡는 몫이다."""
    old = _head(repo)
    (repo / "Other.java").write_text("class Other {}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "second")

    assert snapshot.check(repo, old).ok


def test_guard_refuses_when_the_scan_is_ahead_of_head(repo: Path):
    """체크아웃을 되돌려 놓고 다시 스캔하지 않은 상태."""
    (repo / "Other.java").write_text("class Other {}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "second")
    ahead = _head(repo)
    _git(repo, "reset", "-q", "--hard", "HEAD~1")

    state = snapshot.check(repo, ahead)

    assert not state.ok
    assert state.reason == "scan_ahead_of_head"


def test_guard_refuses_a_diverged_scan(repo: Path):
    _git(repo, "checkout", "-q", "-b", "side")
    (repo / "Side.java").write_text("class Side {}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "side")
    side = _head(repo)

    _git(repo, "checkout", "-q", "main")
    (repo / "Main.java").write_text("class MainOnly {}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "main2")

    state = snapshot.check(repo, side)

    assert not state.ok
    assert state.reason == "scan_diverged"


def test_guard_refuses_outside_a_git_repo(tmp_path: Path):
    state = snapshot.check(tmp_path, "0" * 40)

    assert not state.ok
    assert state.reason == "no_git"


# ------------------------------------------------------------- Python 문법

PY_SAMPLE = '''\
"""Widget dispatch."""


class WidgetDispatcher:
    MAX_ATTEMPTS = 2

    def dispatch(self, payload):
        self._send(payload)

    def _send(self, payload):
        pass


def build_sink():
    return None
'''


def test_extracts_python_classes_and_functions():
    rows = extract_symbols(PY_SAMPLE, "widget.py")
    found = {(r.symbol_name, r.symbol_kind) for r in rows}
    assert ("WidgetDispatcher", "class") in found
    assert ("dispatch", "function") in found
    assert ("build_sink", "function") in found


def test_grammar_is_chosen_by_extension_not_content():
    """Java 소스를 .py 로 주면 심볼이 나오지 않아야 한다 — 확장자가 계약이다."""
    assert extract_symbols(SAMPLE, "Widget.py") == []


def test_unknown_extension_yields_nothing():
    assert extract_symbols(PY_SAMPLE, "notes.txt") == []


def test_python_normalisation_matches_java_rules():
    assert span_hash("def f():\r\n    return 1\r\n") == span_hash("def f():\n    return 1\n")


def test_python_rows_also_carry_no_source_text():
    rows = extract_symbols(PY_SAMPLE, "widget.py")
    for row in rows:
        blob = " ".join(str(v) for v in vars(row).values())
        for token in ["MAX_ATTEMPTS", "payload", "Widget dispatch"]:
            assert token not in blob


def test_scan_walks_both_languages_and_skips_vendor_dirs(tmp_path: Path):
    """벤더 디렉터리 하나가 인덱스를 남의 코드로 뒤덮으면 유일 해소가 무너진다."""
    (tmp_path / "Widget.java").write_text(SAMPLE, encoding="utf-8")
    (tmp_path / "widget.py").write_text(PY_SAMPLE, encoding="utf-8")
    vendor = tmp_path / "node_modules" / "pkg"
    vendor.mkdir(parents=True)
    (vendor / "vendored.py").write_text("class Vendored: pass\n", encoding="utf-8")

    result = scan_repo(tmp_path)

    names = {r.symbol_name for r in result.symbols}
    assert "WidgetDispatcher" in names          # 두 언어 모두에서 나온다
    assert "build_sink" in names
    assert "Vendored" not in names
    assert result.scanned_files == 2            # 벤더는 분모에도 안 들어간다


# ------------------------------------------- 가드가 무엇을 사실로 삼았는지 말하는가

def test_context_names_the_branch_and_the_head_date(repo: Path):
    """이게 없어서 3주 된 피처 브랜치를 조용히 사실로 보고한 적이 있다."""
    state = snapshot.check(repo, _head(repo))

    assert "main" in state.context()
    assert state.branch == "main"
    assert state.head_date                      # ISO 날짜가 붙는다
    assert state.head[:12] in state.context()


def test_a_non_mainline_branch_warns_but_does_not_block(repo: Path):
    _git(repo, "checkout", "-q", "-b", "docs/some-feature")

    state = snapshot.check(repo, _head(repo))

    assert state.ok                              # 막지는 않는다 — 일부러 잴 수 있다
    assert any("기본 브랜치가 아닙니다" in w for w in state.warnings())


def test_being_behind_upstream_warns_from_local_refs_only(tmp_path: Path):
    """업스트림 격차는 **로컬에 저장된** 추적 ref 에서 읽는다 — 네트워크를 쓰지 않는다."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", "main")
    _git(origin, "config", "user.email", "t@example.invalid")
    _git(origin, "config", "user.name", "t")
    (origin / "A.java").write_text("class A {}\n", encoding="utf-8")
    _git(origin, "add", "-A")
    _git(origin, "commit", "-q", "-m", "first")

    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    _git(clone, "config", "user.email", "t@example.invalid")
    _git(clone, "config", "user.name", "t")

    # 원격이 앞서 나간 뒤 fetch — 이후 네트워크 없이도 격차를 안다.
    (origin / "B.java").write_text("class B {}\n", encoding="utf-8")
    _git(origin, "add", "-A")
    _git(origin, "commit", "-q", "-m", "second")
    _git(clone, "fetch", "-q")

    state = snapshot.check(clone, _head(clone))

    assert state.ok                              # 뒤처짐은 거부 사유가 아니다
    assert state.behind == 1
    assert any("뒤입니다" in w for w in state.warnings())


def test_a_clean_mainline_checkout_warns_about_nothing(repo: Path):
    assert snapshot.check(repo, _head(repo)).warnings() == []


# ------------------------------------- 외부 타입 (드리프트 오탐의 주범)

def test_java_imports_are_collected_as_borrowed_names():
    from nexus.index.symbols import imported_names

    got = imported_names(
        "import org.springframework.context.ApplicationEventPublisher;\n"
        "import static java.util.Objects.requireNonNull;\n"
        "import java.util.*;\n", ".java")

    assert "ApplicationEventPublisher" in got
    assert "requireNonNull" in got
    assert "*" not in got


def test_python_imports_are_collected():
    from nexus.index.symbols import imported_names

    got = imported_names("from pathlib import Path, PurePath\nimport structlog\n", ".py")

    assert {"Path", "PurePath", "structlog"} <= got


def test_a_name_that_is_both_declared_and_imported_counts_as_ours(tmp_path: Path):
    """같은 이름의 자체 클래스가 있으면 그건 우리 것이다 — 외부로 빼면 진짜 드리프트를 놓친다."""
    (tmp_path / "A.java").write_text(
        "import com.other.Widget;\nclass Widget { void f() {} }\n", encoding="utf-8")

    result = scan_repo(tmp_path)

    assert "Widget" in {s.symbol_name for s in result.symbols}
    assert "Widget" not in result.imported_names


def test_borrowed_names_are_reported_so_they_are_not_called_missing(tmp_path: Path):
    """문서가 프레임워크 클래스를 불렀다고 '사라졌다' 고 보고하면 목록이 작업 큐가 못 된다."""
    (tmp_path / "A.java").write_text(
        "import org.spring.EventPublisher;\nclass Mine { void f() {} }\n", encoding="utf-8")

    result = scan_repo(tmp_path)

    assert "EventPublisher" in result.imported_names
