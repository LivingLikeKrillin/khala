"""Regenerate the committed dependency constraints for every Python subproject.

Why this exists
---------------
CI installs with plain `pip install -e ...`, which re-resolves the whole dependency
tree on every run. On 2026-08-01 that turned master red: `mcp` 2.0.0 shipped, dropped
`mcp.server.fastmcp`, and two documentation PRs that touched no code failed with
`ModuleNotFoundError`. The version we tested was never the version we declared.

Each subproject now carries a `constraints.txt` that pins the fully resolved set.
`pyproject.toml` stays the source of truth for *what is required*; `constraints.txt`
records *which versions we actually tested*. pip applies it with `-c`.

Regenerate with `task deps:lock` (or `python scripts/lock_deps.py`) whenever a
dependency is added, removed, or deliberately upgraded, and commit the result.

Resolution is universal (`--universal`): one file carries markers for every platform
and Python version, so the same pins serve CI on Linux/3.13, the nexus image on
Linux/3.11, and local development on Windows or macOS.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Extras to resolve per subproject: the union of every extra set installed anywhere
# (CI jobs, the Dockerfile, Taskfile targets). A constraints file only pins versions —
# it never causes a package to be installed — so a superset is safe and keeps the
# optional surfaces pinned consistently with the default one.
PROJECTS: dict[str, list[str]] = {
    "nexus": ["dev", "mcp", "a2a", "slack", "notion"],
    "arbiter": ["dev"],
    "probe": ["dev"],
    "adept": ["dev", "postgres"],
    "adept-web/api": ["dev"],
}

# uv emits path dependencies as editable requirements (`-e ../../adept`). pip refuses
# editable entries in a constraints file, so they are stripped and replaced with a note.
# The path dependency is installed explicitly by CI and pinned by its own constraints file.
# Requirements satisfied by another subproject in this repo rather than by PyPI. They are
# installed editable from a path and pinned by that subproject's own constraints file.
PATH_DEPENDENCIES = {"khala-adept"}

EDITABLE_NOTE = (
    "# Editable path dependencies that uv emitted here are stripped by scripts/lock_deps.py:\n"
    "# pip rejects editable entries in a constraints file. They are installed explicitly\n"
    "# (e.g. `pip install -e ../../adept -e .`) and pinned by their own constraints.txt.\n"
)


def compile_project(rel_path: str, extras: list[str]) -> bool:
    """Compile one subproject's constraints. Returns True if the file is unchanged."""
    project_dir = REPO_ROOT / rel_path
    out_path = project_dir / "constraints.txt"
    before = out_path.read_text(encoding="utf-8") if out_path.exists() else None

    # No -o: uv writes the requirements to stdout by default, and we post-process before
    # writing. (`-o -` is not a stdout idiom here — uv creates a file literally named `-`.)
    # No --quiet either: it suppresses the requirements themselves, leaving a header with
    # nothing under it — a constraints file that constrains nothing while looking like it
    # does. The zero-pin guard below is the backstop for both mistakes.
    cmd = [
        sys.executable, "-m", "uv", "pip", "compile", "pyproject.toml", "--universal",
    ]
    for extra in extras:
        cmd += ["--extra", extra]

    result = subprocess.run(cmd, cwd=project_dir, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(f"\n{rel_path}: uv pip compile failed\n{result.stderr}\n")
        raise SystemExit(1)

    rendered = strip_editables(result.stdout, rel_path, extras)
    pins = count_pins(rendered)
    if pins == 0:
        sys.stderr.write(
            f"\n{rel_path}: resolution produced 0 pins. Refusing to write an empty "
            f"constraints file — it would constrain nothing while looking like it does.\n"
        )
        raise SystemExit(1)

    unchanged = before == rendered

    out_path.write_text(rendered, encoding="utf-8", newline="\n")
    # ASCII only: this prints to a cp949 console on the Windows dev machine.
    print(f"{rel_path}/constraints.txt: {pins} pins{'' if not unchanged else ' (unchanged)'}")
    return unchanged


def count_pins(rendered: str) -> int:
    """Number of actual `name==version` lines, ignoring comments and provenance blocks."""
    return sum(1 for line in rendered.splitlines() if line[:1].isalnum() and "==" in line)


def strip_editables(rendered: str, rel_path: str, extras: list[str]) -> str:
    """Drop `-e <path>` entries (and their `# via` continuation lines) from uv's output."""
    lines = rendered.splitlines(keepends=True)
    kept: list[str] = []
    stripped_any = False
    skipping = False

    for line in lines:
        if line.startswith("-e "):
            skipping = True
            stripped_any = True
            continue
        # uv indents the `# via ...` provenance block under each requirement.
        if skipping and line.startswith((" ", "\t")):
            continue
        skipping = False
        kept.append(line)

    body = "".join(kept)
    extra_flags = "".join(f" --extra {e}" for e in extras)
    header = (
        "# Autogenerated by scripts/lock_deps.py — do not edit by hand.\n"
        f"# Regenerate with `task deps:lock`. Source: {rel_path}/pyproject.toml"
        f"{extra_flags}\n"
        "#\n"
        "# Applied by CI (and the nexus image) via `pip install ... -c constraints.txt` so that\n"
        "# the versions we test are the versions we declared, not whatever resolved that morning.\n"
    )
    if stripped_any:
        header += "#\n" + EDITABLE_NOTE
    # uv's own two-line provenance header is replaced by the one above.
    body = "".join(
        line for line in body.splitlines(keepends=True)
        if not line.startswith("# This file was autogenerated by uv")
        and not line.startswith("#    uv pip compile")
    )
    return header + body.lstrip("\n")


def check_project(rel_path: str, extras: list[str]) -> list[str]:
    """Offline check that constraints.txt still covers pyproject.toml. Returns problems.

    Deliberately does NOT re-resolve. A check that recompiles against live PyPI fails the
    moment anything upstream publishes a release — which is the exact nondeterminism these
    constraints exist to remove. So this asks only the questions drift actually poses:

      1. is every declared requirement pinned, and is the pin legal under its specifier?
      2. does every declared requirement carry an upper bound?

    (2) covers the half constraints cannot reach. constraints.txt governs CI; the bound is
    what governs a fresh `pip install` outside it — a new checkout, a rebuilt image, a
    developer's machine. `mcp>=1.2.0` with no ceiling is how 2.0.0 got in.
    """
    import tomllib

    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    project_dir = REPO_ROOT / rel_path
    constraints_path = project_dir / "constraints.txt"
    problems: list[str] = []

    if not constraints_path.exists():
        return [f"{rel_path}/constraints.txt is missing - run `task deps:lock`"]

    pinned: dict[str, str] = {}
    for line in constraints_path.read_text(encoding="utf-8").splitlines():
        if not line[:1].isalnum() or "==" not in line:
            continue
        spec = line.split(";", 1)[0].strip()  # drop the environment marker
        name, _, version = spec.partition("==")
        pinned[canonicalize_name(name.strip())] = version.strip()

    if not pinned:
        return [f"{rel_path}/constraints.txt has no pins - run `task deps:lock`"]

    with (project_dir / "pyproject.toml").open("rb") as fh:
        pyproject = tomllib.load(fh)

    declared = list(pyproject["project"].get("dependencies", []))
    optional = pyproject["project"].get("optional-dependencies", {})
    for extra in extras:
        declared += list(optional.get(extra, []))

    for raw in declared:
        req = Requirement(raw)
        key = canonicalize_name(req.name)

        # An upper bound is required on everything resolved from an index. `==` counts:
        # an exact pin is a ceiling too.
        if key not in PATH_DEPENDENCIES and not any(
            spec.operator in ("<", "<=", "==", "===", "~=") for spec in req.specifier
        ):
            problems.append(
                f"{rel_path}: `{req.name}` has no upper bound. Add one at the next major "
                f"above the version we test (see CONVENTIONS.md) - an unbounded requirement "
                f"is how mcp 2.0.0 got in."
            )

        version = pinned.get(key)
        if version is None:
            # A path dependency resolved from another subproject is pinned by that
            # subproject's own constraints file, not this one.
            if key in PATH_DEPENDENCIES:
                continue
            problems.append(
                f"{rel_path}: `{req.name}` is declared in pyproject.toml but not pinned in "
                f"constraints.txt - run `task deps:lock`"
            )
            continue
        if req.specifier and not req.specifier.contains(version, prereleases=True):
            problems.append(
                f"{rel_path}: `{req.name}` is pinned to {version}, which violates the declared "
                f"`{req.specifier}` - run `task deps:lock`"
            )

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Offline: verify every declared requirement is pinned and the pin satisfies its "
            "specifier. Does not re-resolve and does not write. Exits 1 on drift."
        ),
    )
    args = parser.parse_args()

    if args.check:
        problems = [p for path, extras in PROJECTS.items() for p in check_project(path, extras)]
        for problem in problems:
            sys.stderr.write(problem + "\n")
        if problems:
            return 1
        print(f"constraints are in sync with pyproject.toml ({len(PROJECTS)} subprojects)")
        return 0

    for path, extras in PROJECTS.items():
        compile_project(path, extras)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
