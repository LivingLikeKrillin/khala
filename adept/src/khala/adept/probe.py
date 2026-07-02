"""Probe — generate N grounded comprehension questions from an artifact's content."""

from __future__ import annotations

import re

from khala.adept.llm import LLMClient
from khala.adept.models import Question

# Rules and their evidence grades live in adept/references/question-design.md +
# evidence.md (situation-first, coverage, response congruency — Pan & Rickard 2018;
# SJT/CIT — McDaniel 2001/2007, Flanagan 1954). Keep this prompt aligned with them.
_SYSTEM = (
    "You are a comprehension examiner. Given an artifact, first enumerate its "
    "critical claims — the decisions, invariants, and boundaries someone would get "
    "wrong at work without understanding it — then write exactly {n} questions that "
    "cover them (do not sample one corner of the artifact). Each question must: be a "
    "realistic WORK SITUATION (a proposal to judge, an objection to answer, a "
    "precondition to name, a symptom to diagnose) whose correct answer demonstrates "
    "understanding of THIS artifact's specific content, not generic domain knowledge; "
    "ask for ONE judgment (decision + reason); NEVER mention the artifact's name or "
    "frame the question as being about a document; and NEVER test recall trivia "
    "(edit history, citations, exact wording). Prefer basic judgments before edge "
    "cases so a person who understands the artifact mostly succeeds. Output one "
    "question per line, no numbering, no preamble."
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
