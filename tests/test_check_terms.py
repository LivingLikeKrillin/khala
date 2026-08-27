"""용어 검사기 — **새로 쓰는 줄**만 본다.

왜 diff 만 보나. 전체 트리를 검사하면 "자" 하나 때문에 사용자·숫자·글자·자동… 예외가
수십 개 필요하고, **예외가 수십 개인 검사는 곧 꺼진다.** 정책이 "앞으로만" 이므로 검사
범위도 앞으로 쓰는 줄에 맞춘다 — 범위가 정책과 같으면 잡음이 거의 없다.

정본은 `GLOSSARY.md` 하나다. 검사기가 자기 목록을 따로 들고 있으면 둘이 갈라지고,
이 리포는 손으로 미러링한 목록이 부패원이라고 이미 적어 뒀다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_terms  # noqa: E402


# ── 정본 읽기 ──────────────────────────────────────────────────────────────

def test_the_banned_list_comes_from_the_glossary():
    """검사기는 자기 목록을 갖지 않는다 — 용어집이 정본이다."""
    banned = check_terms.load_banned(ROOT / "GLOSSARY.md")
    assert "자" in banned
    assert banned["자"], "대체어가 비어 있으면 사람에게 무엇을 쓰라고 못 한다"


def test_a_term_added_to_the_glossary_is_enforced(tmp_path):
    """용어집에 한 줄 더하면 그날부터 검사에 든다. 코드를 안 고쳐도 된다."""
    glossary = tmp_path / "GLOSSARY.md"
    glossary.write_text(
        "\n".join([
            "# 용어집",
            "",
            "## 걷어낸 말",
            "",
            "| 쓰지 않는 말 | 대신 | 왜 |",
            "|---|---|---|",
            "| 삐약 | 병아리 | 자로 쓴 예 |",
        ]),
        encoding="utf-8",
    )
    banned = check_terms.load_banned(glossary)
    assert banned == {"삐약": "병아리"}


# ── 판정 ──────────────────────────────────────────────────────────────────

def test_a_coined_term_in_a_living_doc_is_a_violation():
    hits = check_terms.check_line("nexus/docs/GUIDE.md", "이 자가 무엇을 재는지 적어라",
                                  {"자": "평가 하니스"})
    assert [h[0] for h in hits] == ["자"]


def test_the_same_word_inside_a_longer_word_is_not_a_violation():
    """⛔ **이 자가 없으면 검사기가 꺼진다.** '자' 는 흔한 글자라, 합성어를 잡기 시작하면
    거짓 경고가 쏟아지고 그러면 사람이 검사를 끈다."""
    for line in (
        "사용자는 이것을 본다",
        "숫자가 틀렸다",
        "관리자 권한이 필요하다",
        "자동으로 적재된다",
        "자기 자신을 센다",
        "설계자와 개발자",
    ):
        assert check_terms.check_line("a.md", line, {"자": "평가 하니스"}) == [], line


def test_a_counter_word_is_not_the_coined_term():
    """⛔ '자' 는 글자 수를 세는 단위이기도 하다. 이걸 잡으면 거짓 경고가 나고,
    거짓 경고가 나는 검사는 꺼진다."""
    for line in (
        "답변 길이는 3,000자가 상한이다",
        "해시는 12자만 남긴다",
        "제목은 40자 이내",
    ):
        assert check_terms.check_line("nexus/docs/GUIDE.md", line,
                                      {"자": "평가 하니스"}) == [], line


def test_emphasis_between_a_number_and_its_counter_is_not_prose():
    """⛔ 마크다운 강조가 숫자와 단위 사이에 끼면 경계 검사가 뚫린다 —
    `본문 10735자 → **6812**자` 에서 뒤쪽 '자' 앞 글자는 `*` 다. 실물에서 9곳 나왔다."""
    line = "- 청크 3 → **10** · 본문 10735자 → **6812**자"
    assert check_terms.check_line("nexus/tests/eval/x/README.md", line,
                                  {"자": "평가 하니스"}) == []


def test_machine_read_image_text_is_not_our_prose():
    """그림에서 읽어 낸 원문은 **조직 문서의 말**이지 이 리포가 쓴 문장이 아니다 — 고칠
    대상도 아니다. 시스템이 이미 그렇게 다룬다: 마이그레이션 030 은 이 표시가 붙은 텍스트를
    검색 색인에서 걷어낸다. 재서명 워크시트마다 이런 블록이 들어오므로 미리 막는다."""
    line = ("  > ![](){: derived=vision extractor=gemini-3.6-flash/06e83390 } "
            "> 본문 10735자, 이 자를 옮긴다")
    assert check_terms.check_line("nexus/tests/eval/local/x-worksheet.md", line,
                                  {"자": "평가 하니스"}) == []


def test_an_interpolated_count_is_a_counter_too():
    """`{len(body)}자` 는 f-string 안의 단위다. 숫자가 변수로 들어오면 앞 글자가 `}` 라
    숫자 경계에 안 걸린다 — 실물에서 다섯 곳이 이 모양이었다."""
    for line in (
        'print(f"  {d.name}  ({len(d.body):,}자)  {d.title}")',
        'echo "기본값이거나 24자 미만, 현재 ${#tok}자"',
        'f"스니펫 {n}개 × 최대 {snippet_max_chars}자"',
    ):
        assert check_terms.check_line("nexus/x.md", line, {"자": "평가 하니스"}) == [], line


def test_an_english_term_is_caught_regardless_of_case():
    """공개 문서는 영문 페이지가 짝으로 있다. 문장 첫머리의 대문자를 놓치면 한쪽만 고쳐지고,
    그게 이 항목이 생긴 이유다 — 한국어만 고쳐서 ko/en 이 갈렸다."""
    banned = {"retrieval leg": "retrieval path"}
    for line in ("Retrieval legs fuse by rank.", "both retrieval legs are weak"):
        hits = [w for w, _ in check_terms.check_line("docs/x.md", line, banned)]
        assert hits == ["retrieval leg"], line


def test_the_generated_spec_register_is_archival():
    """`INDEX.md` 는 승인 SPEC 의 제목을 옮긴 등록부이고 `arbiter` 가 **생성**한다 —
    손으로 고쳐도 다음 실행에 덮이고, 그 말은 그 SPEC 들의 것이다."""
    assert check_terms.is_archival("INDEX.md")


def test_a_hyphenated_or_suffixed_name_is_an_identifier_not_prose():
    """⛔ `SPEC-nexus-answer-quality-ruler` 는 **승인된 문서의 이름**이고 `ruler_sha` 는
    필드 이름이다. 이름을 고치면 가리키는 것이 사라진다 — 실물에서 15곳이 이 모양이었다."""
    banned = {"ruler": "grader"}
    for line in (
        "판정 규칙은 SPEC-nexus-answer-quality-ruler §3.2 에 있다",
        '"ruler_sha": _ruler_sha(),',
        "from tests.test_answer_assertion_ruler import x",
    ):
        assert check_terms.check_line("nexus/x.md", line, banned) == [], line


def test_the_english_word_still_fires_in_ordinary_prose():
    """대조군 — 이름을 빼느라 산문까지 놓치면 이 항목은 없는 것과 같다."""
    banned = {"ruler": "grader"}
    for line in ("Two independent rulers share this job",
                 "a later ruler may reopen it"):
        assert [w for w, _ in check_terms.check_line("nexus/x.md", line, banned)] == ["ruler"], line


def test_archival_paths_are_exempt():
    """과거는 그대로 둔다 — 컴포넌트 개명 때 정한 규칙과 같다."""
    line = "이 자가 통과시켰다"
    banned = {"자": "평가 하니스"}
    for path in (
        "specs/SPEC-nexus-answer-quality-ruler.md",
        "adr/ADR-0010-x.md",
        ".reviews/SPEC-x.md",
        "nexus/tests/eval/reports/2026-08-04-ann-vs-exact.md",
    ):
        assert check_terms.check_line(path, line, banned) == [], path


def test_the_public_engineering_log_is_not_archival():
    """⚠ 한때 면제였고 2026-08-27 에 걷어냈다.

    「기록물은 그대로」 의 기제는 둘이다 — 승인 문서는 고치면 **도장이 깨지고**, 결정 기록은
    **그때 정한 것**을 말한다. 공개 로그는 둘 다 아니다: 서명이 없고, 결정 기록도 아니고,
    바깥 사람이 읽으라고 쓴 서사다. 그 독자가 정확히 이 리포의 조어를 해독 못 하는 사람이라,
    여기를 면제하면 정책이 가장 필요한 자리를 비우게 된다.
    """
    for path in ("docs/src/content/docs/ko/engineering-log.md",
                 "docs/src/content/docs/engineering-log.md"):
        assert not check_terms.is_archival(path), path
        assert check_terms.check_line(path, "이 자가 통과시켰다",
                                      {"자": "채점기"}) != [], path


def test_the_glossary_may_name_the_words_it_bans():
    """사전은 자기가 금지한 말을 적어야 한다. 이 면제가 없으면 정본이 자기 검사에 걸려
    아예 쓸 수 없다."""
    assert check_terms.check_line("GLOSSARY.md", "| 자 | 평가 하니스 | … |",
                                  {"자": "평가 하니스"}) == []


def test_a_dated_report_is_archival_but_a_readme_beside_it_is_not():
    """날짜가 박힌 파일은 그날 그 측정의 기록이다. 옆의 README 는 살아 있는 안내문이다."""
    assert check_terms.is_archival("nexus/tests/eval/reports/2026-08-04-x.md")
    assert not check_terms.is_archival("nexus/tests/eval/answer-facts/README.md")


def test_code_spans_are_not_prose():
    """`ruler` 같은 식별자·파일명은 산문이 아니다 — 고칠 대상이 아니고 인용해야 할 때가 있다."""
    line = "승인된 `SPEC-nexus-answer-quality-ruler.md` 는 그대로 둔다"
    assert check_terms.check_line("OPEN.md", line, {"ruler": "채점기"}) == []


# ── diff 파싱 ─────────────────────────────────────────────────────────────

def test_only_added_lines_are_read():
    """지우는 줄과 맥락 줄은 검사하지 않는다. 낡은 말을 **걷어내는** 커밋이 자기 검사에
    걸리면 정리를 못 한다."""
    diff = "\n".join([
        "diff --git a/OPEN.md b/OPEN.md",
        "--- a/OPEN.md",
        "+++ b/OPEN.md",
        "@@ -1,3 +1,3 @@",
        " 맥락 줄에 자가 있어도 무시",
        "-이 자를 걷어낸다",
        "+평가 하니스로 바꿨다",
    ])
    added = check_terms.added_lines(diff)
    assert added == [("OPEN.md", "평가 하니스로 바꿨다")]


def test_the_file_header_is_not_an_added_line():
    """`+++ b/…` 는 `+` 로 시작하지만 본문이 아니다."""
    diff = "\n".join([
        "diff --git a/a.md b/a.md",
        "--- a/a.md",
        "+++ b/a.md",
        "@@ -0,0 +1 @@",
        "+첫 줄",
    ])
    assert check_terms.added_lines(diff) == [("a.md", "첫 줄")]


def test_only_prose_files_are_checked():
    """코드·설정에는 이 정책이 안 걸린다. 범위는 '사람이 보는 말' 이다."""
    diff = "\n".join([
        "diff --git a/x.py b/x.py",
        "+++ b/x.py",
        "@@ -0,0 +1 @@",
        "+# 이 자가 잰다",
    ])
    assert check_terms.added_lines(diff) == []
