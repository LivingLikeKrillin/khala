"""세 번째 독자 — 배포 모델(Sonnet)이 놓치는지, Gemini 가 지어내는지 가른다.

44장 대조에서 비대칭이 나왔다: **gemini 에만 있는 식별자 38 vs claude 에만 있는 것 9.** 둘 중
하나인데 평가 하니스가 가르지 못한다 — Sonnet 누락이거나 Gemini 발명이다.

세 번째 독립 판독을 넣으면 상당 부분이 사람 없이 갈린다:

    토큰이 gemini + opus 에 있고 sonnet 에 없다   →  Sonnet 누락
    토큰이 gemini 에만 있다                      →  Gemini 쪽 (발명 또는 두 Claude 의 공유 맹점)

**같은 SYSTEM 지시**로 부른다. 지시가 다르면 무엇 때문에 갈렸는지 못 가른다.

Opus 는 브리지(구독)로 돌므로 추가 과금이 없다. 대신 느리다 — 예산을 잘라 여러 번 부른다.

    task llm-bridge   # 호스트에서 먼저
    docker exec -e NEXUS_LLM_PROVIDER=claude-code \
      -e NEXUS_LLM_BRIDGE_URL=http://host.docker.internal:8900 \
      -e NEXUS_LLM_BRIDGE_TOKEN=... nexus-app \
      python -u scripts/vision_thirdreader.py --max-images 8
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from nexus import db  # noqa: E402
from nexus.ingest.vision import SYSTEM, image_sha256  # noqa: E402
from scripts.vision_crosscheck import _catalogue, tokens  # noqa: E402

LOCAL = Path("/app/tests/eval/local")
GEMINI_CACHE = LOCAL / "crosscheck-gemini.json"
OPUS_CACHE = LOCAL / f"thirdreader-{os.getenv('THIRD_MODEL', 'opus')}{os.getenv('THIRD_RUN', '')}.json"
OUT = LOCAL / "thirdreader.json"

MODEL = os.getenv("THIRD_MODEL", "opus")


async def opus_read(image_b64: str, media_type: str) -> str:
    """provider 는 **env 가 정한다**(`NEXUS_LLM_PROVIDER`) — 생성자 인자가 아니다.
    모델만 넘긴다. 그래서 이 스크립트는 claude-code 브리지를 가리킨 env 로 불러야 한다."""
    from nexus.providers.llm import LLMService

    svc = LLMService(model=MODEL)
    out = await svc.vision_extract(SYSTEM, image_b64, media_type, 4096)
    return out[0] if isinstance(out, tuple) else out


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-images", type=int, default=0)
    args = ap.parse_args()

    gem = json.loads(GEMINI_CACHE.read_text(encoding="utf-8"))
    cache = json.loads(OPUS_CACHE.read_text(encoding="utf-8")) if OPUS_CACHE.exists() else {}
    cat = await _catalogue()
    print(f"  그림 {len(cat)}장 · 세 번째 독자 {MODEL} · 캐시 {len(cache)}건\n", flush=True)

    await db.get_pool()
    rows, budget = [], args.max_images or 10 ** 9
    try:
        for im in cat:
            key = f"{im['doc']}#{im['index']}"
            if key not in gem:
                continue
            data = httpx.get(im["url"], timeout=60).content
            sha = image_sha256(data)
            sonnet = await db.fetch_val(
                "SELECT text FROM vision_extractions WHERE image_sha256 = $1 LIMIT 1", sha)

            if key not in cache:
                if budget <= 0:
                    print(f"  예산 소진 ({len(cache)}/{len(cat)}) — 다시 부르면 이어서")
                    break
                try:
                    cache[key] = await opus_read(
                        base64.b64encode(data).decode("ascii"), "image/png")
                except Exception as e:      # noqa: BLE001
                    print(f"  ✗ {key}: {type(e).__name__} {str(e)[:80]}", flush=True)
                    break
                OPUS_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
                budget -= 1

            si, _ = tokens(sonnet or "")
            gi, _ = tokens(gem[key]["text"])
            oi, _ = tokens(cache[key])

            # gemini 에만 있던 토큰들을 opus 가 확인해 주는가
            gem_only = gi - si
            confirmed = sorted(gem_only & oi)          # → sonnet 누락
            unconfirmed = sorted(gem_only - oi)        # → gemini 쪽
            # 반대 방향도 본다
            son_only = si - gi
            son_confirmed = sorted(son_only & oi)      # → gemini 누락

            rows.append({"doc": im["doc"], "index": im["index"],
                         "sonnet_missed": confirmed, "gemini_side": unconfirmed,
                         "gemini_missed": son_confirmed})
            print(f"  {im['doc'][:18]:18s} #{im['index']:<3d} "
                  f"sonnet 누락 {len(confirmed):2d} · gemini 쪽 {len(unconfirmed):2d} · "
                  f"gemini 누락 {len(son_confirmed):2d}", flush=True)
    finally:
        await db.close_pool()

    if not rows:
        return 2
    a = sum(len(r["sonnet_missed"]) for r in rows)
    b = sum(len(r["gemini_side"]) for r in rows)
    c = sum(len(r["gemini_missed"]) for r in rows)
    print(f"\n  대조 {len(rows)}장")
    print(f"  Sonnet 누락 확인 (gemini+opus 에 있음)   {a}")
    print(f"  Gemini 쪽 (opus 가 확인 못 함)           {b}   ← 사람이 볼 것")
    print(f"  Gemini 누락 확인 (sonnet+opus 에 있음)   {c}")
    OUT.write_text(json.dumps({"model": MODEL, "rows": rows}, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(f"\n기록: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
