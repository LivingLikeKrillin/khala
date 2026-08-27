"""Pack B 판정 — mecab-ko vs nori 를 khala 자신의 코퍼스에서 (ADR-0008 §5(b)).

Pack A 는 같은 종류의 **공개 대역**이라 §5(b) 를 닫지 못한다. 이 실행이 그 조건을 겨눈다.

**두 관문을 먼저 통과해야 결과로 친다.**

1. 스냅샷 ↔ 매니페스트. §4.1 이 라이브 테넌트를 실격시킨 이유가 '움직인다' 였으므로, 검증되지
   않은 실행은 결과가 아니다.
2. 라벨 게이트. 평가 하니스가 틀렸는지를 측정 **전에** 본다 — 층 균형·gold 존재·제목 베끼기·검토 서명.

관문을 나중에 두면 숫자가 먼저 나오고, 그 숫자를 보고 평가 하니스를 고치게 된다.

**실험군은 같은 테넌트를 순서대로 쓴다.** rid 가 테넌트를 품어서, 테넌트가 다르면 동점 정렬 키까지
달라지고 토크나이저와 무관한 차이가 승패에 섞인다(§4.3).

리포트는 `tests/eval/local/` 에만 쓴다 — 다른 조직의 문서를 가리키고 이 리포는 public 이다.

    docker exec nexus-app python scripts/ko_eval_packb_run.py
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

from scripts.ko_eval_harness import (  # noqa: E402
    LegResult,
    outcomes,
    score_query,
    verdict,
)
from scripts.ko_eval_labels import ManifestPack, check, load  # noqa: E402
from scripts.ko_eval_packb import MANIFEST, cmd_verify  # noqa: E402
from scripts.ko_eval_packb_disagreement import LOCAL_DIR, _snapshot_rows, run_arm  # noqa: E402

LABELS = LOCAL_DIR / "packb-labels.yaml"
REPORT = LOCAL_DIR / "packb-verdict.json"
ARM_TENANT = "ko_eval_arm"


def _leg(name: str, tops: dict[str, list[str]], answerable: list[dict]) -> LegResult:
    leg = LegResult(leg=f"keyword/{name}")
    for q in answerable:
        leg.scores.append(score_query(q["id"], tops.get(q["id"], []), q["gold"]))
    return leg


async def _run(args) -> int:
    from nexus import db
    from nexus.index.bm25 import MecabTokenizer, _get_mecab

    from scripts.ko_eval_nori import NoriTokenizer

    # ── 관문 1: 스냅샷이 매니페스트와 같은가 ────────────────────────────────
    if not MANIFEST.exists():
        print(f"✗ 매니페스트가 없다: {MANIFEST}")
        return 1
    if await cmd_verify(args) != 0:
        print("✗ 스냅샷이 매니페스트와 다르다 — 이 실행은 결과가 아니다 (§4.1)")
        return 1

    # ── 관문 2: 라벨 게이트 ────────────────────────────────────────────────
    if not LABELS.exists():
        print(f"✗ 라벨이 없다: {LABELS}")
        return 1
    labels = load(LABELS)
    if problems := check(labels, ManifestPack(MANIFEST)):
        print("✗ 라벨 게이트 실패 — 측정 이전에 평가 하니스가 틀렸다:", *problems[:6], sep="\n  ")
        return 1
    answerable = [q for q in labels["queries"] if q.get("answerable")]
    print(f"✓ 관문 통과 — 라벨 revision {labels['revision']} · 답변가능 {len(answerable)}건")

    if _get_mecab() is None:
        print("✗ mecab-ko 없음 — 이미지 안에서 실행하라")
        return 1
    mecab, nori = MecabTokenizer(), NoriTokenizer(args.nori_url)

    pool = await db.get_pool()
    try:
        async with pool.acquire() as con:
            rows = await _snapshot_rows(con)
        mecab_tops = await run_arm(mecab, rows, answerable, pool, ARM_TENANT)
        nori_tops = await run_arm(nori, rows, answerable, pool, ARM_TENANT)
    finally:
        await db.close_pool()

    m, n = _leg("mecab-ko", mecab_tops, answerable), _leg(nori.id, nori_tops, answerable)
    print(f"\nmecab: Recall@10 {m.recall:.3f} · MRR {m.mrr:.3f} · 미스 {m.misses}")
    print(f"nori : Recall@10 {n.recall:.3f} · MRR {n.mrr:.3f} · 미스 {n.misses}")

    wins, losses, ties = outcomes(n.scores, m.scores)
    v = verdict(wins, losses, ties, name_a="nori", name_b="mecab-ko")
    print(f"승패(nori 기준): {wins}승 {losses}패 {ties}무 → {v.decision}")

    # 층별은 **서술용**이다. 8건짜리 층은 아무것도 결정하지 못한다 (§2.4).
    by_stratum: dict[str, list[int]] = {}
    mm = {s.qid: s for s in m.scores}
    nn = {s.qid: s for s in n.scores}
    for q in answerable:
        d = nn[q["id"]].recall - mm[q["id"]].recall
        by_stratum.setdefault(q["stratum"], []).append(d)
    print("\n층별 (서술용, 각 8건):")
    for s, ds in sorted(by_stratum.items()):
        print(f"  {s:9s} nori-mecab Recall 차 합계 {sum(ds):+.1f}")

    report = {
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pack": labels["pack"], "labels_revision": labels["revision"],
        "manifest_frozen_at": json.loads(MANIFEST.read_text(encoding="utf-8"))["frozen_at"],
        "arms": {"mecab-ko": {"recall": m.recall, "mrr": m.mrr, "misses": m.misses},
                 nori.id: {"recall": n.recall, "mrr": n.mrr, "misses": n.misses}},
        "outcomes": {"nori_wins": wins, "nori_losses": losses, "ties": ties},
        "decision": v.decision,
        "note": ("Pack B — 커밋하지 않는다. '검정력 부족' 은 차이 없음이 아니라 "
                 "검정이 결론을 낼 수 없다는 뜻이고, ADR-0009 에 따라 의무는 열린 채 남는다."),
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\n기록: {REPORT}")
    return 0


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nori-url", default="http://host.docker.internal:19200")
    args = ap.parse_args(argv)
    if not os.getenv("DATABASE_URL"):
        print("✗ DATABASE_URL 이 없다")
        return 1
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
