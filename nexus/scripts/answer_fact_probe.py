"""답변 사실 채점 — **답이 옳은가**를 측정한다. Recall 이 못 보는 자리.

규칙은 측정 전에 `tests/eval/answer-facts/README.md` 에 박혔다.

검색 평가 하니스(`Recall@10`)는 *정답 문서가 왔는가* 만 측정한다. 2026-08-26 에 그 한계가 끝까지 드러났다 —
Recall 이 **오르는 동안 답변이 나빠졌다**(정답 숫자는 왔는데 낡은 숫자를 무효화하는 문장이 안
와서, 답변이 낡은 값을 정본으로 읽었다). 여기서는 답변 텍스트에 **그 값이 나오는가**를 본다.

**LLM 심판을 쓰지 않는다.** 판정은 정규화 부분일치이고, 그래서 무르다 — 오탐이 아니라 **누락**을
잡는 평가 하니스로 쓴다. 기권도 실패로 센다: 코퍼스가 답을 갖고 있는데 못 낸 것이다.

    docker exec nexus-app python -m scripts.answer_fact_probe \
        --labels /app/tests/eval/local/answer-facts.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

from nexus import db  # noqa: E402
from scripts.ko_eval_answer_quality import (  # noqa: E402
    asserts_all,
    asserts_current_not_stale,
    asserts_value,
    facts_present,
    label_is_usable,
)

#: 기본 코퍼스. `--tenant` 로 바꿀 수 있다 — 합친 코퍼스(`merge_probe`)와 견주려면
#: **같은 라벨·같은 채점기**로 양쪽을 돌려야 하기 때문이다. 채점은 답변 텍스트만 보므로
#: 테넌트가 달라도 판정 규칙은 그대로다.
TENANT = "default"
CLEARANCE = "INTERNAL"


def _norm(s: str) -> str:
    """공백·쉼표를 지운다 — `4,000` 과 `4000`, `최대 1` 과 `최대1` 이 같아야 한다."""
    return re.sub(r"[\s,]+", "", s or "")


def summary_lines(rows: list[dict], for_signature: bool) -> list[str]:
    """요약 줄. **서명 전에는 비율을 만들지 않는다.**

    한 번 찍힌 수는 인용된다 — 이 리포는 라벨 문제를 그렇게 물려받았다. 그래서 이 함수는
    `for_signature` 일 때 어떤 분수도 내지 않는다. 조립을 함수로 뺀 이유는 그 성질을
    **소스 문자열이 아니라 출력으로** 확인하기 위해서다.
    """
    n = len(rows)
    p = sum(r["pass"] for r in rows)
    a = sum(r["asserted"] for r in rows)
    if for_signature:
        return ["",
                "  서명 전이므로 총점을 내지 않는다. 위의 질의별 결과와 답변만 읽어라.",
                "  확인할 것: (1) 지금 값이 정말 지금 값인가 (2) 낡은 값이 정말 낡았는가",
                "  서명하면 라벨 파일의 signed_off 를 true 로 바꾸고 다시 돌린다."]
    out = ["",
           f"  1판 언급(부분일치) **{p}/{n} = {p / n:.3f}**",
           f"  2판 주장(선두·결론)  **{a}/{n} = {a / n:.3f}**"
           f"   — 값은 담고도 결론을 안 낸 답변 {p - a}건"]
    mismatch = [r["id"] for r in rows if r["pass"] != r["mentioned"]]
    if mismatch:
        out.append(f"  ⚠ 두 정규화가 갈린 질의: {mismatch}")
    out.append(f"  낡은 값이 언급된 답변 {sum(1 for r in rows if r['distractor_seen'])}건 "
               "(판정에 안 들어감 — 좋은 답도 기각하며 언급한다)")
    return out


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--tenant", default=TENANT,
                    help="어느 코퍼스에 물을 것인가 (기본: default)")
    ap.add_argument("--for-signature", action="store_true",
                    help="서명 전 라벨을 사람이 읽으려고 돌린다 — 답변은 내고 **점수는 안 낸다**")
    ap.add_argument("--out", default="")
    ap.add_argument("--only", default="", help="쉼표로 구분한 id — 그것만 돈다")
    ap.add_argument("--fill", choices=("on", "off"), default="",
                    help="절 채움(`search.section_fill`) 강제. 비우면 config 그대로")
    ap.add_argument("--save-answers", default="",
                    help="답변 **원문**을 적을 파일. 조직 문서의 사실이므로 gitignore 된 곳에만")
    args = ap.parse_args()

    labels = yaml.safe_load(Path(args.labels).read_text(encoding="utf-8"))
    queries = labels["queries"]
    # ⛔ **서명 전 라벨로 점수를 내지 않는다** (README §3판). 키가 없는 옛 라벨 파일은
    #    이미 서명된 것으로 읽는다 — 새 규칙이 옛 측정을 소급해서 막으면 안 된다.
    signed = bool(labels.get("signed_off", True))
    if not signed and not args.for_signature:
        print("  이 라벨은 아직 서명 전이다 — 점수를 내지 않는다.")
        print("  사람이 확인할 것: (1) 지금 값이 정말 지금 값인가 "
              "(2) 낡은 값이 정말 낡았는가.")
        print("  답변을 읽으려면 --for-signature 로 돌려라.")
        return 1
    # **막힌 라벨은 돌리지 않는다.** 값을 못 정한 이유가 코퍼스 쪽에 있으면(예: 현재 모양을
    # 적은 문서가 없다), 그것을 0점으로 세는 순간 문서 부채가 답변 품질 점수로 둔갑한다.
    blocked = [q for q in queries if q.get("blocked_on")]
    for q in blocked:
        print(f"  {q['id']:4} — 건너뜀: {q['blocked_on']}")
    queries = [q for q in queries if not q.get("blocked_on")]
    if args.only:
        want = {q.strip() for q in args.only.split(",") if q.strip()}
        queries = [q for q in queries if q["id"] in want]

    await db.get_pool()
    try:
        from nexus.api import _load_config
        from nexus.llm.answer import generate_answer
        from nexus.providers.embedding import embedding_service_from_config
        from nexus.providers.llm import LLMService
        from nexus.search import hybrid
        from nexus.search.evidence_packet import assemble_packet

        svc, cfg = embedding_service_from_config(), _load_config()
        if args.fill:
            cfg.setdefault("search", {})["section_fill"] = (args.fill == "on")
        print(f"  절 채움: {cfg.get('search', {}).get('section_fill')}", flush=True)
        rows, answers = [], []
        for q in queries:
            r = await hybrid.hybrid_search(q["query"], tenant=args.tenant, clearance=CLEARANCE,
                                           top_k=10, embedding_svc=svc, config=cfg)
            packet = await assemble_packet(r.hits, r.graph, tenant=args.tenant, fill=r.fill)
            ans = await generate_answer(q["query"], packet, LLMService(),
                                        confidence=r.confidence)
            text = getattr(ans, "answer", None) or getattr(ans, "text", "") or str(ans)
            nt = _norm(text)
            expect = q.get("expect") or []
            ok = any(_norm(e) in nt for e in expect)
            # 2판 — **주장했는가**. 같은 값을 담고도 결론을 안 낸 답변을 1판은 통과시킨다.
            said = asserts_value(expect, text)
            # 3판 — 종합·최신성. 라벨이 그 모양일 때만 판정이 바뀐다.
            if q.get("expect_all"):
                ok = all(any(_norm(x) in nt for x in ([e] if isinstance(e, str) else e))
                         for e in q["expect_all"])
                said = asserts_all(q["expect_all"], text)
            elif q.get("superseded") is not None:
                usable, why = label_is_usable(expect, q["superseded"])
                if not usable:
                    print(f"  {q['id']:4} ⛔ 라벨 버림 — {why}", flush=True)
                    continue
                said = asserts_current_not_stale(expect, q["superseded"], text)
            # 두 정규화(쉼표 제거 vs 공백 축약)가 갈리는 자리를 드러내 둔다.
            mentioned = all(facts_present([expect], text)) if expect else False
            dis = [d for d in (q.get("distractor") or []) if _norm(d) in nt]
            rows.append({"id": q["id"], "pass": ok, "asserted": said,
                         "mentioned": mentioned, "distractor_seen": dis,
                         "chars": len(text)})
            answers.append({"id": q["id"], "query": q["query"], "answer": text,
                            "expect": q.get("expect") or [],
                            "abstained": bool(getattr(ans, "abstained", False)),
                            "weak_evidence": bool(getattr(ans, "weak_evidence", False))})
            print(f"  {q['id']:4} 언급={'통과' if ok else '실패'} 주장={'통과' if said else '실패'}"
                  f"{'  (낡은 값 언급: ' + ','.join(dis) + ')' if dis else ''}", flush=True)

        n = len(rows)
        p = sum(r["pass"] for r in rows)
        a = sum(r["asserted"] for r in rows)
        for line in summary_lines(rows, args.for_signature):
            print(line)
        if args.for_signature:
            if args.save_answers:
                Path(args.save_answers).write_text(
                    json.dumps(answers, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  답변 원문: {args.save_answers}")
            return 0
        if args.out:
            Path(args.out).write_text(json.dumps(
                {"n": n, "passed": p, "asserted": a, "rows": rows},
                ensure_ascii=False, indent=2),
                encoding="utf-8")
            print(f"  기록: {args.out}")
        if args.save_answers:
            Path(args.save_answers).write_text(json.dumps(
                {"fill": cfg.get("search", {}).get("section_fill"), "answers": answers},
                ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  답변 원문: {args.save_answers}")
    finally:
        await db.close_pool()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
