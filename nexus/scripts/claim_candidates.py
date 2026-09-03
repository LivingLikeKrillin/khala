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


#: 애노테이션 **다음에 오는 필드 선언**의 이름. 더 붙은 애노테이션은 건너뛴다.
FIELD_AFTER = re.compile(r"(?:\s*@\w+(?:\([^)]*\))?)*\s+[\w.<>\[\], ]+?\s+(\w+)\s*[;=]")


def field_after(text: str, pos: int) -> str:
    """`@Size(max = 20)` **뒤**에 선언된 필드 이름. 못 찾으면 빈 문자열.

    ⛔ **왜 필요한가 (실측 2026-09-03).** 해석기의 문법은 `클래스.필드@애노.속성` 이다
    (`index/code_source.py: resolve`). 필드 없이 `AdminLoginRequest.@Size.max` 로 적으면
    **해석이 안 된다** — 한 클래스에 `@Size` 필드가 여럿일 수 있으니 당연하다. 그런데 이
    스크립트는 그 모양으로 후보를 내밀고 있었고, 소유자가 그대로 받아들였다면 **값을 못 읽는
    claim** 이 심겼을 것이다. 후보 11건 중 5건이 그 모양이었다.
    """
    m = FIELD_AFTER.match(text, pos)
    return m.group(1) if m else ""


def sites_in(text: str, cls: str) -> list[tuple[str, str, str]]:
    """`(클래스, 심볼, 값)` — `static final` 상수와 값 애노테이션 둘 다.

    애노테이션 심볼은 **해석기가 읽는 모양**(`필드@애노.속성`)으로 낸다. 필드를 못 찾으면
    그 자리는 버린다 — 해석 안 되는 후보를 목록에 올리는 것은 사람에게 함정을 내미는 것이다.
    """
    out = []
    for m in CONST.finditer(text):
        if (v := literal(m.group(2))):
            out.append((cls, m.group(1), v))
    for m in ANN.finditer(text):
        if not (field := field_after(text, m.end())):
            continue
        for a in ATTR.finditer(m.group(2)):
            if (v := literal(a.group(2))):
                out.append((cls, f"{field}@{m.group(1)}.{a.group(1)}", v))
    return out


#: 한도값 애노테이션. 승인된 claim 10건 중 8건이 이 모양이다.
LIMIT_ANN = ("@Size.", "@Max.", "@Min.", "@Length.", "@Range.")


def is_limit(symbol: str) -> bool:
    """이 자리가 **한도값**인가 — 사용자가 부딪히는 상한/하한."""
    return symbol.endswith(LIMIT_ANN[0][:-1]) or any(a in symbol for a in LIMIT_ANN) \
        or symbol.startswith(("MAX_", "MIN_")) or "_MAX_" in symbol or "_MIN_" in symbol


def like_accepted(symbol: str, accepted: list[str]) -> str:
    """이미 승인된 claim 중 **같은 모양**인 것의 이름. 없으면 빈 문자열.

    ⛔ 이것은 판정이 아니라 **참고**다. 무엇이 정책 값인지는 소유자가 정한다(`OPEN.md` A42) —
    여기서 하는 일은 *"당신이 이미 받아들인 것과 같은 모양인가"* 를 보여 주는 것뿐이고,
    그 기준은 내 취향이 아니라 `claims` 테이블에 있는 사실이다. **거르지 않는다** — 모양이
    다른 후보도 목록에 그대로 남는다.
    """
    if not is_limit(symbol):
        return ""
    return next((a for a in accepted if is_limit(a.split(".", 1)[-1])), "")


def quote_line(chunk_text: str, value: str, cls: str = "", symbol: str = "",
               width: int = 110) -> str:
    """문서가 그 값을 말한 **한 줄**. 이름도 부르는 줄을 먼저 고른다.

    제목만 주면 사람이 문서를 열어야 하고, 아무 줄이나 주면 우연히 겹친 숫자를 근거로 읽는다.
    """
    hits = [t for line in chunk_text.splitlines()
            if value in line and (t := " ".join(line.split()))]
    if cls or symbol:
        named = [t for t in hits if names_symbol(t, cls, symbol)]
        hits = named or hits
    return (hits[0][:width] + ("…" if len(hits[0]) > width else "")) if hits else ""


def draft(cls: str, symbol: str, value: str) -> tuple[list[str], str]:
    """`concepts` 와 `statement` 의 **초안**. 사람이 고칠 것을 전제로 낸다.

    개념은 한국어라야 질문에 붙는데(승인된 것들이 `[닉네임]`·`[공지]` 다) 클래스 이름은 영어다.
    **번역을 지어내지 않는다** — 영어 낱말을 그대로 두고 사람이 고른다. 지어낸 번역은 질문에
    안 붙고, 안 붙는 이유를 아무도 못 찾는다.
    """
    words = re.findall(r"[A-Z][a-z]+|[a-z]+", cls)
    drop = {"create", "update", "request", "response", "config", "service", "data", "dto"}
    concepts = [w for w in words if w.lower() not in drop] or [cls]
    if (field := symbol.split("@")[0]) and "@" in symbol:
        concepts = [field] + concepts
    what = "최대" if "Size" in symbol or "MAX" in symbol else ("최소" if "Min" in symbol else "")
    return concepts, f"{' '.join(concepts)} 의 {what} 값은 {value} 이다".replace("  ", " ")


