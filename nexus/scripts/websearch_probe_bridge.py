"""도구 호출 실험 — **브리지 경로**(호스트 `claude -p`)로. 유료 키 불필요.

`websearch_probe.py` 는 Messages API 로 같은 것을 재지만 **계정 사용 한도**로 막혔다(2026-09-01).
이 판은 이미 인증된 호스트 Claude Code 를 쓴다 — `--output-format stream-json` 이 `tool_use`
블록을 그대로 흘려주므로 **트리거를 관측할 수 있다**.

세 단계로 나뉜다. 검색·패킷은 컨테이너(DB·임베딩·mecab)가, `claude` 는 호스트가 갖고 있다:

    docker exec nexus-app python scripts/websearch_probe_bridge.py --emit    # ① 프롬프트 생성
    python scripts/websearch_probe_bridge_host.py                            # ② 호스트에서 claude
    docker exec nexus-app python scripts/websearch_probe_bridge.py --score   # ③ 채점

⚠ **충실도 한계 — 결과를 읽을 때 반드시 같이 읽어라.**
  · Claude Code 의 **자체 시스템 프롬프트가 살아 있고**, khala 프롬프트는 그 위에 덧붙는다.
    배포의 Messages API 호출과 같은 조건이 아니다.
  · 허용목록을 `WebSearch` 로 줘도 `WebFetch`·`ToolSearch` 가 돈다 — 도구 표면이 배포보다 넓다.
  · 그래서 이 실험이 답하는 것은 *"khala 프롬프트와 근거를 본 모델이 검색을 집는가"* 이지
    *"배포가 정확히 이렇게 행동한다"* 가 아니다.

⚠ **API 청구는 없지만 소비는 있다.** 하니스가 호출당 비용을 보고한다(관측 1건 $0.24). 상한은
호스트 단계가 건다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

HERE = Path(__file__).resolve().parents[1] / "tests" / "eval" / "websearch"
WORK = Path(__file__).resolve().parents[1] / ".probe"
TENANT, CLEARANCE = "default", "INTERNAL"


async def _packets(limit: int):
    """질문마다 (질문, 시스템, 사용자, 패킷). **배포와 같은 코드**로 만든다."""
    from nexus import db
    from nexus.api import _load_config
    from nexus.llm.prompts import build_prompts
    from nexus.providers.embedding import embedding_service_from_config
    from nexus.search import hybrid
    from nexus.search.evidence_packet import assemble_packet, format_for_llm

    qset = yaml.safe_load((HERE / "questions.yaml").read_text(encoding="utf-8"))
    svc, cfg = embedding_service_from_config(), _load_config()
    await db.get_pool()
    out = []
    for q in qset["questions"][:limit]:
        r = await hybrid.hybrid_search(q["q"], tenant=TENANT, clearance=CLEARANCE, top_k=10,
                                       embedding_svc=svc, config=cfg)
        if r.degraded:
            raise SystemExit(f"✗ 경로가 죽었다({r.degraded}) — 이 상태의 숫자는 결과가 아니다")
        packet = await assemble_packet(r.hits, r.graph, TENANT, fill=r.fill)
        system, user = build_prompts(q["q"], format_for_llm(packet),
                                     weak_evidence=r.confidence.weak)
        out.append((q, system, user, packet, r.confidence.weak))
    return out


async def emit(limit: int) -> int:
    WORK.mkdir(exist_ok=True)
    rows = [{"id": q["id"], "q": q["q"], "expect": q["expect"], "system": s, "user": u,
             "weak": weak}
            for q, s, u, _p, weak in await _packets(limit)]
    (WORK / "prompts.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print(f"프롬프트 {len(rows)}건 → {WORK / 'prompts.json'}")
    print("다음: 호스트에서  python scripts/websearch_probe_bridge_host.py")
    return 0


async def score(limit: int) -> int:
    from nexus.llm.citations import validate_citations

    answers = {a["id"]: a for a in json.loads((WORK / "answers.json").read_text(encoding="utf-8"))}
    rows, spent = [], 0.0
    for q, _s, _u, packet, weak in await _packets(limit):
        a = answers.get(q["id"])
        if not a:
            continue
        searched = a["n_tool_calls"] > 0
        # 사전등록 규칙 그대로: A군 발동만 차단 사유. C군 발동은 '무해한 오탐'.
        ok = (searched == (q["expect"] == "search")) if q["expect"] != "internal" else not searched
        rep = validate_citations(a["text"], packet)
        spent += a.get("cost_usd") or 0.0
        rows.append({"id": q["id"], "expect": q["expect"], "searched": searched,
                     "tools": a["tools"], "ok": ok,
                     "misfire": q["expect"] == "no_search" and searched,
                     "harmless": q["expect"] == "internal" and searched,
                     "citations": len(rep.citations), "unverified": rep.unverified_count,
                     "cited": [f"{c.title}|{c.verified}" for c in rep.citations][:6],
                     "weak": weak, "cost_usd": a.get("cost_usd"), "text": a["text"]})
        mark = "✗MIS" if rows[-1]["misfire"] else ("OK  " if ok else "    ")
        print(f"{mark} {q['id']:3s} 기대 {q['expect']:10s} 검색 {'예' if searched else '아니오':4s}"
              f" 도구 {','.join(a['tools']) or '-':22s}"
              f" 인용 {len(rep.citations)}/미검증 {rep.unverified_count}"
              f" 약함 {'Y' if weak else 'N'}")

    n_mis = sum(r["misfire"] for r in rows)
    print(f"\n  일치 {sum(r['ok'] for r in rows)}/{len(rows)} · **오선택 {n_mis}** "
          f"· 무해한 발동 {sum(r['harmless'] for r in rows)} "
          f"· 검색 답변 중 미검증 인용 {sum(1 for r in rows if r['searched'] and r['unverified'])}")
    print(f"  하니스 보고 소비 ${spent:.2f} (API 청구 아님)")
    (HERE / "result-bridge.json").write_text(
        json.dumps({"backend": "claude-code-bridge", "rows": rows, "misfire": n_mis,
                    "reported_usd": round(spent, 2)}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"기록: {HERE / 'result-bridge.json'}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--emit", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--limit", type=int, default=13)
    a = ap.parse_args()
    if a.emit:
        raise SystemExit(asyncio.run(emit(a.limit)))
    if a.score:
        raise SystemExit(asyncio.run(score(a.limit)))
    ap.print_help()
    raise SystemExit(1)
