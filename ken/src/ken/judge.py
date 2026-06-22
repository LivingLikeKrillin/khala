"""Judge — LLM-as-judge grading of answers against the artifact. FAIL-CLOSED.

A vouch must be EARNED: any LLM error OR unparseable output yields
Verdict(passed=False, score=0.0) — never an auto-pass.
"""

from __future__ import annotations

import json

from ken.llm import LLMClient
from ken.models import Verdict

_SYSTEM = (
    "You are a strict grader. Given an artifact and a person's answers to grounded "
    "comprehension questions about it, judge whether the answers demonstrate genuine "
    "understanding of THIS artifact. Be strict: vague, generic, or evasive answers fail. "
    'Respond with ONLY a JSON object: {"passed": bool, "score": float (0-1), '
    '"rationale": str}. No prose outside the JSON.'
)


def _format_qa(qa_pairs: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"Q: {q}\nA: {a}" for q, a in qa_pairs)


def grade(text: str, qa_pairs: list[tuple[str, str]], llm: LLMClient) -> Verdict:
    """Grade answers; fail-closed on any LLM error or unparseable output."""
    user = f"Artifact:\n\n{text}\n\nQuestions and answers:\n\n{_format_qa(qa_pairs)}"
    try:
        raw = llm.generate(_SYSTEM, user)
    except Exception as exc:  # noqa: BLE001 — fail-closed on ANY LLM failure
        return Verdict(passed=False, score=0.0, rationale=f"llm_error: {exc}")

    try:
        data = json.loads(raw)
        return Verdict(
            passed=bool(data["passed"]),
            score=float(data["score"]),
            rationale=str(data.get("rationale", "")),
        )
    except Exception as exc:  # noqa: BLE001 — unparseable -> fail-closed
        return Verdict(passed=False, score=0.0, rationale=f"unparseable_verdict: {exc}")
