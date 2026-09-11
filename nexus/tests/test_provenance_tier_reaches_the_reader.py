"""등급이 **사람이 읽는 표면**까지 가는가 — ADR-0010 §4 hop 5 의 「thereby」.

⛔ **왜 있나 (실측 2026-09-11).** ADR-0010 은 hop 다섯째를 이렇게 적는다:

    5. the API response (`/search`, `/search/answer`) **and thereby the web client**

그 「thereby」가 성립하지 않았다. 응답은 `provenance_tier` 를 실어 보내고 있었고,
`test_provenance_tier_hops.py` 는 여섯 hop 을 전부 초록으로 통과하고 있었는데,
**사람이 읽는 두 표면이 그 값을 안 그렸다**:

  · 웹 근거 목록 — 신뢰 배지와 앵커 배지를 달면서 등급만 안 달았다
  · 슬랙 근거 줄 — 제목·절·점수만 그렸다 (팀이 실제로 답을 읽는 자리다)

MCP(hop 6)만 `mark()` 를 불러 쓰고 있었다. 즉 등급은 **에이전트 표면에만** 닿고 있었다.

⭐ hop 을 세는 것과 **표면에서 그려지는지**를 세는 것은 다른 검사다. 앞의 것은 값이
   payload 에 있는지 묻고, 뒤의 것은 읽는 사람이 그것을 보는지 묻는다. ADR 의 문장은
   앞의 것이 뒤의 것을 함의한다고 적었는데 함의하지 않았다.

⚠ 읽는 표면 검사는 **소스를 읽어서** 한다. 웹은 JS 이고 슬랙 블록은 DOM 이 아니라 dict 라
   한쪽만 호출로 검사하면 나머지 한쪽이 조용히 빠진다 — 이 리포가 표면별로 이미 데인 모양이다.
"""

from __future__ import annotations

import re
from pathlib import Path

from nexus.search.provenance import AUTHORED, LIST_MARK, MACHINE_READ, MIXED, mark
from nexus.slack.formatter import format_answer

ROOT = Path(__file__).resolve().parents[1]

#: 답을 **사람**이 읽는 표면과, 그 표면이 등급을 꺼내 쓰는 이름.
READER_SURFACES = (
    "nexus/slack/formatter.py",
    "nexus/web/js/views/chat.js",
)

#: 등급을 payload 에 실어 보내는 서버 표면. 하나만 고치면 다른 쪽 화면이 오늘과 같다.
SERVER_SURFACES = (
    "nexus/api.py",
    "nexus/llm/answer.py",
)


def _src(rel: str) -> str:
    p = ROOT / rel
    assert p.is_file(), f"{rel} 이 없다 — 파일이 옮겨졌으면 이 목록을 고쳐라"
    return p.read_text(encoding="utf-8")


def _code(rel: str) -> str:
    """주석을 걷어낸 소스.

    ⛔ **왜 걷어내나.** 처음 쓴 이 검사는 파일 어디든 `provenance_mark` 라는 글자가 있으면
    통과했다. 그래서 렌더링을 도로 빼고 **설명 주석만 남겨도 초록**이었다 — 일부러 깨뜨려
    보고 알았다. 검사는 제목이 아니라 실패하는 조건으로 판단해야 한다.
    """
    src = _src(rel)
    if rel.endswith(".js"):
        src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
        src = re.sub(r"(?m)^\s*//.*$", " ", src)
    else:
        src = re.sub(r"(?m)#.*$", " ", src)
    return src


def _answer(tier: str) -> dict:
    return {
        "answer": "답변입니다",
        "evidence_snippets": [{
            "doc_title": "정책 A", "section_path": "해금", "score": 0.91,
            "provenance_tier": tier, "provenance_mark": mark(tier),
        }],
    }


def _all_text(blocks: list[dict]) -> str:
    out = []
    for b in blocks:
        t = b.get("text")
        if isinstance(t, dict):
            out.append(t.get("text", ""))
        for e in b.get("elements", []) or []:
            if isinstance(e, dict):
                out.append(e.get("text", ""))
    return "\n".join(out)


# ── 슬랙: 사람이 답을 읽는 자리 ────────────────────────────────────────────────

def test_slack_marks_machine_read_evidence():
    text = _all_text(format_answer(_answer(MACHINE_READ)))

    assert "정책 A" in text, "근거 줄 자체가 안 그려졌다 — 이 검사가 볼 것이 없다"
    assert LIST_MARK.strip() in text


def test_slack_marks_mixed_evidence_too():
    """섞였다는 것은 확인이 필요하다는 뜻이고, 그게 이 등급이 하는 일이다."""
    assert LIST_MARK.strip() in _all_text(format_answer(_answer(MIXED)))


def test_slack_leaves_authored_evidence_quiet():
    """⛔ 대조군. 전부에 붙이면 아무것도 구별하지 못한다 — 기본이 조용해야 표시가 뜻을 갖는다."""
    text = _all_text(format_answer(_answer(AUTHORED)))

    assert "정책 A" in text
    assert LIST_MARK.strip() not in text


# ── 표면 세기: 값이 있는 것과 사람이 보는 것은 다르다 ────────────────────────

def test_every_server_surface_sends_the_rendered_mark():
    """payload 에 등급 문자열이 실려야 표현계층이 어휘를 지어내지 않는다."""
    for rel in SERVER_SURFACES:
        assert "provenance_mark" in _code(rel), f"{rel} 이 등급 표시를 안 실어 보낸다"


def test_every_reader_surface_renders_the_mark():
    """⭐ 이 검사가 없어서 hop 여섯이 전부 초록인 채로 두 화면이 등급을 버리고 있었다."""
    for rel in READER_SURFACES:
        assert "provenance_mark" in _code(rel), f"{rel} 이 등급 표시를 안 그린다"


def test_no_reader_surface_hardcodes_the_vocabulary():
    """어휘는 `search/provenance.py` 한 곳에서 온다. 사본이 생기면 표면마다 다른 말을 한다."""
    for rel in READER_SURFACES:
        src = _code(rel)
        assert LIST_MARK.strip() not in src, f"{rel} 이 표시 문구를 직접 들고 있다"
        # 등급 값으로 분기해 문장을 고르는 것도 사본이다.
        assert not re.search(r"machine_read\s*[=:?]", src), f"{rel} 이 등급으로 직접 분기한다"
