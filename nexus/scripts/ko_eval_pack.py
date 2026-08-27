"""한국어 평가 코퍼스 팩 — 빌드·검증 (SPEC-nexus-korean-retrieval-eval §4.1).

**평가 하니스가 움직이면 평가 하니스가 아니다.** 이 팩은 `kubernetes/website` 의 한국어 문서를 **커밋 SHA 로 못박아**
가져와 정규화하고, 파일별 해시를 매니페스트에 적어 리포에 커밋한다. 라이브 Notion 미러를 안 쓰는
이유는 기술이 아니라 공개 리포이기 때문이다 — 조직 내부 문서를 재배포하게 된다 (SPEC §4.1).

세 가지가 이 파일의 전부다:

1. **선택 규칙** — 업스트림 **원본 바이트** 기준(변환 전). 매니페스트를 믿는 게 아니라 규칙을
   업스트림 트리에 다시 걸어 대조한다(`check`). 첫 실행이 표준이 되면 안 된다.
2. **정규화** — NFC → front-matter → 숏코드 → 주석/개행/공백. NFC 가 맨 앞인 이유: 한글은 플랫폼에
   따라 NFC/NFD 로 오가는데, 둘은 **해시도 다르고 형태소 분해도 다르다**. 재는 대상이 흔들린다.
3. **검증** — 오프라인. 커밋된 팩이 커밋된 매니페스트와 바이트 단위로 일치하는지.

숏코드 규칙이 셋인 이유는 실측이다(265파일·2,872태그, 2026-08-02): `text="…"` 를 가진 태그가 464개,
그중 387개가 한글이다. `{{< glossary_tooltip text="파드" term_id="pod" >}}` 를 통째로 지우면
**외래어 층(loanword)이 재려는 어휘 자체가 사라진다.** 초안 규칙이 정확히 그렇게 했다.

    python -m scripts.ko_eval_pack build   [--pack-dir DIR]   # 네트워크. 팩+매니페스트 생성
    python -m scripts.ko_eval_pack verify  [--pack-dir DIR]   # 오프라인. 커밋된 팩 대조
    python -m scripts.ko_eval_pack check   [--pack-dir DIR]   # 네트워크. 선택 규칙 재유도 대조
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

# ── 핀 (SPEC §4.1) ────────────────────────────────────────────────────────────

PACK_ID = "ko-k8s-2026-08-01"
UPSTREAM_REPO = "kubernetes/website"
UPSTREAM_SHA = "b035ea80a2f666e0a60923560984458806788104"
UPSTREAM_LICENSE = "CC-BY-4.0"

PATH_PREFIX = "content/ko/docs/"
SECTIONS = ("concepts", "tasks", "tutorials", "setup")
MIN_BYTES = 2048
MAX_BYTES = 40960

DEFAULT_PACK_DIR = Path(__file__).resolve().parents[1] / "tests" / "eval" / "ko" / "corpus"

_TREE_URL = f"https://api.github.com/repos/{UPSTREAM_REPO}/git/trees/{UPSTREAM_SHA}?recursive=1"
_RAW_URL = f"https://raw.githubusercontent.com/{UPSTREAM_REPO}/{UPSTREAM_SHA}/{{path}}"


# ── 1. 선택 규칙 ──────────────────────────────────────────────────────────────

def selects(path: str, size: int) -> bool:
    """업스트림 트리 엔트리 하나가 팩에 들어가는가. **원본 바이트 기준**(정규화 전)."""
    if not path.startswith(PATH_PREFIX) or not path.endswith(".md"):
        return False
    if path.rsplit("/", 1)[-1] == "_index.md":
        return False
    rest = path[len(PATH_PREFIX):]
    if rest.split("/", 1)[0] not in SECTIONS:
        return False
    return MIN_BYTES <= size <= MAX_BYTES


def select_tree(tree: list[dict]) -> list[dict]:
    """트리 API 응답 → 선택된 blob 엔트리(경로 정렬). 규칙은 `selects()` 하나뿐."""
    picked = [e for e in tree if e.get("type") == "blob" and selects(e.get("path", ""), e.get("size", 0))]
    return sorted(picked, key=lambda e: e["path"])


def pack_relative(upstream_path: str) -> str:
    """`content/ko/docs/concepts/x.md` → `concepts/x.md`."""
    return upstream_path[len(PATH_PREFIX):]


# ── 2. 정규화 ─────────────────────────────────────────────────────────────────

_FRONT_MATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---[ \t]*\r?\n", re.DOTALL)
_TITLE = re.compile(r"^title:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_SHORTCODE = re.compile(r"\{\{<.*?>\}\}|\{\{%.*?%\}\}", re.DOTALL)
_TEXT_ATTR = re.compile(r'\btext="([^"]*)"')
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def strip_front_matter(text: str) -> str:
    """YAML front-matter 제거. `title:` 은 `# ` 제목으로 살린다(문서의 이름은 검색 신호다)."""
    m = _FRONT_MATTER.match(text)
    if not m:
        return text
    body = text[m.end():]
    tm = _TITLE.search(m.group(1))
    if not tm:
        return body
    title = tm.group(1).strip().strip("\"'")
    return f"# {title}\n\n{body}" if title else body


def strip_shortcodes(text: str) -> str:
    """Hugo 숏코드 세 규칙 (SPEC §4.1). 두 구분자 형식(`{{< >}}`·`{{% %}}`)을 동일 취급한다.

    태그 단위 치환이므로 중첩은 자동으로 안쪽부터 해결된다: 짝 태그는 양쪽이 각각 지워지고 사이의
    내용은 그대로 남는다 — `{{< note >}}` 안에 있는 `text=` 태그도 규칙 1을 그대로 받는다.
    """
    def sub(m: re.Match[str]) -> str:
        tm = _TEXT_ATTR.search(m.group(0))
        return tm.group(1) if tm else ""       # 규칙 1 아니면 규칙 2·3 (둘 다 '태그 삭제')

    return _SHORTCODE.sub(sub, text)


def normalize(text: str) -> str:
    """원본 마크다운 → 팩에 들어갈 텍스트. **NFC 가 먼저**(§4.1)."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = strip_front_matter(text)
    text = strip_shortcodes(text)
    text = _HTML_COMMENT.sub("", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return text.strip("\n") + "\n"


# ── 3. 매니페스트 ─────────────────────────────────────────────────────────────

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_manifest(documents: list[dict]) -> dict:
    """문서 엔트리 목록 → 매니페스트. 숫자는 세어서 넣는다(본문에서 베끼지 않는다)."""
    docs = sorted(documents, key=lambda d: d["path"])
    return {
        "pack": PACK_ID,
        "upstream": {"repo": UPSTREAM_REPO, "sha": UPSTREAM_SHA, "license": UPSTREAM_LICENSE},
        "rule": {
            "path_prefix": PATH_PREFIX, "sections": list(SECTIONS),
            "skip_basename": "_index.md", "min_bytes": MIN_BYTES, "max_bytes": MAX_BYTES,
            "size_basis": "upstream blob bytes, before normalisation",
        },
        "normalisation": ["NFC", "front-matter stripped (title kept as heading)",
                          "hugo shortcodes: text= kept, others removed",
                          "html comments removed", "CRLF->LF", "trailing whitespace",
                          "single final newline"],
        "count": len(docs),
        "bytes_total": sum(d["bytes"] for d in docs),
        "documents": docs,
    }


def verify(pack_dir: Path) -> list[str]:
    """오프라인 검증. 문제를 문자열 목록으로 돌려준다(빈 목록 = 통과).

    바꿔치기·누락·잉여 파일·개수 불일치를 전부 잡는다. 하나라도 걸리면 그건 결과가 아니다.
    """
    problems: list[str] = []
    mpath = pack_dir / "manifest.json"
    if not mpath.exists():
        return [f"매니페스트 없음: {mpath}"]
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    docs_dir = pack_dir / "docs"

    entries = manifest.get("documents", [])
    if manifest.get("count") != len(entries):
        problems.append(f"count({manifest.get('count')}) != documents({len(entries)})")

    seen: set[Path] = set()
    for e in entries:
        f = docs_dir / e["path"]
        if not f.exists():
            problems.append(f"누락: {e['path']}")
            continue
        seen.add(f.resolve())
        data = f.read_bytes()
        if sha256_bytes(data) != e["sha256"]:
            problems.append(f"해시 불일치: {e['path']}")
        elif len(data) != e["bytes"]:
            problems.append(f"크기 불일치: {e['path']}")

    if docs_dir.exists():
        for f in docs_dir.rglob("*.md"):
            if f.resolve() not in seen:
                problems.append(f"매니페스트에 없는 파일: {f.relative_to(docs_dir).as_posix()}")

    total = sum(e["bytes"] for e in entries)
    if manifest.get("bytes_total") != total:
        problems.append(f"bytes_total({manifest.get('bytes_total')}) != 합계({total})")
    return problems


# ── 4. 네트워크 (빌드·대조) ───────────────────────────────────────────────────

def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "khala-ko-eval-pack"})
    with urllib.request.urlopen(req, timeout=60) as resp:      # noqa: S310 — 고정된 https 상수 URL
        return resp.read()


