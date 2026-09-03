"""claim 후보 뽑기 — **문서가 그 값을 말하고 있는** 코드 자리만. 사람이 고를 목록을 만든다.

⛔ **왜 이 모양인가 (실측 2026-09-03).** `OPEN.md` A42 의 처분은 *"후보를 기계로 뽑아 소유자가
고른다"* 이고 그건 맞다 — *"이 값이 정책인가"* 는 판단이다. 그런데 후보를 **"코드에 상수가
있다"** 로 뽑으면 **267개**가 나온다(상수 174 · 값 애노테이션 93, 파일 766개). 267줄을 사람에게
내미는 것은 고르라는 것이 아니라 **일을 넘기는 것**이다.

claim 의 값은 **문서가 그 값을 주장할 때** 생긴다 — 문서 값과 코드 값을 나란히 놓는 것이 이
기능의 전부이므로, 문서가 말한 적 없는 상수는 claim 이 되어도 아무 질문에 안 붙는다. 그래서
후보를 *"문서가 이 값을 말한다"* 로 뽑는다. 실측: 267 → **11**(그중 8은 문서가 클래스 이름도
부른다).

⚠ **이 목록은 정밀도가 높고 재현율이 낮다.** 값이 흔한 수(두 자리라도 `30` 같은)면 문서 여러
곳에 나오고, 그중 하나가 진짜 그 정책 값일 수 있다. 그건 여기서 못 가른다 — 그래서 **버린 것을
같이 센다**(§흔해서 판정 못 함). 목록이 조용히 좁아지면 다음 사람이 그 좁힘을 못 본다.

⚠ 출력은 조직 문서의 값과 인용을 담는다 — **gitignore 된 곳에만** 쓴다.

    docker exec nexus-app python -m scripts.claim_candidates \\
        --out /app/tests/eval/local/claim-candidates.md
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CONST = re.compile(r"static\s+final\s+\w+\s+([A-Z][A-Z0-9_]*)\s*=\s*([^;]+);")
ANN = re.compile(r"@(Size|Max|Min|Length|Range)\s*\(([^)]*)\)")
ATTR = re.compile(r"(\w+)\s*=\s*([^,]+)")
NUM = re.compile(r"-?\d[\d_]*")

#: 한 자리 수는 문서 아무 데나 나온다. 이 아래로 내리면 잡음이 결과가 된다.
MIN_DIGITS = 2

#: 이보다 많은 청크에 나오면 "그 값이 문서에 있다" 는 말이 뜻을 잃는다.
#: ⛔ **이 수에는 근거가 없다** — 고른 것이지 측정한 것이 아니다. 그래서 이 문턱에 걸려 빠진
#: 자리를 **세어서 같이 보고한다**. 문턱을 감추면 그 문턱이 곧 사실로 읽힌다.
COMMON_CHUNKS = 12


def literal(expr: str) -> str | None:
    """문서에서 **찾을 수 있는 모양**의 값인가. 계산식·상수 참조는 뺀다."""
    e = expr.strip().rstrip("Ll").replace("_", "")
    if not NUM.fullmatch(e):
        return None
    return e if len(e.lstrip("-")) >= MIN_DIGITS else None


def sites_in(text: str, cls: str) -> list[tuple[str, str, str]]:
    """`(클래스, 심볼, 값)` — `static final` 상수와 값 애노테이션 둘 다."""
    out = []
    for m in CONST.finditer(text):
        if (v := literal(m.group(2))):
            out.append((cls, m.group(1), v))
    for m in ANN.finditer(text):
        for a in ATTR.finditer(m.group(2)):
            if (v := literal(a.group(2))):
                out.append((cls, f"@{m.group(1)}.{a.group(1)}", v))
    return out


def bucket(n_chunks: int) -> str:
    """이 자리를 어느 칸에 넣는가. 셋을 다 보고한다 — 버린 것이 안 보이면 목록이 거짓말한다."""
    if n_chunks == 0:
        return "문서에 없음"
    return "흔해서 판정 못 함" if n_chunks > COMMON_CHUNKS else "후보"


async def _run(args) -> int:
    from nexus import db
    from nexus.api import _load_config
    from nexus.index.code_source import CodeValueResolver

    cfg = _load_config()
    repo = (cfg.get("code_source") or {}).get("repo_path", "")
    if not repo:
        print("✗ code_source.repo_path 가 없다 — 코드가 마운트되지 않았다")
        return 1
    resolver = CodeValueResolver(repo)
    files = resolver._eligible_files()

    sites: list[tuple[str, str, str]] = []
    for f in files:
        try:
            sites += sites_in(f.read_text(encoding="utf-8", errors="replace"), f.stem)
        except OSError:
            continue

    tenants = [t.strip() for t in args.tenant.split(",") if t.strip()]
    pool = await db.get_pool()
    rows, counts = [], {"후보": 0, "흔해서 판정 못 함": 0, "문서에 없음": 0}
    async with pool.acquire() as con:
        anchored = {r["symbol_name"] for r in await con.fetch(
            "SELECT DISTINCT symbol_name FROM doc_code_anchors")}
        for cls, sym, val in sites:
            n = await con.fetchval(
                "SELECT count(*) FROM chunks WHERE tenant = ANY($1) AND status = 'active' "
                "  AND is_quarantined = false AND chunk_text LIKE '%' || $2 || '%'",
                tenants, val)
            counts[b := bucket(n)] += 1
            if b != "후보":
                continue
            titles = await con.fetch(
                "SELECT DISTINCT d.title FROM chunks c "
                "JOIN documents d ON d.rid = c.doc_rid AND d.tenant = c.tenant "
                "WHERE c.tenant = ANY($1) AND c.status = 'active' "
                "  AND c.chunk_text LIKE '%' || $2 || '%' LIMIT 4",
                tenants, val)
            rows.append({"cls": cls, "symbol": sym, "value": val, "chunks": n,
                         "class_named": cls in anchored,
                         "docs": [r["title"] for r in titles]})
    await db.close_pool()

    rows.sort(key=lambda r: (not r["class_named"], r["chunks"]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(_sheet(rows, counts, len(sites), len(files)), encoding="utf-8")
    print(f"자리 {len(sites)} · 후보 {counts['후보']} "
          f"(흔해서 판정 못 함 {counts['흔해서 판정 못 함']} · 문서에 없음 {counts['문서에 없음']})")
    print(f"검토 시트: {args.out}")
    return 0


def _sheet(rows: list[dict], counts: dict, n_sites: int, n_files: int) -> str:
    """사람이 고를 시트. **버린 것을 맨 위에 적는다** — 목록이 조용히 좁아지면 안 된다."""
    out = [
        "# claim 후보 — 문서가 그 값을 말하고 있는 코드 자리",
        "",
        f"- 생성 {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- 훑은 파일 {n_files} · 값을 문서에서 찾을 수 있는 모양의 자리 **{n_sites}**",
        f"- ⚠ **버린 것**: 값이 흔해서 판정 못 함 **{counts['흔해서 판정 못 함']}** · "
        f"문서에 그 값이 없음 **{counts['문서에 없음']}**",
        "",
        "> 이 목록은 **정밀도가 높고 재현율이 낮다.** 흔한 수는 문서 여러 곳에 나오고 그중 하나가",
        "> 진짜 그 정책 값일 수 있는데, 그건 여기서 못 가른다. 위의 '버린 것' 수가 그 크기다.",
        "",
        "각 줄에서 정할 것은 둘이다 — **정책 값인가**, 그리고 **사람이 물을 때 쓰는 낱말**.",
        "나머지 칸(`claim_id`·`kind`·`value_source`·`value_ref_kind`)은 기계가 채운다.",
        "",
    ]
    if not rows:
        out.append("후보 없음.")
        return "\n".join(out) + "\n"
    for i, r in enumerate(rows, 1):
        out += [
            f"## {i}. `{r['cls']}.{r['symbol']}`",
            "",
            f"- 문서에서 이 값이 나오는 청크 **{r['chunks']}**개"
            + ("  · 문서가 이 클래스 이름도 부른다" if r["class_named"] else ""),
            f"- 그 문서들: {', '.join(r['docs']) or '(제목 없음)'}",
            "",
            "```yaml",
            f"- claim_id: {r['cls'].lower()}-{r['symbol'].lower().replace('@', '').replace('.', '-')}",
            "  kind: invariant",
            f"  value_source: \"{r['cls']}.{r['symbol']}\"",
            f"  value_ref_kind: {'code_annotation' if r['symbol'].startswith('@') else 'code_constant'}",
            "  concepts: []        # ← 사람: 이 값을 물을 때 쓰는 낱말 (전부 나와야 붙는다)",
            "  statement: \"\"       # ← 사람: 이 값이 무슨 뜻인가, 한 줄",
            "  owner: \"\"           # ← 사람",
            "```",
            "",
            "- [ ] 정책 값이다 (위를 채워 `claims.yaml` 로) · [ ] 아니다 (넘김)",
            "",
        ]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tenant", default="default,design_docs", help="문서를 찾을 테넌트")
    p.add_argument("--out", type=Path, required=True,
                   help="검토 시트. 조직 문서의 값·제목이 들어가므로 gitignore 된 곳에")
    return asyncio.run(_run(p.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
