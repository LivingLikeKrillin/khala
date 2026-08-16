"""답변 품질을 실제로 재는 실행기 — 검색이 아니라 **답**을 본다.

이 리포는 검색을 엄격하게 재 왔고 답변은 한 번도 안 쟀다. 이것이 그 첫 실행이다.

**관문을 먼저 통과해야 결과로 친다** (`ko_eval_packb_run.py` 와 같은 이유): 라벨 게이트가
막으면 숫자를 내지 않는다. 관문이 뒤에 있으면 숫자를 보고 자를 고치게 된다.

**LLM 을 부른다 — 돈이 든다.** 질의 하나에 한 번, 기본 40건. `--limit` 로 줄일 수 있고, 무엇을
부를지는 `NEXUS_LLM_PROVIDER` 가 정한다(키 없이 도는 claude-code 브리지 포함).

리포트는 `tests/eval/local/` 에만 쓴다 — 답변 본문이 다른 조직의 정책 내용을 담는다.

    docker exec nexus-app python scripts/ko_eval_answer_run.py --limit 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ko_eval_answer_quality import aggregate, grid, refuses, score_answer  # noqa: E402
from nexus.llm.dev_spend import Spend, paid_flag_help, require_free  # noqa: E402
from scripts.ko_eval_labels import ManifestPack, check, expired, load  # noqa: E402
from nexus.auth.clearance import LEVELS  # noqa: E402
from scripts.ko_eval_packb import MANIFEST, tenant_bodies  # noqa: E402

LOCAL_DIR = Path(__file__).resolve().parents[1] / "tests" / "eval" / "local"
DEFAULT_LABELS = LOCAL_DIR / "packb-labels.yaml"
DEFAULT_MANIFEST = MANIFEST


def resolve_paths(labels_path: Path, tag: str) -> tuple[Path, Path]:
    """(리포트, 누적로그). 이름은 **팩**에서, 자리는 **라벨 파일 옆**에서 온다.

    리포트 파일명에 tag 가 들어간다. 예전에는 고정 경로 하나여서 매 실행이 앞 실행을 덮었고,
    2026-08-12 에 충분성 런의 격자(파라메트릭 2건이 어느 질의였는지)가 40초 뒤 다음 런에 덮여
    복구 불가능해졌다. 누적 로그는 요약과 `ok` 맵만 담으므로 그것으로도 되살릴 수 없었다.

    **접두는 라벨의 `pack` 필드에서 딴다.** 파일 이름에서 따던 첫 판은 Pack A 라벨
    (`answer-labels.yaml`)에서 `answer-answer-runs.jsonl` 을 만들었다 — 파일 이름은 사람이
    붙이는 것이고 팩 이름은 라벨이 이미 선언하는 것이다(게이트가 `pack` 을 요구한다).

    **자리는 라벨 파일이 있는 디렉터리다.** 전에는 무조건 `tests/eval/local/` (gitignore)로
    갔는데, Pack A 는 공개 코퍼스에 대한 공개 라벨이라 결과만 커밋 못 하는 것이 앞뒤가 안 맞았다.
    결과는 자기 라벨 옆에 산다 — 라벨이 커밋되는 자리면 결과도 커밋할 수 있고, 라벨이 gitignore
    안이면 결과도 거기 남는다.
    """
    import yaml

    try:
        pack = (yaml.safe_load(labels_path.read_text(encoding="utf-8")) or {}).get("pack") or ""
    except OSError:
        # 없는 파일이면 실행은 어차피 라벨 적재에서 멈춘다. 경로 계산이 그보다 먼저 죽으면
        # 진짜 원인("라벨 파일이 없다")이 스택 아래로 숨는다.
        pack = ""
    prefix = pack.split("-")[0] or labels_path.stem.removesuffix("-labels")
    suffix = f"-{tag}" if tag else ""
    out = labels_path.parent
    #: 반복 실행은 덮어쓰지 않고 쌓는다. **같은 입력에 같은 답이 안 나오기 때문이다** — 두 실행이
    #: grounded 에서 1, 인용 0개에서 2 흔들렸다(2026-08-08). 그 폭을 모르면 모델 간 차이를 잡음과
    #: 구별할 수 없고, 구별 못 하는 비교는 비교가 아니다.
    return (out / f"{prefix}-answer-quality{suffix}.json",
            out / f"{prefix}-answer-runs.jsonl")


def append_run(args, llm, summary: dict, scores: list, sufficiency: dict[str, str]) -> None:
    """회차를 누적 로그에 **덧붙인다**. 리포트는 tag 별로 갈라지지만 변동은 한 파일에 모여야 한다.

    변동 폭을 모르면 두 모델의 차이가 잡음인지 실력인지 못 가리고, 질의별 `ok` 까지 남겨야
    다수결이 된다.

    **충분성 격자도 여기 남는다.** 격자는 콘솔에만 찍혔고 리포트는 다음 실행이 덮었다 —
    2026-08-12 에 "파라메트릭 2건" 이 어느 질의였는지 40초 만에 복구 불가능해졌다. 가장
    진단적인 산출물이 가장 안 남는 구조였다.

    함수로 떼어 둔 이유는 **배선을 행동으로 걸 수 있게** 하려는 것이다. 2026-08-08 에 누적 쓰기가
    편집 실패로 통째로 빠진 채 3회 실행이 다 돌았고(`--tag` 는 먹었으므로 새 버전처럼 보였다),
    그때 박은 검사는 소스에 `RUNS.open(` 문자열이 있는지 보는 것이었다 — 이름을 바꾸자 깨졌고,
    애초에 문자열은 그 코드가 **돌았다는** 것을 증명하지 않는다.
    """
    args.runs.parent.mkdir(parents=True, exist_ok=True)
    with args.runs.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({
            "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tag": args.tag, "model": getattr(llm, "model", None), "summary": summary,
            "labels": Path(args.labels).name, "tenant": args.tenant,
            "ok": {s.qid: s.ok for s in scores},
            "sufficiency": sufficiency or None,
            "grid": grid(scores, sufficiency) if sufficiency else None,
        }, ensure_ascii=False) + "\n")


#: 등급 순서는 **정본 하나**에서만 온다 (`nexus.auth.clearance`). 여기 사본을 두었더니 곧바로
#: 갈라졌다: 사본은 `CONFIDENTIAL` 을 알았고 Postgres enum 은 `PUBLIC < INTERNAL < RESTRICTED`
#: 셋뿐이라, 그 이름으로 `--clearance` 를 주면 게이트는 통과시키고 SQL 이 캐스트에서 터졌다.
#: 오늘만 두 번째다 — 채점 규칙도 사본이었다가 하나로 합쳤다(`facts_present`).


async def unreadable_gold(con, labels: dict, tenant: str, clearance: str) -> dict[str, list[str]]:
    """이 등급으로 **읽을 수 없는** gold 를 가진 질의 → {qid: ["문서 (등급)"]}.

    2026-08-12 에 q002 가 4런 연속 실패했고 원인은 랭킹이 아니었다: gold 인
    `tutorials/security/apparmor.md` 가 경로 규칙(`**/security/**`)으로 RESTRICTED 인데
    실행은 INTERNAL 로 돌아, `classification <= clearance` 가 그 문서를 원천 배제했다.
    **시스템이 정책을 지킨 것을 자가 검색 실패로 적고 있었다.**

    라벨은 못 읽는 문서를 gold 로 가질 수 없다 — 그런 질의는 통과가 불가능하고, 불가능한
    질의를 섞어 낸 총점은 시스템이 아니라 등급 설정을 재는 수다.
    """
    if clearance not in LEVELS:
        raise ValueError(f"알 수 없는 clearance: {clearance!r} (아는 등급: {', '.join(LEVELS)})")
    ceiling = LEVELS.index(clearance)
    rows = await con.fetch(
        "SELECT split_part(source_uri, ':', 2) AS key, classification FROM documents "
        "WHERE tenant = $1 AND status = 'active'", tenant)
    cls = {r["key"]: r["classification"] for r in rows}
    out: dict[str, list[str]] = {}
    for q in labels.get("queries") or []:
        if not q.get("answerable"):
            continue
        gold = [k for k in (q.get("gold") or []) if k in cls]
        bad = [k for k in gold if LEVELS.index(cls[k]) > ceiling]
        if bad:
            # 전부 못 읽으면 그 질의는 **통과 불가능**하다. 일부만이면 남은 gold 로 통과할 수
            # 있으니 알리되 막지 않는다 — 막을 것은 숫자를 거짓으로 만드는 것뿐이다.
            out[q["id"]] = [f"{k} ({cls[k]})" for k in bad] + (
                [] if len(bad) < len(gold) else ["**통과 불가능**"])
    return out


def gate_reasons(summary: dict, expired_qids: list[str] | None = None) -> list[str]:
    """총점을 내면 안 되는 이유들. 비어 있어야 실행이 결과가 된다.

    관문을 **뒤**에 두면 숫자를 보고 자를 고치게 되므로, 이 판단은 총점 출력 이전에 한다.
    """
    reasons = []
    if qids := summary.get("unadjudicated_qids"):
        reasons.append(f"미판정 {len(qids)}건: {', '.join(qids)}")
    if expired_qids:
        reasons.append(f"만료된 라벨 {len(expired_qids)}건: {', '.join(expired_qids[:6])}"
                       + (" …" if len(expired_qids) > 6 else ""))
    return reasons


def _write_report(args, labels, llm, summary, rows, *, partial: bool,
                  expired_qids: list[str] | None = None, controls: list | None = None) -> None:
    """리포트는 막힌 실행에서도 쓴다 — **판정할 재료가 리포트 안에 있기 때문이다.**

    막혔다는 사실은 파일 안에 `partial` 로 남는다. 사람의 기억이 아니라 파일이 그것을 말해야
    한다(SPEC-nexus-answer-quality-ruler §3.2·§3.3). 총점만 없다.
    """
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(
        {"ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "labels_revision": labels["revision"], "tenant": args.tenant,
         "tag": args.tag, "llm_model": getattr(llm, "model", None),
         "partial": partial, "expired": expired_qids or [],
         "controls": controls or [], "summary": summary, "queries": rows},
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if partial:
        print(f"\n기록: {args.report}  (partial — 총점 없음, 판정 재료만)")


async def _run(args) -> int:
    from nexus import db
    from nexus.providers.embedding import embedding_service_from_config
    from nexus.providers.llm import LLMService
    from nexus.search import hybrid
    from nexus.search.evidence_packet import assemble_packet, format_for_llm
    from nexus.llm.answer import generate_answer

    labels = load(args.labels)
    if problems := check(labels, ManifestPack(args.manifest), require_corpus_binding=True):
        print("✗ 라벨 게이트 실패 — 측정 이전에 자가 틀렸다:", *problems[:4], sep="\n  ")
        return 1

    # **서명된 테넌트가 아니면 시작하지 않는다.** 다른 테넌트의 해시는 이 라벨에 대해 아무것도
    # 말해 주지 않으므로, 만료도 통과도 판정할 수 없다.
    signed_tenant = (labels.get("corpus") or {}).get("tenant")
    if signed_tenant != args.tenant:
        print(f"✗ 라벨은 테넌트 {signed_tenant!r} 에 서명됐는데 재는 것은 {args.tenant!r} 이다")
        return 1

    titles = {d["key"]: d["title"] for d in json.loads(args.manifest.read_text(encoding="utf-8"))["docs"]}
    queries = [q for q in labels["queries"] if q.get("answerable")][:args.limit]
    print(f"✓ 관문 통과 — 라벨 revision {labels['revision']} · 질의 {len(queries)}건\n")

    svc, llm = embedding_service_from_config(), LLMService()
    if args.model:
        llm.model = args.model            # 브리지가 payload 의 model 을 그대로 넘긴다
    # **질의당 LLM 을 한두 번 부른다.** 유료 백엔드면 여기서 멈춘다 — 2026-08-13 에 하루치
    # 평가가 유료로 나갔고, 브리지는 그때도 리포에 있었다 (nexus/llm/dev_spend.py).
    require_free(llm, allow_paid=args.paid, what="답변 품질 실행")
    spend = Spend()
    pool = await db.get_pool()
    # **팩이 아니라 테넌트의 제목이다.** 팩은 2026-08-07 에 얼린 116건이고 테넌트는 적재마다
    # 자란다. 지난주 들어온 문서를 인용한 정답을 오답으로 세면 SPEC §1.2 가 새 문서에 되살아난다.
    async with pool.acquire() as con:
        known_titles = {r["title"] for r in await con.fetch(
            "SELECT DISTINCT title FROM documents "
            "WHERE tenant = $1 AND status = 'active' AND is_quarantined = false", args.tenant)}
        live = await tenant_bodies(con, args.tenant)
        blind = await unreadable_gold(con, labels, args.tenant, args.clearance)

    # ── 이 등급으로 읽을 수 없는 gold ────────────────────────────────────────
    # 측정 **이전에** 막는다. 통과 불가능한 질의를 섞어 낸 총점은 시스템이 아니라 등급 설정을
    # 재는 수이고, 그 실패는 랭킹 결함처럼 보인다.
    if blind:
        impossible = {q: d for q, d in blind.items() if "**통과 불가능**" in d}
        print(f"⚠ 이 등급({args.clearance})으로 읽을 수 없는 gold — 질의 {len(blind)}건")
        print("  검색은 `classification <= clearance` 를 지킨다. 그 실패는 랭킹이 아니라 등급이다.")
        for qid, docs in list(blind.items())[:8]:
            print(f"    {qid:8s} {', '.join(docs)}")
        if impossible:
            print(f"\n✗ 그중 {len(impossible)}건은 gold 를 **전부** 못 읽어 통과가 불가능하다: "
                  f"{', '.join(impossible)}")
            print("  불가능한 질의를 섞어 낸 총점은 시스템이 아니라 등급 설정을 재는 수다.")
            print("  고치는 법: --clearance 를 올리거나(예: RESTRICTED), 라벨의 gold 를 바꿔라.\n")
            return 1
        print("  남은 gold 로 통과할 수 있어 실행은 계속한다 — 다만 그 라벨은 절반이 죽어 있다.\n")

    # ── 라벨이 서명된 본문과 지금 재는 본문이 같은가 ──────────────────────────
    stale = expired(labels, {k: v["sha"] for k, v in live.items()})
    if stale:
        signed = (labels.get("corpus") or {}).get("bodies") or {}
        print(f"✗ 만료된 라벨 {len(stale)}건 — 서명된 본문이 지금 코퍼스에 없다.")
        print("  라벨은 문서에 대한 주장이다. 본문이 바뀌면 그 주장은 사라진 텍스트에 대한 것이다.")
        for qid, keys in list(stale.items())[:8]:
            for k in keys:
                now = live.get(k)
                if now is None:
                    print(f"    {qid:12s} {titles.get(k, k)[:28]:28s} 코퍼스에서 사라졌다")
                    continue
                seen = "서명됨" if k in signed else "서명 없음"
                print(f"    {qid:12s} {titles.get(k, k)[:28]:28s} "
                      f"{now['chunks']:2d}청크 {now['chars']:6d}자 "
                      f"(기계가 읽은 청크 {now['machine_read']}) — {seen}")
        if len(stale) > 8:
            print(f"    … 외 {len(stale) - 8}건")
        print("  사람이 바뀐 문서를 다시 읽고 rationale·must_contain·gold·not_gold 를 확인한 뒤")
        print("  revision 을 올려 다시 서명해야 한다. 만료된 질의는 채점하지 않는다.\n")
        queries = [q for q in queries if q["id"] not in stale]

    scores, rows, controls = [], [], []
    sufficiency: dict[str, str] = {}
    try:
        for q in queries:
            result = await hybrid.hybrid_search(q["query"], tenant=args.tenant, clearance=args.clearance,
                                                top_k=10, embedding_svc=svc)
            if result.degraded:
                print(f"✗ 다리가 죽었다({result.degraded}) — 이 상태의 숫자는 결과가 아니다")
                return 1
            packet = await assemble_packet(result.hits, result.graph)
            ans = await generate_answer(q["query"], packet, llm_svc=llm)
            spend.add(ans.usage, kind="answer")
            # **첫 실패에서 멈춘다.** 계속 돌면 실패한 실행의 집계가 리포트로 남고, 그것을 나중에
            # '답변 품질' 로 읽게 된다 — 실제로 3건 중 2건이 근거 덤프 덕에 '사실 통과' 로 찍혔다.
            if ans.llm_failed:
                print(f"✗ {q['id']}: LLM 호출이 실패했다 — 이 상태의 숫자는 결과가 아니다.")
                print("  답변 자리에는 근거 원문이 들어가므로 사실 검사가 거저 통과한다.")
                print(f"  받은 것: {ans.answer[:80]}…")
                return 1
            s = score_answer(q["id"], ans.answer, ans.citations,
                             {titles[g] for g in q["gold"]}, q.get("must_contain") or [],
                             abstained=ans.abstained, llm_failed=ans.llm_failed,
                             not_gold_titles={titles[g] for g in q.get("not_gold") or []},
                             known_titles=known_titles)
            scores.append(s)

            # ── 축 1: 근거가 충분했는가 ────────────────────────────────────
            # 이것 없이는 기권이 **정직한 기권**(검색 결함)인지 **과잉 기권**(답할 수 있었는데
            # 안 함)인지 못 가른다. 오답도 마찬가지로 생성 결함과 환각이 안 갈린다.
            # 판정자는 답변을 보지 않는다 — 질의와 근거만 본다(nexus/llm/sufficiency.py).
            if args.sufficiency:
                from nexus.llm.sufficiency import judge
                v = await judge(q["query"], format_for_llm(packet), llm)
                spend.add(None, kind="sufficiency")
                sufficiency[q["id"]] = v.label.value

            rows.append({"qid": q["id"], "grounded": s.grounded, "cites_gold": s.cites_gold,
                         "facts": s.facts, "outcome": s.outcome, "refused": s.refused,
                         "sufficiency": sufficiency.get(q["id"]), "answer": ans.answer})
            mark = "OK " if s.ok else "   "
            print(f"{mark} {q['id']:12s} 근거{'✓' if s.grounded else '✗'} "
                  f"정답문서{'✓' if s.cites_gold else '✗'} 사실{'✓' if s.has_facts else '✗'}"
                  f"  인용 {s.n_citations}")

        # ── 대조군: 코퍼스가 답을 못 가진 질의에서 답변자는 거절해야 한다 ──────
        # 이 팔이 없으면 기권 탐지기에는 **양성 대조군이 없다**. 라벨엔 5건이 일주일째 있었고
        # 한 번도 안 돌렸다 — 돌리자마자 규칙 하나가 죽었다(SPEC §1.4).
        for q in ([q for q in labels["queries"] if not q.get("answerable")]
                  if args.controls else []):
            result = await hybrid.hybrid_search(q["query"], tenant=args.tenant, clearance=args.clearance,
                                                top_k=10, embedding_svc=svc)
            ans = await generate_answer(q["query"], await assemble_packet(result.hits, result.graph),
                                        llm_svc=llm)
            if ans.llm_failed:
                print(f"✗ {q['id']}: LLM 호출 실패 — 대조군도 결과가 아니다")
                return 1
            controls.append({"qid": q["id"], "refused": refuses(ans.answer),
                             "chars": len(ans.answer), "answer": ans.answer})
            print(f"{'OK ' if controls[-1]['refused'] else '‼  '} {q['id']:12s} "
                  f"거절{'✓' if controls[-1]['refused'] else '✗'}  {len(ans.answer)}자")
    finally:
        await db.close_pool()

    a = aggregate(scores)
    o = a["outcomes"]

    # ── 대조군이 거절하지 않았다면, 그것은 **환각 판정이 아니라 재판정 대상**이다 ──
    # 코퍼스가 답을 얻었을 수도 있고(2026-08-10 에 스크린샷 44장이 그렇게 했다) 답변자가
    # 지어냈을 수도 있다. 자는 둘을 못 가른다 — 그러니 이름만 부르고 멈춘다.
    if answered := [c["qid"] for c in controls if not c["refused"]]:
        print(f"\n  ‼ 대조군 {len(answered)}건이 거절하지 않았다: {', '.join(answered)}")
        print("    코퍼스가 답을 얻었는지(라벨을 answerable 로 뒤집어야 한다) 답변자가 지어냈는지")
        print("    자는 못 가른다. 사람이 근거를 읽어야 한다.")
    elif controls:
        print(f"\n  대조군 {len(controls)}/{len(controls)} 거절 — 기권 탐지기의 양성 대조군은 살아 있다")

    # ── 판정할 거리는 총점보다 먼저 나온다 ────────────────────────────────────
    # **미판정은 오답이 아니다.** 사실을 배달했고 인용이 해소되는데 라벨이 그 문서를 판정한 적이
    # 없으면 이 자는 모른다 — 모르는 채로 총점을 찍으면 그 총점이 판정을 대신하게 된다.
    if a["adjudication_candidates"]:
        print("\n  판정 대기 — 라벨이 한 번도 읽지 않은 문서를 인용했다:")
        for qid, cited in a["adjudication_candidates"].items():
            flag = "‼" if qid in a["unadjudicated_qids"] else " "
            print(f"   {flag} {qid:12s} {', '.join(cited)}")
    if reasons := gate_reasons(a, sorted(stale)):
        print(f"\n✗ **총점을 내지 않는다** — {' · '.join(reasons)}")
        print("  사람이 그 문서를 읽고 라벨의 gold 또는 not_gold 로 보내야 닫힌다.")
        print("  (판정 없이 나온 총점은 부풀려진 수다 — SPEC-nexus-answer-quality-ruler §3.2)")
        _write_report(args, labels, llm, a, rows, partial=True,
                      expired_qids=sorted(stale), controls=controls)
        return 1

    print(f"\n  정답 {o['correct']}   오답 {o['incorrect']}   기권 {o['abstained']}"
          f"   (잴 수 없음 {o['unmeasurable']})")
    if o["abstained"]:
        print(f"    기권: {', '.join(a['abstained_qids'])}")
    if o["incorrect"]:
        print(f"    오답: {', '.join(a['incorrect_qids'])}")
    if sufficiency:
        print("\n  근거 충분성 × 결과")
        for cell, info in grid(scores, sufficiency).items():
            print(f"    {cell:26s} {info['n']:2d}  {info['means']}")
    else:
        print("  (근거 충분성 미측정 — --sufficiency 를 주면 기권/오답의 원인이 갈린다)")
    print(f"\n  근거 있음      {a['grounded']}/{a['queries']}   (인용 0개: {a['no_citation_at_all']})")
    print(f"  정답 문서 인용  {a['cites_gold']}/{a['queries']}")
    print(f"  사실 포함      {a['facts_present']}/{a['facts_measurable']}")
    print(f"  셋 다          {a['all_three']}/{a['queries']}")
    if a["failed"]:
        print(f"  실패: {', '.join(a['failed'])}")

    _write_report(args, labels, llm, a, rows, partial=False, controls=controls)

    append_run(args, llm, a, scores, sufficiency)

    # 커밋 여부는 **라벨이 사는 자리**가 정한다. 조직 문서 위의 라벨(Pack B)은 gitignore 안에
    # 있고 그 결과도 거기 남는다. 공개 코퍼스 위의 라벨(Pack A)은 리포에 있고, 결과도 올릴 수
    # 있다 — 그게 "누구나 재현한다" 의 나머지 절반이다. 문구를 고정해 두면 둘 중 하나에 거짓말한다.
    local = "eval/local" in args.report.as_posix()
    print(f"\n기록: {args.report}  (답변 본문 — {'커밋하지 않는다' if local else '커밋 가능'})")
    print(f"      {args.runs}  (실행별 누적 — 잡음 폭은 이것으로만 나온다)")
    # **이 실행이 쓴 것.** 하니스 지출은 search_log 에 안 들어간다(평가 트래픽이 "답변 1회 비용"
    # 추정기를 오염시키므로) — 그래서 여기서 스스로 말한다.
    print(f"\n  {spend.summary()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=40, help="LLM 을 부르는 횟수 — 돈이 든다")
    ap.add_argument("--tag", default="", help="이 실행의 이름(모델 팔·반복 회차 구분용)")
    # 라벨셋·매니페스트·테넌트가 인자인 이유: 하니스가 Pack B 에 못박혀 있으면 "다른 코퍼스에서도
    # 같은 수가 나오나" 를 물을 수 없고, 물을 수 없는 질문은 한계가 아니라 사각이 된다.
    ap.add_argument("--labels", type=Path, default=DEFAULT_LABELS, help="라벨 파일")
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="팩 매니페스트")
    ap.add_argument("--tenant", default="default", help="재는 테넌트(라벨의 서명 테넌트와 같아야 한다)")
    # 등급은 **재는 조건**이지 상수가 아니다. 하드코딩돼 있던 동안, 그 등급으로 못 읽는 문서를
    # gold 로 가진 질의는 어떤 질의문으로도 통과할 수 없었고 자는 그것을 "검색 실패" 로 적었다.
    ap.add_argument("--clearance", default="INTERNAL",
                    help="이 등급으로 읽을 수 있는 것만 검색된다. gold 가 이보다 위면 실행이 거부된다")
    ap.add_argument("--model", default="", help="브리지에 넘길 모델. 비우면 백엔드 기본값")
    ap.add_argument("--paid", action="store_true", help=paid_flag_help())
    ap.add_argument("--controls", action="store_true",
                    help="답변불가 5건도 돌린다 — 기권 탐지기의 **양성 대조군**이다. "
                         "거절하지 않는 대조군은 라벨 재판정 대상이다")
    ap.add_argument("--sufficiency", action="store_true",
                    help="근거 충분성도 판정한다(질의당 LLM 1회 추가). 이것 없이는 기권이 "
                         "정직한 기권인지 과잉 기권인지, 오답이 생성 결함인지 환각인지 못 가른다")
    args = ap.parse_args(argv)
    args.report, args.runs = resolve_paths(args.labels, args.tag)
    if not os.getenv("DATABASE_URL"):
        print("✗ DATABASE_URL 이 없다")
        return 1
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
