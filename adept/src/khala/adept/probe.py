"""Probe — generate N grounded comprehension questions from an artifact's content."""

from __future__ import annotations

import re

from khala.adept.llm import LLMClient
from khala.adept.models import Question

_SYSTEM = (
    "You are a comprehension examiner. Given an artifact, generate exactly {n} "
    "grounded comprehension questions that can ONLY be answered correctly by someone "
    "who genuinely understands THIS artifact's specific content (not generic domain "
    "knowledge). Output one question per line, no numbering, no preamble."
)


def make_questions(text: str, n: int, llm: LLMClient) -> list[Question]:
    """Ask the LLM for n grounded questions; parse non-empty lines into Questions."""
    system = _SYSTEM.format(n=n)
    user = f"Artifact:\n\n{text}"
    raw = llm.generate(system, user)
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    # Strip any leading enumeration/bullet prefix the model added despite the
    # instruction, then cap at n so callers get at most n questions.
    cleaned = [re.sub(r"^\s*(\d+[.)]|[-*])\s*", "", ln) for ln in lines]
    return [Question(text=ln) for ln in cleaned[:n]]
