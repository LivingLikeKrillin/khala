"""도구 호출 실험 — **실제 도구(웹 검색)** 를 실제 모델 판정으로 측정하는 첫 실행.

전문과 판정 규칙은 `tests/eval/websearch/README.md` — **측정 전에** 거기 박혔다.

앞의 두 회차(`tests/eval/toolmap/`)는 *생성 이전* 라우터를 쟀고 둘 다 기각됐다. 여기서는 업계
표준 형태를 그대로 돌린다: 도구 스키마를 요청에 실어 보내고 **모델이 생성 도중에** 고른다.

**프로덕션을 건드리지 않는다.** 검색·패킷·프롬프트는 배포와 같은 코드를 부르고, API 호출만 이
스크립트가 직접 한다 — `providers/llm.py` 의 "tools 를 넣지 않는다" 통제는 그대로다.

⚠ **지출이 있는 첫 실험이다.** 웹 검색은 유료(1,000회당 $10)이고 토큰도 유료 키로 나간다.
`--budget` 상한을 넘으면 그 자리에서 멈추고 거기까지를 결과로 쓴다.

    docker exec nexus-app python scripts/websearch_probe.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

HERE = Path(__file__).resolve().parents[1] / "tests" / "eval" / "websearch"
TENANT = "default"
CLEARANCE = "INTERNAL"
#: 최신 변형(동적 필터링). Sonnet 4.6 이상에서 지원된다.
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search"}
#: 배포 기본 모델의 단가(백만 토큰당) + 웹 검색 1,000회당 $10.
PRICE_IN, PRICE_OUT, PRICE_SEARCH = 3.0, 15.0, 0.01


def _blocks(resp):
    """응답 블록을 (검색 호출 수, 검색 결과 수, 본문 텍스트) 로 접는다.

    ⚠ `content[0].text` 로 읽지 않는다 — 도구가 붙으면 첫 블록이 `server_tool_use` 라
    프로덕션의 그 접근은 여기서 죽는다(그 자체가 실행 층이 손볼 자리라는 신호다).
    """
    calls = results = 0
    text = []
    for b in resp.content:
        t = getattr(b, "type", "")
        if t == "server_tool_use" and getattr(b, "name", "") == "web_search":
            calls += 1
        elif t == "web_search_tool_result":
            results += 1
        elif t == "text":
            text.append(b.text)
    return calls, results, "\n".join(text)


async def main(limit: int, budget: float) -> int:
    from anthropic import AsyncAnthropic

    from nexus import db
    from nexus.api import _load_config
    from nexus.llm.citations import validate_citations
    from nexus.llm.prompts import build_prompts
    from nexus.providers.embedding import embedding_service_from_config
    from nexus.search import hybrid
    from nexus.search.evidence_packet import assemble_packet, format_for_llm

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("✗ ANTHROPIC_API_KEY 없음 — 이 실험은 브리지로 못 돈다(브리지는 텍스트 셔틀이라 "
              "tool_use 의미론을 못 나른다)")
        return 1

    qset = yaml.safe_load((HERE / "questions.yaml").read_text(encoding="utf-8"))
    model, questions = qset["model"], qset["questions"][:limit]
    budget = min(budget, float(qset.get("budget_usd", budget)))
    print(f"세트 {len(questions)}건 · 모델 {model} · 상한 ${budget:.2f} · 테넌트 {TENANT}\n")

    svc = embedding_service_from_config()
    cfg = _load_config()
    await db.get_pool()
    client = AsyncAnthropic()

    rows, spent = [], 0.0
    for q in questions:
        if spent >= budget:
            print(f"\n⚠ 상한 ${budget:.2f} 도달 — 여기서 멈춘다({len(rows)}/{len(questions)} 완료)")
            break

        r = await hybrid.hybrid_search(q["q"], tenant=TENANT, clearance=CLEARANCE, top_k=10,
                                       embedding_svc=svc, config=cfg)
        if r.degraded:
            print(f"✗ 경로가 죽었다({r.degraded}) — 이 상태의 숫자는 결과가 아니다")
            return 1
        packet = await assemble_packet(r.hits, r.graph, TENANT, fill=r.fill)
        system, user = build_prompts(q["q"], format_for_llm(packet),
                                     weak_evidence=r.confidence.weak)

        resp = await client.messages.create(
            model=model, max_tokens=2048, system=system,
            messages=[{"role": "user", "content": user}],
            tools=[WEB_SEARCH_TOOL],
        )
        calls, results, text = _blocks(resp)
        u = resp.usage
        n_search = getattr(getattr(u, "server_tool_use", None), "web_search_requests", 0) or calls
        cost = (u.input_tokens / 1e6 * PRICE_IN + u.output_tokens / 1e6 * PRICE_OUT
                + n_search * PRICE_SEARCH)
        spent += cost

        rep = validate_citations(text, packet)
        searched = calls > 0
        # 사전등록 규칙: A군 발동만 차단 사유. C군 발동은 '무해한 오탐'으로 따로 센다.
        ok = (searched == (q["expect"] == "search")) if q["expect"] != "internal" else not searched
        misfire = q["expect"] == "no_search" and searched
        rows.append({"id": q["id"], "expect": q["expect"], "searched": searched,
                     "n_search": n_search, "ok": ok, "misfire": misfire,
                     "harmless": q["expect"] == "internal" and searched,
                     "citations": getattr(rep, "total", None),
                     "unverified": getattr(rep, "unverified", None),
                     "weak": r.confidence.weak, "cost_usd": round(cost, 4),
                     "stop_reason": getattr(resp, "stop_reason", None),
                     "answer": text})
        mark = "✗MIS" if misfire else ("OK  " if ok else "    ")
        print(f"{mark} {q['id']:3s} 기대 {q['expect']:10s} 검색 {'예' if searched else '아니오':4s}"
              f"({n_search}) 인용 {rep.total}/미검증 {rep.unverified} "
              f"약함 {'Y' if r.confidence.weak else 'N'} ${cost:.4f}")

    n_ok = sum(r["ok"] for r in rows)
    n_mis = sum(r["misfire"] for r in rows)
    n_harm = sum(r["harmless"] for r in rows)
    n_unver = sum(1 for r in rows if r["searched"] and (r["unverified"] or 0) > 0)
    print(f"\n  일치 {n_ok}/{len(rows)} · **오선택 {n_mis}** · 무해한 발동 {n_harm} "
          f"· 검색 답변 중 미검증 인용 있는 것 {n_unver}")
    print(f"  지출 ${spent:.4f} (상한 ${budget:.2f})")
    out = HERE / "result.json"
    out.write_text(json.dumps({"model": model, "rows": rows, "ok": n_ok, "misfire": n_mis,
                               "harmless": n_harm, "spent_usd": round(spent, 4)},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"기록: {out}  (답변 본문 포함 — 커밋 전 확인)")
    await db.close_pool()
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=13)
    ap.add_argument("--budget", type=float, default=2.0, help="USD 상한. 넘으면 중단")
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.limit, a.budget)))
