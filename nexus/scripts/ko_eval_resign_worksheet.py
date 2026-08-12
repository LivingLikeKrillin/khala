"""재서명 워크시트 — 사람이 무엇에 서명하는지 **읽을 수 있게** 펼쳐 놓는다.

SPEC-nexus-answer-quality-ruler §3.3 은 재서명을 "바뀐 문서를 다시 읽고 rationale·must_contain·
gold·not_gold 를 확인하는 사람의 행위" 로 정의한다. 그런데 라이브 해시를 계산해 주는 도구만 있고
**무엇이 바뀌었는지** 보여 주는 도구가 없으면, 실제로 일어나는 일은 계산된 `corpus:` 블록을 통째로
붙여넣는 것이다 — §4 가 이름을 붙여 둔 실패("읽지 않고 재서명하도록 훈련시킨다") 그 자체다.

그래서 이 스크립트는 해시를 **주지 않는다**. 얼린 스냅샷 테넌트(`ko_eval_packb`)와 지금 재는
테넌트의 **본문을 청크 단위로 대조**해서 들어온 텍스트·나간 텍스트를 보여 주고, 각 질의의
`must_contain` 요구가 **지금 본문에서 여전히 성립하는지**를 기계적으로 표시한다. 서명용 블록은
맨 끝 부록에 있고, 그 앞을 읽어야 도달한다.

기계적 표시는 판정이 아니다. `must_contain` 이 지금 본문에 없다는 것은 라벨이 틀렸다는 뜻일 수도,
문서가 답을 잃었다는 뜻일 수도 있다. 워크시트는 그 둘을 가르지 않는다 — 사람이 가른다.

출력은 `tests/eval/local/` 안이다. 다른 조직의 정책 문서 본문을 담으므로 리포에 들어가지 않는다
(SPEC-nexus-korean-retrieval-eval §4.1).

    python -m scripts.ko_eval_resign_worksheet
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ko_eval_packb import (  # noqa: E402
    LOCAL_DIR,
    MANIFEST,
    _body_hash,
    _collect,
)
from scripts.ko_eval_answer_quality import _norm, facts_present  # noqa: E402
from scripts.ko_eval_labels import judged_keys, load  # noqa: E402

LABELS = LOCAL_DIR / "packb-labels.yaml"
POOL = LOCAL_DIR / "pool-adjudication.json"
OUT = LOCAL_DIR / "resign-worksheet.md"

#: 본문 발췌는 잘라서 싣는다 — 워크시트는 읽히려고 있는 문서이고, 청크 하나가 4천 자인 것도 있다.
EXCERPT = 700


def _requirement_state(groups: list[list[str]] | None, body: str) -> list[tuple[str, bool, str]]:
    """`must_contain` 각 항목이 **지금 본문에서** 성립하는가 → (표시, 성립, 어느 표기가 맞았나).

    성립 여부는 **채점기의 함수**(`facts_present`)가 정한다. 여기서 관대한 사본을 쓰면 워크시트가
    '본문에 있다' 고 말한 요구를 자가 답변에서 떨어뜨리는 조합이 생기고, 사람은 자기가 확인한
    것과 다른 것에 서명하게 된다. 맞은 표기만 여기서 다시 찾는다 — 보여 주려고.
    """
    ok = facts_present(groups, body)
    normalized = _norm(body)
    out = []
    for group, present in zip(groups or [], ok):
        hit = next((alt for alt in group if _norm(alt) in normalized), "")
        out.append((" | ".join(group), present, hit))
    return out


def _diff_chunks(before: list[tuple], after: list[tuple]) -> tuple[list[tuple], list[tuple]]:
    """(들어온 청크, 나간 청크). 정규화한 본문을 키로 맞춘다 — 청크 번호는 재청킹하면 다 밀린다."""
    b_keys = [_norm(t) for _, _, t in before]
    a_keys = [_norm(t) for _, _, t in after]
    matcher = difflib.SequenceMatcher(None, b_keys, a_keys, autojunk=False)
    added, removed = [], []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            removed += before[i1:i2]
        if tag in ("replace", "insert"):
            added += after[j1:j2]
    return added, removed


async def _tiers(con, tenant: str) -> dict[tuple[str, int], str]:
    """`{(문서키, 청크번호): 출처등급}` — 기계가 그림에서 읽은 텍스트인지 보이게 (ADR-0010 §2)."""
    rows = await con.fetch(
        "SELECT split_part(d.source_uri, ':', 2) AS key, c.chunk_index, c.provenance_tier "
        "FROM documents d JOIN chunks c ON c.doc_rid = d.rid AND c.tenant = d.tenant "
        "WHERE d.tenant = $1 AND d.status = 'active' AND c.status = 'active' "
        "  AND d.is_quarantined = false AND c.is_quarantined = false", tenant)
    return {(r["key"], r["chunk_index"]): r["provenance_tier"] for r in rows}


def _excerpt(text: str) -> str:
    t = _norm(text)
    return t if len(t) <= EXCERPT else t[:EXCERPT] + " …"


def _body(doc: dict | None) -> str:
    return "\n".join(t for _, _, t in (doc or {}).get("chunks", []))


async def _run(args) -> int:
    from nexus import db

    labels = load(LABELS)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    signed = {d["key"]: d for d in manifest["docs"]}
    titles = {k: d["title"] for k, d in signed.items()}

    pool_obj = await db.get_pool()
    async with pool_obj.acquire() as con:
        live = await _collect(con, args.tenant)
        frozen = await _collect(con, args.snapshot)
        tiers = await _tiers(con, args.tenant)
        live_titles = {r["title"] for r in await con.fetch(
            "SELECT DISTINCT title FROM documents "
            "WHERE tenant = $1 AND status = 'active' AND is_quarantined = false", args.tenant)}
    await db.close_pool()

    if not frozen:
        print(f"snapshot tenant {args.snapshot!r} is empty: no body to diff against")
        return 2

    live_sha = {k: _body_hash([t for _, _, t in v["chunks"]]) for k, v in live.items()}
    queries = [q for q in labels["queries"] if q.get("answerable")]

    #: 라벨이 **판정한** 문서만 묶인다 (§3.3: 코퍼스 전체를 묶으면 적재마다 45건이 전부 만료된다).
    judged: dict[str, list[dict]] = {}
    for q in queries:
        for key in judged_keys(q):
            judged.setdefault(key, []).append(q)

    drifted = {k: v for k, v in judged.items()
               if live_sha.get(k) != (signed.get(k) or {}).get("body_sha256")}
    stale_qids = sorted({q["id"] for qs in drifted.values() for q in qs})

    L: list[str] = []
    w = L.append
    w("# 재서명 워크시트 — packb-labels.yaml")
    w("")
    w(f"- 생성: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    w(f"- 라벨 revision **{labels['revision']}** · 팩 `{manifest['pack']}` "
      f"(얼린 시각 {manifest['frozen_at']})")
    w(f"- 재는 테넌트 `{args.tenant}` · 대조하는 스냅샷 테넌트 `{args.snapshot}`")
    w(f"- 판정된 문서 **{len(judged)}**건 중 본문이 달라진 것 **{len(drifted)}**건 "
      f"→ 만료되는 질의 **{len(stale_qids)} / {len(queries)}**")
    w("")
    w("> 이 워크시트는 판정하지 않는다. 기계가 셀 수 있는 것(무슨 텍스트가 들어오고 나갔나, "
      "`must_contain` 이 지금 본문에서 성립하나)만 펼쳐 놓는다. 성립하지 않는 요구가 "
      "**라벨의 결함인지 문서의 변화인지**는 읽는 사람이 정한다.")
    w("")

    # ── A. 본문이 달라진 문서 ────────────────────────────────────────────────
    w("## A. 본문이 달라진 문서")
    w("")
    for key in sorted(drifted):
        before, now = frozen.get(key), live.get(key)
        title = titles.get(key) or (now or {}).get("title") or key
        w(f"### {title}")
        w("")
        w(f"`{key}`")
        w("")
        if now is None:
            w("**코퍼스에서 사라졌다.** 이 문서를 gold 로 쓰는 질의는 gold 를 옮기거나 "
              "질의를 은퇴시켜야 한다.")
            w("")
            w(f"- 딸린 질의: {', '.join(q['id'] for q in drifted[key])}")
            w("")
            continue

        sig = signed.get(key) or {}
        n_mr = sum(1 for _, idx, _ in now["chunks"]
                   if tiers.get((key, idx)) == "machine_read")
        w(f"- 청크 {sig.get('chunks', '?')} → **{len(now['chunks'])}** · "
          f"본문 {sig.get('body_chars', '?')}자 → **{sum(len(t) for _, _, t in now['chunks'])}**자")
        w(f"- 기계가 그림에서 읽은 청크: **{n_mr}** / {len(now['chunks'])} (ADR-0010 §2)")
        w(f"- 딸린 질의: {', '.join(q['id'] for q in drifted[key])}")
        w("")

        added, removed = _diff_chunks(before["chunks"] if before else [], now["chunks"])
        if added:
            w(f"**들어온 텍스트 ({len(added)}청크)**")
            w("")
            for section, idx, text in added:
                tier = tiers.get((key, idx), "?")
                mark = " ⚠️기계판독" if tier == "machine_read" else ""
                w(f"- `#{idx}` {section or '(섹션 없음)'} · {tier}{mark}")
                w(f"  > {_excerpt(text)}")
            w("")
        if removed:
            w(f"**사라진 텍스트 ({len(removed)}청크)**")
            w("")
            for section, idx, text in removed:
                w(f"- `#{idx}` {section or '(섹션 없음)'}")
                w(f"  > {_excerpt(text)}")
            w("")
        if not added and not removed:
            w("청크 경계는 그대로인데 해시가 다르다 — 청크 안의 문자가 바뀌었다는 뜻이다. "
              "본문을 직접 열어 봐야 한다.")
            w("")

    # ── B. 만료된 질의 ───────────────────────────────────────────────────────
    w("## B. 만료된 질의 — 확인하고 고칠 것")
    w("")
    w("`must_contain` 은 **모든 항목**이 성립해야 하고, 항목 안의 후보는 **하나만** 맞으면 된다. "
      "아래 ✓/✗ 는 그 항목이 *지금 gold 본문에* 있는지만 본다 — 답변이 아니라 본문이다.")
    w("")
    for qid in stale_qids:
        q = next(x for x in queries if x["id"] == qid)
        golds = list(q.get("gold") or [])
        body = "\n".join(_body(live.get(k)) for k in golds)
        w(f"### {qid} · {q['stratum']}")
        w("")
        w(f"**질의** {q['query']}")
        w("")
        w(f"- gold: {', '.join(f'{titles.get(k, k)} (`{k}`)' for k in golds) or '(없음)'}")
        if q.get("not_gold"):
            w(f"- not_gold: {', '.join(titles.get(k, k) for k in q['not_gold'])}")
        w(f"- rationale: {q.get('rationale', '')}")
        w("")
        state = _requirement_state(q.get("must_contain"), body)
        if state:
            w("| must_contain 항목 | 지금 본문 | 맞은 표기 |")
            w("|---|---|---|")
            for label, ok, hit in state:
                w(f"| {label} | {'✓' if ok else '**✗ 없음**'} | {hit} |")
            w("")
        broken = [label for label, ok, _ in state if not ok]
        if broken:
            w(f"⚠️ **{len(broken)}개 항목이 지금 본문에 없다** — 라벨이 사라진 텍스트를 "
              "요구하고 있거나, 문서가 답을 잃었다.")
            w("")
        w("- [ ] rationale 그대로 / 고침: ")
        w("- [ ] must_contain 그대로 / 고침: ")
        w("- [ ] gold 그대로 / 고침: ")
        w("- [ ] not_gold 추가: ")
        w("")

    # ── C. 미판정 인용 ───────────────────────────────────────────────────────
    if POOL.exists():
        pool_rows = json.loads(POOL.read_text(encoding="utf-8"))
        open_rows = [r for r in pool_rows if r.get("candidates")]
        w("## C. 미판정 인용 — gold 승격 / not_gold")
        w("")
        w("답변이 인용했지만 아무도 판정하지 않은 문서들. 판정이 없으면 `unadjudicated` 로 남아 "
          "총점이 계속 막힌다(§3.2).")
        w("")
        for r in open_rows:
            cands = [c for c in r["candidates"] if c.get("title") not in (r.get("gold_titles") or [])]
            if not cands:
                continue
            w(f"### {r['qid']}")
            w("")
            w(f"**질의** {r.get('query', '')}")
            w(f"- 현재 gold: {', '.join(r.get('gold_titles') or []) or '(없음)'}")
            w("")
            for c in cands:
                live_mark = "" if c.get("title") in live_titles else "  ⚠️테넌트에 없는 제목"
                w(f"- **{c.get('title')}** (`{c.get('key')}`, 순위 {c.get('rank')}){live_mark}")
                for s in (c.get("snippets") or [])[:2]:
                    w(f"  > {_excerpt(s)}")
                w("  - [ ] gold 승격 · [ ] not_gold · [ ] 판단 보류")
            w("")

    # ── 부록: 서명 블록 ──────────────────────────────────────────────────────
    w("## 부록 — 위를 다 읽은 뒤에 붙여넣을 `corpus:` 블록")
    w("")
    w("**A·B 를 읽지 않았다면 여기서 멈춰라.** 이 블록을 붙여넣는 행위가 "
      "'바뀐 본문을 읽고 라벨이 여전히 옳다고 확인했다'는 서명이다. revision 도 함께 올린다.")
    w("")
    w("```yaml")
    w("corpus:")
    w(f"  tenant: {args.tenant}")
    w(f"  signed_at: '{datetime.now(timezone.utc).date().isoformat()}'")
    w("  bodies:")
    for key in sorted(judged):
        sha = live_sha.get(key)
        w(f"    {key}: sha256:{sha}" if sha else f"    # {key}: 코퍼스에 없다 — gold 를 고쳐라")
    w("```")
    w("")

    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"judged docs {len(judged)}, drifted {len(drifted)}, expired queries {len(stale_qids)}")
    print(f"worksheet: {OUT}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tenant", default="default", help="지금 재는 테넌트")
    p.add_argument("--snapshot", default="ko_eval_packb", help="얼린 스냅샷 테넌트")
    return asyncio.run(_run(p.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
