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
import re
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


#: 테스트 코드 경로. 카드는 **업무 행동**을 서술해 정책·설계 문서와 맞추기 위한 것이고,
#: `setUp` 이나 `…_returns403` 은 업무 용어로 서술할 것이 없다. 모집단에 남겨 두면 생성기가
#: 아니라 모집단을 측정하게 된다.
_TEST_PATH = re.compile(r"(^|/)(test|tests)/|Test[s]?\.java$|IT\.java$|_test\.py$|/conftest\.py$")


def is_test_path(path: str) -> bool:
    return bool(_TEST_PATH.search(path))


def pick_symbols(repo: Path, n: int, *, strategy: str = "first-per-file", seed: int = 0,
                 exclude_tests: bool = False, min_body: int = 0):
    """카드 후보 중에서 고르되, **파일이 겹치지 않게** 흩는다.

    한 파일에서 연속으로 뽑으면 서로 닮은 심볼만 측정하게 되고, 그러면 생성기가 실제보다
    안정적으로 보인다 — 측정하려는 것이 흔들림인데.

    전략이 둘인 이유는 **첫 실행이 그 함정에 절반만 걸렸기 때문**이다. `first-per-file` 은
    파일은 흩지만 경로 정렬 순서를 그대로 따라가므로, 실제로는 알파벳 앞쪽 한 패키지
    (그 저장소에서는 admin/demo 계열의 요청·응답 DTO)만 뽑혔다. 재현성이 낮게 나왔을 때
    그것이 생성기의 성질인지 그 한 묶음의 성질인지 **그 표본으로는 구별할 수 없다.**

    `random` 은 같은 후보 모집단에서 씨앗 고정 무작위로 뽑는다 — 재현 가능하고, 코퍼스 전체에
    흩어진다. 문턱 판정은 사전등록대로 첫 전략의 수로 하고, 이쪽은 **표본 타당성 검사**다.
    """
    result = scan_repo(repo)
    candidates = [s for s in sorted(result.symbols, key=lambda x: (x.file_path, x.start_line))
                  if is_card_candidate(s.symbol_kind, s.start_line, s.end_line)
                  and not (exclude_tests and is_test_path(s.file_path))
                  and (s.end_line - s.start_line + 1) >= min_body]

    picked = []
    if strategy == "random":
        import random
        rng = random.Random(seed)
        pool = list(candidates)
        rng.shuffle(pool)
        seen_files: set[str] = set()
        for s in pool:
            if s.file_path in seen_files:
                continue
            seen_files.add(s.file_path)
            picked.append(s)
            if len(picked) >= n:
                break
    else:
        seen_files = set()
        for s in candidates:
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
    ap.add_argument("--sample", choices=("first-per-file", "random"), default="first-per-file",
                    help="표본 전략. random 은 씨앗 고정(--seed)이라 재현된다")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--exclude-tests", action="store_true",
                    help="테스트 코드를 모집단에서 뺀다 (업무 용어로 서술할 것이 없다)")
    ap.add_argument("--min-body", type=int, default=0,
                    help="본문 최소 줄 수. 5줄짜리 부트스트랩 클래스는 서술할 내용이 없다")
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
        # 더러운 트리에서 측정한 재현성은 무엇의 재현성인지 말할 수 없다.
        print(f"거부: {state.explain()}", file=sys.stderr)
        return 1
    print(f"대상: {state.context()}")
    for w in state.warnings():
        print(f"⚠ {w}")

    import yaml

    from nexus.providers.llm import LLMService
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    # 첫 인자는 **모델 이름**이지 설정이 아니다. 설정을 넘기면 self.model 이 dict 가 되고,
    # 그 dict 가 카드의 generator 필드와 브리지 명령줄로 흘러간다 — 2026-08-16 에 실제로 그랬다.
    llm = LLMService(pricing=(cfg.get("llm") or {}).get("pricing"))
    model = llm.model

    print(f"생성자: {generator_id(model)}  (프롬프트 {PROMPT_VERSION}, 홉 {MAX_HOPS})")

    symbols, scan = pick_symbols(repo, args.symbols, strategy=args.sample, seed=args.seed,
                                 exclude_tests=args.exclude_tests, min_body=args.min_body)
    print(f"표본 전략: {args.sample}" + (f" (seed={args.seed})" if args.sample == "random" else "")
          + (f" · 테스트 제외 · 본문 ≥{args.min_body}줄" if args.exclude_tests else ""))
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
            body = sym.end_line - sym.start_line + 1
            rows.append((sym.symbol_name, a, sym.symbol_kind, body))
            print(f"  [{i}] {sym.symbol_name:<28} {a}  [{sym.symbol_kind}, {body}줄]")

    print()
    if not rows:
        print("측정 가능한 심볼이 없습니다.")
        return 1

    means = [a.mean for _, a, _, _ in rows]
    overall = sum(means) / len(means)
    print(f"domain_terms 일치도 — 심볼 {len(rows)}개 평균 {overall:.3f} "
          f"(최저 {min(means):.3f}, 최고 {max(means):.3f})")
    print(f"규칙 위반으로 버려진 카드: {rejected}건")
    print()
    print("SPEC §6.1 문턱은 0.70 이고 **잠정값**입니다 — 검색 결과에서 유도한 값이 아니라,")
    print("매칭 층이 코퍼스가 아니라 생성기 잡음을 측정하지 않도록 둔 바닥입니다.")
    if overall < 0.70:
        print("→ 문턱 미달. 이 단위는 출하하지 않습니다.")
        return 1
    print("→ 문턱 통과. 다만 표본과 실행 수를 함께 읽으십시오.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
