import re
from pathlib import Path

_SLUG_STRIP = re.compile(r"[^a-z0-9가-힣-]")
_SLUG_COLLAPSE = re.compile(r"-+")
_SLUG_CAP = 56  # leaves room for "-NN" collision suffix within a 60-char budget


def slugify(title: str) -> str:
    s = title.lower()
    s = s.replace(" ", "-")
    s = _SLUG_STRIP.sub("", s)
    s = _SLUG_COLLAPSE.sub("-", s).strip("-")
    return s[:_SLUG_CAP].strip("-")


def make_spec_id(specs_dir: Path, title: str, slug: str | None = None) -> str:
    base = slug if slug else slugify(title)
    candidate = f"SPEC-{base}"
    n = 2
    while (specs_dir / f"{candidate}.md").exists():
        candidate = f"SPEC-{base}-{n}"
        n += 1
    return candidate


_ADR_NUM = re.compile(r"^ADR-(\d{4})")


def next_adr_id(adr_dir: Path) -> str:
    highest = 0
    for p in adr_dir.glob("ADR-*.md"):
        m = _ADR_NUM.match(p.name)
        if m:
            highest = max(highest, int(m.group(1)))
    return f"ADR-{highest + 1:04d}"
