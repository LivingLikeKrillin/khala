"""Gemini 판독 1장 — **비용 추정을 실측으로 갈아치우기 위한 파일럿**.

44장을 돌리기 전에 한 장으로 확인하는 것 셋:

1. `usageMetadata` 의 실제 입출력 토큰 (타일 258토큰 가정이 맞는가 — 공식 가격 페이지가
   그 수치를 명시하지 않아서 추정으로 남아 있다)
2. 같은 `SYSTEM` 지시로 이 모델이 **전사** 를 하는가, 서술로 새는가
3. 출력이 저장된 Claude 판독과 **줄 단위로 대조 가능한 모양**인가

대상은 구현 에이전트가 이미 연 그림에서만 고른다 (아바타 정책 #6). 충실도 표본 8장은 건드리지
않는다 — 디렉터가 먼저 읽어야 하고, 내가 그 기계 판독을 보면 통제가 무너진다.

    docker exec nexus-app python -u scripts/vision_gemini_probe.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from nexus import db  # noqa: E402
from nexus.ingest.sources.notion import NotionSource  # noqa: E402
from nexus.ingest.vision import SYSTEM, image_sha256  # noqa: E402

OUT = Path("/app/tests/eval/local/gemini-probe.json")

TARGET_DOC = "아바타"
TARGET_INDEX = 6

#: 강한 독자를 쓴다. 교차검증의 값어치는 "독립적인 강한 독자 둘이 일치했다" 에서 나오고,
#: 약한 독자는 불일치를 홍수로 만들어 사람이 볼 양을 늘린다 (로컬 Qwen 에서 본 실패).
MODEL = os.getenv("GEMINI_VISION_MODEL", "gemini-3.6-flash")

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


#: 사고 예산. `off` 면 `thinkingBudget: 0` 을 실어 보낸다.
#:
#: **이건 비용 절감이 아니라 통제다.** 첫 실행에서 Gemini 에만 사고 토큰 58,838개가 붙었고
#: Claude 쪽 두 독자에게는 없었다. "같은 프롬프트·temperature 0" 이라고 적어 놓고 한 독자에게만
#: 추론 예산을 준 셈이라, 그 차이를 독자 충실도로 돌리는 근거가 약해진다. 끄고 다시 측정해서
#: 결론이 유지되는지 본다. (부수적으로 비용의 69%가 사라진다.)
THINKING = os.getenv("GEMINI_THINKING", "on").strip().lower()


async def gemini_read(image_b64: str, media_type: str, model: str) -> tuple[str, dict]:
    """이미지 1장 → (텍스트, usage). 같은 SYSTEM 지시·temperature 0.

    지시를 바꾸면 무엇 때문에 두 모델이 갈렸는지 못 가른다 — 그래서 프롬프트는 공유한다.
    """
    key = os.environ["GEMINI_API_KEY"]
    gen: dict = {"temperature": 0, "maxOutputTokens": 4096}
    if THINKING == "off":
        # Gemini 3.x 는 **완전히 끌 수 없다** — `thinkingBudget: 0` 은 400 을 낸다(실측).
        # 3.x 의 식별자는 `thinkingLevel` 이고, 낮출 수는 있어도 0 은 아니다. 그래서 이 실험군의
        # 이름은 "사고 없음" 이 아니라 **"사고 최소"** 이고, 통제도 그만큼만 맞춰진다.
        gen["thinkingConfig"] = {"thinkingLevel": "minimal"}
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [
            {"inline_data": {"mime_type": media_type, "data": image_b64}},
        ]}],
        "generationConfig": gen,
    }
    async with httpx.AsyncClient(timeout=300) as c:
        r = await c.post(ENDPOINT.format(model=model),
                         headers={"x-goog-api-key": key}, json=body)
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code}: {r.text[:400]}")
    data = r.json()
    text = ""
    for cand in data.get("candidates", []):
        for part in (cand.get("content") or {}).get("parts", []):
            text += part.get("text", "")
    return text, data.get("usageMetadata", {})


async def _page():
    await db.get_pool()
    try:
        rows = await db.fetch_all(
            "SELECT source_uri, title FROM documents WHERE tenant='default' "
            "AND status='active' AND n_images > 0")
        envs = [r["token_env"] for r in await db.fetch_all(
            "SELECT DISTINCT token_env FROM notion_sources")]
        for r in rows:
            stem = r["source_uri"].rsplit(":", 1)[-1]
            if TARGET_DOC in r["title"]:
                return stem[len("ext-notion-"):-3], envs
        return None, envs
    finally:
        await db.close_pool()


def _lines(t: str) -> list[str]:
    return [ln.strip() for ln in (t or "").splitlines() if ln.strip()]


async def main() -> int:
    page_id, envs = await _page()
    if not page_id:
        print("대상 문서를 못 찾았다")
        return 2

    conv = None
    for env in envs:
        try:
            s = NotionSource(token_env=env, roots=[])
            conv = s.fetch_markdown(s.page_ref(page_id))
            break
        except Exception:      # noqa: BLE001
            continue
    if conv is None or len(conv.images) < TARGET_INDEX:
        print("그림을 못 얻었다")
        return 2

    im = conv.images[TARGET_INDEX - 1]
    data = httpx.get(im["url"], timeout=60).content
    sha = image_sha256(data)
    print(f"  대상 #{TARGET_INDEX} · {len(data) // 1024}KB · 모델 {MODEL}", flush=True)

    text, usage = await gemini_read(
        base64.b64encode(data).decode("ascii"), "image/png", MODEL)

    await db.get_pool()
    try:
        stored = await db.fetch_val(
            "SELECT text FROM vision_extractions WHERE image_sha256 = $1 LIMIT 1", sha)
    finally:
        await db.close_pool()

    a, b = _lines(stored or ""), _lines(text)
    common = len(set(a) & set(b))
    print(f"\n  실측 토큰  입력 {usage.get('promptTokenCount')} · "
          f"출력 {usage.get('candidatesTokenCount')} · 합 {usage.get('totalTokenCount')}")
    print(f"  줄 수      claude {len(a)} · gemini {len(b)} · 완전일치 {common}")
    print(f"  gemini 출력 {len(text)}자 · claude 저장본 {len(stored or '')}자")

    OUT.write_text(json.dumps({
        "model": MODEL, "image_index": TARGET_INDEX, "image_bytes": len(data),
        "usage": usage, "claude_lines": len(a), "gemini_lines": len(b),
        "exact_common_lines": common,
        "gemini_text": text, "claude_text": stored,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\n기록: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
