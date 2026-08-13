"""형식 요청 준수를 잰다 (SPEC-nexus-multi-turn-narration §5, U1).

사용자가 "세 줄로" 라고 했을 때 답이 세 줄인가. 판정은 전부 문자열 연산이고
(`nexus/search/format_compliance.py`) LLM 판정자를 쓰지 않는다 — 판정자가 흔들리면 자가 흔들린다.

**첫 실행은 성능이 아니라 잡음 측정이다** (§5.1). 답변 생성은 LLM 이라 같은 입력에 같은 출력이
안 나온다. 같은 조건 10회를 돌려 폭을 먼저 보고, 그 폭보다 작은 차이는 승리로 세지 않는다.
검색 SPEC 은 5회로 시작했다가 폭을 과소평가했다(5회 0.021 vs 10회 0.061).

**두 팔을 한 코드 버전에서 나란히 잰다.** U2 는 인자 하나로 켜지므로 그 인자를 팔로 만들 수
있고, 그러면 배포를 갈아 끼우는 대신 같은 실행 안에서 대조가 선다 — 시간·모델·DB 가 두
측정 사이에서 움직일 여지가 없다. 1턴 답변은 이력이 없어 두 팔이 정의상 같으므로 공유한다
(그래야 `shorter` 판정의 기준선이 팔마다 달라지지 않는다).

    docker exec nexus-app python scripts/ko_eval_format.py --runs 10
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.search.format_compliance import check  # noqa: E402
from nexus.search.rewrite import TIMEOUT_S as REWRITE_TIMEOUT_S  # noqa: E402

KO_DIR = Path(__file__).resolve().parents[1] / "tests" / "eval" / "ko"
DEFAULT_CASES = KO_DIR / "format-requests.yaml"


#: 팔. **한 코드 버전에서 둘 다 잰다** — 배포를 갈아 끼우며 재면 두 측정 사이에 코드 말고도
#: 시간·모델·DB 가 함께 움직이고, 그 차이는 사후에 분리되지 않는다. U2 는 인자 하나로 켜지므로
#: 그 인자를 팔로 만드는 것이 가장 정직한 대조다.
ARMS = ("baseline", "u2")


async def answer(query: str, history, *, tenant: str, clearance: str, svc, llm,
                 u2: bool = False, rewrite_timeout: float) -> tuple[str, bool]:
    """오늘의 답변 경로 그대로. **자가 프로덕션 경로를 재구현하지 않는다.**

    `u2=True` 면 답변자가 사용자 원문도 받는다 (SPEC-nexus-multi-turn-narration §3.1).
    이력이 없으면 재작성도 없어 두 팔이 **정의상 같다** — 그래서 1턴은 팔을 안 나눈다.

    돌려주는 둘째 값은 **재작성이 실제로 문장을 바꿨는가**다. 안 바꿨으면 `user_query == query`
    라 두 팔이 산술적으로 같은 프롬프트를 받는다 — 그 행은 대조가 아니라 정의상 무승부이고,
    총점에 섞으면 효과를 0 쪽으로 희석한다.
    """
    from nexus.llm.answer import generate_answer
    from nexus.search import hybrid
    from nexus.search.evidence_packet import assemble_packet
    from nexus.search.rewrite import W_ORIGINAL, W_REWRITTEN, rewrite

    rw = await rewrite(query, history, llm, timeout_s=rewrite_timeout)
    channels = None if not rw.changed else [(rw.query, W_REWRITTEN), (query, W_ORIGINAL)]
    r = await hybrid.hybrid_search(rw.query, tenant=tenant, clearance=clearance, top_k=10,
                                   embedding_svc=svc, route="hybrid_only", channels=channels)
    if r.degraded:
        raise SystemExit(f"✗ 다리가 죽었다({r.degraded}) — 이 상태의 숫자는 결과가 아니다")
    result = await generate_answer(rw.query, assemble_packet(r.hits, r.graph), llm_svc=llm,
                                   user_query=query if u2 else None)
    if result.llm_failed:
        raise SystemExit(f"✗ LLM 실패({result.llm_failure_reason}) — 이 숫자는 결과가 아니다")
    return result.answer, rw.changed


async def one_run(cases: dict, *, tenant: str, clearance: str, svc, llm,
                  arms: tuple[str, ...], rewrite_timeout: float) -> dict:
    """한 회차. 팔별 형식 준수 여부 + 대조군 답변 길이 + **팔이 갈렸는지**.

    **1턴 답변은 팔 사이에 공유한다.** 이력이 없으면 두 팔의 코드 경로가 같으니 두 번 부르는
    것은 돈과 시간만 쓰는 게 아니라 해롭다: `shorter` 판정의 기준선이 팔마다 달라져, 재는 것이
    "원문 전달의 효과" 가 아니라 "두 1턴 답변의 길이 차" 가 섞인 값이 된다.
    """
    out: dict = {arm: {"format": {}, "control": {}} for arm in arms}
    out["applicable"] = {}
    for case in cases["cases"]:
        first, _ = await answer(case["first"], [], tenant=tenant, clearance=clearance,
                                svc=svc, llm=llm, rewrite_timeout=rewrite_timeout)
        history = [{"role": "user", "content": case["first"]},
                   {"role": "assistant", "content": first}]
        changed_any = False
        for arm in arms:
            second, changed = await answer(
                case["followup"], history, tenant=tenant, clearance=clearance,
                svc=svc, llm=llm, u2=(arm == "u2"), rewrite_timeout=rewrite_timeout)
            changed_any = changed_any or changed
            mark = "" if changed else "  ⚠재작성없음"
            if case.get("control"):
                # 대조군은 형식을 안 잰다. 오늘과 같은 답이 나오는지를 본다 — 길이로 근사한다.
                out[arm]["control"][case["id"]] = len(second)
                print(f"  {case['id']:5s} {arm:8s} 대조군  {len(second)}자{mark}")
            else:
                ok = check(case["check"], second, first)
                out[arm]["format"][case["id"]] = ok
                print(f"  {case['id']:5s} {arm:8s} {case['check']:16s}"
                      f" {'통과' if ok else '실패'}  ({len(first)}자 → {len(second)}자){mark}")
        out["applicable"][case["id"]] = changed_any
    return out


async def _run(args) -> int:
    from nexus import db
    from nexus.providers.embedding import embedding_service_from_config
    from nexus.providers.llm import LLMService

    cases = yaml.safe_load(args.cases.read_text(encoding="utf-8"))
    n_fmt = sum(1 for c in cases["cases"] if not c.get("control"))
    arms = ARMS if args.arm == "both" else (args.arm,)
    print(f"형식 요청 {n_fmt}건 · 대조군 {len(cases['cases']) - n_fmt}건 · {args.runs}회"
          f" · 팔 {'+'.join(arms)}\n")

    svc, llm = embedding_service_from_config(), LLMService()
    runs = []
    try:
        for i in range(args.runs):
            print(f"── run {i + 1}/{args.runs} " + "─" * 40)
            runs.append(await one_run(cases, tenant=args.tenant, clearance=args.clearance,
                                      svc=svc, llm=llm, arms=arms,
                                      rewrite_timeout=args.rewrite_timeout))
    finally:
        await db.close_pool()

    # 재작성이 한 번도 안 걸린 행은 **정의상 무승부**다. 총점에는 남기되(자칭 금지) 따로 센다.
    n_skipped = sum(1 for r in runs for c in cases["cases"]
                    if not c.get("control") and not r["applicable"].get(c["id"]))
    if n_skipped:
        print(f"\n  ⚠ 재작성이 문장을 안 바꾼 행 {n_skipped}/{n_fmt * len(runs)} — 그 행에서는"
              f" 두 팔의 프롬프트가 같다(무승부). 효과는 0 쪽으로 희석된다.")

    summary: dict = {}
    for arm in arms:
        rates = [sum(r[arm]["format"].values()) / (n_fmt or 1) for r in runs]
        spread = max(rates) - min(rates)
        summary[arm] = {"rates": rates, "spread": spread, "median": statistics.median(rates),
                        "min": min(rates), "max": max(rates)}
        print(f"\n  [{arm}] 형식 준수율  {[f'{x:.2f}' for x in rates]}")
        print(f"  중앙 {statistics.median(rates):.3f} · 최소 {min(rates):.3f}"
              f" · 최대 {max(rates):.3f} · **폭 {spread:.3f}**")

        # 어떤 유형이 지속적으로 실패하는가 — 총점보다 진단적이다.
        print("  질의별 통과 횟수")
        for case in cases["cases"]:
            if case.get("control"):
                continue
            hits = sum(1 for r in runs if r[arm]["format"].get(case["id"]))
            print(f"    {case['id']:5s} {case['check']:16s} {hits}/{len(runs)}")

    if len(arms) == 2:
        _verdict(summary, runs, cases)
    else:
        print("\n  이 폭보다 작은 차이는 승리로 세지 않는다 (SPEC §5.1).")

    out = args.report or (KO_DIR / f"format-compliance-{'-'.join(arms)}.json")
    out.write_text(json.dumps({
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "revision": cases["revision"], "tenant": args.tenant, "runs": args.runs,
        # 계측 설정도 결과의 일부다 — 재작성 타임아웃이 다르면 다른 실험이다.
        "rewrite_timeout_s": args.rewrite_timeout, "rows_without_rewrite": n_skipped,
        "arms": list(arms), "summary": summary, "detail": runs,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\n기록: {out}")
    return 0


def _verdict(summary: dict, runs: list, cases: dict) -> None:
    """§5.3 판정. 규칙은 **구현 전에** SPEC 에 등록됐다 — 여기서 만들지 않는다.

    채택: 형식 준수율이 잡음 폭 이상 오르고, **대조군에 회귀가 없다.**
    기각: 대조군이 회귀하면 켜지 않는다 — 형식은 편의이고 회귀는 품질이다.
    """
    base, u2 = summary["baseline"], summary["u2"]
    #: 문턱의 폭은 **두 팔 중 큰 쪽**을 쓴다. 작은 쪽을 쓰면 잡음이 승리로 세진다.
    spread = max(base["spread"], u2["spread"])
    gain = u2["median"] - base["median"]

    print("\n── §5.3 판정 " + "─" * 40)
    print(f"  중앙 준수율   baseline {base['median']:.3f} → u2 {u2['median']:.3f}"
          f"  (차 {gain:+.3f})")
    print(f"  잡음 폭       {spread:.3f}  ← 이보다 작은 차이는 승리가 아니다")

    # 대조군 — 형식 요청이 없는 후속. 길이로 근사한다(자가 재는 것이 형식뿐이라 그렇다).
    ctrl_ids = [c["id"] for c in cases["cases"] if c.get("control")]
    print("  대조군(길이)  ", end="")
    for cid in ctrl_ids:
        b = statistics.median([r["baseline"]["control"][cid] for r in runs])
        u = statistics.median([r["u2"]["control"][cid] for r in runs])
        print(f"{cid} {b:.0f}→{u:.0f}자  ", end="")
    print()

    if gain > spread:
        print("  → 형식 준수는 잡음 폭 이상 올랐다. 대조군 회귀 여부는 사람이 본다.")
    else:
        print("  → 차이가 잡음 폭 이하다. **승리로 세지 않는다.**")


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    ap.add_argument("--tenant", default="ko_eval_packa")
    ap.add_argument("--clearance", default="INTERNAL")
    ap.add_argument("--runs", type=int, default=10,
                    help="SPEC §5.1: 첫 실행은 성능이 아니라 잡음 측정이다")
    ap.add_argument("--arm", choices=(*ARMS, "both"), default="both",
                    help="both 면 한 코드 버전에서 두 팔을 나란히 잰다(1턴 답변은 공유)")
    ap.add_argument("--rewrite-timeout", type=float, default=REWRITE_TIMEOUT_S,
                    help="재작성 상한(초). 프로덕션 기본은 6초지만 dev 브리지는 그보다 느려서 "
                         "그대로 두면 재작성이 대부분 타임아웃하고, 그러면 두 팔이 같아져 "
                         "실험이 아무것도 재지 않는다. 값은 리포트에 기록된다")
    ap.add_argument("--report", type=Path, default=None)
    args = ap.parse_args(argv)
    import os
    if not os.getenv("DATABASE_URL"):
        print("✗ DATABASE_URL 이 없다")
        return 1
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
