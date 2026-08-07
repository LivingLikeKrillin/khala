"""한국어 평가 라벨 — 적재와 자 검사 (SPEC-nexus-korean-retrieval-eval §4.2, §6).

**측정 전에 자를 먼저 검사한다.** 예전 조사에서 정답 id 를 8자 접두사로 줬다가 서로 다른 두
페이지에 매칭됐고, 채점기가 정답 1위를 '회귀' 로 적었다. 그 허구를 고치려고 설계를 하나 만들 뻔했다.

여기 게이트가 막는 것들:

- **기대 어휘 칸의 부활** — `token|lexeme|morpheme|term|expected_word` 를 담은 키가 라벨 어디에도
  못 들어온다. 기존 스위트를 토크나이저 비교 불가로 만든 결함이 정확히 그 칸이었다. 관례가 아니라
  표현 불가능성으로 막는다.
- **모호한 정답** — gold 는 팩 상대 경로 전체여야 하고 실제로 존재해야 한다(접두사 금지).
- **제목 베끼기** — 질의가 정답 문서의 **전체 제목**(6자 이상)을 그대로 품으면 그건 검색이 아니라
  문자열 일치를 재는 것이다. 헤딩이나 짧은 제목은 검사하지 않는다 — `파드`·`노드` 같은 헤딩까지
  금지하면 외래어·복합명사 층이 재려는 어휘 자체를 못 쓰게 된다.
- **층 불균형** — 답변가능 40건이 다섯 층에 정확히 8건씩. 층별 수치는 서술용이지만, 그 균형이
  깨지면 서술조차 못 한다.
- **사람 없는 에이전트 라벨** — `authored_by: agent` 인데 `reviewed_by` 가 비면 실패한다. 검토
  기록 없이 "사람이 봤다" 고 적는 건 ADR-0002 의 금지를 이름만 지키는 것이다.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import yaml

STRATA = ("loanword", "compound", "particle", "mixed", "spacing")
UNANSWERABLE = "unanswerable"
PER_STRATUM = 8
TITLE_MIN_CHARS = 6

REQUIRED_FIELDS = ("id", "query", "stratum", "answerable", "gold", "rationale",
                   "provenance", "authored_by")
BANNED_KEY = re.compile(r"token|lexeme|morpheme|term|expected_word", re.IGNORECASE)

DEFAULT_LABELS = Path(__file__).resolve().parents[1] / "tests" / "eval" / "ko" / "labels.yaml"
_HEADING = re.compile(r"^# (.+)$", re.MULTILINE)
_WS = re.compile(r"\s+")


def load(path: Path = DEFAULT_LABELS) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def answerable(labels: dict) -> list[dict]:
    """집계에 들어가는 질의만 (§4.3 분모는 40이지 45가 아니다)."""
    return [q for q in labels.get("queries", []) if q.get("answerable")]


def _banned_keys(node, trail: str = "") -> list[str]:
    """중첩 구조 전체를 훑어 금지된 키 이름을 찾는다 — 어느 깊이에서도 못 들어온다."""
    found: list[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            where = f"{trail}.{k}" if trail else str(k)
            if isinstance(k, str) and BANNED_KEY.search(k):
                found.append(where)
            found += _banned_keys(v, where)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            found += _banned_keys(v, f"{trail}[{i}]")
    return found


def _norm(text: str) -> str:
    return _WS.sub(" ", unicodedata.normalize("NFC", text)).strip()


def doc_title(pack_dir: Path, rel: str) -> str | None:
    """팩 문서의 첫 `# ` 제목. 없으면 None."""
    f = pack_dir / "docs" / rel
    if not f.exists():
        return None
    m = _HEADING.search(f.read_text(encoding="utf-8"))
    return m.group(1).strip() if m else None


class DiskPack:
    """디스크에 풀린 팩 (Pack A). gold 는 `docs/` 아래의 실제 파일이다."""

    def __init__(self, pack_dir: Path) -> None:
        self.pack_dir = Path(pack_dir)

    def has(self, rel: str) -> bool:
        return (self.pack_dir / "docs" / rel).exists()

    def title(self, rel: str) -> str | None:
        return doc_title(self.pack_dir, rel)


class ManifestPack:
    """매니페스트로만 존재하는 팩 (Pack B).

    Pack B 는 테넌트 스냅샷이라 `docs/` 디렉터리가 없다(그 이유는 `ko_eval_packb.py` 참고 —
    Nexus 는 원문을 갖고 있지 않아 디스크로 내보내면 다시 청킹된다). 그래서 gold 의 존재와 제목을
    **매니페스트**에서 읽는다. 규칙은 디스크 팩과 **같다** — 갈라지면 한쪽만 조여진다.
    """

    def __init__(self, manifest_path: Path) -> None:
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        self._titles = {d["key"]: d.get("title") for d in data["docs"]}

    def has(self, rel: str) -> bool:
        return rel in self._titles

    def title(self, rel: str) -> str | None:
        return self._titles.get(rel)


def _as_corpus(source):
    """`Path` 면 디스크 팩. 이미 코퍼스면 그대로 — 옛 호출부가 그대로 돈다."""
    return DiskPack(source) if isinstance(source, (str, Path)) else source


def check(labels: dict, pack_dir) -> list[str]:
    """라벨 파일의 자 검사. 문제 목록을 돌려준다(빈 목록 = 통과).

    `pack_dir` 는 디스크 팩 경로이거나 `ManifestPack` 같은 코퍼스다.
    """
    corpus = _as_corpus(pack_dir)
    problems: list[str] = []

    if not labels.get("revision"):
        problems.append("revision 없음 — 바닥값이 어느 라벨판에 박혔는지 말할 수 없다")
    if not labels.get("pack"):
        problems.append("pack 없음 — 어느 코퍼스에 대한 라벨인지 말할 수 없다")

    problems += [f"금지된 키(기대 어휘 칸): {k}" for k in _banned_keys(labels)]

    queries = labels.get("queries") or []
    if not queries:
        return problems + ["queries 비어 있음"]

    seen_ids: set[str] = set()
    counts = dict.fromkeys(STRATA, 0)

    for q in queries:
        qid = q.get("id", "?")
        for field in REQUIRED_FIELDS:
            if field not in q:
                problems.append(f"{qid}: 필드 없음 — {field}")
        if qid in seen_ids:
            problems.append(f"{qid}: 중복 id")
        seen_ids.add(qid)

        stratum, gold = q.get("stratum"), q.get("gold") or []
        if stratum in counts:
            if q.get("answerable"):
                counts[stratum] += 1
        elif stratum != UNANSWERABLE:
            problems.append(f"{qid}: 알 수 없는 층 — {stratum}")

        if q.get("answerable"):
            if not gold:
                problems.append(f"{qid}: answerable 인데 gold 가 비었다")
            if stratum == UNANSWERABLE:
                problems.append(f"{qid}: answerable 인데 층이 unanswerable")
        else:
            if gold:
                problems.append(f"{qid}: answerable=false 인데 gold 가 있다")
            if stratum != UNANSWERABLE:
                problems.append(f"{qid}: answerable=false 인데 층이 {stratum}")

        if q.get("authored_by") == "agent" and not (q.get("reviewed_by") or "").strip():
            problems.append(f"{qid}: 에이전트가 쓴 라벨에 reviewed_by 가 없다 — 사람의 검토 기록이 곧 게이트다")

        query_text = _norm(q.get("query", ""))
        for rel in gold:
            if not isinstance(rel, str) or not rel.endswith(".md"):
                problems.append(f"{qid}: gold 는 팩 상대 경로여야 한다 — {rel!r}")
                continue
            if not corpus.has(rel):
                problems.append(f"{qid}: 팩에 없는 gold — {rel}")
                continue
            title = corpus.title(rel)
            if title and len(_norm(title)) >= TITLE_MIN_CHARS and _norm(title) in query_text:
                problems.append(f"{qid}: 질의가 정답 문서의 제목을 그대로 품고 있다 — {title!r}")

    for stratum, n in counts.items():
        if n != PER_STRATUM:
            problems.append(f"층 {stratum}: 답변가능 {n}건 (정확히 {PER_STRATUM}건이어야 한다)")

    return problems
