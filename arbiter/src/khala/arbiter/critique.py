from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from typing import Protocol

from .artifacts import Artifact, Status
from .errors import CritiqueError
from .sidecar import Issue, Sidecar

RUBRIC = [
    "risky-assumption", "missing-invariant", "unverifiable-claim",
    "scope-creep", "adr-contradiction", "undefined", "untestable-requirement",
]


class Critic(Protocol):
    def find_issues(
        self, body: str, linked_adr_bodies: list[str], rubric: list[str]
    ) -> list[tuple[str, str, str]]:
        """Return list of (category, severity, description)."""


def critique(ledger, artifact_id: str, critic: Critic, now: Callable[[], str]) -> list[Issue]:
    art = Artifact.load(ledger._resolve(artifact_id))
    linked = []
    for adr_id in (art.meta.get("linked_adrs") or []):
        try:
            linked.append(Artifact.load(ledger._resolve(adr_id)).body)
        except Exception:  # noqa: BLE001 - missing link is non-fatal context
            continue
    try:
        raw = critic.find_issues(art.body, linked, RUBRIC)
    except Exception as e:  # noqa: BLE001 - fail closed regardless of cause
        raise CritiqueError(str(e)) from e
    issues = [
        Issue(f"I-{i + 1:03d}", cat, sev, desc, "open", None)
        for i, (cat, sev, desc) in enumerate(raw)
    ]
    sc = Sidecar(
        target=art.id, critiqued_hash=art.recompute_hash(), critiqued_at=now(),
        issues=issues, narrative="",
    )
    sc.write(ledger.reviews / f"{art.id}.md")
    art.meta["status"] = str(Status.IN_REVIEW)
    art.save()
    return issues


_PROMPT = (
    "You are an independent spec reviewer. Find concrete issues in the DESIGN DOC below, "
    "each tagged with one rubric category: {rubric}. Return ONLY a JSON array of objects "
    '{{"category","severity","description"}} where severity is high|medium|low. '
    "Check especially for contradictions with the LINKED ADRS.\n\n"
    "=== DESIGN DOC ===\n{body}\n\n=== LINKED ADRS ===\n{adrs}\n"
)


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def _unwrap_json(text: str) -> str:
    """모델 응답에서 JSON 배열만 꺼낸다.

    'Return ONLY a JSON array' 라고 지시해도 모델은 프롬프트가 길어지면 ```json 펜스로
    감싸거나 짧은 서두를 붙인다. 지시로 막을 수 없으니 파서가 견딘다. 잘린 응답은 여기서
    고쳐지지 않고 json.loads 에서 그대로 터진다 — fail closed 가 맞다.
    """
    t = text.strip()
    fenced = _FENCE.search(t)
    if fenced:
        t = fenced.group(1).strip()
    if not t.startswith("["):
        start = t.find("[")
        if start != -1:
            t = t[start:]
    return t


class AnthropicCritic:
    """LLM critic. The ``ANTHROPIC_API_KEY`` is read **lazily** — only when a critique is
    actually run — so constructing the critic (and therefore booting the MCP server) needs no
    key. Only the ``critique`` tool requires it; the other 9 Arbiter tools run keyless.
    An injected ``client`` bypasses the key entirely (offline/local + tests).
    """

    # max_tokens: 실측(SPEC-nexus-notion-reconciliation + 링크된 ADR-0002)에서 출력이 1823 토큰까지
    # 찼다. 2000 이면 조금만 더 긴 문서에서 잘리고, 잘린 JSON 은 CritiqueError 로 죽는다.
    def __init__(self, client=None, model: str = "claude-opus-4-8", max_tokens: int = 4096):
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    def _get_client(self):
        if self._client is None:
            key = os.environ.get("ANTHROPIC_API_KEY")
            if not key:
                raise CritiqueError(
                    "critique requires ANTHROPIC_API_KEY (the LLM reviewer); the other "
                    "Arbiter tools — record/approve/status/begin_implementation/check_gate/"
                    "publish — run without it. Set the key or inject a client."
                )
            import anthropic
            self._client = anthropic.Anthropic(api_key=key)
        return self._client

    def find_issues(
        self, body: str, linked_adr_bodies: list[str], rubric: list[str]
    ) -> list[tuple[str, str, str]]:
        prompt = _PROMPT.format(
            rubric=", ".join(rubric), body=body,
            adrs="\n---\n".join(linked_adr_bodies) or "(none)",
        )
        resp = self._get_client().messages.create(
            model=self._model, max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in resp.content if block.type == "text")
        data = json.loads(_unwrap_json(text))
        return [(d["category"], d["severity"], d["description"]) for d in data]
