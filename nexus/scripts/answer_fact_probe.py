"""답변 사실 채점 — **답이 옳은가**를 측정한다. Recall 이 못 보는 자리.

규칙은 측정 전에 `tests/eval/answer-facts/README.md` 에 박혔다.

검색 평가 하니스(`Recall@10`)는 *정답 문서가 왔는가* 만 측정한다. 2026-08-26 에 그 한계가 끝까지 드러났다 —
Recall 이 **오르는 동안 답변이 나빠졌다**(정답 숫자는 왔는데 낡은 숫자를 무효화하는 문장이 안
와서, 답변이 낡은 값을 정본으로 읽었다). 여기서는 답변 텍스트에 **그 값이 나오는가**를 본다.

**LLM 심판을 쓰지 않는다.** 판정은 정규화 부분일치이고, 그래서 무르다 — 오탐이 아니라 **누락**을
잡는 평가 하니스로 쓴다. 기권도 실패로 센다: 코퍼스가 답을 갖고 있는데 못 낸 것이다.

**실패는 귀속까지 간다** (감사 B3). "사실이 답에 없다" 하나로는 검색을 고칠지 서술을 고칠지
모른다. 그래서 못 낸 사실이 **LLM 이 본 근거 문자열에 있었는가**를 같은 정규화로 같이 보고,
검색 쪽(FP1·FP2·FP3) · FP4(근거에 있었는데 하나도 안 뽑음) · FP7(반만 뽑음) 로 가른다.
점수(`언급`·`주장`)는 이것과 **무관하게 예전 그대로**다 — `attribute` 의 `pass` 가 1판과 같은
규칙이라는 것을 검사가 지킨다.

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
from scripts.ko_eval_answer_quality import VERDICTS as _VERDICTS  # noqa: E402
from scripts.ko_eval_corpus_reach import (  # noqa: E402
    UndeclaredCorpus,
    aiming_is_wrong,
    groups_reached,
    needles_in_corpus,
    resolve_tenant,
    unreachable_ids,
)
from scripts.ko_eval_answer_quality import (  # noqa: E402
    asserts_all,
    attribute_facts,
    asserts_current_not_stale,
    asserts_value,
    facts_present,
    discloses_conflict,
    label_is_usable,
)

#: ⛔ **기본 코퍼스 상수를 두지 않는다** (2026-09-05, `OPEN.md` A87). 여기 `TENANT = "default"`
#: 가 있었고 그것이 `--tenant` 의 기본값이었다 — 설계 라벨을 물으면서 아무 말 없이 다른
#: 코퍼스를 측정한 사고의 재료다. 코퍼스는 라벨이 선언하거나 사람이 준다
#: (`ko_eval_corpus_reach.resolve_tenant`).
#:
#: 여러 테넌트는 쉼표로 준다 — 합친 코퍼스와 견주려면 **같은 라벨·같은 채점기**로 양쪽을
#: 돌려야 하고, 라이브 경로도 principal 의 읽기 범위를 여럿으로 해소한다.
CLEARANCE = "INTERNAL"


def _norm(s: str) -> str:
    """공백·쉼표를 지운다 — `4,000` 과 `4000`, `최대 1` 과 `최대1` 이 같아야 한다."""
    return re.sub(r"[\s,]+", "", s or "")



def _all_groups_present(expect_all, normalized_text: str) -> bool:
    """`expect_all` 의 **모든 묶음**이 답변에 있는가. 묶음 안은 표기 후보라 하나면 된다.

    상수·모순·종합 라벨이 이 판정을 공유한다. 갈래마다 따로 쓰면 한 갈래만 고쳐지고
    나머지는 조용히 틀린 채 남는다 — 2026-08-31 에 모순 갈래가 정확히 그렇게 빠져 있었다.
    """
    return all(
        any(_norm(x) in normalized_text for x in ([e] if isinstance(e, str) else e))
        for e in expect_all
    )


#: 판정 이름 — **정본은 `ko_eval_answer_quality.VERDICTS`** 다. 두 러너가 같은 이름을 써야
#: 리포트를 나란히 읽을 수 있다(감사 B3, `research/2026-09-04-rag-current-practice.md`).
VERDICTS = _VERDICTS


def required_groups(q: dict) -> list[list[str]]:
    """라벨이 요구하는 **사실 묶음**의 목록.

    채점이 이미 쓰는 규칙 그대로다 — `expect_all` 은 묶음의 목록이고, `expect` 는 같은
    값의 표기 후보라 **묶음 하나**다. 여기서 규칙을 새로 만들면 귀속과 점수가 서로 다른
    것을 세게 된다.
    """
    if q.get("expect_all"):
        return [list(g) if isinstance(g, list) else [g] for g in q["expect_all"]]
    expect = list(q.get("expect") or [])
    return [expect] if expect else []


def attribute(groups: list[list[str]], evidence_norm: str, answer_norm: str) -> dict:
    """답이 못 낸 사실이 **근거에 있었는가**로 실패를 가른다 (감사 B3).

    ⛔ **왜 필요한가.** 지금까지 이 채점기는 "사실이 답에 없다" 까지만 말했다. 그 하나의
    신호가 세 가지를 뭉쳐 놓는다 — 검색이 못 물어온 것 · 물어왔는데 안 뽑은 것(FP4) ·
    반만 뽑은 것(FP7). 실패를 보고도 **검색을 고칠지 서술을 고칠지 모르는** 상태였다.

    가르는 재료는 `format_for_llm(packet)` — **LLM 이 실제로 본 문자열**이다. 스니펫만이
    아니라 그래프·코드값·부채까지 그 안에 들어간다. 근거 판정도 답변 판정과 **같은
    정규화**(이 파일의 `_norm`)를 쓴다. 조합 규칙 자체는 공용이다
    (`ko_eval_answer_quality.attribute_facts`) — Pack B 러너와 판정이 갈리면 안 된다.

    ⚠ **이 판정이 기우는 방향을 적어 둔다.** 부분일치는 무르다. 사실이 근거에 **다른 말로**
    적혀 있으면 여기서는 "근거에 없음" 으로 읽히고, 그러면 FP4 가 실제보다 적게 세어지고
    `upstream` 이 많게 세어진다. 반대 방향(없는 것을 있다고 읽는 것)은 훨씬 드물다.
    그러니 **FP4/FP7 은 하한**으로, `upstream` 은 상한으로 읽어라.

    Returns:
        n_required · n_in_evidence · n_in_answer · missing(못 낸 묶음의 대표 표기) ·
        verdict(`VERDICTS`).
    """
    def _present(group: list[str], hay: str) -> bool:
        return any(_norm(x) in hay for x in group)

    in_ev = [_present(g, evidence_norm) for g in groups]
    in_ans = [_present(g, answer_norm) for g in groups]
    out = attribute_facts(in_ev, in_ans)
    out["missing"] = [g[0] for g, ans in zip(groups, in_ans) if not ans]
    return out


def attribution_lines(rows: list[dict]) -> list[str]:
    """귀속 내역. **비율을 내지 않는다** — 이 리포는 찍힌 수가 인용되는 자리를 이미 안다."""
    counted = [r for r in rows if r.get("verdict")]
    if not counted:
        return []
    tally = {v: sum(1 for r in counted if r["verdict"] == v) for v in VERDICTS}
    out = ["", "  실패 귀속 (감사 B3 — 못 낸 사실이 근거에 있었는가):"]
    labels = {
        "pass": "통과 — 요구한 사실이 전부 답에 있다",
        "upstream": "검색 — 못 낸 사실이 근거에도 없었다 (FP1·FP2·FP3 쪽)",
        "fp4": "FP4  — 근거에 있었는데 하나도 안 뽑았다",
        "fp7": "FP7  — 근거에 있었는데 반만 뽑았다",
        "mixed": "혼합 — 못 낸 것이 근거 있음과 없음으로 갈렸다",
        "no_groups": "판정 안 함 — 요구 사실이 라벨에 없다",
    }
    for v in VERDICTS:
        if tally[v]:
            ids = [r["id"] for r in counted if r["verdict"] == v]
            out.append(f"    {tally[v]:3}건  {labels[v]}  {ids}")
    out.append("    ⚠ 부분일치는 무르다 — FP4/FP7 은 하한, 검색 쪽은 상한으로 읽어라.")
    return out


def sidecar_path(out: str, explicit: str, disabled: bool) -> str:
    """답변 **원문**을 적을 자리. 빈 문자열이면 안 적는다.

    ⛔ **왜 기본이 켜짐인가 (실측 2026-09-02).** 컷오버 판정에 쓴 실행 65회가 요약만 남기고
    원문을 버렸다. 그래서 *"2판이 왜 이 라벨에서 갈렸는가"* 를 **다시 볼 방법이 없다** —
    같은 답변을 다시 만들 수도 없다(답변 백엔드에 temperature·seed 가 없다). 이 리포는
    같은 일로 이미 3시간을 태우고 *"채점기 리포트는 답변 원문 사이드카를 남긴다"* 고 적어 뒀는데,
    그 규율이 **옵션 하나 뒤에** 있었고 판정 실행이 그 옵션을 안 켰다.

    ⚠ 원문은 조직 문서의 사실이므로 gitignore 된 자리에만 앉는다. 그 성질은 안 바뀐다 —
    `--out` 자체가 이미 그런 자리를 가리킨다.
    """
    if disabled:
        return ""
    if explicit:
        return explicit
    if not out:
        return ""
    q = Path(out)
    return str(q.with_name(q.stem + ".answers" + (q.suffix or ".json")))


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
    ap.add_argument("--top-k", type=int, default=10,
                    help="검색 예산. 집합을 요구하는 질문이 여기서 잘린다")
    # ⛔ **쉼표로 여러 테넌트를 받는다** (2026-08-31). 컷오버 뒤 하니스가 `default` 하나만
    # 물어서 설계 라벨이 떨어졌고, 나는 그것을 제품 회귀로 읽을 뻔했다. 라이브 경로는
    # principal 의 읽기 범위를 해소해 두 테넌트를 보는데(SPEC-nexus-tenant-read-scope),
    # 하니스는 문자열 하나를 그대로 넘겨 **아무도 안 지나는 경로를 측정**하고 있었다.
    # 같은 파일 아래 주석이 2026-08-29 에 같은 실수를 적어 두었는데 또 났다.
    # ⛔ **기본값이 없다** (2026-09-05). 위 두 주석이 같은 사고를 두 번 적어 뒀는데 세 번째가
    # 났다 — `synthesis-recency` 4건이 전부 떨어졌고 나는 그것을 코퍼스 결함으로 읽었다.
    # 요구한 사실은 `design_docs` 에 있었고, 라벨은 자기 코퍼스를 안 밝히고, 기본값이 조용히
    # `default` 였다. **말없이 고르는 기본값이 이 사고의 재료다.** 이제 라벨이 `corpus.tenant`
    # 로 선언하거나 사람이 `--tenant` 로 준다. 둘 다 없으면 돌지 않는다.
    ap.add_argument("--tenant", default="",
                    help="어느 코퍼스에 물을 것인가. 안 주면 라벨의 `corpus.tenant` 를 쓴다")
    ap.add_argument("--for-signature", action="store_true",
                    help="서명 전 라벨을 사람이 읽으려고 돌린다 — 답변은 내고 **점수는 안 낸다**")
    ap.add_argument("--out", default="")
    ap.add_argument("--only", default="", help="쉼표로 구분한 id — 그것만 돈다")
    ap.add_argument("--fill", choices=("on", "off"), default="",
                    help="절 채움(`search.section_fill`) 강제. 비우면 config 그대로")
    ap.add_argument("--save-answers", default="",
                    help="답변 **원문**을 적을 파일. 조직 문서의 사실이므로 gitignore 된 곳에만. "
                         "안 주면 `--out` 옆에 자동으로 적는다")
    ap.add_argument("--no-answers", action="store_true",
                    help="원문 사이드카를 만들지 않는다 — **기본은 만든다**")
    args = ap.parse_args()

    labels = yaml.safe_load(Path(args.labels).read_text(encoding="utf-8"))
    queries = labels["queries"]
    # ⛔ **어느 코퍼스를 물을지 먼저 정한다** — DB 도 LLM 도 건드리기 전에. 말없이 고른
    # 기본값이 2026-09-05 사고의 재료였다(`OPEN.md` A87).
    try:
        tenant, tenant_note = resolve_tenant(labels, args.tenant)
    except UndeclaredCorpus as e:
        print(f"⛔ {e}")
        return 2
    if tenant_note:
        print(tenant_note)
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
        # **LLM 이 실제로 본 문자열**을 만드는 그 함수. 실패 귀속(B3)이 근거 쪽 판정을
        # 여기서 가져온다 — 패킷 필드를 골라 다시 조립하면 프롬프트에 없는 것을 근거로
        # 세게 된다. 두 번 불러도 같은 값이고 싸다(`api.py:1202` 가 같은 이유로 그렇게 한다).
        from nexus.search.evidence_packet import format_for_llm
        from nexus.search.reconcile import packet_for_answer

        svc, cfg = embedding_service_from_config(), _load_config()
        if args.fill:
            cfg.setdefault("search", {})["section_fill"] = (args.fill == "on")
        print(f"  절 채움: {cfg.get('search', {}).get('section_fill')}", flush=True)
        scope = [t.strip() for t in tenant.split(",") if t.strip()]

        # ── 겨냥 검사: 이 라벨들이 **이 코퍼스에서** 답해질 수 있는가 ──────────
        # 실측 2026-09-05: 네 건이 전부 `귀속=upstream` 으로 나와 코퍼스 결함으로 읽었는데,
        # 요구한 사실은 전부 `design_docs` 에 있었고 라벨 파일은 테넌트를 안 적는다.
        # 테넌트를 바꾸니 곧바로 통과했다. 주석은 이미 있었다 — 사람이 읽어야 작동했을 뿐이다.
        groups_by_q = [required_groups(q) for q in queries]
        found = await needles_in_corpus(
            [alt for gs in groups_by_q for g in gs for alt in g], scope, await db.get_pool())
        reach = [groups_reached(gs, found) for gs in groups_by_q]
        unreachable = unreachable_ids([q["id"] for q in queries], reach)
        if aiming_is_wrong(reach):
            print(f"\n⛔ 요구 사실이 있는 라벨이 **하나도** `{tenant}` 에 닿지 못한다.")
            print("   이 상태의 수는 시스템이 아니라 **겨냥**을 측정한다 — 테넌트를 확인하라.")
            print("   (라벨 파일은 자기 테넌트를 안 적는다. `--tenant` 로 준다.)")
            return 1
        if unreachable:
            print(f"  ⚠ 요구 사실이 `{tenant}` 에 하나도 없는 라벨: {unreachable}")
            print("    코퍼스 부재(FP1)일 수도, 테넌트를 잘못 물은 것일 수도 있다 — 사람이 가른다.")

        rows, answers = [], []
        for q in queries:
            r = await hybrid.hybrid_search(q["query"], tenant=scope, clearance=CLEARANCE,
                                           top_k=args.top_k, embedding_svc=svc, config=cfg)
            # **프로덕션이 답변용 근거를 만드는 그 함수**를 쓴다. 직접 조립하면
            # 하니스가 아무도 안 지나는 경로를 측정한다 — 2026-08-29 에 실제로 그랬다.
            packet = await packet_for_answer(r, scope, CLEARANCE, config=cfg,
                                             search=hybrid.hybrid_search, embedding_svc=svc,
                                             question=q["query"], pool=await db.get_pool())
            ans = await generate_answer(q["query"], packet, LLMService(),
                                        confidence=r.confidence)
            text = getattr(ans, "answer", None) or getattr(ans, "text", "") or str(ans)
            nt = _norm(text)
            expect = q.get("expect") or []
            ok = any(_norm(e) in nt for e in expect)
            # 2판 — **주장했는가**. 같은 값을 담고도 결론을 안 낸 답변을 1판은 통과시킨다.
            said = asserts_value(expect, text)
            # 3판 — 종합·최신성. 라벨이 그 모양일 때만 판정이 바뀐다.
            if q.get("type") == "conflict":
                # 모순 라벨은 **늘어놓기가 곧 답**이다 (표로 나란히 놓는 것이 좋은 모양).
                #
                # ⛔ **2026-08-31: 여기서 `ok` 를 다시 계산하지 않았다.** 모순 라벨은
                # `expect` 가 비고 `expect_all` 만 갖는데, `ok` 는 위에서 `expect` 로만
                # 계산됐다 — 그래서 `any([])` = False 가 되어 **답이 무엇이든 1판 실패**였다.
                # 첫 서명 회차에서 A-10 이 `언급=실패 · 주장=통과` 로 찍혔고, 2판은 1판의
                # 부분집합이어야 하므로 그 모순이 결함을 드러냈다.
                ok = _all_groups_present(q["expect_all"], nt)
                said = discloses_conflict(q["expect_all"], text)
            elif q.get("expect_all"):
                ok = _all_groups_present(q["expect_all"], nt)
                said = asserts_all(q["expect_all"], text)
            elif q.get("superseded") is not None:
                usable, why = label_is_usable(expect, q["superseded"])
                if not usable:
                    print(f"  {q['id']:4} ⛔ 라벨 버림 — {why}", flush=True)
                    continue
                said = asserts_current_not_stale(expect, q["superseded"], text)
            # 실패 귀속(감사 B3) — 못 낸 사실이 **근거에 있었는가**.
            attr = attribute(required_groups(q), _norm(format_for_llm(packet)), nt)
            # 교차 검사: 귀속의 `pass` 는 1판(`ok`)과 **같은 규칙**이어야 한다. 갈리면
            # 둘 중 하나가 옮겨 적히며 어긋난 것이고, 그때는 귀속을 믿으면 안 된다.
            if (attr["verdict"] == "pass") != bool(ok) and attr["verdict"] != "no_groups":
                print(f"  {q['id']:4} ⚠ 귀속과 1판이 갈렸다 — "
                      f"ok={ok} verdict={attr['verdict']}", flush=True)

            # 두 정규화(쉼표 제거 vs 공백 축약)가 갈리는 자리를 드러내 둔다.
            # ⛔ **2026-08-31: `expect` 가 없는 라벨은 무조건 False 였다.** 모순·종합 라벨은
            # `expect_all` 만 갖는다. 그 상태로 요약이 `1판 14/15` 를 냈는데, 빠진 하나는
            # 답이 나빠서가 아니라 **1판이 그 라벨을 볼 수 없어서**였다. 분모에 넣고 항상
            # 떨어뜨리는 것은 측정이 아니다.
            if expect:
                mentioned = all(facts_present([expect], text))
            elif q.get("expect_all"):
                mentioned = _all_groups_present(q["expect_all"], nt)
            else:
                mentioned = False
            dis = [d for d in (q.get("distractor") or []) if _norm(d) in nt]
            rows.append({"id": q["id"], "pass": ok, "asserted": said,
                         "mentioned": mentioned, "distractor_seen": dis,
                         "chars": len(text), **attr})
            answers.append({"id": q["id"], "query": q["query"], "answer": text,
                            "expect": q.get("expect") or [],
                            "abstained": bool(getattr(ans, "abstained", False)),
                            "weak_evidence": bool(getattr(ans, "weak_evidence", False))})
            # 귀속은 **서명 전에도** 찍는다 — 점수가 아니라 *왜 떨어졌는가*라서, 라벨을
            # 읽는 사람에게 그것이 필요하다. 총계는 아래에서 서명 뒤에만 낸다.
            where = "" if attr["verdict"] in ("pass", "no_groups") else f" 귀속={attr['verdict']}"
            print(f"  {q['id']:4} 언급={'통과' if ok else '실패'} 주장={'통과' if said else '실패'}"
                  f"{where}"
                  f"{'  (낡은 값 언급: ' + ','.join(dis) + ')' if dis else ''}", flush=True)

        n = len(rows)
        p = sum(r["pass"] for r in rows)
        a = sum(r["asserted"] for r in rows)
        for line in summary_lines(rows, args.for_signature):
            print(line)
        for line in attribution_lines(rows):
            print(line)
        if args.for_signature:
            if args.save_answers:
                Path(args.save_answers).write_text(
                    json.dumps(answers, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  답변 원문: {args.save_answers}")
            return 0
        if args.out:
            Path(args.out).write_text(json.dumps(
                {"n": n, "passed": p, "asserted": a,
                 "attribution": {v: sum(1 for r in rows if r.get("verdict") == v)
                                 for v in VERDICTS},
                 "rows": rows},
                ensure_ascii=False, indent=2),
                encoding="utf-8")
            print(f"  기록: {args.out}")
        sidecar = sidecar_path(args.out, args.save_answers, args.no_answers)
        if sidecar:
            Path(sidecar).write_text(json.dumps(
                {"fill": cfg.get("search", {}).get("section_fill"), "answers": answers},
                ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  답변 원문: {sidecar}")
    finally:
        await db.close_pool()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
