"""새로 저술한 라벨이 **쓸 수 있는 라벨인가** — 점수를 보기 전에 거는 검사.

⛔ **왜 필요한가 (2026-09-03).** `OPEN.md` A54 의 처분으로 Pack B 라벨 13건을 조직 문서 위에
다시 저술한다. 그 13건은 지금 **우리가 매주 고치는 khala 문서**에 걸려 있어서 문서를 손댈
때마다 만료된다. 옮기는 것은 맞는데, **13건을 다 쓰고 나서 게이트에 걸리면** 그때 고치는 것은
이미 점수를 본 뒤의 수정이 된다.

`ko_eval_labels.check` 가 보는 것(필수 칸·gold 존재·제목 베끼기·층)은 그대로 부르고, 여기 더하는
것은 **저술 규칙 둘**이다 (`tests/eval/answer-facts/README.md` §저술 규칙):

  ① 요구가 **gold 본문에서 성립**한다 — 없으면 어떤 답도 통과 못 하는 질의다.
  ② 요구가 **대조군 문서에서 불성립**한다 — 아무 문서에나 있는 낱말은 그 문서를 지목하지 못한다.

대조군이 그 라벨의 gold 자신이면 ②는 **반드시** 걸리고 그 실패는 아무 뜻이 없다. 첫 실행에서
실제로 그렇게 나왔다(후보 8건 중 4건). 그래서 그 조합은 판정하지 않고 건너뛰며, 건너뛴 것을
세어서 **판정을 하나도 못 받은 후보**는 통과로 적지 않는다 — 안 재고 통과시키는 것이 제일 나쁘다.

⛔ **시스템이 답하는지는 보지 않는다.** 그것을 보고 라벨을 고치면 현직 시스템의 표현에 채점기를
맞추는 것이고, 그 채점기로 잰 수는 다음 모델·다음 실험군에 불리하게 기운다(규칙 5). 여기 검사는
전부 **문서에 대한 것**이지 답변에 대한 것이 아니다.

    docker exec nexus-app python -m scripts.label_authoring_check \\
        --candidates /app/tests/eval/local/packb-replacements.yaml \\
        --control "동시성 #1 - ‘락’ 개념 정리"
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ko_eval_answer_quality import facts_present  # noqa: E402
from scripts.ko_eval_labels import STRATA, load  # noqa: E402

#: 저술 규칙이 요구하는 칸. `ko_eval_labels.REQUIRED_FIELDS` 와 겹치지만 여기서 먼저 본다 —
#: 칸이 없으면 아래 두 규칙을 **적용조차 못 하고**, 그때 나오는 오류는 원인을 안 가리킨다.
NEEDED = ("id", "query", "stratum", "gold", "must_contain", "rationale")


def shape_problems(q: dict) -> list[str]:
    """이 후보가 검사를 받을 수 있는 모양인가."""
    out = [f"{q.get('id', '?')}: 칸 없음 — {f}" for f in NEEDED if not q.get(f)]
    if (s := q.get("stratum")) and s not in STRATA:
        out.append(f"{q.get('id')}: 알 수 없는 층 — {s}")
    return out


def holds_in(groups, body: str) -> bool:
    """요구가 **전부** 이 본문에서 성립하는가. 채점기의 정본 함수를 쓴다(사본 금지)."""
    got = facts_present(groups, body)
    return bool(got) and all(got)


def control_is_the_gold(q: dict, control_key: str, control_title: str) -> bool:
    """대조군이 이 라벨의 gold 자신인가 — 그렇다면 규칙 ②는 판정이 아니라 동어반복이다."""
    return control_key in (q.get("gold") or []) or control_title in (q.get("gold") or [])


def authoring_problems(q: dict, gold_body: str, control_body: str | None) -> list[str]:
    """저술 규칙 둘. **문서에 대한 것이지 답변에 대한 것이 아니다.**

    `control_body` 가 None 이면 규칙 ②를 건너뛴다(대조군이 gold 자신인 경우).
    """
    out = []
    groups = q.get("must_contain")
    if not holds_in(groups, gold_body):
        missing = [" | ".join(g) for g, ok in zip(groups or [], facts_present(groups, gold_body))
                   if not ok]
        out.append(f"{q['id']}: 요구가 gold 본문에 없다 — {', '.join(missing)}"
                   " (어떤 답으로도 통과 못 하는 질의다)")
    if control_body is not None and holds_in(groups, control_body):
        out.append(f"{q['id']}: 요구가 **대조군에서도** 성립한다 —"
                   " 그 낱말은 이 문서를 지목하지 못한다")
    return out


def balance_after(existing: list[dict], removed: set[str], added: list[dict]) -> dict[str, int]:
    """교체 뒤 층별 답변가능 수. 40건은 다섯 층에 8건씩으로 지어졌다."""
    out = dict.fromkeys(STRATA, 0)
    for q in existing:
        if q.get("answerable") and q["id"] not in removed:
            out[q["stratum"]] = out.get(q["stratum"], 0) + 1
    for q in added:
        out[q["stratum"]] = out.get(q["stratum"], 0) + 1
    return out


async def _run(args) -> int:
    from nexus import db

    cands = load(args.candidates)
    queries = cands.get("queries") or []
    print(f"후보 {len(queries)}건 · 대조군 「{args.control}」\n")

    problems: list[str] = []
    for q in queries:
        problems += shape_problems(q)
    if problems:
        print("✗ 모양부터 틀렸다 — 아래를 고치기 전에는 저술 규칙을 적용할 수 없다:",
              *problems[:10], sep="\n  ")
        return 1

    pool = await db.get_pool()
    skipped: set[str] = set()
    async with pool.acquire() as con:
        control = await _body(con, args.tenant, title=args.control)
        control_key = await _key_of(con, args.tenant, args.control)
        if not control.strip():
            print(f"✗ 대조군 본문이 비었다 — 「{args.control}」")
            return 1
        for q in queries:
            gold = ""
            for key in q.get("gold") or []:
                gold += "\n" + await _body(con, args.tenant, key=key)
            if not gold.strip():
                problems.append(f"{q['id']}: gold 본문이 비었다 — {q.get('gold')}")
                continue
            same = control_is_the_gold(q, control_key, args.control)
            if same:
                skipped.add(q["id"])
            problems += authoring_problems(q, gold, None if same else control)
    await db.close_pool()

    for q in queries:
        bad = any(p.startswith(f"{q['id']}:") for p in problems)
        mark = "✗  " if bad else ("·· " if q["id"] in skipped else "OK ")
        print(f"  {mark} {q['id']:14s} {q['stratum']:9s} {q['query'][:44]}")
    if skipped:
        print(f"\n  ·· = 대조군이 이 라벨의 gold 자신이라 규칙 ②를 판정하지 않았다"
              f" ({len(skipped)}건) — **다른 대조군으로 한 번 더 돌려야 한다**")
    if problems:
        print("\n✗ 저술 규칙 위반:", *problems, sep="\n  ")
        return 1
    print("\n✓ 후보 전부가 저술 규칙을 통과했다 — 사람의 검토와 서명이 남았다")
    return 0


async def _key_of(con, tenant: str, title: str) -> str:
    row = await con.fetchrow(
        "SELECT split_part(source_uri, ':', 2) AS k FROM documents "
        "WHERE tenant = $1 AND status = 'active' AND title = $2", tenant, title)
    return row["k"] if row else ""


async def _body(con, tenant: str, *, title: str = "", key: str = "") -> str:
    where = "d.title = $2" if title else "split_part(d.source_uri, ':', 2) = $2"
    rows = await con.fetch(
        "SELECT c.chunk_text FROM documents d JOIN chunks c "
        "  ON c.doc_rid = d.rid AND c.tenant = d.tenant "
        f"WHERE d.tenant = $1 AND d.status = 'active' AND c.status = 'active' AND {where} "
        "ORDER BY c.chunk_index", tenant, title or key)
    return "\n".join(r["chunk_text"] for r in rows)


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidates", type=Path, required=True, help="새로 저술한 라벨 파일")
    p.add_argument("--control", required=True,
                   help="대조군 문서 제목 — 요구가 여기서 **불성립**해야 한다")
    p.add_argument("--tenant", default="default")
    return asyncio.run(_run(p.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
