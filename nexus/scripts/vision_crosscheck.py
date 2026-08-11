"""44장 교차검증 — 두 독자가 무엇에서 갈리는가.

파일럿(`vision_gemini_probe.py`)이 확인한 것: 두 판독은 **값이 같고 서식이 다르다**. Claude 는
전각 공백으로 배치를 흉내 내고 Gemini 는 마크다운 표로 접는다. 그래서 줄 단위 완전일치는
19줄 중 5줄이었고, 그 5라는 숫자는 내용에 대해 아무 말도 하지 않는다.

그래서 여기서는 **정규화 후 비자명 토큰 집합**으로 비교한다:

* 마크다운 골격(`|`, `#`, `---`)을 걷어내고 NFKC 로 정규화한다 — 전각 공백·동그라미 숫자
  (`①`→`1`)가 여기서 접힌다. NFKC 가 접지 않는 수학 빼기표(`−` U+2212)만 따로 맵한다.
* **식별자·숫자 토큰**(`Ava_01`, `0.1.6`, `60`, `FENDI`)을 뽑는다. 발명 탐지에 가장 날카롭다 —
  두 독립 모델이 같은 없는 식별자를 지어낼 확률은 낮고, 정책의 값은 대부분 이 모양이다.
* **한글 토큰**(2음절 이상)은 따로 센다. 서술로 새는지 보는 축이라 성격이 다르다.

**한쪽에만 있는 토큰**이 사람에게 올릴 목록이다 — 그것은 *다른 쪽의 누락*이거나 *이쪽의 발명*이고,
둘을 가르는 것은 그림을 보는 사람뿐이다. 이 자는 사람이 볼 곳을 좁힐 뿐 판정하지 않는다.

충실도 표본 8장의 **본문은 출력하지 않는다** — 디렉터가 먼저 읽어야 한다 (§7.1c).

    docker exec nexus-app python -u scripts/vision_crosscheck.py [--max-images N]
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from nexus import db  # noqa: E402
from nexus.ingest.sources.notion import NotionSource  # noqa: E402
from nexus.ingest.vision import image_sha256  # noqa: E402
from scripts.vision_gemini_probe import MODEL, gemini_read  # noqa: E402

LOCAL = Path("/app/tests/eval/local")
# 팔마다 캐시를 가른다. 사고 켠 판독과 끈 판독을 한 파일에 섞으면 무엇을 비교했는지 모른다.
_ARM = ("" if os.getenv("GEMINI_THINKING", "on").strip().lower() != "off" else "-nothink")
# 같은 설정을 두 번 돌려 **실행 간 변동**을 재기 위한 꼬리표. 잡음 바닥을 모르면 독자 간 차이가
# 신호인지 알 수 없다 — 2026-08-11 에 그걸 모른 채 네 번 결론을 냈다.
_ARM += os.getenv("CROSSCHECK_RUN", "")
CACHE = LOCAL / f"crosscheck-gemini{_ARM}.json"
OUT = LOCAL / f"crosscheck{_ARM}.json"
SAMPLE = LOCAL / "fidelity-sample" / "sample.json"

_SCAFFOLD = re.compile(r"^\s*[|#>\-\s]*$")
_IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]*")
_HANGUL = re.compile(r"[가-힣]{2,}")


def normalize(text: str) -> str:
    """서식 차이를 접는다. **내용 차이는 접지 않는다** — 그것이 재려는 것이다."""
    t = unicodedata.normalize("NFKC", text or "")
    t = t.replace("−", "-").replace("–", "-").replace("—", "-")
    out = []
    for ln in t.splitlines():
        if _SCAFFOLD.match(ln):          # 표 구분선·빈 헤딩 — 내용이 없는 줄
            continue
        ln = ln.replace("|", " ").lstrip("#> ").strip()
        if ln:
            out.append(re.sub(r"\s+", " ", ln))
    return "\n".join(out)


def tokens(text: str) -> tuple[set[str], set[str]]:
    """(식별자·숫자, 한글) 토큰 집합."""
    n = normalize(text)
    idents = {m.group(0) for m in _IDENT.finditer(n) if len(m.group(0)) > 1}
    hangul = {m.group(0) for m in _HANGUL.finditer(n)}
    return idents, hangul


async def _catalogue() -> list[dict]:
    await db.get_pool()
    try:
        rows = await db.fetch_all(
            "SELECT source_uri, title FROM documents WHERE tenant='default' "
            "AND status='active' AND n_images > 0 ORDER BY title")
        envs = [r["token_env"] for r in await db.fetch_all(
            "SELECT DISTINCT token_env FROM notion_sources ORDER BY token_env")]
    finally:
        await db.close_pool()

    sources = []
    for env in envs:
        try:
            sources.append(NotionSource(token_env=env, roots=[]))
        except KeyError:
            continue

    cat = []
    for r in rows:
        stem = r["source_uri"].rsplit(":", 1)[-1]
        page_id = stem[len("ext-notion-"):-3]
        conv = None
        for s in sources:
            try:
                conv = s.fetch_markdown(s.page_ref(page_id))
                break
            except Exception:      # noqa: BLE001
                continue
        if conv is None:
            print(f"  ✗ 못 닿음: {r['title'][:24]}", flush=True)
            continue
        for i, im in enumerate(conv.images, start=1):
            cat.append({"doc": r["title"], "index": i, "url": im["url"]})
    return cat


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-images", type=int, default=0, help="0 이면 전부")
    args = ap.parse_args()

    sample_keys = set()
    if SAMPLE.exists():
        for d in json.loads(SAMPLE.read_text(encoding="utf-8"))["drawn"]:
            sample_keys.add((d["doc"], d["image_index"]))

    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    cat = await _catalogue()
    print(f"  그림 {len(cat)}장 · 모델 {MODEL} · 캐시 {len(cache)}건\n", flush=True)

    await db.get_pool()
    rows, budget = [], args.max_images or 10 ** 9
    usage_tot = {"prompt": 0, "out": 0, "total": 0}
    try:
        for im in cat:
            key = f"{im['doc']}#{im['index']}"
            data = httpx.get(im["url"], timeout=60).content
            sha = image_sha256(data)
            stored = await db.fetch_val(
                "SELECT text FROM vision_extractions WHERE image_sha256 = $1 LIMIT 1", sha)

            if key not in cache:
                if budget <= 0:
                    print(f"  예산 소진 — 다시 부르면 이어서 한다 ({len(cache)}/{len(cat)})")
                    break
                text, usage = await gemini_read(
                    base64.b64encode(data).decode("ascii"), "image/png", MODEL)
                cache[key] = {"text": text, "usage": usage}
                CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
                budget -= 1
            g = cache[key]
            u = g.get("usage", {})
            usage_tot["prompt"] += u.get("promptTokenCount", 0) or 0
            usage_tot["out"] += u.get("candidatesTokenCount", 0) or 0
            usage_tot["total"] += u.get("totalTokenCount", 0) or 0

            ci, ch = tokens(stored or "")
            gi, gh = tokens(g["text"])
            rows.append({
                "doc": im["doc"], "index": im["index"],
                "in_sample": (im["doc"], im["index"]) in sample_keys,
                "shared_ident": len(ci & gi),
                "claude_only_ident": sorted(ci - gi), "gemini_only_ident": sorted(gi - ci),
                "shared_hangul": len(ch & gh),
                "claude_only_hangul": len(ch - gh), "gemini_only_hangul": len(gh - ch),
            })
            mark = "*" if rows[-1]["in_sample"] else " "
            print(f" {mark}{im['doc'][:18]:18s} #{im['index']:<3d} "
                  f"식별자 공유 {rows[-1]['shared_ident']:3d} · "
                  f"claude만 {len(rows[-1]['claude_only_ident']):3d} · "
                  f"gemini만 {len(rows[-1]['gemini_only_ident']):3d}", flush=True)
    finally:
        await db.close_pool()

    n = len(rows)
    if not n:
        return 2
    si = sum(r["shared_ident"] for r in rows)
    co = sum(len(r["claude_only_ident"]) for r in rows)
    go = sum(len(r["gemini_only_ident"]) for r in rows)
    print(f"\n  대조한 그림 {n}장")
    print(f"  식별자·숫자 토큰   공유 {si} · claude만 {co} · gemini만 {go}")
    print(f"    → 사람이 볼 항목 {co + go}개 (장당 평균 {(co + go) / n:.1f})")
    print(f"  한글 토큰         공유 {sum(r['shared_hangul'] for r in rows)} · "
          f"claude만 {sum(r['claude_only_hangul'] for r in rows)} · "
          f"gemini만 {sum(r['gemini_only_hangul'] for r in rows)}")
    print(f"\n  실측 토큰 합계 입력 {usage_tot['prompt']} · 출력 {usage_tot['out']} · "
          f"총 {usage_tot['total']} (사고 {usage_tot['total'] - usage_tot['prompt'] - usage_tot['out']})")

    OUT.write_text(json.dumps({"model": MODEL, "images": n, "usage": usage_tot, "rows": rows},
                              ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\n기록: {OUT}  (표본 8장은 * 표시 — 본문은 출력하지 않았다)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