def names_symbol(line: str, cls: str, symbol: str) -> bool:
    """그 문장이 **값만이 아니라 이름도** 부르는가.

    ⛔ **왜 필요한가 (실측 2026-09-03).** 신호가 *"그 값의 숫자가 어느 청크엔가 있다"* 뿐이면
    세 자리 수는 거의 항상 우연히 겹친다. 인용을 붙여 보고서야 보였다 — 후보 9건 중 7건의
    '근거 문장' 이 임베딩 지연 `128 ms`, 디제잉 포인트 표의 `5000`, QA 체크리스트였다.
    숫자가 겹쳤을 뿐 그 문장은 이 상수에 대해 아무 말도 하지 않는다.

    그래서 **문장이 이름도 불러야** 후보로 친다. 이름은 세 모양으로 나타난다 —
    `MAX_NOTICE_CONTENT_LENGTH`(상수 그대로) · `max_notice_content_length`(설정 키) ·
    `noticeContent`(필드). 셋 다 소문자·구분자 제거로 접어서 비교한다.
    """
    flat = re.sub(r"[^a-z0-9]", "", line.lower())
    parts = [symbol.split("@")[0], symbol, cls]
    return any(re.sub(r"[^a-z0-9]", "", p.lower()) in flat for p in parts if len(p) > 3)


