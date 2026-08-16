#!/usr/bin/env python3
"""§6.1 재현성 하니스 — 같은 코드에 같은 카드를 쓰는가.

SPEC-nexus-code-semantic-cards §3.3/§6.1. **이 게이트가 나머지 전부를 막는다.**

왜 먼저인가: 카드 생성기는 바이트를 읽는 비결정적 판독기다. 이 프로젝트는 배포 스크린샷
판독기가 같은 그림에 84.7% 다른 글을 내는 것을 **네 개의 SPEC 을 쓴 뒤에** 발견했고, 그때까지
쌓은 근거 32건이 전부 잡음이었다. 그래서 아래 숫자가 나오기 전에는 매칭도 임베딩도 설계하지
않는다.

측정 대상은 **출하될 생성자**여야 한다 (§3.3). 백엔드를 선언하지 않으면 돌지 않는다.

    python -m scripts.card_reproducibility --repo <path> --symbols 20 --runs 5
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nexus.index.card_gen import (  # noqa: E402
    MAX_HOPS,
    PROMPT_VERSION,
    GenerationInput,
    collect_sources,
    generate_card,
    generator_id,
)
from nexus.index.cards import (  # noqa: E402
    CardSpan,
    check_card,
    is_card_candidate,
    term_agreement,
)
from nexus.index.snapshot import check as snapshot_check  # noqa: E402
from nexus.index.snapshot import head_commit  # noqa: E402
from nexus.index.symbols import scan_repo  # noqa: E402


def pick_symbols(repo: Path, n: int):
    """카드 후보 중에서 고르되, **파일이 겹치지 않게** 흩는다.

    한 파일에서 연속으로 뽑으면 서로 닮은 심볼만 재게 되고, 그러면 생성기가 실제보다
    안정적으로 보인다 — 재려는 것이 흔들림인데.
    """
    result = scan_repo(repo)
    seen_files: set[str] = set()
    picked = []
    for s in sorted(result.symbols, key=lambda x: (x.file_path, x.start_line)):
        if not is_card_candidate(s.symbol_kind, s.start_line, s.end_line):
            continue
        if s.file_path in seen_files:
            continue
        seen_files.add(s.file_path)
        picked.append(s)
        if len(picked) >= n:
            break
    return picked, result


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--symbols", type=int, default=20)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--config", default="config.yaml")
    args = ap.parse_args()

    provider = os.getenv("NEXUS_LLM_PROVIDER", "")
    if not provider:
        print("NEXUS_LLM_PROVIDER 를 선언하십시오. 백엔드를 밝히지 않은 실행은 하지 않습니다.\n"
              "  keyless: NEXUS_LLM_PROVIDER=claude-code (브리지 필요)\n"
              "  paid   : NEXUS_LLM_PROVIDER=anthropic  (사전 허락 필요)", file=sys.stderr)
        return 2

    repo = Path(args.repo)
    commit = head_commit(repo)
    if commit is None:
        print("git 저장소가 아닙니다.", file=sys.stderr)
        return 2
    state = snapshot_check(repo, commit)
    if not state.ok:
        # 더러운 트리에서 잰 재현성은 무엇의 재현성인지 말할 수 없다.
        print(f"거부: {state.explain()}", file=sys.stderr)
        return 1
    print(f"대상: {state.context()}")
    for w in state.warnings():
        print(f"⚠ {w}")

    import yaml

    from nexus.providers.llm import LLMService
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    llm = LLMService(cfg)
    model = getattr(llm, "model", provider)

    print(f"생성자: {generator_id(model)}  (프롬프트 {PROMPT_VERSION}, 홉 {MAX_HOPS})")

    symbols, scan = pick_symbols(repo, args.symbols)
    print(f"심볼 {len(symbols)}개 × {args.runs}회 = 호출 {len(symbols) * args.runs}건 "
          f"(스캔 {scan.scanned_files}파일, 미파싱 {scan.unparsed_files})")
    print()

    rows = []
    rejected = 0
    for i, sym in enumerate(symbols, 1):
        span = CardSpan(repo.name, sym.file_path, sym.start_line, sym.end_line,
                        sym.symbol_name, sym.span_hash)
        sources = collect_sources(repo, [span])
        if not sources:
            continue
        gi = GenerationInput(spans=[span], sources=sources, commit_sha=commit)

        runs = []
        for _ in range(args.runs):
            try:
                card, _usage = await generate_card(llm, sym.symbol_name, gi, model=model)
            except Exception as e:  # noqa: BLE001 — 한 심볼의 실패가 측정을 죽이면 안 된다
                print(f"  [{i}] {sym.symbol_name}: 생성 실패 {type(e).__name__}")
                continue
            problems = check_card(card, sources)
            if problems:
                rejected += 1
                print(f"  [{i}] {sym.symbol_name}: 규칙 위반 {problems[0][:60]}")
                continue
            runs.append(card.domain_terms)

        if len(runs) >= 2:
            a = term_agreement(runs)
            rows.append((sym.symbol_name, a))
            print(f"  [{i}] {sym.symbol_name:<28} {a}")

    print()
    if not rows:
        print("측정 가능한 심볼이 없습니다.")
        return 1

    means = [a.mean for _, a in rows]
    overall = sum(means) / len(means)
    print(f"domain_terms 일치도 — 심볼 {len(rows)}개 평균 {overall:.3f} "
          f"(최저 {min(means):.3f}, 최고 {max(means):.3f})")
    print(f"규칙 위반으로 버려진 카드: {rejected}건")
    print()
    print("SPEC §6.1 문턱은 0.70 이고 **잠정값**입니다 — 검색 결과에서 유도한 값이 아니라,")
    print("매칭 층이 코퍼스가 아니라 생성기 잡음을 재지 않도록 둔 바닥입니다.")
    if overall < 0.70:
        print("→ 문턱 미달. 이 단위는 출하하지 않습니다.")
        return 1
    print("→ 문턱 통과. 다만 표본과 실행 수를 함께 읽으십시오.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