def fetch_tree() -> list[dict]:
    payload = json.loads(_fetch(_TREE_URL).decode("utf-8"))
    if payload.get("truncated"):
        raise RuntimeError("업스트림 트리가 잘렸다 — 선택 규칙을 신뢰할 수 없다")
    return payload.get("tree", [])


def fetch_blob(path: str) -> bytes:
    return _fetch(_RAW_URL.format(path=path))


def build(pack_dir: Path, tree: list[dict] | None = None, fetch=fetch_blob, workers: int = 12) -> dict:
    """업스트림에서 팩을 만든다. `tree`/`fetch` 는 테스트에서 주입한다(네트워크 없이 돌도록)."""
    entries = select_tree(tree if tree is not None else fetch_tree())
    docs_dir = pack_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    def one(e: dict) -> dict:
        raw = fetch(e["path"]).decode("utf-8")
        packed = normalize(raw).encode("utf-8")
        rel = pack_relative(e["path"])
        out = docs_dir / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(packed)
        return {"path": rel, "upstream_path": e["path"], "blob_sha1": e["sha"],
                "sha256": sha256_bytes(packed), "bytes": len(packed)}

    with cf.ThreadPoolExecutor(workers) as ex:
        documents = list(ex.map(one, entries))

    manifest = build_manifest(documents)
    # newline="\n": Windows 의 기본 개행 변환이 매니페스트를 플랫폼마다 다른 바이트로 만든다.
    # 문서 본문은 write_bytes 라 무관하지만, 평가 하니스 자체가 플랫폼을 타면 안 된다.
    (pack_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    return manifest


def check(pack_dir: Path, tree: list[dict] | None = None) -> list[str]:
    """선택 규칙을 업스트림 트리에 **다시 걸어** 커밋된 팩과 대조한다.

    매니페스트 자기검증만으로는 '첫 실행이 곧 표준' 을 못 막는다. 규칙과 팩이 어긋나면 규칙이 이긴다.
    """
    entries = select_tree(tree if tree is not None else fetch_tree())
    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    want = {pack_relative(e["path"]): e["sha"] for e in entries}
    have = {d["path"]: d["blob_sha1"] for d in manifest.get("documents", [])}

    problems = [f"규칙이 고르지만 팩에 없음: {p}" for p in sorted(want.keys() - have.keys())]
    problems += [f"팩에 있으나 규칙이 안 고름: {p}" for p in sorted(have.keys() - want.keys())]
    problems += [f"업스트림 blob 불일치: {p}" for p in sorted(want.keys() & have.keys()) if want[p] != have[p]]
    return problems


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":                    # cp949 콘솔은 한글 출력에서 죽는다 (nexus/cli.py 와 같은 패턴)
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:                          # noqa: BLE001 — 재구성 불가 환경이면 그냥 둔다
            pass

    ap = argparse.ArgumentParser(description="한국어 평가 코퍼스 팩 (SPEC-nexus-korean-retrieval-eval §4.1)")
    ap.add_argument("command", choices=["build", "verify", "check"])
    ap.add_argument("--pack-dir", type=Path, default=DEFAULT_PACK_DIR)
    args = ap.parse_args(argv)

    if args.command == "build":
        m = build(args.pack_dir)
        print(f"팩 생성: {m['count']}문서 · {m['bytes_total'] / 1024:.0f}KiB → {args.pack_dir}")
        return 0

    problems = verify(args.pack_dir) if args.command == "verify" else check(args.pack_dir)
    for p in problems[:50]:
        print(f"✗ {p}")
    if problems:
        print(f"문제 {len(problems)}건 — 이건 결과가 아니다.")
        return 1
    print(f"✓ {args.command} 통과 ({args.pack_dir})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
