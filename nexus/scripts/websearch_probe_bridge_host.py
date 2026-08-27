"""도구 호출 실험 — **호스트 단계**. 이미 인증된 `claude` 를 돌려 트리거를 관측한다.

컨테이너가 만든 `.probe/prompts.json` 을 읽어 질문마다 `claude -p` 를 부르고, 스트림에서
`tool_use` 블록을 세어 `.probe/answers.json` 에 남긴다. 채점은 다시 컨테이너가 한다.

**문은 하나만 연다.** 프로덕션 브리지의 `_DOORS_CLOSED` 는 건드리지 않는다 — 이 스크립트가
자기 호출에만 `WebSearch` 를 허용한다. ⚠ 실측상 `WebFetch`·`ToolSearch` 도 함께 도므로 도구
표면은 배포보다 넓다(결과를 읽을 때 감안할 것).

⚠ **문서 본문이 프롬프트에 들어간 채로 검색 도구가 열린다.** 우리 코퍼스는 우리가 통제하지만,
이 조합을 신뢰할 수 없는 문서에 쓰면 injection 이 검색어로 나갈 수 있다. 실험 전용.

    python scripts/websearch_probe_bridge_host.py [--budget 3.0]
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
from pathlib import Path

# 콘솔이 cp949 면 경고 기호 하나에 죽는다 — 실제로 답변 10건을 그렇게 잃었다(2026-08-25).
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

WORK = Path(__file__).resolve().parents[1] / ".probe"
DOORS = ["--allowed-tools", "WebSearch", "--strict-mcp-config",
         "--setting-sources", "", "--no-session-persistence"]


def run_one(system: str, user: str, timeout: float) -> dict:
    """`claude -p` 한 번. 스트림에서 도구 호출과 본문을 건진다."""
    argv = ["claude", "-p", "--output-format", "stream-json", "--verbose",
            "--append-system-prompt", system, *DOORS]
    proc = subprocess.run(argv, input=user, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)
    tools, text, cost, err = [], [], None, None
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("type") == "assistant":
            for b in d.get("message", {}).get("content", []):
                if b.get("type") == "tool_use":
                    tools.append(b.get("name", "?"))
                elif b.get("type") == "text":
                    text.append(b.get("text", ""))
        elif d.get("type") == "result":
            cost = d.get("total_cost_usd")
            if d.get("subtype") != "success":
                err = d.get("subtype")
    if proc.returncode != 0 and not text:
        err = err or f"exit {proc.returncode}: {proc.stderr[:200]}"
    return {"tools": tools, "n_tool_calls": len(tools), "text": "\n".join(text).strip(),
            "cost_usd": cost, "error": err}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--budget", type=float, default=3.0,
                    help="하니스 보고 비용 상한(USD). 넘으면 그 자리에서 멈춘다")
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--only", default="", help="쉼표로 구분한 id 만 돌린다")
    ap.add_argument("--system-suffix", default="",
                    help="시스템 프롬프트 뒤에 덧붙일 절(실험군 비교용). 출력 파일명에 태그가 붙는다")
    ap.add_argument("--tag", default="", help="출력 파일 태그(실험군 이름)")
    args = ap.parse_args()

    prompts = json.loads((WORK / "prompts.json").read_text(encoding="utf-8"))
    if args.only:
        keep = {x.strip() for x in args.only.split(",")}
        prompts = [p for p in prompts if p["id"] in keep]
    dest = WORK / (f"answers-{args.tag}.json" if args.tag else "answers.json")
    print(f"질문 {len(prompts)}건 · 상한 ${args.budget:.2f} (하니스 보고 기준)\n")
    out, spent = [], 0.0
    for p in prompts:
        if spent >= args.budget:
            print(f"\n⚠ 상한 도달 — 여기서 멈춘다 ({len(out)}/{len(prompts)})")
            break
        try:
            r = run_one(p["system"] + args.system_suffix, p["user"], args.timeout)
        except subprocess.TimeoutExpired:
            r = {"tools": [], "n_tool_calls": 0, "text": "", "cost_usd": None,
                 "error": "timeout"}
        spent += r.get("cost_usd") or 0.0
        out.append({"id": p["id"], **r})
        # **매 건 저장한다.** 루프 끝에서 한 번 쓰면 중간에 죽을 때 전부 잃는다(실측).
        dest.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        print(f"  {p['id']:3s} 도구 {len(r['tools'])}건 {','.join(r['tools']) or '-':24s}"
              f" ${(r.get('cost_usd') or 0):.3f}"
              f"{'  ✗ ' + str(r['error']) if r.get('error') else ''}")
    (WORK / "answers.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"\n답변 {len(out)}건 → {WORK / 'answers.json'} · 보고 소비 ${spent:.2f}")
    print("다음:  docker exec nexus-app python scripts/websearch_probe_bridge.py --score")
    return 0


if __name__ == "__main__":
    sys.exit(main())
