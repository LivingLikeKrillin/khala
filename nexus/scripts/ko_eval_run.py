"""한국어 평가셋 탐색 실행 — 리포트를 남긴다 (SPEC-nexus-korean-retrieval-eval §4.5).

CI 는 mecab 키워드 다리의 **바닥값**만 지킨다(빠르고 임베딩이 필요 없다). 벡터/융합 다리와
토크나이저 비교는 손으로 도는 **탐색 실행**이고, 그 결과는 기억이 아니라 **커밋된 리포트**로
남는다 — ADR-0008 §5(b) 가 인용할 것은 리포트지 "돌려봤다" 가 아니다.

리포트에는 팩·라벨 리비전·토크나이저·필터 정책·풀 구성원·미판정 수·불일치쌍이 함께 적힌다.
숫자만 있는 리포트는 나중에 재현도 반박도 안 된다.

    python -m scripts.ko_eval_run --tokenizer mecab
    python -m scripts.ko_eval_run --tokenizer mecab --keep     # 테넌트를 지우지 않고 남긴다
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.ko_eval_harness import LegResult, load_pack, render_report, run_keyword_leg
from scripts.ko_eval_labels import DEFAULT_LABELS, check, load
from scripts.ko_eval_pack import DEFAULT_PACK_DIR
from scripts.ko_eval_pack import verify as verify_pack

REPORTS_DIR = Path(__file__).resolve().parents[1] / "tests" / "eval" / "reports"
TENANT = "ko_eval_run"


async def _run(args) -> int:
    from nexus import db
    from nexus.index.bm25 import _INCLUDE_POS, _get_mecab

    problems = verify_pack(DEFAULT_PACK_DIR)
    if problems:
        print("✗ 팩 검증 실패 — 이건 결과가 아니다:", *problems[:5], sep="\n  ")
        return 1

    labels = load(DEFAULT_LABELS)
    problems = check(labels, DEFAULT_PACK_DIR)
    if problems:
        print("✗ 라벨 게이트 실패 — 측정 이전에 평가 하니스가 틀렸다:", *problems[:5], sep="\n  ")
        return 1

    if _get_mecab() is None:
        print("✗ mecab-ko 없음 — 프로덕션 토크나이저가 아니면 재지 않는다 (이미지 안에서 실행하라)")
        return 1

    if not os.getenv("DATABASE_URL"):
        print("✗ DATABASE_URL 이 없다 — 어느 DB 에 적재할지 말하지 않았다")
        return 1
    pool = await db.get_pool()
    try:
        async with pool.acquire() as con:
            await con.execute("DELETE FROM chunks WHERE tenant=$1", TENANT)
            await con.execute("DELETE FROM documents WHERE tenant=$1", TENANT)
            print(f"팩 적재 중… ({DEFAULT_PACK_DIR})")
            chunk_doc = await load_pack(DEFAULT_PACK_DIR, TENANT, con)
        print(f"적재 완료: 문서 {len(set(chunk_doc.values()))} · 청크 {len(chunk_doc)}")

        legs: list[LegResult] = [await run_keyword_leg(labels, TENANT, chunk_doc)]

        strata = {q["id"]: q["stratum"] for q in labels["queries"]}
        meta = {
            "실행 시각": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "팩": labels["pack"],
            "라벨 리비전": labels["revision"],
            "질의": f"답변가능 {legs[0].n} · 답변불가 "
                    f"{sum(1 for q in labels['queries'] if not q['answerable'])}(집계 제외)",
            "토크나이저": args.tokenizer,
            "필터 정책": f"POS allow-list {sorted(_INCLUDE_POS)}",
            "다리": "keyword (벡터/융합은 임베딩 서비스가 필요해 이 실행에는 없다)",
            "풀 구성원": args.tokenizer,
            "미판정": "풀 판정 미실시 — gold 는 authored_from_doc 뿐 (§4.2)",
        }
        report = render_report(meta, legs, strata)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        out = args.out or REPORTS_DIR / f"{datetime.now(timezone.utc):%Y-%m-%d}-{args.tokenizer}.md"
        Path(out).write_text(report, encoding="utf-8", newline="\n")
        print(report)
        print(f"→ {out}")

        if not args.keep:
            async with pool.acquire() as con:
                await con.execute("DELETE FROM chunks WHERE tenant=$1", TENANT)
                await con.execute("DELETE FROM documents WHERE tenant=$1", TENANT)
        return 0
    finally:
        await db.close_pool()


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="한국어 평가셋 탐색 실행")
    ap.add_argument("--tokenizer", default="mecab", help="실행에 쓴 토크나이저 id (리포트에 기록)")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--keep", action="store_true", help="적재한 테넌트를 지우지 않는다")
    args = ap.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
