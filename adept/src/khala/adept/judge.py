"""Judge — LLM-as-judge grading of answers against the artifact. FAIL-CLOSED.

A vouch must be EARNED: any LLM error OR unparseable output yields
Verdict(passed=False, score=0.0) — never an auto-pass.
"""

from __future__ import annotations

import json
import re

from khala.adept.llm import LLMClient
from khala.adept.models import Verdict

# Rules and their evidence grades live in adept/references/grading.md + evidence.md.
# Keep this prompt aligned with them. The verdict schema is unchanged; the wrong-answer
# taxonomy code rides at the front of `rationale`.
_SYSTEM = (
    "You are a strict grader. The artifact is the answer key. Judge whether each "
    "answer reaches the artifact's own decision AND its reasoning — grade the essence, "
    "never exact wording. Ignore answer length and fluency entirely: a short correct "
    "judgment beats a long fluent hedge; vague, generic, or evasive answers fail. If "
    "the decision is right but the reasoning differs from the artifact's, pass with "
    "score <= 0.6. Start the rationale with exactly one wrong-answer code in brackets "
    "— [not-retrieved] principle known elsewhere but not applied, [overgeneralized] "
    "right pattern wrong case, [displaced] personal belief substituted for the "
    "artifact's position, [missing-rationale] right decision wrong/absent reason, "
    "[no-knowledge] blank or don't-know — or [ok] for a full pass. Respond with ONLY "
    'a JSON object: {"passed": bool, "score": float (0-1), "rationale": str}. No '
    "prose outside the JSON."
)


def _format_qa(qa_pairs: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"Q: {q}\nA: {a}" for q, a in qa_pairs)


def _parse_verdict_json(raw: str) -> dict:
    """Parse the model's JSON verdict, tolerating fenced/prose-wrapped output.

    Tries, in order: the raw string; the string with a leading/trailing markdown
    code fence (``` or ```json) stripped; the first ``{...}`` span found anywhere.
    Raises (json.JSONDecodeError) if none parse, so callers stay fail-closed.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    fenced = re.sub(r"^\s*```(?:json)?\s*\n?|\n?```\s*$", "", raw.strip())
    try:
        return json.loads(fenced)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise json.JSONDecodeError("no JSON object found", raw, 0)


def grade(text: str, qa_pairs: list[tuple[str, str]], llm: LLMClient) -> Verdict:
    """Grade answers; fail-closed on any LLM error or unparseable output."""
    user = f"Artifact:\n\n{text}\n\nQuestions and answers:\n\n{_format_qa(qa_pairs)}"
    try:
        raw = llm.generate(_SYSTEM, user)
    except Exception as exc:  # noqa: BLE001 — fail-closed on ANY LLM failure
        return Verdict(passed=False, score=0.0, rationale=f"llm_error: {exc}")

    try:
        data = _parse_verdict_json(raw)
        return Verdict(
            passed=bool(data["passed"]),
            score=float(data["score"]),
            rationale=str(data.get("rationale", "")),
        )
    except Exception as exc:  # noqa: BLE001 — unparseable -> fail-closed
        return Verdict(passed=False, score=0.0, rationale=f"unparseable_verdict: {exc}")