def claim_id(cls: str, symbol: str) -> str:
    """`claims.yaml` 의 id. 소문자 · `@`/`.` 는 `-` 로."""
    tail = symbol.lower().replace("@", "-").replace(".", "-").strip("-")
    return f"{cls.lower()}-{tail}".replace("--", "-")


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
    rows, counts = [], {"후보": 0, "흔해서 판정 못 함": 0, "문서에 없음": 0, "해석 안 됨": 0}
    unresolved: list[str] = []
    async with pool.acquire() as con:
        anchored = {r["symbol_name"] for r in await con.fetch(
            "SELECT DISTINCT symbol_name FROM doc_code_anchors")}
        # 이미 승인된 claim 의 모양. **거르는 데 쓰지 않고 보여 주는 데만 쓴다.**
        accepted = [r["value_source"] for r in await con.fetch(
            "SELECT value_source FROM claims WHERE tenant = ANY($1)", tenants)]
        for cls, sym, val in sites:
            n = await con.fetchval(
                "SELECT count(*) FROM chunks WHERE tenant = ANY($1) AND status = 'active' "
                "  AND is_quarantined = false AND chunk_text LIKE '%' || $2 || '%'",
                tenants, val)
            counts[b := bucket(n)] += 1
            if b != "후보":
                continue
            titles = await con.fetch(
                "SELECT DISTINCT d.title, c.chunk_text FROM chunks c "
                "JOIN documents d ON d.rid = c.doc_rid AND d.tenant = c.tenant "
                "WHERE c.tenant = ANY($1) AND c.status = 'active' "
                "  AND c.chunk_text LIKE '%' || $2 || '%' LIMIT 4",
                tenants, val)
            got = resolver.resolve(f"{cls}.{sym}")
            if not got.found:
                counts["해석 안 됨"] += 1
                unresolved.append(f"{cls}.{sym} — {(got.reason or '')[:70]}")
                continue
            rows.append({"cls": cls, "symbol": sym, "value": val, "chunks": n,
                         "class_named": cls in anchored,

                         "resolved": got.value,
                         "like": like_accepted(f"{cls}.{sym}", accepted),
                         "quote": (q := next((x for x in
                                       (quote_line(r["chunk_text"], val, cls, sym)
                                        for r in titles) if x), "")),
                         # **하나의 정의**: 고른 인용 문장 자체가 이름을 부르는가. 청크 단위로
                         # 보면 문서 어딘가에 클래스 이름이 있다는 이유로 우연한 일치가 통과한다.
                         "names": bool(q) and names_symbol(q, cls, sym),
                         "docs": [r["title"] for r in titles]})
    await db.close_pool()

    rows.sort(key=lambda r: (not r["class_named"], r["chunks"]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(_sheet(rows, counts, len(sites), len(files), unresolved),
                        encoding="utf-8")
    print(f"자리 {len(sites)} · 후보 {counts['후보']} "
          f"(흔해서 판정 못 함 {counts['흔해서 판정 못 함']} · 문서에 없음 {counts['문서에 없음']})")
    print(f"검토 시트: {args.out}")
    return 0


def _sheet(rows: list[dict], counts: dict, n_sites: int, n_files: int,
           unresolved: list[str]) -> str:
    """사람이 고를 시트. **버린 것을 맨 위에 적는다** — 목록이 조용히 좁아지면 안 된다."""
    out = [
        "# claim 후보 — 문서가 그 값을 말하고 있는 코드 자리",
        "",
        f"- 생성 {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- 훑은 파일 {n_files} · 값을 문서에서 찾을 수 있는 모양의 자리 **{n_sites}**",
        f"- ⚠ **버린 것**: 값이 흔해서 판정 못 함 **{counts['흔해서 판정 못 함']}** · "
        f"문서에 그 값이 없음 **{counts['문서에 없음']}** · "
        f"코드에서 값을 못 읽음 **{counts['해석 안 됨']}**",
        "",
        "> 이 목록은 **정밀도가 높고 재현율이 낮다.** 흔한 수는 문서 여러 곳에 나오고 그중 하나가",
        "> 진짜 그 정책 값일 수 있는데, 그건 여기서 못 가른다. 위의 '버린 것' 수가 그 크기다.",
        "",
        "**당신이 정할 것은 하나다 — 정책 값인가.** 나머지는 초안이 채워져 있으니 고치기만 하면",
        "된다. 그리고 여기 실린 것은 전부 **지금 코드에서 값이 읽힌다** — 그것부터 확인하고 올린다",
        "(2026-09-03 이전 판은 필드 이름을 빼먹어 애노테이션 후보가 통째로 해석 불가였다).",
        "",
    ]
    weak = [r for r in rows if not r["names"]]
    rows = [r for r in rows if r["names"]]
    if weak:
        out += [f"- ⚠ **숫자만 겹친 자리 {len(weak)}건은 부록으로 내렸다** — 근거 문장이 그 상수의",
                "  이름을 부르지 않는다. 세 자리 수는 문서 아무 데서나 겹친다.", ""]
    if not rows:
        out += ["**후보 없음.** 값을 말하면서 이름도 부르는 문서 문장이 하나도 없다.", "",
                "이것도 자료다 — 조직 문서가 코드 상수를 값으로 인용하지 않는다는 뜻이고,",
                "그러면 claim 을 심어도 붙을 질문이 없다.", ""]
    for i, r in enumerate(rows, 1):
        out += [
            f"## {i}. `{r['cls']}.{r['symbol']}`",
            "",
            f"- 문서에서 이 값이 나오는 청크 **{r['chunks']}**개"
            + ("  · 문서가 이 클래스 이름도 부른다" if r["class_named"] else ""),
            f"- 그 문서들: {', '.join(r['docs']) or '(제목 없음)'}",
            f"- 지금 코드 값: **{r['resolved']}**",
        ] + ([f"- 문서가 말한 문장: > {r['quote']}"] if r["quote"] else []) + [
            (f"- ⭐ **이미 승인한 `{r['like']}` 와 같은 모양이다**" if r["like"]
             else "- ⚠ 승인된 10건과 다른 모양이다 (튜닝 손잡이·내부 ID 일 수 있다)"),
            "",
            "```yaml",
            f"- claim_id: {claim_id(r['cls'], r['symbol'])}",
            "  kind: invariant",
            f"  value_source: \"{r['cls']}.{r['symbol']}\"",
            f"  value_ref_kind: {'code_annotation' if r['symbol'].startswith('@') else 'code_constant'}",
            f"  concepts: [{', '.join(draft(r['cls'], r['symbol'], r['value'])[0])}]"
            "   # ← 초안. 한국어로 고쳐라 — 전부 나와야 붙는다",
            f"  statement: \"{draft(r['cls'], r['symbol'], r['value'])[1]}\"  # ← 초안",
            "  owner: \"\"           # ← 사람",
            "```",
            "",
            "- [ ] 정책 값이다 (위를 채워 `claims.yaml` 로) · [ ] 아니다 (넘김)",
            "",
        ]
    if weak:
        out += ["## 부록 — 숫자만 겹친 자리", "",
                "근거 문장이 그 상수의 이름을 부르지 않는다. 목록이 조용히 좁아지지 않게 적어 둔다.",
                ""]
        for r in weak:
            out.append(f"- `{r['cls']}.{r['symbol']}` = {r['value']} — 문서: "
                       f"{r['quote'][:80] or '(문장 없음)'}")
        out.append("")
    if unresolved:
        out += ["## 부록 — 코드에서 값을 못 읽어 뺀 자리", "",
                "목록이 조용히 좁아지지 않게 적어 둔다. 대개 필드를 못 찾은 애노테이션이다.", ""]
        out += [f"- `{u}`" for u in unresolved[:20]]
        out.append("")
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
