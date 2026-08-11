"""사람에게 **백지가 아니라 질문 목록**을 준다 — 두 판독이 갈린 자리만.

백지에 "그림의 텍스트를 그대로 입력하시오" 는 이 도구 전체를 안 쓰는 것이다. 두 독자가 이미
600개 넘는 토큰에서 일치했고, 사람이 답해야 하는 것은 **갈린 20건 안팎**뿐이다.

## 잡음을 먼저 거른다

Gemini 는 같은 설정으로 **두 번** 돌아 있다. 두 번 다 나온 토큰만 "이 독자가 안정적으로 읽은
것" 으로 친다 — 한 번만 나온 것은 그 독자의 흔들림이지 상대의 누락이 아니다. 이걸 안 하고
독자 간 차이를 신호로 읽었다가 하루를 태웠다 (SPEC-nexus-vision-reproducibility §1.1).

Opus 는 아직 한 번뿐이라 같은 여과를 못 한다. 그래서 항목마다 **어느 근거로 올라왔는지**를
기록하되, 사람에게 보여줄 때는 감춘다.

## 눈가림과 대조군

* 어느 독자가 낸 토큰인지 **말하지 않는다.** 알면 "이쪽이 맞겠지" 가 판정에 들어간다.
* 두 독자가 **일치한** 토큰에서 뽑은 대조군을 섞는다. 그것들이 그림에 없으면 "일치 = 존재"
  라는 전제가 무너진 것이고, 나머지 판정도 못 쓴다. 대조군을 먼저 채점한다.
* 순서는 (그림, 토큰) 해시로 정렬 — 무작위지만 재현된다.

    docker exec nexus-app python -u scripts/vision_adjudication.py
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from nexus.ingest.vision_health import tokens  # noqa: E402
from scripts.vision_crosscheck import _catalogue  # noqa: E402

LOCAL = Path("/app/tests/eval/local")
OUT = LOCAL / os.getenv("ADJ_OUT", "adjudication")

GEM_R1 = LOCAL / os.getenv("ADJ_GEM_R1", "crosscheck-gemini-nothink.json")
GEM_R2 = LOCAL / os.getenv("ADJ_GEM_R2", "crosscheck-gemini-nothink-r2.json")
OPUS_R1 = LOCAL / os.getenv("ADJ_OPUS_R1", "thirdreader-opus.json")
OPUS_R2 = LOCAL / os.getenv("ADJ_OPUS_R2", "thirdreader-opus-r2.json")

#: 대조군 수. 갈린 항목이 20건 안팎이므로 10건이면 "일치=존재" 전제를 흔들기에 충분하고,
#: 사람이 보는 총량을 두 배로 만들지 않는다.
CONTROLS = 10


def _order(image: str, token: str) -> str:
    return hashlib.sha256(f"{image}\x00{token}".encode()).hexdigest()


def build(gem1: dict, gem2: dict, opus1: dict, opus2: dict) -> list[dict]:
    """질문 항목을 만든다. 순수 함수 — 같은 입력이면 같은 목록.

    **양쪽 모두 두 번 돌았으므로 양쪽에 같은 여과를 건다.** 한 독자가 두 실행 중 한 번만 읽은
    토큰은 그 독자의 흔들림이지 상대의 누락이 아니다 — 그것을 사람에게 물으면 잡음을 판정하게
    한다. 한쪽에만 여과를 걸면 그 비대칭이 그대로 판정 기준의 비대칭이 된다.
    """
    items: list[dict] = []
    controls: list[dict] = []
    precision: list[dict] = []      # 부분문자열 — 발명이 아니라 정밀도 차이. 세되 묻지 않는다
    for key in sorted(set(gem1) & set(gem2) & set(opus1) & set(opus2)):
        a1, _ = tokens(gem1[key]["text"])
        a2, _ = tokens(gem2[key]["text"])
        b1, _ = tokens(opus1[key])
        b2, _ = tokens(opus2[key])
        a_stable, b_stable = a1 & a2, b1 & b2
        a_ever, b_ever = a1 | a2, b1 | b2

        # **상대의 토큰에 통째로 들어 있는 토큰은 묻지 않는다.**
        #
        # 긴 쪽이 그림에 있다면 짧은 쪽 글자들도 그림에 있다 — 그러므로 짧은 쪽을 낸 판독기는
        # 무엇도 지어내지 않았다. 반복 횟수를 다르게 센 더미 텍스트(`TXTXT…` 13자 vs 15자)나
        # 자릿수를 흘린 값(`60` vs `160`)이 여기 해당한다. 그것은 **정밀도 불일치**이고 이
        # 게이트가 재는 발명이 아니다.
        #
        # 반대 방향은 남긴다: 긴 쪽은 짧은 쪽에 없는 글자를 포함하므로 여전히 물어야 한다.
        # 이 규칙은 눈앞의 데이터가 아니라 "발명" 의 정의에서 나온다 — 그래서 안전하다.
        def _contained(tok: str, other: set[str]) -> bool:
            return any(tok != o and tok in o for o in other)

        for t in sorted(a_stable - b_ever):
            if _contained(t, b_ever):
                precision.append({"image": key, "token": t, "side": "A"})
                continue
            items.append({"image": key, "token": t, "why": "A안정/B전무"})
        for t in sorted(b_stable - a_ever):
            if _contained(t, a_ever):
                precision.append({"image": key, "token": t, "side": "B"})
                continue
            items.append({"image": key, "token": t, "why": "B안정/A전무"})
        # 둘 다 두 번 다 읽은 것 = "그림에 있다" 는 가장 강한 근거. 여기서 대조군을 뽑는다.
        for t in sorted(a_stable & b_stable):
            controls.append({"image": key, "token": t, "why": "대조군"})

    controls.sort(key=lambda c: _order(c["image"], c["token"]))
    step = max(1, len(controls) // CONTROLS)
    picked = controls[::step][:CONTROLS]

    # **그림으로 묶는다.** 사람이 그림을 한 번 열고 그 그림의 질문을 다 답하게 하려는 것이다 —
    # 해시로만 흩으면 같은 그림을 여러 번 열게 되고, 그 왕복이 판정 자체보다 오래 걸린다.
    #
    # 눈가림은 그대로다: 어느 판독기가 낸 토큰인지도, 무엇이 대조군인지도 여전히 감춰져 있고,
    # **그림 안에서는** 해시 순서로 섞여 후보와 대조군이 붙어 나오지 않는다.
    everything = items + picked
    everything.sort(key=lambda c: (c["image"], _order(c["image"], c["token"])))
    return everything, precision


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", default="default")
    ap.parse_args()

    gem1 = json.loads(GEM_R1.read_text(encoding="utf-8"))
    gem2 = json.loads(GEM_R2.read_text(encoding="utf-8"))
    opus1 = json.loads(OPUS_R1.read_text(encoding="utf-8"))
    opus2 = json.loads(OPUS_R2.read_text(encoding="utf-8"))
    items, precision = build(gem1, gem2, opus1, opus2)
    if not items:
        print("갈린 항목이 없다 — 물을 것이 없다")
        return 0

    need = sorted({i["image"] for i in items})
    OUT.mkdir(parents=True, exist_ok=True)
    cat = {f"{c['doc']}#{c['index']}": c for c in await _catalogue()}

    files: dict[str, str] = {}
    for key in need:
        c = cat.get(key)
        if not c:
            continue
        name = f"{c['doc'][:18].replace('/', '_')}_{c['index']}.png"
        try:
            (OUT / name).write_bytes(httpx.get(c["url"], timeout=60).content)
            files[key] = name
        except Exception as e:      # noqa: BLE001
            files[key] = f"(받지 못함: {type(e).__name__})"

    lines = [
        "# 판정 요청 — 두 판독이 갈린 자리만",
        "",
        f"항목 **{len(items)}건** · 그림 {len(need)}장. 전사가 아닙니다.",
        "",
        "각 항목은 **예/아니오 하나**입니다: 그 문자열이 그 그림에 보이는가.",
        "",
        "- `있음` / `없음` / `모르겠음`(흐려서 판독 불가) 중 하나를 적어 주세요",
        "- **더 긴 문자열의 일부로 보여도 `있음` 입니다.** 이 판정이 재는 것은 *판독기가 그림에"
        " 없는 글자를 지어냈는가* 이므로, 화면에 `txt` 가 35번인데 질문이 33번짜리를 묻는다면"
        " 그 글자들은 전부 실재하고 지어낸 것은 없습니다 — 반복 횟수 오차는 발명이 아닙니다",
        "- 어느 모델이 낸 것인지는 **일부러 감췄습니다** — 알면 판정이 그쪽으로 기웁니다",
        "- 일부는 두 판독이 **일치한** 항목입니다(대조군). 그것들이 `없음` 으로 나오면"
        " 전제가 무너진 것이라, 나머지 판정도 다시 봐야 합니다",
        "",
        "- **`없음` 으로 답할 항목은 확대해서 한 번 더 보십시오.** 지난 라운드에서 20건 중 2건이"
        " 재확인에 뒤집혔고 둘 다 작은 글씨를 놓친 것이었습니다",
        "",
        "그림은 같은 폴더에 있습니다. **그림 하나씩 묶어 두었으니 한 번 열고 그 그림의 질문을"
        " 다 답하시면 됩니다.**",
        "",
    ]
    n = 0
    current = None
    for it in items:
        if it["image"] != current:
            current = it["image"]
            lines += ["", f"### `{files.get(current, current)}`", "",
                      "| # | 이 문자열이 그림에 있습니까 | 답 |", "|---:|---|---|"]
        n += 1
        lines.append(f"| {n} | `{it['token']}` |  |")
    lines.append("")
    (OUT / "questions.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 정답지는 따로 — 사람이 답한 뒤 채점에 쓴다. 질문지에는 근거가 없다.
    (OUT / "key.json").write_text(
        json.dumps({"items": items, "precision": precision}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")

    n_ctl = sum(1 for i in items if i["why"] == "대조군")
    print(f"  질문 {len(items)}건 (갈림 {len(items) - n_ctl} · 대조군 {n_ctl}) · 그림 {len(need)}장")
    print(f"  묻지 않음: 정밀도 불일치 {len(precision)}건 (상대 토큰의 부분문자열)")
    print(f"  {OUT / 'questions.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
