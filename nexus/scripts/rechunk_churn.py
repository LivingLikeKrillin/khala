"""편집 하나가 **몇 개의 청크 rid 를 바꾸는가** — 결정론, LLM 0회, DB 쓰기 0.

⛔ **왜 있나 (`research/2026-09-06-getting-org-documents-into-rag.md` §2.2).** 관행의 처방은
청크 ID 를 `소스 레코드 ID + 그 청크 내용의 해시` 에서 파생시키는 것이다 — 그러면 재청크해도
**안 바뀐 청크는 ID 가 유지되고** 바뀐 것만 재임베딩된다. 이 리포는 정반대다:

    chunk_rid(doc_rid, section_path, chunk_index)

그리고 `chunk_index` 는 `chunker.py` 에서 **문서 전체에 걸쳐 단조 증가**한다(`global_index`).

⛔ **첫 가설은 틀렸고 이 측정이 반증했다.** *"앞쪽에 한 문장이 들어가면 그 뒤 rid 가 전부
밀린다"* 고 적었는데, 실측은 **0** 이다. rid 는 `(section_path, global_index)` 이고 작은 편집은
**청크 경계를 안 건드리므로** 그 짝이 그대로다. 바뀌는 것은 한 청크의 본문뿐이다.

⭐ **이탈의 방아쇠는 위치가 아니라 청크 수다.** 편집이 청크를 하나라도 늘리거나 줄이면 그
지점 뒤의 인덱스가 전부 밀리고, 그때는 **거의 전부**가 이탈한다 — 그리고 그 이탈은 사실상
전량이 낭비다(본문은 하나만 바뀌었으므로).

**여기서 내는 것은 그 낭비의 크기다.** 처방이 아니다 — 청크 ID 체계를 바꾸는 것은 되돌리기
비싼 변경이고, 이 리포의 규칙은 크기를 먼저 측정한 뒤 게이트를 지나는 것이다.

⚠ **판정하지 않는다. 문턱도 없다.** 분포만 낸다.

⚠ **한계 셋.**

1. **리포 문서를 쓴다.** 조직 문서(`design_docs`)는 gitignore 밖이라 여기서 못 읽는다.
   길이·절 구조·언어가 다르면 수도 다르다.
2. **편집 셋은 내가 지어낸 모양**이다. 실제 편집의 분포가 아니다 — 앞·중간·끝 세 극점을
   찍어 **범위**를 보는 것이지 기댓값을 내는 것이 아니다.
3. **rid 만 본다.** 재임베딩 비용과 고아가 된 참조(span 후보·라벨·피드백)는 rid 변화의
   **결과**이지 여기서 세는 값이 아니다.

    docker exec nexus-app python -m scripts.rechunk_churn --glob 'docs/**/*.md'
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

if sys.platform == "win32":          # cp949 콘솔이 ⚠ 에서 죽는다 (`arbiter/cli.py` 와 같은 패턴)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                # noqa: BLE001 — 재구성 불가 환경이면 그냥 둔다
        pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

from nexus.ingest.chunker import chunk_document  # noqa: E402
from nexus.rid import chunk_rid  # noqa: E402

#: 비교에만 쓰는 고정 부모. 문서마다 달라도 결과가 같으므로 하나로 둔다.
DOC_RID = "doc_measurement"

#: 편집 세 모양. **극점을 찍는 것**이지 실제 분포가 아니다.
EDITS = ("top", "middle", "append", "top_block")


def _body_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def apply_edit(content: str, kind: str) -> str:
    """한 문장을 넣거나 고친다. **절 제목을 만들지 않는다** — 만들면 `section_path` 까지
    바뀌어 두 원인이 섞이고, 여기서 보려는 것은 `chunk_index` 하나다."""
    lines = content.split("\n")
    if kind == "append":
        return content.rstrip("\n") + "\n\n측정용으로 덧붙인 문장이다.\n"
    if kind == "top":
        # 첫 본문 줄 바로 앞에 넣는다(제목·frontmatter 뒤).
        for i, ln in enumerate(lines):
            if ln.strip() and not ln.startswith(("#", "---", "*", "|")):
                lines.insert(i, "측정용으로 앞쪽에 끼워 넣은 문장이다.\n")
                return "\n".join(lines)
        return content
    if kind == "top_block":
        # ⭐ **작은 편집은 청크 경계를 안 건드린다** — 첫 판이 그것을 몰라서 rid 이탈 0 을 보고
        # 가설이 틀렸다고 읽을 뻔했다. 이탈은 **청크 수가 바뀔 때** 난다. 그래서 토큰 목표를
        # 넘길 만큼의 문단을 앞쪽에 넣어 그 경우를 따로 찍는다(절 제목은 여전히 안 만든다).
        block = "\n".join(["측정용으로 앞쪽에 끼워 넣은 문단이다." * 12] * 24)
        for i, ln in enumerate(lines):
            if ln.strip() and not ln.startswith(("#", "---", "*", "|")):
                lines.insert(i, block + "\n")
                return "\n".join(lines)
        return content
    if kind == "middle":
        mid = len(lines) // 2
        for i in range(mid, len(lines)):
            if lines[i].strip() and not lines[i].startswith(("#", "---", "|")):
                lines[i] = lines[i] + " (측정용 덧말)"
                return "\n".join(lines)
        return content
    raise ValueError(f"알 수 없는 편집 모양: {kind}")


def churn(content: str, edited: str, cfg: dict, language: str) -> dict:
    """원본과 편집본을 **프로덕션 청커**로 갈라 rid 를 견준다.

    ⭐ 세는 것 둘을 구분한다 — *rid 가 바뀐 청크* 와 *본문이 바뀐 청크*. 그 차이가 낭비다.
    """
    before = chunk_document(content, language=language, config=cfg)
    after = chunk_document(edited, language=language, config=cfg)

    rid_before = {chunk_rid(DOC_RID, c.section_path, c.chunk_index): _body_hash(c.chunk_text)
                  for c in before}
    rid_after = {chunk_rid(DOC_RID, c.section_path, c.chunk_index): _body_hash(c.chunk_text)
                 for c in after}

    body_before = {_body_hash(c.chunk_text) for c in before}
    body_after = {_body_hash(c.chunk_text) for c in after}

    # rid 가 사라진 것 = 그 rid 를 참조하던 모든 것이 고아가 된다
    gone = set(rid_before) - set(rid_after)
    # 그중 **본문이 그대로 살아 있는** 것 = 순수 낭비 (내용은 안 바뀌었는데 이름이 바뀌었다)
    wasted = {r for r in gone if rid_before[r] in body_after}

    return {
        "chunks_before": len(before),
        "chunks_after": len(after),
        "rids_gone": len(gone),
        "bodies_changed": len(body_before - body_after),
        "rid_churn_without_body_change": len(wasted),
    }


def report_lines(rows: list[dict]) -> list[str]:
    """**분포만 낸다.** 이 수로 무엇을 자르지 않는다."""
    out = ["", f"{'문서':<44}{'편집':>8}{'청크':>6}{'rid사라짐':>10}{'본문바뀜':>9}{'낭비':>7}"]
    out.append("-" * 84)
    for r in rows:
        out.append(f"{r['doc'][:42]:<44}{r['edit']:>8}{r['chunks_before']:>6}"
                   f"{r['rids_gone']:>10}{r['bodies_changed']:>9}"
                   f"{r['rid_churn_without_body_change']:>7}")
    for kind in EDITS:
        sub = [r for r in rows if r["edit"] == kind]
        if not sub:
            continue
        out.append(f"\n  [{kind}] 문서 {len(sub)}건 · rid 사라짐 합 "
                   f"{sum(r['rids_gone'] for r in sub)} · 본문 바뀜 합 "
                   f"{sum(r['bodies_changed'] for r in sub)} · **낭비 합 "
                   f"{sum(r['rid_churn_without_body_change'] for r in sub)}**")
    out += ["",
            "⚠ `낭비` = rid 는 사라졌는데 **그 본문이 편집본에 그대로 살아 있는** 청크 수.",
            "   내용이 안 바뀌었는데 이름이 바뀐 것이고, 재임베딩과 고아 참조가 여기서 난다.",
            "⚠ 편집 세 모양은 극점이지 실제 분포가 아니다 — 범위를 보는 값이다.",
            "⚠ 리포 문서로 측정했다. 조직 문서는 길이·절 구조·언어가 다르다."]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--glob", action="append", required=True,
                    help="측정할 markdown (여러 번 줄 수 있다)")
    ap.add_argument("--root", default=".", help="glob 기준 디렉터리")
    ap.add_argument("--language", default="ko", choices=("ko", "en", "mixed"))
    ap.add_argument("--config", default="config.yaml",
                    help="프로덕션과 **같은 청킹 설정**을 쓴다")
    ap.add_argument("--limit", type=int, default=20, help="문서 수 상한")
    args = ap.parse_args()

    cfg_path = Path(args.config)
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    print(f"  청킹 설정: {cfg.get('chunking')}")

    root = Path(args.root)
    files: list[Path] = []
    for pattern in args.glob:
        files += sorted(p for p in root.glob(pattern) if p.is_file())
    files = files[:args.limit]
    if not files:
        print("⛔ 측정할 문서가 없다 — glob 을 확인하라.")
        return 2

    rows = []
    for f in files:
        content = f.read_text(encoding="utf-8", errors="replace")
        if not content.strip():
            continue
        for kind in EDITS:
            edited = apply_edit(content, kind)
            if edited == content:
                continue
            rows.append({"doc": str(f.relative_to(root)), "edit": kind,
                         **churn(content, edited, cfg, args.language)})

    for line in report_lines(rows):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
