"""재서명 워크시트 — 사람이 무엇에 서명하는지 **읽을 수 있게** 펼쳐 놓는다.

SPEC-nexus-answer-quality-ruler §3.3 은 재서명을 "바뀐 문서를 다시 읽고 rationale·must_contain·
gold·not_gold 를 확인하는 사람의 행위" 로 정의한다. 그런데 라이브 해시를 계산해 주는 도구만 있고
**무엇이 바뀌었는지** 보여 주는 도구가 없으면, 실제로 일어나는 일은 계산된 `corpus:` 블록을 통째로
붙여넣는 것이다 — §4 가 이름을 붙여 둔 실패("읽지 않고 재서명하도록 훈련시킨다") 그 자체다.

그래서 이 스크립트는 해시를 **주지 않는다**. 얼린 스냅샷 테넌트(`ko_eval_packb`)와 지금 측정하는
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
from scripts.ko_eval_labels import _digest, judged_keys, load  # noqa: E402

LABELS = LOCAL_DIR / "packb-labels.yaml"
POOL = LOCAL_DIR / "pool-adjudication.json"

#: 본문 발췌는 잘라서 싣는다 — 워크시트는 읽히려고 있는 문서이고, 청크 하나가 4천 자인 것도 있다.
EXCERPT = 700


def signed_bodies(labels: dict, manifest: dict | None) -> tuple[dict[str, str | None], str]:
    """**서명된 본문 해시**와 그 값이 어디서 왔는지 → ({문서키: hex}, 출처 이름).

    ⛔ 정본은 라벨 자신의 `corpus.bodies` 다. 관문(`ko_eval_labels.expired`)이 보는 것이 그것이고,
    워크시트가 다른 것을 보면 사람은 **관문이 막지도 않은 문서**를 다시 읽게 된다.

    실측 2026-09-03 에 실제로 갈라져 있었다. Pack B 의 판정 문서 20건에 대해 매니페스트 기준으로는
    15건이 달라졌고 `corpus.bodies` 기준으로는 8건이었다 — 매니페스트는 2026-08-07 에 얼린 팩의
    해시이고 라벨은 2026-08-12 에 다시 서명됐기 때문이다. 워크시트는 그 차이만큼 사람에게 없는
    일을 시키고 있었다. 매니페스트는 **라벨이 결속을 안 들고 있을 때만** 쓴다(옛 라벨).
    """
    inline = (labels.get("corpus") or {}).get("bodies") or {}
    if inline:
        return {k: _digest(v) for k, v in inline.items()}, "corpus.bodies"
    docs = (manifest or {}).get("docs") or []
    return {d["key"]: _digest(d.get("body_sha256")) for d in docs}, "manifest"


#: `signed_bodies` 의 출처를 사람이 읽는 말로. 워크시트 머리에 **어느 해시로 판정했는지**가 적혀야
#: 한다 — 그것이 관문과 같은지 다른지가 이 문서의 신뢰도 전부다.
SOURCE_TEXT = {"corpus.bodies": "라벨의 `corpus.bodies` (관문이 보는 것과 같다)",
               "manifest": "매니페스트 (라벨에 `corpus.bodies` 가 없다)"}


def _requirement_state(groups: list[list[str]] | None, body: str) -> list[tuple[str, bool, str]]:
    """`must_contain` 각 항목이 **지금 본문에서** 성립하는가 → (표시, 성립, 어느 표기가 맞았나).

    성립 여부는 **채점기의 함수**(`facts_present`)가 정한다. 여기서 관대한 사본을 쓰면 워크시트가
    '본문에 있다' 고 말한 요구를 채점기가 답변에서 떨어뜨리는 조합이 생기고, 사람은 자기가 확인한
    것과 다른 것에 서명하게 된다. 맞은 표기만 여기서 다시 찾는다 — 보여 주려고.
    """
    ok = facts_present(groups, body)
    normalized = _norm(body)
    out = []
    for group, present in zip(groups or [], ok):
        hit = next((alt for alt in group if _norm(alt) in normalized), "")
        # 후보를 `|` 로 이으면 마크다운 표의 칸이 갈라진다 — `["잠금해제", "해금"]` 이 실제로
        # 칸 넷짜리 줄을 만들었다(2026-09-03). 표를 읽으라고 만든 문서에서 표가 깨지면
        # 사람은 그 줄을 안 읽는다.
        out.append((" 또는 ".join(f"`{alt}`" for alt in group), present, hit))
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

    labels = load(args.labels)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8")) if args.manifest.exists() else None
    signed_sha, signed_from = signed_bodies(labels, manifest)
    # 매니페스트의 청크·글자 수는 **매니페스트가 곧 서명일 때만** '이전' 이다. 라벨이 자기
    # 결속을 들고 있으면 그 매니페스트는 다른 시점의 다른 팩일 수 있고(키가 겹쳐도), 그 수를
    # '이전' 이라고 적으면 일어나지 않은 변경을 보여 준다.
    signed = ({d["key"]: d for d in (manifest or {}).get("docs", [])}
              if signed_from == "manifest" else {})
    titles = {d["key"]: d["title"] for d in (manifest or {}).get("docs", [])}

    pool_obj = await db.get_pool()
    async with pool_obj.acquire() as con:
        live = await _collect(con, args.tenant)
        frozen = await _collect(con, args.snapshot)
        tiers = await _tiers(con, args.tenant)
        live_titles = {r["title"] for r in await con.fetch(
            "SELECT DISTINCT title FROM documents "
            "WHERE tenant = $1 AND status = 'active' AND is_quarantined = false", args.tenant)}
    await db.close_pool()

    live_sha = {k: _body_hash([t for _, _, t in v["chunks"]]) for k, v in live.items()}
    #: 스냅샷이 **서명된 그 본문**을 들고 있을 때만 '이전' 이라고 부른다. 해시가 다른 스냅샷을
    #: 나란히 놓으면 워크시트는 일어나지 않은 변경을 보여 주고, 사람은 그것을 읽고 서명한다 —
    #: 아무것도 안 보여 주는 것보다 나쁘다.
    frozen_sha = {k: _body_hash([t for _, _, t in v["chunks"]]) for k, v in frozen.items()}
    titles.update({k: v["title"] for k, v in live.items() if v.get("title")})
    queries = [q for q in labels["queries"] if q.get("answerable")]

    #: 라벨이 **판정한** 문서만 묶인다 (§3.3: 코퍼스 전체를 묶으면 적재마다 45건이 전부 만료된다).
    judged: dict[str, list[dict]] = {}
    for q in queries:
        for key in judged_keys(q):
            judged.setdefault(key, []).append(q)

    drifted = {k: v for k, v in judged.items() if live_sha.get(k) != signed_sha.get(k)}
    stale_qids = sorted({q["id"] for qs in drifted.values() for q in qs})
    #: 서명된 본문을 실제로 들고 있는 스냅샷 문서만 '이전' 이 된다.
    has_before = {k for k in drifted if frozen_sha.get(k) == signed_sha.get(k)}

    L: list[str] = []
    w = L.append
    w(f"# 재서명 워크시트 — {args.labels.name}")
    w("")
    w(f"- 생성: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    w(f"- 라벨 revision **{labels['revision']}** · 팩 `{labels.get('pack', '?')}`"
      + (f" · 매니페스트 얼린 시각 {manifest['frozen_at']}" if manifest else ""))
    w(f"- 서명된 해시의 출처: **{SOURCE_TEXT[signed_from]}**")
    w(f"- 측정하는 테넌트 `{args.tenant}` · 대조하는 스냅샷 테넌트 `{args.snapshot}` "
      f"— 서명된 본문을 실제로 들고 있는 문서 **{len(has_before)}/{len(drifted)}**")
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
        before_chunks = sig.get("chunks") or (len(before["chunks"]) if key in has_before else "?")
        w(f"- 청크 {before_chunks} → **{len(now['chunks'])}** · "
          f"본문 {sig.get('body_chars', '?')}자 → **{sum(len(t) for _, _, t in now['chunks'])}**자")
        w(f"- 기계가 그림에서 읽은 청크: **{n_mr}** / {len(now['chunks'])} (ADR-0010 §2)")
        w(f"- 딸린 질의: {', '.join(q['id'] for q in drifted[key])}")
        w(f"- 서명된 해시 `{(signed_sha.get(key) or '(없음)')[:12]}` → 지금 "
          f"`{(live_sha.get(key) or '')[:12]}`")
        w("")

        if key not in has_before:
            # 스냅샷의 본문이 서명된 그 본문이 아니면, 나란히 놓는 순간 일어나지 않은 변경을
            # 보여 준다. 결속은 해시만 저장하므로 옛 본문은 어디에도 없다 — 없다고 적는다.
            w(f"⚠️ **이전 본문이 없다.** 스냅샷 테넌트 `{args.snapshot}` 의 이 문서는 "
              f"`{(frozen_sha.get(key) or '(없음)')[:12]}` 로 서명된 해시와 다르다. 결속은 해시만"
              " 저장하므로 옛 본문은 복원되지 않는다 — 아래 B 의 요구 성립 여부와 지금 본문으로"
              " 판단해야 한다.")
            w("")
            continue

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
        # **이 라벨셋의 질의만.** 판정 풀은 Pack B 의 것이고, 라벨 인자가 생기기 전에는 어떤
        # 라벨을 펼치든 그 풀이 통째로 실렸다 — 정책 라벨의 워크시트에 `pb-loan-01` 이 나왔다
        # (2026-09-03). 사람에게 자기 목록이 아닌 판정거리를 내미는 것은 목록을 못 믿게 만든다.
        mine = {q["id"] for q in labels.get("queries") or []}
        open_rows = [r for r in pool_rows if r.get("candidates") and r.get("qid") in mine]
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

    out = args.out or (LOCAL_DIR / f"resign-worksheet-{args.labels.stem}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"judged docs {len(judged)}, drifted {len(drifted)}, expired queries {len(stale_qids)}")
    print(f"signed hashes from: {signed_from}")
    print(f"before-body available for {len(has_before)}/{len(drifted)} drifted docs")
    print(f"worksheet: {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tenant", default="default", help="지금 측정하는 테넌트")
    p.add_argument("--snapshot", default="ko_eval_packb", help="얼린 스냅샷 테넌트")
    # 라벨셋이 인자인 이유: 결속은 `packb-labels.yaml` 만의 것이 아니다. 정책·멀티홉 라벨도 같은
    # `corpus:` 블록을 들고 같은 관문에 막히는데, 그것들을 펼칠 방법이 없어 사람이 읽을 것이
    # 없었다. 산출물 이름도 라벨에서 딴다 — 고정 경로 하나면 두 번째 실행이 첫 번째를 덮는다.
    p.add_argument("--labels", type=Path, default=LABELS, help="라벨 파일")
    p.add_argument("--manifest", type=Path, default=MANIFEST,
                   help="팩 매니페스트(제목·청크 수 용도). 없으면 라이브에서 읽는다")
    p.add_argument("--out", type=Path, default=None, help="워크시트 경로. 비우면 라벨 이름에서")
    return asyncio.run(_run(p.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
