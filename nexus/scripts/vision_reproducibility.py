"""판독기 재현율 — 두 번 읽고 비교한다. SPEC-nexus-vision-reproducibility §2.1.

두 단계가 **분리돼 있다**:

    measure   같은 그림을 두 번 읽어 비교한다. **아무것도 쓰지 않는다.**
    record    측정된 값을 `vision_extractions.reader_variation` 에 적는다.

나누는 이유는 §2.1 이다: 같은 신원으로 두 번째 호출을 하는 것이 ADR-0010 §5 가 다루는 바로 그
동작이라, 측정이 실수로 **기록이 되는 길**을 열어 두면 안 된다. 지금 그걸 막고 있는 것은
`vision_store.save()` 의 우연한 `ON CONFLICT DO NOTHING` 하나뿐이고, 여기서는 저장 함수를
아예 부르지 않는다.

`record` 는 **측정한 행에만** 쓴다. 측정하지 않은 행은 NULL 로 남는다 — 외삽해서 채우면 측정하지 않은 것을
측정한 것처럼 적게 되고, 그것이 이 SPEC 이 고치려는 실수다.

    docker exec nexus-app python -u scripts/vision_reproducibility.py measure --arm gemini
    docker exec nexus-app python -u scripts/vision_reproducibility.py record  --arm gemini
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from nexus import db  # noqa: E402
from nexus.ingest.vision import image_sha256  # noqa: E402
from nexus.ingest.vision_health import summarize, variation  # noqa: E402
from scripts.vision_crosscheck import _catalogue  # noqa: E402

LOCAL = Path("/app/tests/eval/local")

#: 실험군 이름 → (1회차 캐시, 2회차 캐시, 그 캐시에서 텍스트 꺼내는 법, 신원)
ARMS = {
    "gemini": ("crosscheck-gemini-nothink.json", "crosscheck-gemini-nothink-r2.json",
               lambda v: v["text"], None),
    "sonnet": ("thirdreader-sonnet.json", "thirdreader-sonnet-r2.json",
               lambda v: v, "claude-sonnet-4-6/18c36580"),
}


def _load(arm: str) -> tuple[dict, dict, callable, str | None]:
    a, b, get, identity = ARMS[arm]
    return (json.loads((LOCAL / a).read_text(encoding="utf-8")),
            json.loads((LOCAL / b).read_text(encoding="utf-8")), get, identity)


async def measure(arm: str) -> dict:
    """두 실행을 비교한다. **읽기만 한다** — DB 에 한 글자도 쓰지 않는다."""
    first, second, get, identity = _load(arm)
    keys = [k for k in first if k in second]
    pairs = [(get(first[k]), get(second[k])) for k in keys]
    s = summarize(pairs)

    print(f"  실험군 {arm} · 그림 {s['images']}장")
    print(f"  두 실행 완전 동일   {s['identical']}/{s['images']}")
    print(f"  토큰 변동률         {s['variation']:.1%}")
    print(f"  문턱 통과           {'예' if s['passes'] else '아니오'}")

    per_image = {k: round(variation(get(first[k]), get(second[k])), 4) for k in keys}
    out = LOCAL / f"reproducibility-{arm}.json"
    out.write_text(json.dumps({"arm": arm, "identity": identity, "summary": s,
                               "per_image": per_image}, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(f"\n기록(파일만): {out}")
    return {"summary": s, "identity": identity, "images": keys}


async def record(arm: str, tenant: str) -> int:
    """측정값을 **측정한 행에만** 적는다. 어느 그림을 쟀는지는 measure 가 남긴 파일이 안다."""
    report = json.loads((LOCAL / f"reproducibility-{arm}.json").read_text(encoding="utf-8"))
    identity = report["identity"]
    if not identity:
        print("  이 실험군은 저장된 추출이 아니다 — 적을 행이 없다 (측정만 유효)")
        return 0
    rate = report["summary"]["variation"]
    measured = set(report["per_image"])

    cat = await _catalogue()
    await db.get_pool()
    written = 0
    try:
        for im in cat:
            if f"{im['doc']}#{im['index']}" not in measured:
                continue
            sha = image_sha256(httpx.get(im["url"], timeout=60).content)
            n = await db.execute(
                "UPDATE vision_extractions SET reader_variation = $1 "
                "WHERE tenant = $2 AND image_sha256 = $3 AND extractor_identity = $4",
                rate, tenant, sha, identity)
            written += 1 if n else 0
    finally:
        await db.close_pool()
    print(f"  {written}행에 재현율 {rate:.1%} 기록 · 나머지는 NULL(안 측정한 것)로 남는다")
    return 0


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["measure", "record"])
    ap.add_argument("--arm", required=True, choices=sorted(ARMS))
    ap.add_argument("--tenant", default="default")
    args = ap.parse_args()

    if args.mode == "measure":
        await measure(args.arm)
        return 0
    return await record(args.arm, args.tenant)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
