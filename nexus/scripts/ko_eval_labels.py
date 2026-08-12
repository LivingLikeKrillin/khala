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

#: 질의가 **어디서 왔는가**. 자유 문자열이면 `from_user_query` 와 `from_user_queries` 가 나란히
#: 존재할 수 있고, 그러면 "저술된 질의와 실사용 질의를 영원히 구별한다"
#: (SPEC-nexus-query-text-retention §6.3)는 아무도 오타를 안 낸다는 가정이 된다.
#:
#:   authored_from_doc  문서를 읽고 지은 질의 — 천장이 붙어 있다(코퍼스가 반드시 답을 갖는다)
#:   adjudicated        판정 과정에서 고쳐 박은 질의
#:   from_user_query    사람이 실제로 던진 질문에서 온 질의 — 천장을 낮추는 유일한 재료
PROVENANCE = ("authored_from_doc", "adjudicated", "from_user_query")
BANNED_KEY = re.compile(r"token|lexeme|morpheme|term|expected_word", re.IGNORECASE)

DEFAULT_LABELS = Path(__file__).resolve().parents[1] / "tests" / "eval" / "ko" / "labels.yaml"
_HEADING = re.compile(r"^# (.+)$", re.MULTILINE)
_WS = re.compile(r"\s+")


def load(path: Path = DEFAULT_LABELS) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def judged_keys(q: dict) -> list[str]:
    """이 질의에서 **사람이 판정한** 문서들 — 양성(gold)과 음성(not_gold) 둘 다.

    둘 다 텍스트에 묶인다. 음성만 안 묶으면, 판정 뒤에 기계가 그림에서 읽은 텍스트가 들어와
    답을 담게 된 문서가 영원히 not_gold 로 남아 재판정이 막힌다.
    """
    return list(q.get("gold") or []) + list(q.get("not_gold") or [])


def _digest(value: str | None) -> str | None:
    """`sha256:<hex>` 와 `<hex>` 를 같은 값으로 본다.

    SPEC §3.3 의 예시는 `sha256:` 접두를 달고 있고 워크시트도 그렇게 뽑아 준다. 그런데 실행이
    비교 대상으로 넘기는 것은 `tenant_bodies()` 의 **맨 hex** 다. 접두를 그대로 두면 문자열이
    영원히 안 맞아 **40질의 전부가 만료된다** — 게이트는 통과하므로(키 존재만 본다) 라벨을
    실제로 서명해서 돌려 보기 전에는 보이지 않았다. 2026-08-12 에 첫 서명에서 터졌다.

    옛 테스트가 못 잡은 이유는 서명 쪽과 라이브 쪽을 **같은 가짜 문자열**로 만들어 비교했기
    때문이다. 두 쪽의 형식이 다를 수 있다는 것 자체가 표현되지 않았다.
    """
    return None if value is None else value.strip().removeprefix("sha256:")


def expired(labels: dict, live_bodies: dict[str, str]) -> dict[str, list[str]]:
    """서명된 본문과 **지금 재는 코퍼스**가 다른 질의 → {qid: [바뀐 문서키]}.

    라벨은 문서에 대한 주장이다("이 문서가 이 질의에 답하고, 답에는 이 사실이 있어야 한다").
    그 문서의 본문이 바뀌면 주장은 사라진 텍스트에 대한 것이 된다 — 2026-08-10 에 44장의
    스크린샷이 코퍼스에 들어오면서 실제로 그렇게 됐고, 게이트가 매니페스트만 보느라 못 봤다.
    """
    signed = ((labels.get("corpus") or {}).get("bodies") or {})
    out: dict[str, list[str]] = {}
    for q in labels.get("queries") or []:
        if not q.get("answerable"):
            continue
        moved = [k for k in judged_keys(q)
                 if _digest(signed.get(k)) != _digest(live_bodies.get(k))]
        if moved:
            out[q["id"]] = moved
    return out


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


def check(labels: dict, pack_dir, *, require_corpus_binding: bool = False) -> list[str]:
    """라벨 파일의 자 검사. 문제 목록을 돌려준다(빈 목록 = 통과).

    `pack_dir` 는 디스크 팩 경로이거나 `ManifestPack` 같은 코퍼스다.

    `require_corpus_binding` 은 **살아 있는 테넌트를 재는 실행**이 켠다(Pack B). 디스크 팩
    (Pack A)은 매니페스트 해시 가드가 이미 같은 일을 하므로 켜지 않는다 — 팩은 얼어 있고,
    움직이는 것은 테넌트다.
    """
    corpus = _as_corpus(pack_dir)
    problems: list[str] = []

    if not labels.get("revision"):
        problems.append("revision 없음 — 바닥값이 어느 라벨판에 박혔는지 말할 수 없다")
    if not labels.get("pack"):
        problems.append("pack 없음 — 어느 코퍼스에 대한 라벨인지 말할 수 없다")

    if require_corpus_binding:
        block = labels.get("corpus") or {}
        signed = block.get("bodies") or {}
        if not block.get("tenant"):
            problems.append("corpus.tenant 없음 — 어느 테넌트에 서명했는지 말할 수 없는 자다")
        if not signed:
            problems.append("corpus.bodies 없음 — 어느 본문에 서명했는지 말할 수 없는 자다")
        else:
            missing = sorted({k for q in (labels.get("queries") or []) if q.get("answerable")
                              for k in judged_keys(q)} - set(signed))
            if missing:
                problems.append(
                    "판정된 문서인데 서명된 본문 해시가 없다 — " + ", ".join(missing[:4]))

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

        if (prov := q.get("provenance")) is not None and prov not in PROVENANCE:
            problems.append(
                f"{qid}: 알 수 없는 provenance — {prov!r} (기대값: {', '.join(PROVENANCE)})")

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

        if q.get("authored_by") == "agent":
            if not (q.get("reviewed_by") or "").strip():
                problems.append(
                    f"{qid}: 에이전트가 쓴 라벨에 reviewed_by 가 없다 — 사람의 검토 기록이 곧 게이트다")
            # **서명은 리비전에 묶인다.** 검토가 끝난 뒤 판단 재료가 한 줄 더 붙어도 예전 게이트는
            # 통과시켰다 — `reviewed_by` 만 보니까. 2026-08-08 에 실제로 그럴 뻔했다: 서명 뒤에
            # `must_contain` 을 40건에 추가했고, 그건 "이 답에 이 사실이 있어야 한다" 는 새 판단이다.
            elif q.get("reviewed_revision") != labels.get("revision"):
                problems.append(
                    f"{qid}: 검토 리비전 {q.get('reviewed_revision')!r} ≠ 라벨 리비전 "
                    f"{labels.get('revision')!r} — 서명 이후 판단 재료가 바뀌었다. 다시 검토받아라")

        # `not_gold` = 사람이 읽고 **답을 담지 않는다고 판정한** 문서. 판정의 음성 절반이 없으면
        # 같은 인용이 매 실행 미판정으로 되살아나 게이트가 절대 안 닫힌다
        # (SPEC-nexus-answer-quality-ruler §3.2).
        not_gold = q.get("not_gold") or []
        for rel in not_gold:
            if not isinstance(rel, str) or not rel.endswith(".md"):
                problems.append(f"{qid}: not_gold 는 팩 상대 경로여야 한다 — {rel!r}")
            elif not corpus.has(rel):
                problems.append(f"{qid}: 팩에 없는 not_gold — {rel}")
        if overlap := sorted(set(not_gold) & set(gold)):
            problems.append(f"{qid}: 같은 문서가 gold 이자 not_gold 다 — {', '.join(overlap)}")

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
